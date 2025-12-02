
import pytest
from unittest.mock import patch, MagicMock
from core.metrics import get_counter, get_histogram, _counter_cache, _hist_cache, _NoOpMetric

@pytest.fixture(autouse=True)
def clear_caches():
    _counter_cache.clear()
    _hist_cache.clear()
    yield
    _counter_cache.clear()
    _hist_cache.clear()

def test_get_counter_creates_new_metric():
    with patch('core.metrics.Counter') as MockCounter:
        metric = get_counter('test_counter', 'Test doc')
        assert metric is not None
        MockCounter.assert_called_once_with('test_counter', 'Test doc', [])

def test_get_counter_returns_cached_metric():
    with patch('core.metrics.Counter') as MockCounter:
        metric1 = get_counter('test_counter', 'Test doc')
        metric2 = get_counter('test_counter', 'Test doc')
        assert metric1 is metric2
        MockCounter.assert_called_once()

def test_get_counter_noop_fallback():
    with patch('core.metrics.Counter', None):
        metric = get_counter('test_counter_noop', 'Test doc')
        assert isinstance(metric, _NoOpMetric)
        assert metric.inc() is None

def test_get_histogram_creates_new_metric():
    with patch('core.metrics.Histogram') as MockHistogram:
        metric = get_histogram('test_hist', 'Test doc')
        assert metric is not None
        MockHistogram.assert_called_once_with('test_hist', 'Test doc', [])

def test_get_histogram_with_buckets():
    with patch('core.metrics.Histogram') as MockHistogram:
        buckets = [0.1, 0.5, 1.0]
        metric = get_histogram('test_hist_buckets', 'Test doc', buckets=buckets)
        MockHistogram.assert_called_once_with('test_hist_buckets', 'Test doc', [], buckets=buckets)

def test_get_histogram_returns_cached_metric():
    with patch('core.metrics.Histogram') as MockHistogram:
        metric1 = get_histogram('test_hist', 'Test doc')
        metric2 = get_histogram('test_hist', 'Test doc')
        assert metric1 is metric2
        MockHistogram.assert_called_once()

def test_get_histogram_noop_fallback():
    with patch('core.metrics.Histogram', None):
        metric = get_histogram('test_hist_noop', 'Test doc')
        assert isinstance(metric, _NoOpMetric)
        assert metric.observe(1) is None

def test_noop_metric_methods():
    metric = _NoOpMetric()
    assert metric.labels('label') is metric
    assert metric.inc() is None
    assert metric.observe(1) is None
