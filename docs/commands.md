---
title: Management Commands
description: GetResponse management commands for shop, campaign, category and product sync.
---

```bash
python manage.py sync-shops-to-getresponse         # creates/updates GR shops from channel config
python manage.py sync-campaigns-from-getresponse   # pulls GR campaigns into local rows
python manage.py sync-categories-to-getresponse    # pushes django_pim.ProductCategory
python manage.py sync-products-to-getresponse      # pushes django_pim.Product catalog
```

Celery equivalents live in `tasks/` with matching names (`@shared_task(queue="pim_pull")`).
