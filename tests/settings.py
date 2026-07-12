# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import dj_database_url

SECRET_KEY = "test-secret-key-for-getresponse"

# Required by django_pim at import time.
MEDIA_URL = "/media/"
STATIC_URL = "/static/"
TMP_DIR = "/tmp/getresponse-test-tmp"

# Required by bievents-based BI events at import time.
BI_ENVIRONMENT = "test"
BI_BUSINESS_UNIT = "test"

DATABASES = {
    "default": dj_database_url.config(default="postgresql://postgres:postgres@localhost:5432/test"),
}

# django_crm is deliberately NOT installed here: the two apps are mutually dependent
# and django_crm is not published yet. The suite is import-only (no DB fixtures) —
# FK string references to django_crm stay lazy and the django_crm imports in
# utils/contact_helpers are function-local.
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django_regional",
    "django_utils",
    "django_pim",
    "django_pricemanager",
    "django_getresponse",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
