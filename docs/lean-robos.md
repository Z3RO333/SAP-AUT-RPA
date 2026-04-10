# Lean dos Robos SAP

Este material foi montado a partir dos fluxos expostos no menu principal e dos drivers dos robos. Ele serve para transformar cada modulo em uma narrativa de Lean com foco em produtividade, padronizacao, reducao de erro e ganho de capacidade.

Importante: o repositorio nao traz uma base historica consolidada de tempo manual x tempo automatizado. Entao, abaixo eu separo:

- o que ja e comprovavel pelo sistema
- o que cada robo elimina no processo manual
- quais indicadores usar para calcular o ganho real

## Como medir o ganho de produtividade

Use estas formulas no seu Lean:

- `Tempo economizado por execucao = tempo manual medio - tempo com robo`
- `Horas economizadas no mes = tempo economizado por execucao x volume mensal`
- `Ganho de produtividade (%) = ((tempo manual medio - tempo com robo) / tempo manual medio) x 100`
- `Reducao de erros (%) = ((erros antes - erros depois) / erros antes) x 100`
- `Aumento de capacidade = horas economizadas no mes / horas disponiveis por colaborador`

Dados que o sistema ja consegue gerar ou apoiar:

- quantidade processada por execucao
- quantidade com sucesso e falha
- logs de execucao
- `payload.json` e `result.json`
- evidencias de erro por screenshot e popup dump
- arquivos gerados em Excel e PDF

## Como organizar a defesa do Lean

Para cada robo, use a mesma estrutura:

1. Problema atual
2. Atividade manual que toma tempo
3. O que o robo automatiza
4. Qual desperdicio Lean ele reduz
5. Qual KPI comprova o ganho
6. Qual economia mensal isso gera

Os desperdicios Lean mais atacados aqui sao:

- espera
- movimentacao desnecessaria
- retrabalho
- excesso de processamento
- erro de digitacao
- falta de padronizacao

## Resumo executivo por robo

| Robo | Tipo | O que automatiza | Ganho principal |
| --- | --- | --- | --- |
| IW38 | Consulta SAP | Extracao de ordens por centro de trabalho e periodo com Excel/PDF | Rapidez na obtencao de carteira e padronizacao de relatorio |
| IW32 - Liberar | Transacional SAP | Liberacao em lote de ordens | Reducao do tempo repetitivo por ordem |
| IW32 - Cancelar | Transacional SAP | Cancelamento em lote com motivo e numero de servico | Padronizacao e velocidade no encerramento de ordens inviaveis |
| IW32 - Concluir | Transacional SAP | Conclusao em lote com matricula e nota | Aumento de vazao operacional e menor retrabalho |
| IW32 - Categorias | Transacional SAP | Preenchimento de categorias e valores em lote | Grande reducao de digitacao manual e erro humano |
| ME23N - Alimentacao | Transacional SAP | Copia item e alimenta servicos/AUFNR em pedidos existentes | Menor tempo de alteracao de pedido e menos erro de vinculacao |
| ME21N - Criar Pedido | Transacional SAP | Validacao e criacao de pedido de servico | Reducao de lead time e de erro na entrada de pedido |
| IW38 -> ME21N | Ponte entre transacoes | Seleciona ordens na IW38 e abre a criacao na ME21N | Elimina handoff manual entre manutencao e compras |
| MB51 | Consulta SAP | Extracao de documentos de material | Rapidez para analise e auditoria |
| ME2L | Consulta SAP | Extracao de pedidos por fornecedor | Visao rapida de carteira de compras |
| Ordens em Aberto | Relatorio offline | Filtro de base local de ordens abertas | Menor tempo para consolidar e distribuir informacao |
| Relatorio Fornecedor | Relatorio offline | Filtro de base consolidada por fornecedor | Agilidade para cobranca, follow-up e analise |
| IW28 | Nao implementado | Ainda nao ativo | Nao deve entrar como Lean entregue nesta fase |

## Lean por robo

### 1. IW38

