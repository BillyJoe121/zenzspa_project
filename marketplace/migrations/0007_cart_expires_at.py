from django.db import migrations, models
import django.utils.timezone
from datetime import timedelta


def default_expiration():
    return django.utils.timezone.now() + timedelta(days=7)


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0006_order_estimated_delivery_date_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cart',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
