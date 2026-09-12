import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import async_session_factory
from app.models.blueprint import Blueprint
from app.models.deliverable import Deliverable
from app.models.transformation import Transformation
from app.models.user import User
from app.services.blueprints import BlueprintService
from app.services.deliverables import DeliverableService
from app.services.errors import NotFoundError, OutputFormatError
from app.services.transformations import TransformationService

CREATED_EMAILS: list[str] = []


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


async def cleanup_created_users() -> None:
    if not CREATED_EMAILS:
        return
    async with async_session_factory() as db:
        await db.execute(delete(User).where(User.email.in_(CREATED_EMAILS)))
        await db.commit()
    CREATED_EMAILS.clear()


@pytest.fixture(autouse=True)
async def _cleanup_created():
    yield
    await cleanup_created_users()


async def _make_user(prefix: str) -> User:
    email = unique_email(prefix)
    CREATED_EMAILS.append(email)
    async with async_session_factory() as db:
        user = User(email=email, password_hash="test-hash")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _make_transformation(user: User) -> Transformation:
    async with async_session_factory() as db:
        transformation = Transformation(user_id=user.id, status="draft")
        db.add(transformation)
        await db.commit()
        await db.refresh(transformation)
        return transformation


async def test_blueprint_versions_are_distinct_and_prior_content_unchanged():
    owner = await _make_user("blueprint")
    transformation = await _make_transformation(owner)
    service = BlueprintService()

    async with async_session_factory() as db:
        first = await service.create_version(
            db, owner, transformation.id, "advisory", "DRAFT VERSION 1"
        )
        second = await service.create_version(
            db, owner, transformation.id, "advisory", "REVISED VERSION 2"
        )
        assert first.version == 1
        assert second.version == 2
        assert first.content == "DRAFT VERSION 1"
        assert second.content == "REVISED VERSION 2"

        versions = await service.list_versions(db, owner, transformation.id, "advisory")
        assert [v.version for v in versions] == [1, 2]
        assert versions[0].content == "DRAFT VERSION 1"
        assert versions[1].content == "REVISED VERSION 2"
        assert versions[0].is_current is False
        assert versions[1].is_current is True

    async with async_session_factory() as db:
        stored = await db.scalar(
            select(Blueprint).where(
                Blueprint.transformation_id == transformation.id,
                Blueprint.version == 1,
            )
        )
        assert stored is not None
        assert stored.content == "DRAFT VERSION 1"


async def test_blueprint_approve_sets_approved_at():
    owner = await _make_user("blueprintappr")
    transformation = await _make_transformation(owner)
    async with async_session_factory() as db:
        blueprint = await BlueprintService().create_version(
            db, owner, transformation.id, "playbook", "PLAYBOOK", approve=True
        )
        assert blueprint.is_current is True
        assert blueprint.approved_at is not None


async def test_blueprint_rejects_unknown_output_format():
    owner = await _make_user("blueprintfmt")
    transformation = await _make_transformation(owner)
    async with async_session_factory() as db:
        with pytest.raises(OutputFormatError):
            await BlueprintService().create_version(
                db, owner, transformation.id, "bogus", "CONTENT"
            )


async def test_blueprint_rejects_foreign_transformation():
    owner = await _make_user("blueprintown")
    other = await _make_user("blueprintforeign")
    transformation = await _make_transformation(other)
    async with async_session_factory() as db:
        with pytest.raises(NotFoundError):
            await BlueprintService().create_version(
                db, owner, transformation.id, "advisory", "CONTENT"
            )


async def test_deliverable_revisions_are_distinct_and_prior_content_unchanged():
    owner = await _make_user("deliverable")
    transformation = await _make_transformation(owner)
    service = DeliverableService()

    async with async_session_factory() as db:
        first = await service.create_revision(
            db,
            owner,
            transformation.id,
            "exec_summary",
            "EXEC SUMMARY V1",
            generation_metadata={"model": "mock", "attempt": 1},
        )
        second = await service.create_revision(
            db, owner, transformation.id, "exec_summary", "EXEC SUMMARY V2"
        )
        assert first.revision == 1
        assert second.revision == 2
        assert first.content == "EXEC SUMMARY V1"
        assert second.content == "EXEC SUMMARY V2"
        assert first.generation_metadata["attempt"] == 1

        revisions = await service.list_revisions(
            db, owner, transformation.id, "exec_summary"
        )
        assert [r.revision for r in revisions] == [1, 2]
        assert revisions[0].content == "EXEC SUMMARY V1"
        assert revisions[1].content == "EXEC SUMMARY V2"
        assert revisions[0].is_current is False
        assert revisions[1].is_current is True

    async with async_session_factory() as db:
        stored = await db.scalar(
            select(Deliverable).where(
                Deliverable.transformation_id == transformation.id,
                Deliverable.revision == 1,
            )
        )
        assert stored is not None
        assert stored.content == "EXEC SUMMARY V1"


async def test_deliverable_rejects_unknown_output_format_and_foreign_owner():
    owner = await _make_user("deliverablefmt")
    other = await _make_user("deliverableforeign")
    transformation = await _make_transformation(other)
    async with async_session_factory() as db:
        with pytest.raises(OutputFormatError):
            await DeliverableService().create_revision(
                db, owner, transformation.id, "bogus", "CONTENT"
            )
        with pytest.raises(NotFoundError):
            await DeliverableService().create_revision(
                db, owner, transformation.id, "advisory", "CONTENT"
            )


async def test_transformation_service_is_ownership_scoped():
    owner = await _make_user("transformscoped")
    other = await _make_user("transformother")
    transformation = await _make_transformation(owner)
    async with async_session_factory() as db:
        service = TransformationService()
        with pytest.raises(NotFoundError):
            await service.get_for_user(db, other, transformation.id)
        owned = await service.get_for_user(db, owner, transformation.id)
        assert owned.id == transformation.id