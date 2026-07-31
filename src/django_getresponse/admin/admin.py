# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.utils.safestring import mark_safe

from django_getresponse.admin.mixins import ApiDataPreviewMixin, ResyncActionMixin, SyncStatusBadgeMixin
from django_getresponse.models import (
    CartSync,
    CategorySync,
    Channel,
    GetResponseAccount,
    GetResponseCampaign,
    GetResponseContact,
    GetResponseShop,
    OrderSync,
    ProductSync,
    ShopSyncStatus,
)

try:
    from get_response_sdk import GetResponseClient as GRClient
except ImportError:
    GRClient = None


class GetResponseShopInline(admin.TabularInline):
    """Inline admin for GetResponseShop in ChannelAdmin."""

    model = GetResponseShop
    extra = 0
    fields = ("name", "currency", "language", "gr_shop_id", "sync_status", "last_sync_at")
    readonly_fields = ("gr_shop_id", "sync_status", "last_sync_at")


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("idx", "shop_count", "created_at", "modified_at")
    search_fields = ("idx",)
    readonly_fields = ("created_at", "modified_at")
    inlines = [GetResponseShopInline]

    @admin.display(description="Shops")
    def shop_count(self, obj):
        count = obj.getresponse_shops.count()
        synced = obj.getresponse_shops.filter(sync_status=ShopSyncStatus.SYNCED).count()
        return f"{synced}/{count} synced"


@admin.register(GetResponseShop)
class GetResponseShopAdmin(SyncStatusBadgeMixin, ResyncActionMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "channel",
        "currency",
        "language",
        "price_country",
        "sync_status_badge",
        "gr_shop_id",
        "last_sync_at",
    )
    list_filter = ("sync_status", "channel", "currency", "language", "external_language")
    search_fields = ("name", "channel__idx", "gr_shop_id")
    readonly_fields = (
        "gr_shop_id",
        "customer_type_field_id",
        "total_orders_count_field_id",
        "last_order_date_field_id",
        "created_at",
        "modified_at",
        "last_sync_at",
        "error_message",
    )
    autocomplete_fields = ["channel", "cart_campaign", "crm_campaign"]
    raw_id_fields = ["currency", "language", "external_language", "price_country"]
    actions = ["mark_for_resync"]
    resync_success_message = "{count} shop(s) marked for re-sync. Run sync-shops-to-getresponse command to sync."

    fieldsets = (
        (None, {"fields": ("channel", "name")}),
        ("Regional Settings", {"fields": ("currency", "language", "external_language", "price_country")}),
        ("Domain", {"fields": ("domain_url", "domain_url_categories", "domain_url_cart")}),
        (
            "Campaign Routing",
            {
                "fields": ("cart_campaign", "crm_campaign"),
                "description": (
                    "Route contacts by source. cart_campaign: contacts created from cart/order. "
                    "crm_campaign: contacts created from newsletter signups (legacy field name). "
                    "Either falls back to language auto-select when empty."
                ),
            },
        ),
        (
            "Marketing Consent Gate",
            {
                "fields": ("marketing_consent_type_name",),
                "description": (
                    "django_agreements AgreementDefinition.slug that gates Cart/Order push and GR contact "
                    "creation. Resources are synced only when the latest ConsentRecord for this slug is "
                    "granted and was recorded before the resource was created."
                ),
            },
        ),
        ("GetResponse Sync", {"fields": ("gr_shop_id", "sync_status", "last_sync_at", "error_message")}),
        (
            "Custom Fields",
            {
                "fields": ("customer_type_field_id", "total_orders_count_field_id", "last_order_date_field_id"),
                "description": "Auto-created custom field IDs for contact segmentation (readonly - created automatically)",
                "classes": ("collapse",),
            },
        ),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )


