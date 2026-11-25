"""Regenerate the reportlab-generated Chinese PDF fixture for the extraction arm.

The PDF is committed so CI and `pytest` do not need reportlab at test time; this
script records how it was produced.

    pip install reportlab
    cd backend && python scripts/gen_resume_pdf_fixture.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

BACKEND = Path(__file__).resolve().parents[1]
SOURCE = BACKEND / "tests/eval/resume_files/sample_resume_zh.txt"
TARGET = BACKEND / "tests/eval/resume_files/sample_resume_zh_reportlab.pdf"


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdf = canvas.Canvas(str(TARGET), pagesize=A4)
    pdf.setTitle("Sample Resume (reportlab STSong-Light fixture)")
    pdf.setFont("STSong-Light", 11)
    y = A4[1] - 20 * mm
    for line in lines:
        pdf.drawString(20 * mm, y, line)
        y -= 6 * mm
    pdf.save()
    print(f"written {TARGET} ({TARGET.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
