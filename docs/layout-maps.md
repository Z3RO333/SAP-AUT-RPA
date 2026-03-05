# Layout Maps

## Objetivo

Isolar IDs SAP em JSON para reduzir quebra por mudanca de layout.

## Local padrao

- Empacotado: `sap/layouts/<transacao>.json`
- Override por usuario: `%AppData%\Robos SAP\layouts\<transacao>.json`

Se existir override, ele tem prioridade.

## Estrutura basica

```json
{
  "version": 1,
  "transaction": "ME21N",
  "defaultProfile": "standard",
  "profiles": {
    "standard": {
      "fields": {},
      "buttons": {},
      "tabs": {},
      "toolbar": {}
    }
  }
}
```

## Regras

- Cada campo usa lista ordenada de candidatos
- O codigo sempre tenta o primeiro ID existente
- O driver nunca deve embutir um ID fixo que possa morar no JSON

## Transacoes entregues

- `iw32.json`
- `iw32-categorias.json`
- `iw38.json`
- `me2l.json`
- `mb51.json`
- `me23n.json`
- `me21n.json`

## Inspecao

O utilitario de inspecao exporta a arvore da tela SAP atual com:

- `id`
- `type`
- `name`
- `text`
- `tooltip`
- `childrenCount`

Use esse dump para curar o JSON manualmente.
