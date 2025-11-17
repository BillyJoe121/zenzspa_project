# profiles/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
# --- INICIO DE LA MODIFICACIÓN ---
# Se importa el ViewSet principal y se eliminan las vistas que ahora maneja el router.
from .views import (
    ClinicalProfileViewSet,
    ClinicalProfileHistoryViewSet,
    ConsentTemplateViewSet,
    DoshaQuestionListView,
    DoshaQuestionViewSet,
    DoshaQuizSubmitView,
    KioskSessionDiscardChangesView,
    KioskSessionHeartbeatView,
    KioskSessionLockView,
    KioskSessionPendingChangesView,
    KioskSessionSecureScreenView,
    KioskSessionStatusView,
    KioskStartSessionView,
    AnonymizeProfileView,
)
# --- FIN DE LA MODIFICACIÓN ---

router = DefaultRouter()

router.register(r'users', ClinicalProfileViewSet, basename='clinical-profile')
router.register(r'clinical-history', ClinicalProfileHistoryViewSet, basename='clinical-profile-history')

router.register(r'dosha-questions-admin', DoshaQuestionViewSet, basename='dosha-question-admin')
router.register(r'consent-templates', ConsentTemplateViewSet, basename='consent-template')


urlpatterns = [
    # Las rutas de perfiles ahora son manejadas por el router, se eliminan las entradas manuales.
    
    # Se mantienen las rutas que no forman parte de un ViewSet estándar.
    path('dosha-quiz/', DoshaQuestionListView.as_view(), name='dosha-quiz-list'),
    path('dosha-quiz/submit/', DoshaQuizSubmitView.as_view(), name='dosha-quiz-submit'),
    path('kiosk/start/', KioskStartSessionView.as_view(), name='kiosk-start-session'),
    path('kiosk/status/', KioskSessionStatusView.as_view(), name='kiosk-status'),
    path('kiosk/heartbeat/', KioskSessionHeartbeatView.as_view(), name='kiosk-heartbeat'),
    path('kiosk/lock/', KioskSessionLockView.as_view(), name='kiosk-lock'),
    path('kiosk/discard/', KioskSessionDiscardChangesView.as_view(), name='kiosk-discard'),
    path('kiosk/secure-screen/', KioskSessionSecureScreenView.as_view(), name='kiosk-secure-screen'),
    path('kiosk/pending-changes/', KioskSessionPendingChangesView.as_view(), name='kiosk-pending-changes'),
    path('anonymize/<str:phone_number>/', AnonymizeProfileView.as_view(), name='clinical-profile-anonymize'),
    
    # Se incluye el router al final para que maneje todas las rutas registradas.
    path('', include(router.urls)),
]
