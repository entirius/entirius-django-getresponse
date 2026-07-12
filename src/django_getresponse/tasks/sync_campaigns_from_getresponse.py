# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from celery import shared_task
from process_logger import ProcessLogger

from django_getresponse.models import GetResponseAccount
from django_getresponse.services.campaign_sync_service import CampaignSyncService


@shared_task(queue="pim_pull")
def sync_campaigns_from_getresponse(
    runned_at: str,
    account_id: int | None = None,
    delete_missing: bool = True,
    log_level: int = 10,
) -> dict:
    logger = _setup_logger(runned_at, account_id, delete_missing, log_level)
    accounts = _get_accounts_to_sync(account_id, logger)
    results = _sync_all_accounts(accounts, delete_missing, logger)
    return _aggregate_results(results, logger)


def _setup_logger(runned_at: str, account_id: int | None, delete_missing: bool, level: int) -> ProcessLogger:
    logger = ProcessLogger("SYNC_CAMPAIGNS_FROM_GETRESPONSE")
    logger.setLevel(level)
    _add_log_params(logger, runned_at, account_id, delete_missing)
    return logger


def _add_log_params(logger: ProcessLogger, runned_at: str, account_id: int | None, delete_missing: bool) -> None:
    logger.add_log_param("runned_at", runned_at)
    logger.add_log_param("account_id", account_id)
    logger.add_log_param("delete_missing", delete_missing)


def _get_accounts_to_sync(account_id: int | None, logger: ProcessLogger) -> list[GetResponseAccount]:
    if account_id:
        return _get_single_account(account_id, logger)
    return _get_all_enabled_accounts(logger)


def _get_single_account(account_id: int, logger: ProcessLogger) -> list[GetResponseAccount]:
    try:
        account = GetResponseAccount.objects.get(id=account_id)
        return [account]
    except GetResponseAccount.DoesNotExist:
        return _handle_account_not_found(account_id, logger)


def _handle_account_not_found(account_id: int, logger: ProcessLogger) -> list:
    logger.error(f"Account with id={account_id} not found")
    return []


def _get_account_name(account: GetResponseAccount) -> str:
    return account.name or f"{account.api_key[:12]}..."


def _get_all_enabled_accounts(logger: ProcessLogger) -> list[GetResponseAccount]:
    accounts = list(GetResponseAccount.objects.filter(is_enabled=True))
    logger.info(f"Found {len(accounts)} enabled accounts to sync")
    return accounts


def _sync_all_accounts(accounts: list[GetResponseAccount], delete_missing: bool, logger: ProcessLogger) -> list[dict]:
    service = CampaignSyncService()
    return [_sync_single_account(service, account, delete_missing, logger) for account in accounts]


def _sync_single_account(
    service: CampaignSyncService,
    account: GetResponseAccount,
    delete_missing: bool,
    logger: ProcessLogger,
) -> dict:
    try:
        stats = service.sync_campaigns_from_api(account, delete_missing)
        _log_account_success(account, stats, logger)
        return _build_success_result(account, stats)
    except Exception as e:
        return _handle_account_sync_failure(account, e, logger)


def _build_success_result(account: GetResponseAccount, stats: dict) -> dict:
    return {"account_id": account.id, "success": True, **stats}


def _handle_account_sync_failure(account: GetResponseAccount, error: Exception, logger: ProcessLogger) -> dict:
    _log_account_failure(account, error, logger)
    return {"account_id": account.id, "success": False, "error": str(error)}


def _log_account_success(account: GetResponseAccount, stats: dict, logger: ProcessLogger) -> None:
    logger.info(
        f"Account {_get_account_name(account)}: "
        f"created={stats['created']}, updated={stats['updated']}, deleted={stats['deleted']}"
    )


def _log_account_failure(account: GetResponseAccount, error: Exception, logger: ProcessLogger) -> None:
    logger.error(
        f"Failed to sync account {_get_account_name(account)}: {str(error)}",
        exc_info=True,
    )


def _aggregate_results(results: list[dict], logger: ProcessLogger) -> dict:
    successful = [r for r in results if r["success"]]
    aggregated = _build_aggregated_stats(results, successful)
    _log_final_summary(aggregated, logger)
    return aggregated


def _build_aggregated_stats(results: list[dict], successful: list[dict]) -> dict:
    return {
        "success": _is_overall_success(results),
        "total_accounts": len(results),
        "successful_accounts": len(successful),
        **_sum_campaign_stats(successful),
    }


def _is_overall_success(results: list[dict]) -> bool:
    return len(results) > 0 and any(r["success"] for r in results)


def _sum_campaign_stats(results: list[dict]) -> dict:
    return {
        "total_campaigns": sum(r.get("total", 0) for r in results),
        "created": sum(r.get("created", 0) for r in results),
        "updated": sum(r.get("updated", 0) for r in results),
        "deleted": sum(r.get("deleted", 0) for r in results),
    }


def _log_final_summary(stats: dict, logger: ProcessLogger) -> None:
    logger.info(
        f"Sync completed: "
        f"accounts={stats['successful_accounts']}/{stats['total_accounts']}, "
        f"campaigns={stats['total_campaigns']}, "
        f"created={stats['created']}, updated={stats['updated']}, deleted={stats['deleted']}"
    )
