# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from get_response_sdk import GetResponseClient
from process_logger import ProcessLogger

from django_getresponse.dto.category import GetResponseCategoryDTO
from django_getresponse.models import CategorySync, CategorySyncStatus, Channel


@dataclass
class CategorySyncResult:
    success: bool
    message: str


@dataclass
class CategorySyncStats:
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
class CategorySyncContext:
    channel: Channel
    gr_shop_id: str
    api_key: str
    shop: Optional["GetResponseShop"] = None
    parent_gr_category_id: str | None = None
    force: bool = False


class CategorySyncService:
    def __init__(self, gr_client: GetResponseClient | None = None):
        self.gr_client = gr_client or GetResponseClient()
        self.logger = ProcessLogger("CategorySyncService")
        self.context: CategorySyncContext | None = None
        self.sync_record: CategorySync | None = None
        self.product_category = None

    @transaction.atomic
    def sync_category(self, product_category, context: CategorySyncContext) -> CategorySyncResult:
        self._initialize_sync(product_category, context)
        if self._should_skip_sync():
            return CategorySyncResult(True, f"Already synced: {product_category.name}")
        return self._perform_sync()

    def _initialize_sync(self, product_category, context: CategorySyncContext) -> None:
        self.product_category = product_category
        self.context = context
        self.sync_record = self._get_or_create_sync_record()

    def _get_or_create_sync_record(self) -> CategorySync:
        external_id = f"pim_cat_{self.product_category.id}"
        sync_record, _ = CategorySync.objects.get_or_create(
            shop=self.context.shop,
            product_category=self.product_category,
            defaults={
                "channel": self.context.channel,
                "gr_shop_id": self.context.gr_shop_id,
                "external_id": external_id,
                "sync_status": CategorySyncStatus.PENDING,
            },
        )
        return sync_record

    def _should_skip_sync(self) -> bool:
        if not self._is_already_synced():
            return False
        return self._should_skip_synced_category()

    def _is_already_synced(self) -> bool:
        return self.sync_record.is_synced

    def _should_skip_synced_category(self) -> bool:
        if self.context.force:
            return False
        return self._check_and_log_if_unchanged()

    def _check_and_log_if_unchanged(self) -> bool:
        if not self._has_data_changed():
            self._log_no_changes()
            return True
        return False

    def _log_no_changes(self) -> None:
        pass

    def _has_data_changed(self) -> bool:
        current_payload = self._generate_current_payload()
        return current_payload != self.sync_record.last_request_data

    def _generate_current_payload(self) -> dict:
        category_dto = self._create_category_dto()
        return category_dto.to_create_payload()

    def _perform_sync(self) -> CategorySyncResult:
        self.sync_record.increment_attempts()
        try:
            return self._sync_with_api()
        except Exception as e:
            return self._handle_sync_failure(e)

    def _sync_with_api(self) -> CategorySyncResult:
        category_dto = self._create_category_dto()
        self.sync_record.last_request_data = category_dto.to_create_payload()
        existing = self._find_existing_category()
        return self._upsert_category(existing, category_dto)

    def _create_category_dto(self) -> GetResponseCategoryDTO:
        category_url = self._build_category_url()
        return GetResponseCategoryDTO.from_product_category(
            product_category=self.product_category,
            parent_gr_category_id=self.context.parent_gr_category_id,
            category_url=category_url,
        )

    def _build_category_url(self) -> str | None:
        if not self.context.shop:
            return None
        if not self.context.shop.domain_url_categories:
            return None
        url_key = self._get_category_url_key()
        if not url_key:
            return None
        return self._construct_full_url(url_key)

    def _get_category_url_key(self) -> str | None:
        lang = self._get_language()
        url_key = self.product_category.url_key_lang(lang)
        return url_key if url_key else None

    def _get_language(self) -> str:
        return self.context.shop.language.iso2

    def _construct_full_url(self, url_key: str) -> str:
        base_url = self.context.shop.domain_url_categories.rstrip("/")
        return f"{base_url}/{url_key}"

    def _find_existing_category(self) -> dict | None:
        try:
            categories = self.gr_client.get_shop_categories(
                shop_id=self.context.gr_shop_id,
                api_key=self.context.api_key,
                query={"externalId": self.sync_record.external_id},
            )
            return categories[0] if categories and len(categories) > 0 else None
        except Exception as e:
            self._log_find_error(e)
            return None

    def _log_find_error(self, error: Exception) -> None:
        self.logger.exception(error)

    def _upsert_category(self, existing: dict | None, category_dto: GetResponseCategoryDTO) -> CategorySyncResult:
        if existing:
            return self._update_existing_category(existing, category_dto)
        return self._create_new_category(category_dto)

    def _update_existing_category(self, existing: dict, category_dto: GetResponseCategoryDTO) -> CategorySyncResult:
        gr_category_id = existing.get("categoryId")
        payload = category_dto.to_update_payload()
        status_code, response_data = self.gr_client.update_category(
            shop_id=self.context.gr_shop_id,
            category_id=gr_category_id,
            category_data=payload,
            api_key=self.context.api_key,
        )
        return self._handle_update_response(status_code, response_data, gr_category_id, category_dto)

    def _handle_update_response(
        self, status_code: int, response_data: dict, gr_category_id: str, category_dto: GetResponseCategoryDTO
    ) -> CategorySyncResult:
        if status_code == 200:
            self.sync_record.mark_as_synced(gr_category_id, response_data)
            self.sync_record.save()
            self._log_update_success(category_dto, gr_category_id)
            return CategorySyncResult(True, f"Updated: {category_dto.name}")
        return self._handle_update_failure(status_code)

    def _log_update_success(self, category_dto: GetResponseCategoryDTO, gr_category_id: str) -> None:
        self.logger.add_log_param_once("category_name", category_dto.name)
        self.logger.add_log_param_once("gr_category_id", gr_category_id)
        self.logger.info("Updated category")

    def _handle_update_failure(self, status_code: int) -> CategorySyncResult:
        error_msg = f"Failed to update category (HTTP {status_code})"
        self.sync_record.mark_as_failed(error_msg)
        self.sync_record.save()
        return CategorySyncResult(False, error_msg)

    def _create_new_category(self, category_dto: GetResponseCategoryDTO) -> CategorySyncResult:
        payload = category_dto.to_create_payload()
        status_code, response_data = self.gr_client.create_category(
            shop_id=self.context.gr_shop_id, category_data=payload, api_key=self.context.api_key
        )
        return self._handle_create_response(status_code, response_data, category_dto)

    def _handle_create_response(
        self, status_code: int, response_data: dict, category_dto: GetResponseCategoryDTO
    ) -> CategorySyncResult:
        if status_code in [200, 201]:
            gr_category_id = response_data.get("categoryId")
            self.sync_record.mark_as_synced(gr_category_id, response_data)
            self.sync_record.save()
            self._log_create_success(category_dto, gr_category_id)
            return CategorySyncResult(True, f"Created: {category_dto.name}")
        return self._handle_create_failure(status_code)

    def _log_create_success(self, category_dto: GetResponseCategoryDTO, gr_category_id: str) -> None:
        self.logger.add_log_param_once("category_name", category_dto.name)
        self.logger.add_log_param_once("gr_category_id", gr_category_id)
        self.logger.info("Created category in GetResponse")

    def _handle_create_failure(self, status_code: int) -> CategorySyncResult:
        error_msg = f"Failed to create category (HTTP {status_code})"
        self.sync_record.mark_as_failed(error_msg)
        self.sync_record.save()
        return CategorySyncResult(False, error_msg)

    def _handle_sync_failure(self, error: Exception) -> CategorySyncResult:
        self.logger.add_log_param_once("product_category_id", self.product_category.id)
        self.logger.exception(error)
        self.sync_record.mark_as_failed(str(error))
        self.sync_record.save()
        return CategorySyncResult(False, f"Failed to sync {self.product_category.name}: {str(error)}")

    def sync_categories_batch(self, product_categories: list, context: CategorySyncContext) -> dict:
        stats = CategorySyncStats(total=len(product_categories))
        for product_category in product_categories:
            self._sync_single_category_in_batch(product_category, context, stats)
        return stats.to_dict()

    def _sync_single_category_in_batch(
        self, product_category, context: CategorySyncContext, stats: CategorySyncStats
    ) -> None:
        parent_context = self._create_context_with_parent(product_category, context)
        result = self.sync_category(product_category, parent_context)
        self._update_batch_stats(result, stats)
        self._log_batch_progress(result, stats)

    def _create_context_with_parent(self, product_category, base_context: CategorySyncContext) -> CategorySyncContext:
        parent_gr_id = self._get_parent_category_id(product_category)
        return CategorySyncContext(
            channel=base_context.channel,
            gr_shop_id=base_context.gr_shop_id,
            api_key=base_context.api_key,
            shop=base_context.shop,
            parent_gr_category_id=parent_gr_id,
            force=base_context.force,
        )

    def _get_parent_category_id(self, product_category) -> str | None:
        if not product_category.parent_category:
            return None
        parent_sync = CategorySync.objects.filter(
            shop=self.context.shop, product_category=product_category.parent_category
        ).first()
        return parent_sync.gr_category_id if parent_sync and parent_sync.gr_category_id else None

    def _update_batch_stats(self, result: CategorySyncResult, stats: CategorySyncStats) -> None:
        if not result.success:
            stats.increment_failed()
        elif "Created" in result.message:
            stats.increment_created()
        elif "Updated" in result.message:
            stats.increment_updated()
        elif "Already synced" in result.message:
            stats.increment_skipped()

    def _log_batch_progress(self, result: CategorySyncResult, stats: CategorySyncStats) -> None:
        pass
