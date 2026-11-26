import re
from importlib import import_module
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if __package__:
    from . import database
else:
    database = import_module("database")


def sao_paulo_now():
    try:
        zone = ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        zone = timezone(timedelta(hours=-3), name="America/Sao_Paulo")
    return datetime.now(zone).replace(microsecond=0)


def parse_weight(raw_value, prefix="", suffix=""):
    value = str(raw_value).strip()
    if prefix and value.startswith(prefix):
        value = value[len(prefix):]
    if suffix and value.endswith(suffix):
        value = value[:-len(suffix)]
    value = re.sub(r"\s*(?:KG|KGS)\s*$", "", value.strip(), flags=re.IGNORECASE)
    value = value.replace(" ", "")
    if not value:
        raise ValueError("INFORME O PESO DO BAG.")
    if not re.fullmatch(r"[+-]?[0-9.,]+", value):
        raise ValueError("PESO INVÁLIDO.")
    if "," in value and "." in value:
        decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        value = value.replace(thousands_separator, "")
        value = value.replace(decimal_separator, ".")
    elif "," in value:
        if value.count(",") > 1:
            raise ValueError("PESO INVÁLIDO.")
        value = value.replace(",", ".")
    elif value.count(".") > 1:
        raise ValueError("PESO INVÁLIDO.")
    try:
        weight = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("PESO INVÁLIDO.") from error
    if not weight.is_finite() or weight <= 0 or weight.as_tuple().exponent < -2:
        raise ValueError("PESO INVÁLIDO.")
    return weight.quantize(Decimal("0.01"))


def validate_date(value, label):
    value = str(value).strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise ValueError(f"{label}: use o formato AAAA-MM-DD.") from error


def register_bag(
    code,
    raw_weight,
    scanner_prefix="",
    scanner_suffix="",
    db_path=None,
    label_id="",
):
    label_id = str(label_id or "").strip().upper()
    if not label_id:
        raise ValueError("ID DA ETIQUETA OBRIGATÓRIO.")
    if database.label_id_is_registered(label_id, db_path):
        raise ValueError(f"ETIQUETA JÁ REGISTRADA. ID: {label_id}.")
    code = str(code).strip()
    if not code:
        raise ValueError("CÓDIGO DO MATERIAL OBRIGATÓRIO.")
    material = database.find_material(code, db_path)
    if material is None:
        raise ValueError("MATERIAL NÃO CADASTRADO.")
    if not material["active"]:
        raise ValueError("MATERIAL INATIVO. Solicite a ativação ao administrador.")
    weight = parse_weight(raw_weight, scanner_prefix, scanner_suffix)
    bag_id = database.insert_bag(
        material,
        weight,
        sao_paulo_now(),
        label_id,
        db_path,
    )
    return bag_id, material, weight
