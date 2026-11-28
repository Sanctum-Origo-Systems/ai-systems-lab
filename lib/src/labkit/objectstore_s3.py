"""ObjectStore adapter backed by a boto3 S3 client.

``put(..., if_none_match=True)`` sends ``IfNoneMatch="*"``, so S3 rejects the write
with a 412 when the key already exists. That 412 surfaces as PreconditionFailedError,
the same as the in-memory fake.
"""

from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from labkit.objectstore import ObjectNotFoundError, PreconditionFailedError, _check_key
from labkit.settings import LabSettings

_NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}
_PRECONDITION_CODES = {"PreconditionFailed", "412"}


def _error_code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


def _http_status(exc: ClientError) -> int | None:
    return exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")


def _is_not_found(exc: ClientError) -> bool:
    return _error_code(exc) in _NOT_FOUND_CODES or _http_status(exc) == 404


def _is_precondition_failed(exc: ClientError) -> bool:
    return _error_code(exc) in _PRECONDITION_CODES or _http_status(exc) == 412


class S3ObjectStore:
    """ObjectStore on one S3 bucket. Other ClientErrors propagate unchanged."""

    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    def put(self, key: str, data: bytes, if_none_match: bool = False) -> None:
        _check_key(key)
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key, "Body": bytes(data)}
        if if_none_match:
            params["IfNoneMatch"] = "*"
        try:
            self._client.put_object(**params)
        except ClientError as exc:
            if _is_precondition_failed(exc):
                raise PreconditionFailedError(key) from exc
            raise

    def get(self, key: str) -> bytes:
        _check_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        _check_key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_not_found(exc):
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        _check_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        params: dict[str, Any] = {"Bucket": self._bucket, "Prefix": prefix}
        while True:
            response = self._client.list_objects_v2(**params)
            keys.extend(obj["Key"] for obj in response.get("Contents", []))
            if not response.get("IsTruncated"):
                break
            params["ContinuationToken"] = response["NextContinuationToken"]
        return sorted(keys)


def s3_client(settings: LabSettings) -> Any:
    """Build an S3 client; a set s3_endpoint adds endpoint_url and path-style addressing."""
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.s3_endpoint:
        kwargs["endpoint_url"] = settings.s3_endpoint
        kwargs["config"] = Config(s3={"addressing_style": "path"})
    return boto3.client("s3", **kwargs)
