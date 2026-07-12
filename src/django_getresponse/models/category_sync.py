# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class CategorySyncStatus(models.TextChoices):
    """Status of category synchronization with GetResponse"""

    PENDING = "pending", "Pending"
    SYNCED = "synced", "Synced"
    FAILED = "failed", "Failed"


class CategorySync(BaseModel):
    """
    Tracks synchronization status of ProductCategory with GetResponse categories.

    This model maintains the mapping between django_pim ProductCategory and GetResponse
    category IDs, along with sync history and status.
    """

    channel = models.ForeignKey(
        "Channel",
        on_delete=models.CASCADE,
        related_name="category_syncs",
        help_text="GetResponse channel (shop.idx == channel.idx)",
    )
    shop = models.ForeignKey(
        "GetResponseShop",
        on_delete=models.CASCADE,
        related_name="category_syncs",
        help_text="GetResponse shop this category is synced to",
    )
    product_category = models.ForeignKey(
        "django_pim.ProductCategory",
        on_delete=models.CASCADE,
        related_name="getresponse_syncs",
        help_text="Product category from django_pim",
    )
    gr_category_id = models.CharField(max_length=128, blank=True, null=True, help_text="Category ID in GetResponse API")
    gr_shop_id = models.CharField(
        max_length=128, blank=True, help_text="Shop ID in GetResponse API (legacy - use shop FK instead)"
    )
    external_id = models.CharField(max_length=255, help_text="External ID sent to GetResponse (e.g., 'shop_cat_123')")
    sync_status = models.CharField(
        max_length=20,
        choices=CategorySyncStatus.choices,
        default=CategorySyncStatus.PENDING,
        help_text="Current synchronization status",
    )
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last successful synchronization timestamp")
    last_request_data = models.JSONField(
        default=dict, blank=True, help_text="Last POST/PATCH request payload sent to GetResponse"
    )
    last_response_data = models.JSONField(
        default=dict, blank=True, help_text="Last response received from GetResponse API"
    )
    error_message = models.TextField(blank=True, help_text="Error message if sync_status is 'failed'")
    sync_attempts = models.IntegerField(default=0, help_text="Number of synchronization attempts")

    objects = models.Manager()

    class Meta:
        verbose_name = "Category Sync"
        verbose_name_plural = "Category Syncs"
        db_table = "django_getresponse_category_sync"
        unique_together = [["shop", "product_category"]]
        indexes = [
            models.Index(fields=["shop", "sync_status"]),
            models.Index(fields=["channel", "sync_status"]),
            models.Index(fields=["gr_category_id"]),
            models.Index(fields=["external_id"]),
        ]

    def __str__(self):
        status_indicator = {
            CategorySyncStatus.SYNCED: "[OK]",
            CategorySyncStatus.FAILED: "[FAILED]",
            CategorySyncStatus.PENDING: "[PENDING]",
        }.get(self.sync_status, "?")

        return f"{status_indicator} {self.product_category.name} -> GR:{self.gr_category_id or 'N/A'}"

    def mark_as_synced(self, gr_category_id: str, response_data: dict):
        """Mark category as successfully synced"""
        from django.utils import timezone

        self.gr_category_id = gr_category_id
        self.sync_status = CategorySyncStatus.SYNCED
        self.last_sync_at = timezone.now()
        self.last_response_data = response_data
        self.error_message = ""

    def mark_as_failed(self, error_message: str):
        """Mark category sync as failed"""
        self.sync_status = CategorySyncStatus.FAILED
        self.error_message = error_message

    def increment_attempts(self):
        """Increment sync attempt counter"""
        self.sync_attempts += 1

    @property
    def is_synced(self) -> bool:
        """Check if category is successfully synced"""
        return self.sync_status == CategorySyncStatus.SYNCED

    @property
    def needs_sync(self) -> bool:
        """Check if category needs synchronization"""
        return self.sync_status in [CategorySyncStatus.PENDING, CategorySyncStatus.FAILED]

    def get_shop_id(self) -> str:
        """
        Get GetResponse shop ID.

        Returns shop.gr_shop_id if shop FK exists, otherwise returns gr_shop_id (legacy).
        Raises ValueError if neither is available.
        """
        if self.shop and self.shop.gr_shop_id:
            return self.shop.gr_shop_id
        elif self.gr_shop_id:
            return self.gr_shop_id
        else:
            raise ValueError(
                f"CategorySync {self.id} has no shop ID. Either assign a GetResponseShop or set gr_shop_id."
            )
