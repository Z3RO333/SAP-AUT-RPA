from __future__ import annotations

from decimal import Decimal

from core.common.excel_utils import as_decimal, as_text
from core.common.models import ValidationIssue

from .models import PurchaseOrderHeader, PurchaseOrderItem, PurchaseOrderPayload, PurchaseOrderServiceLine


HEADER_REQUIRED = (
    "doc_ref",
    "tipo_doc",
    "org_compras",
    "grupo_compras",
    "empresa",
    "fornecedor",
    "moeda",
    "condicao_pagamento",
)


def _has_row_error(errors: list[ValidationIssue], sheet: str, row_number: int) -> bool:
    return any(issue.sheet == sheet and issue.row_number == row_number for issue in errors)


def _sort_service_lines(lines: list[PurchaseOrderServiceLine]) -> list[PurchaseOrderServiceLine]:
    def _sort_key(line: PurchaseOrderServiceLine):
        if line.line_ref.isdigit():
            return (0, int(line.line_ref))
        return (1, line.line_ref)

    return sorted(lines, key=_sort_key)


def _profile_capabilities(profile: dict | None) -> dict:
    return profile.get("capabilities", {}) if isinstance(profile, dict) else {}


def _allowed_tax_codes(profile: dict | None) -> set[str]:
    if not isinstance(profile, dict):
        return set()
    constraints = profile.get("constraints", {})
    if isinstance(constraints, dict):
        values = constraints.get("allowedTaxCodes", [])
        if isinstance(values, list):
            return {str(value).strip().upper() for value in values if str(value).strip()}
    return set()


def _row_number_for_item(item_rows: list[dict], item_ref: str) -> int:
    for index, row in enumerate(item_rows, start=2):
        if as_text(row.get("item_ref")) == item_ref:
            return index
    return 2


