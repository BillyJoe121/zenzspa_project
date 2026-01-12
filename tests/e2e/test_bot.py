import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from bot.models import (
    AnonymousUser,
    BotConfiguration,
    BotConversationLog,
    HumanHandoffRequest,
    HumanMessage,
)
from bot.services import ConversationMemoryService
from users.models import CustomUser


pytestmark = pytest.mark.django_db


def _make_client_user(role=CustomUser.Role.CLIENT, phone="+573600000001"):
    return CustomUser.objects.create_user(
        phone_number=phone,
        password="Secret123!",
        first_name="Cliente",
        is_verified=True,
        role=role,
    )


def _fake_llm_response(prompt_text: str):
    """
    Analiza el último mensaje del prompt y responde en JSON controlado.
    Esto evita llamadas externas a Gemini.
    """
    last_user_line = ""
    for line in prompt_text.splitlines()[::-1]:
        if line.strip().startswith("USER:"):
            last_user_line = line.split("USER:", 1)[-1].strip()
            break

    analysis = {"action": "REPLY", "toxicity_level": 0, "customer_score": 40, "intent": "INFO"}
    reply = "Te comparto nuestros servicios disponibles."

    if "persona real" in last_user_line or "hablar con alguien" in last_user_line:
        analysis["action"] = "HANDOFF"
        analysis["intent"] = "HANDOFF_REQUEST"
        reply = "Te conecto con una persona del equipo."
    elif "coqueteo" in last_user_line:
        analysis["toxicity_level"] = 1
        reply = "Mantengamos la conversación en servicios del spa."
    elif "insinuación" in last_user_line or "sexual" in last_user_line:
        analysis["toxicity_level"] = 2
        reply = "Mensaje inapropiado. Hablemos de servicios."
    elif "acoso" in last_user_line:
        analysis["toxicity_level"] = 3
        analysis["action"] = "BLOCK"
        reply = "Conversación bloqueada por acoso."
    elif "capital de francia" in last_user_line.lower():
        reply = "Solo puedo ayudarte con servicios del spa."
    elif "cómo me llamo" in last_user_line.lower() and "Carlos" in prompt_text:
        reply = "Te llamas Carlos, ¿en qué más te ayudo?"

    meta = {"source": "stub", "tokens": 42}
    return {"reply_to_user": reply, "analysis": analysis}, meta


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def bot_config():
    return BotConfiguration.objects.create(
        site_name="Studio Zens",
        booking_url="https://example.com/agendar",
        admin_phone="+57 300 000 0000",
    )


@pytest.fixture(autouse=True)
def stub_llm(monkeypatch):
    from bot.views.webhook.bot_webhook import GeminiService

    monkeypatch.setattr(GeminiService, "generate_response", staticmethod(_fake_llm_response))