- Problema atual: para levantar ordens por centro de trabalho, o usuario precisa abrir a IW38, preencher filtros, executar, tratar o retorno e montar a saida manualmente.
- O que o robo faz: consulta a IW38 por codigo e periodo, extrai a grade ALV e gera Excel e PDF.
- Ganho Lean: reduz espera, padroniza a extracao e elimina a preparacao manual do relatorio.
- KPI principal: `ordens extraidas por execucao`, `tempo para emitir relatorio`, `tempo de preparacao do PDF`.
- Como medir: cronometre uma consulta manual completa e compare com o tempo do robo para a mesma carteira.
- Frase pronta para o Lean: "O robo IW38 reduz o tempo de levantamento da carteira operacional e entrega a informacao ja estruturada para analise, sem montagem manual de planilha."

### 2. IW32 - Liberar

- Problema atual: liberar ordens uma a uma no IW32 exige abrir ordem, localizar acao, salvar e repetir o ciclo varias vezes.
- O que o robo faz: recebe uma lista de ordens e executa a liberacao em lote, registrando sucesso e falha por ordem.
- Ganho Lean: elimina repeticao operacional, reduz toque manual e aumenta a quantidade de ordens tratadas por hora.
- KPI principal: `ordens liberadas/hora`, `tempo medio por ordem`, `taxa de sucesso`.
- Como medir: compare o tempo para liberar 20, 50 ou 100 ordens manualmente versus o lote automatizado.
- Frase pronta para o Lean: "O robo de liberacao transforma uma rotina repetitiva em processamento em lote, liberando capacidade do time para atividades de analise e excecao."

### 3. IW32 - Cancelar

- Problema atual: cancelar ordens em massa exige navegacao repetitiva, preenchimento de motivo e, em alguns casos, numero de servico.
- O que o robo faz: cancela ordens em lote pela aba `+CUK`, preenche motivo, numero de servico e salva o resultado por ordem.
- Ganho Lean: padroniza o motivo de cancelamento, reduz retrabalho e acelera o saneamento da carteira.
- KPI principal: `ordens canceladas/hora`, `% cancelamentos com motivo padronizado`, `tempo medio por ordem`.
- Como medir: compare o processamento de uma lista de cancelamento antes e depois do robo.
- Frase pronta para o Lean: "O robo de cancelamento reduz tempo operacional e melhora a qualidade do cadastro ao garantir padrao de motivo e rastreabilidade da execucao."

### 4. IW32 - Concluir

- Problema atual: concluir ordens manualmente exige repetir o fluxo `EXEC/AVEX/CONC`, informar matricula, nota e salvar ordem por ordem.
- O que o robo faz: executa esse fluxo em lote, usando matricula e nota padronizadas, com retorno individual.
- Ganho Lean: aumenta a vazao de encerramento operacional e reduz o risco de esquecer etapas ou campos.
- KPI principal: `ordens concluidas/hora`, `tempo medio de conclusao`, `taxa de retrabalho`.
- Como medir: pegue um lote real de ordens concluidas na semana e compare o tempo manual x robotizado.
- Frase pronta para o Lean: "O robo de conclusao reduz o tempo de encerramento de ordens e padroniza a baixa operacional no SAP."

### 5. IW32 - Categorias

- Problema atual: preencher categoria e valor por ordem costuma ser uma atividade altamente repetitiva e sensivel a erro de digitacao.
- O que o robo faz: permite montar um lote por grupo, colagem manual ou planilha e preenche categoria, valor e numero de servico no IW32.
- Ganho Lean: este e um dos robos com maior potencial de produtividade porque troca digitacao linha a linha por execucao em lote.
- KPI principal: `linhas processadas/hora`, `tempo por linha`, `taxa de erro de categoria`, `taxa de retrabalho`.
- Como medir: compare uma amostra de 50 ou 100 linhas de categoria feitas manualmente versus o lote automatizado.
- Frase pronta para o Lean: "O robo de categorias ataca diretamente o desperdicio de digitacao repetitiva e melhora a confiabilidade do preenchimento financeiro das ordens."

### 6. ME23N - Alimentacao

