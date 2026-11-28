import pytest
from labkit.metrics import ALLOWED_LABELS, counter, histogram, render
from prometheus_client import CollectorRegistry


def test_allowed_labels_are_the_bounded_set():
    assert ALLOWED_LABELS == frozenset({"service", "backend", "priority", "decision", "status"})


def test_counter_rejects_name_without_lab_prefix():
    with pytest.raises(ValueError, match="lab_"):
        counter("requests_total", "Requests.", registry=CollectorRegistry())


def test_counter_rejects_name_without_total_suffix():
    with pytest.raises(ValueError, match="_total"):
        counter("lab_requests", "Requests.", registry=CollectorRegistry())


def test_histogram_rejects_name_without_lab_prefix():
    with pytest.raises(ValueError, match="lab_"):
        histogram("latency_seconds", "Latency.", registry=CollectorRegistry())


@pytest.mark.parametrize("name", ["lab_latency", "lab_latency_ms", "lab_latency_total"])
def test_histogram_rejects_name_without_seconds_or_tokens_suffix(name):
    with pytest.raises(ValueError, match="_seconds"):
        histogram(name, "Latency.", registry=CollectorRegistry())


def test_counter_rejects_label_outside_allowed_labels():
    with pytest.raises(ValueError, match="request_id"):
        counter(
            "lab_requests_total",
            "Requests.",
            labels=("service", "request_id"),
            registry=CollectorRegistry(),
        )


def test_histogram_rejects_label_outside_allowed_labels():
    with pytest.raises(ValueError, match="request_id"):
        histogram(
            "lab_latency_seconds",
            "Latency.",
            labels=("request_id",),
            registry=CollectorRegistry(),
        )


def test_rejected_metric_is_not_registered():
    registry = CollectorRegistry()
    with pytest.raises(ValueError):
        counter("lab_requests_total", "Requests.", labels=("request_id",), registry=registry)

    counter("lab_requests_total", "Requests.", labels=("service",), registry=registry)


def test_valid_counter_renders_name_and_label():
    registry = CollectorRegistry()
    requests = counter("lab_requests_total", "Requests.", labels=("service",), registry=registry)

    requests.labels(service="gateway").inc()

    text = render(registry).decode()
    assert isinstance(render(registry), bytes)
    assert 'lab_requests_total{service="gateway"} 1.0' in text


def test_valid_histogram_renders_bucket_count_and_sum():
    registry = CollectorRegistry()
    latency = histogram("lab_latency_seconds", "Latency.", registry=registry)

    latency.observe(0.2)

    text = render(registry).decode()
    assert "lab_latency_seconds_bucket{" in text
    assert "lab_latency_seconds_count 1.0" in text
    assert "lab_latency_seconds_sum 0.2" in text


def test_histogram_accepts_tokens_suffix_and_custom_buckets():
    registry = CollectorRegistry()
    tokens = histogram(
        "lab_prompt_tokens",
        "Prompt tokens.",
        labels=("backend",),
        buckets=(10, 100, 1000),
        registry=registry,
    )

    tokens.labels(backend="fake").observe(50)

    text = render(registry).decode()
    assert 'lab_prompt_tokens_bucket{backend="fake",le="100.0"} 1.0' in text
    assert 'lab_prompt_tokens_bucket{backend="fake",le="10.0"} 0.0' in text
