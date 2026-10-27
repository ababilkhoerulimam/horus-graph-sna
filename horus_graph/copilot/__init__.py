"""
Copilot opsional: tanya-jawab di atas `AppState`.

Dua jalur, satu set tool:

1. LLM dengan tool calling, bila `HORUS_LLM_BASE_URL` dan `HORUS_LLM_MODEL`
   diisi dan paket `openai` terpasang (ekstra `[llm]`).
2. Jawaban deterministik dari `fallback.py`, yang memakai tool yang sama dan
   merakit kalimat dari `presentation.wording`.

Karena keduanya berbagi tool, angka yang disebut copilot selalu sama dengan
angka di visualizer, terlepas dari jalur mana yang aktif.
"""

from .llm import LLMUnavailable, llm_available
from .service import Copilot, get_copilot

__all__ = ["Copilot", "get_copilot", "llm_available", "LLMUnavailable"]
