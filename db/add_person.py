from db.database import SessionLocal
from db.models import Person
import face_recognition
import numpy as np

def add_person(name, image_path):
    session = SessionLocal()
    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)

    if encodings:
        person = Person(
            name=name,
            photo_path=image_path,
            face_encoding=encodings[0].tolist()
        )
        session.add(person)
        session.commit()
        print(f"Лицо человека по имени: '{name}' добавлено.")
    else:
        print("Лицо не найдено.")
