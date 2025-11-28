from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0014_consentdocument_revoked_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clinicalprofile',
            name='dosha',
            field=models.CharField(choices=[('VATA', 'Vata'), ('PITTA', 'Pitta'), ('KAPHA', 'Kapha'), ('UNKNOWN', 'Desconocido')], default='UNKNOWN', max_length=7, verbose_name='Dosha Dominante'),
        ),
        migrations.AlterField(
            model_name='historicalclinicalprofile',
            name='dosha',
            field=models.CharField(blank=True, choices=[('VATA', 'Vata'), ('PITTA', 'Pitta'), ('KAPHA', 'Kapha'), ('UNKNOWN', 'Desconocido')], default='UNKNOWN', max_length=7, verbose_name='Dosha Dominante'),
        ),
        migrations.AlterField(
            model_name='doshaoption',
            name='associated_dosha',
            field=models.CharField(choices=[('VATA', 'Vata'), ('PITTA', 'Pitta'), ('KAPHA', 'Kapha'), ('UNKNOWN', 'Desconocido')], max_length=7, verbose_name='Dosha Asociado'),
        ),
    ]
