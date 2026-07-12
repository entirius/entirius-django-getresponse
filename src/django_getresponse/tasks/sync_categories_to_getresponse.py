# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from celery import shared_task
from django_pim.models import ProductCategory
from process_logger import ProcessLogger

from django_getresponse.models import Channel, GetResponseAccount, GetResponseShop
from django_getresponse.services.category_sync_service import CategorySyncContext, CategorySyncService


@shared_task(queue="pim_pull")
def sync_categories_to_getresponse(
    runned_at: str, channel_idx: str, gr_shop_id: str | None = None, force: bool = False, log_level: int = 10
):
    """
    Celery task for synchronizing categories to GetResponse.

    When gr_shop_id is provided, syncs to that specific shop only.
    When not provided, syncs to ALL synced shops for the channel
    (a channel may have multiple shops, e.g., one per language).

    Args:
        runned_at: Timestamp when task was triggered
        channel_idx: Channel idx (required)
        gr_shop_id: GetResponse shop ID (optional - syncs all channel shops if not provided)
        force: Force re-sync even if already synced
        log_level: Logging level (default: DEBUG=10)
    """
    logger = ProcessLogger("SYNC_CATEGORIES_TO_GETRESPONSE")
    logger.setLevel(log_level)
    logger.add_log_param("runned_at", runned_at)
    logger.add_log_param("channel_idx", channel_idx)
    logger.add_log_param("gr_shop_id", gr_shop_id)
    logger.add_log_param("force", force)

    try:
        channel = _get_channel(channel_idx, logger)
        if channel is None:
            return {"success": False, "error": f"Channel '{channel_idx}' not found"}

        account = _get_account(channel, channel_idx, logger)
        if account is None:
            return {"success": False, "error": f"No enabled GetResponse account for channel '{channel_idx}'"}

        pim_shop = _get_pim_shop(channel_idx, logger)
        if pim_shop is None:
            return {"success": False, "error": f"Shop '{channel_idx}' not found in django_pim"}

        categories = _get_categories(pim_shop, logger)
        if not categories:
            return {"success": True, "total": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

        gr_shops = _get_gr_shops(channel, gr_shop_id, logger)
        if not gr_shops:
            return {"success": False, "error": f"No synced GetResponseShop found for channel '{channel_idx}'"}

        return _sync_to_all_shops(gr_shops, categories, channel, account, force, logger)

    except Exception as e:
        error_msg = f"Task failed with error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}


def _get_channel(channel_idx: str, logger: ProcessLogger) -> Channel | None:
    try:
        channel = Channel.objects.get(idx=channel_idx)
        logger.info(f"Channel found: {channel.idx}")
        return channel
    except Channel.DoesNotExist:
        logger.error(f"Channel with idx='{channel_idx}' not found")
        return None


def _get_account(channel: Channel, channel_idx: str, logger: ProcessLogger) -> GetResponseAccount | None:
    account = GetResponseAccount.objects.filter(channel=channel, is_enabled=True).first()
    if not account:
        logger.error(f"No enabled GetResponse account found for channel '{channel_idx}'")
        return None
    logger.info(f"GetResponse account: {account.name or account.api_key[:12]}...")
    return account


def _get_pim_shop(channel_idx: str, logger: ProcessLogger):
    try:
        from django_pim.models import Shop

        shop = Shop.objects.get(idx=channel_idx)
        logger.info(f"PIM shop found: {shop.idx}")
        return shop
    except Exception:
        logger.error(f"Shop with idx='{channel_idx}' not found in django_pim")
        return None


def _get_categories(pim_shop, logger: ProcessLogger) -> list:
    categories = list(ProductCategory.objects.filter(shop=pim_shop).order_by("tree_deep", "position", "idx"))
    logger.info(f"Found {len(categories)} categories to sync")
    if not categories:
        logger.warning("No categories to sync")
    return categories


def _get_gr_shops(channel: Channel, gr_shop_id: str | None, logger: ProcessLogger) -> list[GetResponseShop]:
    if gr_shop_id:
        shop = GetResponseShop.objects.filter(channel=channel, gr_shop_id=gr_shop_id).first()
        if not shop:
            logger.error(f"GetResponseShop with gr_shop_id='{gr_shop_id}' not found")
            return []
        logger.info(f"Using specific GR shop: {shop.name} (GR ID: {gr_shop_id})")
        return [shop]

    shops = list(
        GetResponseShop.objects.filter(channel=channel, sync_status="synced").select_related(
            "language", "external_language"
        )
    )
    if not shops:
        logger.error(f"No synced GetResponseShop found for channel '{channel.idx}'")
        return []
    logger.info(f"Found {len(shops)} synced GR shop(s) for channel '{channel.idx}'")
    return shops


def _sync_to_all_shops(
    gr_shops: list[GetResponseShop],
    categories: list,
    channel: Channel,
    account: GetResponseAccount,
    force: bool,
    logger: ProcessLogger,
) -> dict:
    service = CategorySyncService()
    overall = {"total": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

    for gr_shop in gr_shops:
        logger.add_log_param("gr_shop_name", gr_shop.name)
        logger.info(f"Syncing categories to shop: {gr_shop.name} (GR ID: {gr_shop.gr_shop_id})")

        context = CategorySyncContext(
            channel=channel,
            gr_shop_id=gr_shop.gr_shop_id,
            api_key=account.api_key,
            shop=gr_shop,
            force=force,
        )
        stats = service.sync_categories_batch(product_categories=categories, context=context)

        for key in overall:
            overall[key] += stats.get(key, 0)

        logger.info(
            f"Shop '{gr_shop.name}': "
            f"total={stats['total']}, created={stats['created']}, "
            f"updated={stats['updated']}, skipped={stats['skipped']}, failed={stats['failed']}"
        )

    logger.delete_log_param("gr_shop_name")
    logger.info(
        f"Overall: shops={len(gr_shops)}, total={overall['total']}, "
        f"created={overall['created']}, updated={overall['updated']}, "
        f"skipped={overall['skipped']}, failed={overall['failed']}"
    )
    return {"success": True, **overall}
