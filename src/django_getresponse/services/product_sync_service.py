# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass

from django.db import transaction
from get_response_sdk import GetResponseClient
from process_logger import ProcessLogger

from django_getresponse.dto.product import GetResponseProductDTO, GetResponseProductVariantDTO
from django_getresponse.models import CategorySync, ProductSync, ProductSyncStatus


class ProductSkip(Exception):
    """Raised when a product has nothing valid to sync and must be skipped (not failed).

    GetResponse requires at least one priced variant. A configurable with zero priced
    variants, or a simple product without a price (e.g. not priced for this shop's
    country/currency), is skipped rather than marked failed.
    """


@dataclass
class ProductSyncResult:
    success: bool
    message: str


@dataclass
class ProductSyncStats:
    total: int
    created: int = 0
    updated: int = 0
    failed: int = 0
    skipped: int = 0

    def increment_created(self):
        self.created += 1

    def increment_updated(self):
        self.updated += 1

    def increment_failed(self):
        self.failed += 1

    def increment_skipped(self):
        self.skipped += 1

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "failed": self.failed,
            "skipped": self.skipped,
        }


@dataclass
class ProductSyncContext:
    shop: "GetResponseShop"
    api_key: str
    force: bool = False


class ProductSyncService:
    def __init__(self, gr_client: GetResponseClient | None = None):
        self.gr_client = gr_client or GetResponseClient()
        self.logger = ProcessLogger("ProductSyncService")
        self.context: ProductSyncContext | None = None
        self.sync_record: ProductSync | None = None
        self.product = None

    @transaction.atomic
    def sync_product(self, product, context: ProductSyncContext) -> ProductSyncResult:
        self._initialize_sync(product, context)
        try:
            if self._should_skip_sync():
                return ProductSyncResult(True, f"Already synced: {product.sku}")
            return self._perform_sync()
        except ProductSkip as skip:
            return self._handle_product_skip(skip)

    def _initialize_sync(self, product, context: ProductSyncContext) -> None:
        self.product = product
        self.context = context
        self.sync_record = self._get_or_create_sync_record()

    def _get_or_create_sync_record(self) -> ProductSync:
        external_id = self.product.sku
        defaults = self._build_sync_defaults(external_id)
        sync_record, _ = ProductSync.objects.get_or_create(
            shop=self.context.shop, product=self.product, defaults=defaults
        )
        return sync_record

    def _build_sync_defaults(self, external_id: str) -> dict:
        return {
            "external_id": external_id,
            "sync_status": ProductSyncStatus.PENDING,
        }

    def _should_skip_sync(self) -> bool:
        if not self._is_already_synced():
            return False
        return self._should_skip_synced_product()

    def _is_already_synced(self) -> bool:
        return self.sync_record.is_synced

    def _should_skip_synced_product(self) -> bool:
        if self.context.force:
            return False
        return self._check_and_log_if_unchanged()

    def _check_and_log_if_unchanged(self) -> bool:
        if not self._has_data_changed():
            self._log_no_changes()
            return True
        return False

    def _log_no_changes(self) -> None:
        self.logger.add_log_param_once("sku", self.product.sku)
        self.logger.info("Product no changes, skipping")

    def _has_data_changed(self) -> bool:
        current_payload = self._generate_current_payload()
        return current_payload != self.sync_record.last_request_data

    def _generate_current_payload(self) -> dict:
        product_dto = self._create_product_dto()
        return product_dto.to_create_payload()

    def _perform_sync(self) -> ProductSyncResult:
        self.sync_record.increment_attempts()
        try:
            return self._sync_with_api()
        except ProductSkip:
            raise
        except Exception as e:
            return self._handle_sync_failure(e)

    def _sync_with_api(self) -> ProductSyncResult:
        product_dto = self._create_product_dto()
        self.sync_record.last_request_data = product_dto.to_create_payload()
        existing = self._find_existing_product()
        return self._upsert_product(existing, product_dto)

    def _create_product_dto(self) -> GetResponseProductDTO:
        lang = self._get_language()
        variants = self._build_variants_dto(lang)
        categories = self._get_category_gr_ids()
        url = self._get_product_url(lang)
        try:
            return GetResponseProductDTO.from_pim_product(
                product=self.product,
                variants_dto=variants,
                url=url,
                categories=categories,
                lang=lang,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to build product DTO for product_id={self.product.id}: {e.__class__.__name__}: {e}"
            ) from e

    def _get_language(self) -> str:
        return self.context.shop.language.iso2

    def _build_variants_dto(self, lang: str) -> list[GetResponseProductVariantDTO]:
        if self._is_configurable():
            return self._build_configurable_variants(lang)
        return self._build_simple_variant(lang)

    def _is_configurable(self) -> bool:
        from django_pim.models.product_configurable import ProductConfigurable

        return isinstance(self.product.as_child, ProductConfigurable)

    def _build_configurable_variants(self, lang: str) -> list[GetResponseProductVariantDTO]:
        """Build variants for configurable product.

        Uses select_related to avoid N+1 queries on subproducts.
        Deduplicates by SKU — GetResponse rejects duplicate variant SKUs.
        """
        configurable = self.product.as_child
        subproduct_links = configurable.subproduct_links.select_related("subproduct").all()

        variants = []
        seen_skus: set[str] = set()
        skipped_no_price = 0
        for link in subproduct_links:
            sku = link.subproduct.sku
            if sku in seen_skus:
                continue
            seen_skus.add(sku)
            variant_dto = self._create_variant_dto(link.subproduct, lang)
            if variant_dto is None:
                # Sub-product without a price: skip it but still sync the config with the rest.
                skipped_no_price += 1
                self.logger.warning(f"Skipping variant {sku} (product_id={link.subproduct.id}): no price")
                continue
            variants.append(variant_dto)

        if not variants:
            raise ProductSkip(
                f"Configurable product {self.product.sku} has no priced variants to sync "
                f"({skipped_no_price} sub-product(s) skipped for missing price)"
            )
        return variants

    def _build_simple_variant(self, lang: str) -> list[GetResponseProductVariantDTO]:
        variant_dto = self._create_variant_dto(self.product, lang)
        if variant_dto is None:
            raise ProductSkip(f"No price found for product {self.product.sku}")
        return [variant_dto]

    def _create_variant_dto(self, product, lang: str) -> GetResponseProductVariantDTO | None:
        """Build a variant DTO, or return None when the product has no price (caller decides to skip)."""
        price = self._get_product_price(product)
        if price is None:
            return None
        try:
            url = self._get_product_url(lang, product)
            media_url = self._get_media_url()
            return GetResponseProductVariantDTO.from_pim_product(
                product=product, price=price, url=url, lang=lang, media_url=media_url
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to build variant DTO for product_id={product.id}: {e.__class__.__name__}: {e}"
            ) from e

    def _get_country_code(self) -> str:
        if not self.context.shop.price_country:
            raise ValueError(
                f"GetResponseShop '{self.context.shop.name}' (id={self.context.shop.id}) "
                f"has no price_country configured. Please set price_country in Django admin."
            )
        return self.context.shop.price_country.iso2

    def _get_media_url(self) -> str:
        from django_getresponse.settings import MEDIA_URL

        return MEDIA_URL

    def _get_product_price(self, product):
        """Return the product price, or None when no price is configured (caller decides to skip)."""
        result = self._fetch_price_from_pricemanager(product)
        if not result or not result.get("price"):
            return None
        return result["price"]

    def _fetch_price_from_pricemanager(self, product):
        from django_pricemanager.output import get_product_price_for_country_and_currency

        return get_product_price_for_country_and_currency(
            channel_idx=self.context.shop.channel.idx,
            product_sku=product.sku,
            country_code=self._get_country_code(),
            currency_code=self.context.shop.currency.iso3,
        )

    def _get_product_url(self, lang: str, product=None) -> str | None:
        from django_getresponse.settings import USE_CONFIG_URL_KEY

        if product is None or USE_CONFIG_URL_KEY:
            product = self.product
        url_key = self._get_product_url_key(product, lang)
        if not url_key:
            return None
        return self._build_product_url(url_key)

    def _get_product_url_key(self, product, lang: str) -> str | None:
        from django.core.exceptions import ObjectDoesNotExist

        try:
            url_key = product.url_key_lang(lang)
        except ObjectDoesNotExist:
            self.logger.warning(f"No url_key ProductAttribute for product_id={product.id}, skipping URL")
            return None
        if url_key == product.sku:
            return None
        return url_key

    def _build_product_url(self, url_key: str) -> str:
        base_url = self._get_shop_base_url()
        return f"{base_url}/{url_key}"

    def _get_shop_base_url(self) -> str:
        return self.context.shop.domain_url.rstrip("/")

    def _get_category_gr_ids(self) -> list[dict]:
        categories = self.product.categories.filter(is_active=True)
        synced_categories = CategorySync.objects.filter(
            shop=self.context.shop, product_category__in=categories, sync_status="synced"
        ).select_related("product_category")
        return self._build_category_objects(synced_categories)

    def _build_category_objects(self, synced_categories) -> list[dict]:
        lang = self._get_language()
        return [self._build_category_dict(cat, lang) for cat in synced_categories]

    def _build_category_dict(self, cat, lang) -> dict:
        return {"categoryId": cat.gr_category_id, "name": cat.product_category.name_lang(lang)}

    def _find_existing_product(self) -> dict | None:
        try:
            products = self.gr_client.get_products(
                shop_id=self.context.shop.gr_shop_id,
                api_key=self.context.api_key,
                query={"externalId": self.sync_record.external_id},
            )
            return products[0] if products and len(products) > 0 else None
        except Exception as e:
            self._log_find_error(e)
            return None

    def _log_find_error(self, error: Exception) -> None:
        self.logger.add_log_param_once("external_id", self.sync_record.external_id)
        self.logger.add_log_param_once("error", str(error))
        self.logger.warning("Error finding product by externalId")

    def _upsert_product(self, existing: dict | None, product_dto: GetResponseProductDTO) -> ProductSyncResult:
        if existing:
            return self._update_existing_product(existing, product_dto)
        return self._create_new_product(product_dto)

    def _update_existing_product(self, existing: dict, product_dto: GetResponseProductDTO) -> ProductSyncResult:
        gr_product_id = existing.get("productId")
        payload = product_dto.to_update_payload()
        status_code, response_data = self.gr_client.update_product(
            shop_id=self.context.shop.gr_shop_id,
            product_id=gr_product_id,
            product_data=payload,
            api_key=self.context.api_key,
        )
        return self._handle_update_response(status_code, response_data, gr_product_id, product_dto)

    def _handle_api_response(
        self,
        status_code: int,
        response_data: dict,
        product_dto: GetResponseProductDTO,
        success_codes: list[int],
        action: str,
    ) -> ProductSyncResult:
        """Handle API response for create/update operations.

        Args:
            status_code: HTTP status code from API
            response_data: Response data from API
            product_dto: Product DTO
            success_codes: List of success status codes
            action: Action name for logging ("Created" or "Updated")

        Returns:
            ProductSyncResult with success/failure status
        """
        if status_code in success_codes:
            gr_product_id = response_data.get("productId")
            self.sync_record.mark_as_synced(gr_product_id, response_data)
            self.sync_record.save()
            self.logger.add_log_param_once("action", action)
            self.logger.add_log_param_once("product_name", product_dto.name)
            self.logger.add_log_param_once("gr_product_id", gr_product_id)
            self.logger.info("Product synced in GetResponse")
            return ProductSyncResult(True, f"{action}: {product_dto.name}")

        error_msg = f"Failed to {action.lower()} product (HTTP {status_code})"
        self.sync_record.mark_as_failed(error_msg)
        self.sync_record.save()
        return ProductSyncResult(False, error_msg)

    def _handle_update_response(
        self, status_code: int, response_data: dict, gr_product_id: str, product_dto: GetResponseProductDTO
    ) -> ProductSyncResult:
        """Handle update response (delegates to common handler)."""
        return self._handle_api_response(
            status_code=status_code,
            response_data=response_data,
            product_dto=product_dto,
            success_codes=[200],
            action="Updated",
        )

    def _create_new_product(self, product_dto: GetResponseProductDTO) -> ProductSyncResult:
        payload = product_dto.to_create_payload()
        status_code, response_data = self.gr_client.create_product(
            shop_id=self.context.shop.gr_shop_id, product_data=payload, api_key=self.context.api_key
        )
        return self._handle_create_response(status_code, response_data, product_dto)

    def _handle_create_response(
        self, status_code: int, response_data: dict, product_dto: GetResponseProductDTO
    ) -> ProductSyncResult:
        """Handle create response (delegates to common handler)."""
        return self._handle_api_response(
            status_code=status_code,
            response_data=response_data,
            product_dto=product_dto,
            success_codes=[200, 201],
            action="Created",
        )

    def _handle_sync_failure(self, error: Exception) -> ProductSyncResult:
        import traceback

        try:
            product_label = self.product.sku
        except Exception:
            product_label = f"product_id={self.product.id}"
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        error_detail = f"{error.__class__.__name__}: {error}\n\nTraceback:\n{tb}"
        self.logger.exception(f"Error syncing product {product_label}: {error}")
        self.sync_record.mark_as_failed(error_detail)
        self.sync_record.save()
        return ProductSyncResult(False, f"Failed to sync {product_label}: {error}")

    def _handle_product_skip(self, skip: ProductSkip) -> ProductSyncResult:
        try:
            product_label = self.product.sku
        except Exception:
            product_label = f"product_id={self.product.id}"
        self.logger.add_log_param_once("sku", product_label)
        self.logger.warning(f"Skipping product {product_label}: {skip}")
        return ProductSyncResult(True, f"Skipped: {skip}")

    def sync_products_batch(self, products: list, context: ProductSyncContext) -> dict:
        stats = ProductSyncStats(total=len(products))
        for product in products:
            self._sync_single_product_in_batch(product, context, stats)
        return stats.to_dict()

    def _sync_single_product_in_batch(self, product, context: ProductSyncContext, stats: ProductSyncStats) -> None:
        result = self.sync_product(product, context)
        self._update_batch_stats(result, stats)
        self._log_batch_progress(result, stats)

    def _update_batch_stats(self, result: ProductSyncResult, stats: ProductSyncStats) -> None:
        if not result.success:
            stats.increment_failed()
        elif "Created" in result.message:
            stats.increment_created()
        elif "Updated" in result.message:
            stats.increment_updated()
        elif "Already synced" in result.message or result.message.startswith("Skipped"):
            stats.increment_skipped()

    def _log_batch_progress(self, result: ProductSyncResult, stats: ProductSyncStats) -> None:
        pass
