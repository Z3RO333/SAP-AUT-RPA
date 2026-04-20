# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos essenciais

```bash
# Rodar o menu principal (ponto de entrada)
python panels/menu-principal.py

# Rodar um panel diretamente (sem passar pelo menu)
python panels/zme62-avaliacao-panel.py
python panels/iw32-categorias-panel.py

# Rodar todos os testes (sem SAP, sem COM)
python -m pytest tests/

# Rodar um teste específico
python -m pytest tests/test_iw32_categorias.py

# Build PyInstaller (onedir)
python scripts/build.py

# Empacotamento Inno Setup
python scripts/package.py
```

> Requisito: Python 3.12 x86 no Windows. O COM do SAP GUI Scripting é 32-bit.

---

## Arquitetura

Três camadas fixas, sempre nessa direção:

```
panels/                   ← UI Tkinter, threading, queue
    ↓ chama run_job()
core/<modulo>/            ← lógica de negócio, orquestração por item
    ↓ usa
core/common/              ← SAP COM, logging, modelos, runtime
    ↓ lê
sap/layouts/<tx>.json     ← IDs SAP por transação e profile
```

Cada panel roda como **subprocesso separado** lançado pelo menu principal via `subprocess.Popen`. A comunicação UI ↔ core é via `queue.Queue` com polling a cada 200ms (`root.after(200, _poll_queue)`).

---

## Padrão de módulo core

Todo robô expõe exatamente:

```python
def run_job(input_data: dict, options: dict, callbacks: dict) -> RobotResult:
```

Sequência canônica dentro de `run_job`:

1. `pythoncom.CoInitialize()`
2. Cria `output_dir`, `ExecutionLogger`, `RunContext`, `RobotResult`
3. Escreve `payload.json` em disco
4. Carrega profile via `load_layout_map()` + `resolve_profile()`
5. `resolve_session()` — conecta ao SAP
6. Loop por item: `context.progress()` → automação → captura erro individual sem parar o lote
7. `finally`: `result.finalize()`, escreve `result.json`, `pythoncom.CoUninitialize()`

Erros por item nunca interrompem o lote. Erros fatais (ex: sem sessão SAP) vão para o `except` externo e definem `result.status = "error"`.

---

## Padrão de panel

```python
from _panel_utils import ensure_repo_root
ensure_repo_root()  # sempre primeira chamada — garante core/ no sys.path

class MeuPanel:
    def __init__(self, root):
        self.result_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.is_running = False
        self._poll_queue()  # inicia polling

    def _run(self, input_data):           # roda em thread daemon
        result = run_job(input_data, options, callbacks)
        self.result_queue.put(("success", result.to_dict()))

    def _poll_queue(self):                # processa log/progress/success/error
        ...
        self.root.after(200, self._poll_queue)
```

---

## Layout maps (`sap/layouts/*.json`)

Cada valor de campo/botão é **lista de candidatos** — o código tenta cada um em ordem até encontrar. Nunca hardcode um ID SAP no Python.

```json
{
  "transaction": "ZME62",
  "defaultProfile": "standard",
  "profiles": {
    "standard": {
      "fields": { "fornecedor": ["wnd[0]/usr/ctxtGV_FORNECEDOR"] },
      "buttons": { "salvar": ["wnd[0]/tbar[0]/btn[11]"] },
      "grid": { "container": ["wnd[0]/usr/cntlGC_CONTAINER_AVALIACAO/shellcont/shell"], "responseColumn": "VALOR_OBTIDO" }
    }
  }
}
```

Override por usuário em `%AppData%\Robos SAP\layouts\<tx>.json` tem prioridade sobre `sap/layouts/`.

---

## Camada SAP (`core/common/`)

| Arquivo | O que faz |
|---|---|
| `sap_session.py` | `resolve_session()` — conecta via COM, múltiplas sessões → chooser |
| `sap_actions.py` | `set_text`, `press`, `send_vkey`, `tcode`, `first_existing` com retry |
| `sap_wait.py` | `wait`, `wait_not_busy`, `retry_call` com backoff exponencial |
| `sap_popups.py` | `popup_exists`, `close_popup_ok`, `dump_popup` |
| `sap_status.py` | `read_statusbar(session) → (text, type)` — `"E"` = erro SAP |
| `layout_maps.py` | `load_layout_map(tx)`, `resolve_profile(map, name)` |
| `run_context.py` | `RunContext` — logger + callbacks + artifacts + errors |
| `models.py` | `RobotResult`, `RunArtifact`, `StatusMessage`, `SessionMeta` |
| `runtime.py` | `run_output_dir()`, `timestamp_id()`, `ensure_dir()` |

**Padrão de validação pós-ação SAP:**
```python
status_text, status_type = read_statusbar(session)
if status_type == "E":
    raise RuntimeError(status_text)
```

---

## Saídas de execução

Cada `run_job` grava em `%USERPROFILE%\Documents\SAP Robots\Saidas\<Robo>\<key>\<timestamp>\`:
- `run.log` — log técnico linha a linha
- `payload.json` — input normalizado
- `result.json` — `RobotResult` completo com `business_result`
- `erro-<id>.png` — screenshot em falha
- `popup-<id>.json` — dump da janela SAP em falha

---

## Testes

Os testes não precisam de SAP — mockam `session` com `unittest.mock.Mock`. Rodam com `pytest` a partir da raiz. Para adicionar testes de um novo módulo, siga o padrão de `tests/test_iw32_categorias.py`.

---

## Adicionar novo robô (checklist)

1. `sap/layouts/<tx>.json` — IDs como listas de candidatos
2. `core/<tx>/__init__.py` — vazio
3. `core/<tx>/avaliacao.py` (ou nome do domínio) — `run_job()`
4. `panels/<tx>-panel.py` — UI com threading + queue
5. Entrada no dicionário `APPS` em `panels/menu-principal.py`
