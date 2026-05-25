import requests
import tempfile

try:
    import cv2
    CV2_AVAILABLE = True
except Exception:
    cv2 = None
    CV2_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    Image = None
    PIL_AVAILABLE = False


def extract_first_frame(video_path):
    if not CV2_AVAILABLE:
        raise RuntimeError("OpenCV not available in lightweight mode.")
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    if ret:
        return frame
    else:
        raise ValueError("Failed to read the video.")

def convert_to_rgb(frame):
    if not CV2_AVAILABLE:
        raise RuntimeError("OpenCV not available in lightweight mode.")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def save_frame_as_image(frame):
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow not available.")
    pil_image = Image.fromarray(frame)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
    pil_image.save(temp_file, 'JPEG')
    return temp_file.name

def send_scan_to_roboflow(video_path):
    """Send first frame of video to Roboflow API for classification.
    
    Returns (class_name, confidence) or ("Not classified", 0.0) on error.
    In lightweight mode (no OpenCV), returns a demo response.
    """
    API_URL = "https://detect.roboflow.com/human-activity-recognition-0lqsi/1"
    API_KEY = "Ax4LhZgUTmUL8cGMbYUU"

    if not CV2_AVAILABLE or not PIL_AVAILABLE:
        # Lightweight fallback — return demo data
        return "Not classified", 0.0

    try:
        frame = extract_first_frame(video_path)
        rgb_frame = convert_to_rgb(frame)
        image_path = save_frame_as_image(rgb_frame)
        
        try:
            with open(image_path, 'rb') as image_file:
                response = requests.post(
                    API_URL,
                    files={"file": image_file},
                    params={"api_key": API_KEY}
                )
                response.raise_for_status()
                result = response.json()
                predictions = result.get("predictions", [])
                if predictions:
                    return predictions[0].get("class"), predictions[0].get("confidence")
                return "Not classified", 0.0
        finally:
            import os
            try:
                os.unlink(image_path)
            except Exception:
                pass

    except requests.RequestException as e:
        return "Not classified", 0.0
    except Exception as e:
        return "Not classified", 0.0
