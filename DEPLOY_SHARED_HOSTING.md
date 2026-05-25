# Deploying to Shared Hosting (Lightweight Version)

This guide explains how to deploy the HAR Safety Detection project on **shared hosting** (e.g., InterServer, HostGator, Bluehost) where heavy ML libraries cannot be installed.

---

## ⚠️ What Gets Disabled in Lightweight Mode

| Feature | Status | Reason |
|---------|--------|--------|
| **YOLO Safety Detection** | ❌ Disabled | Requires `torch` + `ultralytics` (~2GB) |
| **Face Recognition** | ❌ Disabled | Requires `dlib` + `face_recognition` (~500MB) |
| **Live Webcam Detection** | ❌ Disabled | Requires YOLO + OpenCV |
| **Video Processing (AVI→MP4)** | ⚠️ Fallback | Copies file as-is if `moviepy` missing |
| **Activity Recognition** | ⚠️ Demo mode | Returns random activity if OpenCV missing |
| **Admin Dashboard** | ✅ Works | All Django admin features |
| **Employee CRUD** | ✅ Works | Add/edit/delete employees |
| **Violation Logging** | ✅ Works | Manual entry + viewing |
| **Email/SMS** | ✅ Works | SendGrid / SMTP |
| **OTP Login** | ✅ Works | Phone-based employee login |

---

## 📦 Requirements (Lightweight)

Use `requirements_light.txt` instead of `requirements.txt`:

```bash
pip install -r requirements_light.txt
```

**Total size: ~50MB** (vs ~3-4GB with heavy libs)

---

## 🚀 Deployment Steps

### 1. Upload Files
Upload these to your shared hosting (via FTP/cPanel File Manager):
- All Python files (`users/`, `har_project/`, `templates/`, `static/`)
- `manage.py`
- `requirements_light.txt`
- `db.sqlite3` (or use MySQL if provided by host)
- `.env` file (see below — **must include `DISABLE_ML=1`**)
- **SKIP**: `best.pt`, `yolov8n.pt` (not needed in lightweight mode)

### 2. Set Up Python (if host supports it)
Some hosts provide Python via cPanel or SSH:
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install lightweight deps
pip install -r requirements_light.txt
```

### 3. Configure Database
In `har_project/settings.py`, use SQLite (default) or MySQL:
```python
# SQLite (simplest for shared hosting)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

### 4. Collect Static Files
```bash
python manage.py collectstatic
```

### 5. Run Migrations
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Configure WSGI
Most shared hosts use Apache + mod_wsgi or Passenger. Point to `har_project/wsgi.py`.

---

## 🔧 cPanel Specific (InterServer, etc.)

1. **Setup Python App** in cPanel → Select Python 3.10+
2. **Application root**: `/public_html/har_project` (or your path)
3. **Application URL**: your domain
4. **WSGI file**: `har_project/wsgi.py`
5. **Install requirements** via cPanel terminal:
   ```bash
   pip install -r requirements_light.txt
   ```

---

## 🔄 Two-Mode Setup (Advanced)

You can keep **both** versions working:

```bash
# Full version (local/VPS)
pip install -r requirements.txt

# Lightweight version (shared hosting)
pip install -r requirements_light.txt
```

The code automatically detects which libraries are available and disables heavy features gracefully.

---

## 📝 Environment Variables

Create a `.env` file in the project root:

```env
DEBUG=False
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# CRITICAL: Disable heavy ML libraries on shared hosting
DISABLE_ML=1

# Email (G SMTP)
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# SendGrid (optional)
SENDGRID_API_KEY=your-sendgrid-key
```

---

## ✅ Verify It's Working

After deployment, visit these URLs:
- `/` → Home page
- `/login/` → Login page
- `/admin/` → Django admin (after creating superuser)

You should see a warning banner if running in lightweight mode.

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ultralytics not available` spam in logs | Make sure `DISABLE_ML=1` is set in `.env` |
| `ModuleNotFoundError: No module named 'cv2'` | Expected in lightweight mode — app still works |
| `YOLO model not available` | Normal — safety detection disabled |
| `Face recognition not installed` | Normal — manual employee assignment still works |
| `500 Internal Server Error` | Check `DEBUG=True` temporarily to see details |
| `Permission denied` | Set folder permissions to 755, files to 644 |

---

## 💡 Recommendation

For **full AI features** (YOLO detection + face recognition), use:
- **VPS** (DigitalOcean, Linode, AWS Lightsail) — $5-10/month
- **PythonAnywhere** (has some ML libs pre-installed)
- **Render.com** or **Railway.app** (free tier available)

For **management dashboard only** on shared hosting, this lightweight version works perfectly.
