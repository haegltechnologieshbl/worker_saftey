"""Face encoding + identification utilities.

LIGHTWEIGHT VERSION for shared hosting — works WITHOUT dlib/face_recognition.
If the heavy libraries are available, they are used; otherwise graceful fallbacks.

Each employee can have MULTIPLE face encodings (one per angle/expression).
Encodings are stored as a pickled list[np.ndarray] in User.face_encoding.
"""
import pickle
import threading
import numpy as np

# ---------------------------------------------------------------------------
# Try to import heavy CV/ML libs — but DON'T fail if missing
# ---------------------------------------------------------------------------
try:
    import cv2
except Exception:
    cv2 = None

try:
    import face_recognition
    HEAVY_AVAILABLE = True
except Exception:
    face_recognition = None
    HEAVY_AVAILABLE = False

# ---------------------------------------------------------------------------
# Lightweight face detection fallback (Haar Cascades via Pillow / simple methods)
# ---------------------------------------------------------------------------
# For shared hosting we provide a *stub* face pipeline.  Real face matching
# requires dlib/face_recognition which are too heavy.  The app keeps working:
#   - Enrollment stores a placeholder encoding
#   - Identification returns None ("Unknown")
#   - Admin can still manually assign violations to employees
# ---------------------------------------------------------------------------

DISTANCE_THRESHOLD = 0.7
_cache = None
_cache_lock = threading.Lock()
_identify_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def encode_from_path(image_path):
    """Encode the first face found in an image file."""
    if not HEAVY_AVAILABLE:
        return None
    try:
        img = face_recognition.load_image_file(image_path)
        encs = face_recognition.face_encodings(img)
        return encs[0] if encs else None
    except Exception:
        return None


def encode_video_frames(video_path, num_samples=12):
    """Open a video, sample N evenly-spaced frames, return all face encodings.

    Used during employee enrollment to capture multiple angles.
    """
    if not HEAVY_AVAILABLE or cv2 is None:
        return []
    encodings = []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return encodings
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        if total < 2:
            num_samples = 1
        sample_indexes = [
            int(i * (total - 1) / max(1, num_samples - 1))
            for i in range(num_samples)
        ]
        for idx in sample_indexes:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            frame = _resize_for_dlib(frame)
            rgb = frame[:, :, ::-1]
            try:
                locs = face_recognition.face_locations(rgb, model='hog')
                if not locs:
                    continue
                encs = face_recognition.face_encodings(rgb, locs)
                if encs:
                    encodings.append(encs[0])
            except Exception:
                continue
    finally:
        cap.release()
    return encodings


def encodings_to_blob(encodings):
    """Pickle a list of encodings (numpy arrays) into bytes for DB storage."""
    if not encodings:
        return None
    return pickle.dumps([np.asarray(e) for e in encodings])


def encodings_from_blob(blob):
    """Unpickle stored data; returns list. Handles legacy single-encoding format."""
    if not blob:
        return []
    try:
        data = pickle.loads(blob)
    except Exception:
        return []
    if isinstance(data, list):
        return [np.asarray(x) for x in data]
    return [np.asarray(data)]


# Backward-compat single helpers
def to_blob(encoding):
    if encoding is None:
        return None
    return encodings_to_blob([encoding])


def from_blob(blob):
    encs = encodings_from_blob(blob)
    return encs[0] if encs else None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def invalidate_cache():
    global _cache
    with _cache_lock:
        _cache = None


def _load_cache():
    global _cache
    from .models import User
    employees = (User.objects
                 .filter(role='employee', is_superuser=False, is_staff=False)
                 .exclude(face_encoding__isnull=True))
    cache = []
    for emp in employees:
        encs = encodings_from_blob(emp.face_encoding)
        if encs:
            cache.append((emp.pk, encs))
    _cache = cache


