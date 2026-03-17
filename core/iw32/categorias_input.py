from __future__ import annotations

import re
import unicodedata


TIPO_CATEGORIA_MAP = {
    "Preventiva": "SERVICO DE MANUTENCAO-CONTRATO",
    "Corretiva": "SERVICO DE MANUTENCAO",
}

_TIPO_CATEGORIA_LOOKUP = {key.casefold(): value for key, value in TIPO_CATEGORIA_MAP.items()}
_DECIMAL_INTEGER_RE = re.compile(r"^\d{1,3}(?:\.\d{3})*$|^\d+$")
_DECIMAL_FRACTION_RE = re.compile(r"^\d{1,2}$")
_NUMERIC_RE = re.compile(r"^\d+$")
_VALUE_RE = re.compile(r"^-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?$")
_MARKDOWN_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")


def tipo_para_categoria(tipo: str) -> str:
    text = str(tipo or "").strip()
    if not text:
        return ""
    return _TIPO_CATEGORIA_LOOKUP.get(text.casefold(), text.upper())


def parse_group_orders(raw_text: str) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    rows: list[dict[str, str]] = []
    errors: list[dict[str, object]] = []
    for line_number, raw_line in enumerate(str(raw_text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        ordem, nome = _split_group_line(line)
        if not _NUMERIC_RE.fullmatch(ordem):
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Ordem deve conter apenas numeros.",
                }
            )
            continue
        rows.append({"ordem": ordem, "nome": nome})
    return rows, errors


def parse_manual_rows(
    raw_text: str,
    *,
    default_tipo: str,
    default_numero_servico: str,
    allowed_categories: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, object]]]:
    rows: list[dict[str, str]] = []
    errors: list[dict[str, object]] = []
    fallback_tipo = str(default_tipo or "").strip()
    fallback_service = str(default_numero_servico or "").strip()

    for line_number, raw_line in enumerate(str(raw_text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = _split_manual_columns(line)
        if not parts or _is_ignorable_manual_row(parts):
            continue
        if len(parts) < 2:
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Informe ao menos ordem e valor.",
                }
            )
            continue
        if len(parts) > 5:
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Linha com colunas demais. Use no maximo ordem, valor, tipo e numero de servico, com nome/local opcional.",
                }
            )
            continue

        ordem = parts[0]
        nome = ""
        tipo = fallback_tipo
        numero_servico = fallback_service
        has_name = len(parts) >= 3 and not _looks_like_value(parts[1])
        value_index = 1

        if has_name:
            nome = parts[1]
            value_index = 2

        if len(parts) <= value_index:
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Informe ao menos ordem e valor.",
                }
            )
            continue

        valor = parts[value_index]
        extras = parts[value_index + 1 :]

        if len(extras) > 2:
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Linha com colunas demais. Use no maximo ordem, valor, tipo e numero de servico, com nome/local opcional.",
                }
            )
            continue

        if len(extras) == 1:
            extra = extras[0]
            if _looks_like_service_number(extra):
                numero_servico = extra
            else:
                tipo = extra
        elif len(extras) == 2:
            tipo = extras[0] or fallback_tipo
            numero_servico = extras[1] or fallback_service

        if not _NUMERIC_RE.fullmatch(ordem):
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Ordem deve conter apenas numeros.",
                }
            )
            continue
        if not valor:
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Valor obrigatorio para colagem linha a linha.",
                }
            )
            continue
        if not _looks_like_value(valor):
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": "Valor invalido. Use apenas numeros, com ou sem R$.",
                }
            )
            continue

        categoria = tipo_para_categoria(tipo)
        if allowed_categories is not None and categoria not in allowed_categories:
            errors.append(
                {
                    "line_number": line_number,
                    "raw": raw_line,
                    "message": f"Categoria nao configurada no layout: {categoria}.",
                }
            )
            continue

        rows.append(
            {
                "ordem": ordem,
                "nome": nome,
                "categoria": categoria,
                "valor": _normalize_value(valor),
                "numero_servico": numero_servico,
            }
        )

    return rows, errors


def _split_group_line(line: str) -> tuple[str, str]:
    if "\t" in line:
        ordem, rest = line.split("\t", 1)
    elif ";" in line:
        ordem, rest = line.split(";", 1)
    elif "," in line:
        ordem, rest = line.split(",", 1)
    else:
        return _clean_cell(line), ""
    return _clean_cell(ordem), _clean_cell(rest)


def _split_manual_columns(line: str) -> list[str]:
    if "|" in line:
        parts = [_clean_cell(part) for part in line.split("|")]
        while parts and not parts[0]:
            parts = parts[1:]
        while parts and not parts[-1]:
            parts = parts[:-1]
        return parts
    if "\t" in line:
        parts = line.split("\t")
    elif ";" in line:
        parts = line.split(";")
    else:
        parts = line.split(",")
        if len(parts) >= 4 and _looks_like_decimal_parts(parts[2], parts[3]):
            parts = parts[:2] + [f"{parts[2]},{parts[3]}"] + parts[4:]
        elif len(parts) == 1:
            parts = _split_whitespace_columns(line)
    return [_clean_cell(part) for part in parts]


def _looks_like_decimal_parts(integer_part: str, fraction_part: str) -> bool:
    left = _clean_cell(integer_part)
    right = _clean_cell(fraction_part)
    return bool(_DECIMAL_INTEGER_RE.fullmatch(left) and _DECIMAL_FRACTION_RE.fullmatch(right))


def _looks_like_service_number(value: str) -> bool:
    return bool(_NUMERIC_RE.fullmatch(_clean_cell(value)))


def _looks_like_value(value: str) -> bool:
    return bool(_VALUE_RE.fullmatch(_normalize_value(value)))


def _normalize_value(value: str) -> str:
    text = _clean_cell(value).replace("\xa0", " ")
    text = re.sub(r"^\s*R\$\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", "", text)


def _split_whitespace_columns(line: str) -> list[str]:
    if re.search(r"\s{2,}", line):
        return re.split(r"\s{2,}", line.strip())
    parts = line.strip().split(maxsplit=1)
    if len(parts) == 2 and _NUMERIC_RE.fullmatch(parts[0]):
        return parts
    return parts


def _is_ignorable_manual_row(parts: list[str]) -> bool:
    if not parts:
        return True
    non_empty = [part for part in parts if part]
    if not non_empty:
        return True
    if all(_MARKDOWN_SEPARATOR_RE.fullmatch(part.replace(" ", "")) for part in non_empty):
        return True
    header_tokens = {_header_token(part) for part in non_empty}
    return "ordem" in header_tokens and "valor" in header_tokens


def _header_token(value: str) -> str:
    text = unicodedata.normalize("NFKD", _clean_cell(value).casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def _clean_cell(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1].strip()
    return text
