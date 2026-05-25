# Dockerfile for Hugging Face Spaces / Render / Any Docker host
# This image supports PyTorch, Ultralytics, OpenCV, and Django

FROM python:3.10-slim

# Install system dependencies for OpenCV, dlib, and video processing
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    libgtk-3-dev \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create media directories
RUN mkdir -p media/employees media/violations media/violations/clean media/uploads media/outputs

# Collect static files
RUN python manage.py collectstatic --noinput

# Run migrations (optional - you may want to do this manually)
# RUN python manage.py migrate

# Expose port
EXPOSE 7860

# Start Django with gunicorn
CMD gunicorn har_project.wsgi:application --bind 0.0.0.0:7860 --workers 2 --threads 4 --timeout 120
