from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_customuser_cancellation_streak'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='phone_number',
            field=models.CharField(
                max_length=15,
                unique=True,
                validators=[django.core.validators.RegexValidator(
                    message='El número debe estar en formato internacional (+573001234567).',
                    regex='^\\+[1-9]\\d{9,14}$')],
                verbose_name='Número de Teléfono',
            ),
        ),
        migrations.AddIndex(
            model_name='customuser',
            index=models.Index(fields=['email'], name='users_custo_email_e8f2ee_idx'),
        ),
        migrations.AddIndex(
            model_name='customuser',
            index=models.Index(fields=['role', 'is_active'], name='users_custo_role_is__2b457f_idx'),
        ),
        migrations.AddIndex(
            model_name='customuser',
            index=models.Index(fields=['is_persona_non_grata'], name='users_custo_is_pers_07be15_idx'),
        ),
        migrations.AddIndex(
            model_name='customuser',
            index=models.Index(fields=['vip_expires_at'], name='users_custo_vip_exp_99392d_idx'),
        ),
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['user', 'is_active'], name='users_users_user_is__94c994_idx'),
        ),
        migrations.AddIndex(
            model_name='usersession',
            index=models.Index(fields=['last_activity'], name='users_users_last_ac_2824a4_idx'),
        ),
        migrations.AddIndex(
            model_name='otpattempt',
            index=models.Index(fields=['phone_number', 'created_at'], name='users_otpat_phone_n_827658_idx'),
        ),
        migrations.AddIndex(
            model_name='otpattempt',
            index=models.Index(fields=['attempt_type', 'is_successful'], name='users_otpat_attempt_bb01aa_idx'),
        ),
    ]
