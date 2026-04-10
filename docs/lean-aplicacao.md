# Lean da Aplicacao Robos SAP

## 1. Nome do projeto

`Robos SAP` - plataforma desktop para automacao operacional, consulta SAP e geracao de relatorios padronizados.

## 2. Resumo executivo

Esta aplicacao centraliza, em uma unica interface desktop, um conjunto de automacoes SAP GUI Scripting voltadas para rotinas repetitivas de manutencao, compras e emissao de relatorios. Em vez de executar transacoes SAP manualmente, uma a uma, o usuario escolhe um modulo, informa os dados de entrada e o sistema realiza o processamento, registra logs, gera artefatos e entrega saidas padronizadas.

No repositorio atual, a aplicacao concentra:

- robos transacionais para `IW32`, `ME23N`, `ME21N` e `IW38 -> ME21N`
- robos de consulta para `IW38`, `MB51` e `ME2L`
- modulos offline para `Ordens em Aberto` e `Relatorio Fornecedor`
- camada comum de sessao SAP, layouts, logs, evidencias e empacotamento

Em termos de Lean, esta aplicacao nao representa apenas um robo isolado. Ela representa uma plataforma unica de automacao operacional para reduzir tempo de execucao, padronizar atividades, diminuir erro manual e aumentar a capacidade da equipe sem aumentar headcount.

## 3. Problema de negocio

O processo atual, quando feito manualmente no SAP, sofre com os seguintes pontos:

- alto volume de digitacao repetitiva
- navegacao ordem por ordem ou pedido por pedido
- dependencia de usuarios experientes para saber o caminho correto no SAP
- tempo elevado para gerar relatorios e consolidar informacao
- retrabalho causado por erro de digitacao, preenchimento incompleto ou selecao incorreta
- baixa rastreabilidade da execucao quando o processo e feito manualmente
- dificuldade para escalar a operacao em picos de demanda

Em resumo, o problema central e a existencia de atividades operacionais de baixo valor agregado consumindo tempo da equipe em transacoes SAP e em manipulacao manual de planilhas.

## 4. Objetivo do Lean

O objetivo deste Lean e demonstrar que a aplicacao `Robos SAP`:

- reduz o lead time das rotinas operacionais
- aumenta a produtividade por colaborador
- padroniza processos antes dependentes de experiencia individual
- reduz falhas operacionais e retrabalho
- gera rastreabilidade por log, resultado e evidencias
- cria uma base reutilizavel para novas automacoes SAP dentro do mesmo produto

## 5. Escopo da aplicacao

### 5.1 Macroprocessos cobertos

#### Gestao de ordens

- `IW32 - Liberar`
- `IW32 - Cancelar`
- `IW32 - Concluir`
- `IW32 - Categorias`

#### Compras e pedidos

- `ME23N - Alimentacao`
- `ME21N - Criar Pedido`
- `IW38 -> ME21N`

#### Consulta e relatorio SAP

- `IW38`
- `MB51`
- `ME2L`

#### Tratamento de base local

- `Ordens em Aberto`
- `Relatorio Fornecedor`

### 5.2 Itens fora do ganho capturado atual

- `IW28` aparece no menu, mas o painel atual informa que ainda nao foi implementado nesta fase

## 6. Como a aplicacao funciona como produto

O valor da aplicacao nao esta apenas nos robos separados, mas no fato de ela entregar uma estrutura comum de operacao:

- menu principal unico para abrir todos os modulos
- interface desktop padronizada em `Python + Tkinter`
- conexao e escolha de sessao SAP compartilhadas
- camada unica para acao, espera, leitura de status, popup e screenshot
- layouts externos em JSON, com possibilidade de override sem mexer no codigo-fonte
- saida padronizada com `run.log`, `payload.json`, `result.json` e evidencias
- build automatizado com `PyInstaller`
- empacotamento final com `Inno Setup`

Isso e relevante para o Lean porque reduz o custo de manutencao e aumenta a capacidade de evolucao da ferramenta ao longo do tempo.

## 7. Desperdicios Lean atacados pela aplicacao

