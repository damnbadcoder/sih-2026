from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import engine
from app.models import Artifact, InputFile, Job, User


def test_input_file_importable():
    assert InputFile.__tablename__ == "input_files"


def test_input_files_registered_on_metadata():
    assert "input_files" in Base.metadata.tables


def test_input_files_table_columns():
    table = Base.metadata.tables["input_files"]
    columns = {col.name: col for col in table.columns}
    assert set(columns) == {
        "id",
        "job_id",
        "original_filename",
        "stored_filename",
        "content_type",
        "file_size",
        "storage_path",
        "created_at",
    }


def test_input_files_columns_not_nullable():
    table = Base.metadata.tables["input_files"]
    for name in (
        "id",
        "job_id",
        "original_filename",
        "stored_filename",
        "content_type",
        "file_size",
        "storage_path",
        "created_at",
    ):
        assert table.columns[name].nullable is False, f"{name} should be NOT NULL"


def test_input_file_ids_are_uuid():
    table = Base.metadata.tables["input_files"]
    assert table.columns["id"].type.__class__.__name__ == "UUID"
    assert table.columns["job_id"].type.__class__.__name__ == "UUID"


def test_input_files_column_types():
    table = Base.metadata.tables["input_files"]
    assert table.columns["file_size"].type.__class__.__name__ == "Integer"
    assert table.columns["original_filename"].type.__class__.__name__ == "String"
    assert table.columns["storage_path"].type.__class__.__name__ == "String"


def test_input_files_job_foreign_key_references_jobs():
    foreign_key = next(iter(Base.metadata.tables["input_files"].foreign_keys))
    assert foreign_key.parent.name == "job_id"
    assert foreign_key.column.table.name == "jobs"
    assert foreign_key.column.name == "id"
    assert foreign_key.ondelete == "CASCADE"


def test_input_files_job_id_indexed():
    table = Base.metadata.tables["input_files"]
    assert any([col.name for col in index.columns] == ["job_id"] for index in table.indexes)


def test_job_input_files_relationship():
    relationship = inspect(Job).relationships["input_files"]
    assert relationship.back_populates == "job"
    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade
    assert relationship.passive_deletes is True


def test_input_file_job_relationship():
    relationship = inspect(InputFile).relationships["job"]
    assert relationship.back_populates == "input_files"


def test_relationships_sets():
    assert set(inspect(User).relationships.keys()) == {"jobs"}
    assert set(inspect(Job).relationships.keys()) == {"user", "artifacts", "input_files"}
    assert set(inspect(Artifact).relationships.keys()) == {"job"}
    assert set(inspect(InputFile).relationships.keys()) == {"job"}


async def test_live_schema_has_input_files():
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
    assert "input_files" in tables