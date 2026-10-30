from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import InstructorProfile, StudentProfile


def index(request):
    now = datetime.now(ZoneInfo("America/Chicago"))
    context = {
        "current_time": now.strftime("%H:%M"),
        "user_name": request.user.username if request.user.is_authenticated else None,
    }
    return render(request, "app/index.html", context)


@csrf_exempt
@require_GET
def new(request):
    return render(request, "app/new.html")


@csrf_exempt  # needed so the plain curl request (no CSRF token) works
@require_POST
def createUser(request):
    email = request.POST.get("email", "").strip()
    user_name = request.POST.get("user_name", "").strip()
    password = request.POST.get("password", "")
    is_student = request.POST.get("is_student", "")

    if not (email and user_name and password) or is_student not in ("0", "1"):
        return HttpResponse("Missing or invalid field", status=400)

    if User.objects.filter(email__iexact=email).exists():
        return HttpResponse("Email already registered", status=409)
    if User.objects.filter(username=user_name).exists():
        return HttpResponse("Username already taken", status=409)

    with transaction.atomic():
        user = User.objects.create_user(
            username=user_name, email=email, password=password
        )
        if is_student == "1":
            StudentProfile.objects.create(user=user, student_id=f"S{user.id:06d}")
        else:
            InstructorProfile.objects.create(user=user)

    login(request, user)
    return HttpResponse("User created", status=200)


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
