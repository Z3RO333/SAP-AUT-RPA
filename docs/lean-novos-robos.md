# Lean dos novos robos adicionados

Base de leitura: historico Git do repositorio.

- `25a32e0`: base inicial do projeto
- `77a2718`: melhorias ME21N, novo modulo `IW38 -> ME21N` e correcoes

Conclusao objetiva:

- novo robo adicionado de fato: `IW38 -> ME21N`
- evolucoes relevantes que tambem geram valor Lean novo: `ME21N` e `IW32 - Categorias`

Se voce precisar falar estritamente dos "novos robos", use apenas a secao `IW38 -> ME21N`.
Se quiser fortalecer a apresentacao, use tambem as duas evolucoes abaixo como ganhos incrementais da aplicacao.

## 1. Lean do novo robo: IW38 -> ME21N

### Problema atual

Hoje o usuario precisa:

- abrir a `IW38`
- colar ou pesquisar ordens manualmente
- executar o relatorio
- selecionar os itens desejados
- iniciar a criacao de pedido na `ME21N`

Esse fluxo cria desperdicio de:

- espera
- movimentacao manual entre telas
- repeticao operacional
- risco de esquecer ordens ou selecionar itens errados

### Solucao entregue

O robo `IW38 -> ME21N`:

- recebe a lista de ordens
- cola tudo na selecao multipla da `IW38`
- executa o relatorio
- seleciona todas as linhas do grid
- aciona a abertura da criacao de pedido na `ME21N`

### Ganho Lean

- reduz o tempo de transicao entre manutencao e compras
- elimina a etapa manual de carregar e selecionar ordens uma a uma
- padroniza o inicio do processo de criacao de pedido
- reduz erro de handoff entre consulta e criacao

### KPI recomendado

- `tempo entre receber a lista de ordens e abrir a ME21N`
- `quantidade de ordens transferidas por execucao`
- `% de execucoes sem retrabalho`
- `horas economizadas por mes`

### Formula de produtividade

- `ganho de produtividade (%) = ((tempo manual - tempo com robo) / tempo manual) x 100`

### Frase pronta para o Lean

"O robo IW38 -> ME21N elimina etapas manuais entre a selecao de ordens e a abertura da criacao de pedido, reduzindo tempo de preparacao, erro operacional e espera entre areas."

## 2. Lean complementar: evolucao do ME21N

O `ME21N` nao nasceu neste ultimo commit, mas recebeu melhorias que aumentam o ganho Lean do robo.

### O que mudou

- novo botao `Colar servicos`
- possibilidade de excluir multiplas linhas
- aplicacao de `Valor em lote` nas linhas selecionadas
- melhoria no tratamento de `preco_bruto` opcional
- maior clareza de uso no painel

### Ganho Lean incremental

- reduz ainda mais a digitacao manual dentro do pedido
- acelera a montagem de pedidos com muitas linhas de servico
- diminui retrabalho de ajuste de preco
- melhora a experiencia operacional e reduz erro de preenchimento

### KPI recomendado

- `linhas de servico criadas por hora`
- `tempo para montar um pedido complexo`
- `% de pedidos sem correcao manual`
- `tempo medio por pedido`

### Frase pronta para o Lean

"A evolucao do robo ME21N aumenta a produtividade na criacao de pedidos complexos ao reduzir digitacao repetitiva, edicao manual e retrabalho em linhas de servico."

## 3. Lean complementar: evolucao do IW32 - Categorias

O `IW32 - Categorias` tambem recebeu uma evolucao relevante, embora nao seja um robo novo no menu.

### O que mudou

- nova camada de parsing de entrada
- suporte melhor para colagem manual
- suporte a montagem de lote por grupo
- suporte a importacao estruturada
- cobertura de testes ampliada

### Ganho Lean incremental

- mais velocidade para montar lotes
- menor dependencia de ajuste manual antes da execucao
- menor risco de erro de formato na entrada
- mais robustez para operacao recorrente

### KPI recomendado

- `linhas preparadas por minuto antes da execucao`
- `tempo total da preparacao do lote`
- `% de linhas aceitas sem ajuste manual`
- `tempo medio para alimentar categorias`

### Frase pronta para o Lean

"A evolucao do IW32 - Categorias reduz o esforco de preparacao do lote e aumenta a confiabilidade da entrada, tornando a automacao mais escalavel para volumes maiores."

## Resumo executivo

Se a pergunta for "qual novo robo entrou?", a resposta correta e:

- `IW38 -> ME21N`

Se a pergunta for "quais novos ganhos Lean entraram na ultima entrega?", use:

- `IW38 -> ME21N` como novo robo
- `ME21N` como ganho incremental de produtividade
- `IW32 - Categorias` como ganho incremental de produtividade e robustez
