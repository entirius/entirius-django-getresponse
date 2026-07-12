# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass

# Status mapping from django_checkout to GetResponse
STATUS_MAP = {
    "new": "PENDING",
    "unpaid": "PENDING",
    "confirmed": "PROCESSING",
    "holded": "PROCESSING",
    "in_progress": "PROCESSING",
    "complete": "COMPLETED",
    "returned": "CANCELLED",
    "canceled": "CANCELLED",
}


@dataclass
class GetResponseOrderDTO:
    contact_id: str
    external_id: str
    total_price: float
    currency: str
    status: str
    processed_at: str
    selected_variants: list[dict]
    billing_address: dict | None = None
    shipping_address: dict | None = None

    def __post_init__(self):
        self._validate_contact_id()
        self._validate_external_id()
        self._validate_total_price()
        self._validate_currency()
        self._validate_status()

    def _validate_contact_id(self):
        if not self.contact_id:
            raise ValueError("contact_id is required")

    def _validate_external_id(self):
        if not self.external_id or len(self.external_id) > 255:
            raise ValueError("external_id required, max 255 chars")

    def _validate_total_price(self):
        if self.total_price < 0:
            raise ValueError("total_price must be >= 0")

    def _validate_currency(self):
        if not self.currency or len(self.currency) != 3:
            raise ValueError("currency must be 3-char ISO code")

    def _validate_status(self):
        valid_statuses = ["PENDING", "PROCESSING", "COMPLETED", "CANCELLED", "SHIPPED"]
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}")

    def to_create_payload(self) -> dict:
        """Generate payload for POST /shops/{shopId}/orders."""
        data = self._build_base_dict()
        return self._filter_none_values(data)

    def to_update_payload(self) -> dict:
        """Generate payload for POST /shops/{shopId}/orders/{orderId} (status update)."""
        return {"status": self.status}

    def _build_base_dict(self) -> dict:
        return {
            "contactId": self.contact_id,
            "externalId": self.external_id,
            "totalPrice": self.total_price,
            "currency": self.currency,
            "status": self.status,
            "processedAt": self.processed_at,
            "selectedVariants": self.selected_variants,
            "billingAddress": self.billing_address,
            "shippingAddress": self.shipping_address,
        }

    def _filter_none_values(self, data: dict) -> dict:
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_order(cls, order, contact_id: str, shop):
        """Create DTO from django_checkout.Order instance."""
        order_data = cls._extract_order_data(order)
        variants = cls._build_variants_from_order(order, shop)
        billing_address = cls._build_billing_address(order)
        shipping_address = cls._build_shipping_address(order)

        return cls(
            contact_id=contact_id,
            external_id=str(order.order_id),
            total_price=float(order_data["total"]),
            currency=order_data["currency"],
            status=cls._map_status_to_gr(order.order_status),
            processed_at=order_data["processed_at"],
            selected_variants=variants,
            billing_address=billing_address,
            shipping_address=shipping_address,
        )

    @classmethod
    def _extract_order_data(cls, order) -> dict:
        order_data = order.as_data
        # Format: Y-m-d\TH:i:sO (e.g., 2026-01-29T13:59:12+0000)
        processed_at = order.created.strftime("%Y-%m-%dT%H:%M:%S%z")
        return {
            "total": order_data.total,
            "currency": order_data.currency_code or "PLN",
            "processed_at": processed_at,
        }

    @staticmethod
    def _map_status_to_gr(order_status: str) -> str:
        """Map django_checkout order status to GetResponse status."""
        return STATUS_MAP.get(order_status, "PENDING")

    @staticmethod
    def _convert_country_code(code: str) -> str:
        """Convert ISO 3166-1 alpha-2 to alpha-3 country code.

        Uses django_regional.models.Country to lookup ISO3 code from database.

        Args:
            code: 2-letter country code (e.g., 'PL')

        Returns:
            3-letter country code (e.g., 'POL')
        """
        if not code:
            return "POL"

        try:
            from django_regional.models import Country

            country = Country.objects.get(iso2__iexact=code)
            return country.iso3
        except Country.DoesNotExist:
            return code.upper()
        except Exception:
            return code.upper()

    @staticmethod
    def _build_full_name(firstname: str, lastname: str) -> str:
        """Build full name from first and last name.

        Args:
            firstname: First name (can be empty)
            lastname: Last name (can be empty)

        Returns:
            Combined full name or 'N/A' if both empty
        """
        return f"{firstname} {lastname}".strip() or "N/A"

    @staticmethod
    def _safe_get_attr(obj, attr: str, default: str = "") -> str:
        """Safely get attribute from object with default fallback.

        Args:
            obj: Object to get attribute from
            attr: Attribute name
            default: Default value if attribute doesn't exist

        Returns:
            Attribute value or default
        """
        return getattr(obj, attr, default) if hasattr(obj, attr) else default

    @classmethod
    def _build_variants_from_order(cls, order, shop) -> list[dict]:
        """Build selectedVariants array from order items.

        Raises:
            ValueError: If no valid variants can be built (GetResponse requires at least one).
        """

        items = order.as_data.cart.items
        variants = []
        for item in items:
            variant_dict = cls._build_variant_dict(item, shop)
            if variant_dict:
                variants.append(variant_dict)

        if not variants:
            raise ValueError(
                f"No synced products found for order {order.order_id}. "
                "All order items must have corresponding synced products in GetResponse."
            )

        return variants

    @classmethod
    def _build_variant_dict(cls, item, shop) -> dict | None:
        """Build single variant dict with GR variant ID.

        Lookup priority:
        1. Direct match: ProductSync where product.real_product.sku == item.sku
        2. Variant match: ProductSync whose last_response_data.variants contains item.sku
        """
        from django_getresponse.models import ProductSync

        # 1. Direct match (item is the synced product itself)
        product_sync = (
            ProductSync.objects.select_related("product")
            .filter(shop=shop, product__real_product__sku=item.sku, sync_status="synced")
            .first()
        )

        if product_sync:
            gr_variant_id = cls._extract_gr_variant_id(product_sync, item.sku)
            if gr_variant_id:
                return cls._format_variant(gr_variant_id, item)

        # 2. Variant match (item is a simple linked to a configurable)
        product_sync = ProductSync.objects.filter(
            shop=shop,
            sync_status="synced",
            last_response_data__variants__contains=[{"sku": item.sku}],
        ).first()

        if product_sync:
            gr_variant_id = cls._extract_gr_variant_id(product_sync, item.sku)
            if gr_variant_id:
                return cls._format_variant(gr_variant_id, item)

        return None

    @staticmethod
    def _format_variant(gr_variant_id: str, item) -> dict:
        return {
            "variantId": gr_variant_id,
            "price": float(item.unit_price),
            "priceTax": (
                float(item.unit_price_tax) if hasattr(item, "unit_price_tax") and item.unit_price_tax else 0.0
            ),
            "quantity": int(item.quantity),
        }

    @staticmethod
    def _extract_gr_variant_id(product_sync, sku: str) -> str | None:
        """Extract GetResponse variant ID matching the given SKU."""
        response_data = product_sync.last_response_data
        if not response_data:
            return None

        variants = response_data.get("variants", [])
        # Match by SKU first
        for variant in variants:
            if variant.get("sku") == sku or variant.get("externalId") == sku:
                return variant.get("variantId")

        # Fallback: single variant product (direct match case)
        if len(variants) == 1:
            return variants[0].get("variantId")

        return None

    @classmethod
    def _build_address_dict(cls, address_obj, phone: str = "", company: str = "") -> dict:
        """Build address dict from address object.

        Args:
            address_obj: Address object (billing or shipping)
            phone: Phone number (optional, for billing)
            company: Company name (optional, for billing)

        Returns:
            Formatted address dict for GetResponse API
        """
        firstname = cls._safe_get_attr(address_obj, "firstname")
        lastname = cls._safe_get_attr(address_obj, "lastname")

        return {
            "name": cls._build_full_name(firstname, lastname),
            "firstname": firstname,
            "lastname": lastname,
            "address1": cls._safe_get_attr(address_obj, "street"),
            "city": cls._safe_get_attr(address_obj, "city"),
            "zip": cls._safe_get_attr(address_obj, "postcode"),
            "province": "",
            "provinceCode": "",
            "phone": phone,
            "company": company,
            "countryCode": cls._convert_country_code(cls._safe_get_attr(address_obj, "country_code")),
        }

    @classmethod
    def _build_billing_address(cls, order) -> dict | None:
        """Build billing address dict from order."""
        try:
            order_data = order.as_data
            if not order_data.addresses or not order_data.addresses.billing_address:
                return None

            billing = order_data.addresses.billing_address
            phone = f"{billing.dialling_code}{billing.telephone}"
            company = billing.company or ""

            return cls._build_address_dict(billing, phone=phone, company=company)
        except Exception:
            return None

    @classmethod
    def _build_shipping_address(cls, order) -> dict | None:
        """Build shipping address dict from order."""
        try:
            order_data = order.as_data
            if not order_data.addresses or not order_data.addresses.shipping_address:
                return None

            shipping = order_data.addresses.shipping_address
            return cls._build_address_dict(shipping)
        except Exception:
            return None
