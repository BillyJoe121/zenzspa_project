from celery import shared_task

from .services import DeveloperCommissionService


@shared_task
def run_developer_payout():
    """
    Task periódica para evaluar y ejecutar el payout al desarrollador
    en función de la deuda y el saldo Wompi disponible.
    """
    return DeveloperCommissionService.evaluate_payout()
