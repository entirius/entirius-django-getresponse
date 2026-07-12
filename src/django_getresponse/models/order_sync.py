# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class OrderSyncStatus(models.TextChoices):
    """Status of order synchronization with GetResponse."""

    PENDING = "pending", "Pending"
    SYNCED = "synced", "Synced"
    FAILED = "failed", "Failed"


class OrderSync(BaseModel):
    """
    GetResponse Order synchronization tracking.

    Tracks synchronization of django_checkout.Order with GetResponse Orders API.
    Each order is synced realtime when created or status changes via Django signals.
    """

    shop = models.ForeignKey(
        "django_getresponse.GetResponseShop",
        on_delete=models.CASCADE,
        related_name="order_syncs",
        help_text="GetResponse shop for this order",
    )
    order_id = models.CharField(max_length=255, help_text="Django checkout Order UUID")
    gr_order_id = models.CharField(
        max_length=128, blank=True, null=True, help_text="GetResponse order ID (assigned after sync)"
    )
    contact_id = models.CharField(max_length=255, help_text="GetResponse contact ID")
    external_id = models.CharField(max_length=255, unique=True, help_text="External ID for order (order_id)")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Order total price")
    currency = models.CharField(max_length=3, help_text="Currency code (ISO 4217)")
    status = models.CharField(max_length=50, help_text="GetResponse order status (PENDING, COMPLETED, etc.)")
    processed_at = models.DateTimeField(help_text="Order processing timestamp")
    selected_variants = models.JSONField(default=list, help_text="List of ordered product variants")
    billing_address = models.JSONField(default=dict, blank=True, help_text="Billing address data")
    shipping_address = models.JSONField(default=dict, blank=True, help_text="Shipping address data")
    sync_status = models.CharField(
        max_length=20,
        choices=OrderSyncStatus.choices,
        default=OrderSyncStatus.PENDING,
        help_text="Synchronization status",
    )
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last successful synchronization timestamp")
    last_request_data = models.JSONField(null=True, blank=True, help_text="Last API request payload")
    last_response_data = models.JSONField(null=True, blank=True, help_text="Last API response data")
    error_message = models.TextField(blank=True, help_text="Last error message if sync failed")
    sync_attempts = models.IntegerField(default=0, help_text="Number of sync attempts")

    objects = models.Manager()

    class Meta:
        verbose_name = "Order Sync"
        verbose_name_plural = "Order Syncs"
        db_table = "django_getresponse_order_sync"
        unique_together = [("shop", "order_id")]
        indexes = [
            models.Index(fields=["order_id"]),
            models.Index(fields=["gr_order_id"]),
            models.Index(fields=["sync_status"]),
            models.Index(fields=["contact_id"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        status_icon = {
            OrderSyncStatus.PENDING: "...",
            OrderSyncStatus.SYNCED: "[OK]",
            OrderSyncStatus.FAILED: "[FAILED]",
        }.get(self.sync_status, "")
        return f"Order {self.order_id[:8]} -> GR {status_icon}"

    def mark_as_synced(self, gr_order_id: str, response_data: dict):
        """Mark order as successfully synced."""
        from django.utils import timezone

        self.gr_order_id = gr_order_id
        self.sync_status = OrderSyncStatus.SYNCED
        self.last_sync_at = timezone.now()
        self.last_response_data = response_data
        self.error_message = ""
        self.save()

    def mark_as_failed(self, error_message: str):
        """Mark order sync as failed."""
        self.sync_status = OrderSyncStatus.FAILED
        self.error_message = error_message
        self.sync_attempts += 1
        self.save()