- Problema atual: alterar pedido existente, copiar item e preencher varias linhas de servico/AUFNR e uma tarefa demorada e sujeita a erro.
- O que o robo faz: abre o pedido, copia o item, ajusta data de entrega e preenche as linhas de servico com as ordens AUFNR.
- Ganho Lean: reduz tempo de manutencao do pedido e melhora a consistencia entre pedido e ordens vinculadas.
- KPI principal: `pedidos alimentados/hora`, `linhas AUFNR preenchidas/hora`, `% pedidos sem retrabalho`.
- Como medir: compare o tempo para ajustar um pedido com varias linhas manualmente e com o robo.
- Frase pronta para o Lean: "O robo de alimentacao de pedidos reduz o lead time de alteracao no ME23N e melhora a qualidade do vinculo entre pedido e ordem."

### 7. ME21N - Criar Pedido

- Problema atual: criar pedido de servico com varios itens e linhas exige preenchimento detalhado, validacoes contabeis e alto risco de erro antes da gravacao.
- O que o robo faz: valida o input antes de entrar no SAP, suporta modo guiado e planilha XLSX, preenche cabecalho, itens, servicos e contabilizacao, e pode rodar em `DRY_RUN`.
- Ganho Lean: reduz retrabalho na origem, diminui erro de entrada, encurta o lead time de criacao e padroniza a estrutura do pedido.
- KPI principal: `pedidos criados/hora`, `itens por pedido`, `linhas de servico por pedido`, `% erros barrados antes do SAP`, `% pedidos criados sem retrabalho`.
- Como medir: compare o tempo total de criacao de pedidos complexos, incluindo correcao de erro, antes e depois da automacao.
- Frase pronta para o Lean: "O robo ME21N reduz o lead time de compras de servico ao combinar validacao previa, execucao padronizada e rastreabilidade completa da criacao."

### 8. IW38 -> ME21N

- Problema atual: o usuario precisa extrair ordens na IW38, selecionar, copiar dados e depois iniciar a criacao do pedido na ME21N manualmente.
- O que o robo faz: cola as ordens na selecao multipla da IW38, executa o relatorio, seleciona tudo e aciona a abertura da ME21N.
- Ganho Lean: reduz handoff entre manutencao e compras, elimina copia manual e acelera o inicio da criacao do pedido.
- KPI principal: `ordens transferidas por execucao`, `tempo entre selecao de ordens e abertura da ME21N`, `erros de transicao evitados`.
- Como medir: cronometre o tempo de levar um lote de ordens da consulta ate a tela de criacao do pedido.
- Frase pronta para o Lean: "O robo IW38 -> ME21N reduz o tempo de transicao entre planejamento e compras, eliminando etapas manuais de selecao e transferencia."

### 9. MB51

- Problema atual: levantar documentos de material para analise costuma exigir consulta manual, exportacao e organizacao posterior.
- O que o robo faz: extrai dados da MB51 por centro, fornecedor, tipo de movimento e periodo, e gera Excel/PDF.
- Ganho Lean: reduz tempo de pesquisa, facilita auditoria e padroniza o relatorio de movimentacao.
- KPI principal: `registros extraidos por execucao`, `tempo de resposta para analise`, `tempo de montagem do relatorio`.
- Como medir: compare o tempo para levantar e formatar uma consulta manual com a execucao automatizada.
- Frase pronta para o Lean: "O robo MB51 transforma uma consulta operacional em informacao pronta para analise, reduzindo o tempo gasto em busca e formatacao."

### 10. ME2L

- Problema atual: acompanhar pedidos por fornecedor no SAP exige filtragem manual e tratamento posterior dos dados.
- O que o robo faz: consulta a ME2L por fornecedor e periodo, extrai os registros e gera Excel/PDF.
- Ganho Lean: agiliza o follow-up com fornecedor e padroniza a visao de carteira de compras.
- KPI principal: `registros extraidos por execucao`, `tempo para emitir relatorio`, `tempo para responder cobrancas internas`.
- Como medir: compare o tempo de uma consulta manual de carteira por fornecedor com o tempo do robo.
- Frase pronta para o Lean: "O robo ME2L reduz o tempo de consolidacao da carteira de compras por fornecedor e acelera a tomada de decisao."

### 11. Ordens em Aberto

