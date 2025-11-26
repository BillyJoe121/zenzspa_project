import time
import logging
from unittest.mock import patch, Mock
from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from django.contrib.auth.models import AnonymousUser
from core.middleware import (
    RequestIDMiddleware,
    AdminAuditMiddleware,
    PerformanceLoggingMiddleware,
    _RESPONSE_ID_HEADER
)

class MiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.logger = logging.getLogger('core.middleware')

    def test_request_id_middleware(self):
        middleware = RequestIDMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/')
        
        # Test process_request
        middleware.process_request(request)
        self.assertTrue(hasattr(request, 'request_id'))
        self.assertIsNotNone(request.request_id)
        
        # Test process_response
        response = HttpResponse("OK")
        response = middleware.process_response(request, response)
        self.assertTrue(response.has_header(_RESPONSE_ID_HEADER))
        self.assertEqual(response[_RESPONSE_ID_HEADER], request.request_id)

    def test_request_id_middleware_existing_header(self):
        middleware = RequestIDMiddleware(lambda r: HttpResponse("OK"))
        existing_id = "existing-uuid"
        request = self.factory.get('/', HTTP_X_REQUEST_ID=existing_id)
        
        middleware.process_request(request)
        self.assertEqual(request.request_id, existing_id)

    @patch('core.middleware.safe_audit_log')
    def test_admin_audit_middleware_admin_route(self, mock_audit):
        middleware = AdminAuditMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/api/v1/admin/users/')
        
        # Mock authenticated user
        user = Mock()
        user.is_authenticated = True
        user.id = 1
        request.user = user
        request.request_id = "test-id"
        
        # Process view to set metadata
        middleware.process_view(request, None, None, None)
        self.assertTrue(hasattr(request, '_audit_meta'))
        
        # Process response
        response = HttpResponse("OK")
        middleware.process_response(request, response)
        
        mock_audit.assert_called_once()
        args, kwargs = mock_audit.call_args
        self.assertEqual(kwargs['action'], "ADMIN_ENDPOINT_HIT")
        self.assertEqual(kwargs['admin_user'], user)

    @patch('core.middleware.safe_audit_log')
    def test_admin_audit_middleware_non_admin_route(self, mock_audit):
        middleware = AdminAuditMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/api/v1/public/')
        request.user = Mock(is_authenticated=True)
        
        middleware.process_response(request, HttpResponse("OK"))
        mock_audit.assert_not_called()

    @patch('core.middleware.safe_audit_log')
    def test_admin_audit_middleware_unauthenticated(self, mock_audit):
        middleware = AdminAuditMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/api/v1/admin/users/')
        request.user = AnonymousUser()
        
        middleware.process_response(request, HttpResponse("OK"))
        mock_audit.assert_not_called()

    @patch('core.middleware.logger')
    def test_performance_middleware_fast_request(self, mock_logger):
        middleware = PerformanceLoggingMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/')
        
        middleware.process_request(request)
        response = HttpResponse("OK")
        response = middleware.process_response(request, response)
        
        self.assertTrue(response.has_header('X-Response-Time'))
        mock_logger.warning.assert_not_called()

    @patch('core.middleware.logger')
    @patch('core.middleware.time')
    def test_performance_middleware_slow_request(self, mock_time, mock_logger):
        middleware = PerformanceLoggingMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/')
        
        # Simulate 2 seconds duration
        mock_time.time.side_effect = [100.0, 102.0]
        
        middleware.process_request(request)
        response = HttpResponse("OK")
        response = middleware.process_response(request, response)
        
        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        self.assertIn("Slow request detected", args[0])
        self.assertEqual(kwargs['extra']['duration'], 2.0)

    @patch('core.middleware.logger')
    @patch('core.middleware.time')
    def test_performance_middleware_exception(self, mock_time, mock_logger):
        middleware = PerformanceLoggingMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/')
        
        mock_time.time.side_effect = [100.0, 100.5]
        
        middleware.process_request(request)
        middleware.process_exception(request, ValueError("Test error"))
        
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        self.assertIn("Request failed", args[0])
        self.assertEqual(kwargs['extra']['exception'], "Test error")

    @patch('core.middleware.safe_audit_log', side_effect=RuntimeError("fail"))
    def test_admin_audit_middleware_swallows_errors_when_debug_false(self, mock_audit):
        middleware = AdminAuditMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/api/v1/admin/users/')
        user = Mock(is_authenticated=True, id=1)
        request.user = user
        request.request_id = "rid"

        response = middleware.process_response(request, HttpResponse("OK"))

        self.assertIsInstance(response, HttpResponse)
        mock_audit.assert_called_once()

    def test_performance_middleware_returns_response_without_start_time(self):
        middleware = PerformanceLoggingMiddleware(lambda r: HttpResponse("OK"))
        request = self.factory.get('/')
        response = HttpResponse("OK")

        processed = middleware.process_response(request, response)

        self.assertIs(processed, response)
