"""
PDF Report Generation Service — Kisan Setu.

Layout mirrors the Digital Report screen in the app design:
  ┌──────────────────────────────────────────────────┐
  │  LOGO  |  Kisan Setu Quality Inspection Certificate
  │  Batch code · Farmer · Centre · Date & Time
  ├──────────────────────────────────────────────────┤
  │  Three-Bucket Summary  (Grade A | URS | Defective | Total)
  ├──────────────────────────────────────────────────┤
  │  Annotated image thumbnail
  ├──────────────────────────────────────────────────┤
  │  Defect breakdown table
  ├──────────────────────────────────────────────────┤
  │  Verification block (AI result · Final result · Verified by · Reason)
  ├──────────────────────────────────────────────────┤
  │  QR  |  "Scan to verify"  |  SHA-256 hash
  └──────────────────────────────────────────────────┘

Fonts
-----
Noto Sans (Latin), Noto Sans Devanagari (Hindi), Noto Sans Telugu are
embedded so that non-ASCII text in farmer / centre names renders correctly.
The fonts are loaded from `backend/fonts/` (downloaded at setup time).
If a font file is missing we fall back to Helvetica gracefully.

DEMO DATA watermark is drawn when `report.is_mock` is True.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..core.config import settings
from ..models.audit_log import AuditLog
from ..models.grade_result import GradeResult
from ..models.lot import Lot
from ..models.onion_detection import OnionDetection
from ..models.report import Report
from .image_annotator import draw_annotated_lot_image

# ── Font registration ──────────────────────────────────────────────────────
_FONTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fonts"

_FONT_MAP = {
    "NotoSans": "NotoSans-Regular.ttf",
    "NotoSans-Bold": "NotoSans-Bold.ttf",
    "NotoSansDevanagari": "NotoSansDevanagari-Regular.ttf",
    "NotoSansTelugu": "NotoSansTelugu-Regular.ttf",
}

_FONTS_LOADED = False


def _register_fonts() -> str:
    """
    Register Noto TTF fonts with ReportLab.
    Returns the base font name to use ("NotoSans" or "Helvetica" as fallback).
    """
    global _FONTS_LOADED
    if _FONTS_LOADED:
        return "NotoSans"

    all_ok = True
    for name, filename in _FONT_MAP.items():
        path = _FONTS_DIR / filename
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
            except Exception:
                all_ok = False
        else:
            all_ok = False

    if all_ok:
        _FONTS_LOADED = True
        return "NotoSans"
    return "Helvetica"  # graceful fallback


# ── Custom numbered canvas with watermark ─────────────────────────────────

class _ReportCanvas(rl_canvas.Canvas):
    """Adds page numbers, top border, and optional DEMO DATA watermark."""

    def __init__(self, *args, is_mock: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list = []
        self.is_mock = is_mock

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_furniture(num_pages)
            super().showPage()
        super().save()

    def _draw_page_furniture(self, page_count: int):
        self.saveState()

        # DEMO DATA diagonal watermark
        if self.is_mock:
            self.setFont("Helvetica-Bold", 52)
            self.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.12))
            self.translate(297, 420)
            self.rotate(42)
            self.drawCentredString(0, 0, "DEMO DATA — MOCK")
            self.restoreState()
            self.saveState()

        # Top blue border line
        self.setStrokeColor(colors.HexColor("#276749"))
        self.setLineWidth(2.5)
        self.line(36, 808, 559, 808)

        # Footer
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#718096"))
        self.drawString(36, 22,
                        "Kisan Setu · AI-Powered Onion Inspection · Agmark Compliant")
        self.drawRightString(559, 22, f"Page {self._pageNumber} of {page_count}")

        self.restoreState()


# ── QR code helper ─────────────────────────────────────────────────────────

def _make_qr(url: str, dest: Path) -> Path:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1A202C", back_color="#FFFFFF")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(dest))
    return dest


# ── Public API ─────────────────────────────────────────────────────────────

def generate_qr_code_image(data_url: str, output_path: Path) -> Path:
    """Public helper kept for backward-compat with reports.py."""
    return _make_qr(data_url, output_path)


def generate_lot_pdf_report(
    lot: Lot,
    grade_result: GradeResult,
    detections: List[OnionDetection],
    report: Report,
    audit_logs: Optional[List[AuditLog]] = None,
    output_pdf_path: Optional[Path] = None,
) -> Path:
    """
    Build and save the official tamper-evident inspection report PDF.

    Parameters mirror the old signature exactly so callers (reports.py) need
    no changes.
    """
    storage_dir = Path(settings.STORAGE_DIR) / "reports"
    storage_dir.mkdir(parents=True, exist_ok=True)

    if output_pdf_path is None:
        fname = f"report_lot_{lot.id}_v{report.version}_{report.report_hash[:8]}.pdf"
        output_pdf_path = storage_dir / fname

    base_font = _register_fonts()
    bold_font = "NotoSans-Bold" if base_font == "NotoSans" else "Helvetica-Bold"
    mono_font = "Courier"

    # ── Annotated image ────────────────────────────────────────────────────
    annotated_img_path: Optional[Path] = None
    if lot.images:
        primary = lot.images[0]
        raw_path = Path(primary.storage_key)
        if raw_path.exists():
            out_ann = storage_dir / f"annotated_lot_{lot.id}_v{report.version}.jpg"
            annotated_img_path = draw_annotated_lot_image(
                image_path=raw_path,
                detections=detections,
                output_path=out_ann,
            )

    # ── QR code ────────────────────────────────────────────────────────────
    verify_url = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/verify/{report.id}/view"
    qr_path = storage_dir / f"qr_report_{report.id}.png"
    _make_qr(verify_url, qr_path)

    # ── Document ───────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        str(output_pdf_path),
        pagesize=A4,
        leftMargin=36, rightMargin=36,
        topMargin=44, bottomMargin=44,
    )

    # Style helpers
    def _p(name: str, **kw) -> ParagraphStyle:
        base = getSampleStyleSheet()["Normal"]
        # Don't inherit fontName from base; always pass it explicitly
        return ParagraphStyle(name, parent=base, **kw)

    title_s = _p("Title", fontName=bold_font, fontSize=17, leading=21,
                 textColor=colors.HexColor("#1A365D"))
    sub_s = _p("Sub", fontName=base_font, fontSize=8.5, leading=11, textColor=colors.HexColor("#4A5568"))
    sec_s = _p("Section", fontName=bold_font, fontSize=11, leading=15,
                textColor=colors.HexColor("#276749"), spaceBefore=8, spaceAfter=3)
    body_s = _p("Body", fontName=base_font, fontSize=9, leading=12, textColor=colors.HexColor("#2D3748"))
    small_s = _p("Small", fontName=mono_font, fontSize=7, leading=9,
                  textColor=colors.HexColor("#4A5568"))
    label_s = _p("Label", fontName=bold_font, fontSize=8,
                  textColor=colors.HexColor("#4A5568"))


    story = []

    # ── 1. Header ──────────────────────────────────────────────────────────
    batch_code = getattr(lot, "batch_code", None) or getattr(lot, "lot_number", None) or f"LOT-{lot.id}"
    farmer_name = (lot.farmer.name if lot.farmer else None) or lot.farmer_name or "Farmer"
    centre_name = (lot.centre.name if lot.centre else None) or f"Centre #{lot.centre_id}"
    lot_weight = f"{float(lot.weight_kg):.2f} kg" if lot.weight_kg else "N/A"
    batch_date = (lot.batch_date or lot.created_at or datetime.utcnow()).strftime("%d %b %Y, %H:%M UTC")

    hdr_data = [
        [
            Paragraph(f"<b>Kisan Setu</b> Quality Inspection Certificate", title_s),
            Paragraph(
                f"<b>Report ID:</b> #{report.id} &nbsp; <b>v{report.version}</b><br/>"
                f"<b>Generated:</b> {report.generated_at.strftime('%Y-%m-%d %H:%M UTC') if report.generated_at else 'N/A'}",
                sub_s,
            ),
        ],
    ]
    hdr_table = Table(hdr_data, colWidths=[370, 150])
    hdr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 5))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=8))

    # ── 2. Batch metadata ──────────────────────────────────────────────────
    meta_rows = [
        [
            Paragraph(f"<b>Batch Code:</b>  {batch_code}", body_s),
            Paragraph(f"<b>Farmer:</b>  {farmer_name}", body_s),
        ],
        [
            Paragraph(f"<b>Centre:</b>  {centre_name}", body_s),
            Paragraph(f"<b>Date & Time:</b>  {batch_date}", body_s),
        ],
        [
            Paragraph(f"<b>Weight:</b>  {lot_weight}", body_s),
            Paragraph(f"<b>Rule Version:</b>  {report.rule_version}", body_s),
        ],
        [
            Paragraph(f"<b>Status:</b>  {lot.status.value.upper()}", body_s),
            Paragraph(f"<b>Crop:</b>  {getattr(lot, 'crop', 'onion').capitalize()}", body_s),
        ],
    ]
    meta_tbl = Table(meta_rows, colWidths=[260, 260])
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    # ── 3. Three-Bucket Grade Summary ─────────────────────────────────────
    story.append(Paragraph("Three-Bucket Grading Summary", sec_s))

    defective_pct = float(getattr(grade_result, "defective_pct", 0.0) or 0.0)
    urs_pct = float(getattr(grade_result, "urs_pct", 0.0) or 0.0)
    grade_a_pct = float(getattr(grade_result, "grade_a_pct", 0.0) or 0.0)
    total_count = int(getattr(grade_result, "total_count", 0) or 0)

    # Grade counts from raw_counts if available
    raw_counts: dict = grade_result.raw_counts or {}
    grade_a_count = raw_counts.get("grade_a", 0)
    urs_count = raw_counts.get("urs", 0)
    defective_count = raw_counts.get("defective", 0)

    def _bucket_cell(pct: float, count: int, label: str, bg: str, fg: str, sub_fg: str) -> Paragraph:
        return Paragraph(
            f"<font size=16 color='{fg}'><b>{pct:.1f}%</b></font><br/>"
            f"<font size=8 color='{fg}'>{count} onions</font><br/>"
            f"<font size=7.5 color='{sub_fg}'><b>{label}</b></font>",
            ParagraphStyle("bc", alignment=1, leading=14),
        )

    bucket_data = [[
        _bucket_cell(grade_a_pct, grade_a_count, "GRADE A (PREMIUM)", "#F0FFF4", "#22543D", "#276749"),
        _bucket_cell(urs_pct, urs_count, "URS (UNDERSIZED)", "#FEFCBF", "#B7791F", "#975A16"),
        _bucket_cell(defective_pct, defective_count, "DEFECTIVE", "#FFF5F5", "#742A2A", "#9B2C2C"),
        _bucket_cell(100.0, total_count, "TOTAL ONIONS", "#EDF2F7", "#2D3748", "#4A5568"),
    ]]
    bucket_tbl = Table(bucket_data, colWidths=[130, 130, 130, 130])
    bucket_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F0FFF4")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#FEFCBF")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FFF5F5")),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#EDF2F7")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E0")),
        ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(bucket_tbl)

    # Lot grade label banner
    lot_grade_label = getattr(grade_result, "lot_grade_label", None) or "N/A"
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"<b>Lot Grade:</b> &nbsp;<font color='#276749'>{lot_grade_label}</font>",
        ParagraphStyle("LotGrade", parent=body_s, fontSize=10, leading=14,
                       fontName=bold_font),
    ))
    story.append(Spacer(1, 10))

    # ── 4. Annotated Image ─────────────────────────────────────────────────
    if annotated_img_path and annotated_img_path.exists():
        story.append(Paragraph("Annotated AI Inspection Capture", sec_s))
        img_fl = RLImage(str(annotated_img_path), width=520, height=200)
        img_fl.hAlign = "CENTER"
        story.append(img_fl)
        story.append(Spacer(1, 10))

    # ── 5. Defect Breakdown Table ──────────────────────────────────────────
    story.append(Paragraph("Quality Metrics & Defect Breakdown", sec_s))

    breakdown: dict = grade_result.defect_breakdown or {}
    det_rows = [
        [
            Paragraph("<b>Category</b>", body_s),
            Paragraph("<b>Count</b>", body_s),
            Paragraph("<b>%</b>", body_s),
            Paragraph("<b>Bucket</b>", body_s),
        ]
    ]
    for cls_name in ["good", "damaged", "rotten", "sprouted", "undersized"]:
        info = breakdown.get(cls_name, {"count": 0, "pct": 0.0})
        if cls_name == "good":
            bucket_lbl, col = "Grade A / URS", "#276749"
        elif cls_name == "undersized":
            bucket_lbl, col = "URS", "#B7791F"
        else:
            bucket_lbl, col = "Defective", "#9B2C2C"
        det_rows.append([
            Paragraph(cls_name.capitalize(), body_s),
            Paragraph(str(info.get("count", 0)), body_s),
            Paragraph(f"{float(info.get('pct', 0.0)):.1f}%", body_s),
            Paragraph(f"<font color='{col}'><b>{bucket_lbl}</b></font>", body_s),
        ])
    det_tbl = Table(det_rows, colWidths=[150, 70, 90, 210])
    det_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(det_tbl)
    story.append(Spacer(1, 10))

    # ── 6. Verification Block (always present) ─────────────────────────────
    story.append(Paragraph("Verification Details", sec_s))

    ai_grade = (lot.ai_result or {}).get("lot_grade", "N/A")
    final_grade = (lot.final_result or {}).get("lot_grade", "N/A")

    ver_rows = [
        [
            Paragraph(f"<b>AI Result:</b>  {ai_grade}", body_s),
            Paragraph(f"<b>Final Result:</b>  {final_grade}", body_s),
        ]
    ]

    if lot.verifications:
        latest_ver = sorted(lot.verifications, key=lambda v: v.created_at)[-1]
        verifier_name = (
            latest_ver.verifier.name if hasattr(latest_ver, "verifier") and latest_ver.verifier
            else f"Staff #{latest_ver.verifier_id}"
        )
        verified_at = latest_ver.created_at.strftime("%d %b %Y, %H:%M UTC") if latest_ver.created_at else "N/A"
        decision_lbl = latest_ver.decision.value.upper() if hasattr(latest_ver.decision, "value") else str(latest_ver.decision).upper()

        ver_rows.append([
            Paragraph(f"<b>Verified By:</b>  {verifier_name}", body_s),
            Paragraph(f"<b>Verified At:</b>  {verified_at}", body_s),
        ])
        ver_rows.append([
            Paragraph(f"<b>Decision:</b>  {decision_lbl}", body_s),
            Paragraph(f"<b>Override Reason:</b>  {latest_ver.reason or 'N/A'}", body_s),
        ])
    else:
        ver_rows.append([
            Paragraph("<i>Pending staff verification</i>", body_s),
            Paragraph("", body_s),
        ])

    ver_bg = colors.HexColor("#FFF5F5") if lot.verifications and any(
        (v.decision.value if hasattr(v.decision, "value") else str(v.decision)) == "overridden"
        for v in lot.verifications
    ) else colors.HexColor("#F7FAFC")

    ver_tbl = Table(ver_rows, colWidths=[260, 260])
    ver_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ver_bg),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(ver_tbl)
    story.append(Spacer(1, 10))

    # ── 7. QR + Tamper-Evident Section ────────────────────────────────────
    story.append(KeepTogether([
        Paragraph("Digital Authenticity & Scan to Verify", sec_s),
        Table(
            [[
                RLImage(str(qr_path), width=75, height=75),
                [
                    Paragraph("<b>Scan QR code to verify this report online:</b>", body_s),
                    Paragraph(
                        f"<font color='#2B6CB0'><u>{verify_url}</u></font>",
                        small_s,
                    ),
                    Spacer(1, 4),
                    Paragraph("<b>SHA-256 Canonical Report Hash:</b>", body_s),
                    Paragraph(report.report_hash, small_s),
                ],
            ]],
            colWidths=[85, 435],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF8FF")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#90CDF4")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]),
        )
    ]))

    # ── Build PDF ──────────────────────────────────────────────────────────
    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: _ReportCanvas(
            *args, is_mock=report.is_mock, **kwargs
        ),
    )

    return output_pdf_path
