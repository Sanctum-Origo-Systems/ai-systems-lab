import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from labkit.queue import InvalidReceiptError, Message, Queue
from labkit.queue_sqs import SqsQueue, sqs_client
from labkit.settings import LabSettings

LOCAL_ENDPOINT = "http://elasticmq.test:9324"
QUEUE_URL = f"{LOCAL_ENDPOINT}/000000000000/jobs"

AWS_ENV_VARS = (
    "AWS_ENDPOINT_URL",
    "AWS_ENDPOINT_URL_SQS",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_PROFILE",
    "AWS_CONFIG_FILE",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_SESSION_TOKEN",
)


@pytest.fixture(autouse=True)
def isolated_aws_env(monkeypatch, tmp_path):
    for name in AWS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Keep real ~/.aws files out, and stop botocore probing EC2 metadata for credentials.
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake-test-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake-test-secret")


def make_settings(**overrides) -> LabSettings:
    return LabSettings(service_name="sqs-test", **overrides)


@pytest.fixture
def client():
    return sqs_client(make_settings(aws_region="eu-west-1", queue_endpoint=LOCAL_ENDPOINT))


@pytest.fixture
def stubber(client):
    with Stubber(client) as stub:
        yield stub
        stub.assert_no_pending_responses()


@pytest.fixture
def queue(client) -> SqsQueue:
    return SqsQueue(QUEUE_URL, client)


def receive_response(*messages: dict) -> dict:
    return {"Messages": list(messages)}


def test_sqs_queue_satisfies_queue_protocol(client, stubber):
    queue: Queue = SqsQueue(QUEUE_URL, client)
    stubber.add_response(
        "send_message",
        {"MessageId": "m-1"},
        {"QueueUrl": QUEUE_URL, "MessageBody": "job"},
    )
    stubber.add_response(
        "receive_message",
        receive_response(
            {
                "MessageId": "m-1",
                "Body": "job",
                "ReceiptHandle": "r-1",
                "Attributes": {"ApproximateReceiveCount": "1"},
            }
        ),
    )
    stubber.add_response(
        "change_message_visibility",
        {},
        {"QueueUrl": QUEUE_URL, "ReceiptHandle": "r-1", "VisibilityTimeout": 60},
    )
    stubber.add_response("delete_message", {}, {"QueueUrl": QUEUE_URL, "ReceiptHandle": "r-1"})

    assert queue.send("job") == "m-1"
    [message] = queue.receive()
    queue.change_visibility(message.receipt, 60)
    queue.delete(message.receipt)


def test_send_with_attributes_sends_string_message_attributes(queue, stubber):
    stubber.add_response(
        "send_message",
        {"MessageId": "m-42"},
        {
            "QueueUrl": QUEUE_URL,
            "MessageBody": '{"task": "resize"}',
            "MessageAttributes": {
                "tenant": {"DataType": "String", "StringValue": "tenant-a"},
                "priority": {"DataType": "String", "StringValue": "high"},
            },
        },
    )

    message_id = queue.send(
        '{"task": "resize"}', attributes={"tenant": "tenant-a", "priority": "high"}
    )

    assert message_id == "m-42"


@pytest.mark.parametrize("attributes", [None, {}])
def test_send_without_attributes_leaves_message_attributes_out(queue, stubber, attributes):
    # Stubber matches expected params exactly, so an extra MessageAttributes key fails.
    stubber.add_response(
        "send_message",
        {"MessageId": "m-7"},
        {"QueueUrl": QUEUE_URL, "MessageBody": "plain"},
    )

    assert queue.send("plain", attributes=attributes) == "m-7"


