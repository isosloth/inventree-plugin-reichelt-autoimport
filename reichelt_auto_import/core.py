"""Imports Parts from Reichelt"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from plugin import InvenTreePlugin
from plugin.mixins import BarcodeMixin, SettingsMixin, UrlsMixin, UserInterfaceMixin

from . import PLUGIN_VERSION
from .client import ReicheltClient
from .loader import DEFAULT_SOURCE_URL
from .service import import_reichelt_product, resolve_reichelt_supplier

logger = logging.getLogger(__name__)


class ReicheltAutoImport(
    BarcodeMixin, SettingsMixin, UrlsMixin, UserInterfaceMixin, InvenTreePlugin
):
    """ReicheltAutoImport - custom InvenTree plugin."""

    # Plugin metadata
    TITLE = "Reichelt Auto Import"
    NAME = "ReicheltAutoImport"
    SLUG = "reichelt-auto-import"
    DESCRIPTION = "Imports Parts from Reichelt"
    VERSION = PLUGIN_VERSION

    # Additional project information
    AUTHOR = "Isosloth"
    WEBSITE = "https://github.com/isosloth/inventree-plugin-reichelt-autoimport"
    LICENSE = "MIT"

    # Render custom UI elements to the plugin settings page
    ADMIN_SOURCE = "Settings.js:RenderPluginSettings"

    # A Reichelt product page URL, e.g. https://www.reichelt.com/de/en/shop/product/...
    REICHELT_URL_RE = re.compile(
        r"https?://(?:www\.)?reichelt\.(?:com|de)/\S+", re.IGNORECASE
    )

    # Plugin settings (from SettingsMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/settings/
    SETTINGS = {
        "REICHELT_SUPPLIER_ID": {
            "name": "Reichelt Supplier",
            "description": "The supplier company record used for Reichelt parts",
            "model": "company.company",
            "model_filters": {"is_supplier": True},
        },
        "CATEGORY_ROOT_PATH": {
            "name": "Category Root Path",
            "description": "All Reichelt categories are created below this InvenTree category path",
            "default": "Electronics/Reichelt",
        },
        "DEFAULT_CATEGORY_PATH": {
            "name": "Default Category Path",
            "description": "Fallback category name, relative to Category Root Path, when Reichelt reports no category",
            "default": "Uncategorized",
        },
        "MODULE_SOURCE": {
            "name": "ReicheltAPI Module Source",
            "description": (
                "Local file path or URL used to load the upstream ReicheltAPI 'reichelt.py' "
                "module (https://github.com/jkreucher/ReicheltAPI) when it is not already "
                "importable in this environment. Defaults to the project's GitHub raw URL."
            ),
            "default": DEFAULT_SOURCE_URL,
        },
        "DEFAULT_STOCK_LOCATION": {
            "name": "Default Stock Location",
            "description": (
                "Fallback location used when importing a quantity and the user has not "
                "chosen their own location (see the user's account settings for a per-user "
                "override)"
            ),
            "model": "stock.stocklocation",
        },
        "TIMEOUT_SECONDS": {
            "name": "Timeout Seconds",
            "description": "Request timeout in seconds when fetching product data",
            "default": 15,
        },
    }

    USER_SETTINGS = {
        "DEFAULT_STOCK_LOCATION": {
            "name": "Default Stock Location",
            "description": "Location used when importing a Reichelt part with a quantity",
            "model": "stock.stocklocation",
        },
    }

    # Custom URL endpoints (from UrlsMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/urls/
    def setup_urls(self):
        """Configure custom URL endpoints for this plugin.

        Note: `URLS` (as a plain list of strings) is *not* supported here - UrlsMixin treats
        that class attribute as a ready-made list of URL patterns (e.g. from `path()`), not
        as dotted module paths to `include()`. Overriding `setup_urls()` and using `include()`
        explicitly is required to mount a whole `urls.py` module.
        """
        from django.urls import include, path

        return [
            path("", include("reichelt_auto_import.urls")),
        ]

    def _get_supplier(self):
        supplier_id = self.get_setting("REICHELT_SUPPLIER_ID")
        supplier = resolve_reichelt_supplier(supplier_id)
        if supplier is not None:
            return supplier
        return resolve_reichelt_supplier("Reichelt")

    def _category_path_for_product(self, category_chain: list[str] | None) -> str:
        root_path = self.get_setting("CATEGORY_ROOT_PATH") or "Electronics/Reichelt"
        if category_chain:
            return "/".join([root_path, *category_chain])
        default = self.get_setting("DEFAULT_CATEGORY_PATH") or "Uncategorized"
        return "/".join([root_path, default])

    def _stock_location(self, user=None):
        if user is not None and getattr(user, "is_authenticated", False):
            user_location = self.get_user_setting("DEFAULT_STOCK_LOCATION", user)
            if user_location:
                return user_location
        return self.get_setting("DEFAULT_STOCK_LOCATION")

    def _client(self) -> ReicheltClient:
        return ReicheltClient(
            module_source=self.get_setting("MODULE_SOURCE") or DEFAULT_SOURCE_URL,
            timeout=int(self.get_setting("TIMEOUT_SECONDS") or 15),
        )

    def import_reichelt_code(self, code: str, *, quantity=None, user=None):
        """Import a Reichelt product from a "code" (its product page URL).

        ``quantity`` defaults to 1 when not provided.
        """
        code = str(code or "").strip()
        if not code:
            raise ValidationError("A Reichelt product URL is required")

        match = self.REICHELT_URL_RE.search(code)
        url = match.group(0) if match else code

        supplier = self._get_supplier()
        if supplier is None:
            raise ValidationError("No Reichelt supplier company could be resolved")

        if quantity is None:
            quantity = Decimal(1)
        elif not isinstance(quantity, Decimal):
            try:
                quantity = Decimal(str(quantity))
            except InvalidOperation as exc:
                raise ValidationError("Quantity must be numeric") from exc

        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero")

        product = self._client().fetch_product(url)
        category_path = self._category_path_for_product(product.get("category_chain"))

        return import_reichelt_product(
            product,
            supplier=supplier,
            category_path=category_path,
            quantity=quantity,
            stock_location=self._stock_location(user),
        )

    def scan(self, barcode_data: str, user, **kwargs):
        """Auto-import a Reichelt part when a scanned barcode contains a product URL."""
        if not isinstance(barcode_data, str):
            return None

        match = self.REICHELT_URL_RE.search(barcode_data.strip())
        if not match:
            return None

        url = match.group(0)
        try:
            result = self.import_reichelt_code(url, user=user)
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            logger.exception("Reichelt scan auto-import failed for %s", url)
            return {"error": str(exc)}

        part = result["part"]
        return {
            "part": part.format_matched_response(user=user),
            "success": "Found matching Reichelt part",
            "sku": result["sku"],
            "supplierpart": {"pk": result["supplier_part"].pk},
            "stock_item": result["stock_item"].pk if result["stock_item"] else None,
        }

    # User interface elements (from UserInterfaceMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/ui/
    def get_ui_dashboard_items(self, request, context: dict, **kwargs):
        """Return a list of custom dashboard items to be rendered in the InvenTree user interface."""
        if not request.user or not request.user.is_staff:
            return []

        return [
            {
                "key": "reichelt-auto-import-dashboard",
                "title": "Reichelt Auto Import",
                "description": "Import a Reichelt part by product URL",
                "icon": "ti:download:outline",
                "source": self.plugin_static_file(
                    "Dashboard.js:RenderReicheltAutoImportDashboardItem"
                ),
                "context": {
                    "settings": self.get_settings_dict(),
                },
            }
        ]
