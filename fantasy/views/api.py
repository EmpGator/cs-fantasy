"""
API views for the fantasy app.
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required

from ..models import CloudflareCookie

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def submit_cloudflare_cookies(request):
    """
    Endpoint to receive Cloudflare bypass cookies.

    Expects JSON body:
    {
        "cf_clearance": "cookie_value",
        "cf_bm": "cookie_value",  // optional
        "user_agent": "...",  // optional
        "domain": "www.hltv.org"  // optional, defaults to hltv
    }

    Returns:
    {
        "status": "ok",
        "message": "Cookies updated",
        "age_minutes": 0
    }
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "ignored", "message": "Invalid JSON"})

    cf_clearance = data.get("cf_clearance", "").strip() if isinstance(data, dict) else ""
    if not cf_clearance:
        return JsonResponse({"status": "ignored", "message": "No cf_clearance provided"})

    cf_bm = (data.get("cf_bm") or "").strip()
    user_agent = (data.get("user_agent") or "").strip()
    domain = (data.get("domain") or "www.hltv.org").strip()

    cookie, created = CloudflareCookie.update_or_create_cookies(
        cf_clearance=cf_clearance,
        cf_bm=cf_bm,
        user_agent=user_agent,
        domain=domain,
    )

    action = "created" if created else "updated"
    logger.info(f"Cloudflare cookies {action} for {domain}")

    return JsonResponse({
        "status": "ok",
        "message": f"Cookies {action} for {domain}",
        "age_minutes": cookie.age_minutes,
        "is_likely_valid": cookie.is_likely_valid,
    })


@staff_member_required
def get_cookie_status(request):
    """
    Get current cookie status.

    Returns:
    {
        "status": "ok",
        "cookies": {
            "domain": "www.hltv.org",
            "age_minutes": 5,
            "is_likely_valid": true,
            "use_count": 10,
            "last_error": ""
        }
    }
    """
    cookie = CloudflareCookie.get_latest()

    if not cookie:
        return JsonResponse({
            "status": "ok",
            "cookies": None,
            "message": "No cookies stored"
        })

    return JsonResponse({
        "status": "ok",
        "cookies": {
            "domain": cookie.domain,
            "age_minutes": cookie.age_minutes,
            "is_likely_valid": cookie.is_likely_valid,
            "use_count": cookie.use_count,
            "last_error": cookie.last_error,
            "updated_at": cookie.updated_at.isoformat(),
        }
    })
