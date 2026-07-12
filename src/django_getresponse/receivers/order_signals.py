# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass

from django.db.models.signals import post_save
from django.dispatch import receiver
from process_logger import ProcessLogger

from django_getresponse.services.marketing_consent_service import has_marketing_consent, is_consent_required
from django_getresponse.utils.contact_helpers import (
    get_contact_id_from_customer,
    get_contact_id_from_email,
)
from django_getresponse.utils.sync_helpers import get_api_key_for_channel, get_shop_for_checkout

logger = ProcessLogger("order_signals")


@dataclass
class OrderSyncSetup:
    """Container for order sync setup data."""

    shop: "GetResponseShop"
    contact_id: str
    api_key: str


@receiver(post_save, sender="django_checkout.Order")
def sync_order_on_create(sender, instance, created, **kwargs):
    """Sync order to GetResponse when order is created.

    Triggered by: Order save with created=True
    IMPORTANT: Does NOT delete CartSync - GetResponse requirement
    """
    if not created:
        return

    from django_getresponse.services.order_sync_service import OrderSyncContext, OrderSyncService

    order = instance
    setup = _prepare_order_sync(order)
    if not setup:
        return

    try:
        context = OrderSyncContext(order=order, shop=setup.shop, contact_id=setup.contact_id, api_key=setup.api_key)
        service = OrderSyncService()
        success, message = service.sync_order(context)

        logger.add_log_param_once("order_id", str(order.order_id))
        logger.add_log_param_once("message", message)
        if success:
            logger.info("Order synced to GetResponse")
        else:
            logger.error("Failed to sync order")
    except Exception as e:
        logger.add_log_param_once("order_id", str(order.order_id))
        logger.exception(e)


@receiver(post_save, sender="django_checkout.Order")
def sync_order_status_change(sender, instance, created, **kwargs):
    """Update order status in GetResponse when order status changes.

    Triggered by: Order save (not created) when status differs from synced status.
    """
    if created:
        return

    from django_getresponse.dto.order import GetResponseOrderDTO
    from django_getresponse.models import OrderSync
    from django_getresponse.services.order_sync_service import OrderSyncContext, OrderSyncService

    order = instance
    setup = _prepare_order_sync(order)
    if not setup:
        return

    try:
        sync_record = OrderSync.objects.get(shop=setup.shop, order_id=str(order.order_id))
    except OrderSync.DoesNotExist:
        return

    if not sync_record.gr_order_id:
        return

    current_gr_status = GetResponseOrderDTO._map_status_to_gr(order.order_status)
    if sync_record.status == current_gr_status:
        return

    try:
        context = OrderSyncContext(order=order, shop=setup.shop, contact_id=setup.contact_id, api_key=setup.api_key)
        service = OrderSyncService()
        success, message = service.update_order_status(context)

        logger.add_log_param_once("order_id", str(order.order_id))
        logger.add_log_param_once("old_status", sync_record.status)
        logger.add_log_param_once("new_status", current_gr_status)
        logger.add_log_param_once("message", message)
        if success:
            logger.info("Order status updated in GetResponse")
        else:
            logger.error("Failed to update order status")
    except Exception as e:
        logger.add_log_param_once("order_id", str(order.order_id))
        logger.exception(e)


def _prepare_order_sync(order: "Order") -> OrderSyncSetup | None:
    """Prepare and validate all data needed for order sync.

    Args:
        order: Order instance to sync

    Returns:
        OrderSyncSetup with shop, contact_id, api_key or None if validation fails
    """
    if not order.channel:
        logger.debug(f"Order {order.order_id} has no channel, skipping GR sync")
        return None

    try:
        order_data = order.as_data
        language_code = getattr(order_data, "language_code", None)
        currency_code = getattr(order_data, "currency_code", None)
    except Exception:
        language_code, currency_code = None, None

    shop = get_shop_for_checkout(order.channel, language_code, currency_code)
    if not shop:
        return None

    email = _get_email_from_order(order)
    if not has_marketing_consent(email=email, shop=shop, resource_created_at=order.created):
        logger.debug(f"Order {order.order_id}: no marketing consent, skipping GR sync")
        return None

    if not is_consent_required(shop) and email:
        _auto_create_contact_from_order_email(shop, email)

    contact_id = _get_contact_id_from_order(order)
    if not contact_id or not contact_id.strip():
        logger.debug(f"Order {order.order_id} has no contact_id, skipping GR sync")
        return None

    api_key = get_api_key_for_channel(shop.channel)
    if not api_key:
        return None

    return OrderSyncSetup(shop=shop, contact_id=contact_id, api_key=api_key)


def _auto_create_contact_from_order_email(shop: "GetResponseShop", email: str) -> None:
    """Auto-create a GR contact from the order email (used only when the consent gate is disabled)."""
    from django_getresponse.services.contact_auto_create_service import (
        ContactAutoCreateContext,
        ContactAutoCreateService,
    )

    try:
        api_key = get_api_key_for_channel(shop.channel)
        if not api_key:
            return
        context = ContactAutoCreateContext(email=email, shop=shop, api_key=api_key, source="order")
        ContactAutoCreateService().create_contact_if_needed(context)
    except Exception as e:
        logger.exception(e)


def _get_email_from_order(order: "Order") -> str | None:
    """Extract billing or shipping email from order_body. Used by the consent gate."""
    try:
        order_data = order.as_data
        if order_data.addresses and order_data.addresses.billing_address:
            billing_email = order_data.addresses.billing_address.email
            if billing_email:
                return billing_email
        if order_data.addresses and order_data.addresses.shipping_address:
            shipping_email = order_data.addresses.shipping_address.email
            if shipping_email:
                return shipping_email
    except Exception as e:
        logger.debug(f"Could not extract email from order_body: {e}")
    return None


def _get_contact_id_from_order(order: "Order") -> str | None:
    """Get GetResponse contact_id from order.

    Priority:
    1. From customer's GetResponseContact
    2. From billing_email (from order_body) lookup
    3. From shipping_email (from order_body) lookup
    """
    if order.customer:
        contact_id = get_contact_id_from_customer(order.customer)
        if contact_id:
            return contact_id

    try:
        order_data = order.as_data

        if order_data.addresses and order_data.addresses.billing_address:
            billing_email = order_data.addresses.billing_address.email
            if billing_email:
                contact_id = get_contact_id_from_email(billing_email)
                if contact_id:
                    return contact_id

        if order_data.addresses and order_data.addresses.shipping_address:
            shipping_email = order_data.addresses.shipping_address.email
            if shipping_email:
                contact_id = get_contact_id_from_email(shipping_email)
                if contact_id:
                    return contact_id
    except Exception as e:
        logger.debug(f"Could not extract email from order_body: {e}")

    return None
