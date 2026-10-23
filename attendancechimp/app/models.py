"""
models.py — Data model for AttendanceChimp.

AttendanceChimp is an electronic class attendance tool.  Instructors create
courses and lectures; each lecture is assigned a random QR code.  Students
photograph the QR code and upload the image.  The system decodes the QR code,
matches it to a lecture, and records the attendance.

Entities
--------
- CourseProfile   : extends Django User → instructor-specific data
- StudentProfile  : extends Django User → student-specific data
- Course          : a course taught by one instructor
- Enrollment      : junction table linking students to courses
- Lecture         : a single class meeting (has a QR-code identifier)
- QRCodeUpload    : a student's uploaded QR-code photograph
"""

from django.db import models
from django.contrib.auth.models import User

import logging
import string
import random

logger = logging.getLogger(__name__) # set up tracking, auditing, and debugging
                                                               # allows using logger.warning(), logger.error(), 
                                                               # logger.info(), etc. Better than print() for debuggin... 


# ---------------------------------------------------------------------------
# User profiles
# ---------------------------------------------------------------------------

class InstructorProfile(models.Model):
    """Instructor-specific data attached to a Django User.

    Each User has at most one InstructorProfile. Instructors own courses
    (see Course.instructor). Kept separate from StudentProfile because the
    two roles have different attributes and different relationships.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.username


class StudentProfile(models.Model):
    """Student-specific data attached to a Django User.

    Students enroll in courses (see Enrollment) and upload QR code photos
    (see QRCodeUpload). student_id is unique so two students can never
    share an identity.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student_id = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.user.username


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------


class Course(models.Model):
    """A course taught by exactly one instructor.

    The meeting schedule is stored as the days it meets (e.g. "MWF") plus a
    start and end time. Students are linked through Enrollment (many-to-many).
    """

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, blank=True)  # e.g. "DATA 13600"
    instructor = models.ForeignKey(
        InstructorProfile,
        on_delete=models.PROTECT,
        related_name="courses",
    )
    meeting_days = models.CharField(max_length=20, help_text='e.g. "MWF"')
    start_time = models.TimeField()
    end_time = models.TimeField()
    students = models.ManyToManyField(
        StudentProfile, through="Enrollment", related_name="courses"
    )

    def __str__(self):
        return f"{self.code} {self.name}".strip()

# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------
class Enrollment(models.Model):
    """Links a student to a course (the many-to-many junction table).

    Stored as its own table so we can record when the student enrolled, and
    so a (student, course) pair can only exist once.
    """

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course"], name="unique_enrollment"
            )
        ]

    def __str__(self):
        return f"{self.student} in {self.course}"

# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------

def generate_qr_identifier(length=16):
    """Return a random alphanumeric string to be encoded in a lecture's QR code.

    Uses SystemRandom (cryptographically secure) so identifiers can't be
    predicted, which stops students from guessing a code they never saw.
    """
    alphabet = string.ascii_letters + string.digits
    rng = random.SystemRandom()
    return "".join(rng.choice(alphabet) for _ in range(length))
class Lecture(models.Model):
    """A single class meeting of a course.

    Each lecture gets a random, unique qr_identifier. That string is what the
    projected QR code encodes, and what uploads are matched against.
    """

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="lectures"
    )
    date = models.DateTimeField()
    qr_identifier = models.CharField(
        max_length=64, unique=True, default=generate_qr_identifier, editable=False
    )

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.course} on {self.date:%Y-%m-%d}"


# ---------------------------------------------------------------------------
# QR Code Upload
# ---------------------------------------------------------------------------

class QRCodeUpload(models.Model):
    """A student's uploaded photo of a lecture's QR code.

    The lecture is optional: an upload can be stored before we have decoded
    which lecture it belongs to. Anti-cheating fields: the server sets
    uploaded_at, decoded_text records what the image actually said, and
    image_hash flags the same photo being submitted twice. A student can have
    at most one upload per lecture.
    """

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="uploads"
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploads",
    )
    image = models.FileField(upload_to="qr_uploads/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    decoded_text = models.CharField(max_length=64, blank=True)
    image_hash = models.CharField(max_length=64, blank=True, db_index=True)
    is_valid = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["student", "lecture"], name="one_upload_per_student_lecture"
            )
        ]

    def __str__(self):
        return f"Upload by {self.student} at {self.uploaded_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Helper / API functions
# ---------------------------------------------------------------------------
def is_enrolled(student, course):
    """Return True if the student is enrolled in the course."""
    return Enrollment.objects.filter(student=student, course=course).exists()


def record_attendance(student, decoded_text, image):
    """Record a student's QR upload and return the QRCodeUpload (or None).

    Finds the lecture whose qr_identifier matches decoded_text, checks the
    student is enrolled in that lecture's course, and refuses duplicates.
    Problems are logged rather than raised so callers can handle them.
    """
    try:
        lecture = Lecture.objects.get(qr_identifier=decoded_text)
    except Lecture.DoesNotExist:
        logger.warning("Student %s uploaded an unknown QR code", student)
        return None

    if not is_enrolled(student, lecture.course):
        logger.warning("Student %s is not enrolled in %s", student, lecture.course)
        return None

    upload, created = QRCodeUpload.objects.get_or_create(
        student=student,
        lecture=lecture,
        defaults={"image": image, "decoded_text": decoded_text, "is_valid": True},
    )
    if not created:
        logger.info("Student %s already checked in to %s", student, lecture)
    return upload


