"""Lab 8-9, Task 3: integration tests against the local MinIO.

MinIO must be running first:  docker compose up -d
Run:  python -m pytest tests -v
"""
import hashlib
import os
import sys
import uuid

import boto3
import pytest
from botocore.client import Config
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import s3_client as storage  # noqa: E402

BUCKET = 'distributed-course-bucket'


@pytest.fixture(scope="module")
def s3_client():
    return boto3.client(
        's3',
        endpoint_url='http://localhost:9001',
        aws_access_key_id='minioadmin',
        aws_secret_access_key='minioadminpassword',
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )


@pytest.fixture(scope="module", autouse=True)
def bucket():
    """Make sure the bucket exists before any test runs."""
    storage.init_storage()


@pytest.fixture
def prefix(s3_client):
    """A unique key prefix for one test; everything under it is deleted afterwards."""
    name = f"tests/{uuid.uuid4().hex}/"
    yield name
    for key in storage.list_objects(name):
        s3_client.delete_object(Bucket=BUCKET, Key=key)


# --------------------------------------------------------------------------
# Tests from the assignment
# --------------------------------------------------------------------------
def test_s3_bucket_existence(s3_client):
    buckets = [b['Name'] for b in s3_client.list_buckets()['Buckets']]
    assert 'distributed-course-bucket' in buckets


def test_s3_object_upload_and_read(s3_client):
    key = "test_dir/sample.txt"
    content = b"Stream Data Content"
    s3_client.put_object(Bucket='distributed-course-bucket', Key=key, Body=content)
    obj = s3_client.get_object(Bucket='distributed-course-bucket', Key=key)
    assert obj['Body'].read() == content


# --------------------------------------------------------------------------
# Our own tests: metadata, object semantics, bucket integrity
# --------------------------------------------------------------------------
def test_custom_metadata_roundtrip(prefix, tmp_path):
    src = tmp_path / "note.txt"
    src.write_text("hello")
    key = prefix + "note.txt"

    storage.upload_object(key, str(src), {"Author": "Miras", "Lab": "8-9"})
    meta = storage.read_object_metadata(key)

    # S3 stores user metadata keys in lower case
    assert meta["author"] == "Miras"
    assert meta["lab"] == "8-9"


def test_head_object_reports_size_without_downloading(s3_client, prefix):
    key = prefix + "blob.bin"
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=b"x" * 1234)

    head = s3_client.head_object(Bucket=BUCKET, Key=key)

    assert head["ContentLength"] == 1234


def test_overwrite_replaces_the_whole_object(s3_client, prefix):
    key = prefix + "doc.txt"
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=b"version one")
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=b"v2")

    body = s3_client.get_object(Bucket=BUCKET, Key=key)["Body"].read()

    assert body == b"v2"   # objects are immutable: a PUT replaces the whole value


def test_flat_namespace_folders_are_just_key_prefixes(s3_client, prefix):
    for name in ("a/1.txt", "a/2.txt", "b/3.txt"):
        s3_client.put_object(Bucket=BUCKET, Key=prefix + name, Body=b"x")

    assert sorted(storage.list_objects(prefix + "a/")) == [
        prefix + "a/1.txt", prefix + "a/2.txt"]
    assert len(storage.list_objects(prefix)) == 3
    listing = s3_client.list_objects_v2(Bucket=BUCKET, Prefix=prefix, Delimiter="/")
    folders = {p["Prefix"] for p in listing["CommonPrefixes"]}
    assert folders == {prefix + "a/", prefix + "b/"}


def test_deleted_object_is_gone(s3_client, prefix):
    key = prefix + "gone.txt"
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=b"temporary")
    s3_client.delete_object(Bucket=BUCKET, Key=key)

    with pytest.raises(ClientError) as err:
        s3_client.get_object(Bucket=BUCKET, Key=key)

    assert err.value.response["Error"]["Code"] == "NoSuchKey"


def test_head_of_missing_object_is_404(s3_client, prefix):
    with pytest.raises(ClientError) as err:
        s3_client.head_object(Bucket=BUCKET, Key=prefix + "does-not-exist")

    assert err.value.response["Error"]["Code"] in ("404", "NoSuchKey")


def test_large_file_roundtrip_is_intact(s3_client, prefix, tmp_path):
    """9 MB is above boto3's 8 MB multipart threshold, so this is a multipart upload."""
    data = os.urandom(9 * 1024 * 1024)
    src = tmp_path / "big.bin"
    src.write_bytes(data)
    key = prefix + "big.bin"

    storage.upload_object(key, str(src), {"purpose": "integrity"})
    got = s3_client.get_object(Bucket=BUCKET, Key=key)["Body"].read()

    assert hashlib.sha256(got).hexdigest() == hashlib.sha256(data).hexdigest()
