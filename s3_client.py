"""S3 client for the local MinIO object store (Lab 8-9, Task 2).

MinIO must be running first:  docker compose up -d
Quick demo (uploads one object with custom metadata):  python s3_client.py
"""
import os
import tempfile
import time

import boto3
from botocore.client import Config

s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9001',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadminpassword',
    config=Config(signature_version='s3v4'),
    region_name='us-east-1'
)

BUCKET_NAME = 'distributed-course-bucket'


def init_storage():
    """Create the bucket if it does not exist yet."""
    buckets = [b['Name'] for b in s3.list_buckets()['Buckets']]
    if BUCKET_NAME not in buckets:
        s3.create_bucket(Bucket=BUCKET_NAME)


def upload_object(key_name, file_path, metadata=None):
    """Upload a local file as an object with custom metadata.
    Returns how many seconds the upload took."""
    start_time = time.time()
    s3.upload_file(
        Filename=file_path,
        Bucket=BUCKET_NAME,
        Key=key_name,
        ExtraArgs={'Metadata': metadata or {}}
    )
    return time.time() - start_time


def read_object_metadata(key_name):
    """HEAD the object and return its custom metadata.
    S3 stores user metadata keys in lower case."""
    response = s3.head_object(Bucket=BUCKET_NAME, Key=key_name)
    return response['Metadata']


def read_object(key_name):
    """GET a whole object. Returns (data, seconds). Used by the latency comparison."""
    start = time.perf_counter()
    data = s3.get_object(Bucket=BUCKET_NAME, Key=key_name)['Body'].read()
    return data, time.perf_counter() - start


def list_objects(prefix=''):
    """All keys that start with `prefix` (the flat namespace has no real folders)."""
    keys = []
    paginator = s3.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        keys.extend(item['Key'] for item in page.get('Contents', []))
    return keys


def delete_object(key_name):
    s3.delete_object(Bucket=BUCKET_NAME, Key=key_name)


if __name__ == '__main__':
    init_storage()
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as tmp:
        tmp.write('Hello from the CSS4004 storage lab\n')
        path = tmp.name
    try:
        seconds = upload_object(
            'reports/demo.txt', path,
            {'author': 'miras', 'course': 'CSS4004', 'lab': '8-9'})
    finally:
        os.remove(path)
    print(f'uploaded reports/demo.txt in {seconds:.3f} s')
    print('metadata:', read_object_metadata('reports/demo.txt'))
    print('objects in bucket:', list_objects())
