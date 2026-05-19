#!/usr/bin/env python
"""
Setup script for Gmail SMTP configuration.

INSTRUCTIONS:
1. Edit the .env file in this directory
2. Replace:
   - your_email@gmail.com  →  your actual Gmail address
   - your_16_char_app_password  →  your Gmail App Password
3. Save the file
4. Run: python manage.py runserver

HOW TO GENERATE GMAIL APP PASSWORD:
1. Go to: https://myaccount.google.com/
2. Click 'Security' in the left sidebar
3. Under 'Signing in to Google', click '2-Step Verification'
4. At the bottom, click 'App passwords'
5. Select 'Mail' and 'Other (Custom name)'
6. Type: SafeGuard AI
7. Click 'Generate' and COPY the 16-character password

TROUBLESHOOTING:
- If you get "Please log in with your web browser":
  Visit https://accounts.google.com/DisplayUnlockCaptcha
  and click 'Continue' to allow the app access

- If App Password option is not visible:
  Make sure 2-Factor Authentication is ENABLED first
"""

import os

print(__doc__)

# Check if .env file exists and show current content
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    print("\nCurrent .env file content:")
    print("-" * 50)
    with open(env_path, 'r') as f:
        content = f.read()
        # Mask the password for security
        lines = content.split('\n')
        for line in lines:
            if 'PASSWORD' in line and '=' in line:
                key, val = line.split('=', 1)
                if val and not val.startswith('your_'):
                    masked = val[:4] + '*' * (len(val) - 4) if len(val) > 4 else '****'
                    print(f"{key}={masked}")
                else:
                    print(line)
            else:
                print(line)
    print("-" * 50)
    print("\nEdit this file with your actual credentials.")
else:
    print("\n.env file not found. Creating template...")
    with open(env_path, 'w') as f:
        f.write("""EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_16_char_app_password
DEFAULT_FROM_EMAIL=SafeGuard AI <your_email@gmail.com>
""")
    print("Template created at .env - please edit it with your credentials.")
