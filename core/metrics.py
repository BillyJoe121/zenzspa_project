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
        try:
            metric = Counter(name, doc, list(labelnames))
        except ValueError:
            # La métrica ya existe en el registro (común en tests)
            # Intentar obtenerla del registro
            from prometheus_client import REGISTRY
            for collector in REGISTRY._collector_to_names.keys():
                if hasattr(collector, '_name') and collector._name == name:
                    metric = collector
                    break
            else:
                # Si no se encuentra, usar un no-op
                metric = _NoOpMetric()
    else:
        metric = _NoOpMetric()
    _counter_cache[key] = metric
    return metric


def get_histogram(name: str, doc: str, labelnames: Iterable[str] = (), buckets: Iterable[float] | None = None) -> object:
    key = (name, tuple(labelnames))
    if key in _hist_cache:
        return _hist_cache[key]
    if Histogram:
        try:
            if buckets:
                metric = Histogram(name, doc, list(labelnames), buckets=buckets)
            else:
                metric = Histogram(name, doc, list(labelnames))
        except ValueError:
            # La métrica ya existe en el registro (común en tests)
            # Intentar obtenerla del registro
            from prometheus_client import REGISTRY
            for collector in REGISTRY._collector_to_names.keys():
                if hasattr(collector, '_name') and collector._name == name:
                    metric = collector
                    break
            else:
                # Si no se encuentra, usar un no-op
                metric = _NoOpMetric()
    else:
        metric = _NoOpMetric()
    _hist_cache[key] = metric
    return metric
