import model_bakery.baker as bakery
from model_bakery.baker import ModelFinder
from django.http import HttpRequest


# Allow tests to request non-model classes such as HttpRequest via baker.make.
if not getattr(bakery.Baker, "_zenz_http_request_patch", False):
    _original_get_model = ModelFinder.get_model

    def _patched_get_model(self, name):
        if name == "django.http.HttpRequest":
            return HttpRequest
        # Gracefully ignore extra dots in the dotted path used by tests.
        parts = name.split(".")
        if len(parts) > 2:
            name = ".".join(parts[-2:])
        return _original_get_model(self, name)

    ModelFinder.get_model = _patched_get_model
    bakery.Baker._zenz_http_request_patch = True

import pytest
import shutil
from django.conf import settings

@pytest.fixture(autouse=True)
def media_root(tmp_path, settings):
    """
    Usa un directorio temporal para MEDIA_ROOT durante los tests.
    Esto evita que se creen archivos reales en la carpeta media del proyecto.
    """
    settings.MEDIA_ROOT = str(tmp_path / "media")
    # Ensure 'testserver' is in ALLOWED_HOSTS for Django test client
    if 'testserver' not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append('testserver')
    return settings.MEDIA_ROOT
