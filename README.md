# Robos SAP

Aplicativo desktop em `Python + Tkinter + pywin32` para automacoes SAP GUI Scripting com stack unica em Python.

## Requisitos

- Windows 10 ou 11
- SAP GUI instalado
- SAP GUI Scripting habilitado no cliente e no servidor
- Python 3.12 x86 para desenvolvimento

## Modulos

- `IW32` Liberar
- `IW32` Cancelar
- `IW32` Concluir
- `IW32` Categorias
- `IW38`
- `ME2L`
- `MB51`
- `ME23N` Alimentacao
- `ME21N` Criar Pedido
- Ferramenta offline de `Ordens em Aberto`

## Estrutura

- `core/common`: sessao SAP, waits, logs, screenshots, popups, layout maps
- `core/iw32`, `core/me23n`, `core/me21n`, `core/reports`: logica dos robos
- `panels`: UI Tkinter
- `sap/layouts`: mapeamentos externos de IDs
- `templates`: planilhas modelo
- `docs`: documentacao operacional
- `scripts`: build e empacotamento

## Como rodar localmente

```bash
python panels/menu-principal.py
```

## Build

```bash
python scripts/build.py
python scripts/package.py
```

O build principal gera um pacote `PyInstaller onedir`. O empacotamento final usa `Inno Setup`.

## Configuracao

O app procura `%AppData%\Robos SAP\config.json`.

Campos padrao:

```json
{
  "sapLogonPath": null,
  "outputRoot": "%USERPROFILE%\\Documents\\SAP Robots\\Saidas",
  "layoutOverridesDir": "%APPDATA%\\Robos SAP\\layouts",
  "defaultSessionSelection": "prompt",
  "diagnosticsEnabled": true
}
```

## Saidas

Cada execucao grava artefatos em `%USERPROFILE%\Documents\SAP Robots\Saidas\...`:

- `run.log`
- `payload.json`
- `result.json`
- screenshots em falha
- `popup_dump.json` quando aplicavel

## ME21N

O modulo `ME21N` agora tem `Modo Guiado` e `Modo Planilha XLSX`. O fluxo homologado desta entrega cobre pedido de servico com `categoria_item = D` e `categoria_classif = F` ou `K`, incluindo multiplos itens, multiplas linhas de servico, `tax_code` por item e referencia contabil por linha (`ordem` para `F`, `centro_custo` para `K`).

Defaults editaveis da UI ficam em `%AppData%\\Robos SAP\\me21n.defaults.json`. O profile base entregue esta em `sap/layouts/me21n.json`, mas ainda precisa de homologacao no ambiente SAP alvo.

Veja:

- `docs/me21n.md`
- `docs/layout-maps.md`
- `docs/troubleshooting.md`
