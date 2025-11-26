import importlib

import core.views


def test_views_module_imports_render():
    reloaded = importlib.reload(core.views)
    assert hasattr(reloaded, "render")