### Espera

- menos tempo para emitir relatorios
- menos tempo para concluir, cancelar, liberar ou alimentar registros no SAP
- menos tempo entre a necessidade do negocio e a disponibilizacao da informacao

### Movimentacao desnecessaria

- reducao de cliques repetitivos
- eliminacao de navegacao ordem por ordem
- reducao de troca manual entre transacoes e planilhas

### Excesso de processamento

- o sistema ja gera Excel, PDF, log e artefatos sem depender de tratamento adicional
- varias rotinas passam a ser executadas em lote, em vez de uma a uma

### Defeitos

- validacoes previas no `ME21N`
- padronizacao de motivo, matricula, nota, categoria e numero de servico em varios fluxos
- screenshots e popup dump para tratamento de excecao

### Retrabalho

- menos retorno ao SAP para corrigir digitacao
- menos necessidade de refazer relatorio manual
- menos dependencia de reconstruir o que foi feito, porque a execucao deixa rastro

### Talento subutilizado

- a equipe deixa de gastar tempo com atividade mecanica e pode focar em excecao, analise e tomada de decisao

## 8. Estado atual x estado futuro

| Situacao atual | Estado futuro com a aplicacao |
| --- | --- |
| Usuario executa rotinas SAP manualmente, uma por uma | Usuario aciona modulos com processamento em lote |
| Relatorios dependem de consulta, exportacao e tratamento manual | Relatorios sao gerados em Excel/PDF com padrao unico |
| Falhas operacionais ficam dispersas e sem evidencias | Execucao gera log, resultado, screenshot e dump quando necessario |
| Mudanca de layout SAP exige ajuste manual no fluxo | Layouts podem ser tratados por perfis e overrides em JSON |
| Distribuicao da ferramenta e mais dificil | Build e instalador permitem padronizacao de implantacao |

## 9. Ganhos esperados no nivel da aplicacao

Os ganhos do Lean da aplicacao inteira podem ser defendidos em cinco frentes:

### 9.1 Produtividade operacional

- aumento de ordens, pedidos, linhas e relatorios processados por hora
- reducao do tempo medio por atividade

### 9.2 Qualidade

- reducao de erro de digitacao
- maior padronizacao de preenchimento
- menor retrabalho em processos SAP sensiveis

### 9.3 Tempo de resposta

- atendimento mais rapido a demandas operacionais
- reducao do tempo para consulta e consolidacao de dados

### 9.4 Rastreabilidade e governanca

- cada execucao pode deixar log, payload, resultado e evidencias
- facilita auditoria, suporte e analise de falha

### 9.5 Escalabilidade

- novos robos podem aproveitar a mesma base tecnica
- manutencao fica mais economica do que sustentar varios scripts isolados

## 10. Indicadores recomendados para o Lean da aplicacao

Para o Lean do produto inteiro, recomendo medir em dois niveis.

### 10.1 KPIs de negocio

- horas economizadas por mes
- ganho de produtividade por processo
- tempo medio de atendimento por demanda
- reducao de retrabalho
- volume mensal absorvido pela automacao

### 10.2 KPIs de produto

- numero de execucoes por modulo
- taxa de sucesso por modulo
- quantidade media processada por execucao
- numero de erros com evidencia registrada
- numero de usuarios ou areas atendidas

## 11. Formula de ganho consolidado da aplicacao

Para apresentar o ganho total da plataforma, some o ganho dos modulos ativos:

- `Horas economizadas no mes = soma das horas economizadas de cada modulo`
- `Produtividade global (%) = ((tempo manual total - tempo automatizado total) / tempo manual total) x 100`
- `Capacidade adicional = horas economizadas no mes / jornada media mensal`

Exemplo de estrutura de medicao:

| Macroprocesso | Volume mensal | Tempo manual medio | Tempo com aplicacao | Horas economizadas |
| --- | --- | --- | --- | --- |
| Gestao de ordens | `__` | `__` | `__` | `__` |
| Compras e pedidos | `__` | `__` | `__` | `__` |
| Consulta e relatorios SAP | `__` | `__` | `__` | `__` |
| Relatorios offline | `__` | `__` | `__` | `__` |
| Total da aplicacao | `__` | `__` | `__` | `__` |

