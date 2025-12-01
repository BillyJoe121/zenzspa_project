"""
Helpers para exponer métricas Prometheus con fallback no-op si la librería no está disponible.
"""
from typing import Iterable

try:
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    Counter = None
    Histogram = None


class _NoOpMetric:
    def labels(self, *args, **kwargs):  # pragma: no cover - no-op
        return self

    def inc(self, *args, **kwargs):  # pragma: no cover
        return None

    def observe(self, *args, **kwargs):  # pragma: no cover
        return None


_counter_cache: dict[tuple[str, tuple[str, ...]], object] = {}
_hist_cache: dict[tuple[str, tuple[str, ...]], object] = {}


def get_counter(name: str, doc: str, labelnames: Iterable[str] = ()) -> object:
    key = (name, tuple(labelnames))
    if key in _counter_cache:
        return _counter_cache[key]
    if Counter:
        metric = Counter(name, doc, list(labelnames))
    else:
        metric = _NoOpMetric()
    _counter_cache[key] = metric
    return metric


def get_histogram(name: str, doc: str, labelnames: Iterable[str] = (), buckets: Iterable[float] | None = None) -> object:
    key = (name, tuple(labelnames))
    if key in _hist_cache:
        return _hist_cache[key]
    if Histogram:
        if buckets:
            metric = Histogram(name, doc, list(labelnames), buckets=buckets)
        else:
            metric = Histogram(name, doc, list(labelnames))
    else:
        metric = _NoOpMetric()
    _hist_cache[key] = metric
    return metric
