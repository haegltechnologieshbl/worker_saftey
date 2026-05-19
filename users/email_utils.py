"""Email notification utilities using SendGrid API.

To use SendGrid:
1. Sign up at https://sendgrid.com/ (free tier: 100 emails/day)
2. Get your API Key from Settings > API Keys
3. Set SENDGRID_API_KEY in your .env file or environment variables
"""

import base64
from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition


def send_violation_email_sendgrid(employee_email, employee_name, violation_type, timestamp,
                                   snapshot_path=None, violation_id=None):
    """Send email notification using SendGrid API.

    Returns:
        (success: bool, info: str)
    """
    if not employee_email:
        return False, "No email address available"

    api_key = getattr(settings, 'SENDGRID_API_KEY', '')
    if not api_key:
        return False, "SendGrid API key not configured"

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'SafeGuard AI <safeguard@example.com>')
    
    subject = f"SAFETY ALERT: {violation_type} Violation Detected"

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #dc3545;">🚨 Safety Violation Alert</h2>
            <p>Dear <strong>{employee_name}</strong>,</p>
            <p>You have been identified in a safety violation.</p>
            
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #dc3545;">Violation Details</h3>
                <table style="width: 100%;">
                    <tr>
                        <td style="padding: 5px 0;"><strong>Type:</strong></td>
                        <td style="padding: 5px 0;">{violation_type}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 0;"><strong>Date & Time:</strong></td>
                        <td style="padding: 5px 0;">{timestamp.strftime('%Y-%m-%d at %H:%M')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 5px 0;"><strong>Violation ID:</strong></td>
                        <td style="padding: 5px 0;">#{violation_id}</td>
                    </tr>
                </table>
            </div>
            
            <p style="background: #fff3cd; padding: 10px; border-left: 4px solid #ffc107;">
                <strong>Action Required:</strong> Please report to your supervisor immediately.
            </p>
            
            <hr style="border: none; border-top: 1px solid #dee2e6; margin: 20px 0;">
            <p style="font-size: 12px; color: #6c757d;">
                This is an automated notification from SafeGuard AI - Workplace Safety System.<br>
                Please do not reply to this email.
            </p>
        </div>
    </body>
    </html>
    """

    text_content = (
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
        message = Mail(
            from_email=from_email,
            to_emails=employee_email,
            subject=subject,
            html_content=html_content,
            plain_text_content=text_content
        )

        # Attach the violation snapshot if available
        if snapshot_path:
            try:
                with open(str(snapshot_path), 'rb') as f:
                    data = f.read()
                
                encoded = base64.b64encode(data).decode()
                attachment = Attachment(
                    FileContent(encoded),
                    FileName(f'violation_{violation_id}.jpg'),
                    FileType('image/jpeg'),
                    Disposition('attachment')
                )
                message.add_attachment(attachment)
            except Exception as attach_err:
                print(f"[email] Could not attach snapshot: {attach_err}")

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        if response.status_code in (200, 201, 202):
            return True, f"Email sent (status: {response.status_code})"
        else:
            return False, f"SendGrid error: {response.status_code} - {response.body}"
            
    except Exception as e:
        return False, str(e)
