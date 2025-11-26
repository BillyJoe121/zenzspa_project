import os

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import URLResolver


class BootstrapTests(SimpleTestCase):
    def test_asgi_application_configured(self):
        from zenzspa import asgi

        self.assertEqual(os.environ.get("DJANGO_SETTINGS_MODULE"), "zenzspa.settings")
        self.assertTrue(callable(asgi.application))

    def test_wsgi_application_configured(self):
        from zenzspa import wsgi

        self.assertTrue(callable(wsgi.application))

    def test_celery_app_exports(self):
        from zenzspa import celery, celery_app

        self.assertIs(celery.app, celery_app)
        self.assertEqual(celery.app.main, "zenzspa")
        self.assertEqual(celery.app.conf.timezone, settings.TIME_ZONE)

    def test_urlpatterns_include_expected_routes(self):
        from zenzspa import urls

        route_map = {resolver.pattern._route: resolver for resolver in urls.urlpatterns if isinstance(resolver, URLResolver)}
        self.assertIn("api/v1/auth/", route_map)
        self.assertIn("api/v1/bot/", route_map)
        self.assertIn("api/v1/", route_map)

    def test_api_patterns_include_apps(self):
        from zenzspa import urls

        included_modules = {
            getattr(resolver.urlconf_module, "__name__", "")
            for resolver in urls.api_patterns
            if isinstance(resolver, URLResolver)
        }
        self.assertIn("spa.urls_catalog", included_modules)
        self.assertIn("marketplace.urls", included_modules)
        self.assertIn("profiles.urls", included_modules)
        self.assertIn("notifications.urls", included_modules)

    def test_health_check_endpoint_responds(self):
        """
        Test que el health check responde correctamente.
        Ahora puede retornar 200 (OK) o 503 (dependencias caídas).
        """
        response = self.client.get("/health/")
        # Aceptar tanto 200 como 503, ya que el health check ahora verifica dependencias reales
        self.assertIn(response.status_code, [200, 503])
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("app", data)
        self.assertEqual(data["app"], "zenzspa")
        # Verificar que incluye checks de dependencias
        if "checks" in data:
            self.assertIn("db", data["checks"])
            self.assertIn("cache", data["checks"])
