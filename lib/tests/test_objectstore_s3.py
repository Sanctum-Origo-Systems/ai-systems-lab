import io

import boto3
import pytest
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber
from labkit.objectstore import ObjectNotFoundError, ObjectStore, PreconditionFailedError
from labkit.objectstore_s3 import S3ObjectStore, s3_client
from labkit.settings import LabSettings

BUCKET = "lab-results"


@pytest.fixture(autouse=True)
def _isolated_aws_env(monkeypatch, tmp_path):
    # Keep the developer's AWS config and env out of client construction.
    for name in (
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_S3",
        "AWS_PROFILE",
        "AWS_DEFAULT_REGION",
        "S3_ENDPOINT",
        "LAB_AWS_REGION",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))


@pytest.fixture
def client():
    # Unsigned: Stubber answers every call, so no credentials are needed.
    return boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))


@pytest.fixture
def stubber(client):
    with Stubber(client) as stub:
        yield stub
        stub.assert_no_pending_responses()


@pytest.fixture
def store(client):
    return S3ObjectStore(BUCKET, client)


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(data), len(data))


def test_s3_object_store_satisfies_protocol(store):
    s: ObjectStore = store
    assert callable(s.put)


def test_put_without_if_none_match_omits_header(store, stubber):
    stubber.add_response("put_object", {}, {"Bucket": BUCKET, "Key": "k", "Body": b"data"})
    store.put("k", b"data")


def test_put_with_if_none_match_sends_star(store, stubber):
    stubber.add_response(
        "put_object", {}, {"Bucket": BUCKET, "Key": "k", "Body": b"data", "IfNoneMatch": "*"}
    )
    store.put("k", b"data", if_none_match=True)


@pytest.mark.parametrize(("code", "status"), [("PreconditionFailed", 412), ("Unknown", 412)])
def test_put_precondition_failure_raises(store, stubber, code, status):
    stubber.add_client_error(
        "put_object",
        service_error_code=code,
        http_status_code=status,
        expected_params={"Bucket": BUCKET, "Key": "k", "Body": b"data", "IfNoneMatch": "*"},
    )
    with pytest.raises(PreconditionFailedError):
        store.put("k", b"data", if_none_match=True)


def test_put_other_client_error_propagates(store, stubber):
    stubber.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)
    with pytest.raises(ClientError):
        store.put("k", b"data")


def test_get_returns_body_bytes(store, stubber):
    stubber.add_response(
        "get_object", {"Body": _body(b"hello")}, {"Bucket": BUCKET, "Key": "results/job-1"}
    )
    assert store.get("results/job-1") == b"hello"


@pytest.mark.parametrize(("code", "status"), [("NoSuchKey", 404), ("Unknown", 404)])
def test_get_missing_key_raises_object_not_found(store, stubber, code, status):
    stubber.add_client_error(
        "get_object",
        service_error_code=code,
        http_status_code=status,
        expected_params={"Bucket": BUCKET, "Key": "missing"},
    )
    with pytest.raises(ObjectNotFoundError):
        store.get("missing")


def test_exists_true_on_successful_head(store, stubber):
    stubber.add_response("head_object", {}, {"Bucket": BUCKET, "Key": "k"})
    assert store.exists("k") is True


def test_exists_false_on_404(store, stubber):
    stubber.add_client_error(
        "head_object",
        service_error_code="404",
        http_status_code=404,
        expected_params={"Bucket": BUCKET, "Key": "k"},
    )
    assert store.exists("k") is False


def test_exists_other_client_error_propagates(store, stubber):
    stubber.add_client_error("head_object", service_error_code="403", http_status_code=403)
    with pytest.raises(ClientError):
        store.exists("k")


def test_delete_calls_delete_object_with_bucket_and_key(store, stubber):
    stubber.add_response("delete_object", {}, {"Bucket": BUCKET, "Key": "results/job-1"})
    store.delete("results/job-1")


def test_list_keys_follows_continuation_token(store, stubber):
    stubber.add_response(
        "list_objects_v2",
        {
            "Contents": [{"Key": "results/a"}, {"Key": "results/b"}],
            "IsTruncated": True,
            "NextContinuationToken": "page-2",
        },
        {"Bucket": BUCKET, "Prefix": "results/"},
    )
    stubber.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "results/c"}], "IsTruncated": False},
        {"Bucket": BUCKET, "Prefix": "results/", "ContinuationToken": "page-2"},
    )
    assert store.list_keys("results/") == ["results/a", "results/b", "results/c"]


def test_list_keys_empty_bucket(store, stubber):
    stubber.add_response(
        "list_objects_v2", {"IsTruncated": False}, {"Bucket": BUCKET, "Prefix": ""}
    )
    assert store.list_keys() == []


def test_empty_key_rejected_without_calling_s3(store, stubber):
    with pytest.raises(ValueError):
        store.put("", b"data")


def test_s3_client_with_endpoint_uses_endpoint_and_path_style():
    settings = LabSettings(service_name="svc", s3_endpoint="http://objectstore:9000")
    client = s3_client(settings)
    assert client.meta.endpoint_url == "http://objectstore:9000"
    assert client.meta.config.s3["addressing_style"] == "path"
    assert client.meta.region_name == "us-east-1"


def test_s3_client_without_endpoint_sets_neither():
    settings = LabSettings(service_name="svc", aws_region="eu-west-1")
    client = s3_client(settings)
    assert "amazonaws.com" in client.meta.endpoint_url
    assert (client.meta.config.s3 or {}).get("addressing_style") != "path"
    assert client.meta.region_name == "eu-west-1"