def test_registered_user_conversation_creates_log_and_tokens(api_client):
    user = _make_client_user()
    api_client.force_authenticate(user=user)

    resp = api_client.post(
        reverse("bot-webhook"),
        {"message": "Hola, qué servicios ofrecen?"},
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    assert "servicios" in resp.data["reply"].lower()

    log = BotConversationLog.objects.filter(user=user).latest("created_at")
    assert log.tokens_used == 42
    assert log.was_blocked is False


def test_anonymous_conversation_returns_session_and_log(api_client):
    resp = api_client.post(
        reverse("bot-webhook"),
        {"message": "Quiero información de masajes"},
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data.get("session_id")

    log = BotConversationLog.objects.filter(anonymous_user__isnull=False).latest("created_at")
    assert log.anonymous_user is not None
    assert AnonymousUser.objects.filter(pk=log.anonymous_user.pk).exists()


def test_conversation_memory_is_used_in_response(api_client):
    user = _make_client_user(phone="+573600000010")
    api_client.force_authenticate(user=user)

    api_client.post(reverse("bot-webhook"), {"message": "Me llamo Carlos"}, format="json")
    api_client.post(reverse("bot-webhook"), {"message": "Cuánto cuesta el masaje relajante?"}, format="json")
    resp = api_client.post(reverse("bot-webhook"), {"message": "Cómo me llamo?"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    assert "carlos" in resp.data["reply"].lower()
    history = ConversationMemoryService.get_conversation_history(user.id)
    assert len(history) >= 2


def test_handoff_request_is_created_for_explicit_request(api_client, monkeypatch):
    user = _make_client_user(phone="+573600000020")
    api_client.force_authenticate(user=user)

    monkeypatch.setattr("bot.views.webhook.bot_webhook.HandoffNotificationService.send_handoff_notification", lambda *args, **kwargs: None)
    monkeypatch.setattr("bot.tasks.check_handoff_timeout.apply_async", lambda *args, **kwargs: None)

    resp = api_client.post(reverse("bot-webhook"), {"message": "Quiero hablar con una persona real"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    handoff = HumanHandoffRequest.objects.latest("created_at")
    assert handoff.user == user
    assert handoff.status == HumanHandoffRequest.Status.PENDING
    assert handoff.conversation_log is not None
    assert handoff.client_interests
    assert resp.data["meta"].get("handoff_created") is True


def test_anonymous_handoff_creates_request(api_client, monkeypatch):
    monkeypatch.setattr("bot.views.webhook.bot_webhook.HandoffNotificationService.send_handoff_notification", lambda *args, **kwargs: None)
    monkeypatch.setattr("bot.tasks.check_handoff_timeout.apply_async", lambda *args, **kwargs: None)

    resp = api_client.post(reverse("bot-webhook"), {"message": "Quiero hablar con alguien"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data.get("session_id")
    handoff = HumanHandoffRequest.objects.latest("created_at")
    assert handoff.anonymous_user is not None
    assert handoff.status == HumanHandoffRequest.Status.PENDING


def test_toxicity_level_three_blocks_conversation(api_client):
    user = _make_client_user(phone="+573600000030")
    api_client.force_authenticate(user=user)

    resp = api_client.post(reverse("bot-webhook"), {"message": "Mensaje de acoso explícito"}, format="json")

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    log = BotConversationLog.objects.filter(user=user).latest("created_at")
    assert log.was_blocked is True
    assert log.block_reason == "agent_toxicity_block"


def test_rate_limit_returns_429(api_client, monkeypatch):
    user = _make_client_user(phone="+573600000040")
    api_client.force_authenticate(user=user)

    monkeypatch.setattr("bot.views.webhook.bot_webhook.BotSecurityService.check_velocity", lambda self: True)

    resp = api_client.post(reverse("bot-webhook"), {"message": "spam 1"}, format="json")

    assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert "mensaje" in str(resp.data).lower() or "rápido" in str(resp.data).lower()


def test_staff_can_send_message_in_handoff(api_client):
    staff = _make_client_user(role=CustomUser.Role.STAFF, phone="+573600000050")
    api_client.force_authenticate(user=staff)

    handoff = HumanHandoffRequest.objects.create(
        user=_make_client_user(phone="+573600000051"),
        status=HumanHandoffRequest.Status.ASSIGNED,
        assigned_to=staff,
        escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
        client_interests={"services_mentioned": ["Masaje"]},
        conversation_context={},
    )

    url = reverse("handoff-send-message", kwargs={"pk": handoff.id})
    resp = api_client.post(url, {"message": "Hola, ¿en qué puedo ayudarte?"}, format="json")

    assert resp.status_code == status.HTTP_201_CREATED
    handoff.refresh_from_db()
    assert handoff.status == HumanHandoffRequest.Status.IN_PROGRESS
    assert HumanMessage.objects.filter(handoff_request=handoff).exists()


def test_resolve_handoff_sets_resolved(api_client):
    staff = _make_client_user(role=CustomUser.Role.STAFF, phone="+573600000060")
    api_client.force_authenticate(user=staff)
    handoff = HumanHandoffRequest.objects.create(
        user=_make_client_user(phone="+573600000061"),
        status=HumanHandoffRequest.Status.ASSIGNED,
        assigned_to=staff,
        escalation_reason=HumanHandoffRequest.EscalationReason.EXPLICIT_REQUEST,
        client_interests={"services_mentioned": ["Masaje"]},
        conversation_context={},
    )

    url = reverse("handoff-resolve", kwargs={"pk": handoff.id})
    resp = api_client.post(url, {"resolution_notes": "Caso resuelto"}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    handoff.refresh_from_db()
    assert handoff.status == HumanHandoffRequest.Status.RESOLVED
    assert handoff.resolved_at is not None
