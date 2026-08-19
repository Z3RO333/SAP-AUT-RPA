# SAP Automation / RPA Suite

Aplicação desktop desenvolvida para automatizar rotinas operacionais no SAP GUI, reduzindo atividades repetitivas e aumentando a rastreabilidade das execuções.

## Visão geral

O projeto utiliza **Python, Tkinter, pywin32 e SAP GUI Scripting** para automatizar diferentes fluxos de manutenção, compras e consulta dentro do SAP.

Além da automação em si, a solução foi estruturada com logs, screenshots de falha, tratamento de pop-ups, mapeamento externo de layouts e geração de artefatos de diagnóstico.

## Principais automações

- `IW32` — liberar, cancelar, concluir e classificar ordens
- `IW38` — consulta e processamento de ordens
- `ME2L` — consultas relacionadas a fornecedores
- `MB51` — movimentações de materiais
- `ME23N` — alimentação e consulta de pedidos
- `ME21N` — criação de pedidos
- Consulta offline de ordens em aberto

## Tecnologias

- Python
- Tkinter
- pywin32
- SAP GUI Scripting
- PyInstaller
- Inno Setup
- XLSX / automação baseada em planilhas

## Arquitetura

```text
core/common      Sessão SAP, waits, logs, screenshots e pop-ups
core/iw32        Automações relacionadas à IW32
core/me23n       Fluxos da ME23N
core/me21n       Criação de pedidos
core/reports     Relatórios e consultas
panels           Interface desktop em Tkinter
sap/layouts      Mapeamentos externos de IDs do SAP
scripts          Build e empacotamento
docs             Documentação operacional
```

## Observabilidade e diagnóstico

Cada execução pode gerar artefatos como:

- `run.log`
- `payload.json`
- `result.json`
- screenshots em caso de falha
- `popup_dump.json`

Esse modelo facilita auditoria, troubleshooting e evolução das automações.

## ME21N

O módulo de criação de pedidos possui modo guiado e processamento via planilha XLSX, incluindo suporte a múltiplos itens, múltiplas linhas de serviço, classificação contábil e configurações específicas por item.

## Objetivo técnico

Centralizar automações SAP em uma aplicação reutilizável e estruturada, reduzindo tarefas manuais, padronizando execuções e tornando falhas mais fáceis de identificar e diagnosticar.

## Segurança

Credenciais, dados internos, endpoints, parâmetros específicos do ambiente SAP e demais informações corporativas sensíveis não devem ser armazenados neste repositório ou na documentação pública.
