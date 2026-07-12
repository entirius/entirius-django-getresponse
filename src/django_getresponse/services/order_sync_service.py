# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass

from django_getresponse.services.base_sync_service import BaseSyncService


@dataclass
class OrderSyncContext:
    order: "Order"
    shop: "GetResponseShop"
    contact_id: str
    api_key: str


class OrderSyncService(BaseSyncService[OrderSyncContext, "OrderSync"]):
    """Service for synchronizing orders with GetResponse API."""

    def __init__(self, client=None):
        super().__init__(client=client, service_name="OrderSyncService")

    def sync_order(self, context: OrderSyncContext) -> tuple[bool, str]:
        """Sync order to GetResponse (create only)."""
        self.context = context
        self._log_sync_start()

        if self._is_already_synced():
            self._log_sync_skip("already synced")
            return True, "Order already synced"

        try:
            self._create_order()
            self._log_sync_success("synced successfully")
            return True, "Order synced successfully"
        except Exception as e:
            self._handle_sync_error(e)
            return False, str(e)

    def update_order_status(self, context: OrderSyncContext) -> tuple[bool, str]:
        """Update order status in GetResponse."""
        self.context = context

        sync_record = self._get_sync_record()
        if not sync_record or not sync_record.gr_order_id:
            return False, "Order not synced yet, cannot update status"

        try:
            self._update_order(sync_record)
            self.logger.info("Order status updated successfully")
            return True, "Order status updated successfully"
        except Exception as e:
            self._handle_sync_error(e)
            return False, str(e)

    def _is_already_synced(self) -> bool:
        """Check if order sync record exists."""
        from django_getresponse.models import OrderSync

        return OrderSync.objects.filter(shop=self.context.shop, order_id=str(self.context.order.order_id)).exists()

    def _generate_current_payload(self) -> dict:
        """Generate current payload for change detection."""
        from django_getresponse.dto.order import GetResponseOrderDTO

        order_dto = GetResponseOrderDTO.from_order(
            order=self.context.order, contact_id=self.context.contact_id, shop=self.context.shop
        )
        return order_dto.to_create_payload()

    def _get_sync_record(self):
        """Get existing OrderSync record."""
        from django_getresponse.models import OrderSync

        try:
            return OrderSync.objects.get(shop=self.context.shop, order_id=str(self.context.order.order_id))
        except OrderSync.DoesNotExist:
            return None

    def _get_entity_name(self) -> str:
        """Get entity name for logging."""
        return "Order"

    def _get_entity_id(self) -> str:
        """Get entity ID for logging."""
        return str(self.context.order.order_id)

    def _create_order(self):
        """Create new order in GetResponse."""
        from django_getresponse.dto.order import GetResponseOrderDTO
        from django_getresponse.models import OrderSync

        order_dto = GetResponseOrderDTO.from_order(
            order=self.context.order, contact_id=self.context.contact_id, shop=self.context.shop
        )
        payload = order_dto.to_create_payload()

        status_code, response = self.client.create_order(
            shop_id=self.context.shop.gr_shop_id, order_data=payload, api_key=self.context.api_key
        )

        gr_order_id = response.get("orderId")

        sync_record = OrderSync.objects.create(
            shop=self.context.shop,
            order_id=str(self.context.order.order_id),
            contact_id=self.context.contact_id,
            external_id=str(self.context.order.order_id),
            total_price=order_dto.total_price,
            currency=order_dto.currency,
            status=order_dto.status,
            processed_at=self.context.order.created,
            selected_variants=order_dto.selected_variants,
            billing_address=order_dto.billing_address or {},
            shipping_address=order_dto.shipping_address or {},
            last_request_data=payload,
        )

        sync_record.mark_as_synced(gr_order_id, response)
        self.logger.add_log_param_once("gr_order_id", gr_order_id)
        self.logger.info("Order created")

    def _update_order(self, sync_record):
        """Update existing order status in GetResponse."""
        from django_getresponse.dto.order import GetResponseOrderDTO

        order_dto = GetResponseOrderDTO.from_order(
            order=self.context.order, contact_id=self.context.contact_id, shop=self.context.shop
        )
        payload = order_dto.to_update_payload()

        status_code, response = self.client.update_order(
            shop_id=self.context.shop.gr_shop_id,
            order_id=sync_record.gr_order_id,
            order_data=payload,
            api_key=self.context.api_key,
        )

        sync_record.status = order_dto.status
        sync_record.last_request_data = payload
        sync_record.mark_as_synced(sync_record.gr_order_id, response)
        self.logger.add_log_param_once("status", order_dto.status)
        self.logger.add_log_param_once("gr_order_id", sync_record.gr_order_id)
        self.logger.info("Order status updated")
