# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from datetime import datetime

from django_utils.workers.command import CeleryBaseCommand

from django_getresponse.models import GetResponseShop
from django_getresponse.tasks.sync_products_to_getresponse import sync_products_to_getresponse


class Command(CeleryBaseCommand):
    help = "Synchronize Product to GetResponse products"

    def add_arguments(self, parser):
        _add_shop_idx_argument(parser)
        _add_force_argument(parser)
        self.default_arguments.extend(["shop_idx", "force"])
        super().add_arguments(parser)

    def handle(self, *args, **options):
        shop_idx = options.get("shop_idx")
        if not shop_idx:
            self._handle_multi_shop_sync(options)
        else:
            super().handle(*args, **options)

    def _handle_multi_shop_sync(self, options):
        shops = _get_synced_shops()
        if not shops:
            _display_no_shops_warning(self)
            return
        _display_sync_info(shops, options, self)
        _trigger_shop_sync_tasks(shops, options, self)


def _add_shop_idx_argument(parser) -> None:
    parser.add_argument(
        "--shop-idx",
        type=str,
        required=False,
        help="Shop idx (optional - syncs all shops if not specified)",
    )


def _add_force_argument(parser) -> None:
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-sync all products (even if already synced)",
    )


def _get_synced_shops() -> list[GetResponseShop]:
    return list(GetResponseShop.objects.filter(sync_status="synced"))


def _display_no_shops_warning(command) -> None:
    command.stdout.write(command.style.WARNING("No synced GetResponseShop found."))
    command.stdout.write("Create and sync GetResponseShop first using: sync-shops-to-getresponse")


def _display_sync_info(shops: list[GetResponseShop], options: dict, command) -> None:
    command.stdout.write(command.style.SUCCESS("=== Product Synchronization to GetResponse ===\n"))
    command.stdout.write(f"[OK] Found {len(shops)} synced shop(s)")
    _display_force_warning_if_enabled(options, command)


def _display_force_warning_if_enabled(options: dict, command) -> None:
    if options.get("force"):
        command.stdout.write(
            command.style.WARNING("WARNING: Force mode enabled - will re-sync already synced products")
        )


def _trigger_shop_sync_tasks(shops: list[GetResponseShop], options: dict, command) -> None:
    runned_at = datetime.now().isoformat()
    use_celery = options.get("celery", True)
    _display_trigger_info(len(shops), use_celery, command)

    task_ids = []
    for shop in shops:
        _trigger_single_shop_task(shop, runned_at, options, use_celery, task_ids, command)

    _display_completion_summary(len(task_ids), use_celery, command)


def _display_trigger_info(shop_count: int, use_celery: bool, command) -> None:
    mode = "Celery (async)" if use_celery else "synchronous"
    command.stdout.write(command.style.SUCCESS(f"\nTriggering {shop_count} task(s) in {mode} mode...\n"))


def _trigger_single_shop_task(
    shop: GetResponseShop,
    runned_at: str,
    options: dict,
    use_celery: bool,
    task_ids: list,
    command,
) -> None:
    if use_celery:
        _trigger_celery_task(shop, runned_at, options, task_ids, command)
    else:
        _execute_sync_directly(shop, runned_at, options, command)


def _trigger_celery_task(shop: GetResponseShop, runned_at: str, options: dict, task_ids: list, command) -> None:
    result = sync_products_to_getresponse.delay(
        runned_at=runned_at,
        shop_idx=shop.channel.idx,
        force=options.get("force", False),
        log_level=10,
    )
    task_ids.append((shop.channel.idx, result.id))
    command.stdout.write(f"  [OK] {shop.channel.idx}: Task {result.id}")


def _execute_sync_directly(shop: GetResponseShop, runned_at: str, options: dict, command) -> None:
    sync_products_to_getresponse(
        runned_at=runned_at,
        shop_idx=shop.channel.idx,
        force=options.get("force", False),
        log_level=10,
    )
    command.stdout.write(f"  [OK] {shop.channel.idx}: Completed")


def _display_completion_summary(task_count: int, use_celery: bool, command) -> None:
    if use_celery:
        command.stdout.write(command.style.SUCCESS(f"\n[OK] {task_count} task(s) queued"))
        command.stdout.write("Monitor task progress in Celery logs or Flower dashboard.")
    else:
        command.stdout.write(command.style.SUCCESS(f"\n[OK] {task_count} shop(s) processed"))
