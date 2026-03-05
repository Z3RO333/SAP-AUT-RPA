# ME21N

## Escopo da entrega

A `ME21N` desta versao foi ajustada para o fluxo real de pedido de servico:

- `categoria_item = D`
- `categoria_classif = F` ou `K`
- multiplos itens por pedido
- multiplas linhas de servico por item
- `tax_code` por item
- `conta_razao` por item ou por linha
- referencia contabil por linha:
  - `ordem` quando o item e `F`
  - `centro_custo` quando o item e `K`

Fora de escopo nesta entrega:

- material
- `A`
- `P`
- texto livre manual por linha de servico
- PB00 como fluxo principal

## Modos de uso

O painel tem dois modos:

- `Modo Guiado`
- `Planilha XLSX`

### Modo Guiado

E o modo principal para uso manual e recorrente.

Blocos da tela:

- `Execucao`: profile, `DRY_RUN`, validar, inspecionar e executar
- `Padroes Editaveis`: valores repetitivos persistidos em `%AppData%\\Robos SAP\\me21n.defaults.json`
- `Cabecalho do Pedido`
- `Itens do Pedido`
- `Editor do Item`
- `Linhas de Servico`

No modo guiado:

- o item pode ser `F` ou `K`
- a linha de servico mostra `Ordem` quando o item e `F`
- a linha de servico mostra `Centro de custo` quando o item e `K`
- `texto breve` da linha nao e digitado manualmente; o robo assume que o SAP o resolve a partir do `numero_servico`

### Planilha XLSX

Use quando o pedido ja estiver estruturado em workbook.

Abas obrigatorias:

- `CABECALHO`
- `ITENS`
- `SERVICOS`

## Campos do CABECALHO

Obrigatorios:

- `doc_ref`
- `tipo_doc`
- `org_compras`
- `grupo_compras`
- `empresa`
- `fornecedor`
- `moeda`
- `condicao_pagamento`

Opcionais:

- `incoterms`
- `texto_cabecalho`

## Campos de ITENS

Colunas preferidas:

- `item_ref`
- `texto_livre`
- `categoria_item`
- `categoria_classif`
- `grupo_mercadoria`
- `plant_or_center`
- `tax_code`
- `observacao_item`
- `conta_razao_default`

Aliases aceitos:

- `conta_contabil` -> `conta_razao_default`
- `centro` -> `plant_or_center`
- `mwskz` -> `tax_code`

Regras:

- `categoria_item` deve ser `D`
- `categoria_classif` deve ser `F` ou `K`
- `tax_code` obrigatorio no profile entregue, com valores `S1` ou `S2`
- `plant_or_center` pode ser obrigatorio conforme o profile

## Campos de SERVICOS

Colunas preferidas:

- `item_ref`
- `line_ref`
- `numero_servico`
- `quantidade`
- `preco_bruto`
- `ordem`
- `centro_custo`
- `conta_razao`

Aliases aceitos:

- `service_code` -> `numero_servico`
- `srvpos` -> `numero_servico`
- `valor_total` -> `preco_bruto`
- `tbtwr` -> `preco_bruto`
- `aufnr` -> `ordem`
- `conta_contabil` -> `conta_razao`
- `sakto` -> `conta_razao`

Regras:

- item `F` exige `ordem`
- item `K` exige `centro_custo`
- `conta_razao` da linha tem prioridade
- se a linha nao tiver `conta_razao`, o robo tenta herdar `conta_razao_default` do item

## Validacoes

Antes de abrir o SAP, o robo aborta se:

- faltar qualquer aba obrigatoria
- `CABECALHO` nao tiver exatamente uma linha
- `ITENS` estiver vazio
- `SERVICOS` estiver vazio
- algum `SERVICOS.item_ref` nao existir em `ITENS`
- algum item ficar sem linhas de servico
- `categoria_item != D`
- `categoria_classif` nao for `F` nem `K`
- faltar `tax_code` no item
- `tax_code` fora de `S1/S2`
- faltar `condicao_pagamento`
- faltar `numero_servico`, `quantidade` ou `preco_bruto`
- item `F` vier sem `ordem`
- item `K` vier sem `centro_custo`
- faltar `conta_razao` na linha e no item

## Layout map

O layout ativo esta em `sap/layouts/me21n.json`.

Profile entregue no repositorio:

- `service_item_fk`

Esse profile cobre:

- fornecedor no topo
- `ZTERM`
- org. compras, grupo compras e empresa
- overview do item `D/F` e `D/K`
- tabela de servicos
- popup contabil com `conta_razao`
- tentativa de `ordem` na grade e fallback por popup
- `centro_custo` por popup
- aba de imposto
- save com popup `SPOP-VAROPTION2`

Se o ambiente SAP variar, use o botao `Inspecionar tela SAP` e ajuste por override em:

- `%AppData%\\Robos SAP\\layouts\\me21n.json`

## Dry Run

Com `DRY_RUN` marcado, o robo:

- abre e prepara a `ME21N`
- preenche cabecalho, itens e linhas
- captura mensagens na barra de status
- nao salva o pedido

## Artefatos gerados

Cada execucao grava:

- `payload.json`
- `result.json`
- `run.log`
- screenshot em falha
- `popup_dump.json` quando houver popup relevante

## Observacoes operacionais

- o robo nao cria sessoes novas no SAP
- o robo nao depende de um unico `subSUB`
- `ordem` e `centro_custo` sao tratados por item/linha conforme a classificacao
- `tax_code` e por item, nao por linha
- o profile de `K` ainda precisa ser homologado no ambiente SAP alvo
