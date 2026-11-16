import io
import json
import os
from unittest.mock import patch

import bdh_sdk.storage as sdk_storage
from bdh_sdk import appdata, rpc
from bdh_sdk.identity import IdentityMiddleware, encode_identity, signed_headers
from bdh_sdk.testing import FakeBroker
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from feedback import unread, views
from feedback.models import Feedback
from feedback.plugin import spec

TOKEN = "app-token"


def hub_post(path, data, identity):
    """A form POST signed like the hub's, run through the SDK's middleware."""
    rf = RequestFactory()
    headers = signed_headers(TOKEN, "POST", path, identity=identity)
    request = rf.post(path, data, headers=headers)
    with patch.dict(os.environ, {"BDH_APP_TOKEN": TOKEN}):
        return IdentityMiddleware(views.submit)(request)


class SpecTests(TestCase):
    def test_manifest(self):
        self.assertEqual(spec.id, "feedback")
        self.assertEqual(spec.api_version, 2)
        self.assertEqual(tuple(spec.permissions), ())


class SubmitTests(TestCase):
    path = "/feedback/submit/"
    form = {"message": "  The hot tub is cold  ", "page_url": "http://hub/weather/",
            "page_title": "Weather", "page_icon": "/static/weather/icon.png", "stay": "the Smith stay"}

    def test_hub_submit_is_saved(self):
        resp = hub_post(self.path, self.form, {"mode": "guest", "feedback_submit": 1})
        self.assertEqual(resp.status_code, 200)
        fb = Feedback.objects.get()
        self.assertEqual(fb.message, "The hot tub is cold")
        self.assertEqual((fb.page_url, fb.page_title, fb.stay),
                         ("http://hub/weather/", "Weather", "the Smith stay"))
        self.assertFalse(fb.is_read)

    def test_needs_the_hubs_submit_flag(self):
        resp = hub_post(self.path, self.form, {"mode": "guest"})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Feedback.objects.exists())

    def test_unsigned_flag_is_rejected(self):
        # No middleware (as in-process) or a forged header: not from the hub.
        request = RequestFactory().post(
            self.path, self.form, headers={"X-BDH-Identity": encode_identity({"feedback_submit": 1})})
        self.assertEqual(views.submit(request).status_code, 403)
        with patch.dict(os.environ, {"BDH_APP_TOKEN": TOKEN}):
            self.assertEqual(IdentityMiddleware(views.submit)(request).status_code, 403)
        self.assertFalse(Feedback.objects.exists())

    def test_empty_message(self):
        resp = hub_post(self.path, {**self.form, "message": "  "}, {"feedback_submit": 1})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Feedback.objects.exists())


class InboxTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user("admin", password="pw", is_staff=True)
        self.guest = User.objects.create_user("guest", password="pw")
        self.a = Feedback.objects.create(message="first", page_url="http://hub/")
        self.b = Feedback.objects.create(message="second", page_url="http://hub/weather/",
                                         page_title="Weather", page_icon="/static/w.png")

    def test_inbox_is_admin_only(self):
        url = reverse("feedback_inbox")
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "second")

    def test_list_pages(self):
        self.client.force_login(self.admin)
        items = self.client.get(reverse("feedback_list")).json()["items"]
        self.assertEqual([i["message"] for i in items], ["second", "first"])
        self.assertEqual(items[0]["page"], {"title": "Weather", "icon": "/static/w.png"})
        self.assertEqual(items[1]["page"]["title"], "Home")

    def test_icon_points_at_the_hub(self):
        self.b.page_icon = "/static/w.png"
        self.assertEqual(views._page(self.b, "https://hub.example")["icon"], "https://hub.example/static/w.png")
        self.b.page_icon = "javascript:alert(1)"
        self.assertEqual(views._page(self.b, "https://hub.example")["icon"], "")

    def test_list_and_bulk_are_admin_only(self):
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(reverse("feedback_list")).status_code, 403)
        resp = self.client.post(reverse("feedback_bulk_action"),
                                json.dumps({"feedback_ids": [self.a.id], "action": "delete"}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Feedback.objects.count(), 2)

    def test_bulk_actions(self):
        self.client.force_login(self.admin)

        def act(action, ids):
            return self.client.post(reverse("feedback_bulk_action"),
                                    json.dumps({"feedback_ids": ids, "action": action}),
                                    content_type="application/json")

        self.assertEqual(act("mark_read", [self.a.id, self.b.id]).status_code, 200)
        self.assertEqual(Feedback.objects.filter(is_read=True).count(), 2)
        self.assertEqual(act("mark_unread", [self.b.id]).status_code, 200)
        self.assertEqual(list(Feedback.objects.filter(is_read=False)), [self.b])
        self.assertEqual(act("delete", [self.a.id]).status_code, 200)
        self.assertEqual(list(Feedback.objects.all()), [self.b])
        self.assertEqual(act("explode", [self.b.id]).status_code, 400)
        self.assertEqual(act("delete", []).status_code, 400)


class UnreadPushTests(TransactionTestCase):
    """The unread count reaches the hub's app state through the broker.

    Real commits (not TestCase's wrapping transaction), since the push waits
    for the commit and is sent once per transaction.
    """

    def setUp(self):
        self.fb = FakeBroker(app_id="feedback").start()
        self.addCleanup(self.fb.stop)
        # Swap only the state backend: rpc.install() would replace (and on
        # uninstall reset) every SDK backend of the hub running these tests.
        old = sdk_storage._backend
        sdk_storage._backend = rpc.StateBackend(rpc.Client(self.fb.url, self.fb.token, retries=0))
        self.addCleanup(setattr, sdk_storage, "_backend", old)

    def pushed(self):
        return [p["value"] for p in self.fb.ops("state.set")
                if p.get("app") == "feedback" and p.get("key") == unread.UNREAD_KEY]

    def test_changes_push_the_count(self):
        with transaction.atomic():
            a = Feedback.objects.create(message="one")
            Feedback.objects.create(message="two")
            self.assertEqual(self.pushed(), [])
        self.assertEqual(self.pushed(), [2])  # once, after the commit
        with transaction.atomic():
            Feedback.objects.filter(pk=a.pk).update(is_read=True)
            unread.schedule()
        a.delete()
        Feedback.objects.create(message="three")
        self.assertEqual(self.pushed(), [2, 1, 1, 2])

    def test_import_pushes_the_count(self):
        # Rows exported from the hub's built-in feedback app (no page title/icon).
        rows = [{"model": "feedback.feedback", "pk": 7, "fields": {
            "name": None, "email": None, "message": "old", "submitted_at": "2025-01-02T03:04:05Z",
            "is_read": False, "page_url": "http://hub/", "stay": ""}}]
        self.assertEqual(appdata.import_rows("feedback", io.StringIO(json.dumps(rows))), 1)
        self.assertEqual(Feedback.objects.get(pk=7).message, "old")
        self.assertEqual(self.pushed(), [1])

    def test_push_failure_is_swallowed(self):
        self.fb.stop()
        with self.assertLogs("feedback.unread", "ERROR"):
            unread.push()
