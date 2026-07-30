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

# The suite is import-only (no DB fixtures); django_agreements is not installed —
# the consent gate imports it lazily inside has_marketing_consent only.
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
