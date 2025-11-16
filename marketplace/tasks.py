import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def notify_order_status_change(order_id):
    logger.info("Estado de la orden %s actualizado.", order_id)
