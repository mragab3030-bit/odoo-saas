import io
import logging
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import arabic_reshaper
from bidi.algorithm import get_display

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


logger = logging.getLogger(__name__)

BRAND_BLUE = colors.HexColor('#2563eb')
BRAND_DARK = colors.HexColor('#1e293b')
LIGHT_GREY = colors.HexColor('#f8fafc')
MID_GREY = colors.HexColor('#e2e8f0')


# ---------------------------------------------------------------------------
# Unicode / Arabic font registration
# ---------------------------------------------------------------------------

_FONTS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'fonts')

# Latin / general font — used for non-Arabic cells and the body text.
_LATIN_CANDIDATES = [
    (os.path.join(_FONTS_DIR, 'DejaVuSans.ttf'),
     os.path.join(_FONTS_DIR, 'DejaVuSans-Bold.ttf')),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
     '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    ('/usr/share/fonts/dejavu/DejaVuSans.ttf',
     '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf'),
]

# Dedicated Arabic font — applied to cells that contain Arabic glyphs.
_ARABIC_CANDIDATES = [
    (os.path.join(_FONTS_DIR, 'Amiri-Regular.ttf'),
     os.path.join(_FONTS_DIR, 'Amiri-Bold.ttf')),
    ('/usr/share/fonts/truetype/amiri/Amiri-Regular.ttf',
     '/usr/share/fonts/truetype/amiri/Amiri-Bold.ttf'),
]

UNICODE_FONT = 'Helvetica'
UNICODE_FONT_BOLD = 'Helvetica-Bold'
ARABIC_FONT = UNICODE_FONT
ARABIC_FONT_BOLD = UNICODE_FONT_BOLD


def _register_pair(candidates, regular_name, bold_name, fallback):
    for regular, bold in candidates:
        if not os.path.exists(regular):
            continue
        try:
            pdfmetrics.registerFont(TTFont(regular_name, regular))
            reg = regular_name
            if os.path.exists(bold):
                pdfmetrics.registerFont(TTFont(bold_name, bold))
                bld = bold_name
            else:
                bld = reg
            logger.info("PDF font registered (%s): %s", regular_name, regular)
            return reg, bld
        except Exception as e:
            logger.warning("Failed to register font %s: %s", regular, e)
    logger.warning("No font found for %s — using %s.", regular_name, fallback)
    return fallback, fallback


def _register_fonts():
    global UNICODE_FONT, UNICODE_FONT_BOLD, ARABIC_FONT, ARABIC_FONT_BOLD
    UNICODE_FONT, UNICODE_FONT_BOLD = _register_pair(
        _LATIN_CANDIDATES, 'AppFont', 'AppFont-Bold', 'Helvetica')
    ARABIC_FONT, ARABIC_FONT_BOLD = _register_pair(
        _ARABIC_CANDIDATES, 'AppArabic', 'AppArabic-Bold', UNICODE_FONT)


_register_fonts()


def _has_arabic(text: str) -> bool:
    return any('؀' <= ch <= 'ۿ' or 'ݐ' <= ch <= 'ݿ'
               or 'ﭐ' <= ch <= '﷿' or 'ﹰ' <= ch <= '﻿'
               for ch in text)


def _shape_arabic(text: str) -> str:
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def export_pdf(title: str, headers: list, rows: list,
               subtitle: str = '', col_widths: list = None) -> io.BytesIO:
    buf = io.BytesIO()
    page_size = landscape(A4) if len(headers) > 6 else A4
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontName=UNICODE_FONT_BOLD, fontSize=16,
        textColor=BRAND_DARK, spaceAfter=4
    )
    sub_style = ParagraphStyle(
        'Sub', parent=styles['Normal'],
        fontName=UNICODE_FONT, fontSize=9,
        textColor=colors.HexColor('#64748b'), spaceAfter=12
    )
    cell_style_ltr = ParagraphStyle(
        'Cell', parent=styles['Normal'],
        fontName=UNICODE_FONT, fontSize=8,
        textColor=BRAND_DARK, alignment=TA_LEFT,
        leading=10,
    )
    cell_style_rtl = ParagraphStyle(
        'CellRTL', parent=cell_style_ltr,
        fontName=ARABIC_FONT, fontSize=10,
        alignment=TA_RIGHT, leading=13,
    )
    header_style = ParagraphStyle(
        'Header', parent=styles['Normal'],
        fontName=UNICODE_FONT_BOLD, fontSize=9,
        textColor=colors.white, alignment=TA_CENTER,
        leading=11,
    )

    def make_cell(value, header_cell=False):
        text = '' if value is None else str(value)
        if _has_arabic(text):
            text = _shape_arabic(text)
            return Paragraph(_esc(text), cell_style_rtl)
        return Paragraph(_esc(text), header_style if header_cell else cell_style_ltr)

    elements = [
        Paragraph(title, title_style),
        Paragraph(
            subtitle or f'Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")} | {len(rows)} records',
            sub_style
        ),
        Spacer(1, 0.3 * cm),
    ]

    table_data = (
        [[make_cell(h, header_cell=True) for h in headers]]
        + [[make_cell(c) for c in row] for row in rows]
    )

    col_count = len(headers)
    page_width = page_size[0]
    available_width = page_width - 2.4 * cm  # matches left+right margins above

    if col_widths and len(col_widths) == col_count:
        total = float(sum(col_widths)) or 1.0
        widths = [w / total * available_width for w in col_widths]
    else:
        widths = [available_width / col_count] * col_count

    table = Table(table_data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), UNICODE_FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ('FONTNAME', (0, 1), (-1, -1), UNICODE_FONT),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, MID_GREY),
        ('LINEBELOW', (0, 0), (-1, 0), 1, BRAND_BLUE),
    ]))

    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return buf


def export_excel(title: str, headers: list, rows: list) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31]

    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

    title_font = Font(bold=True, size=14, color='1E293B')
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.font = title_font
    title_cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 28

    meta_cell = ws.cell(
        row=2, column=1,
        value=f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}  |  {len(rows)} records'
    )
    meta_cell.font = Font(color='64748B', size=9, italic=True)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    ws.row_dimensions[2].height = 18

    header_row = 4
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = Border(
            bottom=Side(style='medium', color='1D4ED8')
        )
    ws.row_dimensions[header_row].height = 22

    alt_fill = PatternFill(start_color='F8FAFC', end_color='F8FAFC', fill_type='solid')
    border = Border(
        bottom=Side(style='thin', color='E2E8F0'),
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
    )

    for row_idx, row in enumerate(rows, header_row + 1):
        fill = alt_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.border = border
            cell.alignment = Alignment(vertical='center')
            if fill:
                cell.fill = fill
        ws.row_dimensions[row_idx].height = 18

    for col_idx in range(1, len(headers) + 1):
        max_len = max(
            (len(str(ws.cell(row=r, column=col_idx).value or ''))
             for r in range(header_row, header_row + len(rows) + 1)),
            default=8
        )
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_len + 4, 40)

    ws.freeze_panes = f'A{header_row + 1}'
    ws.auto_filter.ref = f'A{header_row}:{openpyxl.utils.get_column_letter(len(headers))}{header_row}'

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
