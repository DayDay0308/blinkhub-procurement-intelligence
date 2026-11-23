"""Background worker: Celery with Redis as the broker.

    celery -A app.worker worker --beat --loglevel=info

Beat schedules the SLA check; the worker runs it. The task body is a plain
function (app.services.sla.run_sla_check), so it is tested without Redis.
"""

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.risk import run_risk_engine
from app.services.sla import run_sla_check

settings = get_settings()
celery_app = Celery("blinkhub", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    timezone="Africa/Johannesburg",
    task_acks_late=True,  # a crashed worker doesn't lose the task
    worker_prefetch_multiplier=1,
    beat_schedule={
        "invoice-sla-check": {
            "task": "app.worker.sla_check",
            "schedule": settings.sla_check_minutes * 60,
        },
        "nightly-risk-scan": {
            "task": "app.worker.risk_scan",
            "schedule": crontab(hour=2, minute=0),  # 02:00 Johannesburg time
        },
    },
)
log = logging.getLogger(__name__)


@celery_app.task(name="app.worker.sla_check")
def sla_check() -> dict[str, int]:
    with SessionLocal() as db, db.begin():
        result = run_sla_check(db)
    log.info("sla_check %s", result)
    return result


@celery_app.task(name="app.worker.risk_scan")
def risk_scan() -> dict:
    with SessionLocal() as db, db.begin():
        result = run_risk_engine(db)
    log.info("risk_scan %s", result)
    return result
