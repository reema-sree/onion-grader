"""Public Verification API & Mobile-Friendly Server-Rendered HTML View."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.grade_result import GradeResult
from ..models.lot import Lot
from ..models.onion_detection import OnionDetection
from ..models.report import Report
from ..schemas.report import ReportVerifyResponse
from ..services.report_hash import build_canonical_report_payload, compute_canonical_hash

router = APIRouter()


def compute_report_verification_data(report_id: int, db: Session) -> ReportVerifyResponse:
    """Core logic to check digital authenticity, tampering, and superseding status."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report #{report_id} not found."
        )

    lot = db.query(Lot).filter(Lot.id == report.lot_id).first()
    if not lot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated lot not found."
        )

    # Fetch grade result
    grade_res = (
        db.query(GradeResult)
        .filter(GradeResult.lot_id == lot.id)
        .order_by(GradeResult.computed_at.desc())
        .first()
    )
    if not grade_res:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Grade result missing for this lot."
        )

    detections = db.query(OnionDetection).filter(OnionDetection.lot_id == lot.id).all()

    # Recompute canonical hash from current database state
    current_canonical_payload = build_canonical_report_payload(
        lot=lot,
        grade_result=grade_res,
        detections=detections,
        version=report.version,
    )
    computed_hash = compute_canonical_hash(current_canonical_payload)

    # Verification checks
    is_hash_match = (computed_hash == report.report_hash)
    is_superseded = (report.superseded_by is not None)

    # If the report is superseded by a newer version, report status is SUPERSEDED
    if is_superseded:
        status_label = "SUPERSEDED"
        is_valid = True
        summary_msg = f"This report was superseded by Report #{report.superseded_by} due to subsequent inspection updates."
    elif not is_hash_match:
        status_label = "TAMPERED"
        is_valid = False
        summary_msg = "ALERT: Tamper detected! Cryptographic signature mismatch — database records have been altered after report issuance."
    else:
        status_label = "VALID"
        is_valid = True
        summary_msg = "Official AgriGrade inspection report verified authentic."

    centre_name = lot.centre.name if lot.centre else f"Centre #{lot.centre_id}"

    return ReportVerifyResponse(
        report_id=report.id,
        lot_id=lot.id,
        lot_number=lot.lot_number or f"LOT-{lot.id}",
        farmer_name=lot.farmer_name,
        centre_name=centre_name,
        version=report.version,
        status=status_label,
        is_valid=is_valid,
        is_superseded=is_superseded,
        superseded_by_report_id=report.superseded_by,
        stored_hash=report.report_hash,
        computed_hash=computed_hash,
        grade_a_pct=grade_res.grade_a_pct,
        urs_pct=grade_res.urs_pct,
        total_count=grade_res.total_count,
        generated_at=report.generated_at,
        is_mock=report.is_mock,
        summary=summary_msg,
    )


@router.get("/verify/{report_id}", response_model=ReportVerifyResponse)
def verify_report_json(
    report_id: int,
    db: Session = Depends(get_db),
):
    """Public endpoint to verify report authenticity and detect database tampering (JSON API)."""
    return compute_report_verification_data(report_id, db)


