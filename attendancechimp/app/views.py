from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import (
    Course,
    InstructorProfile,
    Lecture,
    QRCodeUpload,
    StudentProfile,
    getUploadsForCourse,
)


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


@csrf_exempt  
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


# HW%

def is_instructor(user):
    return user.is_authenticated and hasattr(user, "instructorprofile")


def is_student(user):
    return user.is_authenticated and hasattr(user, "studentprofile")


def unauthorized():
    return HttpResponse("Unauthorized", status=401)


def parse_time(text):
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(text.strip(), fmt).time()
        except (ValueError, AttributeError):
            pass
    return None


def is_checked(value):
    """True if a form checkbox/field value means 'checked'."""
    return value not in (None, "", "false", "False", "0", "off")


@login_required
def new_course(request):
    return render(request, "app/new_course.html")


@login_required
def new_lecture(request):
    return render(request, "app/new_lecture.html", {"courses": Course.objects.all()})


@login_required
def new_qr_upload(request):
    return render(request, "app/new_qr_upload.html")


@csrf_exempt
@require_http_methods(["POST"])
def createCourse(request):
    if not is_instructor(request.user):
        return unauthorized()

    name = request.POST.get("course-name")
    start = parse_time(request.POST.get("start-time", ""))
    end = parse_time(request.POST.get("end-time", ""))
    code = (
        request.POST.get("course-number")
        or request.POST.get("course")
        or request.POST.get("code")
        or (name or "")
    )
    code = code.replace(" ", "").strip()

    day_fields = {
        "mon": "day-mon",
        "tue": "day-tue",
        "wed": "day-wed",
        "thu": "day-thu",
        "fri": "day-fri",
        "sat": "day-sat",
        "sun": "day-sun",
    }
    days = {
        attr: is_checked(request.POST.get(field))
        for attr, field in day_fields.items()
    }

    if not name or not code or start is None or end is None or not any(days.values()):
        return HttpResponse("Bad input", status=400)

    if Course.objects.filter(code=code).exists():
        return HttpResponse("Course number already exists", status=409)

    Course.objects.create(
        name=name,
        code=code,
        instructor=request.user.instructorprofile,
        start_time=start,
        end_time=end,
        **days,
    )
    return HttpResponse("Course created", status=200)


@csrf_exempt
@require_http_methods(["POST"])
def createLecture(request):
    if not is_instructor(request.user):
        return unauthorized()

    course = Course.objects.filter(name=request.POST.get("choice")).first()
    if course is None:
        return HttpResponse("No such course", status=400)

    Lecture.objects.create(course=course, date=timezone.now())
    return HttpResponse("Lecture created", status=200)


@csrf_exempt
@require_http_methods(["POST"])
def createQRCodeUpload(request):
    if not is_student(request.user):
        return unauthorized()

    image = request.FILES.get("imageUpload")
    if image is None:
        return HttpResponse("Missing imageUpload", status=400)

    QRCodeUpload.objects.create(student=request.user.studentprofile, image=image)
    return HttpResponse("Upload saved", status=200)


@csrf_exempt
@require_http_methods(["GET"])
def dumpUploads(request):
    if not is_instructor(request.user):
        return unauthorized()

    data = []
    for up in QRCodeUpload.objects.select_related("student__user").order_by("uploaded_at"):
        ts = up.uploaded_at
        if timezone.is_aware(ts):
            ts = timezone.localtime(ts)
        data.append({
            "username": up.student.user.username,
            "upload_time": ts.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return JsonResponse(data, safe=False)


# HW6

@csrf_exempt
@require_http_methods(["GET"])
def getUploads(request):
    """Return the valid (during-class-time) uploads for ?course=<course number>."""
    if not is_instructor(request.user):
        return unauthorized()

    course = request.GET.get("course")
    if not course:
        return JsonResponse({"error": "Missing course parameter"}, status=400)

    uploads = getUploadsForCourse(course)

    data = []
    for up in uploads:
        ts = up.uploaded_at
        if timezone.is_aware(ts):
            ts = timezone.localtime(ts)
        data.append({
            "username": up.student.user.username,
            "upload_time": ts.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return JsonResponse(data, safe=False)