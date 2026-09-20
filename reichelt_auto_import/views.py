"""API views for the ReicheltAutoImport plugin."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


def _get_plugin():
    from plugin.registry import registry

    return registry.get_plugin("reichelt-auto-import")


class ImportAPIView(APIView):
    """Import a single Reichelt part from a product page URL ("code").

    POST body:
        ``code`` (str, required): the Reichelt product page URL.
        ``quantity`` (number, optional): stock quantity to add. Defaults to ``1``.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        code = (request.data or {}).get("code") or (request.data or {}).get("url")
        if not code:
            return Response(
                {"error": "Field 'code' (Reichelt product URL) is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        quantity_value = (request.data or {}).get("quantity", 1)
        try:
            quantity = (
                Decimal(str(quantity_value))
                if quantity_value not in (None, "")
                else Decimal(1)
            )
        except InvalidOperation:
            return Response(
                {"error": "Field 'quantity' must be numeric"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plugin = _get_plugin()
        if plugin is None:
            return Response(
                {"error": "ReicheltAutoImport plugin is not enabled"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            result = plugin.import_reichelt_code(
                code, quantity=quantity, user=request.user
            )
        except ValidationError as exc:
            return Response(
                {"error": "; ".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as exc:  # pragma: no cover - exercised via integration tests
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        part = result["part"]
        return Response(
            {
                "result": result["result"],
                "sku": result["sku"],
                "part": part.pk,
                "part_name": part.name,
                "supplier_part": result["supplier_part"].pk,
                "unit_price": str(result["unit_price"])
                if result["unit_price"] is not None
                else None,
                "price_breaks": [
                    {"quantity": str(pb.quantity), "price": str(pb.price)}
                    for pb in result["price_breaks"]
                ],
                "stock_item": result["stock_item"].pk if result["stock_item"] else None,
            },
            status=status.HTTP_200_OK,
        )
