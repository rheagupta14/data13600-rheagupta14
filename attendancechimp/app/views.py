from datetime import datetime
from zoneinfo import ZoneInfo

from django.http import HttpResponse, JsonResponse


def time_view(request):
    now = datetime.now(ZoneInfo("America/Chicago"))
    return HttpResponse(now.strftime("%H:%M"), content_type="text/plain")


def _to_number(s):
    try:
        return int(s)
    except ValueError:
        return float(s)


def sum_view(request):
    try:
        n1 = _to_number(request.GET["n1"])
        n2 = _to_number(request.GET["n2"])
    except (KeyError, ValueError):
        return JsonResponse({"error": "n1 and n2 must be numbers"}, status=400)
    return HttpResponse(f"<p>{n1 + n2}</p>")