# Generated manually for Wompi integration
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('spa', '0009_appointment_outcome_payment_order_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='customer_legal_id',
            field=models.CharField(blank=True, default='', help_text='Documento de identidad del pagador (para PSE, etc.)', max_length=50),
        ),
        migrations.AddField(
            model_name='payment',
            name='customer_legal_id_type',
            field=models.CharField(blank=True, choices=[('CC', 'Cédula de Ciudadanía'), ('CE', 'Cédula de Extranjería'), ('NIT', 'Número de Identificación Tributaria'), ('PP', 'Pasaporte'), ('TI', 'Tarjeta de Identidad'), ('DNI', 'Documento Nacional de Identidad'), ('RG', 'Carteira de Identidade / Registro Geral'), ('OTHER', 'Otro')], default='', help_text='Tipo de documento del pagador', max_length=10),
        ),
        migrations.AddField(
            model_name='payment',
            name='tax_vat_in_cents',
            field=models.PositiveIntegerField(blank=True, help_text='IVA en centavos (incluido en amount, no se suma)', null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='tax_consumption_in_cents',
            field=models.PositiveIntegerField(blank=True, help_text='Impuesto al consumo en centavos (incluido en amount)', null=True),
        ),
        migrations.AddField(
            model_name='payment',
            name='payment_method_type',
            field=models.CharField(blank=True, choices=[('CARD', 'Tarjeta de Crédito/Débito'), ('PSE', 'PSE'), ('NEQUI', 'Nequi'), ('BANCOLOMBIA_TRANSFER', 'Botón Bancolombia'), ('BANCOLOMBIA_QR', 'QR Bancolombia'), ('DAVIPLATA', 'Daviplata'), ('BNPL', 'Buy Now Pay Later'), ('PCOL', 'Puntos Colombia')], default='', help_text='Método de pago utilizado en Wompi', max_length=30),
        ),
        migrations.AddField(
            model_name='payment',
            name='payment_method_data',
            field=models.JSONField(blank=True, default=dict, help_text='Datos adicionales del método de pago (ej: financial_institution_code para PSE)'),
        ),
    ]
