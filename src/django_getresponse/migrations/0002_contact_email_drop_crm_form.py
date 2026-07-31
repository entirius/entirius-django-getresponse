# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# 3.0.0 bridge for databases migrated under 2.x, where GetResponseContact carried
# a FK to django_crm.Form instead of its own `email` column. The edited squash
# already provides the final STATE (email field, no FK), so this migration is
# raw SQL only (state_operations empty) and fully idempotent:
#
# - fresh databases: the squash created the final schema — every statement is a no-op;
# - 2.x databases: adds `email`, backfills it from django_crm_form (guarded — the
#   crm table may already be gone), drops `form_id` (its indexes drop with it) and
#   creates the named indexes the squash gives fresh installations.
#
# Irreversible by design: the FK target app is withdrawn.

from django.db import migrations

FORWARD_SQL = """
ALTER TABLE django_getresponse_contact
    ADD COLUMN IF NOT EXISTS email varchar(254) NOT NULL DEFAULT '';

DO $$
BEGIN
    IF to_regclass('django_crm_form') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_name = 'django_getresponse_contact' AND column_name = 'form_id'
       ) THEN
        UPDATE django_getresponse_contact c
        SET email = f.email
        FROM django_crm_form f
        WHERE c.form_id = f.id AND c.email = '';
    END IF;
END $$;

ALTER TABLE django_getresponse_contact DROP COLUMN IF EXISTS form_id;
ALTER TABLE django_getresponse_contact ALTER COLUMN email DROP DEFAULT;

CREATE INDEX IF NOT EXISTS idx_grcontact_email
    ON django_getresponse_contact (email);
CREATE INDEX IF NOT EXISTS idx_grcontact_campaign_email
    ON django_getresponse_contact (campaign_id, email);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("django_getresponse", "0001_squashed_0009_getresponseshop_domain_url_cart"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=migrations.RunSQL.noop, state_operations=[]),
    ]
