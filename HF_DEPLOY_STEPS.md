# Exact Steps to Deploy on Hugging Face Spaces

## Step 1: Create the Space on Hugging Face Website

1. Go to https://huggingface.co/spaces
2. Click the **"Create new Space"** button (top right)
3. Fill in the form:
   - **Owner**: Haegl001 (your username)
   - **Space name**: `har-safety-detection`
   - **License**: apache-2.0 (or whatever you prefer)
   - **Space SDK**: Select **"Docker"** from dropdown
   - **Space hardware**: Select **"CPU Basic"** (free) or **"ZeroGPU"** (free GPU)
   - **Make it public**: ✅ (required for free tier)
4. Click **"Create Space"**

## Step 2: Get Your Token

1. Go to https://huggingface.co/settings/tokens
2. Click **"New token"**
3. Name: `deploy`
4. Role: **Write**
5. Click **"Generate token"**
6. **Copy the token** (starts with `hf_...`)

## Step 3: Login via CLI

```bash
pip install huggingface_hub
huggingface-cli login
# Paste your token when asked
```

## Step 4: Clone the Empty Space

```bash
cd C:\Users\haegl\Desktop\hosting
huggingface-cli repo clone spaces/Haegl001/har-safety-detection
```

Or use Git with token:
```bash
git clone https://Haegl001:YOUR_TOKEN@huggingface.co/spaces/Haegl001/har-safety-detection
```

## Step 5: Copy Your Project Files

```bash
cd har-safety-detection

# Copy all project files (except .git, __pycache__, etc.)
cp -r ../har_project/* .

# Or manually copy these files:
# - manage.py
# - requirements_full.txt (rename to requirements.txt)
# - Dockerfile
# - har_project/ folder
# - users/ folder
# - templates/ folder
# - static/ folder
# - best.pt
# - yolov8n.pt
# - db.sqlite3 (optional - for initial data)
```

## Step 6: Rename Requirements

```bash
mv requirements_full.txt requirements.txt
```

## Step 7: Commit and Push

```bash
git add .
git commit -m "Initial deployment"
git push
```

## Step 8: Wait for Build

- Go to https://huggingface.co/spaces/Haegl001/har-safety-detection
- Click **"Files"** tab → **"Console"** to see build logs
- Build takes 5-10 minutes (installing torch, ultralytics, etc.)

## Step 9: Add Secrets

1. Go to your Space → **"Settings"** tab → **"Secrets"**
2. Add these:

```
SECRET_KEY=your-django-secret-key-change-this
DEBUG=False
DISABLE_ML=0
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
SENDGRID_API_KEY=your-key-if-you-have
```

## Step 10: Run Migrations

1. In your Space, go to **"Console"** tab
2. Run:
```bash
python manage.py migrate
python manage.py createsuperuser
```

## Your App URL

Once deployed, your app will be at:
```
https://huggingface.co/spaces/Haegl001/har-safety-detection
```

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| `Repository not found` | Create the Space on website first (Step 1) |
| `403 Forbidden` | Check your token has "Write" permission |
| `Build failed` | Check Console logs for missing dependencies |
| `Module not found` | Make sure `requirements.txt` has all packages |
| `best.pt not found` | Upload model file to repo or add download in Dockerfile |

---

## Alternative: Upload via Web Interface (No Git)

If Git doesn't work, you can upload files directly:

1. Go to https://huggingface.co/spaces/Haegl001/har-safety-detection
2. Click **"Files"** tab
3. Click **"Upload Files"** button
4. Drag and drop all your project files
5. Click **"Commit"**

The Space will rebuild automatically.
