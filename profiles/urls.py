# profiles/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
# --- INICIO DE LA MODIFICACIÓN ---
# Se importa el ViewSet principal y se eliminan las vistas que ahora maneja el router.
from .views import (
    ClinicalProfileViewSet, DoshaQuestionViewSet,
    DoshaQuestionListView, DoshaQuizSubmitView,
    KioskStartSessionView
)
# --- FIN DE LA MODIFICACIÓN ---

router = DefaultRouter()

router.register(r'profiles', ClinicalProfileViewSet, basename='clinical-profile')

router.register(r'dosha-questions-admin', DoshaQuestionViewSet, basename='dosha-question-admin')


urlpatterns = [
    # Las rutas de perfiles ahora son manejadas por el router, se eliminan las entradas manuales.
    
    # Se mantienen las rutas que no forman parte de un ViewSet estándar.
    path('dosha-quiz/', DoshaQuestionListView.as_view(), name='dosha-quiz-list'),
    path('dosha-quiz/submit/', DoshaQuizSubmitView.as_view(), name='dosha-quiz-submit'),
    path('kiosk/start/', KioskStartSessionView.as_view(), name='kiosk-start-session'),
    
    # Se incluye el router al final para que maneje todas las rutas registradas.
    path('', include(router.urls)),
]