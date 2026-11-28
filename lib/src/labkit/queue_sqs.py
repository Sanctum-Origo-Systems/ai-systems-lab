"""Queue adapter over a boto3 SQS client.

The same code reaches ElasticMQ locally (QUEUE_ENDPOINT set) and SQS on AWS
(QUEUE_ENDPOINT unset). Only string message attributes are carried.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from labkit.queue import InvalidReceiptError, Message
from labkit.settings import LabSettings

_INVALID_RECEIPT = "ReceiptHandleIsInvalid"


def sqs_client(settings: LabSettings) -> BaseClient:
    """Build an SQS client for `settings`, honouring the local endpoint override if set."""
    kwargs: dict[str, Any] = {"region_name": settings.aws_region}
    if settings.queue_endpoint:
        kwargs["endpoint_url"] = settings.queue_endpoint
    return boto3.client("sqs", **kwargs)


class SqsQueue:
    """A Queue backed by one SQS (or SQS-compatible) queue URL."""

    def __init__(self, queue_url: str, client: BaseClient) -> None:
        self._url = queue_url
        self._client = client

    def send(self, body: str, attributes: dict[str, str] | None = None) -> str:
        kwargs: dict[str, Any] = {"QueueUrl": self._url, "MessageBody": body}
        if attributes:
            kwargs["MessageAttributes"] = {
                name: {"DataType": "String", "StringValue": value}
                for name, value in attributes.items()
            }
        return self._client.send_message(**kwargs)["MessageId"]

    def receive(
        self, max_messages: int = 1, visibility_timeout: float | None = None
    ) -> list[Message]:
        kwargs: dict[str, Any] = {
            "QueueUrl": self._url,
            "MaxNumberOfMessages": max_messages,
            "AttributeNames": ["ApproximateReceiveCount"],
            "MessageAttributeNames": ["All"],
        }
        if visibility_timeout is not None:
            kwargs["VisibilityTimeout"] = int(visibility_timeout)
        response = self._client.receive_message(**kwargs)
        return [_to_message(raw) for raw in response.get("Messages", [])]

    def delete(self, receipt: str) -> None:
        with _translate_invalid_receipt(receipt):
            self._client.delete_message(QueueUrl=self._url, ReceiptHandle=receipt)

    def change_visibility(self, receipt: str, timeout: float) -> None:
        with _translate_invalid_receipt(receipt):
            self._client.change_message_visibility(
                QueueUrl=self._url, ReceiptHandle=receipt, VisibilityTimeout=int(timeout)
            )


def _to_message(raw: dict[str, Any]) -> Message:
    return Message(
        message_id=raw["MessageId"],
        body=raw["Body"],
        receipt=raw["ReceiptHandle"],
        receive_count=int(raw["Attributes"]["ApproximateReceiveCount"]),
        attributes={
            name: attr["StringValue"]
            for name, attr in raw.get("MessageAttributes", {}).items()
            if attr.get("DataType") == "String"
        },
    )


@contextmanager
def _translate_invalid_receipt(receipt: str) -> Iterator[None]:
    try:
        yield
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == _INVALID_RECEIPT:
            raise InvalidReceiptError(receipt) from exc
        raise
