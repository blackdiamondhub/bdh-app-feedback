"""The unread count the hub shows on its feedback badge.

The hub never reads this app's database: the app keeps the count in its app
state (``unread_count``), and the hub reads it from there. It is written
whenever a message is added, deleted or marked, including rows loaded with
``import_app_data``.
"""
import logging

from django.db import connection, transaction
from django.db.models.signals import post_delete, post_save

from bdh_sdk.storage import app_state

log = logging.getLogger(__name__)

APP_ID = "feedback"
UNREAD_KEY = "unread_count"


def count():
    from .models import Feedback

    return Feedback.objects.filter(is_read=False).count()


def push():
    """Write the current unread count to the app state. Never raises."""
    try:
        app_state(APP_ID).set(UNREAD_KEY, count())
    except Exception:
        log.exception("could not push the unread feedback count")


def schedule():
    """Push once the current transaction commits (at once outside one).

    Many changes in one transaction (an import, a bulk delete) push once.
    """
    if any(entry[1] is push for entry in connection.run_on_commit):
        return
    transaction.on_commit(push)


def _changed(sender, **kwargs):
    schedule()


def connect():
    from .models import Feedback

    post_save.connect(_changed, sender=Feedback, dispatch_uid="feedback-unread-save")
    post_delete.connect(_changed, sender=Feedback, dispatch_uid="feedback-unread-delete")
