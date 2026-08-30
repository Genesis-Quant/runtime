from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pandas as pd

from runtime.utils.manage import (
    RESULT_MANIFEST_FILENAME,
    write_parquet_result,
    write_result_manifest,
)
from runtime.utils.storage import ObjectStorage


def test_local_writer_persists_metadata_manifest(tmp_path: Path) -> None:
    data = pd.DataFrame(
        {
            "code": ["000001.SZ", "600000.SH"],
            "value": [1.25, 2.5],
        }
    )

    written = write_parquet_result(
        data,
        "query.parquet",
        output_target=tmp_path,
        storage=None,
    )
    write_result_manifest(
        tmp_path,
        None,
        {"data": ("query.parquet", written)},
    )

    parquet = tmp_path / "query.parquet"
    manifest = json.loads(
        (tmp_path / RESULT_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    entry = manifest["files"]["data"]
    assert manifest["version"] == 1
    assert entry["filename"] == "query.parquet"
    assert entry["size"] == parquet.stat().st_size
    assert entry["row_count"] == 2
    assert entry["snapshot_token"] is None
    assert entry["sha256"] == hashlib.sha256(parquet.read_bytes()).hexdigest()
    assert [column["name"] for column in entry["columns"]] == ["code", "value"]
    assert datetime.fromisoformat(entry["modified_at"]).tzinfo is not None


def test_cloud_writer_uploads_parquet_and_small_manifest() -> None:
    client = FakeS3Client()
    storage = ObjectStorage(client, "bucket", "root")
    data = pd.DataFrame({"code": ["000001.SZ"], "value": [3.0]})

    written = write_parquet_result(
        data,
        "query.parquet",
        output_target="query/workspace/output",
        storage=storage,
    )
    write_result_manifest(
        "query/workspace/output",
        storage,
        {"data": ("query.parquet", written)},
    )

    parquet_key = "root/query/workspace/output/query.parquet"
    manifest_key = f"root/query/workspace/output/{RESULT_MANIFEST_FILENAME}"
    manifest = json.loads(client.objects[manifest_key])
    entry = manifest["files"]["data"]
    assert written.location == f"s3://bucket/{parquet_key}"
    assert entry["size"] == len(client.objects[parquet_key])
    assert entry["row_count"] == 1
    assert entry["snapshot_token"] == "cloud:fixture-etag:"
    assert entry["sha256"] == hashlib.sha256(client.objects[parquet_key]).hexdigest()
    assert client.content_types[manifest_key] == "application/json"


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.modified_at = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)

    def upload_fileobj(
        self,
        source: object,
        bucket: str,
        key: str,
        *,
        ExtraArgs: dict[str, str],
    ) -> None:
        assert bucket == "bucket"
        self.objects[key] = source.read()
        self.content_types[key] = ExtraArgs["ContentType"]

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        assert Bucket == "bucket"
        return {
            "ContentLength": len(self.objects[Key]),
            "LastModified": self.modified_at,
            "ETag": '"fixture-etag"',
        }

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        assert Bucket == "bucket"
        self.objects[Key] = Body
        self.content_types[Key] = ContentType
