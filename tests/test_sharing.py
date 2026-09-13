# tests/test_sharing.py

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import async_session_factory, engine
from app.db.base import Base
from app.models.user import User
from app.models.transformation import Transformation
from app.models.share_link import ShareLink
from app.services.sharing import SharingService


@pytest.fixture(autouse=True, scope="module")
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_create_and_resolve_share_link():
    async with async_session_factory() as db:
        user = User(id=uuid.uuid4(), email=f"user_{uuid.uuid4().hex[:6]}@example.com", password_hash="hash")
        db.add(user)
        await db.commit()

        trans = Transformation(id=uuid.uuid4(), user_id=user.id, tlp="green")
        db.add(trans)
        await db.commit()

        link = await SharingService.create_share_link(
            db=db,
            transformation_id=trans.id,
            user_id=user.id,
            tenant_id=uuid.uuid4(),
            permission="read",
        )
        assert link.token is not None
        assert link.permission == "read"

        resolved = await SharingService.resolve_share_link(db, link.token)
        assert resolved.id == link.id
        assert resolved.use_count == 1


@pytest.mark.asyncio
async def test_tlp_red_sharing_blocked():
    async with async_session_factory() as db:
        user = User(id=uuid.uuid4(), email=f"user_{uuid.uuid4().hex[:6]}@example.com", password_hash="hash")
        db.add(user)
        await db.commit()

        trans = Transformation(id=uuid.uuid4(), user_id=user.id, tlp="red")
        db.add(trans)
        await db.commit()

        with pytest.raises(ValueError, match="TLP:RED"):
            await SharingService.create_share_link(
                db=db,
                transformation_id=trans.id,
                user_id=user.id,
                tenant_id=uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_share_link_endpoint():
    async with async_session_factory() as db:
        user = User(id=uuid.uuid4(), email=f"user_{uuid.uuid4().hex[:6]}@example.com", password_hash="hash")
        db.add(user)
        await db.commit()

        trans = Transformation(id=uuid.uuid4(), user_id=user.id, tlp="green")
        db.add(trans)
        await db.commit()

        trans_id = trans.id
        user_id = user.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post(
            f"/api/v1/transformations/{trans_id}/share?current_user_id={user_id}",
            json={"permission": "write", "requires_auth": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["permission"] == "write"
        token = data["token"]

        resolve_res = await ac.get(f"/api/v1/share/resolve/{token}")
        assert resolve_res.status_code == 200
        assert resolve_res.json()["token"] == token