@router.get("/verify/{report_id}/view", response_class=HTMLResponse)
def verify_report_html(
    report_id: int,
    db: Session = Depends(get_db),
):
    """Public mobile-responsive HTML certificate verification page."""
    data = compute_report_verification_data(report_id, db)

    # Status badge styling
    if data.status == "VALID":
        badge_bg = "#DEF7EC"
        badge_color = "#03543F"
        badge_border = "#31C48D"
        icon = "✓"
        status_heading = "VERIFIED AUTHENTIC"
    elif data.status == "SUPERSEDED":
        badge_bg = "#FEF08A"
        badge_color = "#713F12"
        badge_border = "#EAB308"
        icon = "ℹ"
        status_heading = f"SUPERSEDED VERSION (v{data.version})"
    else:  # TAMPERED
        badge_bg = "#FDE8E8"
        badge_color = "#9B1C1C"
        badge_border = "#F98080"
        icon = "⚠"
        status_heading = "TAMPERING DETECTED"

    mock_badge = ""
    if data.is_mock:
        mock_badge = """
        <div style="background:#FFF3CD; color:#856404; padding:8px 12px; border-radius:6px; font-weight:600; font-size:13px; margin-bottom:16px; border:1px solid #FFEEBA; text-align:center;">
          DEMO DATA - Generated in Simulation Mode
        </div>
        """

    superseded_notice = ""
    if data.is_superseded and data.superseded_by_report_id:
        superseded_notice = f"""
        <div style="background:#EFF6FF; color:#1E40AF; padding:10px 14px; border-radius:6px; font-size:13px; margin-top:12px; border:1px solid #BFDBFE;">
          <b>Note:</b> A newer version of this report is available:
          <a href="/verify/{data.superseded_by_report_id}/view" style="color:#2563EB; font-weight:bold; text-decoration:underline;">
            View Report #{data.superseded_by_report_id}
          </a>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>AgriGrade Verification - Report #{data.report_id}</title>
      <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
          background: #F3F4F6;
          color: #1F2937;
          line-height: 1.5;
          padding: 16px;
        }}
        .container {{
          max-width: 540px;
          margin: 0 auto;
          background: #FFFFFF;
          border-radius: 12px;
          box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
          overflow: hidden;
        }}
        .header {{
          background: #1E3A8A;
          color: #FFFFFF;
          padding: 20px;
          text-align: center;
        }}
        .header h1 {{ font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
        .header p {{ font-size: 13px; opacity: 0.85; }}
        .content {{ padding: 20px; }}
        .status-badge {{
          background: {badge_bg};
          color: {badge_color};
          border: 1.5px solid {badge_border};
          border-radius: 8px;
          padding: 14px;
          text-align: center;
          margin-bottom: 16px;
        }}
        .status-badge .icon {{ font-size: 24px; font-weight: bold; margin-bottom: 4px; }}
        .status-badge .heading {{ font-size: 16px; font-weight: 800; }}
        .status-badge .summary {{ font-size: 13px; margin-top: 4px; }}
        .grid {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
          margin-bottom: 16px;
        }}
        .card {{
          background: #F9FAFB;
          border: 1px solid #E5E7EB;
          border-radius: 8px;
          padding: 12px;
          text-align: center;
        }}
        .card .label {{ font-size: 11px; color: #6B7280; text-transform: uppercase; font-weight: 600; }}
        .card .val {{ font-size: 18px; font-weight: 800; color: #111827; margin-top: 2px; }}
        .meta-list {{
          background: #F9FAFB;
          border: 1px solid #E5E7EB;
          border-radius: 8px;
          padding: 12px 16px;
          margin-bottom: 16px;
          font-size: 14px;
        }}
        .meta-row {{
          display: flex;
          justify-content: space-between;
          padding: 6px 0;
          border-bottom: 1px solid #F3F4F6;
        }}
        .meta-row:last-child {{ border-bottom: none; }}
        .meta-row .k {{ color: #6B7280; font-weight: 500; }}
        .meta-row .v {{ font-weight: 600; color: #111827; text-align: right; }}
        .hash-box {{
          background: #1E293B;
          color: #E2E8F0;
          padding: 12px;
          border-radius: 8px;
          font-family: monospace;
          font-size: 10px;
          word-break: break-all;
          margin-bottom: 16px;
        }}
        .hash-title {{ font-size: 11px; color: #94A3B8; margin-bottom: 4px; font-family: sans-serif; text-transform: uppercase; }}
        .footer {{
          text-align: center;
          font-size: 12px;
          color: #9CA3AF;
          padding: 16px;
          border-top: 1px solid #E5E7EB;
        }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>AgriGrade Verification</h1>
          <p>Government of India Agmark Standards</p>
        </div>

        <div class="content">
          {mock_badge}

          <div class="status-badge">
            <div class="icon">{icon}</div>
            <div class="heading">{status_heading}</div>
            <div class="summary">{data.summary}</div>
          </div>

          <div class="grid">
            <div class="card" style="background:#F0FDF4; border-color:#BBF7D0;">
              <div class="label" style="color:#166534;">Grade A</div>
              <div class="val" style="color:#15803D;">{data.grade_a_pct:.1f}%</div>
            </div>
            <div class="card" style="background:#FEF2F2; border-color:#FECACA;">
              <div class="label" style="color:#991B1B;">URS</div>
              <div class="val" style="color:#B91C1C;">{data.urs_pct:.1f}%</div>
            </div>
          </div>

          <div class="meta-list">
            <div class="meta-row">
              <span class="k">Batch / Lot ID</span>
              <span class="v">{data.lot_number}</span>
            </div>
            <div class="meta-row">
              <span class="k">Farmer Name</span>
              <span class="v">{data.farmer_name}</span>
            </div>
            <div class="meta-row">
              <span class="k">Procurement Centre</span>
              <span class="v">{data.centre_name}</span>
            </div>
            <div class="meta-row">
              <span class="k">Total Onions</span>
              <span class="v">{data.total_count}</span>
            </div>
            <div class="meta-row">
              <span class="k">Report Version</span>
              <span class="v">v{data.version}</span>
            </div>
            <div class="meta-row">
              <span class="k">Generated At</span>
              <span class="v">{data.generated_at.strftime('%Y-%m-%d %H:%M UTC')}</span>
            </div>
          </div>

          <div class="hash-box">
            <div class="hash-title">Canonical SHA-256 Hash</div>
            {data.stored_hash}
          </div>

          {superseded_notice}
        </div>

        <div class="footer">
          AgriGrade Digital Authenticity System • Tamper-Proof Cryptographic Verification
        </div>
      </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)
