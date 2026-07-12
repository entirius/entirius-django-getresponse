# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from django.db import transaction
from django.utils import timezone
from get_response_sdk import GetResponseClient
from process_logger import ProcessLogger

from django_getresponse.models import GetResponseAccount, GetResponseShop, ShopSyncStatus

logger = ProcessLogger("ShopSyncService")


class ShopSyncService:
    """
    Service for synchronizing GetResponseShop with GetResponse API.

    This service follows Clean Code and DDD principles:
    - Single Responsibility: Only handles shop synchronization
    - Dependency Injection: Receives dependencies through constructor
    - Domain-driven: Operates on domain models (GetResponseShop)
    """

    def __init__(self, gr_client: GetResponseClient | None = None):
        """
        Initialize service with GetResponse client.

        Args:
            gr_client: GetResponse API client (injected dependency)
        """
        self.gr_client = gr_client or GetResponseClient()

    @transaction.atomic
    def sync_shop(self, shop: GetResponseShop, account: GetResponseAccount, force: bool = False) -> tuple[bool, str]:
        """
        Synchronize single GetResponseShop with GetResponse API.

        Args:
            shop: GetResponseShop instance to synchronize
            account: GetResponseAccount with API credentials
            force: Force update even if already synced

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if shop.is_synced and not force:
                logger.add_log_param_once("shop_name", shop.name)
                logger.add_log_param_once("gr_shop_id", shop.gr_shop_id)
                logger.info("Shop already synced")
                return True, f"Shop '{shop.name}' already synced"

            payload = shop.to_getresponse_payload()
            logger.add_log_param("shop_name", shop.name)

            try:
                if shop.gr_shop_id:
                    status_code, response_data = self.gr_client.update_shop(
                        shop_id=shop.gr_shop_id, shop_data=payload, api_key=account.api_key
                    )
                    operation = "updated"
                    logger.add_log_param_once("status_code", status_code)
                    logger.info("Shop updated")
                else:
                    status_code, response_data = self.gr_client.create_shop(shop_data=payload, api_key=account.api_key)
                    operation = "created"
                    shop_id = response_data.get("shopId")
                    if not shop_id:
                        raise ValueError(f"No shopId in response: {response_data}")

                    shop.gr_shop_id = shop_id
                    logger.add_log_param_once("shop_id", shop_id)
                    logger.info("Shop created")
            except (ValueError, ConnectionError) as api_error:
                error_msg = str(api_error)
                logger.add_log_param_once("error", error_msg)
                logger.error("GetResponse API error for shop")
                raise
            finally:
                logger.delete_log_param("shop_name")

            shop.sync_status = ShopSyncStatus.SYNCED
            shop.last_sync_at = timezone.now()
            shop.error_message = ""
            shop.save()

            success_msg = f"Shop '{shop.name}' {operation} successfully"
            return True, success_msg

        except Exception as e:
            logger.add_log_param_once("shop_name", shop.name)
            logger.add_log_param_once("error", str(e))
            logger.error("Failed to sync shop")

            shop.sync_status = ShopSyncStatus.FAILED
            shop.error_message = str(e)
            shop.save()

            error_msg = f"Failed to sync shop '{shop.name}': {str(e)}"
            return False, error_msg

    def sync_shops_batch(self, shops: list[GetResponseShop], account: GetResponseAccount, force: bool = False) -> dict:
        """
        Synchronize multiple shops in batch.

        Args:
            shops: List of GetResponseShop instances
            account: GetResponseAccount with API credentials
            force: Force update even if already synced

        Returns:
            Dictionary with statistics:
            {
                'total': int,
                'created': int,
                'updated': int,
                'skipped': int,
                'failed': int,
                'results': list of tuples (shop, success, message)
            }
        """
        stats = {"total": len(shops), "created": 0, "updated": 0, "skipped": 0, "failed": 0, "results": []}

        for shop in shops:
            was_synced = shop.is_synced

            success, message = self.sync_shop(shop=shop, account=account, force=force)

            stats["results"].append((shop, success, message))

            if success:
                if "already synced" in message:
                    stats["skipped"] += 1
                elif was_synced:
                    stats["updated"] += 1
                else:
                    stats["created"] += 1
            else:
                stats["failed"] += 1

            logger.info(f"Shop sync result: {shop.name} - {message}")

        return stats