def cache_size():
    with _cache_lock:
        if _cache is None:
            _load_cache()
        return len(_cache)


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _match_encoding(target_enc):
    """Match against any encoding of any employee (uses min distance)."""
    if not HEAVY_AVAILABLE:
        return None
    with _cache_lock:
        if _cache is None:
            _load_cache()
        cache_snapshot = list(_cache)
    if not cache_snapshot:
        return None
    best_pk, best_dist = None, DISTANCE_THRESHOLD
    all_dists = []
    for pk, encs in cache_snapshot:
        emp_best = min(float(np.linalg.norm(e - target_enc)) for e in encs)
        all_dists.append((pk, emp_best, len(encs)))
        if emp_best < best_dist:
            best_pk, best_dist = pk, emp_best
    if best_pk is None:
        return None
    from .models import User
    try:
        return User.objects.get(pk=best_pk)
    except User.DoesNotExist:
        return None


def identify(face_bgr):
    """Legacy: encode a tight face crop and match it."""
    if not HEAVY_AVAILABLE:
        return None
    if not _identify_lock.acquire(blocking=False):
        return None
    try:
        if face_bgr is None or face_bgr.size == 0:
            return None
        rgb = face_bgr[:, :, ::-1]
        try:
            encs = face_recognition.face_encodings(rgb)
        except Exception:
            return None
        if not encs:
            return None
        return _match_encoding(encs[0])
    finally:
        _identify_lock.release()


def _resize_for_dlib(bgr, max_dim=720):
    """Shrink image if very large — dlib can crash on huge frames on Windows."""
    if cv2 is None or bgr is None:
        return bgr
    h, w = bgr.shape[:2]
    biggest = max(h, w)
    if biggest <= max_dim:
        return bgr
    scale = max_dim / biggest
    return cv2.resize(bgr, (int(w * scale), int(h * scale)))


def identify_in_frame(frame_bgr, bbox=None):
    """Detect faces in the full frame, pick best one, match against employees."""
    if not HEAVY_AVAILABLE:
        return None
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    if not _identify_lock.acquire(blocking=False):
        return None
    try:
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        try:
            face_locs = face_recognition.face_locations(rgb, model='hog')
        except Exception:
            return None
        if not face_locs:
            return None

        if bbox is not None:
            x1, y1, x2, y2 = bbox
            bbox_cx = (x1 + x2) / 2.0
            chosen = None
            best_score = float('inf')
            for (top, right, bottom, left) in face_locs:
                fcx = (left + right) / 2.0
                fcy = (top + bottom) / 2.0
                if fcy > y2:
                    continue
                score = abs(fcx - bbox_cx) + max(0, fcy - y2) * 0.5
                if score < best_score:
                    best_score = score
                    chosen = (top, right, bottom, left)
            if chosen is None:
                chosen = face_locs[0]
            face_locs = [chosen]

        try:
            encs = face_recognition.face_encodings(rgb, face_locs)
        except Exception:
            return None
        if not encs:
            return None
        return _match_encoding(encs[0])
    finally:
        _identify_lock.release()


def identify_in_image_path(image_path):
    """Open an image file, run face detection + match. Used for on-demand search."""
    if not HEAVY_AVAILABLE:
        return None
    try:
        img = face_recognition.load_image_file(str(image_path))
    except Exception:
        return None
    if img is None or img.size == 0:
        return None
    if not _identify_lock.acquire(blocking=False):
        return None
    try:
        try:
            face_locs = face_recognition.face_locations(img, model='hog')
        except Exception:
            return None
        if not face_locs:
            return None
        try:
            encs = face_recognition.face_encodings(img, face_locs)
        except Exception:
            return None
        if not encs:
            return None
        return _match_encoding(encs[0])
    finally:
        _identify_lock.release()


# ---------------------------------------------------------------------------
# Lightweight availability flag (renamed for backward compat)
# ---------------------------------------------------------------------------
AVAILABLE = HEAVY_AVAILABLE
