from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


NAVY = "0B1F3A"
WHITE = "FFFFFF"
LIGHT_BLUE = "EAF1F8"
TOTAL_FILL = "DDEBDD"
WEIGHT_FORMAT = '#,##0.00'


def build_workbook(records):
    workbook = Workbook()
    summary = workbook.active
    summary.title = "RESUMO DA PESAGEM"
    detail = workbook.create_sheet("REGISTRO DE BIPAGENS")
    headers = ("Código do material", "Descrição do material", "Categoria", "Quantidade de bags", "Peso total (KG)")
    summary.append(headers)

    grouped = defaultdict(lambda: {"bags": 0, "weight": Decimal("0")})
    for record in records:
        key = (
            record["material_code"],
            record["material_description"],
            record["category"],
        )
        grouped[key]["bags"] += 1
        grouped[key]["weight"] += Decimal(str(record["weight"]))

    for (code, description, category), totals in sorted(grouped.items()):
        summary.append(
            (code, description, category, totals["bags"], float(totals["weight"]))
        )

    total_row = summary.max_row + 1
    summary.cell(total_row, 1, "TOTAL GERAL")
    summary.cell(total_row, 4, len(records))
    summary.cell(
        total_row,
        5,
        float(sum((Decimal(str(record["weight"])) for record in records), Decimal("0"))),
    )
    summary.auto_filter.ref = f"A1:E{max(1, total_row - 1)}"
    summary.freeze_panes = "A2"

    detail_headers = (
        "Número do registro",
        "Código do material",
        "Descrição do material",
        "Categoria",
        "Peso (KG)",
        "Data do registro",
        "Hora do registro",
    )
    detail.append(detail_headers)
    for record in sorted(records, key=lambda item: (item["recorded_at"], item["id"])):
        detail.append(
            (
                record["id"],
                record["material_code"],
                record["material_description"],
                record["category"],
                float(Decimal(str(record["weight"]))),
                datetime.strptime(record["record_date"], "%Y-%m-%d").date(),
                datetime.strptime(record["record_time"], "%H:%M:%S").time(),
            )
        )
    detail.auto_filter.ref = f"A1:G{max(1, detail.max_row)}"
    detail.freeze_panes = "A2"

    for sheet in (summary, detail):
        sheet.sheet_view.showGridLines = False
        for cell in sheet[1]:
            cell.fill = PatternFill("solid", fgColor=NAVY)
            cell.font = Font(color=WHITE, bold=True)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        sheet.row_dimensions[1].height = 32
        for row in sheet.iter_rows(min_row=2):
            if row[0].row % 2 == 0:
                for cell in row:
                    cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)

    for cell in summary[total_row]:
        cell.fill = PatternFill("solid", fgColor=TOTAL_FILL)
        cell.font = Font(bold=True, color=NAVY)
    for row in range(2, total_row + 1):
        summary.cell(row, 5).number_format = WEIGHT_FORMAT
    for row in range(2, detail.max_row + 1):
        detail.cell(row, 5).number_format = WEIGHT_FORMAT
        detail.cell(row, 6).number_format = "dd/mm/yyyy"
        detail.cell(row, 7).number_format = "hh:mm:ss"

    widths = {
        "RESUMO DA PESAGEM": (20, 48, 18, 20, 22),
        "REGISTRO DE BIPAGENS": (20, 20, 48, 18, 16, 20, 18),
    }
    for sheet in (summary, detail):
        for column, width in enumerate(widths[sheet.title], start=1):
            sheet.column_dimensions[get_column_letter(column)].width = width
    return workbook


def export_workbook(records, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    build_workbook(records).save(destination)
    return destination


def report_filename(start_date=None, end_date=None):
    def format_date(value):
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")

    if start_date and end_date and start_date == end_date:
        return f"RELATORIO_INVENTARIO_{format_date(start_date)}.xlsx"
    if start_date and end_date:
        return (
            f"RELATORIO_INVENTARIO_{format_date(start_date)}"
            f"_A_{format_date(end_date)}.xlsx"
        )
    if start_date:
        return f"RELATORIO_INVENTARIO_A_PARTIR_DE_{format_date(start_date)}.xlsx"
    if end_date:
        return f"RELATORIO_INVENTARIO_ATE_{format_date(end_date)}.xlsx"
    return "RELATORIO_INVENTARIO_COMPLETO.xlsx"
