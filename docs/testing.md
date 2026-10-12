---
title: Testing
description: Import-only smoke tests of the GetResponse module and their settings.
---

```bash
# Import-only smoke suite; DATABASE_URL optional (no DB fixtures).
make test
```

`tests/settings.py` deliberately omits `django_agreements` (the consent gate imports it
lazily) — the suite stays import-only and never touches the DB.
