from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_alter_idempotencykey_key_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='idempotencykey',
            index=models.Index(
                fields=['request_hash'],
                name='core_idempo_request_hash_idx',
            ),
        ),
    ]