def validate_payload(
    header_rows: list[dict],
    item_rows: list[dict],
    service_rows: list[dict],
    profile: dict | None = None,
) -> tuple[PurchaseOrderPayload | None, list[ValidationIssue], list[ValidationIssue]]:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    profile = profile or {}
    capabilities = _profile_capabilities(profile)
    requires_plant_or_center = bool(capabilities.get("requiresPlantOrCenter"))
    allowed_tax_codes = _allowed_tax_codes(profile)

    if not header_rows:
        errors.append(ValidationIssue(sheet="CABECALHO", row_number=1, column_name="", level="error", message="Aba CABECALHO sem dados."))
        return None, errors, warnings
    if len(header_rows) != 1:
        errors.append(
            ValidationIssue(
                sheet="CABECALHO",
                row_number=1,
                column_name="",
                level="error",
                message="Aba CABECALHO deve conter exatamente 1 linha util.",
            )
        )
        return None, errors, warnings
    if not item_rows:
        errors.append(ValidationIssue(sheet="ITENS", row_number=1, column_name="", level="error", message="Aba ITENS sem dados."))
    if not service_rows:
        errors.append(ValidationIssue(sheet="SERVICOS", row_number=1, column_name="", level="error", message="Aba SERVICOS sem dados."))
    if errors:
        return None, errors, warnings

    header_row = header_rows[0]
    for field_name in HEADER_REQUIRED:
        if not as_text(header_row.get(field_name)):
            errors.append(
                ValidationIssue(
                    sheet="CABECALHO",
                    row_number=2,
                    column_name=field_name,
                    level="error",
                    message="Campo obrigatorio ausente.",
                )
            )

    item_payloads: list[PurchaseOrderItem] = []
    item_index: dict[str, PurchaseOrderItem] = {}
    for row_number, row in enumerate(item_rows, start=2):
        item_ref = as_text(row.get("item_ref"))
        texto_livre = as_text(row.get("texto_livre"))
        categoria_item = as_text(row.get("categoria_item")).upper()
        categoria_classif = as_text(row.get("categoria_classif")).upper()
        grupo_mercadoria = as_text(row.get("grupo_mercadoria"))
        plant_or_center = as_text(row.get("plant_or_center")) or None
        tax_code = as_text(row.get("tax_code")).upper() or None
        observacao_item = as_text(row.get("observacao_item")) or None
        conta_razao_default = as_text(row.get("conta_razao_default")) or None

        if not item_ref:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="item_ref", level="error", message="Item_ref obrigatorio."))
        if not texto_livre:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="texto_livre", level="error", message="Texto_livre obrigatorio."))
        if not categoria_item:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="categoria_item", level="error", message="Categoria_item obrigatoria."))
        elif categoria_item != "D":
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="categoria_item", level="error", message="Categoria_item deve ser D nesta entrega."))
        if not categoria_classif:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="categoria_classif", level="error", message="Categoria_classif obrigatoria."))
        elif categoria_classif not in {"F", "K"}:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="categoria_classif", level="error", message="Categoria_classif deve ser F ou K."))
        if not grupo_mercadoria:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="grupo_mercadoria", level="error", message="Grupo_mercadoria obrigatorio."))
        if requires_plant_or_center and not plant_or_center:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="plant_or_center", level="error", message="Plant/Center obrigatorio para este layout."))
        if allowed_tax_codes and not tax_code:
            allowed_text = "/".join(sorted(allowed_tax_codes))
            errors.append(
                ValidationIssue(
                    sheet="ITENS",
                    row_number=row_number,
                    column_name="tax_code",
                    level="error",
                    message=f"Tax code obrigatorio para este layout. Use {allowed_text}.",
                )
            )
        elif allowed_tax_codes and tax_code not in allowed_tax_codes:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="tax_code", level="error", message=f"Tax code invalido para este layout: {tax_code}."))
        if item_ref and item_ref in item_index:
            errors.append(ValidationIssue(sheet="ITENS", row_number=row_number, column_name="item_ref", level="error", message="Item_ref duplicado."))

        if _has_row_error(errors, "ITENS", row_number):
            continue

        item = PurchaseOrderItem(
            item_ref=item_ref,
            texto_livre=texto_livre,
            categoria_item=categoria_item,
            categoria_classif=categoria_classif,
            grupo_mercadoria=grupo_mercadoria,
            plant_or_center=plant_or_center,
            tax_code=tax_code,
            observacao_item=observacao_item,
            conta_razao_default=conta_razao_default,
            service_lines=[],
        )
        item_payloads.append(item)
        item_index[item_ref] = item

    service_count_by_item: dict[str, int] = {item_ref: 0 for item_ref in item_index}
    seen_line_refs: set[tuple[str, str]] = set()
    for row_number, row in enumerate(service_rows, start=2):
        try:
            quantidade = as_decimal(row.get("quantidade"))
            preco_bruto = as_decimal(row.get("preco_bruto"))
        except Exception as exc:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="", level="error", message=str(exc)))
            continue

        item_ref = as_text(row.get("item_ref"))
        line_ref = as_text(row.get("line_ref"))
        numero_servico = as_text(row.get("numero_servico"))
        ordem = as_text(row.get("ordem")) or None
        centro_custo = as_text(row.get("centro_custo")) or None
        conta_razao = as_text(row.get("conta_razao")) or None
        descricao_externa = as_text(row.get("descricao_externa")) or None

        if not item_ref:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="item_ref", level="error", message="Item_ref obrigatorio."))
        elif item_ref not in item_index:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="item_ref", level="error", message="Item_ref nao encontrado na aba ITENS."))
        if not line_ref:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="line_ref", level="error", message="Line_ref obrigatorio."))
        elif item_ref and (item_ref, line_ref) in seen_line_refs:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="line_ref", level="error", message="Line_ref duplicado dentro do item."))
        if not numero_servico:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="numero_servico", level="error", message="Numero_servico obrigatorio."))
        if quantidade is None or quantidade <= 0:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="quantidade", level="error", message="Quantidade deve ser maior que zero."))
        if preco_bruto is None:
            preco_bruto = Decimal("0")
        if preco_bruto < 0:
            errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="preco_bruto", level="error", message="Preco_bruto deve ser maior ou igual a zero."))

        item = item_index.get(item_ref)
        categoria_classif = item.categoria_classif if item else ""
        inherited_account = item.conta_razao_default if item else None
        if categoria_classif == "F":
            if not ordem:
                errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="ordem", level="error", message="Ordem obrigatoria para item F."))
            if centro_custo:
                warnings.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="centro_custo", level="warning", message="Centro_custo informado para item F sera ignorado."))
                centro_custo = None
        elif categoria_classif == "K":
            if not centro_custo:
                errors.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="centro_custo", level="error", message="Centro_custo obrigatorio para item K."))
            if ordem:
                warnings.append(ValidationIssue(sheet="SERVICOS", row_number=row_number, column_name="ordem", level="warning", message="Ordem informada para item K sera ignorada."))
                ordem = None

        if not conta_razao and not inherited_account:
            errors.append(
                ValidationIssue(
                    sheet="SERVICOS",
                    row_number=row_number,
                    column_name="conta_razao",
                    level="error",
                    message="Conta_razao obrigatoria na linha ou no item pai.",
                )
            )

        if _has_row_error(errors, "SERVICOS", row_number):
            continue

        seen_line_refs.add((item_ref, line_ref))
        service_line = PurchaseOrderServiceLine(
            item_ref=item_ref,
            line_ref=line_ref,
            numero_servico=numero_servico,
            quantidade=quantidade or Decimal("0"),
            preco_bruto=preco_bruto,
            ordem=ordem,
            centro_custo=centro_custo,
            conta_razao=conta_razao or inherited_account,
            descricao_externa=descricao_externa,
        )
        item.service_lines.append(service_line)
        service_count_by_item[item_ref] = service_count_by_item.get(item_ref, 0) + 1

    for item_ref, item in item_index.items():
        if service_count_by_item.get(item_ref, 0) <= 0:
            errors.append(
                ValidationIssue(
                    sheet="ITENS",
                    row_number=_row_number_for_item(item_rows, item_ref),
                    column_name="item_ref",
                    level="error",
                    message="Item sem linhas de servico na aba SERVICOS.",
                )
            )
        else:
            item.service_lines = _sort_service_lines(item.service_lines)

    if errors:
        return None, errors, warnings

    header = PurchaseOrderHeader(
        doc_ref=as_text(header_row.get("doc_ref")),
        tipo_doc=as_text(header_row.get("tipo_doc")),
        org_compras=as_text(header_row.get("org_compras")),
        grupo_compras=as_text(header_row.get("grupo_compras")),
        empresa=as_text(header_row.get("empresa")),
        fornecedor=as_text(header_row.get("fornecedor")),
        moeda=as_text(header_row.get("moeda")),
        condicao_pagamento=as_text(header_row.get("condicao_pagamento")),
        incoterms=as_text(header_row.get("incoterms")) or None,
        texto_cabecalho=as_text(header_row.get("texto_cabecalho")) or None,
    )
    return PurchaseOrderPayload(header=header, items=item_payloads), errors, warnings
