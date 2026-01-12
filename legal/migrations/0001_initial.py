import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0013_rename_core_idempo_request_hash_idx_core_idempo_request_9b0aea_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegalDocument",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True, editable=False)),
                ("slug", models.SlugField(help_text="Identificador único legible, ej: terms-and-conditions", max_length=100)),
                ("title", models.CharField(max_length=200)),
                ("body", models.TextField(help_text="Contenido renderizable (markdown/HTML)")),
                (
                    "doc_type",
                    models.CharField(
                        choices=[
                            ("GLOBAL_POPUP", "Términos Generales"),
                            ("PROFILE", "Perfil/Onboarding"),
                            ("PURCHASE", "Compra/Checkout"),
                            ("OTHER", "Otro"),
                        ],
                        default="GLOBAL_POPUP",
                        max_length=20,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("is_active", models.BooleanField(default=True)),
                ("effective_at", models.DateTimeField(blank=True, help_text="Fecha desde la cual aplica esta versión.", null=True)),
                ("notes", models.CharField(blank=True, max_length=255)),
            ],
            options={
                "verbose_name": "Documento Legal",
                "verbose_name_plural": "Documentos Legales",
                "ordering": ["-created_at"],
                "unique_together": {("slug", "version")},
            },
        ),
        migrations.CreateModel(
            name="UserConsent",
            fields=[
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True, editable=False)),
                (
                    "document_version",
                    models.PositiveIntegerField(help_text="Versión del documento al momento de la aceptación."),
                ),
                (
                    "anonymous_id",
                    models.CharField(
                        blank=True,
                        help_text="Identificador temporal/fingerprint para usuarios anónimos.",
                        max_length=64,
                    ),
                ),
                (
                    "context_type",
                    models.CharField(
                        choices=[
                            ("GLOBAL", "Consentimiento Global"),
                            ("PROFILE", "Perfil"),
                            ("ORDER", "Orden"),
                            ("APPOINTMENT", "Cita"),
                            ("OTHER", "Otro"),
                        ],
                        default="GLOBAL",
                        max_length=20,
                    ),
                ),
                ("context_id", models.CharField(blank=True, max_length=64)),
                ("context_label", models.CharField(blank=True, help_text="Texto auxiliar ej: ORDER-1234, PROFILE-UUID.", max_length=120)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True)),
                ("accepted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="consents",
                        to="legal.legaldocument",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="consents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Consentimiento de Usuario",
                "verbose_name_plural": "Consentimientos de Usuario",
                "ordering": ["-accepted_at"],
            },
        ),
        migrations.AddIndex(
            model_name="legaldocument",
            index=models.Index(fields=["slug", "version"], name="legal_legald_slug_versi_b7f135_idx"),
        ),
        migrations.AddIndex(
            model_name="legaldocument",
            index=models.Index(fields=["doc_type", "is_active"], name="legal_legald_doc_typ_c0ce6a_idx"),
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["document", "document_version"], name="legal_userco_document_6df65c_idx"),
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["user", "document"], name="legal_userco_user_id_3ae876_idx"),
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["anonymous_id", "document"], name="legal_userco_anonymo_99b87e_idx"),
        ),
        migrations.AddIndex(
            model_name="userconsent",
            index=models.Index(fields=["context_type", "context_id"], name="legal_userco_context_78b0b1_idx"),
        ),
        migrations.AddConstraint(
            model_name="userconsent",
            constraint=models.UniqueConstraint(
                fields=["document", "document_version", "user", "anonymous_id", "context_type", "context_id"],
                name="unique_user_consent_per_context",
            ),
        ),
    ]
