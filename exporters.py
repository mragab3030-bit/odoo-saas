import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT, TA_CENTER

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


BRAND_BLUE = colors.HexColor('#2563eb')
BRAND_DARK = colors.HexColor('#1e293b')
LIGHT_GREY = colors.HexColor('#f8fafc')
MID_GREY = colors.HexColor('#e2e8f0')


def export_pdf(title: str, headers: list, rows: list, subtitle: str = '') -> io.BytesIO:
    buf = io.BytesIO()
    page_size = landscape(A4) if len(headers) > 6 else A4
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        fontSize=16, textColor=BRAND_DARK, spaceAfter=4
    )
    sub_style = ParagraphStyle(
        'Sub', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#64748b'), spaceAfter=12
    )

    elements = [
        Paragraph(title, title_style),
        Paragraph(
            subtitle or f'Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")} | {len(rows)} records',
            sub_style
        ),
        Spacer(1, 0.3 * cm),
    ]

    table_data = [headers] + [[str(cell) if cell is not None else '' for cell in row] for row in rows]

    col_count = len(headers)
    available_width = (landscape(A4)[0] if len(headers) > 6 else A4[0]) - 3 * cm
    col_width = available_width / col_count

    table = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
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
