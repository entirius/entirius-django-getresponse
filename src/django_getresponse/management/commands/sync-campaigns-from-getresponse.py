# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime

from django_utils.workers.command import CeleryBaseCommand

from django_getresponse.models import GetResponseAccount
from django_getresponse.tasks.sync_campaigns_from_getresponse import (
    sync_campaigns_from_getresponse,
)


class Command(CeleryBaseCommand):
    help = "Synchronize campaigns from GetResponse API to local database"

    def add_arguments(self, parser):
        _add_account_argument(parser)
        _add_delete_missing_argument(parser)
        self.default_arguments.extend(["account_id", "delete_missing"])
        super().add_arguments(parser)

    def handle(self, *args, **options):
        account_id = options.get("account_id")
        if not account_id:
            self._handle_multi_account_sync(options)
        else:
            super().handle(*args, **options)

    def _handle_multi_account_sync(self, options):
        accounts = _get_enabled_accounts()
        _display_sync_header(len(accounts), options, self)
        _trigger_sync_tasks(accounts, options, self)


def _add_account_argument(parser) -> None:
    parser.add_argument(
        "--account-id",
        type=int,
        required=False,
        help="Sync specific GetResponseAccount by ID (optional, syncs all if not specified)",
    )


def _add_delete_missing_argument(parser) -> None:
    parser.add_argument(
        "--delete-missing",
        action="store_true",
        default=True,
        help="Delete local campaigns not found in GetResponse API (default: True)",
    )


def _get_enabled_accounts() -> list[GetResponseAccount]:
    return list(GetResponseAccount.objects.filter(is_enabled=True))


def _display_sync_header(account_count: int, options: dict, command) -> None:
    command.stdout.write(command.style.SUCCESS("=== Campaign Synchronization from GetResponse ===\n"))
    command.stdout.write(f"[OK] Found {account_count} enabled account(s)")
    _display_delete_warning(options, command)


def _display_delete_warning(options: dict, command) -> None:
    if options.get("delete_missing"):
        command.stdout.write(command.style.WARNING("WARNING: Delete mode: Local campaigns not in API will be removed"))


def _trigger_sync_tasks(accounts: list[GetResponseAccount], options: dict, command) -> None:
    runned_at = datetime.now().isoformat()
    use_celery = options.get("celery", True)
    mode = "Celery (async)" if use_celery else "synchronous"
    command.stdout.write(command.style.SUCCESS(f"\nTriggering {len(accounts)} task(s) in {mode} mode...\n"))

    for account in accounts:
        _trigger_single_task(account, runned_at, options, use_celery, command)

    _display_completion_message(len(accounts), use_celery, command)


def _trigger_single_task(
    account: GetResponseAccount,
    runned_at: str,
    options: dict,
    use_celery: bool,
    command,
) -> None:
    if use_celery:
        _trigger_celery_task(account, runned_at, options, command)
    else:
        _execute_sync_directly(account, runned_at, options, command)


def _trigger_celery_task(account: GetResponseAccount, runned_at: str, options: dict, command) -> None:
    result = sync_campaigns_from_getresponse.delay(
        runned_at=runned_at,
        account_id=account.id,
        delete_missing=options.get("delete_missing", True),
    )
    command.stdout.write(f"  [OK] {_get_account_display_name(account)}: Task {result.id}")


def _execute_sync_directly(account: GetResponseAccount, runned_at: str, options: dict, command) -> None:
    sync_campaigns_from_getresponse(
        runned_at=runned_at,
        account_id=account.id,
        delete_missing=options.get("delete_missing", True),
    )
    command.stdout.write(f"  [OK] {_get_account_display_name(account)}: Completed")


def _get_account_display_name(account: GetResponseAccount) -> str:
    return account.name or f"{account.api_key[:12]}..."


def _display_completion_message(account_count: int, use_celery: bool, command) -> None:
    if use_celery:
        command.stdout.write(command.style.SUCCESS(f"\n[OK] {account_count} task(s) queued"))
        command.stdout.write("Monitor task progress in Celery logs or Flower dashboard.")
    else:
        command.stdout.write(command.style.SUCCESS(f"\n[OK] {account_count} account(s) processed"))
