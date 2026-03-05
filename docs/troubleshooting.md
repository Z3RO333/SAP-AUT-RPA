# Troubleshooting

## Onde olhar primeiro

- `run.log`
- `result.json`
- screenshots da execucao
- `popup_dump.json`

## Erros comuns

### Nenhuma sessao SAP disponivel

- Abra o SAP Logon
- Faça login manual
- Confirme se o SAP GUI Scripting esta habilitado

### Mais de uma sessao SAP encontrada

- Escolha a sessao no seletor exibido pelo app

### Falha de layout

- Revise o JSON em `sap/layouts/...`
- Gere um novo dump com `Inspecionar tela SAP`
- Atualize os candidatos do campo faltante

### Excel invalido na ME21N

- Confirme as abas `CABECALHO` e `ITENS`
- Revise os campos obrigatorios
- Verifique `K/F/A/P`

### Sem pedido criado na ME21N

- Revise `status_bar_text` e `status_bar_type` no `result.json`
- Valide a regex de numero do pedido contra o idioma do ambiente

## Boas praticas

- Homologue layouts por ambiente
- Mantenha overrides em `%AppData%\Robos SAP\layouts`
- Sempre preserve os artefatos de uma falha antes de alterar o layout map
