from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0003_alter_commissionledger_source_payment'),
    ]

    operations = [
        migrations.AlterField(
            model_name='commissionledger',
            name='source_payment',
            field=models.ForeignKey(help_text='Pago original que generó la comisión.', on_delete=models.PROTECT, related_name='commission_entries', to='finances.payment'),
        ),
    ]
