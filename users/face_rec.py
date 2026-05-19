"""Face encoding + identification utilities.

Each employee can have MULTIPLE face encodings (one per angle/expression).
Encodings are stored as a pickled list[np.ndarray] in User.face_encoding.
"""
import pickle
import threading
import numpy as np

try:
    import cv2
except Exception:
    cv2 = None

try:
    import face_recognition
    AVAILABLE = True
except Exception:
    AVAILABLE = False

DISTANCE_THRESHOLD = 0.7     # 0.6 = strict, 0.7 = lenient

_cache = None                # list[(user_pk, list_of_encodings)]
_cache_lock = threading.Lock()
_identify_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def encode_from_path(image_path):
    """Encode the first face found in an image file."""
    if not AVAILABLE:
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
    if not AVAILABLE or cv2 is None:
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
                # Take only the largest face if multiple
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
    return [np.asarray(data)]    # legacy single encoding


# Backward-compat single helpers (still used by old call sites)
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
    with _cache_lock:
        if _cache is None:
            _load_cache()
        cache_snapshot = list(_cache)
    if not cache_snapshot:
        print("[face_rec] cache empty - no employees with encodings")
        return None
    best_pk, best_dist = None, DISTANCE_THRESHOLD
    all_dists = []
    for pk, encs in cache_snapshot:
        emp_best = min(float(np.linalg.norm(e - target_enc)) for e in encs)
        all_dists.append((pk, emp_best, len(encs)))
        if emp_best < best_dist:
            best_pk, best_dist = pk, emp_best
    print(f"[face_rec] distances: {all_dists}  threshold={DISTANCE_THRESHOLD}")
    if best_pk is None:
        return None
    from .models import User
    try:
        u = User.objects.get(pk=best_pk)
        print(f"[face_rec] MATCHED: {u.username} ({u.employee_id}) dist={best_dist:.3f}")
        return u
    except User.DoesNotExist:
        return None


def identify(face_bgr):
    """Legacy: encode a tight face crop and match it."""
    if not AVAILABLE:
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
    """Detect faces in the full frame, pick best one, match against employees.

    NOTE: We convert the BGR frame to a PIL-compatible RGB array to avoid
    dlib segfaults on Windows with cv2-resized images.
    """
    if not AVAILABLE:
        print("[face_rec] face_recognition not installed")
        return None
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    if not _identify_lock.acquire(blocking=False):
        return None
    try:
        # Convert BGR -> RGB via numpy to ensure PIL/dlib compatibility
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        try:
            face_locs = face_recognition.face_locations(rgb, model='hog')
        except Exception as e:
            print(f"[face_rec] face_locations error: {e}")
            return None
        print(f"[face_rec] faces detected in frame: {len(face_locs)}")
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
        except Exception as e:
            print(f"[face_rec] face_encodings error: {e}")
            return None
        if not encs:
            return None
        return _match_encoding(encs[0])
    finally:
        _identify_lock.release()


def identify_in_image_path(image_path):
    """Open an image file, run face detection + match. Used for on-demand search."""
    if not AVAILABLE:
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
        except Exception as e:
            print(f"[face_rec] face_locations error: {e}")
            return None
        print(f"[face_rec] faces detected in image: {len(face_locs)}")
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
