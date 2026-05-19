import requests
import cv2
from PIL import Image
import tempfile

def extract_first_frame(video_path):
    cap = cv2.VideoCapture(video_path)
    ret, frame = cap.read()
    cap.release()
    if ret:
        return frame
    else:
        raise ValueError("Failed to read the video.")

def convert_to_rgb(frame):
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def save_frame_as_image(frame):
    pil_image = Image.fromarray(frame)
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
    pil_image.save(temp_file, 'JPEG')
    return temp_file.name

def send_scan_to_roboflow(video_path):
    API_URL = "https://detect.roboflow.com/human-activity-recognition-0lqsi/1"
    API_KEY = "Ax4LhZgUTmUL8cGMbYUU"

    
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
                # print(predictions[0].get("class"))
                return predictions[0].get("class"), predictions[0].get("confidence")
            # print("Roboflow Result:", result)
            return "Not classified", 0.0

    except requests.RequestException as e:
        return {"error": f"API request failed: {str(e)}"}