## 12. Evidencias de maturidade da aplicacao

O repositorio mostra que a solucao nao e um script pontual. Ela ja tem elementos de produto:

- estrutura modular em `core/` e `panels/`
- configuracao central em `AppData`
- layout maps externos para absorver variacao do SAP
- testes automatizados em pontos criticos
- empacotamento e instalador
- documentacao operacional e de troubleshooting

Isso fortalece o Lean porque mostra sustentabilidade, replicabilidade e menor risco de dependencia de uma unica pessoa.

## 13. Riscos e limitacoes

Para manter a defesa honesta, o Lean deve citar as principais dependencias:

- depende de `SAP GUI` instalado e com `SAP GUI Scripting` habilitado
- alguns layouts podem variar por ambiente, exigindo override
- `IW28` ainda nao esta pronta e nao deve entrar no ganho realizado
- alguns fluxos ainda dependem de homologacao no ambiente alvo, como parte do `ME21N`
- o repositorio nao traz historico consolidado de tempo antes/depois, entao o ganho quantitativo precisa ser medido em campo

## 14. Sustentacao e implantacao

A aplicacao ja foi pensada para uso recorrente, nao apenas para desenvolvimento:

- build local automatizado
- empacotamento em executavel
- instalador para distribuicao
- configuracao fora do codigo
- pasta de saida padronizada
- diagnostico habilitavel por configuracao

No Lean, isso pode ser defendido como reducao do custo de suporte e aumento da confiabilidade operacional da automacao.

## 15. Texto pronto para usar no Lean

### 15.1 Versao curta

"A aplicacao Robos SAP centraliza automacoes operacionais e relatorios SAP em uma unica plataforma desktop. A solucao reduz tarefas repetitivas, padroniza execucoes, melhora a rastreabilidade e aumenta a produtividade da equipe ao substituir atividades manuais de baixo valor agregado por fluxos automatizados e auditaveis."

### 15.2 Versao completa

"O projeto Robos SAP foi desenvolvido para reduzir desperdicios operacionais em rotinas SAP de manutencao, compras e relatorios. Antes da aplicacao, as atividades eram executadas manualmente, com alto consumo de tempo, risco de erro de digitacao, dependencia de usuarios experientes e baixa rastreabilidade. A solucao entrega uma plataforma unica com modulos transacionais, consultas SAP e filtros offline, permitindo processamento em lote, geracao automatica de Excel e PDF, validacoes previas, logs de execucao e evidencias de falha. Como resultado, a aplicacao reduz lead time, retrabalho e esforco administrativo, aumentando a capacidade do time e criando uma base escalavel para novas automacoes no mesmo produto."

## 16. Como apresentar o ganho sem inventar numero

Se voce ainda nao tiver a medicao, apresente assim:

- ganho qualitativo ja comprovado: padronizacao, rastreabilidade, processamento em lote e reducao de toque manual
- ganho quantitativo em validacao: horas economizadas, produtividade e reducao de erro por modulo

Se a area pedir numero, use amostragem:

1. escolha 3 a 5 processos reais por modulo
2. cronometre o tempo manual
3. cronometre o tempo com a aplicacao
4. multiplique pelo volume mensal
5. consolide o ganho total da plataforma

## 17. Relacao com o guia por robo

Este documento e a visao Lean da aplicacao como produto.

Para detalhar o ganho por modulo individual, use tambem:

- `docs/lean-robos.md`

## 18. Conclusao

O Lean desta aplicacao pode ser defendido como uma iniciativa de transformacao operacional digital. O repositorio mostra uma plataforma unica, com varios modulos reutilizando a mesma base tecnica, para reduzir tempo, erro e retrabalho em operacoes SAP e relatorios. Em vez de enxergar apenas varios robos separados, o melhor enquadramento executivo e tratar a solucao como um produto interno de automacao com impacto direto em produtividade, governanca e escalabilidade.
