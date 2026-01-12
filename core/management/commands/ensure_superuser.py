"""
Management command to create a superuser if it doesn't exist.
Usage: python manage.py ensure_superuser
"""
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create a superuser if it doesn't exist (for production deployment)"

    def handle(self, *args, **options):
        phone_number = os.getenv("DJANGO_SUPERUSER_PHONE", "+573157589548")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
        first_name = os.getenv("DJANGO_SUPERUSER_FIRST_NAME", "Joe")
        last_name = os.getenv("DJANGO_SUPERUSER_LAST_NAME", "Admin")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", None)

        if not password:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  DJANGO_SUPERUSER_PASSWORD not set. Skipping superuser creation."
                )
            )
            return

        if User.objects.filter(phone_number=phone_number).exists():
            self.stdout.write(
                self.style.SUCCESS(f"✓ Superuser with phone {phone_number} already exists.")
            )
            return

        try:
            user = User.objects.create_superuser(
                phone_number=phone_number,
                password=password,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role='ADMIN',
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Superuser created successfully: {user.phone_number} ({user.first_name})"
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Error creating superuser: {str(e)}")
            )
            raise
