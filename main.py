import argparse
from db.database import SessionLocal
from db.models import Person, Base
import face_recognition
import numpy as np
import os
from sqlalchemy import create_engine
from db.database import host, password, port, user, db

def add_person(name: str, image_path: str):
    session = SessionLocal()

    if not os.path.exists(image_path):
        print("Файл не найден:", image_path)
        return

    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)

    if not encodings:
        print("Лицо не найдено на изображении.")
        return

    encoding = encodings[0]
    person = Person(name=name, photo_path=image_path, face_encoding=encoding.tolist())
    session.add(person)
    session.commit()
    print(f"Лицо человека по имени: '{name}' добавлено в базу.")


def recognize(image_path: str, tolerance: float = 0.6):
    session = SessionLocal()

    if not os.path.exists(image_path):
        print("Файл не найден:", image_path)
        return

    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)

    if not encodings:
        print("Лицо не найдено.")
        return

    unknown_encoding = encodings[0]
    persons = session.query(Person).all()

    if not persons:
        print("База данных пуста.")
        return

    known_encodings = [np.array(p.face_encoding) for p in persons]
    known_names = [p.name for p in persons]

    distances = face_recognition.face_distance(known_encodings, unknown_encoding)
    best_index = np.argmin(distances)
    best_distance = distances[best_index]

    if best_distance < tolerance:
        confidence = (1 - best_distance)*100
        print(f"Распознан: {known_names[best_index]} (уверенность: {confidence:.2f}%)")
    else:
        print("Лицо не распознано.")


def main():
    parser = argparse.ArgumentParser(description="Система распознавания лиц")
    subparsers = parser.add_subparsers(dest="command")

    # Добавление
    add_parser = subparsers.add_parser("add", help="Добавить нового человека")
    add_parser.add_argument("--name", required=True, help="Имя человека")
    add_parser.add_argument("--image", required=True, help="Путь к изображению")

    # Распознавание
    rec_parser = subparsers.add_parser("recognize", help="Распознать лицо на изображении")
    rec_parser.add_argument("--image", required=True, help="Путь к изображению")
    rec_parser.add_argument("--tolerance", type=float, default=0.6, help="Порог уверенности (по умолчанию: 0.6)")

    args = parser.parse_args()

    if args.command == "add":
        add_person(args.name, args.image)
    elif args.command == "recognize":
        recognize(args.image, args.tolerance)
    else:
        parser.print_help()


Base.metadata.create_all(create_engine(f"postgresql://{user}:{password}@{host}:{port}/{db}"))

if __name__ == "__main__":
    main()
