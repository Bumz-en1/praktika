from db.database import SessionLocal
from db.models import Person
import face_recognition
import numpy as np
import cv2
import os
import uuid
import shutil
from PIL import Image
from io import BytesIO
import base64

FRAMES_DIR = "video_frames"
UNIQUE_DIR = "unique_faces"
DUPLICATES_DIR = os.path.join(UNIQUE_DIR, "duplicates")
CROPPED_DIR = "temp_cropped_faces"

def recognize(image_path, tolerance=0.6):
    session = SessionLocal()
    image = face_recognition.load_image_file(image_path)

    unknown_encodings = face_recognition.face_encodings(image)
    if not unknown_encodings:
        return []

    results = []
    all_persons = session.query(Person).all()
    known_encodings = [np.array(p.face_encoding) for p in all_persons]
    known_names = [p.name for p in all_persons]

    for unknown_encoding in unknown_encodings:
        distances = face_recognition.face_distance(known_encodings, unknown_encoding)
        min_index = np.argmin(distances)
        if distances[min_index] < tolerance:
            results.append({
                "name": known_names[min_index],
                "distance": float(distances[min_index]),
                "confidence": float(1 - distances[min_index])
            })
        else:
            results.append({"name": "Неизвестно", "confidence": None})
    
    return results

def prepare_dirs():
    for path in [FRAMES_DIR, UNIQUE_DIR, DUPLICATES_DIR, CROPPED_DIR]:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)

def extract_frames(video_path, interval=3):
    video_capture = cv2.VideoCapture(video_path)
    if not video_capture.isOpened():
        print("[ОШИБКА] Видео не удалось открыть:", video_path)
        return

    frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[INFO] Размер видео: {frame_width}x{frame_height}, Кадров: {total_frames}")

    count = 0
    saved = 0

    while True:
        success, frame = video_capture.read()
        if not success:
            print(f"[INFO] Видео завершено на кадре {count}")
            break

        if frame is None:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] Кадр {count} пуст")
            continue

        if count % interval == 0:
            frame_path = os.path.join(FRAMES_DIR, f"frame_{saved:04d}.jpg")
            success_write = cv2.imwrite(frame_path, frame)
            if success_write:
                print(f"[OK] Сохранён кадр: {frame_path}")
                saved += 1
            else:
                print(f"[ОШИБКА] Не удалось сохранить кадр: {frame_path}")

        count += 1

    video_capture.release()
    print(f"[ИТОГО] Сохранено кадров: {saved}")

def variance_of_laplacian(image):
    return cv2.Laplacian(image, cv2.CV_64F).var()

def encode_image_base64(image_array):
    pil_image = Image.fromarray(image_array)
    buffer = BytesIO()
    pil_image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()

def debug_recognize(image_path, tolerance=0.6):
    image = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(image, model="hog")

    print(f"[DEBUG] Найдено лиц: {len(face_locations)} в {image_path}")

    results = []
    for location in face_locations:
        top, right, bottom, left = location
        face_image = image[top:bottom, left:right]
        encoding = face_recognition.face_encodings(image, known_face_locations=[location])[0]

        gray = cv2.cvtColor(face_image, cv2.COLOR_RGB2GRAY)
        sharpness = variance_of_laplacian(gray)
        area = (right - left) * (bottom - top)

        face_id = uuid.uuid4().hex
        temp_face_path = os.path.join(CROPPED_DIR, f"face_{face_id}.jpg")
        Image.fromarray(face_image).save(temp_face_path)

        image_base64 = encode_image_base64(face_image)

        results.append({
            "name": "Неизвестно",
            "encoding": encoding.tolist(),
            "temp_path": f"/{CROPPED_DIR}/{os.path.basename(temp_face_path)}",
            "quality": sharpness,
            "area": area,
            "file_path": temp_face_path,
            "image": image_base64
        })

    return results

def recognize_faces_in_video(video_path, frame_interval=10, tolerance=0.6):
    prepare_dirs()
    extract_frames(video_path, frame_interval)

    unique_faces = []

    # получить fps
    video_capture = cv2.VideoCapture(video_path)
    fps = video_capture.get(cv2.CAP_PROP_FPS)
    video_capture.release()

    for filename in sorted(os.listdir(FRAMES_DIR)):
        frame_path = os.path.join(FRAMES_DIR, filename)
        frame_number = int(filename.split("_")[1].split(".")[0])  # из frame_0001.jpg
        timestamp = frame_number / fps if fps else 0

        matches = debug_recognize(frame_path, tolerance=tolerance)

        for match in matches:
            match["frame"] = frame_number
            match["timestamp"] = timestamp

            encoding = np.array(match["encoding"])
            is_duplicate = False
            best_index = None

            for i, known in enumerate(unique_faces):
                dist = np.linalg.norm(np.array(known["encoding"]) - encoding)
                if dist < 0.5:
                    is_duplicate = True
                    best_index = i
                    break

            if not is_duplicate:
                unique_faces.append(match)
            else:
                existing = unique_faces[best_index]
                score_existing = existing["area"] * 0.6 + existing["quality"] * 0.4
                score_new = match["area"] * 0.6 + match["quality"] * 0.4
                if score_new > score_existing:
                    try:
                        os.remove(existing["file_path"])
                    except:
                        pass
                    unique_faces[best_index] = match
                else:
                    duplicate_path = os.path.join(DUPLICATES_DIR, os.path.basename(match["file_path"]))
                    shutil.copyfile(match["file_path"], duplicate_path)

    print(f"[INFO] Уникальных лиц найдено: {len(unique_faces)}")
    return unique_faces
