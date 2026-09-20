"""Client wrapping the upstream ReicheltAPI ``Reichelt`` object."""

from __future__ import annotations

import logging
from typing import Any

from .adapter import normalize_reichelt_payload
from .loader import DEFAULT_SOURCE_URL, get_reichelt_module

logger = logging.getLogger(__name__)


class ReicheltClient:
    """Fetches and normalizes product information from a Reichelt product page URL."""

    def __init__(self, *, module_source: str | None = None, timeout: int = 15):
        self.module_source = module_source or DEFAULT_SOURCE_URL
        self.timeout = timeout

    def fetch_product(self, part: str) -> dict[str, Any]:
        part = str(part).strip()

        if not part:
            raise ValueError("Product URL/Manufacturer part number is required")

        url = ""
        if part.startswith("https://www.reichelt.de/"):
            url = part

        module = get_reichelt_module(source=self.module_source, timeout=self.timeout)
        api = module.Reichelt()

        try:
            if url:
                raw = api.get_part_information(part)
            else:
                raw = api.search_part(part)
        except (
            Exception
        ) as exc:  # pragma: no cover - network/parsing errors from upstream lib
            logger.exception("ReicheltAPI request failed for %s", part)
            raise RuntimeError(
                f"Failed to fetch Reichelt product {part}: {exc}"
            ) from exc

        if not isinstance(raw, dict) or not raw.get("part"):
            raise RuntimeError(f"Reichelt returned no usable product data for {part}")

        return normalize_reichelt_payload(raw, source_url=part)
