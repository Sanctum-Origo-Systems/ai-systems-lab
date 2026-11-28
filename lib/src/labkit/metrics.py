"""Prometheus metrics that follow the lab naming and label rules.

Every metric name starts with `lab_`. Counters end in `_total`; histograms end in
`_seconds` or `_tokens`. Labels come from a fixed, bounded set so no metric can grow
one time series per request. Services serve `render(registry)` from `/metrics`.
"""

from collections.abc import Sequence

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.registry import REGISTRY

ALLOWED_LABELS = frozenset({"service", "backend", "priority", "decision", "status"})

PREFIX = "lab_"
COUNTER_SUFFIX = "_total"
HISTOGRAM_SUFFIXES = ("_seconds", "_tokens")


def _registry(registry: CollectorRegistry | None) -> CollectorRegistry:
    return REGISTRY if registry is None else registry


def _check_common(name: str, labels: Sequence[str]) -> None:
    if not name.startswith(PREFIX):
        raise ValueError(f"metric name {name!r} must start with {PREFIX!r}")
    unknown = sorted(set(labels) - ALLOWED_LABELS)
    if unknown:
        raise ValueError(
            f"metric {name!r} uses labels {unknown} outside ALLOWED_LABELS {sorted(ALLOWED_LABELS)}"
        )


def counter(
    name: str,
    doc: str,
    labels: Sequence[str] = (),
    registry: CollectorRegistry | None = None,
) -> Counter:
    """Create a Counter named `lab_*_total` with labels from ALLOWED_LABELS."""
    _check_common(name, labels)
    if not name.endswith(COUNTER_SUFFIX):
        raise ValueError(f"counter name {name!r} must end in {COUNTER_SUFFIX!r}")
    return Counter(name, doc, labelnames=tuple(labels), registry=_registry(registry))


def histogram(
    name: str,
    doc: str,
    labels: Sequence[str] = (),
    buckets: Sequence[float] | None = None,
    registry: CollectorRegistry | None = None,
) -> Histogram:
    """Create a Histogram named `lab_*_seconds` or `lab_*_tokens` with bounded labels."""
    _check_common(name, labels)
    if not name.endswith(HISTOGRAM_SUFFIXES):
        raise ValueError(f"histogram name {name!r} must end in one of {HISTOGRAM_SUFFIXES}")
    kwargs = {} if buckets is None else {"buckets": tuple(buckets)}
    return Histogram(name, doc, labelnames=tuple(labels), registry=_registry(registry), **kwargs)


def render(registry: CollectorRegistry) -> bytes:
    """Return the Prometheus text exposition format for `registry`."""
    return generate_latest(registry)
