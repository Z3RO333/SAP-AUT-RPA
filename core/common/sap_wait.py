from __future__ import annotations

import time
from collections.abc import Callable


def wait(seconds: float = 0.3) -> None:
    time.sleep(seconds)


def wait_not_busy(session, timeout: float = 30.0, interval: float = 0.2) -> None:
    start = time.time()
    while time.time() - start < timeout:
        try:
            if not session.Busy:
                return
        except Exception:
            pass
        time.sleep(interval)
    raise TimeoutError("SAP permaneceu Busy alem do timeout.")


def retry_call(
    func: Callable[[], object],
    attempts: int = 5,
    base_delay: float = 0.25,
    multiplier: float = 1.8,
    max_delay: float = 3.0,
):
    delay = base_delay
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - COM specific
            last_error = exc
            time.sleep(delay)
            delay = min(delay * multiplier, max_delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_call falhou sem excecao")


def wait_for_element(session, element_id: str, timeout: float = 10.0, interval: float = 0.25):
    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < timeout:
        try:
            return session.findById(element_id)
        except Exception as exc:  # pragma: no cover - COM specific
            last_error = exc
            time.sleep(interval)
    raise TimeoutError(f"Elemento nao apareceu: {element_id}. Ultimo erro: {last_error}")

