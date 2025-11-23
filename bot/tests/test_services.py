import pytest
import requests
from model_bakery import baker  # IMPORTANTE: Usaremos baker
from bot.services import GeminiService, DataContextService

@pytest.mark.django_db
class TestDataContextService:
    
    # --- Servicios ---
    def test_get_services_empty(self):
        assert "No hay servicios" in DataContextService.get_services_context()

    def test_get_services_with_data(self):
        """Prueba que se listen los servicios activos."""
        # CORRECCIÓN: Usamos baker.make para que cree la 'Category' obligatoria automáticamente
        baker.make('spa.Service', name="Masaje Relax", duration=60, price=100000, is_active=True, description="Desc")
        baker.make('spa.Service', name="Masaje Off", duration=60, price=100000, is_active=False, description="Desc")
        
        ctx = DataContextService.get_services_context()
        assert "Masaje Relax" in ctx
        assert "Masaje Off" not in ctx 

    # --- Productos ---
    def test_get_products_formatting(self):
        from marketplace.models import ProductVariant, Product
        
        # Setup datos reales
        prod = Product.objects.create(name="Aceite", is_active=True)
        # Usamos SKU único para cada variante
        ProductVariant.objects.create(product=prod, name="50ml", sku="SKU-TEST-1", price=50000, stock=10)
        ProductVariant.objects.create(product=prod, name="100ml", sku="SKU-TEST-2", price=80000, stock=0)
        
        ctx = DataContextService.get_products_context()
        
        assert "Aceite (50ml): $50.000" in ctx
        assert "Stock disponible: 10" in ctx
        assert "Actualmente agotado" in ctx

    # --- Staff ---
    def test_get_staff_empty(self):
        assert "Equipo de terapeutas expertos" in DataContextService.get_staff_context()

    def test_get_staff_with_data(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # CORRECCIÓN: Agregamos emails únicos para evitar error de integridad
        User.objects.create(
            first_name="Ana", last_name="Terapeuta",
            role=User.Role.STAFF, is_active=True,
            phone_number="+573000000001", email="ana@test.com"
        )
        User.objects.create(
            first_name="Pedro", last_name="Inactivo",
            role=User.Role.STAFF, is_active=False,
            phone_number="+573000000002", email="pedro@test.com"
        )
        User.objects.create(
            first_name="Cliente", role=User.Role.CLIENT,
            is_active=True,
            phone_number="+573000000003", email="cliente@test.com"
        )

        ctx = DataContextService.get_staff_context()
        assert "Ana Terapeuta" in ctx
        assert "Pedro" not in ctx
        assert "Cliente" not in ctx

    def test_cache_behavior(self):
        """
        MEJORA #8: Verifica que el caché de contexto funciona correctamente.
        """
        from django.core.cache import cache
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Limpiar caché
        cache.clear()

        # Primera llamada - debe hacer query a DB
        baker.make('spa.Service', name="Masaje Test", duration=60, price=100000, is_active=True)
        ctx1 = DataContextService.get_services_context()
        assert "Masaje Test" in ctx1

        # Crear nuevo servicio
        baker.make('spa.Service', name="Masaje Nuevo", duration=90, price=150000, is_active=True)

        # Segunda llamada - debe usar caché (no incluye el nuevo servicio aún)
        ctx2 = DataContextService.get_services_context()
        assert "Masaje Test" in ctx2
        # El caché aún no tiene "Masaje Nuevo" porque se cacheó antes

        # Limpiar caché manualmente
        cache.delete('bot_context:services')

        # Tercera llamada - debe refrescar desde DB
        ctx3 = DataContextService.get_services_context()
        assert "Masaje Nuevo" in ctx3

@pytest.mark.django_db
class TestGeminiServiceInternals:
    # ... (El resto de la clase TestGeminiServiceInternals se queda IGUAL que antes)
    def test_init_missing_api_key(self, settings):
        settings.GEMINI_API_KEY = ""
        service = GeminiService()
        assert not service.api_key

    def test_generate_response_success(self, mocker, settings):
        settings.GEMINI_API_KEY = "fake-key"
        service = GeminiService()
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Hola mundo"}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}
        }
        mocker.patch("requests.post", return_value=mock_response)
        text, meta = service.generate_response("Hola")
        assert text == "Hola mundo"
        assert meta["tokens"] == 15

    def test_generate_response_retry_logic(self, mocker, settings):
        settings.GEMINI_API_KEY = "fake-key"
        mocker.patch("time.sleep") 
        service = GeminiService()
        mock_post = mocker.patch("requests.post", side_effect=[
            requests.Timeout, requests.Timeout,
            mocker.Mock(status_code=200, json=lambda: {
                "candidates": [{"content": {"parts": [{"text": "Al fin"}]}}],
                "usageMetadata": {}
            })
        ])
        text, _ = service.generate_response("Hola")
        assert text == "Al fin"
        assert mock_post.call_count == 3

    def test_generate_response_security_block(self, mocker, settings):
        settings.GEMINI_API_KEY = "fake-key"
        service = GeminiService()
        mock_response = mocker.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"promptFeedback": {"blockReason": "SAFETY"}}
        mocker.patch("requests.post", return_value=mock_response)
        text, meta = service.generate_response("Nude")
        assert text == "noRelated"
        assert meta["reason"] == "blocked_content"

    def test_generate_response_connection_error(self, mocker, settings):
        settings.GEMINI_API_KEY = "fake-key"
        service = GeminiService()
        mocker.patch("requests.post", side_effect=requests.ConnectionError("Fail"))
        text, meta = service.generate_response("Hola")
        assert "problema de conexión" in text
        assert meta["source"] == "fallback"