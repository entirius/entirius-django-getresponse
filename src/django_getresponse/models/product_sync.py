# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class ProductSyncStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SYNCED = "synced", "Synced"
    FAILED = "failed", "Failed"


class ProductSync(BaseModel):
    shop = models.ForeignKey(
        "GetResponseShop", on_delete=models.CASCADE, related_name="product_syncs", help_text="GetResponse shop"
    )
    product = models.ForeignKey(
        "django_pim.Product",
        on_delete=models.CASCADE,
        related_name="getresponse_syncs",
        help_text="Product from django_pim",
    )
    gr_product_id = models.CharField(max_length=128, blank=True, null=True, help_text="Product ID in GetResponse API")
    external_id = models.CharField(max_length=255, help_text="External ID sent to GetResponse")
    sync_status = models.CharField(
        max_length=20,
        choices=ProductSyncStatus.choices,
        default=ProductSyncStatus.PENDING,
        help_text="Current synchronization status",
    )
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last successful synchronization timestamp")
    last_request_data = models.JSONField(default=dict, blank=True, help_text="Last request payload sent to GetResponse")
    last_response_data = models.JSONField(
        default=dict, blank=True, help_text="Last response received from GetResponse API"
    )
    error_message = models.TextField(blank=True, help_text="Error message if sync_status is 'failed'")
    sync_attempts = models.IntegerField(default=0, help_text="Number of synchronization attempts")

    objects = models.Manager()

    class Meta:
        verbose_name = "Product Sync"
        verbose_name_plural = "Product Syncs"
        db_table = "django_getresponse_product_sync"
        unique_together = [["shop", "product"]]
        indexes = [
            models.Index(fields=["shop", "sync_status"]),
            models.Index(fields=["gr_product_id"]),
            models.Index(fields=["external_id"]),
        ]

    def __str__(self):
        status_map = {
            ProductSyncStatus.SYNCED: "[OK]",
            ProductSyncStatus.FAILED: "[FAILED]",
            ProductSyncStatus.PENDING: "[PENDING]",
        }
        status_indicator = status_map.get(self.sync_status, "?")
        try:
            sku = self.product.sku
        except Exception as e:
            sku = f"product_id={self.product_id} ({e.__class__.__name__}: {e})"
        return f"{status_indicator} {sku} -> GR:{self.gr_product_id or 'N/A'}"

    def mark_as_synced(self, gr_product_id: str, response_data: dict):
        from django.utils import timezone

        self.gr_product_id = gr_product_id
        self.sync_status = ProductSyncStatus.SYNCED
        self.last_sync_at = timezone.now()
        self.last_response_data = response_data
        self.error_message = ""

    def mark_as_failed(self, error_message: str):
        self.sync_status = ProductSyncStatus.FAILED
        self.error_message = error_message

    def increment_attempts(self):
        self.sync_attempts += 1

    @property
    def is_synced(self) -> bool:
        return self.sync_status == ProductSyncStatus.SYNCED

    @property
    def needs_sync(self) -> bool:
        return self.sync_status in [ProductSyncStatus.PENDING, ProductSyncStatus.FAILED]
