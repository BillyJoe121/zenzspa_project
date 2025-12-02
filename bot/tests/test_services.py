import pytest
import sys
import types
from unittest.mock import MagicMock, patch
from model_bakery import baker
from bot.services import GeminiService, DataContextService

# Fallback de módulos google.genai solo si no están instalados.
# No reemplazamos el paquete real cuando existe.
try:
    import google.genai as genai_mod  # type: ignore
except ImportError:  # pragma: no cover - solo entornos sin google-genai
    google_mod = sys.modules.setdefault("google", types.ModuleType("google"))
    genai_mod = types.ModuleType("google.genai")
    sys.modules["google.genai"] = genai_mod
    google_mod.genai = genai_mod

    class _DummyModels:
        def generate_content(self, *args, **kwargs):
            raise AttributeError("Dummy client cannot call generate_content")

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            self.models = _DummyModels()

    genai_mod.Client = _DummyClient

    types_mod = types.ModuleType("google.genai.types")
    types_mod.GenerateContentConfig = lambda **kwargs: types.SimpleNamespace(**kwargs)
    types_mod.ThinkingConfig = lambda **kwargs: types.SimpleNamespace(**kwargs)
    sys.modules["google.genai.types"] = types_mod
    genai_mod.types = types_mod

@pytest.mark.django_db
class TestDataContextService:
    
    # --- Servicios ---
    def test_get_services_empty(self):
        assert "No hay servicios" in DataContextService.get_services_context()

    def test_get_services_with_data(self):
        """Prueba que se listen los servicios activos."""
        baker.make('spa.Service', name="Masaje Relax", duration=60, price=100000, is_active=True, description="Desc")
        baker.make('spa.Service', name="Masaje Off", duration=60, price=100000, is_active=False, description="Desc")
        
        ctx = DataContextService.get_services_context()
        assert "Masaje Relax" in ctx
        assert "Masaje Off" not in ctx 

    # --- Productos ---
    def test_get_products_formatting(self):
        from marketplace.models import ProductVariant, Product
        
        prod = Product.objects.create(name="Aceite", is_active=True)
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
        from django.core.cache import cache
        User = get_user_model()

        # Limpiar cache antes del test
        cache.delete('bot_context:staff')

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
        """Verifica que el caché de contexto funciona correctamente."""
        from django.core.cache import cache
        
        cache.clear()

        baker.make('spa.Service', name="Masaje Test", duration=60, price=100000, is_active=True)
        ctx1 = DataContextService.get_services_context()
        assert "Masaje Test" in ctx1

        baker.make('spa.Service', name="Masaje Nuevo", duration=90, price=150000, is_active=True)

        ctx2 = DataContextService.get_services_context()
        assert "Masaje Test" in ctx2
        
        cache.delete('bot_context:services')

        ctx3 = DataContextService.get_services_context()
        assert "Masaje Nuevo" in ctx3

@pytest.mark.django_db
class TestGeminiServiceInternals:
    """
    Tests unitarios para GeminiService usando mocks del SDK oficial (google.genai).
    CORRECCIÓN: Ya no mockeamos requests.post, sino google.genai.Client.
    """

    def test_init_missing_api_key(self, settings):
        settings.GEMINI_API_KEY = ""
        # Patch os.getenv to ensure no fallback to environment variables
        with patch("os.getenv", return_value=""):
            service = GeminiService()
            assert not service.api_key
            assert service.client is None

    @patch("google.genai.Client")
    def test_generate_response_success(self, mock_client_cls, settings):
        settings.GEMINI_API_KEY = "fake-key"
        
        # Configurar el mock del cliente y su respuesta
        mock_client_instance = mock_client_cls.return_value
        mock_response = MagicMock()
        mock_response.text = '{"reply_to_user": "Hola mundo", "analysis": {"action": "REPLY"}}'
        
        # Mock usage metadata
        mock_usage = MagicMock()
        mock_usage.total_token_count = 15
        mock_response.usage_metadata = mock_usage
        
        mock_client_instance.models.generate_content.return_value = mock_response

        service = GeminiService()
        response_json, meta = service.generate_response("Hola")
        
        assert response_json["reply_to_user"] == "Hola mundo"
        assert meta["tokens"] == 15
        assert meta["source"] == "gemini-json"
        
        # Verificar que se llamó con los argumentos correctos
        mock_client_instance.models.generate_content.assert_called_once()

    @patch("google.genai.Client")
    def test_generate_response_security_block(self, mock_client_cls, settings):
        """Verifica que si no hay texto (bloqueo), se maneja como error."""
        settings.GEMINI_API_KEY = "fake-key"
        
        mock_client_instance = mock_client_cls.return_value
        mock_response = MagicMock()
        # Simular que acceder a .text lanza AttributeError
        type(mock_response).text = property(fget=lambda self: (_ for _ in ()).throw(AttributeError("No text")))

        mock_client_instance.models.generate_content.return_value = mock_response

        service = GeminiService()
        response_json, meta = service.generate_response("Nude")

        # En la implementación actual, esto cae en el catch general
        assert "dificultades técnicas" in response_json["reply_to_user"]
        assert meta["source"] == "fallback_error"

    @patch("google.genai.Client")
    def test_generate_response_api_error(self, mock_client_cls, settings):
        """Verifica manejo de errores de API"""
        settings.GEMINI_API_KEY = "fake-key"
        
        mock_client_instance = mock_client_cls.return_value
        # Simular error 500
        mock_client_instance.models.generate_content.side_effect = Exception("500 Internal Server Error")

        service = GeminiService()
        response_json, meta = service.generate_response("Hola")

        assert "dificultades técnicas" in response_json["reply_to_user"]
        assert meta["source"] == "fallback_error"
        assert "500" in meta["reason"]
