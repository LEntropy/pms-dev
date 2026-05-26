from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "pms",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.deployment_tasks",
        "app.tasks.report_tasks",
        "app.tasks.sync_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_routes={
        "app.tasks.deployment_tasks.*": {"queue": "deployment"},
        "app.tasks.report_tasks.*": {"queue": "reporting"},
        "app.tasks.sync_tasks.*": {"queue": "default"},
    },
    beat_schedule={
        # 매주 월요일 08:00 KST 컴플라이언스 PDF 리포트
        "weekly-compliance-report": {
            "task": "app.tasks.report_tasks.generate_compliance_report",
            "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
        },
        # 매일 02:00 KST LDAP/AD 동기화
        "daily-ldap-sync": {
            "task": "app.tasks.sync_tasks.ldap_sync",
            "schedule": crontab(hour=2, minute=0),
        },
        # 매주 일요일 03:00 KST OpenVAS 스캔
        "weekly-openvas-scan": {
            "task": "app.tasks.sync_tasks.openvas_scan",
            "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        },
    },
)
