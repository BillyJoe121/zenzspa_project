from django.db import migrations


def delete_shipping_templates(apps, schema_editor):
    Template = apps.get_model("notifications", "NotificationTemplate")
    Template.objects.filter(
        event_code__in=["ORDER_SHIPPED", "ORDER_DELIVERED"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0006_add_bot_handoff_reply_template"),
    ]

    operations = [
        migrations.RunPython(delete_shipping_templates, migrations.RunPython.noop),
    ]
