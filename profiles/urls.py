from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ClinicalProfileDetailView, DoshaQuestionViewSet,
    DoshaQuestionListView, DoshaQuizSubmitView,
    KioskStartSessionView # Se importa la nueva vista
)

router = DefaultRouter()
router.register(r'dosha-questions-admin', DoshaQuestionViewSet, basename='dosha-question-admin')

urlpatterns = [
    path('clinical-profile/me/', ClinicalProfileDetailView.as_view(), name='my-clinical-profile-detail'),
    path('clinical-profile/<str:phone_number>/', ClinicalProfileDetailView.as_view(), name='clinical-profile-detail'),
    
    path('dosha-quiz/', DoshaQuestionListView.as_view(), name='dosha-quiz-list'),
    path('dosha-quiz/submit/', DoshaQuizSubmitView.as_view(), name='dosha-quiz-submit'),
    
    # --- INICIO DE LA MODIFICACIÓN ---
    # Endpoint para que el STAFF inicie una sesión de quiosco
    path('kiosk/start/', KioskStartSessionView.as_view(), name='kiosk-start-session'),
    # --- FIN DE LA MODIFICACIÓN ---
    
    path('', include(router.urls)),
]