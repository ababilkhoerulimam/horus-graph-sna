"""Lapisan HTTP opsional. Butuh ekstra `pip install horus-graph[api]`."""

from __future__ import annotations

__all__ = ["AppState", "BundleNotFound", "create_app"]


def __getattr__(name: str):
    # Impor ditunda supaya `horus_graph` tetap bisa dipakai tanpa fastapi.
    if name == "create_app":
        from .app import create_app

        return create_app
    if name in ("AppState", "BundleNotFound"):
        from . import state

        return getattr(state, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
