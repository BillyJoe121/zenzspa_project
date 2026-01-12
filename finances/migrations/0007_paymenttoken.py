from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0006_add_payment_indexes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('token_id', models.CharField(db_index=True, max_length=255, unique=True)),
                ('token_type', models.CharField(blank=True, default='', max_length=50)),
                ('status', models.CharField(choices=[('PENDING', 'PENDING'), ('APPROVED', 'APPROVED'), ('DECLINED', 'DECLINED'), ('ERROR', 'ERROR')], default='PENDING', max_length=20)),
                ('customer_email', models.EmailField(blank=True, default='', max_length=254)),
                ('phone_number', models.CharField(blank=True, default='', max_length=30)),
                ('raw_payload', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True, default='')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payment_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='paymenttoken',
            index=models.Index(fields=['status'], name='payment_token_status_idx'),
        ),
        migrations.AddIndex(
            model_name='paymenttoken',
            index=models.Index(fields=['token_type'], name='payment_token_type_idx'),
        ),
    ]
