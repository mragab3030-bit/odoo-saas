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


REV_GREEN  = colors.HexColor('#16a34a')
EXP_RED    = colors.HexColor('#dc2626')
NET_BLUE   = colors.HexColor('#2563eb')
NET_RED    = colors.HexColor('#dc2626')
SUBTOTAL_BG = colors.HexColor('#f1f5f9')


def _fmt_amount(value, currency=''):
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    s = '{:,.2f}'.format(n)
    return ('%s %s' % (currency, s)).strip()


def export_pnl_pdf(company_name: str, cost_center_name: str,
                   period_label: str, currency: str,
                   pnl: dict) -> io.BytesIO:
    """Render a one-page Cost Center P&L Statement.

    pnl shape:
      revenue_lines / expense_lines: [{'name', 'code', 'amount'}, ...]
      total_revenue / total_expenses / net: float
      margin_display: str (e.g. '23.5%' or '—')
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontName=UNICODE_FONT_BOLD, fontSize=18,
        textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        'Sub', parent=styles['Normal'],
        fontName=UNICODE_FONT, fontSize=10,
        textColor=colors.HexColor('#64748b'),
        alignment=TA_CENTER, spaceAfter=14,
    )
    section_label = ParagraphStyle(
        'SectionLabel', parent=styles['Normal'],
        fontName=UNICODE_FONT_BOLD, fontSize=11,
        textColor=BRAND_DARK, spaceAfter=4,
    )

    def cell(text, bold=False, align='left', color=BRAND_DARK):
        style = ParagraphStyle(
            'C', parent=styles['Normal'],
            fontName=UNICODE_FONT_BOLD if bold else UNICODE_FONT,
            fontSize=10, textColor=color, leading=13,
            alignment={'left': TA_LEFT, 'right': TA_RIGHT,
                       'center': TA_CENTER}[align],
        )
        text = '' if text is None else str(text)
        if _has_arabic(text):
            text = _shape_arabic(text)
        return Paragraph(_esc(text), style)

    elements = [
        Paragraph('COST CENTER P&amp;L STATEMENT', title_style),
    ]
    meta_parts = []
    if company_name:
        meta_parts.append(company_name)
    if cost_center_name:
        meta_parts.append('Cost Center: %s' % cost_center_name)
    if period_label:
        meta_parts.append('Period: %s' % period_label)
    meta_parts.append('Generated %s' %
                      datetime.now().strftime('%Y-%m-%d %H:%M'))
    elements.append(Paragraph('  |  '.join(meta_parts), sub_style))

    # Two-column table: account name (60%) / amount (40%)
    page_width = A4[0]
    available_width = page_width - 3.0 * cm
    col_widths = [available_width * 0.66, available_width * 0.34]

    def section_block(label, color, lines, total, total_label):
        table_data = [[
            cell(label, bold=True, color=color),
            cell('', align='right'),
        ]]
        for ln in lines:
            label_text = ln.get('name') or 'Unassigned'
            code = ln.get('code')
            if code:
                label_text = '[%s] %s' % (code, label_text)
            table_data.append([
                cell('   ' + label_text),
                cell(_fmt_amount(ln.get('amount', 0), currency),
                     align='right'),
            ])
        if not lines:
            table_data.append([
                cell('   (no lines)', color=colors.HexColor('#94a3b8')),
                cell('—', align='right',
                     color=colors.HexColor('#94a3b8')),
            ])
        table_data.append([
            cell(total_label, bold=True),
            cell(_fmt_amount(total, currency), bold=True, align='right',
                 color=color),
        ])
        t = Table(table_data, colWidths=col_widths, hAlign='LEFT')
        styles_list = [
            ('FONTNAME', (0, 0), (-1, -1), UNICODE_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            # Header row tint
            ('BACKGROUND', (0, 0), (-1, 0), SUBTOTAL_BG),
            ('LINEBELOW', (0, 0), (-1, 0), 0.7, color),
            # Subtotal row
            ('BACKGROUND', (0, -1), (-1, -1), SUBTOTAL_BG),
            ('LINEABOVE', (0, -1), (-1, -1), 0.7, color),
            ('LINEBELOW', (0, -1), (-1, -1), 0.7, color),
        ]
        t.setStyle(TableStyle(styles_list))
        return t

    elements.append(section_block(
        'REVENUE', REV_GREEN, pnl.get('revenue_lines') or [],
        pnl.get('total_revenue') or 0, 'Total Revenue'))
    elements.append(Spacer(1, 0.4 * cm))
    elements.append(section_block(
        'EXPENSES', EXP_RED, pnl.get('expense_lines') or [],
        pnl.get('total_expenses') or 0, 'Total Expenses'))
    elements.append(Spacer(1, 0.6 * cm))

    net_value  = pnl.get('net') or 0
    net_color  = NET_BLUE if net_value >= 0 else NET_RED
    net_label  = 'NET PROFIT' if net_value >= 0 else 'NET LOSS'
    summary_data = [
        [cell(net_label, bold=True, color=net_color),
         cell(_fmt_amount(net_value, currency), bold=True, align='right',
              color=net_color)],
        [cell('Margin %', bold=True),
         cell(pnl.get('margin_display') or '—', bold=True, align='right',
              color=net_color)],
    ]
    summary = Table(summary_data, colWidths=col_widths)
    summary.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), UNICODE_FONT_BOLD),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('FONTSIZE', (0, 1), (-1, 1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 0), (-1, -1), SUBTOTAL_BG),
        ('LINEABOVE', (0, 0), (-1, 0), 1.2, net_color),
        ('LINEBELOW', (0, -1), (-1, -1), 1.2, net_color),
    ]))
    elements.append(summary)

    doc.build(elements)
    buf.seek(0)
    return buf


def export_pnl_excel(company_name: str, cost_center_name: str,
                     period_label: str, currency: str,
                     pnl: dict) -> io.BytesIO:
    """Render a Cost Center P&L Statement as a single-sheet workbook."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Cost Center P&L'[:31]

    money_fmt = '#,##0.00'
    pct_fmt   = '0.0"%"'

    bold = Font(bold=True, size=11)
    title_font = Font(bold=True, size=14, color='1E293B')
    meta_font  = Font(color='64748B', size=9, italic=True)
    rev_font   = Font(bold=True, color='16A34A', size=11)
    exp_font   = Font(bold=True, color='DC2626', size=11)
    net_font_pos = Font(bold=True, color='2563EB', size=12)
    net_font_neg = Font(bold=True, color='DC2626', size=12)

    header_fill = PatternFill(start_color='F1F5F9', end_color='F1F5F9',
                              fill_type='solid')
    thin = Side(style='thin', color='E2E8F0')
    box  = Border(top=thin, bottom=thin, left=thin, right=thin)

    # Title + meta
    ws.merge_cells('A1:B1')
    cell = ws['A1']
    cell.value = 'COST CENTER P&L STATEMENT'
    cell.font = title_font
    cell.alignment = Alignment(horizontal='center')
    ws.row_dimensions[1].height = 26

    meta_lines = []
    if company_name:        meta_lines.append('Company: ' + company_name)
    if cost_center_name:    meta_lines.append('Cost Center: ' + cost_center_name)
    if period_label:        meta_lines.append('Period: ' + period_label)
    meta_lines.append('Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M'))
    row = 2
    for line in meta_lines:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        c = ws.cell(row=row, column=1, value=line)
        c.font = meta_font
        c.alignment = Alignment(horizontal='center')
        row += 1
    row += 1  # blank spacer

    def write_section(label, lines, total_label, total, header_font, color):
        nonlocal row
        # Section header row
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        c = ws.cell(row=row, column=1, value=label)
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal='left', indent=0)
        c.border = box
        row += 1
        if not lines:
            ws.cell(row=row, column=1, value='   (no lines)').font = Font(
                color='94A3B8', italic=True)
            ws.cell(row=row, column=2, value=None)
            row += 1
        for ln in lines:
            label_text = ln.get('name') or 'Unassigned'
            code = ln.get('code')
            if code:
                label_text = '[%s] %s' % (code, label_text)
            ws.cell(row=row, column=1, value='   ' + label_text)
            amt_cell = ws.cell(row=row, column=2, value=ln.get('amount') or 0)
            amt_cell.number_format = money_fmt
            amt_cell.alignment = Alignment(horizontal='right')
            row += 1
        # Subtotal
        total_cell_label = ws.cell(row=row, column=1, value=total_label)
        total_cell_label.font = bold
        total_cell_label.fill = header_fill
        total_cell_label.border = box
        total_cell = ws.cell(row=row, column=2, value=total or 0)
        total_cell.font = Font(bold=True, color=color, size=11)
        total_cell.fill = header_fill
        total_cell.border = box
        total_cell.number_format = money_fmt
        total_cell.alignment = Alignment(horizontal='right')
        row += 2  # spacer

    write_section('REVENUE', pnl.get('revenue_lines') or [],
                  'Total Revenue', pnl.get('total_revenue') or 0,
                  rev_font, '16A34A')
    write_section('EXPENSES', pnl.get('expense_lines') or [],
                  'Total Expenses', pnl.get('total_expenses') or 0,
                  exp_font, 'DC2626')

    # Net + margin summary
    net_value = pnl.get('net') or 0
    net_color = '2563EB' if net_value >= 0 else 'DC2626'
    net_font  = net_font_pos if net_value >= 0 else net_font_neg
    net_label = 'NET PROFIT' if net_value >= 0 else 'NET LOSS'

    net_label_cell = ws.cell(row=row, column=1, value=net_label)
    net_label_cell.font = net_font
    net_label_cell.fill = header_fill
    net_label_cell.border = box
    net_amt_cell = ws.cell(row=row, column=2, value=net_value)
    net_amt_cell.font = net_font
    net_amt_cell.fill = header_fill
    net_amt_cell.border = box
    net_amt_cell.number_format = money_fmt
    net_amt_cell.alignment = Alignment(horizontal='right')
    row += 1

    margin_label_cell = ws.cell(row=row, column=1, value='Margin %')
    margin_label_cell.font = bold
    margin_label_cell.fill = header_fill
    margin_label_cell.border = box
    margin_value = pnl.get('margin_pct') or 0
    if (pnl.get('total_revenue') or 0) > 0:
        m = ws.cell(row=row, column=2, value=margin_value)
        m.number_format = pct_fmt
    else:
        m = ws.cell(row=row, column=2, value=pnl.get('margin_display') or '—')
    m.font = Font(bold=True, color=net_color, size=11)
    m.fill = header_fill
    m.border = box
    m.alignment = Alignment(horizontal='right')

    # Column widths
    ws.column_dimensions['A'].width = 60
    ws.column_dimensions['B'].width = 22

    if currency:
        # Tag the second column with the currency in row 4 hint
        pass  # money cells display the symbol via formatting elsewhere

    buf = io.BytesIO()
    wb.save(buf)
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
