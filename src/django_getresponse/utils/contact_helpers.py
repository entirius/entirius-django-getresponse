# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Helper functions for GetResponse contact lookup.

This module provides reusable functions for retrieving contact IDs
from various sources (Customer, Form, email).
"""

from process_logger import ProcessLogger

logger = ProcessLogger("contact_helpers")


def get_contact_id_from_form(form) -> str | None:
    """Get contact_id from Form via GetResponseContact.

    Args:
        form: Form instance to lookup

    Returns:
        Contact ID string or None if not found or not synced
    """
    from django_getresponse.models import GetResponseContact

    try:
        contact = GetResponseContact.objects.filter(form=form, sync_status="synced").first()
        return contact.contact_id if contact else None
    except Exception as e:
        logger.debug(f"Could not get contact_id from form: {e}")
        return None


def get_contact_id_from_customer(customer) -> str | None:
    """Get contact_id from customer's GetResponseContact.

    Args:
        customer: Customer instance

    Returns:
        Contact ID string or None
    """
    from django_crm.models import Form

    try:
        form = Form.objects.filter(email=customer.email.email).first()
        return get_contact_id_from_form(form) if form else None
    except Exception as e:
        logger.debug(f"Could not get contact_id from customer: {e}")
        return None


def get_contact_id_from_email(email: str) -> str | None:
    """Get contact_id by email lookup.

    Args:
        email: Email address to lookup

    Returns:
        Contact ID string or None
    """
    from django_crm.models import Form

    try:
        form = Form.objects.filter(email=email).first()
        return get_contact_id_from_form(form) if form else None
    except Exception as e:
        logger.debug(f"Could not get contact_id from email {email}: {e}")
        return None


def get_synced_contact_id_from_email(email: str) -> str | None:
    """Get contact_id by email lookup (only if synced with contactId set).

    This variant is more strict - only returns contact_id if:
    - Contact exists
    - sync_status = 'synced'
    - contact_id is not null

    Args:
        email: Email address to lookup

    Returns:
        Contact ID string or None if not synced
    """
    from django_crm.models import Form

    from django_getresponse.models import GetResponseContact

    try:
        form = Form.objects.filter(email=email).first()
        if not form:
            return None

        contact = GetResponseContact.objects.filter(form=form, sync_status="synced", contact_id__isnull=False).first()

        return contact.contact_id if contact else None
    except Exception as e:
        logger.debug(f"Error getting synced contact_id for {email}: {e}")
        return None


def synced_contact_exists_for_email(email: str) -> bool:
    """Check if synced GetResponse contact already exists for email.

    Args:
        email: Email address to check

    Returns:
        True if synced contact exists, False otherwise
    """
    from django_crm.models import Form

    from django_getresponse.models import GetResponseContact

    try:
        form = Form.objects.filter(email=email).first()
        if not form:
            return False

        return GetResponseContact.objects.filter(form=form, sync_status="synced", contact_id__isnull=False).exists()
    except Exception:
        return False
