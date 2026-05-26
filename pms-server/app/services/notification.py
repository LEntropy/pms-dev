"""이메일 알림 서비스 — 배포 완료/실패 시 담당자에게 발송."""
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


async def send_deployment_notification(
    deployment_id: str,
    status: str,
    success_count: int,
    failure_count: int,
    initiated_by: str | None,
    recipient_emails: list[str],
) -> None:
    """배포 결과 이메일 발송. SMTP 미설정 시 로그만 남긴다."""
    from app.config import settings

    if not settings.smtp_host or not recipient_emails:
        logger.info(
            "Deployment %s %s (success=%d, failure=%d) — SMTP not configured, skipping email",
            deployment_id, status, success_count, failure_count,
        )
        return

    subject = f"[PMS] 배포 {'완료' if status == 'completed' else '실패'} — {deployment_id[:8]}"
    body = (
        f"배포 ID: {deployment_id}\n"
        f"상태: {status}\n"
        f"성공: {success_count}대 / 실패: {failure_count}대\n"
        f"담당자: {initiated_by or '알 수 없음'}\n"
    )

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipient_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        import aiosmtplib

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_tls,
        )
        logger.info("Deployment notification sent to %s", recipient_emails)
    except Exception as exc:
        logger.warning("Failed to send deployment notification: %s", exc)
