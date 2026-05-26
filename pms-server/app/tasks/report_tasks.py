"""
정기 PDF 리포트 생성 Celery 태스크.
Celery beat 스케줄에 의해 매주 월요일 08:00에 실행.
컴플라이언스 현황 요약을 PDF로 생성하고 MinIO에 저장한다.
"""
import asyncio
import io
import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.tasks.report_tasks.generate_compliance_report",
    queue="reporting",
)
def generate_compliance_report():
    """주간 컴플라이언스 PDF 리포트 생성."""
    _run_async(_do_generate_report())


async def _do_generate_report():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        from app.services.compliance import get_org_compliance_summary
        summary = await get_org_compliance_summary(db)

    await engine.dispose()

    pdf_bytes = _build_pdf(summary)
    _upload_to_minio(pdf_bytes)
    logger.info("Compliance report generated and uploaded to MinIO")


def _build_pdf(summary: dict) -> bytes:
    """reportlab으로 컴플라이언스 요약 PDF를 생성한다."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
    except ImportError:
        logger.warning("reportlab not installed, generating plain-text report")
        text = _build_text_report(summary)
        return text.encode("utf-8")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="PMS 컴플라이언스 리포트")
    styles = getSampleStyleSheet()
    elements = []

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(Paragraph(f"PMS 컴플라이언스 리포트 — {now_str}", styles["Title"]))
    elements.append(Spacer(1, 12))

    # 요약 통계
    stats = [
        ["항목", "값"],
        ["전체 엔드포인트", str(summary.get("total_endpoints", 0))],
        ["평균 준수율", f"{summary.get('avg_compliance_pct', 0):.1f}%"],
        ["미준수 엔드포인트", str(summary.get("non_compliant_count", 0))],
    ]
    tbl = Table(stats, colWidths=[200, 200])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1890ff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 16))

    # 엔드포인트별 준수율
    endpoints = summary.get("endpoints", [])
    if endpoints:
        elements.append(Paragraph("엔드포인트별 준수율 (하위 20개)", styles["Heading2"]))
        rows = [["엔드포인트 ID", "준수율 (%)", "누락 패치"]]
        for ep in sorted(endpoints, key=lambda x: x.get("compliance_pct", 100))[:20]:
            rows.append([
                ep.get("endpoint_id", "")[:8] + "…",
                f"{ep.get('compliance_pct', 0):.1f}",
                str(ep.get("missing", 0)),
            ])
        tbl2 = Table(rows, colWidths=[160, 100, 100])
        tbl2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]))
        elements.append(tbl2)

    doc.build(elements)
    return buf.getvalue()


def _build_text_report(summary: dict) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"PMS 컴플라이언스 리포트 — {now_str}",
        "=" * 60,
        f"전체 엔드포인트: {summary.get('total_endpoints', 0)}",
        f"평균 준수율: {summary.get('avg_compliance_pct', 0):.1f}%",
        f"미준수 엔드포인트: {summary.get('non_compliant_count', 0)}",
    ]
    return "\n".join(lines)


def _upload_to_minio(pdf_bytes: bytes) -> str:
    from app.services.file_distribution import _get_minio_client

    now = datetime.now(timezone.utc)
    object_name = f"reports/compliance_{now.strftime('%Y%m%d_%H%M%S')}.pdf"

    client = _get_minio_client()
    client.put_object(
        settings.minio_bucket_patches,
        object_name,
        io.BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )
    return object_name


@celery_app.task(
    name="app.tasks.report_tasks.generate_report_on_demand",
    queue="reporting",
)
def generate_report_on_demand(report_type: str = "compliance") -> str:
    """API 요청에 의한 즉시 리포트 생성. MinIO 오브젝트 경로 반환."""
    if report_type == "compliance":
        _run_async(_do_generate_report())
    return f"report/{report_type} generated"
