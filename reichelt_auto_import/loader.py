"""Loads the upstream ``ReicheltAPI`` module (https://github.com/jkreucher/ReicheltAPI).

That project ships as a single GPLv3-licensed script rather than a package published to
PyPI, so it cannot simply be added as a normal pip dependency of this (MIT-licensed) plugin
without redistributing GPL-covered source inside this repository. Instead, this module loads
``reichelt.py`` at runtime - either from an already-installed/importable ``reichelt`` module
(if the operator placed one on ``PYTHONPATH`` themselves), a local file path, or the upstream
raw URL - without ever vendoring its source into this repository.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import threading
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_URL = (
    "https://raw.githubusercontent.com/jkreucher/ReicheltAPI/main/reichelt.py"
)

_lock = threading.Lock()
_cached_module: Any = None
_cached_source: str | None = None


def _load_installed_module():
    """Return an already-importable ``reichelt`` module, if one is available."""
    try:
        return importlib.import_module("reichelt")
    except ImportError:
        return None


def _load_module_from_source(source: str, *, timeout: int = 15):
    """Load the ``reichelt`` module from a local file path or a remote URL."""
    if source.startswith("http://") or source.startswith("https://"):
        response = requests.get(source, timeout=timeout)
        response.raise_for_status()
        source_code = response.text
    else:
        source_code = Path(source).expanduser().read_text(encoding="utf-8")

    spec = importlib.util.spec_from_loader("reichelt_api_external", loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source_code, source, "exec"), module.__dict__)  # noqa: S102 - trusted operator-configured source
    return module


def get_reichelt_module(
    *, source: str | None = None, timeout: int = 15, force_reload: bool = False
):
    """Return the (cached) upstream ``reichelt`` module, loading it on first use.

    Args:
        source: Local file path or URL to load ``reichelt.py`` from when it is not already
            importable. Defaults to the upstream GitHub raw URL.
        timeout: Timeout (seconds) used when fetching the module from a remote URL.
        force_reload: Ignore any cached module and reload it.
    """
    global _cached_module, _cached_source

    resolved_source = source or DEFAULT_SOURCE_URL

    with _lock:
        if (
            _cached_module is not None
            and not force_reload
            and _cached_source == resolved_source
        ):
            return _cached_module

        module = _load_installed_module()
        if module is None:
            module = _load_module_from_source(resolved_source, timeout=timeout)

        if not hasattr(module, "Reichelt"):
            raise RuntimeError("Loaded module does not expose a 'Reichelt' class")

        _cached_module = module
        _cached_source = resolved_source
        return module
