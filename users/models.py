from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.utils import timezone

class UploadedImage(models.Model):
    image = models.ImageField(upload_to='images/')
    result = models.TextField(blank=True, null=True)

class User(AbstractUser):
    ROLE_CHOICES = [('admin', 'Admin'), ('employee', 'Employee')]
    email = models.EmailField(_('email address'), unique=True)
    phone_number = models.CharField(max_length=15, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='employee')
    employee_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    photo = models.ImageField(upload_to='employees/', blank=True, null=True)
    face_encoding = models.BinaryField(blank=True, null=True)
    department = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.username

    @property
    def is_admin_user(self):
        return self.role == 'admin' or self.is_superuser

    @property
    def is_employee(self):
        return self.role == 'employee' and not self.is_superuser

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')


class Violation(models.Model):
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='violations',
                                 null=True, blank=True, limit_choices_to={'role': 'employee'})
    violation_type = models.CharField(max_length=100)
    snapshot = models.ImageField(upload_to='violations/')                # annotated, for display
    clean_snapshot = models.ImageField(upload_to='violations/clean/',    # un-annotated, for face match
                                       null=True, blank=True)
    confidence = models.FloatField()
    source = models.CharField(max_length=20, default='live')
    timestamp = models.DateTimeField(auto_now_add=True)

    # SMS notification tracking
    sms_sent = models.BooleanField(default=False)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    sms_error = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        who = self.employee.username if self.employee else 'Unknown'
        return f"{self.violation_type} - {who}"




class Video(models.Model):
    STATUS_CHOICES = [
        ('uploading', 'Uploading'),
        ('processing', 'Processing'),
        ('analyzing', 'Analyzing'),
        ('recognized_eating', 'Recognized: Eating'),
        ('recognized_walking', 'Recognized: Walking'),
        ('recognized_running', 'Recognized: Running'),
        ('recognized_sitting', 'Recognized: Sitting'),
        ('recognized_yoga', 'Recognized: Yoga'),
        ('recognized_dancing', 'Recognized: Dancing'),
        ('not_recognized', 'Activity Not Recognized'),
        ('failed', 'Failed')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='videos')
    title = models.CharField(max_length=100)
    video_file = models.FileField(upload_to='videos/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='uploading')
    status_message = models.TextField(blank=True, null=True)
    recognized_activity = models.CharField(max_length=50, blank=True, null=True)
    confidence_score = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-uploaded_at']

class VideoProcess(models.Model):
    uploaded_file = models.FileField(upload_to='uploads/')
    output_file = models.FileField(upload_to='outputs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.uploaded_file.name} -> {self.output_file.name}"
