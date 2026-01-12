from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0007_alter_clinicalprofile_accidents_notes_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='consentdocument',
            name='revoked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='consentdocument',
            name='revoked_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='revoked_consents', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='consentdocument',
            name='revoked_reason',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
