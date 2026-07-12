# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from celery import shared_task
from process_logger import ProcessLogger

from django_getresponse.models import Channel, GetResponseAccount, GetResponseShop
from django_getresponse.services.shop_sync_service import ShopSyncService


@shared_task(queue="pim_pull")
def sync_shops_to_getresponse(runned_at: str, channel_idx: str | None = None, force: bool = False, log_level: int = 10):
    """
    Celery task for synchronizing GetResponse shops.

    Args:
        runned_at: Timestamp when task was triggered
        channel_idx: Optional channel idx to filter shops
        force: Force update even if already synced
        log_level: Logging level (default: DEBUG=10)
    """
    logger = ProcessLogger("SYNC_SHOPS_TO_GETRESPONSE")
    logger.setLevel(log_level)
    logger.add_log_param("runned_at", runned_at)
    logger.add_log_param("channel_idx", channel_idx)
    logger.add_log_param("force", force)

    try:
        service = ShopSyncService()

        shops_queryset = GetResponseShop.objects.select_related("channel", "currency", "language", "external_language")

        if channel_idx:
            try:
                channel = Channel.objects.get(idx=channel_idx)
                shops_queryset = shops_queryset.filter(channel=channel)
                logger.info(f"Filtering shops for channel: {channel_idx}")
            except Channel.DoesNotExist:
                logger.error(f"Channel not found: {channel_idx}")
                return {"success": False, "error": f"Channel '{channel_idx}' not found"}

        shops = list(shops_queryset)
        total_shops = len(shops)

        if total_shops == 0:
            logger.warning("No shops found to synchronize")
            return {"success": True, "total": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

        channels_map = {}
        for shop in shops:
            if shop.channel.idx not in channels_map:
                channels_map[shop.channel.idx] = []
            channels_map[shop.channel.idx].append(shop)

        overall_stats = {"total": total_shops, "created": 0, "updated": 0, "skipped": 0, "failed": 0}

        for ch_idx, channel_shops in channels_map.items():
            try:
                account = GetResponseAccount.objects.get(channel__idx=ch_idx, is_enabled=True)
            except GetResponseAccount.DoesNotExist:
                logger.error(f"No enabled GetResponse account for channel: {ch_idx}")
                overall_stats["failed"] += len(channel_shops)
                continue

            stats = service.sync_shops_batch(shops=channel_shops, account=account, force=force)

            overall_stats["created"] += stats["created"]
            overall_stats["updated"] += stats["updated"]
            overall_stats["skipped"] += stats["skipped"]
            overall_stats["failed"] += stats["failed"]

            logger.info(
                f"Channel {ch_idx} results: "
                f"created={stats['created']}, "
                f"updated={stats['updated']}, "
                f"skipped={stats['skipped']}, "
                f"failed={stats['failed']}"
            )

        logger.info(
            f"Overall sync completed: "
            f"total={overall_stats['total']}, "
            f"created={overall_stats['created']}, "
            f"updated={overall_stats['updated']}, "
            f"skipped={overall_stats['skipped']}, "
            f"failed={overall_stats['failed']}"
        )

        return {"success": True, **overall_stats}

    except Exception as e:
        logger.error(f"Task failed with error: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}
