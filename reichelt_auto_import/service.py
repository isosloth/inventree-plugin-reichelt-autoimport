"""Creates/updates InvenTree Parts, SupplierParts and Parameters from a normalized Reichelt product."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.models import Parameter, ParameterTemplate
from company.models import Company, SupplierPart, SupplierPriceBreak
from part.models import Part, PartCategory, PartCategoryParameterTemplate
from stock.models import StockItem, StockLocation


class ReicheltImportError(RuntimeError):
    pass


def get_default_supplier() -> Company | None:
    return Company.objects.filter(is_supplier=True, name__icontains="Reichelt").first()


def resolve_reichelt_supplier(supplier: Company | int | str | None) -> Company | None:
    if supplier is None:
        return get_default_supplier()
    if isinstance(supplier, Company):
        return supplier
    if isinstance(supplier, int):
        return Company.objects.filter(pk=supplier, is_supplier=True).first()
    if isinstance(supplier, str):
        supplier = supplier.strip()
        if not supplier:
            return get_default_supplier()
        return Company.objects.filter(
            is_supplier=True, name__icontains=supplier
        ).first()
    return None


def ensure_category_path(
    category_path: str, *, parent: PartCategory | None = None
) -> PartCategory:
    """Create (or fetch) the full category tree for a slash-separated path."""
    path = [
        segment.strip()
        for segment in category_path.split("/")
        if segment and segment.strip()
    ]
    if not path:
        raise ValueError("Category path is empty")

    current = parent
    for segment in path:
        current, _created = PartCategory.objects.get_or_create(
            name=segment, parent=current
        )
    return current


def create_or_update_parameter(
    part: Part, parameter_id: str, display_name: str, value: Any
) -> ParameterTemplate:
    """Create/update a part parameter using a stable ``parameter_id`` as the template name."""
    parameter_id = (parameter_id or "").strip() or "PARAM"
    display_name = (display_name or "").strip() or parameter_id

    template, created = ParameterTemplate.objects.get_or_create(
        name=parameter_id,
        defaults={"description": display_name},
    )
    if not created and display_name and template.description != display_name:
        template.description = display_name
        template.save(update_fields=["description"])

    if not PartCategoryParameterTemplate.objects.filter(
        category=part.category, template=template
    ).exists():
        PartCategoryParameterTemplate.objects.get_or_create(
            category=part.category,
            template=template,
            defaults={"default_value": ""},
        )

    existing = part.parameters_list.filter(template=template).first()
    if existing:
        existing.data = str(value)
        existing.save(update_fields=["data"])
    else:
        Parameter.objects.create(
            model_type=part.get_content_type(),
            model_id=part.pk,
            template=template,
            data=str(value),
        )
    return template


def _sync_price_breaks(
    supplier_part: SupplierPart,
    price_breaks: list[dict[str, Any]] | None,
    *,
    currency: str = "EUR",
) -> list[SupplierPriceBreak]:
    if not price_breaks:
        return []

    synced: list[SupplierPriceBreak] = []
    for entry in price_breaks:
        quantity = entry.get("quantity")
        price = entry.get("price")
        if quantity is None or price is None:
            continue
        price_break, _created = SupplierPriceBreak.objects.update_or_create(
            part=supplier_part,
            quantity=quantity,
            defaults={"price": price, "price_currency": currency},
        )
        synced.append(price_break)
    return synced


def _add_stock(
    part: Part,
    supplier_part: SupplierPart,
    quantity: Decimal | None,
    stock_location,
    purchase_price,
) -> StockItem | None:
    if quantity is None:
        return None
    location = StockLocation.objects.filter(
        pk=getattr(stock_location, "pk", stock_location)
    ).first()
    if location is None:
        raise ReicheltImportError(
            "Configure a Default Stock Location before importing stock quantity"
        )
    stock_item = (
        StockItem.objects.filter(part=part, location=location).order_by("pk").first()
    )
    if stock_item is None:
        return StockItem.objects.create(
            part=part,
            supplier_part=supplier_part,
            location=location,
            quantity=quantity,
            purchase_price=purchase_price,
        )
    stock_item.quantity += quantity
    stock_item.purchase_price = purchase_price
    stock_item.save()
    return stock_item


def import_reichelt_product(
    product: dict[str, Any],
    *,
    supplier: Company | int | str | None,
    category_path: str | None = None,
    quantity: Decimal | None = None,
    stock_location=None,
) -> dict[str, Any]:
    """Create or update a Part and SupplierPart for a normalized Reichelt product payload."""
    if not isinstance(product, dict):
        raise ReicheltImportError("Product payload is not a dictionary")

    supplier_obj = resolve_reichelt_supplier(supplier)
    if supplier_obj is None:
        raise ReicheltImportError("No Reichelt supplier company configured")

    sku = str(product.get("sku") or "").strip()
    if not sku:
        raise ReicheltImportError("Reichelt product payload is missing a part number")

    resolved_category_path = category_path or "Uncategorized"
    category = ensure_category_path(resolved_category_path)

    supplier_part = (
        SupplierPart.objects.filter(SKU=sku, supplier=supplier_obj)
        .select_related("part")
        .first()
    )
    part = supplier_part.part if supplier_part else None

    if part is None:
        part = Part.objects.create(
            name=product.get("name") or sku,
            description=product.get("name") or "",
            category=category,
            purchaseable=True,
            component=True,
            active=True,
            link=product.get("url") or None,
        )
        create_result = "created"
    else:
        part.name = product.get("name") or part.name
        part.category = category
        part.link = product.get("url") or part.link
        part.save(update_fields=["name", "category", "link"])
        create_result = "updated"

    if supplier_part is None:
        supplier_part = SupplierPart.objects.create(
            SKU=sku,
            supplier=supplier_obj,
            part=part,
            link=product.get("url") or None,
        )
    else:
        supplier_part.part = part
        supplier_part.link = product.get("url") or supplier_part.link
        supplier_part.save(update_fields=["part", "link"])

    for parameter in product.get("parameters") or []:
        create_or_update_parameter(
            part, parameter.get("id"), parameter.get("name"), parameter.get("value")
        )

    if product.get("availability"):
        create_or_update_parameter(
            part, "AVAILABILITY", "Availability", product["availability"]
        )

    for index, datasheet_url in enumerate(product.get("datasheets") or []):
        suffix = "" if index == 0 else f" {index + 1}"
        create_or_update_parameter(
            part,
            f"DATASHEET{suffix}".replace(" ", "_").upper(),
            f"Datasheet{suffix}",
            datasheet_url,
        )

    price_breaks = _sync_price_breaks(
        supplier_part,
        product.get("price_breaks"),
        currency=product.get("price_currency") or "EUR",
    )

    unit_price = product.get("unit_price")
    stock_item = _add_stock(part, supplier_part, quantity, stock_location, unit_price)

    part.tags.add(f"reichelt:{sku}")

    return {
        "result": create_result,
        "sku": sku,
        "part": part,
        "supplier_part": supplier_part,
        "price_breaks": price_breaks,
        "unit_price": unit_price,
        "stock_item": stock_item,
    }