def test_receive_sends_parameters_and_maps_messages(queue, stubber):
    stubber.add_response(
        "receive_message",
        receive_response(
            {
                "MessageId": "m-1",
                "Body": "first",
                "ReceiptHandle": "r-1",
                "Attributes": {"ApproximateReceiveCount": "3"},
                "MessageAttributes": {
                    "tenant": {"DataType": "String", "StringValue": "tenant-a"},
                    "blob": {"DataType": "Binary", "BinaryValue": b"\x00\x01"},
                },
            },
            {
                "MessageId": "m-2",
                "Body": "second",
                "ReceiptHandle": "r-2",
                "Attributes": {"ApproximateReceiveCount": "1"},
            },
        ),
        {
            "QueueUrl": QUEUE_URL,
            "MaxNumberOfMessages": 5,
            "VisibilityTimeout": 30,
            "AttributeNames": ["ApproximateReceiveCount"],
            "MessageAttributeNames": ["All"],
        },
    )

    messages = queue.receive(max_messages=5, visibility_timeout=30)

    assert messages == [
        Message(
            message_id="m-1",
            body="first",
            receipt="r-1",
            receive_count=3,
            attributes={"tenant": "tenant-a"},
        ),
        Message(message_id="m-2", body="second", receipt="r-2", receive_count=1, attributes={}),
    ]
    assert isinstance(messages[0].receive_count, int)


def test_receive_truncates_fractional_visibility_timeout(queue, stubber):
    stubber.add_response(
        "receive_message",
        {},
        {
            "QueueUrl": QUEUE_URL,
            "MaxNumberOfMessages": 1,
            "VisibilityTimeout": 12,
            "AttributeNames": ["ApproximateReceiveCount"],
            "MessageAttributeNames": ["All"],
        },
    )

    assert queue.receive(visibility_timeout=12.9) == []


def test_receive_defaults_omit_visibility_timeout_and_handle_empty_response(queue, stubber):
    stubber.add_response(
        "receive_message",
        {},
        {
            "QueueUrl": QUEUE_URL,
            "MaxNumberOfMessages": 1,
            "AttributeNames": ["ApproximateReceiveCount"],
            "MessageAttributeNames": ["All"],
        },
    )

    assert queue.receive() == []


def test_delete_sends_receipt_handle(queue, stubber):
    stubber.add_response("delete_message", {}, {"QueueUrl": QUEUE_URL, "ReceiptHandle": "r-9"})

    assert queue.delete("r-9") is None


def test_change_visibility_sends_int_timeout(queue, stubber):
    stubber.add_response(
        "change_message_visibility",
        {},
        {"QueueUrl": QUEUE_URL, "ReceiptHandle": "r-9", "VisibilityTimeout": 45},
    )

    assert queue.change_visibility("r-9", 45.7) is None


@pytest.mark.parametrize(
    ("operation", "call"),
    [
        ("delete_message", lambda q: q.delete("stale")),
        ("change_message_visibility", lambda q: q.change_visibility("stale", 10)),
    ],
)
def test_invalid_receipt_raises_invalid_receipt_error(queue, stubber, operation, call):
    stubber.add_client_error(
        operation, service_error_code="ReceiptHandleIsInvalid", http_status_code=400
    )

    with pytest.raises(InvalidReceiptError):
        call(queue)


@pytest.mark.parametrize(
    ("operation", "call"),
    [
        ("delete_message", lambda q: q.delete("r-1")),
        ("change_message_visibility", lambda q: q.change_visibility("r-1", 10)),
    ],
)
def test_other_client_errors_propagate_unchanged(queue, stubber, operation, call):
    stubber.add_client_error(
        operation, service_error_code="AWS.SimpleQueueService.NonExistentQueue"
    )

    with pytest.raises(ClientError) as excinfo:
        call(queue)

    assert not isinstance(excinfo.value, InvalidReceiptError)
    assert excinfo.value.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue"


def test_sqs_client_uses_endpoint_override_when_set():
    client = sqs_client(make_settings(aws_region="eu-west-1", queue_endpoint=LOCAL_ENDPOINT))

    assert client.meta.service_model.service_name == "sqs"
    assert client.meta.region_name == "eu-west-1"
    assert client.meta.endpoint_url == LOCAL_ENDPOINT


def test_sqs_client_without_override_uses_aws_endpoint():
    client = sqs_client(make_settings(aws_region="eu-west-1"))

    assert client.meta.service_model.service_name == "sqs"
    assert client.meta.region_name == "eu-west-1"
    assert client.meta.endpoint_url != LOCAL_ENDPOINT
    assert "amazonaws.com" in client.meta.endpoint_url
