# Deploy to Hugging Face Spaces

## Step 1: Create a Hugging Face Account
Go to https://huggingface.co/join and sign up (free).

## Step 2: Create a New Space
1. Go to https://huggingface.co/spaces
2. Click "Create new Space"
3. Name: `har-safety-detection`
4. SDK: Select "Docker"
5. Hardware: Select "CPU Basic" (free) or "ZeroGPU" (free GPU)
6. Click "Create Space"

## Step 3: Upload Your Code

### Option A: Via Git
```bash
git clone https://huggingface.co/spaces/YOUR_USERNAME/har-safety-detection
cd har-safety-detection
# Copy all your project files here
git add .
git commit -m "Initial deployment"
git push
```

### Option B: Via Web Upload
1. In your Space, click "Files" tab
2. Click "Upload Files"
3. Upload all project files

## Step 4: Required Files
Make sure these files are in your Space:
- `Dockerfile` (provided below)
- `requirements.txt` (full version with all ML libs)
- All Django project files
- `best.pt` and `yolov8n.pt` model files

## Step 5: Environment Variables
In your Space settings, add these secrets:
```
DEBUG=False
SECRET_KEY=your-secret-key-here
DISABLE_ML=0
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
SENDGRID_API_KEY=your-key
```

## Hardware Options

| Plan | Price | Specs | Good For |
|------|-------|-------|----------|
| CPU Basic | **Free** | 2 vCPU, 16GB RAM | Testing, small loads |
| ZeroGPU | **Free** | Shared NVIDIA A100 | YOLO inference, face recognition |
| CPU Upgrade | $0.03/hr | 4 vCPU, 32GB RAM | Production |
| GPU Small | $0.50/hr | NVIDIA T4 | Heavy inference |

## Note on ZeroGPU
ZeroGPU gives you **free GPU time** but with limits:
- Functions must use `@spaces.GPU` decorator
- Max 120 seconds per GPU call
- Great for inference, not for 24/7 GPU usage

For your use case (video upload → YOLO detection), ZeroGPU works perfectly.
