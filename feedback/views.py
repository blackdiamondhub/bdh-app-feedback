import json
import logging
from functools import wraps
from urllib.parse import urlsplit

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bdh_sdk.auth import is_admin
from bdh_sdk.identity import HEADER_IDENTITY, decode_identity

from . import unread
from .models import Feedback

log = logging.getLogger(__name__)

# Set by the hub, in the identity it signs, only on messages from its own submit
# endpoint (which adds the page and the stay). Visitors' requests through the
# app proxy never carry it.
SUBMIT_FLAG = "feedback_submit"


def admin_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not is_admin(request):
            return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def _from_hub_submit(request):
    # bdh_mode is only set by the SDK's IdentityMiddleware, which has checked the
    # hub's signature over the identity header.
    raw = request.headers.get(HEADER_IDENTITY) or ""
    if not hasattr(request, "bdh_mode") or not raw:
        return False
    try:
        identity = decode_identity(raw) or {}
    except ValueError:
        return False
    return bool(identity.get(SUBMIT_FLAG))


def _page(fb, hub_origin):
    """Title and icon of the hub page a message was sent from."""
    title = fb.page_title
    if not title:
        path = urlsplit(fb.page_url or "").path or ""
        title = "Home" if path in ("", "/") else path
    icon = fb.page_icon
    # Hub static paths: this page is on the app's origin, so point them at the hub.
    if icon.startswith("/") and not icon.startswith("//"):
        icon = hub_origin + icon if hub_origin else icon
    elif icon and not icon.startswith(("https://", "http://")):
        icon = ""
    return {"title": title, "icon": icon}


def _items(request):
    origin = getattr(request, "bdh_hub_origin", "")
    return [
        {
            "id": fb.id,
            "message": fb.message,
            "submitted_at": fb.submitted_at.isoformat(),
            "is_read": fb.is_read,
            "page": _page(fb, origin),
            "stay": fb.stay,
        }
        for fb in Feedback.objects.order_by("-submitted_at", "-id")
    ]


def inbox(request):
    if not is_admin(request):
        raise Http404
    # Opening the inbox also re-syncs the hub's badge.
    unread.push()
    return render(request, "feedback/inbox.html", {"items": _items(request)})


@admin_api
def feedback_list(request):
    return JsonResponse({"items": _items(request)})


@require_POST
@admin_api
def bulk_action(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    ids = data.get("feedback_ids") or []
    action = data.get("action")
    if not ids or not action or not isinstance(ids, list):
        return JsonResponse({"success": False, "error": "Missing data"}, status=400)

    rows = Feedback.objects.filter(id__in=[i for i in ids if isinstance(i, int)])
    if action == "delete":
        rows.delete()
    elif action == "mark_read":
        rows.update(is_read=True)
    elif action == "mark_unread":
        rows.update(is_read=False)
    else:
        return JsonResponse({"success": False, "error": "Invalid action"}, status=400)
    # update() sends no signals.
    unread.schedule()
    return JsonResponse({"success": True})


@csrf_exempt
@require_POST
def submit(request):
    """A message from the hub's top bar, posted by the hub itself."""
    if not _from_hub_submit(request):
        return JsonResponse({"success": False, "error": "Forbidden"}, status=403)
    post = request.POST
    message = (post.get("message") or "").strip()
    if not message:
        return JsonResponse({"success": False, "error": "Empty message"}, status=400)
    Feedback.objects.create(
        message=message,
        page_url=(post.get("page_url") or "")[:200],
        page_title=(post.get("page_title") or "")[:120],
        page_icon=(post.get("page_icon") or "")[:300],
        stay=(post.get("stay") or "")[:120],
    )
    return JsonResponse({"success": True})
