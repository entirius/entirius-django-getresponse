# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass


@dataclass
class GetResponseCartDTO:
    contact_id: str
    external_id: str
    total_price: float
    currency: str
    selected_variants: list[dict]
    cart_url: str | None = None

    def __post_init__(self):
        self._validate_contact_id()
        self._validate_external_id()
        self._validate_total_price()
        self._validate_currency()

    def _validate_contact_id(self):
        if not self.contact_id or not self.contact_id.strip():
            raise ValueError("contact_id is required and cannot be empty")

    def _validate_external_id(self):
        if not self.external_id or len(self.external_id) > 255:
            raise ValueError("external_id required, max 255 chars")

    def _validate_total_price(self):
        if self.total_price < 0:
            raise ValueError("total_price must be >= 0")

    def _validate_currency(self):
        if not self.currency or len(self.currency) != 3:
            raise ValueError("currency must be 3-char ISO code")

    def to_create_payload(self) -> dict:
        """Generate payload for POST /shops/{shopId}/carts."""
        data = self._build_base_dict()
        return self._filter_none_values(data)

    def to_update_payload(self) -> dict:
        """Generate payload for POST /shops/{shopId}/carts/{cartId}."""
        data = self._build_base_dict()
        return self._filter_none_values(data)

    def _build_base_dict(self) -> dict:
        return {
            "contactId": self.contact_id,
            "externalId": self.external_id,
            "totalPrice": self.total_price,
            "currency": self.currency,
            "selectedVariants": self.selected_variants,
            "cartUrl": self.cart_url,
        }

    def _filter_none_values(self, data: dict) -> dict:
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_cart(cls, cart, shop, contact_id: str):
        """
        Create DTO from django_checkout.Cart instance.

        Args:
            cart: Cart instance from django_checkout
            shop: GetResponseShop instance
            contact_id: GetResponse contact ID (required by GetResponse API)
        """
        cart_data = cls._extract_cart_data(cart)
        variants = cls._build_variants_from_cart(cart, shop)

        return cls(
            contact_id=contact_id,
            external_id=str(cart.cart_id),
            total_price=float(cart_data["total"]),
            currency=cart_data["currency"],
            selected_variants=variants,
            cart_url=cls._build_cart_url(cart, shop),
        )

    @classmethod
    def _extract_cart_data(cls, cart) -> dict:
        checkout_data = cart.as_data
        return {
            "total": checkout_data.total,
            "currency": checkout_data.currency_code or "PLN",
        }

    @classmethod
    def _build_cart_url(cls, cart, shop) -> str | None:
        """Build cartUrl from the shop's configured cart URL.

        Appends the cart UUID as a query param (?cart=<uuid>) only when
        SEND_CART_UID_TO_GETRESPONSE_IN_LINK is enabled; otherwise returns the
        configured URL as-is. Returns None when the shop has no cart URL set,
        so the cartUrl key is omitted from the payload.
        """
        if not shop.domain_url_cart:
            return None

        base_url = shop.domain_url_cart.rstrip("/")

        from django_getresponse.settings import SEND_CART_UID_TO_GETRESPONSE_IN_LINK

        if SEND_CART_UID_TO_GETRESPONSE_IN_LINK:
            return f"{base_url}?cart={cart.cart_id}"
        return base_url

    @classmethod
    def _build_variants_from_cart(cls, cart, shop) -> list[dict]:
        """Build selectedVariants array from cart items.

        Raises:
            ValueError: If no valid variants can be built (GetResponse requires at least one).
        """
        checkout_data = cart.as_data
        items = checkout_data.cart.items
        variants = []

        for item in items:
            variant_dict = cls._build_variant_dict(item, shop)
            if variant_dict:
                variants.append(variant_dict)

        if not variants:
            raise ValueError(
                f"No synced products found for cart {cart.cart_id}. "
                "All cart items must have corresponding synced products in GetResponse."
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