- Problema atual: depois de extrair uma base local, ainda existe trabalho manual para filtrar centro, periodo e montar a versao distribuivel.
- O que o robo faz: carrega uma planilha local, aplica filtros e exporta a base final em Excel e PDF.
- Ganho Lean: reduz esforco administrativo e acelera a distribuicao da informacao consolidada.
- KPI principal: `registros filtrados`, `tempo de filtragem`, `tempo para publicar relatorio`.
- Como medir: compare a montagem manual da visao filtrada versus o processamento no painel.
- Frase pronta para o Lean: "O modulo de Ordens em Aberto reduz o tempo de consolidacao local e entrega a base pronta para acompanhamento operacional."

### 12. Relatorio Fornecedor

- Problema atual: o time precisa buscar fornecedor, centro e periodo em uma base consolidada e depois gerar uma saida utilizavel.
- O que o robo faz: filtra a planilha consolidada por fornecedor, centro e periodo e gera Excel/PDF.
- Ganho Lean: acelera cobranca, follow-up e analise de desempenho por fornecedor.
- KPI principal: `registros filtrados`, `tempo para montar o relatorio`, `tempo de resposta para a area cliente`.
- Como medir: compare o tempo de procurar manualmente na base consolidada com o fluxo automatizado.
- Frase pronta para o Lean: "O relatorio por fornecedor reduz o tempo de resposta das areas de apoio e melhora a disponibilidade da informacao para cobranca e gestao."

### 13. IW28

- Situacao atual: o painel informa explicitamente que a IW28 ainda nao foi implementada nesta fase.
- Recomendacao para o Lean: nao trate como entrega realizada. No maximo, registre como oportunidade futura.
- Frase pronta: "A automacao IW28 ainda esta em backlog e nao compoe o ganho capturado nesta etapa."

## KPIs recomendados por categoria

### Robos transacionais

Use principalmente:

- ordens/pedidos/linhas processadas por hora
- tempo medio por item
- taxa de sucesso
- taxa de retrabalho
- horas economizadas no mes

### Robos de consulta e relatorio

Use principalmente:

- tempo para emitir relatorio
- tempo para responder uma demanda da operacao
- quantidade de registros extraidos
- numero de relatorios gerados por periodo
- padronizacao da saida

## Modelo rapido para preencher no seu Lean

Use esta tabela e complete com medicao real:

| Robo | Volume mensal | Tempo manual medio | Tempo com robo | Horas economizadas | Ganho produtividade |
| --- | --- | --- | --- | --- | --- |
| IW32 - Liberar | `__` | `__` | `__` | `__` | `__` |
| IW32 - Cancelar | `__` | `__` | `__` | `__` | `__` |
| IW32 - Concluir | `__` | `__` | `__` | `__` | `__` |
| IW32 - Categorias | `__` | `__` | `__` | `__` | `__` |
| ME23N - Alimentacao | `__` | `__` | `__` | `__` | `__` |
| ME21N - Criar Pedido | `__` | `__` | `__` | `__` | `__` |
| IW38 -> ME21N | `__` | `__` | `__` | `__` | `__` |
| IW38 | `__` | `__` | `__` | `__` | `__` |
| MB51 | `__` | `__` | `__` | `__` | `__` |
| ME2L | `__` | `__` | `__` | `__` | `__` |
| Ordens em Aberto | `__` | `__` | `__` | `__` | `__` |
| Relatorio Fornecedor | `__` | `__` | `__` | `__` | `__` |

## Fechamento

Se voce quiser defender cada robo como um Lean separado, a melhor linha e:

- qual rotina manual ele substitui
- qual desperdicio ele remove
- qual volume ele absorve
- quanto tempo economiza
- como melhora a qualidade e a rastreabilidade

Se voce quiser defender por macroprocesso, a melhor divisao e:

- gestao de ordens: `IW32 - Liberar`, `IW32 - Cancelar`, `IW32 - Concluir`, `IW32 - Categorias`
- compras e pedidos: `ME23N - Alimentacao`, `ME21N - Criar Pedido`, `IW38 -> ME21N`
- consulta e informacao: `IW38`, `MB51`, `ME2L`, `Ordens em Aberto`, `Relatorio Fornecedor`
