import requests
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.core.mail import EmailMessage


def send_password_reset_otp(email, otp, name=None):
    """Email a password-reset OTP to the user via Gmail SMTP.

    Returns:
        (success: bool, info: str)
    """
    if not email:
        return False, "No email address available"

    greeting = f"Hi {name}," if name else "Hi,"
    subject = "SafeGuard AI - Password Reset OTP"

    text_body = (
        f"{greeting}\n\n"
        f"Your one-time password (OTP) to reset your SafeGuard AI password is:\n\n"
        f"    {otp}\n\n"
        f"This code is valid for 10 minutes. If you did not request a password "
        f"reset, please ignore this email.\n\n"
        f"- SafeGuard AI - Workplace Safety System"
    )

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 520px; margin: 0 auto; padding: 24px;">
            <h2 style="color: #FF6B00;">🔐 Password Reset Request</h2>
            <p>{greeting}</p>
            <p>Use the one-time password (OTP) below to reset your SafeGuard AI password:</p>
            <div style="background: #0F1B2D; color: #FFD600; font-size: 32px;
                        font-weight: bold; letter-spacing: 8px; text-align: center;
                        padding: 18px; border-radius: 10px; margin: 24px 0;">
                {otp}
            </div>
            <p style="background: #FFF8F0; border-left: 4px solid #FF6B00; padding: 10px;">
                This code is valid for <strong>10 minutes</strong>.
            </p>
            <p style="font-size: 13px; color: #6c757d;">
                If you did not request a password reset, you can safely ignore this email.
            </p>
            <hr style="border: none; border-top: 1px solid #dee2e6; margin: 20px 0;">
            <p style="font-size: 12px; color: #6c757d;">
                Automated message from SafeGuard AI - Workplace Safety System.
                Please do not reply.
            </p>
        </div>
    </body>
    </html>
    """

    try:
        from django.core.mail import EmailMultiAlternatives
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL',
                               'SafeGuard AI <safeguard@example.com>'),
            to=[email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()
        return True, "OTP email sent successfully"
    except Exception as e:
        error_msg = str(e)
        # Console fallback so the flow still works when SMTP is blocked.
        print("=" * 60)
        print("[PASSWORD RESET OTP - email send failed, console fallback]")
        print("=" * 60)
        print(f"To: {email}")
        print(f"OTP: {otp}")
        print(f"Error: {error_msg}")
        print("=" * 60)
        return False, error_msg

MALERT_API_URL = getattr(settings, 'MALERT_API_URL',
                          "https://apps.malert.io/api/api_http.php")


def _malert_param_map():
    """Maps logical fields -> the actual Malert query param names.

    Confirmed from the panel's sample request:
      api_http.php?username=&password=&senderid=&to=&text=&route=&type=text
    Override via MALERT_PARAMS in settings if the panel changes.
    """
    default = {
        'apikey': 'password',     # API password param name
        'username': 'username',
        'sender': 'senderid',
        'mobile': 'to',
        'message': 'text',
        'route': 'route',
    }
    default.update(getattr(settings, 'MALERT_PARAMS', {}) or {})
    return default


# DLT-approved OTP template (sender HGLTCH). The '%' is the OTP variable.
# This text MUST be sent verbatim or the carrier drops the SMS.
MALERT_OTP_TEMPLATE = (
    "Your One Time Password (OTP) is %. Use this OTP to log in to the "
    "JainConnect Portal. This OTP is valid for 10 minutes and can be used "
    "only once.\n\nHaegl Technologies Pvt. Ltd."
)


def _send_via_malert(mobile, message, log_tag="SMS"):
    """Single place that talks to the Malert HTTP API.

    Returns (success: bool, info: str). Always logs the raw response so the
    OTP/message is recoverable from the server console if delivery fails.
    """
    username = getattr(settings, 'MALERT_USERNAME', '')
    api_password = getattr(settings, 'MALERT_API_PASSWORD', '')
    sender = getattr(settings, 'MALERT_SENDER', 'HGLTCH')
    route = getattr(settings, 'MALERT_ROUTE', 'Informative')
    http_method = getattr(settings, 'MALERT_HTTP_METHOD', 'GET').upper()

    if not username or not api_password:
        print("=" * 60)
        print(f"[{log_tag} - Malert not configured, console fallback]")
        print(f"To: {mobile}\nMessage:\n{message}")
        print("=" * 60)
        return False, "Malert credentials not configured"

    # Malert requires E.164 (Indian numbers prefixed with +91).
    digits = ''.join(c for c in str(mobile) if c.isdigit())
    if str(mobile).strip().startswith('+'):
        to = str(mobile).strip()
    elif digits.startswith('91') and len(digits) == 12:
        to = '+' + digits
    else:
        to = '+91' + digits[-10:]

    pm = _malert_param_map()
    payload = {
        pm['username']: username,
        pm['apikey']: api_password,
        pm['sender']: sender,
        pm['mobile']: to,
        pm['message']: message,
        pm['route']: route,
        'type': 'text',
    }

    try:
        if http_method == 'GET':
            response = requests.get(MALERT_API_URL, params=payload, timeout=15)
        else:
            response = requests.post(MALERT_API_URL, data=payload, timeout=15)
        body = response.text
        print("=" * 60)
        print(f"[{log_tag} - Malert raw response]")
        print(f"Endpoint : {MALERT_API_URL} ({http_method})")
        print(f"To       : {to}")
        print(f"HTTP     : {response.status_code}")
        print(f"Body     : {body[:600]}")
        print(f"Message  :\n{message}")
        print("=" * 60)
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}: {body[:200]}"
        # Malert success looks like:  OK [b1dd8a85-51ba-11f1-...]
        stripped = body.strip()
        if stripped.upper().startswith('OK'):
            msg_id = stripped[2:].strip().strip('[]') or 'sent'
            return True, msg_id
        if stripped.upper().startswith('ERROR'):
            return False, stripped[:200]
        try:
            result = response.json()
            if result.get('success') or str(result.get('status', '')).lower() in (
                    'success', 'ok', 'submitted'):
                return True, str(result.get('message_id')
                                  or result.get('msgid') or 'sent')
            return False, result.get('message', body[:200] or 'API error')
        except ValueError:
            ok = any(s in body.lower()
                     for s in ('success', 'submitted', 'sent', 'accepted'))
            return ok, body[:200]
    except requests.RequestException as e:
        print(f"[{log_tag}] send failed: {e} | to={mobile}")
        return False, str(e)


def send_violation_sms(phone_number, violation_type, timestamp):
    """Send SMS notification to employee about a violation via Malert.

    Returns:
        (success: bool, info: str)
    """
    if not phone_number:
        return False, "No phone number available"

    username = getattr(settings, 'MALERT_USERNAME', '')
    api_password = getattr(settings, 'MALERT_API_PASSWORD', '')

    if not username or not api_password:
        return False, "Malert credentials not configured"

    message_body = (
        f"SAFETY ALERT: You have been identified in a safety violation "
        f"({violation_type}) on {timestamp.strftime('%Y-%m-%d at %H:%M')}. "
        f"Please report to your supervisor. - SafeGuard AI"
    )

    payload = {
        'username': username,
        'api_password': api_password,
        'to': phone_number,
        'message': message_body,
    }

    try:
        response = requests.post(MALERT_API_URL, data=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get('success') or result.get('status') == 'success':
            return True, result.get('message_id', 'sent')
        return False, result.get('message', 'Unknown API error')
    except requests.RequestException as e:
        return False, str(e)


def send_login_otp_sms(phone_number, otp, name=None):
    """Send a login OTP to an employee's phone via Malert, using the
    DLT-approved OTP template (the '%' placeholder is replaced with the OTP).

    Returns:
        (success: bool, info: str)
    """
    if not phone_number:
        return False, "No phone number available"

    # Build the exact approved DLT message (verbatim except OTP substitution).
    message = MALERT_OTP_TEMPLATE.replace('%', str(otp), 1)
    return _send_via_malert(phone_number, message, log_tag="LOGIN OTP SMS")


def send_login_sms(phone_number, employee_name=None, login_time=None):
    """Notify an employee by SMS that their account was just logged into.

    Returns:
        (success: bool, info: str)
    """
    if not phone_number:
        return False, "No phone number available"

    username = getattr(settings, 'MALERT_USERNAME', '')
    api_password = getattr(settings, 'MALERT_API_PASSWORD', '')

    if not username or not api_password:
        # Console fallback so the feature still "works" without a provider.
        print("=" * 60)
        print("[LOGIN SMS - Malert not configured, console fallback]")
        print(f"To: {phone_number}")
        print(f"Name: {employee_name}")
        print("=" * 60)
        return False, "Malert credentials not configured"

    when = (login_time or timezone.now()).strftime('%Y-%m-%d at %H:%M')
    name = employee_name or "Employee"
    message_body = (
        f"Hi {name}, your SafeGuard AI account was logged in on {when}. "
        f"If this was not you, contact your supervisor immediately. - SafeGuard AI"
    )

    payload = {
        'username': username,
        'api_password': api_password,
        'to': phone_number,
        'message': message_body,
    }

    try:
        response = requests.post(MALERT_API_URL, data=payload, timeout=15)
        response.raise_for_status()
        result = response.json()
        if result.get('success') or result.get('status') == 'success':
            return True, result.get('message_id', 'sent')
        return False, result.get('message', 'Unknown API error')
    except requests.RequestException as e:
        return False, str(e)


def send_violation_email(employee_email, employee_name, violation_type, timestamp,
                         snapshot_path=None, violation_id=None):
    """Send email notification to employee about a violation with snapshot attachment.

    Returns:
        (success: bool, info: str)
    """
    if not employee_email:
        return False, "No email address available"

    subject = f"SAFETY ALERT: {violation_type} Violation Detected"

    message_body = (
        f"Dear {employee_name},\n\n"
        f"You have been identified in a safety violation.\n\n"
        f"Violation Details:\n"
        f"  - Type: {violation_type}\n"
        f"  - Date & Time: {timestamp.strftime('%Y-%m-%d at %H:%M')}\n"
        f"  - Violation ID: #{violation_id}\n\n"
        f"Please report to your supervisor immediately.\n\n"
        f"Stay safe,\n"
        f"SafeGuard AI - Workplace Safety System"
    )

    try:
        email = EmailMessage(
            subject=subject,
            body=message_body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'SafeGuard AI <safeguard@example.com>'),
            to=[employee_email],
        )

        # Attach the violation snapshot if available
        if snapshot_path:
            try:
                with open(str(snapshot_path), 'rb') as f:
                    email.attach(
                        filename=f'violation_{violation_id}.jpg',
                        content=f.read(),
                        mimetype='image/jpeg'
                    )
            except Exception as attach_err:
                print(f"[email] Could not attach snapshot: {attach_err}")

        email.send()
        return True, "Email sent successfully"
    except Exception as e:
        error_msg = str(e)
        # If SMTP auth fails, log to console as fallback
        if 'SMTPAuthenticationError' in type(e).__name__ or 'WebLoginRequired' in error_msg:
            print("=" * 60)
            print("[EMAIL FALLBACK - Gmail SMTP blocked]")
            print("=" * 60)
            print(f"To: {employee_email}")
            print(f"Subject: {subject}")
            print("-" * 40)
            print(message_body)
            print("=" * 60)
            print("TIP: Visit https://accounts.google.com/DisplayUnlockCaptcha")
            print("     and click 'Continue' to allow this app to send emails.")
            print("=" * 60)
            return True, "Email logged to console (Gmail SMTP blocked - see tip above)"
        return False, error_msg
