"""
Comando Django para revisar y auto-bloquear IPs sospechosas.
Uso: python manage.py check_suspicious_ips [--days=7] [--dry-run]

Este comando revisa todas las IPs con actividades sospechosas y las bloquea
automáticamente si cumplen los criterios configurados.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from bot.models import SuspiciousActivity
from bot.alerts import AutoBlockService


class Command(BaseCommand):
    help = 'Revisa IPs sospechosas y aplica auto-bloqueo si es necesario'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Número de días a analizar (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se haría sin realizar cambios'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        since = timezone.now() - timedelta(days=days)

        self.stdout.write(
            self.style.WARNING(f'Revisando actividades sospechosas de los últimos {days} días...')
        )

        if dry_run:
            self.stdout.write(self.style.WARNING('MODO DRY-RUN: No se realizarán cambios'))

        # Obtener todas las IPs con actividades críticas
        critical_ips = SuspiciousActivity.objects.filter(
            created_at__gte=since,
            severity=SuspiciousActivity.SeverityLevel.CRITICAL
        ).values_list('ip_address', flat=True).distinct()

        total_ips = len(critical_ips)
        blocked_count = 0

        self.stdout.write(f'Encontradas {total_ips} IPs con actividades críticas')

        for ip in critical_ips:
            # Obtener actividad más reciente para esta IP
            activity = SuspiciousActivity.objects.filter(
                ip_address=ip,
                created_at__gte=since
            ).first()

            if not activity:
                continue

            # Verificar si debe bloquearse
            if not dry_run:
                was_blocked, block = AutoBlockService.check_and_auto_block(
                    user=activity.user,
                    anonymous_user=activity.anonymous_user,
                    ip_address=ip
                )

                if was_blocked:
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✅ IP {ip} bloqueada automáticamente')
                    )
                    blocked_count += 1
                else:
                    self.stdout.write(f'  ℹ️ IP {ip} no cumple criterios de bloqueo o ya está bloqueada')
            else:
                # Dry run: solo mostrar info
                critical_count = SuspiciousActivity.objects.filter(
                    ip_address=ip,
                    created_at__gte=since,
                    severity=SuspiciousActivity.SeverityLevel.CRITICAL
                ).count()

                self.stdout.write(
                    f'  🔍 IP {ip}: {critical_count} actividades críticas'
                )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    '\nEjecuta sin --dry-run para aplicar los bloqueos'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Proceso completado: {blocked_count} IPs bloqueadas de {total_ips} analizadas'
                )
            )
