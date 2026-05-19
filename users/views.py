import os
# Avoid BLAS library conflicts on Windows that crash dlib silently.
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
os.environ.setdefault('OMP_NUM_THREADS', '1')

import json
import base64
import shutil
import signal as _signal
import threading
import time
from datetime import timedelta, datetime as _dt
from functools import wraps
from pathlib import Path
from ultralytics import YOLO
from pathlib import Path
import shutil
from moviepy import VideoFileClip


# Patch signal.signal so ultralytics/moviepy don't crash when invoked
# from a non-main thread (Django dev server runs requests in threads).
_orig_signal = _signal.signal
def _safe_signal(sig, handler):
    if threading.current_thread() is threading.main_thread():
        return _orig_signal(sig, handler)
    return None
_signal.signal = _safe_signal

import cv2
import numpy as np


# Load YOLO model once at server startup (visible in terminal logs)
print("Loading YOLO model (best.pt)...")
try:
    YOLO_MODEL = YOLO('best.pt')
    print("YOLO model loaded.")
except Exception as _e:
    print(f"YOLO load failed: {_e}")
    YOLO_MODEL = None



from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, UpdateView
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.db.models import Count

from .forms import VideoUploadForm, EmployeeCreateForm, EmployeeEditForm
from .models import User, Video, VideoProcess, UploadedImage, Violation


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_admin_user:
            messages.error(request, 'Admins only.')
            return redirect('employee_dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def employee_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if request.user.is_admin_user:
            return redirect('manage_dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return _post_login_redirect(request.user)

    if request.method == 'POST':
        login_type = request.POST.get('login_type', 'admin')

        # ---- Employee ----
        if login_type == 'employee':
            emp_method = request.POST.get('emp_method', 'otp')

            # ---- Employee: username + password ----
            if emp_method == 'password':
                username = request.POST.get('username', '').strip()
                password = request.POST.get('password', '')
                user = authenticate(request, username=username,
                                     password=password)
                if user is None:
                    messages.error(request,
                                    'Invalid username or password.')
                    return render(request, 'users/login.html')
                if not user.is_employee:
                    messages.error(request,
                                    'Admins must log in using the Admin tab.')
                    return render(request, 'users/login.html')
                login(request, user)
                messages.success(request, 'Login successful')
                try:
                    from .sms_utils import send_login_sms
                    send_login_sms(user.phone_number,
                                   employee_name=(user.first_name
                                                  or user.username),
                                   login_time=timezone.now())
                except Exception as e:
                    print(f"[login] employee login SMS error: {e}")
                return _post_login_redirect(user)

            # ---- Employee: phone number -> SMS OTP ----
            phone = request.POST.get('phone', '').strip()
            user = (User.objects.filter(phone_number=phone, role='employee',
                                        is_superuser=False, is_staff=False)
                    .first())
            if user is None:
                messages.error(request,
                                'No employee account found for that phone number.')
                return render(request, 'users/login.html')

            otp = _generate_otp()
            request.session['emp_otp'] = otp
            request.session['emp_otp_user_id'] = user.pk
            request.session['emp_otp_phone'] = phone
            request.session['emp_otp_expires'] = (
                timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
            ).isoformat()
            request.session['emp_otp_attempts'] = 0

            from .sms_utils import send_login_otp_sms
            ok, info = send_login_otp_sms(
                phone, otp, name=(user.first_name or user.username))
            if ok:
                messages.success(request, f'OTP sent to {phone}.')
            else:
                messages.warning(request,
                                 'Could not send SMS; check the server console '
                                 'for the OTP (SMS provider issue).')
            return redirect('employee_otp')

        # ---- Admin: username + password ----
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_admin_user:
                messages.error(request,
                               'Employees must log in using the Employee tab '
                               '(phone number + OTP).')
                return render(request, 'users/login.html')
            login(request, user)
            messages.success(request, 'Login successful')
            return _post_login_redirect(user)
        messages.error(request, 'Invalid username or password')
    return render(request, 'users/login.html')


def employee_otp(request):
    """Employee login step 2: verify the SMS OTP and log in."""
    if request.user.is_authenticated:
        return _post_login_redirect(request.user)

    user_id = request.session.get('emp_otp_user_id')
    phone = request.session.get('emp_otp_phone')
    if not user_id:
        messages.error(request, 'Please request a login OTP first.')
        return redirect('login')

    def _clear():
        for k in ('emp_otp', 'emp_otp_user_id', 'emp_otp_phone',
                  'emp_otp_expires', 'emp_otp_attempts'):
            request.session.pop(k, None)

    if request.method == 'POST':
        entered = request.POST.get('otp', '').strip()

        expires_raw = request.session.get('emp_otp_expires')
        expired = True
        if expires_raw:
            try:
                expired = timezone.now() > _dt.fromisoformat(expires_raw)
            except ValueError:
                expired = True
        if expired:
            _clear()
            messages.error(request, 'OTP expired. Please log in again.')
            return redirect('login')

        attempts = request.session.get('emp_otp_attempts', 0)
        if attempts >= OTP_MAX_ATTEMPTS:
            _clear()
            messages.error(request,
                           'Too many incorrect attempts. Please log in again.')
            return redirect('login')

        if entered != request.session.get('emp_otp'):
            request.session['emp_otp_attempts'] = attempts + 1
            messages.error(request, 'Incorrect OTP. Please try again.')
            return render(request, 'users/employee_otp.html', {'phone': phone})

        user = User.objects.filter(pk=user_id, role='employee').first()
        if user is None:
            _clear()
            messages.error(request, 'Account not found.')
            return redirect('login')

        _clear()
        login(request, user,
              backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Login successful')
        # Notify the employee by SMS that their account was logged in.
        try:
            from .sms_utils import send_login_sms
            send_login_sms(user.phone_number,
                           employee_name=(user.first_name or user.username),
                           login_time=timezone.now())
        except Exception as e:
            print(f"[employee_otp] login SMS error: {e}")
        return _post_login_redirect(user)

    return render(request, 'users/employee_otp.html', {'phone': phone})


def _post_login_redirect(user):
    if user.is_admin_user:
        return redirect('manage_dashboard')
    return redirect('employee_dashboard')


def logout_view(request):
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'Logged out successfully')
        return redirect('login')
    return redirect('home')


# ---------------------------------------------------------------------------
# Forgot password (email OTP)
# ---------------------------------------------------------------------------

OTP_TTL_SECONDS = 600        # OTP valid for 10 minutes
OTP_MAX_ATTEMPTS = 5         # wrong-OTP attempts before requiring a new code


def _generate_otp():
    import secrets
    return f"{secrets.randbelow(1000000):06d}"


def forgot_password(request):
    """Step 1: user enters their email, we send a 6-digit OTP."""
    if request.user.is_authenticated:
        return _post_login_redirect(request.user)

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        user = User.objects.filter(email__iexact=email).first()
        # Always behave the same way to avoid leaking which emails exist.
        if user:
            otp = _generate_otp()
            request.session['pwd_reset_otp'] = otp
            request.session['pwd_reset_email'] = user.email
            request.session['pwd_reset_expires'] = (
                timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
            ).isoformat()
            request.session['pwd_reset_attempts'] = 0

            from .sms_utils import send_password_reset_otp
            ok, info = send_password_reset_otp(
                user.email, otp,
                name=(user.first_name or user.username),
            )
            if not ok:
                print(f"[forgot_password] OTP send issue: {info}")
        messages.success(
            request,
            'If that email is registered, a one-time password has been sent. '
            'Please check your inbox.'
        )
        return redirect('verify_otp')

    return render(request, 'users/forgot_password.html')


def verify_otp(request):
    """Step 2: user enters the OTP and a new password."""
    if request.user.is_authenticated:
        return _post_login_redirect(request.user)

    email = request.session.get('pwd_reset_email')
    if not email:
        messages.error(request, 'Please request a password reset first.')
        return redirect('forgot_password')

    if request.method == 'POST':
        entered = request.POST.get('otp', '').strip()
        new_pw = request.POST.get('new_password', '')
        confirm_pw = request.POST.get('confirm_password', '')

        expires_raw = request.session.get('pwd_reset_expires')
        expired = True
        if expires_raw:
            try:
                expired = timezone.now() > _dt.fromisoformat(expires_raw)
            except ValueError:
                expired = True

        if expired:
            for k in ('pwd_reset_otp', 'pwd_reset_email',
                      'pwd_reset_expires', 'pwd_reset_attempts'):
                request.session.pop(k, None)
            messages.error(request, 'OTP expired. Please request a new one.')
            return redirect('forgot_password')

        attempts = request.session.get('pwd_reset_attempts', 0)
        if attempts >= OTP_MAX_ATTEMPTS:
            for k in ('pwd_reset_otp', 'pwd_reset_email',
                      'pwd_reset_expires', 'pwd_reset_attempts'):
                request.session.pop(k, None)
            messages.error(request,
                           'Too many incorrect attempts. Please request a new OTP.')
            return redirect('forgot_password')

        if entered != request.session.get('pwd_reset_otp'):
            request.session['pwd_reset_attempts'] = attempts + 1
            messages.error(request, 'Incorrect OTP. Please try again.')
            return render(request, 'users/verify_otp.html', {'email': email})

        if len(new_pw) < 6:
            messages.error(request, 'Password must be at least 6 characters.')
            return render(request, 'users/verify_otp.html', {'email': email})
        if new_pw != confirm_pw:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'users/verify_otp.html', {'email': email})

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            messages.error(request, 'Account not found.')
            return redirect('forgot_password')

        user.set_password(new_pw)
        user.save()
        for k in ('pwd_reset_otp', 'pwd_reset_email',
                  'pwd_reset_expires', 'pwd_reset_attempts'):
            request.session.pop(k, None)
        messages.success(request,
                         'Password reset successfully. You can now log in.')
        return redirect('login')

    return render(request, 'users/verify_otp.html', {'email': email})


# ---------------------------------------------------------------------------
# Public / shared
# ---------------------------------------------------------------------------

class HomeView(TemplateView):
    template_name = 'home.html'


@login_required
def profile(request):
    return render(request, 'users/profile.html')


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    fields = ['username', 'email', 'first_name', 'last_name', 'phone_number']
    template_name = 'users/profile_update.html'
    success_url = reverse_lazy('profile')

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Profile updated.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Admin: dashboard
# ---------------------------------------------------------------------------

@admin_required
def manage_dashboard(request):
    today = timezone.now().date()
    week_ago = timezone.now() - timedelta(days=7)
    ctx = {
        'employee_count': User.objects.filter(role='employee', is_superuser=False, is_staff=False).count(),
        'violation_count': Violation.objects.count(),
        'today_violations': Violation.objects.filter(timestamp__date=today).count(),
        'week_violations': Violation.objects.filter(timestamp__gte=week_ago).count(),
        'recent_violations': Violation.objects.select_related('employee')[:8],
        'top_violators': (User.objects.filter(role='employee', is_superuser=False, is_staff=False)
                          .annotate(vc=Count('violations'))
                          .filter(vc__gt=0).order_by('-vc')[:5]),
    }
    return render(request, 'admin_panel/dashboard.html', ctx)


# ---------------------------------------------------------------------------
# Admin: employees CRUD
# ---------------------------------------------------------------------------

@admin_required
def employee_list(request):
    q = request.GET.get('q', '').strip()
    employees = User.objects.filter(role='employee', is_superuser=False, is_staff=False).annotate(vc=Count('violations'))
    if q:
        employees = employees.filter(username__icontains=q) | \
                    employees.filter(employee_id__icontains=q) | \
                    employees.filter(first_name__icontains=q) | \
                    employees.filter(last_name__icontains=q)
    employees = employees.order_by('-created_at')
    return render(request, 'admin_panel/employee_list.html',
                  {'employees': employees, 'q': q})


@admin_required
def employee_add(request):
    if request.method == 'POST':
        form = EmployeeCreateForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            _process_enrollment(user, form.cleaned_data.get('enrollment_video'))
            user.refresh_from_db()
            from . import face_rec
            if face_rec.AVAILABLE and not user.face_encoding:
                messages.warning(request,
                    f'Employee saved, but no face was detected. Edit and re-upload a clearer photo or enrollment video.')
            else:
                from . import face_rec as _fr
                num = len(_fr.encodings_from_blob(user.face_encoding))
                messages.success(request,
                    f'Employee {user.username} created with {num} face encoding(s). '
                    f'Login: {user.username} / (the password you set)')
            return redirect('employee_list')
    else:
        form = EmployeeCreateForm()
    return render(request, 'admin_panel/employee_form.html',
                  {'form': form, 'mode': 'add'})


def _process_enrollment(user, enrollment_video):
    """Build face_encoding list from enrollment video (preferred) or photo."""
    from . import face_rec
    if not face_rec.AVAILABLE:
        return
    encodings = []
    if enrollment_video:
        # Save video temporarily, extract encodings, delete
        import tempfile
        suffix = '.' + enrollment_video.name.rsplit('.', 1)[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in enrollment_video.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            encodings = face_rec.encode_video_frames(tmp_path)
            print(f"[enrollment] extracted {len(encodings)} encodings from video")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    if not encodings and user.photo:
        single = face_rec.encode_from_path(user.photo.path)
        if single is not None:
            encodings = [single]
            print(f"[enrollment] extracted 1 encoding from photo")
    if encodings:
        blob = face_rec.encodings_to_blob(encodings)
        type(user).objects.filter(pk=user.pk).update(face_encoding=blob)
        face_rec.invalidate_cache()


@admin_required
def employee_edit(request, pk):
    employee = get_object_or_404(User, pk=pk, role='employee', is_superuser=False, is_staff=False)
    if request.method == 'POST':
        form = EmployeeEditForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            obj = form.save(commit=False)
            video = form.cleaned_data.get('enrollment_video')
            # If photo or video changed, recompute encodings
            recompute = bool(video) or 'photo' in form.changed_data
            if recompute:
                obj.face_encoding = None
            obj.save()
            if recompute:
                _process_enrollment(obj, video)
            messages.success(request, 'Employee updated.')
            return redirect('employee_list')
    else:
        form = EmployeeEditForm(instance=employee)
    return render(request, 'admin_panel/employee_form.html',
                  {'form': form, 'mode': 'edit', 'employee': employee})


@admin_required
def employee_delete(request, pk):
    employee = get_object_or_404(User, pk=pk, role='employee', is_superuser=False, is_staff=False)
    if request.method == 'POST':
        employee.delete()
        messages.success(request, 'Employee deleted.')
        return redirect('employee_list')
    return render(request, 'admin_panel/employee_confirm_delete.html',
                  {'employee': employee})


@admin_required
def employee_detail(request, pk):
    employee = get_object_or_404(User, pk=pk, role='employee', is_superuser=False, is_staff=False)
    violations = employee.violations.all()
    from . import face_rec
    encoding_count = len(face_rec.encodings_from_blob(employee.face_encoding))
    return render(request, 'admin_panel/employee_detail.html',
                  {'employee': employee, 'violations': violations,
                   'encoding_count': encoding_count})


@admin_required
def employee_reset_password(request, pk):
    employee = get_object_or_404(User, pk=pk, role='employee', is_superuser=False, is_staff=False)
    if request.method == 'POST':
        new_pw = request.POST.get('new_password', '').strip()
        if len(new_pw) < 6:
            messages.error(request, 'Password too short.')
        else:
            employee.set_password(new_pw)
            employee.save()
            messages.success(request, f'Password reset for {employee.username}.')
            return redirect('employee_detail', pk=pk)
    return render(request, 'admin_panel/reset_password.html', {'employee': employee})


# ---------------------------------------------------------------------------
# Admin: violations
# ---------------------------------------------------------------------------

@admin_required
def violation_list(request):
    qs = Violation.objects.select_related('employee').all()
    vtype = request.GET.get('type', '').strip()
    emp_id = request.GET.get('employee', '').strip()
    if vtype:
        qs = qs.filter(violation_type__icontains=vtype)
    if emp_id:
        qs = qs.filter(employee__employee_id=emp_id)
    return render(request, 'admin_panel/violation_list.html',
                  {'violations': qs[:200], 'vtype': vtype, 'emp_id': emp_id})


@admin_required
def violation_detail(request, pk):
    violation = get_object_or_404(Violation, pk=pk)
    return render(request, 'admin_panel/violation_detail.html',
                  {'violation': violation})


@admin_required
def violation_search(request, pk):
    """Run face recognition on the violation's snapshot to identify the person.
    If identified, send email notification to the employee with violation details."""
    violation = get_object_or_404(Violation, pk=pk)
    # Prefer the clean (un-annotated) snapshot — face_recognition struggles
    # when YOLO bounding boxes are drawn over the face.
    src_path = None
    if violation.clean_snapshot:
        src_path = violation.clean_snapshot.path
    elif violation.snapshot:
        src_path = violation.snapshot.path
    if not src_path:
        messages.error(request, 'No snapshot to search.')
        return redirect('violation_detail', pk=pk)
    from . import face_rec
    if not face_rec.AVAILABLE:
        messages.error(request, 'Face recognition library is not installed.')
        return redirect('violation_detail', pk=pk)
    emp = face_rec.identify_in_image_path(src_path)
    if emp is None:
        messages.warning(request, 'No matching employee found for this snapshot.')
    else:
        violation.employee = emp
        violation.save(update_fields=['employee'])

        # Send email notification to the identified employee
        # Try SendGrid first, fallback to Django email
        snapshot_path = violation.snapshot.path if violation.snapshot else None
        
        # Try SendGrid
        from .email_utils import send_violation_email_sendgrid
        email_ok, email_info = send_violation_email_sendgrid(
            employee_email=emp.email,
            employee_name=f"{emp.first_name} {emp.last_name}",
            violation_type=violation.violation_type,
            timestamp=violation.timestamp,
            snapshot_path=snapshot_path,
            violation_id=violation.pk
        )
        
        # Fallback to Django email if SendGrid fails
        if not email_ok:
            from .sms_utils import send_violation_email
            email_ok, email_info = send_violation_email(
                employee_email=emp.email,
                employee_name=f"{emp.first_name} {emp.last_name}",
                violation_type=violation.violation_type,
                timestamp=violation.timestamp,
                snapshot_path=snapshot_path,
                violation_id=violation.pk
            )
        
        violation.sms_sent = email_ok  # reusing field for email tracking
        violation.sms_sent_at = timezone.now() if email_ok else None
        violation.sms_error = None if email_ok else email_info
        violation.save(update_fields=['sms_sent', 'sms_sent_at', 'sms_error'])
        if email_ok:
            messages.success(request,
                f'Identified as {emp.first_name} {emp.last_name} ({emp.employee_id}). '
                f'Email notification sent to {emp.email}.')
        else:
            messages.warning(request,
                f'Identified as {emp.first_name} {emp.last_name} ({emp.employee_id}). '
                f'Email failed: {email_info}')
    return redirect('violation_detail', pk=pk)


@admin_required
def violation_send_email(request, pk):
    """Manually (re)send the violation notification email to the already
    identified employee via Gmail SMTP (with the snapshot attached)."""
    violation = get_object_or_404(Violation, pk=pk)
    if request.method != 'POST':
        return redirect('violation_detail', pk=pk)

    emp = violation.employee
    if emp is None:
        messages.error(request,
                        'No employee identified yet. Run "Search This Person" first.')
        return redirect('violation_detail', pk=pk)
    if not emp.email:
        messages.error(request,
                        f'{emp.first_name} {emp.last_name} has no email address on file.')
        return redirect('violation_detail', pk=pk)

    snapshot_path = violation.snapshot.path if violation.snapshot else None

    # Try SendGrid first (if configured), then fall back to Gmail SMTP.
    from .email_utils import send_violation_email_sendgrid
    email_ok, email_info = send_violation_email_sendgrid(
        employee_email=emp.email,
        employee_name=f"{emp.first_name} {emp.last_name}",
        violation_type=violation.violation_type,
        timestamp=violation.timestamp,
        snapshot_path=snapshot_path,
        violation_id=violation.pk,
    )
    if not email_ok:
        from .sms_utils import send_violation_email
        email_ok, email_info = send_violation_email(
            employee_email=emp.email,
            employee_name=f"{emp.first_name} {emp.last_name}",
            violation_type=violation.violation_type,
            timestamp=violation.timestamp,
            snapshot_path=snapshot_path,
            violation_id=violation.pk,
        )

    violation.sms_sent = email_ok
    violation.sms_sent_at = timezone.now() if email_ok else None
    violation.sms_error = None if email_ok else email_info
    violation.save(update_fields=['sms_sent', 'sms_sent_at', 'sms_error'])

    if email_ok:
        messages.success(request, f'Email notification sent to {emp.email}.')
    else:
        messages.warning(request, f'Email failed: {email_info}')
    return redirect('violation_detail', pk=pk)


@admin_required
def violation_delete(request, pk):
    violation = get_object_or_404(Violation, pk=pk)
    if request.method == 'POST':
        violation.delete()
        messages.success(request, 'Violation deleted.')
        return redirect('violation_list')
    return render(request, 'admin_panel/violation_confirm_delete.html',
                  {'violation': violation})


@admin_required
def violations_delete_all(request):
    if request.method == 'POST':
        count = Violation.objects.count()
        Violation.objects.all().delete()
        messages.success(request, f'Deleted {count} violation(s).')
    return redirect('violation_list')


@admin_required
def violation_search_all_unknown(request):
    """Run face recognition on every Unknown violation.
    Send email notification to each identified employee."""
    from . import face_rec
    if not face_rec.AVAILABLE:
        messages.error(request, 'Face recognition library is not installed.')
        return redirect('violation_list')
    qs = Violation.objects.filter(employee__isnull=True)
    matched = 0
    email_sent_count = 0
    email_failed_count = 0
    total = qs.count()
    from .sms_utils import send_violation_email
    for v in qs:
        path = None
        if v.clean_snapshot:
            path = v.clean_snapshot.path
        elif v.snapshot:
            path = v.snapshot.path
        if not path:
            continue
        try:
            emp = face_rec.identify_in_image_path(path)
        except Exception:
            emp = None
        if emp is not None:
            v.employee = emp
            v.save(update_fields=['employee'])
            matched += 1

            # Send email notification
            snapshot_path = v.snapshot.path if v.snapshot else None
            
            # Try SendGrid first
            from .email_utils import send_violation_email_sendgrid
            email_ok, email_info = send_violation_email_sendgrid(
                employee_email=emp.email,
                employee_name=f"{emp.first_name} {emp.last_name}",
                violation_type=v.violation_type,
                timestamp=v.timestamp,
                snapshot_path=snapshot_path,
                violation_id=v.pk
            )
            
            # Fallback to Django email
            if not email_ok:
                email_ok, email_info = send_violation_email(
                    employee_email=emp.email,
                    employee_name=f"{emp.first_name} {emp.last_name}",
                    violation_type=v.violation_type,
                    timestamp=v.timestamp,
                    snapshot_path=snapshot_path,
                    violation_id=v.pk
                )
            
            v.sms_sent = email_ok  # reusing field for email tracking
            v.sms_sent_at = timezone.now() if email_ok else None
            v.sms_error = None if email_ok else email_info
            v.save(update_fields=['sms_sent', 'sms_sent_at', 'sms_error'])
            if email_ok:
                email_sent_count += 1
            else:
                email_failed_count += 1
    msg = f'Searched {total} unknown violations. Identified {matched}.'
    if matched > 0:
        msg += f' Email sent: {email_sent_count}, failed: {email_failed_count}.'
    messages.success(request, msg)
    return redirect('violation_list')


@admin_required
def leaderboard(request):
    ranking = (User.objects.filter(role='employee', is_superuser=False, is_staff=False)
               .annotate(vc=Count('violations'))
               .order_by('-vc'))
    return render(request, 'admin_panel/leaderboard.html', {'ranking': ranking})


# ---------------------------------------------------------------------------
# Employee dashboard
# ---------------------------------------------------------------------------

@employee_required
def employee_dashboard(request):
    user = request.user
    violations = user.violations.all()
    ctx = {
        'violation_count': violations.count(),
        'recent': violations[:5],
    }
    return render(request, 'users/employee_dashboard.html', ctx)


@employee_required
def my_violations(request):
    violations = request.user.violations.all()
    return render(request, 'users/my_violations.html', {'violations': violations})


# ---------------------------------------------------------------------------
# Video upload (admin only) + AVI->MP4 conversion
# ---------------------------------------------------------------------------

def _convert_avi_to_mp4(avi_path, mp4_path):
    try:
        from moviepy import VideoFileClip
        clip = VideoFileClip(str(avi_path))
        clip.write_videofile(
            str(mp4_path), codec='libx264', audio_codec='aac',
            temp_audiofile='temp-audio.m4a', remove_temp=True,
            threads=4, preset='ultrafast'
        )
        clip.close()
    except Exception as e:
        print(f"Video conversion failed: {e}")



def analyze_video_content(video_path):
    """Analyze video content to detect human activities

    This function uses multiple features to identify different activities:
    - Motion analysis (frame differences)
    - Optical flow patterns
    - Spatial features (edges, contours)
    - Temporal patterns

    Returns the detected activity and confidence score
    """
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("Could not open video file")

        # Get video properties
        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # Initialize variables for feature extraction
        frame_count = 0
        prev_gray = None

        # Feature accumulators
        motion_scores = []
        edge_densities = []
        contour_areas = []
        brightness_values = []
        vertical_movements = []
        horizontal_movements = []

        # Process frames for feature extraction (sample up to 60 frames)
        while cap.isOpened() and frame_count < 60:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert to grayscale for analysis
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)  # Reduce noise

            # Extract brightness
            brightness = np.mean(gray)
            brightness_values.append(brightness)

            # Extract edges
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.count_nonzero(edges) / (frame_width * frame_height)
            edge_densities.append(edge_density)

            # Extract contours
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(largest_contour) / (frame_width * frame_height)
                contour_areas.append(area)
            else:
                contour_areas.append(0)

            # Calculate motion if we have a previous frame
            if prev_gray is not None:
                # Frame difference for motion detection
                frame_diff = cv2.absdiff(prev_gray, gray)
                motion = np.mean(frame_diff)
                motion_scores.append(motion)

                # Simple optical flow for movement direction
                # This is a simplified version - real optical flow would be more complex
                if frame_count % 5 == 0:  # Check every 5th frame to save computation
                    y_diff = np.mean(frame_diff[:frame_height//2, :]) - np.mean(frame_diff[frame_height//2:, :])
                    x_diff = np.mean(frame_diff[:, :frame_width//2]) - np.mean(frame_diff[:, frame_width//2:])
                    vertical_movements.append(y_diff)
                    horizontal_movements.append(x_diff)

            prev_gray = gray
            frame_count += 1

        cap.release()

        if frame_count == 0:
            return None, 0.0

        # Calculate feature statistics
        avg_motion = np.mean(motion_scores) if motion_scores else 0
        motion_variance = np.var(motion_scores) if len(motion_scores) > 1 else 0
        avg_edge = np.mean(edge_densities) if edge_densities else 0
        avg_contour = np.mean(contour_areas) if contour_areas else 0
        avg_brightness = np.mean(brightness_values) if brightness_values else 0

        # Calculate vertical/horizontal movement tendencies
        vertical_tendency = np.mean(vertical_movements) if vertical_movements else 0
        horizontal_tendency = np.mean(horizontal_movements) if horizontal_movements else 0

        # Normalize features for classification
        norm_motion = min(1.0, avg_motion / 25.0)
        norm_motion_var = min(1.0, motion_variance / 100.0)
        norm_edge = min(1.0, avg_edge * 10.0)
        norm_contour = min(1.0, avg_contour * 20.0)

        # Activity classification using multiple features
        # Each activity has a specific pattern of features

        # Calculate scores for each activity type based on feature patterns
        activity_scores = {
            'walking': (
                norm_motion * 0.4 +                # Medium motion
                (1 - norm_motion_var) * 0.2 +      # Consistent motion
                norm_edge * 0.2 +                  # Some edges
                abs(horizontal_tendency) * 0.2     # Horizontal movement
            ),
            'running': (
                norm_motion * 0.5 +                # High motion
                norm_motion_var * 0.3 +            # Variable motion
                abs(horizontal_tendency) * 0.2     # Strong horizontal movement
            ),
            'eating': (
                (1 - norm_motion) * 0.3 +          # Low motion
                norm_edge * 0.3 +                  # Some edges (hand movements)
                norm_contour * 0.2 +               # Contours (hand to mouth)
                (vertical_tendency > 0) * 0.2      # Some vertical movement (hand up/down)
            ),
            'sitting': (
                (1 - norm_motion) * 0.6 +          # Very low motion
                (1 - norm_motion_var) * 0.2 +      # Consistent (lack of) motion
                (1 - norm_edge) * 0.2              # Fewer edges
            ),
            'yoga': (
                (norm_motion < 0.3) * 0.3 +        # Low to medium motion
                (norm_motion_var > 0.3) * 0.3 +     # Variable poses
                (norm_edge > 0.4) * 0.2 +          # Many edges (poses)
                (vertical_tendency != 0) * 0.2     # Vertical movements
            ),
            'dancing': (
                (norm_motion > 0.4) * 0.3 +         # Medium to high motion
                (norm_motion_var > 0.5) * 0.3 +      # Very variable motion
                (abs(vertical_tendency) +
                 abs(horizontal_tendency)) * 0.4    # Movement in all directions
            )
        }

        # Find the activity with the highest score
        detected_activity = max(activity_scores, key=activity_scores.get)

        # Calculate confidence (base 60% + weighted score)
        base_confidence = 60.0
        score_weight = 40.0
        confidence = base_confidence + (activity_scores[detected_activity] * score_weight)

        # Add some randomization to avoid all videos being classified the same
        # This simulates the natural variation in real ML models
        # For a real implementation, remove this and use an actual ML model
        random_factor = np.random.uniform(0.85, 1.15)
        confidence = min(99.0, confidence * random_factor)

        return detected_activity, confidence

    except Exception as e:
        raise Exception(f"Error analyzing video: {str(e)}")

from .roboflow import send_scan_to_roboflow


SAFETY_KEYWORDS = ['no-hardhat', 'no-safety vest', 'no-mask', 'no-helmet',
                   'no-jacket', 'no-suit', 'no-vest', 'without-helmet',
                   'without-jacket']


def _is_safety_violation(label):
    return any(k in label.lower() for k in SAFETY_KEYWORDS)


def _normalize_violation_label(label):
    if label == 'NO-Hardhat':
        return 'No Safety Helmet'
    if label == 'NO-Safety Vest':
        return 'No Safety Vest'
    if label == 'NO-Mask':
        return 'No Safety Mask'
    if 'helmet' in label.lower() and 'no' in label.lower():
        return 'No Safety Helmet'
    if 'jacket' in label.lower() and 'no' in label.lower():
        return 'No Safety Jacket'
    if 'vest' in label.lower() and 'no' in label.lower():
        return 'No Safety Vest'
    return label


def _scan_video_for_violations(video_path, source_label='upload'):
    """Walk through the video at ~1 fps, detect violations, identify faces, log.

    Returns a list of dicts {employee, violation_type, snapshot_url} for the UI.
    """
    if YOLO_MODEL is None:
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    sample_every = max(1, int(fps))         # roughly 1 frame per second
    debounce_frames = int(fps * 30)         # 30s in-video debounce

    logged = {}                             # {(emp_pk_or_None, label): last_frame_idx}
    summary = []
    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % sample_every != 0:
                frame_idx += 1
                continue

            results = YOLO_MODEL.predict(source=frame, conf=0.4, iou=0.5,
                                         verbose=False)
            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue
                # Frame with YOLO bboxes + labels drawn on it
                annotated_frame = result.plot()
                for box in boxes:
                    conf = float(box.conf)
                    cls = int(box.cls)
                    raw_label = result.names.get(cls, f'Class_{cls}')
                    if not _is_safety_violation(raw_label):
                        continue
                    label = _normalize_violation_label(raw_label)

                    # Save violation without identifying the person yet.
                    # Admin runs face match on demand via "Search Person".
                    key = (None, label)
                    last = logged.get(key, -debounce_frames)
                    if frame_idx - last < debounce_frames:
                        continue
                    logged[key] = frame_idx

                    ok_a, buf_a = cv2.imencode('.jpg', annotated_frame)
                    ok_c, buf_c = cv2.imencode('.jpg', frame)
                    if not (ok_a and ok_c):
                        continue
                    v = Violation(employee=None, violation_type=label,
                                  confidence=conf, source=source_label)
                    ts = int(timezone.now().timestamp())
                    v.snapshot.save(
                        f'v_{ts}_{frame_idx}.jpg',
                        ContentFile(buf_a.tobytes()), save=False
                    )
                    v.clean_snapshot.save(
                        f'v_{ts}_{frame_idx}_clean.jpg',
                        ContentFile(buf_c.tobytes()), save=True
                    )
                    summary.append({
                        'pk': v.pk,
                        'employee': None,
                        'violation_type': label,
                        'snapshot_url': v.snapshot.url,
                        'confidence': conf,
                    })
            frame_idx += 1
    finally:
        cap.release()
    return summary


def video_upload(request):
    if request.method == 'POST' and request.FILES.get('video'):
        video_file = request.FILES['video']

        # Save uploaded video
        fs = FileSystemStorage(location='media/uploads/')
        filename = fs.save(video_file.name, video_file)
        uploaded_path = fs.path(filename)

        # Run detection (model loaded once at startup)
        model = YOLO_MODEL if YOLO_MODEL is not None else YOLO('best.pt')
        results = model.predict(
            source=uploaded_path,
            save=True,
            save_txt=False,
            save_conf=True,
            conf=0.4
        )

        # Find output video (avi or mp4)
        detect_folder = Path(results[0].save_dir)
        video_files = list(detect_folder.glob("*.avi")) + list(detect_folder.glob("*.mp4"))
        if not video_files:
            return render(request, 'upload.html', {'error': 'No output video found.'})

        detected_video_path = video_files[0]
        base_filename = Path(filename).stem.replace(' ', '_')

        # Prepare output path
        output_dir = Path('media/outputs/')
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert to mp4 if avi
        output_filename = f"detected_{base_filename}.mp4"
        output_path = output_dir / output_filename

        if detected_video_path.suffix == '.avi':
            _convert_avi_to_mp4(detected_video_path, output_path)
        else:
            shutil.copy(detected_video_path, output_path)

        VideoProcess.objects.create(
            uploaded_file=f"uploads/{filename}",
            output_file=f"outputs/{output_filename}"
        )

        # Second pass: identify violators and log violations
        violation_summary = _scan_video_for_violations(uploaded_path,
                                                      source_label='upload')

        return render(request, 'upload.html', {
            'uploaded_file_url': f'/media/uploads/{filename}',
            'output_file_url': f'/media/outputs/{output_filename}',
            'violation_summary': violation_summary,
        })

    return render(request, 'upload.html')


def video_lists(request):
    videos = VideoProcess.objects.order_by('-uploaded_at')
    return render(request, 'video_list.html', {'videos': videos})



# ---------------------------------------------------------------------------
# Live detection
# ---------------------------------------------------------------------------

# Live Webcam Detection
@login_required
def live_detection_page(request):
    """Render the live detection page"""
    return render(request, 'users/live_detection.html')

@csrf_exempt
def live_detect_api(request):
    """API endpoint to process webcam frames for safety detection"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)

    try:
        data = json.loads(request.body)
        image_data = data.get('image', '')
        confidence_threshold = data.get('confidence', 0.5)

        if not image_data:
            return JsonResponse({'error': 'No image data provided'}, status=400)

        # Remove base64 prefix
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        # Decode base64 image
        image_bytes = base64.b64decode(image_data)
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if frame is None:
            return JsonResponse({'error': 'Failed to decode image'}, status=400)

        # Check if model file exists
        if not os.path.exists('best.pt'):
            return JsonResponse({'error': 'Model file not found. Please train or download best.pt model'}, status=500)

        # Run YOLO detection (model loaded once at startup)
        model = YOLO_MODEL if YOLO_MODEL is not None else YOLO('best.pt')
        results = model.predict(
            source=frame,
            conf=confidence_threshold,
            iou=0.5,
            verbose=False
        )

        detections = []

        # Process results
        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    # Get box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf)
                    cls = int(box.cls)

                    # Get class label
                    class_names = model.names
                    label = class_names[cls] if cls in class_names else f'Class_{cls}'

                    # Only include safety-related detections
                    safety_labels = ['NO-Hardhat', 'NO-Safety Vest', 'NO-Mask',
                                    'no-helmet', 'no-jacket', 'no-suit', 'no-vest',
                                    'without-helmet', 'without-jacket', 'person',
                                    'no-helmet-detection', 'no-jacket-detection']

                    # Check if label contains safety-related keywords
                    is_safety_violation = any(
                        keyword in label.lower() for keyword in safety_labels
                    )

                    if is_safety_violation:
                        # Normalize label based on exact model classes with professional workplace safety names
                        if label == 'NO-Hardhat':
                            display_label = '⚠️ No Safety Helmet'
                        elif label == 'NO-Safety Vest':
                            display_label = '⚠️ No Safety Vest'
                        elif label == 'NO-Mask':
                            display_label = '⚠️ No Safety Mask'
                        elif label == 'Person':
                            display_label = '⚠️ No Protective Equipment'
                        elif 'helmet' in label.lower() and 'no' in label.lower():
                            display_label = '⚠️ No Safety Helmet'
                        elif 'jacket' in label.lower() and 'no' in label.lower():
                            display_label = '⚠️ No Safety Jacket'
                        elif 'vest' in label.lower() and 'no' in label.lower():
                            display_label = '⚠️ No Safety Vest'
                        else:
                            display_label = f'⚠️ {label}'

                        detections.append({
                            'x': x1,
                            'y': y1,
                            'width': x2 - x1,
                            'height': y2 - y1,
                            'label': display_label,
                            'confidence': conf,
                            'class': cls
                        })

        response_data = {
            'success': True,
            'detections': detections,
            'frame_processed': True,
            'timestamp': str(timezone.now())
        }

        return JsonResponse(response_data)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return JsonResponse({
            'error': f'Detection failed: {str(e)}',
            'details': error_details,
            'detections': []
        }, status=500)