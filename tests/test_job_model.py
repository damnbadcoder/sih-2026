from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import engine
from app.models import Artifact, Job, User


def test_job_importable():
    assert Job.__tablename__ == "jobs"


def test_artifact_importable():
    assert Artifact.__tablename__ == "artifacts"


def test_jobs_and_artifacts_registered_on_metadata():
    assert "jobs" in Base.metadata.tables
    assert "artifacts" in Base.metadata.tables


def test_jobs_table_columns():
    table = Base.metadata.tables["jobs"]
    columns = {col.name: col for col in table.columns}
    assert set(columns) == {"id", "user_id", "status", "config", "created_at", "updated_at"}


def test_artifacts_table_columns():
    table = Base.metadata.tables["artifacts"]
    columns = {col.name: col for col in table.columns}
    assert set(columns) == {"id", "job_id", "artifact_type", "file_path", "created_at"}


def test_jobs_columns_not_nullable():
    table = Base.metadata.tables["jobs"]
    for name in ("id", "user_id", "status", "created_at", "updated_at"):
        assert table.columns[name].nullable is False, f"{name} should be NOT NULL"


def test_artifacts_columns_not_nullable():
    table = Base.metadata.tables["artifacts"]
    for name in ("id", "job_id", "artifact_type", "file_path", "created_at"):
        assert table.columns[name].nullable is False, f"{name} should be NOT NULL"


def test_job_and_user_ids_are_uuid():
    table = Base.metadata.tables["jobs"]
    assert table.columns["id"].type.__class__.__name__ == "UUID"
    assert table.columns["user_id"].type.__class__.__name__ == "UUID"


def test_artifact_ids_are_uuid():
    table = Base.metadata.tables["artifacts"]
    assert table.columns["id"].type.__class__.__name__ == "UUID"
    assert table.columns["job_id"].type.__class__.__name__ == "UUID"


def test_jobs_config_is_nullable_jsonb():
    table = Base.metadata.tables["jobs"]
    assert table.columns["config"].type.__class__.__name__ == "JSONB"
    assert table.columns["config"].nullable is True


def test_jobs_user_foreign_key_references_users():
    foreign_key = next(iter(Base.metadata.tables["jobs"].foreign_keys))
    assert foreign_key.parent.name == "user_id"
    assert foreign_key.column.table.name == "users"
    assert foreign_key.column.name == "id"
    assert foreign_key.ondelete == "CASCADE"


def test_artifacts_job_foreign_key_references_jobs():
    foreign_key = next(iter(Base.metadata.tables["artifacts"].foreign_keys))
    assert foreign_key.parent.name == "job_id"
    assert foreign_key.column.table.name == "jobs"
    assert foreign_key.column.name == "id"
    assert foreign_key.ondelete == "CASCADE"


def test_jobs_user_id_indexed():
    table = Base.metadata.tables["jobs"]
    assert any([col.name for col in index.columns] == ["user_id"] for index in table.indexes)


def test_artifacts_job_id_indexed():
    table = Base.metadata.tables["artifacts"]
    assert any([col.name for col in index.columns] == ["job_id"] for index in table.indexes)


def test_jobs_status_has_created_default():
    table = Base.metadata.tables["jobs"]
    assert table.columns["status"].default is not None
    assert table.columns["status"].default.arg == "created"
    assert table.columns["status"].server_default is not None


def test_jobs_status_check_constraint():
    table = Base.metadata.tables["jobs"]
    checks = [c for c in table.constraints if c.name == "ck_jobs_status"]
    assert checks
    text = str(checks[0].sqltext)
    for value in ("created", "processing", "completed", "failed"):
        assert value in text


def test_user_jobs_relationship():
    relationship = inspect(User).relationships["jobs"]
    assert relationship.back_populates == "user"
    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade
    assert relationship.passive_deletes is True


def test_job_user_relationship():
    relationship = inspect(Job).relationships["user"]
    assert relationship.back_populates == "jobs"


def test_job_artifacts_relationship():
    relationship = inspect(Job).relationships["artifacts"]
    assert relationship.back_populates == "job"
    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade
    assert relationship.passive_deletes is True


def test_artifact_job_relationship():
    relationship = inspect(Artifact).relationships["job"]
    assert relationship.back_populates == "artifacts"


def test_relationships_sets():
    assert set(inspect(User).relationships.keys()) == {"jobs", "transformations"}
    assert set(inspect(Job).relationships.keys()) == {"user", "artifacts", "input_files"}
    assert set(inspect(Artifact).relationships.keys()) == {"job"}


async def test_live_schema_has_jobs_and_artifacts():
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
    assert {"jobs", "artifacts"} <= tables