"""Normalizes raw payloads returned by the upstream ReicheltAPI's ``get_part_information``."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

# Reichelt breadcrumbs always start with a generic "Home" entry which is not useful as a
# category name in InvenTree.
_IGNORED_CATEGORY_SEGMENTS = {"home"}


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _normalize_parameter_name(name: Any) -> str:
    text = _clean_text(name)
    if not text:
        return ""
    text = text.replace("_", " ").replace("-", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.title()


def _slugify_key(name: Any) -> str:
    """Build a stable, uppercase parameter key from a human-readable name."""
    text = _clean_text(name).upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text or "PARAM"


def parse_price_breaks(price: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract ``{quantity, price}`` price breaks from a Reichelt ``price`` object.

    The upstream API reports tiers under numeric-string keys (``"1"``, ``"10"``, ``"100"``,
    ``"1000"``) alongside a ``"currency"`` key; missing tiers are reported as ``None``.
    """
    if not isinstance(price, dict):
        return []

    breaks: list[dict[str, Any]] = []
    for key, value in price.items():
        if key == "currency":
            continue
        quantity = _to_decimal(key)
        unit_price = _to_decimal(value)
        if quantity is None or unit_price is None:
            continue
        breaks.append({"quantity": quantity, "price": unit_price})

    breaks.sort(key=lambda entry: entry["quantity"])
    return breaks


def parse_parameters(data: dict[str, Any] | None) -> list[dict[str, str]]:
    """Flatten Reichelt's ``data`` (category -> {name: value}) into a parameter list."""
    parameters: list[dict[str, str]] = []
    if not isinstance(data, dict):
        return parameters

    for category, attributes in data.items():
        if not isinstance(attributes, dict):
            continue
        for name, value in attributes.items():
            display_name = _normalize_parameter_name(name)
            if not display_name:
                continue
            parameters.append({
                "id": _slugify_key(name),
                "name": display_name,
                "value": _clean_text(value),
                "group": _clean_text(category),
            })
    return parameters


def parse_category_chain(categories: list[Any] | None) -> list[str]:
    chain: list[str] = []
    for entry in categories or []:
        text = _clean_text(entry)
        if text and text.lower() not in _IGNORED_CATEGORY_SEGMENTS:
            chain.append(text)
    return chain


def normalize_reichelt_payload(
    raw: dict[str, Any], *, source_url: str | None = None
) -> dict[str, Any]:
    """Convert the raw ``get_part_information`` result into a normalized product payload."""
    if not isinstance(raw, dict):
        raise ValueError("Reichelt payload must be a dictionary")

    price_breaks = parse_price_breaks(raw.get("price"))
    unit_price = next(
        (entry["price"] for entry in price_breaks if entry["quantity"] == 1), None
    )

    return {
        "sku": _clean_text(raw.get("part")),
        "name": _clean_text(raw.get("name")),
        "url": _clean_text(raw.get("url")) or _clean_text(source_url),
        "availability": _clean_text(raw.get("availability")),
        "price_currency": _clean_text((raw.get("price") or {}).get("currency"))
        or "EUR",
        "unit_price": unit_price,
        "price_breaks": price_breaks,
        "datasheets": [
            _clean_text(url)
            for url in (raw.get("datasheets") or [])
            if _clean_text(url)
        ],
        "parameters": parse_parameters(raw.get("data")),
        "category_chain": parse_category_chain(raw.get("categories")),
    }
