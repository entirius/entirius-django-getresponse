# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class CartSyncStatus(models.TextChoices):
    """Status of cart synchronization with GetResponse."""

    PENDING = "pending", "Pending"
    SYNCED = "synced", "Synced"
    FAILED = "failed", "Failed"


class CartSync(BaseModel):
    """
    GetResponse Cart synchronization tracking.

    Tracks synchronization of django_checkout.Cart with GetResponse Carts API.
    Each cart is synced realtime when created or updated via Django signals.
    """

    shop = models.ForeignKey(
        "django_getresponse.GetResponseShop",
        on_delete=models.CASCADE,
        related_name="cart_syncs",
        help_text="GetResponse shop for this cart",
    )
    cart_id = models.CharField(max_length=255, help_text="Django checkout Cart UUID")
    gr_cart_id = models.CharField(
        max_length=128, blank=True, null=True, help_text="GetResponse cart ID (assigned after sync)"
    )
    contact_id = models.CharField(max_length=255, help_text="GetResponse contact ID (required by GetResponse API)")
    external_id = models.CharField(max_length=255, unique=True, help_text="External ID for cart (cart_id)")
    total_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Cart total price")
    currency = models.CharField(max_length=3, help_text="Currency code (ISO 4217)")
    cart_url = models.CharField(max_length=512, help_text="URL to cart page")
    selected_variants = models.JSONField(default=list, help_text="List of selected product variants")
    sync_status = models.CharField(
        max_length=20,
        choices=CartSyncStatus.choices,
        default=CartSyncStatus.PENDING,
        help_text="Synchronization status",
    )
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last successful synchronization timestamp")
    last_request_data = models.JSONField(null=True, blank=True, help_text="Last API request payload")
    last_response_data = models.JSONField(null=True, blank=True, help_text="Last API response data")
    error_message = models.TextField(blank=True, help_text="Last error message if sync failed")
    sync_attempts = models.IntegerField(default=0, help_text="Number of sync attempts")

    objects = models.Manager()

    class Meta:
        verbose_name = "Cart Sync"
        verbose_name_plural = "Cart Syncs"
        db_table = "django_getresponse_cart_sync"
        unique_together = [("shop", "cart_id")]
        indexes = [
            models.Index(fields=["cart_id"]),
            models.Index(fields=["gr_cart_id"]),
            models.Index(fields=["sync_status"]),
            models.Index(fields=["contact_id"]),
        ]

    def __str__(self):
        status_icon = {
            CartSyncStatus.PENDING: "...",
            CartSyncStatus.SYNCED: "[OK]",
            CartSyncStatus.FAILED: "[FAILED]",
        }.get(self.sync_status, "")
        return f"Cart {self.cart_id[:8]} -> GR {status_icon}"

    def mark_as_synced(self, gr_cart_id: str, response_data: dict):
        """Mark cart as successfully synced."""
        from django.utils import timezone

        self.gr_cart_id = gr_cart_id
        self.sync_status = CartSyncStatus.SYNCED
        self.last_sync_at = timezone.now()
        self.last_response_data = response_data
        self.error_message = ""
        self.save()

    def mark_as_failed(self, error_message: str):
        """Mark cart sync as failed."""
        self.sync_status = CartSyncStatus.FAILED
        self.error_message = error_message
        self.sync_attempts += 1
        self.save()
