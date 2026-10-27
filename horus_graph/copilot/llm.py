"""
Klien LLM opsional.

Copilot tetap menjawab tanpa modul ini: `service.py` jatuh ke jalur
deterministik yang memakai tool yang sama. Yang dibutuhkan hanyalah gateway
yang kompatibel dengan OpenAI Chat Completions; nama model tidak pernah ditulis
di kode karena setiap pemasangan memakai model yang berbeda.

Konfigurasi lewat lingkungan:

    HORUS_LLM_BASE_URL   mis. http://127.0.0.1:20130/v1
    HORUS_LLM_MODEL      nama model di gateway tersebut
    HORUS_LLM_API_KEY    opsional, default "local"
    HORUS_LLM_TEMPERATURE opsional, default 0.2
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

BASE_URL_ENV = "HORUS_LLM_BASE_URL"
API_KEY_ENV = "HORUS_LLM_API_KEY"
MODEL_ENV = "HORUS_LLM_MODEL"
TEMPERATURE_ENV = "HORUS_LLM_TEMPERATURE"
DEFAULT_TEMPERATURE = 0.2


class LLMUnavailable(RuntimeError):
    """Gateway LLM belum dikonfigurasi atau paket `openai` belum terpasang."""


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float


def config() -> Optional[LLMConfig]:
    """Konfigurasi aktif, atau `None` bila gateway belum diarahkan."""
    base_url = (os.environ.get(BASE_URL_ENV) or "").strip()
    model = (os.environ.get(MODEL_ENV) or "").strip()
    if not base_url or not model:
        return None
    try:
        temperature = float(os.environ.get(TEMPERATURE_ENV) or DEFAULT_TEMPERATURE)
    except ValueError:
        temperature = DEFAULT_TEMPERATURE
    return LLMConfig(
        base_url=base_url,
        api_key=(os.environ.get(API_KEY_ENV) or "local").strip(),
        model=model,
        temperature=temperature,
    )


def llm_available() -> bool:
    """True hanya bila gateway diarahkan dan SDK-nya benar-benar bisa diimpor."""
    if config() is None:
        return False
    try:
        import openai  # noqa: F401
    except ImportError:
        return False
    return True


_client: Any = None


def get_client() -> Any:
    global _client
    cfg = config()
    if cfg is None:
        raise LLMUnavailable(
            f"{BASE_URL_ENV} dan {MODEL_ENV} belum diisi; memakai jawaban deterministik."
        )
    if _client is None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - tergantung pemasangan
            raise LLMUnavailable(
                "Paket `openai` belum terpasang. Pasang dengan: pip install 'horus-graph[llm]'"
            ) from exc
        _client = AsyncOpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
    return _client


async def call_llm(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
) -> Any:
    """Satu panggilan Chat Completions; mengembalikan respons mentah SDK."""
    cfg = config()
    if cfg is None:
        raise LLMUnavailable("Gateway LLM belum dikonfigurasi.")
    client = get_client()
    return await client.chat.completions.create(
        model=model or cfg.model,
        messages=messages,
        tools=tools,
        temperature=cfg.temperature if temperature is None else temperature,
    )


def reset_client() -> None:
    """Untuk pengujian: paksa klien dibangun ulang setelah env berubah."""
    global _client
    _client = None
