# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from celery import shared_task
from process_logger import ProcessLogger

from django_getresponse.models import GetResponseAccount, GetResponseShop
from django_getresponse.services.product_sync_service import ProductSyncContext, ProductSyncService


@shared_task(queue="pim_pull")
def sync_products_to_getresponse(runned_at: str, shop_idx: str | None = None, force: bool = False, log_level: int = 10):
    logger = ProcessLogger("SYNC_PRODUCTS_TO_GETRESPONSE")
    logger.setLevel(log_level)
    logger.add_log_param("runned_at", runned_at)
    logger.add_log_param("shop_idx", shop_idx)
    logger.add_log_param("force", force)

    try:
        shops = _get_shops(shop_idx, logger)
        if not shops:
            return _error_response("No synced shops found")

        overall = {"total": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

        for shop in shops:
            logger.add_log_param("gr_shop_name", shop.name)
            account = _get_account(shop, logger)
            if not account:
                overall["failed"] += 1
                continue

            products = _get_products_to_sync(shop, logger)
            if not products:
                continue

            stats = _sync_products(products, shop, account, force, logger)
            for key in overall:
                overall[key] += stats.get(key, 0)
            _log_completion(stats, logger)

        logger.delete_log_param("gr_shop_name")
        return _success_response_with_stats(overall)

    except Exception as e:
        error_msg = f"Task failed with error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return _error_response(error_msg)


def _get_shops(shop_idx: str | None, logger) -> list[GetResponseShop]:
    qs = GetResponseShop.objects.filter(sync_status="synced").select_related(
        "channel", "currency", "language", "external_language"
    )
    if shop_idx:
        qs = qs.filter(channel__idx=shop_idx)
    shops = list(qs)
    if not shops:
        logger.error(f"No synced GetResponseShop found for shop_idx='{shop_idx}'")
        return []
    logger.info(f"Found {len(shops)} synced shop(s) to process")
    return shops


def _get_account(shop: GetResponseShop, logger) -> GetResponseAccount | None:
    account = GetResponseAccount.objects.filter(channel=shop.channel, is_enabled=True).first()
    if not account:
        logger.error(f"No enabled GetResponse account for channel '{shop.channel.idx}'")
        return None
    logger.info(f"GetResponse account: {account.name or account.api_key[:12]}...")
    return account


def _get_products_to_sync(shop: GetResponseShop, logger):
    """Enabled products for the channel, excluding configurable sub-products.

    A simple product that is a variant of a configurable (has configurable_links) is synced
    as a variant inside that configurable's GR entry, not as a standalone GR product.
    No ProductVisibility or category filtering.
    """
    from django_pim.models import Product

    products = (
        Product.objects.filter(is_enabled=True, shop__idx=shop.channel.idx)
        .filter(configurable_links__isnull=True)
        .order_by("id")
    )
    total = products.count()
    logger.info(f"Found {total} enabled products to sync for shop '{shop.name}'")
    return products


def _sync_products(products, shop, account, force, logger):
    service = ProductSyncService()
    context = ProductSyncContext(shop=shop, api_key=account.api_key, force=force)
    return service.sync_products_batch(list(products), context)


def _log_completion(stats: dict, logger):
    logger.info(
        f"Sync completed: total={stats['total']}, "
        f"created={stats['created']}, updated={stats['updated']}, "
        f"skipped={stats['skipped']}, failed={stats['failed']}"
    )


def _error_response(error_msg: str) -> dict:
    return {"success": False, "error": error_msg}


def _success_response_no_products() -> dict:
    return {"success": True, "total": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}


def _success_response_with_stats(stats: dict) -> dict:
    return {"success": True, **stats}
