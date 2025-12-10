# Generated migration to seed default BotConfiguration

from django.db import migrations


def create_default_bot_configuration(apps, schema_editor):
    """
    Crea la configuracion por defecto del bot si no existe.
    Esto garantiza que el chatbot funcione inmediatamente despues de migrate.
    """
    BotConfiguration = apps.get_model('bot', 'BotConfiguration')

    if not BotConfiguration.objects.exists():
        BotConfiguration.objects.create(
            site_name="Studio Zens",
            booking_url="https://www.studiozens.com/agendar",
            admin_phone="+57 300 000 0000",
            is_active=True,
        )


def reverse_migration(apps, schema_editor):
    """
    Reverse: No eliminamos la configuracion para evitar perder datos personalizados.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('bot', '0010_alter_humanhandoffrequest_status'),
    ]

    operations = [
        migrations.RunPython(
            create_default_bot_configuration,
            reverse_migration,
        ),
    ]
