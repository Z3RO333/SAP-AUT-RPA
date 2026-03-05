from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class PurchaseOrderHeader:
    doc_ref: str
    tipo_doc: str
    org_compras: str
    grupo_compras: str
    empresa: str
    fornecedor: str
    moeda: str
    condicao_pagamento: str
    incoterms: str | None = None
    texto_cabecalho: str | None = None

    def to_dict(self) -> dict:
        return {
            "doc_ref": self.doc_ref,
            "tipo_doc": self.tipo_doc,
            "org_compras": self.org_compras,
            "grupo_compras": self.grupo_compras,
            "empresa": self.empresa,
            "fornecedor": self.fornecedor,
            "moeda": self.moeda,
            "condicao_pagamento": self.condicao_pagamento,
            "incoterms": self.incoterms,
            "texto_cabecalho": self.texto_cabecalho,
        }


@dataclass(slots=True)
class PurchaseOrderServiceLine:
    item_ref: str
    line_ref: str
    numero_servico: str
    quantidade: Decimal
    preco_bruto: Decimal | None
    ordem: str | None = None
    centro_custo: str | None = None
    conta_razao: str | None = None
    descricao_externa: str | None = None

    def to_dict(self) -> dict:
        return {
            "item_ref": self.item_ref,
            "line_ref": self.line_ref,
            "numero_servico": self.numero_servico,
            "quantidade": str(self.quantidade),
            "preco_bruto": "" if self.preco_bruto is None else str(self.preco_bruto),
            "ordem": self.ordem,
            "centro_custo": self.centro_custo,
            "conta_razao": self.conta_razao,
            "descricao_externa": self.descricao_externa,
        }


@dataclass(slots=True)
class PurchaseOrderItem:
    item_ref: str
    texto_livre: str
    categoria_item: str
    categoria_classif: str
    grupo_mercadoria: str
    plant_or_center: str | None = None
    tax_code: str | None = None
    observacao_item: str | None = None
    conta_razao_default: str | None = None
    service_lines: list[PurchaseOrderServiceLine] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "item_ref": self.item_ref,
            "texto_livre": self.texto_livre,
            "categoria_item": self.categoria_item,
            "categoria_classif": self.categoria_classif,
            "grupo_mercadoria": self.grupo_mercadoria,
            "plant_or_center": self.plant_or_center,
            "tax_code": self.tax_code,
            "observacao_item": self.observacao_item,
            "conta_razao_default": self.conta_razao_default,
            "service_lines": [line.to_dict() for line in self.service_lines],
        }


@dataclass(slots=True)
class PurchaseOrderPayload:
    header: PurchaseOrderHeader
    items: list[PurchaseOrderItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "header": self.header.to_dict(),
            "items": [item.to_dict() for item in self.items],
        }
