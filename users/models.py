from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from core.models import BaseModel
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, phone_number, email, first_name, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('El número de teléfono es obligatorio.')
        if not email:
            raise ValueError('El correo electrónico es obligatorio.')

        email = self.normalize_email(email)
        user = self.model(
            phone_number=phone_number,
            email=email,
            first_name=first_name,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, email, first_name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('role', self.model.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')

        return self.create_user(phone_number, email, first_name, password, **extra_fields)


class CustomUser(BaseModel, AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        CLIENT = 'CLIENT', 'Cliente'
        VIP = 'VIP', 'Suscriptor VIP'
        STAFF = 'STAFF', 'Trabajador'
        ADMIN = 'ADMIN', 'Administrador'

    phone_number = models.CharField(
        max_length=15, unique=True, verbose_name='Número de Teléfono')
    email = models.EmailField(
        max_length=255, unique=True, verbose_name='Correo Electrónico')
    first_name = models.CharField(max_length=100, verbose_name='Nombre')
    last_name = models.CharField(
        max_length=100, blank=True, verbose_name='Apellido')

    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.CLIENT, verbose_name='Rol')
    vip_expires_at = models.DateField(
        null=True, blank=True, verbose_name="Fecha de Vencimiento VIP",
        help_text="Indica hasta qué fecha la membresía VIP del usuario está activa.")
    is_verified = models.BooleanField(
        default=False, verbose_name='Verificado por SMS')
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    is_staff = models.BooleanField(
        default=False, verbose_name='Personal del Staff')

    is_persona_non_grata = models.BooleanField(
        default=False, verbose_name="Cliente No Grato")

    # --- INICIO DE LA MODIFICACIÓN ---
    # Se elimina 'profile_picture' y se añaden los campos requeridos.
    internal_notes = models.TextField(
        blank=True, null=True, verbose_name="Notas Internas (Staff/Admin)")
    internal_photo_url = models.URLField(
        max_length=512, blank=True, null=True, verbose_name="URL de Foto Interna (Staff/Admin)")
    # --- FIN DE LA MODIFICACIÓN ---

    objects = CustomUserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['email', 'first_name']

    def __str__(self):
        return f"{self.first_name} ({self.phone_number})"

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'