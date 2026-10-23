# LLM: Claude (Anthropic), Sonnet 5.5
# Prompt: [uploaded the HW3 instructions PDF] "help me with step 5 which I stopped generate an LLM Data Model"
# Result: Claude responded to the prompt by generating a models.py for the
# AttendanceChimp specification in the PDF (InstructorProfile, StudentProfile,
# Course, Enrollment, Lecture, QRCodeUpload). No special emphasis or
# deliberate mistakes were requested.
AttendanceChimp data model (HW3).
 
Design notes
------------
* Users: Django's built-in User handles login/passwords. Role-specific data
  lives in two separate profile tables (InstructorProfile / StudentProfile),
  each linked one-to-one to a User. Two tables are better than one "Users"
  table with a role flag because students and instructors have different
  attributes (e.g. student_id vs. department) and different relationships
  (instructors teach courses; students enroll and upload QR photos).
* Course -> one instructor (ForeignKey). Students <-> Courses is many-to-many,
  made explicit through the Enrollment table so we can store extra data
  (enrolled_at) and enforce "one enrollment per student per course".
* Lecture -> one course. Each lecture gets a unique, hard-to-guess QR
  identifier that is what the projected QR code encodes.
* QRCodeUpload -> one student and (optionally) one lecture. The lecture is
  optional because the upload may arrive before we've decoded which lecture
  its QR code belongs to.
 
Anti-cheating features
----------------------
* Lecture.qr_identifier is random (uuid4 hex) and unique.
* QRCodeUpload.uploaded_at is set by the server, not the client.
* QRCodeUpload.decoded_text records what the QR code actually said.
* QRCodeUpload.image_hash lets us detect the same photo being re-submitted
  (e.g. a friend forwarding a picture of the code).
* A student can have at most one upload per lecture (UniqueConstraint).
* Enrollment is checked via helper methods so a student cannot be marked
  present for a course they are not enrolled in.
"""
import uuid
 
from django.contrib.auth.models import User
from django.db import models
 
 
def new_qr_identifier():
    """Return a fresh random identifier to be encoded in a lecture's QR code."""
    return uuid.uuid4().hex
 
 
class InstructorProfile(models.Model):
    """Instructor-specific data attached to a Django User."""
 
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="instructor_profile"
    )
    department = models.CharField(max_length=100, blank=True)
 
    def __str__(self):
        return f"Instructor: {self.user.get_full_name() or self.user.username}"
 
 
class StudentProfile(models.Model):
    """Student-specific data attached to a Django User."""
 
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="student_profile"
    )
    student_id = models.CharField(max_length=20, unique=True)
 
    def __str__(self):
        return f"Student: {self.user.get_full_name() or self.user.username}"
 
 
class Course(models.Model):
    """A course taught by exactly one instructor."""
 
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, blank=True)  # e.g. "DATA 13600"
    instructor = models.ForeignKey(
        InstructorProfile,
        on_delete=models.PROTECT,  # don't silently delete courses with an instructor
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
 
 
class Enrollment(models.Model):
    """Links a student to a course (the many-to-many through table)."""
 
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
 
 
class Lecture(models.Model):
    """One class meeting of a course, identified by a unique QR identifier."""
 
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="lectures"
    )
    date = models.DateTimeField()
    qr_identifier = models.CharField(
        max_length=64, unique=True, default=new_qr_identifier, editable=False
    )
 
    class Meta:
        ordering = ["date"]
 
    def __str__(self):
        return f"{self.course} on {self.date:%Y-%m-%d}"
 
 
class QRCodeUpload(models.Model):
    """A photo of a QR code uploaded by a student as proof of attendance."""
 
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="uploads"
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,  # keep the upload record if a lecture is removed
        null=True,
        blank=True,
        related_name="uploads",
    )
    # FileField (not ImageField) so Django runs without Pillow installed.
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
 
    def is_enrolled(self):
        """True if the uploading student is enrolled in the lecture's course."""
        if self.lecture is None:
            return False
        return Enrollment.objects.filter(
            student=self.student, course=self.lecture.course
        ).exists()
 
    def matches_lecture(self):
        """True if the decoded QR text equals the lecture's QR identifier."""
        return self.lecture is not None and self.decoded_text == self.lecture.qr_identifier
 
    def __str__(self):
        return f"Upload by {self.student} at {self.uploaded_at:%Y-%m-%d %H:%M}"
 