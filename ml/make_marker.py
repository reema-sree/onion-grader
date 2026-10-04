#!/usr/bin/env python3
"""
make_marker.py — Generate a print-ready A4 PDF with an ArUco marker.

Usage
-----
    python ml/make_marker.py [--size-cm 5.0] [--output marker.pdf]

The PDF contains:
- ArUco DICT_4X4_50 marker (ID 0) rendered at EXACT physical size
- A 5 cm ruler line for print-size verification
- Printed instructions: "Print at 100% scale, do not fit to page"

Requires: opencv-python, reportlab
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import cv2
import numpy as np

# ── ReportLab ──────────────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
except ImportError:
    sys.exit("ReportLab is required: pip install reportlab")

# ArUco constants (must match aruco_marker.py)
ARUCO_DICT_ID = cv2.aruco.DICT_4X4_50
ARUCO_MARKER_ID = 0

PAGE_W, PAGE_H = A4  # 595 × 842 pts


def _generate_aruco_png(marker_size_px: int = 400) -> bytes:
    """Render the ArUco marker to PNG bytes at the given pixel size."""
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT_ID)
    marker_img = np.zeros((marker_size_px, marker_size_px), dtype=np.uint8)
    cv2.aruco.generateImageMarker(dictionary, ARUCO_MARKER_ID, marker_size_px, marker_img, 1)
    # Add a white border (quiet zone = 1 cell ≈ 10% of size)
    border = marker_size_px // 10
    bordered = cv2.copyMakeBorder(
        marker_img, border, border, border, border,
        cv2.BORDER_CONSTANT, value=255,
    )
    ok, buf = cv2.imencode(".png", bordered)
    if not ok:
        raise RuntimeError("Failed to encode ArUco marker to PNG")
    return bytes(buf)


def generate_marker_pdf(
    size_cm: float = 5.0,
    output_path: Path = Path("aruco_marker.pdf"),
) -> Path:
    """
    Build the print-ready PDF.

    Parameters
    ----------
    size_cm : physical side-length of the marker square (default 5.0 cm)
    output_path : where to save the PDF
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert physical size to ReportLab points (1 cm = 28.346 pts)
    marker_pts = size_cm * cm  # desired printed size

    # ── Render marker PNG ──────────────────────────────────────────────────
    png_bytes = _generate_aruco_png(marker_size_px=800)
    img_reader = ImageReader(io.BytesIO(png_bytes))

    # ── PDF canvas ────────────────────────────────────────────────────────
    c = rl_canvas.Canvas(str(output_path), pagesize=A4)

    margin_x = (PAGE_W - marker_pts) / 2  # centre horizontally
    marker_y = PAGE_H - 5 * cm - marker_pts  # 5 cm from top

    # ── Header ────────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#1A365D"))
    c.drawCentredString(PAGE_W / 2, PAGE_H - 2 * cm, "Kisan Setu — ArUco Reference Marker")

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#4A5568"))
    c.drawCentredString(PAGE_W / 2, PAGE_H - 2.7 * cm,
                        f"DICT_4X4_50  ·  Marker ID {ARUCO_MARKER_ID}  ·  Print side length: {size_cm:.1f} cm")

    # ── Critical instruction box ───────────────────────────────────────────
    box_y = PAGE_H - 3.8 * cm
    c.setStrokeColor(colors.HexColor("#C53030"))
    c.setFillColor(colors.HexColor("#FFF5F5"))
    c.roundRect(margin_x - 5, box_y - 20, marker_pts + 10, 26, 4, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#C53030"))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(PAGE_W / 2, box_y - 13,
                        "⚠  Print at 100% scale — do NOT fit to page or scale to fit  ⚠")

    # ── ArUco marker image ─────────────────────────────────────────────────
    c.drawImage(img_reader, margin_x, marker_y, width=marker_pts, height=marker_pts,
                preserveAspectRatio=True, mask="auto")

    # Draw thin registration border around marker
    c.setStrokeColor(colors.HexColor("#2D3748"))
    c.setLineWidth(0.5)
    c.rect(margin_x, marker_y, marker_pts, marker_pts)

    # ── 5 cm Ruler verification line ──────────────────────────────────────
    ruler_y = marker_y - 2.0 * cm
    ruler_x = margin_x
    ruler_len = 5.0 * cm  # always 5 cm, user can check

    c.setStrokeColor(colors.HexColor("#2B6CB0"))
    c.setLineWidth(1.5)
    # Main ruler line
    c.line(ruler_x, ruler_y, ruler_x + ruler_len, ruler_y)
    # End ticks
    tick_h = 4
    c.line(ruler_x, ruler_y - tick_h, ruler_x, ruler_y + tick_h)
    c.line(ruler_x + ruler_len, ruler_y - tick_h, ruler_x + ruler_len, ruler_y + tick_h)
    # Mid tick
    c.setLineWidth(0.5)
    mid = ruler_x + ruler_len / 2
    c.line(mid, ruler_y - tick_h / 2, mid, ruler_y + tick_h / 2)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#2B6CB0"))
    c.drawCentredString(ruler_x + ruler_len / 2, ruler_y - 1.0 * cm,
                        "← 5.0 cm verification ruler →")
    c.setFillColor(colors.HexColor("#4A5568"))
    c.setFont("Helvetica", 7)
    c.drawCentredString(ruler_x + ruler_len / 2, ruler_y - 1.4 * cm,
                        "If this ruler measures exactly 5 cm, your print scale is correct.")

    # ── Footer instructions ────────────────────────────────────────────────
    footer_y = ruler_y - 2.6 * cm
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#2D3748"))
    c.drawCentredString(PAGE_W / 2, footer_y, "How to use this marker:")
    instructions = [
        f"1. Print this page at 100% scale on plain white A4 paper (no scaling).",
        f"2. Measure the 5 cm ruler above to confirm the printed size.",
        f"3. Laminate or place inside a clear sleeve for durability (optional).",
        f"4. Place the marker flat next to the onions before taking a photo.",
        f"5. Ensure the full marker is visible and not obstructed in the frame.",
    ]
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#4A5568"))
    for i, line in enumerate(instructions):
        c.drawCentredString(PAGE_W / 2, footer_y - (i + 1) * 13, line)

    # ── Technical footer ──────────────────────────────────────────────────
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#A0AEC0"))
    c.drawCentredString(
        PAGE_W / 2, 1.2 * cm,
        f"Kisan Setu Inspection System  ·  ArUco DICT_4X4_50 ID {ARUCO_MARKER_ID}  ·  Physical size: {size_cm:.1f} cm",
    )

    c.save()
    return output_path


# ── CLI entry point ────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a print-ready ArUco reference marker PDF for Kisan Setu onion grading."
    )
    parser.add_argument(
        "--size-cm", type=float, default=5.0,
        help="Physical side length of the marker in cm (default: 5.0 cm)"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("aruco_marker.pdf"),
        help="Output PDF file path (default: aruco_marker.pdf)"
    )
    args = parser.parse_args()

    print(f"Generating ArUco marker PDF …  size={args.size_cm} cm  →  {args.output}")
    out = generate_marker_pdf(size_cm=args.size_cm, output_path=args.output)
    print(f"✓ Saved: {out.resolve()}")
    print("IMPORTANT: Print at 100% scale — do NOT fit to page.")


if __name__ == "__main__":
    main()
