"""
Management command para limpiar usuarios anónimos expirados.

Uso:
    python manage.py cleanup_expired_sessions

Este comando debe ejecutarse periódicamente (ej: diariamente con cron/celery beat)
para prevenir crecimiento excesivo de la tabla AnonymousUser.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from bot.models import AnonymousUser


class Command(BaseCommand):
    help = 'Limpia usuarios anónimos expirados y no convertidos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la limpieza sin eliminar registros',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=0,
            help='Eliminar sesiones expiradas hace N días adicionales (por defecto: 0)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        extra_days = options['days']

        now = timezone.now()

        # Usuarios anónimos expirados y no convertidos
        query = AnonymousUser.objects.filter(
            expires_at__lt=now,
            converted_to_user__isnull=True
        )

        # Si se especificó días adicionales, filtrar más agresivamente
        if extra_days > 0:
            cutoff = now - timezone.timedelta(days=extra_days)
            query = query.filter(expires_at__lt=cutoff)

        count = query.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY RUN] Se eliminarían {count} usuarios anónimos expirados'
                )
            )
            if count > 0:
                # Mostrar algunos ejemplos
                samples = query[:5]
                self.stdout.write('\nEjemplos:')
                for anon in samples:
                    self.stdout.write(
                        f'  - ID: {anon.id}, Session: {anon.session_id}, '
                        f'Expiró: {anon.expires_at}, IP: {anon.ip_address}'
                    )
        else:
            deleted_count, _ = query.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Eliminados {deleted_count} usuarios anónimos expirados'
                )
            )

            # Log para auditoría
            if deleted_count > 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    "Limpieza de sesiones expiradas: %d registros eliminados",
                    deleted_count
                )