@admin.register(GetResponseAccount)
class GetResponseAccountAdmin(admin.ModelAdmin):
    list_display = ("name_or_key", "is_enabled", "campaign_count", "created_at", "modified_at")
    list_filter = ("is_enabled",)
    search_fields = ("name", "api_key")
    readonly_fields = ("created_at", "modified_at")
    actions = ["refresh_campaigns", "enable_accounts", "disable_accounts"]
    fieldsets = (
        (None, {"fields": ("name", "api_key", "is_enabled", "channel")}),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Account")
    def name_or_key(self, obj):
        if obj.name:
            return obj.name
        return f"{obj.api_key[:12]}..."

    @admin.display(description="Campaigns")
    def campaign_count(self, obj):
        count = obj.campaigns.count()
        active_count = obj.campaigns.filter(is_active=True).count()
        return f"{active_count}/{count} active"

    @admin.action(description="Refresh campaigns from GetResponse API")
    def refresh_campaigns(self, request, queryset):
        """Fetch campaigns from GetResponse API and sync to database"""
        if GRClient is None:
            self.message_user(request, "get_response_sdk is not installed", level="error")
            return

        def campaign_to_kwargs(campaign_obj: dict) -> tuple:
            campaign_id = campaign_obj.get("campaignId", "")
            name = campaign_obj.get("name", "")
            return campaign_id, name

        total_synced = 0
        for account in queryset:
            try:
                campaign_list = GRClient().get_campaign_list(account.api_key)
            except Exception as e:
                self.message_user(request, f"Error fetching campaigns for {account}: {str(e)}", level="error")
                continue

            campaigns_as_kwargs = (campaign_to_kwargs(obj) for obj in campaign_list)
            for campaign_id, name in campaigns_as_kwargs:
                campaign, created = GetResponseCampaign.objects.get_or_create(account=account, campaign_id=campaign_id)
                campaign.name = name
                campaign.save()
                total_synced += 1

        self.message_user(
            request,
            f"Successfully synced {total_synced} campaigns from {queryset.count()} account(s).",
            level="success",
        )

    @admin.action(description="Enable selected accounts")
    def enable_accounts(self, request, queryset):
        updated = queryset.update(is_enabled=True)
        self.message_user(request, f"{updated} account(s) enabled.", level="success")

    @admin.action(description="Disable selected accounts")
    def disable_accounts(self, request, queryset):
        updated = queryset.update(is_enabled=False)
        self.message_user(request, f"{updated} account(s) disabled.", level="success")


@admin.register(GetResponseCampaign)
class GetResponseCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "account",
        "campaign_id",
        "is_active",
        "default_day_of_cycle",
        "language",
        "language_priority",
        "contact_count",
        "created_at",
    )
    list_filter = ("is_active", "language", "account")
    search_fields = ("name", "campaign_id", "account__name", "account__api_key")
    readonly_fields = ("created_at", "modified_at")
    actions = ["activate_campaigns", "deactivate_campaigns"]
    fieldsets = (
        (None, {"fields": ("account", "name", "campaign_id")}),
        ("Configuration", {"fields": ("language", "is_active", "default_day_of_cycle")}),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Language Priority")
    def language_priority(self, obj):
        if obj.language:
            return mark_safe(f"<strong>{obj.language.name_pl} ({obj.language.iso2})</strong> - Primary")
        return mark_safe("<em>All languages - Fallback</em>")

    @admin.display(description="Contacts")
    def contact_count(self, obj):
        return obj.contacts.count()

    @admin.action(description="Activate selected campaigns")
    def activate_campaigns(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} campaign(s) activated.", level="success")

    @admin.action(description="Deactivate selected campaigns")
    def deactivate_campaigns(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} campaign(s) deactivated.", level="success")


@admin.register(GetResponseContact)
class GetResponseContactAdmin(SyncStatusBadgeMixin, admin.ModelAdmin):
    list_display = (
        "form_email",
        "campaign",
        "contact_id",
        "sync_status_badge",
        "day_of_cycle",
        "scoring",
        "last_sync_at",
        "created_at",
    )
    list_filter = ("sync_status", "campaign", "campaign__account", "last_sync_at")
    search_fields = ("email", "campaign__name", "contact_id")
    readonly_fields = ("contact_id", "created_at", "modified_at", "last_sync_at", "error_message", "payload_preview")

    fieldsets = (
        (None, {"fields": ("campaign", "email")}),
        ("Contact Settings", {"fields": ("day_of_cycle", "scoring", "tags", "custom_field_values")}),
        ("GetResponse Sync", {"fields": ("contact_id", "sync_status", "last_sync_at", "error_message")}),
        ("API Preview", {"fields": ("payload_preview",), "classes": ("collapse",)}),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Email")
    def form_email(self, obj):
        return obj.email

    @admin.display(description="API Payload Preview")
    def payload_preview(self, obj):
        import json

        payload = obj.generate_payload()
        formatted = json.dumps(payload, indent=2, ensure_ascii=False)
        return mark_safe(f"<pre>{formatted}</pre>")


@admin.register(CategorySync)
class CategorySyncAdmin(SyncStatusBadgeMixin, ApiDataPreviewMixin, ResyncActionMixin, admin.ModelAdmin):
    list_display = (
        "product_category_name",
        "channel",
        "shop",
        "sync_status_badge",
        "gr_category_id",
        "last_sync_at",
        "sync_attempts",
    )
    list_filter = ("sync_status", "channel", "shop", "last_sync_at")
    search_fields = ("product_category__name", "product_category__idx", "gr_category_id", "external_id")
    readonly_fields = ("created_at", "modified_at", "request_preview", "response_preview")
    autocomplete_fields = ["channel", "product_category"]
    raw_id_fields = ["shop"]
    actions = ["mark_for_resync"]
    resync_success_message = "{count} category sync(s) marked for re-sync. Run export command to sync."

    fieldsets = (
        (None, {"fields": ("channel", "shop", "product_category")}),
        ("GetResponse Info", {"fields": ("gr_shop_id", "gr_category_id", "external_id")}),
        ("Sync Status", {"fields": ("sync_status", "last_sync_at", "sync_attempts", "error_message")}),
        ("API Data", {"fields": ("request_preview", "response_preview"), "classes": ("collapse",)}),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Category")
    def product_category_name(self, obj):
        return obj.product_category.name if obj.product_category else "N/A"


@admin.register(ProductSync)
class ProductSyncAdmin(SyncStatusBadgeMixin, ApiDataPreviewMixin, ResyncActionMixin, admin.ModelAdmin):
    list_display = ("product_sku", "shop", "sync_status_badge", "gr_product_id", "last_sync_at", "sync_attempts")
    list_filter = ("sync_status", "shop", "last_sync_at", "product__product_class")
    search_fields = ("product__real_product__sku", "gr_product_id", "external_id")
    readonly_fields = ("created_at", "modified_at", "request_preview", "response_preview")
    autocomplete_fields = ["shop", "product"]
    actions = ["mark_for_resync"]
    resync_success_message = (
        "{count} product sync(s) marked for re-sync. Run sync-products-to-getresponse command to sync."
    )

    fieldsets = (
        (None, {"fields": ("shop", "product")}),
        ("GetResponse Info", {"fields": ("gr_product_id", "external_id")}),
        ("Sync Status", {"fields": ("sync_status", "last_sync_at", "sync_attempts", "error_message")}),
        ("API Data", {"fields": ("request_preview", "response_preview"), "classes": ("collapse",)}),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Product SKU")
    def product_sku(self, obj):
        if not obj.product:
            return "N/A"
        try:
            return obj.product.sku
        except Exception as e:
            return f"[broken] product_id={obj.product_id} ({e.__class__.__name__}: {e})"


@admin.register(CartSync)
class CartSyncAdmin(SyncStatusBadgeMixin, ApiDataPreviewMixin, ResyncActionMixin, admin.ModelAdmin):
    list_display = (
        "cart_id_short",
        "shop",
        "sync_status_badge",
        "gr_cart_id",
        "total_price",
        "currency",
        "last_sync_at",
    )
    list_filter = ("sync_status", "shop", "currency", "last_sync_at")
    search_fields = ("cart_id", "gr_cart_id", "contact_id", "external_id")
    readonly_fields = ("created_at", "modified_at", "request_preview", "response_preview")
    raw_id_fields = ["shop"]
    actions = ["mark_for_resync"]
    resync_success_message = "{count} cart sync(s) marked for re-sync."

    fieldsets = (
        (None, {"fields": ("shop", "cart_id", "contact_id")}),
        ("GetResponse Info", {"fields": ("gr_cart_id", "external_id")}),
        ("Cart Data", {"fields": ("total_price", "currency", "selected_variants")}),
        ("Sync Status", {"fields": ("sync_status", "last_sync_at", "sync_attempts", "error_message")}),
        ("API Data", {"fields": ("request_preview", "response_preview"), "classes": ("collapse",)}),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Cart ID")
    def cart_id_short(self, obj):
        return f"{obj.cart_id[:8]}..." if len(obj.cart_id) > 8 else obj.cart_id


@admin.register(OrderSync)
class OrderSyncAdmin(SyncStatusBadgeMixin, ApiDataPreviewMixin, ResyncActionMixin, admin.ModelAdmin):
    list_display = (
        "order_id_short",
        "shop",
        "sync_status_badge",
        "status",
        "gr_order_id",
        "total_price",
        "currency",
        "last_sync_at",
    )
    list_filter = ("sync_status", "status", "shop", "currency", "last_sync_at")
    search_fields = ("order_id", "gr_order_id", "contact_id", "external_id")
    readonly_fields = ("created_at", "modified_at", "request_preview", "response_preview")
    raw_id_fields = ["shop"]
    actions = ["mark_for_resync"]
    resync_success_message = "{count} order sync(s) marked for re-sync."

    fieldsets = (
        (None, {"fields": ("shop", "order_id", "contact_id")}),
        ("GetResponse Info", {"fields": ("gr_order_id", "external_id", "status")}),
        ("Order Data", {"fields": ("total_price", "currency", "processed_at", "selected_variants")}),
        ("Addresses", {"fields": ("billing_address", "shipping_address"), "classes": ("collapse",)}),
        ("Sync Status", {"fields": ("sync_status", "last_sync_at", "sync_attempts", "error_message")}),
        ("API Data", {"fields": ("request_preview", "response_preview"), "classes": ("collapse",)}),
        ("Timestamps", {"fields": ("created_at", "modified_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Order ID")
    def order_id_short(self, obj):
        return f"{obj.order_id[:8]}..." if len(obj.order_id) > 8 else obj.order_id
