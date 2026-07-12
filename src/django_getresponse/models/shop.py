# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models
from django_utils.models.base_model import BaseModel


class ShopSyncStatus(models.TextChoices):
    """Status of shop synchronization with GetResponse."""

    PENDING = "pending", "Pending"
    SYNCED = "synced", "Synced"
    FAILED = "failed", "Failed"


class GetResponseShop(BaseModel):
    """
    GetResponse Shop configuration.

    Each shop represents an e-commerce store in GetResponse and is assigned
    to a specific channel. Shops are synchronized with GetResponse API
    to enable product catalog management.
    """

    channel = models.ForeignKey(
        "django_getresponse.Channel",
        on_delete=models.CASCADE,
        related_name="getresponse_shops",
        help_text="Channel this shop belongs to",
    )
    name = models.CharField(max_length=64, help_text="Shop name in GetResponse (1-64 characters)")
    currency = models.ForeignKey(
        "django_regional.Currency", on_delete=models.PROTECT, help_text="Shop currency (ISO 4217 code)"
    )
    language = models.ForeignKey(
        "django_regional.Language",
        on_delete=models.PROTECT,
        related_name="getresponse_shops",
        help_text="Shop language for DB lookups (ISO 639-1 code, e.g., 'gb', 'us')",
    )
    external_language = models.ForeignKey(
        "django_regional.Language",
        on_delete=models.PROTECT,
        related_name="getresponse_shops_external",
        help_text="Shop language sent to GetResponse API (ISO 639-1 code, e.g., 'en')",
    )
    domain_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Base domain URL for product links (e.g., 'https://shop.example.com')",
    )
    domain_url_categories = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Base domain URL for category links (e.g., 'https://shop.example.com')",
    )
    domain_url_cart = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Cart page URL sent to GetResponse as cartUrl (e.g., 'https://shop.example.com/cart')",
    )
    price_country = models.ForeignKey(
        "django_regional.Country",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        help_text="Country for price calculation",
    )
    cart_campaign = models.ForeignKey(
        "django_getresponse.GetResponseCampaign",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="cart_shops",
        help_text="Campaign for cart/order contacts (if not set, will auto-select by language)",
    )
    crm_campaign = models.ForeignKey(
        "django_getresponse.GetResponseCampaign",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="crm_shops",
        help_text="Campaign for contacts created from the CRM newsletter form (if not set, auto-selects by language).",
    )

    # Custom field IDs for contact segmentation
    customer_type_field_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="GetResponse custom field ID for customer_type (new/returning)",
    )
    total_orders_count_field_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="GetResponse custom field ID for total_orders_count",
    )
    last_order_date_field_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="GetResponse custom field ID for last_order_date",
    )

    marketing_consent_type_name = models.CharField(
        max_length=64,
        default="marketing",
        blank=True,
        help_text=(
            "django_crm ConsentType.name that gates GR sync. Cart/Order push and "
            "GR contact creation happen only after this consent is granted (consent_bool=True). "
            "Leave EMPTY to disable the gate for this shop: cart/order then sync without any "
            "consent check (contact auto-created from the cart/order email)."
        ),
    )

    gr_shop_id = models.CharField(
        max_length=128, blank=True, null=True, help_text="GetResponse shop ID (assigned after sync)"
    )
    sync_status = models.CharField(
        max_length=20,
        choices=ShopSyncStatus.choices,
        default=ShopSyncStatus.PENDING,
        help_text="Synchronization status with GetResponse",
    )
    last_sync_at = models.DateTimeField(null=True, blank=True, help_text="Last successful synchronization timestamp")
    error_message = models.TextField(blank=True, help_text="Last error message if sync failed")

    objects = models.Manager()

    class Meta:
        verbose_name = "GetResponse Shop"
        verbose_name_plural = "GetResponse Shops"
        db_table = "django_getresponse_shop"
        unique_together = [("channel", "name")]
        indexes = [
            models.Index(fields=["channel", "sync_status"]),
            models.Index(fields=["gr_shop_id"]),
        ]

    def __str__(self):
        status_icon = {
            ShopSyncStatus.PENDING: "...",
            ShopSyncStatus.SYNCED: "[OK]",
            ShopSyncStatus.FAILED: "[FAILED]",
        }.get(self.sync_status, "")

        return f"{self.channel.idx} | {self.name} {status_icon}"

    @property
    def locale(self) -> str:
        """
        Get language code for GetResponse API.

        GetResponse expects only 2-character language code (ISO 639-1).
        Uses external_language (e.g., "en") rather than language (e.g., "gb", "us")
        because GetResponse does not support region-specific locale codes.

        Returns:
            Language code like "pl", "en", "de"
        """
        return self.external_language.iso2

    @property
    def is_synced(self) -> bool:
        """Check if shop has been successfully synced to GetResponse."""
        return self.gr_shop_id is not None and self.sync_status == ShopSyncStatus.SYNCED

    def to_getresponse_payload(self) -> dict:
        """
        Generate payload for GetResponse API.

        Returns:
            Dictionary with shop data for create/update operations
        """
        return {
            "name": self.name,
            "locale": self.locale,
            "currency": self.currency.iso3,
        }

    def save(self, *args, **kwargs):
        """
        Save shop and auto-create custom fields if not set.

        If custom field IDs are empty and shop is synced, will attempt to
        create the custom fields in GetResponse and store their IDs.
        """
        super().save(*args, **kwargs)
        self._ensure_custom_fields()

    def _ensure_custom_fields(self):
        """Create custom fields in GetResponse if not already set."""
        from django_getresponse.services.custom_field_service import CustomFieldService

        if self.customer_type_field_id and self.total_orders_count_field_id and self.last_order_date_field_id:
            return

        try:
            service = CustomFieldService()
            if not self.customer_type_field_id:
                self.customer_type_field_id = service.create_or_get_field(
                    channel=self.channel,
                    field_name="customer_type",
                    field_type="string",
                    field_format="text",
                    hidden="false",
                )

            if not self.total_orders_count_field_id:
                self.total_orders_count_field_id = service.create_or_get_field(
                    channel=self.channel,
                    field_name="total_orders_count",
                    field_type="number",
                    field_format="text",
                    hidden="false",
                )

            if not self.last_order_date_field_id:
                self.last_order_date_field_id = service.create_or_get_field(
                    channel=self.channel,
                    field_name="last_order_date",
                    field_type="date",
                    field_format="text",
                    hidden="false",
                )

            super().save(
                update_fields=["customer_type_field_id", "total_orders_count_field_id", "last_order_date_field_id"]
            )

        except Exception as e:
            from process_logger import ProcessLogger

            logger = ProcessLogger("GetResponseShop")
            logger.warning(f"Failed to create custom fields for shop {self.name}: {e}")
