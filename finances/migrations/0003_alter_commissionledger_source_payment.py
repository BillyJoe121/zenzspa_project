from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0002_add_payment_models'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commissionledger',
            name='source_payment',
            field=models.ForeignKey(blank=True, help_text='Pago original que generó la comisión.', null=True, on_delete=models.SET_NULL, related_name='commission_entries', to='finances.payment'),
        ),
    ]
