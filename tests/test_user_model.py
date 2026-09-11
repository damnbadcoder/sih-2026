from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint

from app.db.base import Base
from app.models import User


def test_user_importable():
    assert User.__tablename__ == "users"


def test_user_registered_on_metadata():
    assert "users" in Base.metadata.tables


def test_users_table_columns():
    table = Base.metadata.tables["users"]
    columns = {col.name: col for col in table.columns}
    assert set(columns) == {
        "id",
        "email",
        "password_hash",
        "is_active",
        "created_at",
        "updated_at",
    }


def test_users_table_constraints():
    table = Base.metadata.tables["users"]
    unique = {
        constraint.columns.keys()[0]
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "email" in unique
    primary = {
        constraint.columns.keys()[0]
        for constraint in table.constraints
        if isinstance(constraint, PrimaryKeyConstraint)
    }
    assert "id" in primary


def test_users_columns_not_nullable():
    table = Base.metadata.tables["users"]
    for name in ("id", "email", "password_hash", "is_active", "created_at", "updated_at"):
        assert table.columns[name].nullable is False, f"{name} should be NOT NULL"


def test_user_id_is_uuid():
    table = Base.metadata.tables["users"]
    column_type = table.columns["id"].type.__class__.__name__
    assert column_type == "UUID"