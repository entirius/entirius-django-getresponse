# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass

from django_getresponse.services.base_sync_service import BaseSyncService


@dataclass
class CartSyncContext:
    cart: "Cart"
    shop: "GetResponseShop"
    contact_id: str
    api_key: str


class CartSyncService(BaseSyncService[CartSyncContext, "CartSync"]):
    """Service for synchronizing carts with GetResponse API."""

    def __init__(self, client=None):
        super().__init__(client=client, service_name="CartSyncService")

    def sync_cart(self, context: CartSyncContext) -> tuple[bool, str]:
        """Sync cart to GetResponse (create or update)."""
        self.context = context
        self._log_sync_start()

        if self._should_skip_sync():
            self._log_sync_skip("already synced, no changes")
            return True, "Cart already synced, no changes"

        try:
            self._perform_sync()
            self._log_sync_success("synced successfully")
            return True, "Cart synced successfully"
        except Exception as e:
            self._handle_sync_error(e)
            return False, str(e)

    def _is_already_synced(self) -> bool:
        """Check if cart sync record exists."""
        from django_getresponse.models import CartSync

        return CartSync.objects.filter(shop=self.context.shop, cart_id=str(self.context.cart.cart_id)).exists()

    def _generate_current_payload(self) -> dict:
        """Generate cart payload for comparison."""
        from django_getresponse.dto.cart import GetResponseCartDTO

        cart_dto = GetResponseCartDTO.from_cart(
            cart=self.context.cart, shop=self.context.shop, contact_id=self.context.contact_id
        )
        return cart_dto.to_create_payload()

    def _perform_sync(self):
        """Perform cart sync (create or update)."""
        sync_record = self._get_or_create_sync_record()

        if sync_record.gr_cart_id:
            self._update_cart(sync_record)
        else:
            self._create_cart(sync_record)

    def _get_or_create_sync_record(self):
        """Get or create CartSync record. Updates contact_id if changed."""
        from django_getresponse.models import CartSync

        sync_record, created = CartSync.objects.get_or_create(
            shop=self.context.shop, cart_id=str(self.context.cart.cart_id), defaults=self._build_sync_defaults()
        )

        if not created and sync_record.contact_id != self.context.contact_id:
            self.logger.add_log_param_once("old_contact_id", sync_record.contact_id)
            self.logger.add_log_param_once("new_contact_id", self.context.contact_id)
            self.logger.info("Contact changed for cart")
            if sync_record.gr_cart_id:
                self._delete_old_cart(sync_record)

            sync_record.contact_id = self.context.contact_id
            sync_record.gr_cart_id = None
            sync_record.sync_status = "pending"
            sync_record.save(update_fields=["contact_id", "gr_cart_id", "sync_status"])

        return sync_record

    def _delete_old_cart(self, sync_record):
        """Delete old cart from GetResponse when contact changed."""
        self.logger.add_log_param("gr_cart_id", sync_record.gr_cart_id)
        try:
            self.client.delete_cart(
                shop_id=self.context.shop.gr_shop_id, cart_id=sync_record.gr_cart_id, api_key=self.context.api_key
            )
            self.logger.info("Old cart deleted")
        except Exception as e:
            self.logger.add_log_param_once("error", str(e))
            self.logger.warning("Failed to delete old cart")
        finally:
            self.logger.delete_log_param("gr_cart_id")

    def _build_sync_defaults(self) -> dict:
        """Build default values for CartSync record."""
        from django_getresponse.dto.cart import GetResponseCartDTO

        cart_dto = GetResponseCartDTO.from_cart(
            cart=self.context.cart, shop=self.context.shop, contact_id=self.context.contact_id
        )
        return {
            "contact_id": self.context.contact_id,
            "external_id": str(self.context.cart.cart_id),
            "total_price": cart_dto.total_price,
            "currency": cart_dto.currency,
            "selected_variants": cart_dto.selected_variants,
            "cart_url": cart_dto.cart_url or "",
        }

    def _create_cart(self, sync_record):
        """Create new cart in GetResponse."""
        from django_getresponse.dto.cart import GetResponseCartDTO

        cart_dto = GetResponseCartDTO.from_cart(
            cart=self.context.cart, shop=self.context.shop, contact_id=self.context.contact_id
        )
        payload = cart_dto.to_create_payload()

        status_code, response = self.client.create_cart(
            shop_id=self.context.shop.gr_shop_id, cart_data=payload, api_key=self.context.api_key
        )

        gr_cart_id = response.get("cartId")
        sync_record.last_request_data = payload
        sync_record.cart_url = cart_dto.cart_url or ""
        sync_record.mark_as_synced(gr_cart_id, response)
        self.logger.add_log_param_once("gr_cart_id", gr_cart_id)
        self.logger.info("Cart created")

    def _update_cart(self, sync_record):
        """Update existing cart in GetResponse."""
        from django_getresponse.dto.cart import GetResponseCartDTO

        cart_dto = GetResponseCartDTO.from_cart(
            cart=self.context.cart, shop=self.context.shop, contact_id=self.context.contact_id
        )
        payload = cart_dto.to_update_payload()

        status_code, response = self.client.update_cart(
            shop_id=self.context.shop.gr_shop_id,
            cart_id=sync_record.gr_cart_id,
            cart_data=payload,
            api_key=self.context.api_key,
        )

        sync_record.last_request_data = payload
        sync_record.total_price = cart_dto.total_price
        sync_record.currency = cart_dto.currency
        sync_record.selected_variants = cart_dto.selected_variants
        sync_record.cart_url = cart_dto.cart_url or ""
        sync_record.mark_as_synced(sync_record.gr_cart_id, response)
        self.logger.add_log_param_once("gr_cart_id", sync_record.gr_cart_id)
        self.logger.info("Cart updated")

    def _get_sync_record(self):
        """Get existing CartSync record."""
        from django_getresponse.models import CartSync

        try:
            return CartSync.objects.get(shop=self.context.shop, cart_id=str(self.context.cart.cart_id))
        except CartSync.DoesNotExist:
            return None

    def _get_entity_name(self) -> str:
        """Get entity name for logging."""
        return "Cart"

    def _get_entity_id(self) -> str:
        """Get entity ID for logging."""
        return str(self.context.cart.cart_id)
