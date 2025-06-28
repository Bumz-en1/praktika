from auth import create_access_token, verify_password, get_password_hash, SECRET_KEY, ALGORITHM, get_current_user, get_db
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Response
from fastapi.responses import JSONResponse, FileResponse
from recognizer.recognizer import recognize_faces_in_video, recognize
from starlette.middleware.sessions import SessionMiddleware
from passlib.hash import bcrypt
from db.database import SessionLocal
from db.models import Person, User
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from starlette.status import HTTP_303_SEE_OTHER
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware import Middleware
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from datetime import datetime
from fastapi import Request
from fastapi import Form
from fastapi import Cookie
from fastapi import status
from jose import JWTError, jwt
from datetime import datetime, timedelta
from tg.main import telegram_app
from threading import Thread
import face_recognition
import numpy as np
import mimetypes
import asyncio
import secrets
import random
import shutil
import uuid
import jwt
import os

load_dotenv()

#временный параметр
import logging
logging.basicConfig(
    level=logging.INFO,  # уровень логирования
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

twofa_codes = {}
recognition_temp = {}
MAIN_URL = os.getenv("MAIN_URL")

class AuthRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Разрешённые публичные пути
        public_paths = [
            "/login", "/register", "/static", "/favicon.ico",
            "/token", "/tg_recognize", "/verify_2fa", "/request_2fa_code"
        ]
        # Разрешаем доступ к публичным путям
        if any(request.url.path.startswith(path) for path in public_paths):
            return await call_next(request)

        # Проверка авторизации по cookie
        token = request.cookies.get("access_token")
        if token:
            try:
                scheme, jwt_token = token.split()
                payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
                user_id = payload.get("sub")
                db = SessionLocal()
                user = db.query(User).filter(User.id == user_id).first()
                db.close()
                if user:
                    return await call_next(request)
            except (JWTError, ValueError):
                pass

        # Неавторизованный — редирект на /login
        return RedirectResponse("/login")

middleware = [
    Middleware(SessionMiddleware, secret_key=os.getenv("SECRET_STROKE")),
    Middleware(AuthRedirectMiddleware),
]

app = FastAPI(middleware=middleware)
UPLOAD_DIR = "known_faces"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs("user_photos", exist_ok=True)

templates = Jinja2Templates(directory="templates") 

def save_upload_file(upload_file: UploadFile, destination: str):
    with open(destination, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user_role": current_user.role,
        "current_user": current_user
    })

@app.post("/token")
async def login_for_jwt(email: str = Form(...), password: str = Form(...), db=Depends(get_db)):
    user = db.query(User).filter_by(email=email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Неверный email или пароль")
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users", response_class=HTMLResponse)
async def view_users(request: Request, current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    session = SessionLocal()
    users = session.query(User).all()

    for user in users:
        if isinstance(user.created_at, datetime):
            user.created_at_str = user.created_at.strftime('%d.%m.%Y')
        else:
            user.created_at_str = user.created_at

    session.close()

    query_params = dict(request.query_params)
    success = request.query_params.get("success")
    error = request.query_params.get("error")

    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "current_user": current_user,
        "user_role": current_user.role,
        "query": {"success": success, "error": error}
    })

@app.post("/admin/change-password/{user_id}")
async def admin_change_password(
    user_id: int,
    request: Request,
    new_password: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            # Передать ошибку в query при редиректе
            return RedirectResponse("/users?error=Пользователь не найден", status_code=302)

        user.hashed_password = get_password_hash(new_password)
        session.commit()

    return RedirectResponse("/users?success=edit", status_code=302)


@app.post("/admin/delete-user/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return RedirectResponse("/users?error=Пользователь не найден", status_code=302)

        session.delete(user)
        session.commit()

    return RedirectResponse("/users?success=delete", status_code=302)

@app.post("/add/confirm")
async def confirm_person(name: str = Form(...), photo_filename: str = Form(...)):
    print(f"[+] Добавлен человек: {name}, файл: {photo_filename}")
    return RedirectResponse("/", status_code=303)

@app.get("/add", response_class=HTMLResponse)
async def add_person_form(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("add_person.html", {
        "request": request,
        "user_role": current_user.role
    })

@app.get("/database", response_class=HTMLResponse)
async def database_view(request: Request, current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        return RedirectResponse("/", status_code=303)

    db = SessionLocal()
    persons = db.query(Person).all()
    db.close()

    return templates.TemplateResponse("database.html", {
        "request": request,
        "user": current_user,
        "persons": persons
    })

@app.post("/add", response_class=HTMLResponse)
async def add_person(
    request: Request,
    name: str = Form(...),
    gender: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        path = os.path.join(UPLOAD_DIR, filename)
        save_upload_file(file, path)

        image = face_recognition.load_image_file(path)
        encodings = face_recognition.face_encodings(image)

        if not encodings:
            os.remove(path)
            return templates.TemplateResponse("add_person.html", {
                "request": request,
                "error": "Лицо не найдено на изображении. Попробуйте другое фото."
            })

        encoding = encodings[0].tolist()

        session = SessionLocal()
        person = Person(name=name, gender=gender, photo_path=path, face_encoding=encoding)
        session.add(person)
        session.commit()
        session.close()

        return RedirectResponse("/", status_code=303)

    except Exception as e:
        return templates.TemplateResponse("add_person.html", {
            "request": request,
            "error": f"Ошибка при добавлении: {str(e)}"
        })

@app.post("/recognize", response_class=HTMLResponse)
async def recognize_route(
    request: Request,
    user_id: int = Form(...),
    media: UploadFile = File(...),
    gender: str = Form("не указано"),
    tolerance: float = 0.6,
    current_user: User = Depends(get_current_user),
):
    import uuid
    import os
    import shutil
    import mimetypes
    import numpy as np
    from fastapi import HTTPException
    from db.database import SessionLocal
    from db.models import User, Person
    from recognizer.recognizer import recognize, recognize_faces_in_video

    filename = f"{uuid.uuid4().hex}_{media.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(media.file, buffer)

    mimetype = mimetypes.guess_type(filepath)[0]
    if mimetype is None:
        os.remove(filepath)
        raise HTTPException(status_code=400, detail="Невозможно определить тип файла.")

    session = SessionLocal()
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        session.close()
        os.remove(filepath)
        raise HTTPException(status_code=404, detail="Пользователь не найден.")
    user.face_searches += 1
    session.commit()

    # === ВИДЕО ===
    if mimetype.startswith("video"):
        unique_faces = recognize_faces_in_video(filepath, tolerance=tolerance)

        all_persons = session.query(Person).all()
        if gender != "не указано":
            all_persons = [p for p in all_persons if p.gender == gender or p.gender == "не указано"]

        matched_candidates = []
        for person in all_persons:
            known_enc = np.array(person.face_encoding)
            for face in unique_faces:
                unknown_enc = np.array(face["encoding"])
                dist = np.linalg.norm(known_enc - unknown_enc)
                similarity = round((1 - dist) * 100, 2)
                if similarity >= 40:
                    matched_candidates.append({
                        "id": person.id,
                        "name": person.name,
                        "photo_url": f"/known_faces/{os.path.basename(person.photo_path)}",
                        "gender": person.gender,
                        "similarity": similarity
                    })
                    break  # один раз — одно совпадение

        session.close()

        return templates.TemplateResponse("recognition_result_video.html", {
            "request": request,
            "input_video": f"/known_faces/{filename}",
            "unique_faces": unique_faces,
            "matched_candidates": matched_candidates,
            "current_user": current_user
        })

    # === ИЗОБРАЖЕНИЕ ===
    elif mimetype.startswith("image"):
        results = recognize(filepath, tolerance=tolerance)

        all_persons = session.query(Person).all()
        if gender != "не указано":
            filtered_persons = [p for p in all_persons if p.gender == gender or p.gender == "не указано"]
        else:
            filtered_persons = all_persons

        candidates = []
        for result in results:
            if result["name"] == "Неизвестно":
                continue
            person = next((p for p in filtered_persons if p.name == result["name"]), None)
            if person:
                candidates.append({
                    "id": person.id,
                    "name": person.name,
                    "photo_url": f"/known_faces/{os.path.basename(person.photo_path)}",
                    "gender": person.gender,
                    "similarity": round(result["confidence"] * 100, 2)
                })

        session.close()

        return templates.TemplateResponse("recognition_result.html", {
            "request": request,
            "candidates": candidates,
            "input_photo": f"/known_faces/{filename}",
            "gender_filter": gender,
            "current_user": current_user
        })

    else:
        session.close()
        os.remove(filepath)
        raise HTTPException(status_code=400, detail="Поддерживаются только изображения и видео.")


@app.post("/admin/edit-user/{user_id}")
async def admin_edit_user(
    user_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    new_password: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        user.first_name = first_name
        user.last_name = last_name
        user.email = email
        user.role = role

        if new_password:
            user.hashed_password = get_password_hash(new_password)

        if photo and photo.filename:
            filename = f"{uuid.uuid4().hex}_{photo.filename}"
            file_path = os.path.join("user_photos", filename)
            with open(file_path, "wb") as f:
                f.write(await photo.read())
            user.profile_photo = f"/user_photos/{filename}"

        session.commit()

    return RedirectResponse("/users", status_code=302)


@app.post("/recognize_decision")
async def recognize_decision(
    user_id: int = Form(...),
    input_path: str = Form(...),
    matched_id: int = Form(...),
    decision: str = Form(...)
):
    session: Session = SessionLocal()
    logger.info(f"recognize_decision called with user_id={user_id}, input_path={input_path}, matched_id={matched_id}, decision={decision}")

    user = session.query(User).filter(User.id == user_id).first()
    person = session.query(Person).filter(Person.id == matched_id).first()
    real_input_path = os.path.join(UPLOAD_DIR, os.path.basename(input_path))
    logger.info("пиписька 1")
    logger.info(f"user found: {user is not None}")
    logger.info(f"person found: {person is not None}")
    logger.info(f"input_path exists: {os.path.exists(real_input_path)}")
    logger.info(f"person.photo_path exists: {os.path.exists(person.photo_path)}")
    if not user or not person or not os.path.exists(real_input_path) or not os.path.exists(person.photo_path):
        session.close()
        return RedirectResponse("/", status_code=303)

    if decision == "yes":
        user.confirmed_matches += 1
    else:
        user.rejected_matches += 1
    logger.info("пиписька 5")
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info(f"User {user.id} stats after commit: confirmed_matches={user.confirmed_matches}, rejected_matches={user.rejected_matches}")
    session.close()

    if os.path.exists(input_path):
        os.remove(input_path)

    return RedirectResponse("/", status_code=303)



@app.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register", response_class=HTMLResponse)
async def register_user(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    photo: UploadFile = File(None)
):
    session = SessionLocal()

    if session.query(User).filter(User.email == email).first():
        session.close()
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Пользователь с таким email уже существует."
        })

    photo_path = None
    if photo:
        filename = f"{uuid.uuid4().hex}_{photo.filename}"
        full_path = os.path.join("user_photos", filename)
        with open(full_path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)
        photo_path = f"/user_photos/{filename}"

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        hashed_password=bcrypt.hash(password),
        profile_photo=photo_path,
        role="user"
    )

    session.add(user)
    session.commit()
    session.close()

    return RedirectResponse("/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Неверная почта или пароль",
        })

    if user.telegram_id and user.two_step_auth:
        code = str(random.randint(100000, 999999))
        twofa_codes[user.id] = {
            "code": code,
            "expires": datetime.utcnow() + timedelta(minutes=3),
        }

        from telegram import Bot
        bot = Bot(token=os.getenv("TG_API_TOKEN"))
        await bot.send_message(
            chat_id=user.telegram_id,
            text=f"🔐 Ваш код подтверждения входа: {code}\n\nЕсли это не вы, введите /quit",
        )

        # временно сохранить ID пользователя в сессии
        request.session["2fa_user_id"] = user.id
        return templates.TemplateResponse("two_step_auth.html", {"request": request})

    # Если 2FA не нужна
    access_token = create_access_token(data={"sub": str(user.id)})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, current_user: User = Depends(get_current_user)):
    session = SessionLocal()
    user = session.query(User).filter(User.id == current_user.id).first()

    # Собираем статистику
    stats = {
        "confirmed": user.confirmed_matches,
        "rejected": user.rejected_matches,
        "total": user.face_searches,
    }

    # Пример: загружаем историю из временного атрибута
    matches = getattr(user, "_history", [])

    session.close()

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": user,
            "matches": matches,
            "stats": stats,
            "message": request.query_params.get("message"),
        },
    )


@app.post("/change-password")
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if new_password != confirm_password:
        stats = {"confirmed": 0, "rejected": 0, "total": 0}
        matches = []
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": current_user,
                "matches": matches,
                "stats": stats,
                "password_error": "Пароли не совпадают",
            },
        )

    if not verify_password(old_password, current_user.hashed_password):
        stats = {"confirmed": 0, "rejected": 0, "total": 0}
        matches = []
        return templates.TemplateResponse(
            "profile.html",
            {
                "request": request,
                "user": current_user,
                "matches": matches,
                "stats": stats,
                "password_error": "Старый пароль неверный",
            },
        )

    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    return RedirectResponse("/profile?message=Пароль+успешно+изменён", status_code=303)



@app.post("/logout")
async def logout_user():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response

@app.post("/link_telegram")
async def generate_telegram_link(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.telegram_id:
        return JSONResponse(content={"error": "Уже привязан Telegram"}, status_code=400)

    link_token = secrets.token_urlsafe(16)
    current_user.telegram_link_token = link_token
    db.commit()
    link = f"https://t.me/VisualFacePro_bot?start={link_token}"
    return JSONResponse(content={"link": link})

@app.post("/unlink_telegram")
async def unlink_telegram(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.telegram_id = None
    current_user.telegram_link_token = None
    db.commit()
    return JSONResponse(content={"message": "Telegram отвязан"})

@app.post("/tg_recognize")
async def tg_recognize(
    user_id: int = Form(...),
    file: UploadFile = File(...),
    tolerance: float = 0.6
):
    session = SessionLocal()
    user = session.query(User).filter(User.id == user_id).first()

    if not user or not user.telegram_id:
        session.close()
        return JSONResponse(
            content={
                "error": "Вы не авторизованы. Пожалуйста, сначала войдите на сайте:",
                "login_url": MAIN_URL
            },
            status_code=401
        )

    # Сохраняем файл
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    save_upload_file(file, filepath)

    # Запускаем распознавание
    results = recognize(filepath, tolerance=tolerance)

    all_persons = session.query(Person).all()
    session.close()

    best_match = None
    max_similarity = 0

    for result in results:
        if result["name"] == "Неизвестно":
            continue
        person = next((p for p in all_persons if p.name == result["name"]), None)
        if not person:
            continue
        similarity = round(result["confidence"] * 100, 2)
        if similarity > max_similarity:
            best_match = {
                "id": person.id,
                "name": person.name,
                "photo_url": f"{MAIN_URL}/known_faces/{os.path.basename(person.photo_path)}",
                "similarity": similarity
            }
            max_similarity = similarity

    if not best_match:
        return JSONResponse(content={"matched": None, "input_photo": filepath})

    return JSONResponse(content={"matched": best_match, "input_photo": filepath})

@app.post("/request_2fa_code")
async def request_2fa_code(current_user: User = Depends(get_current_user)):
    if not current_user.telegram_id:
        return JSONResponse({"error": "Telegram не привязан"}, status_code=400)

    # Генерация кода (например, 6 цифр)
    code = secrets.randbelow(1000000)
    code_str = f"{code:06}"

    # Временно сохраняем код в память
    recognition_temp[current_user.id] = {
        "code": code_str,
        "expires": datetime.utcnow().timestamp() + 300  # 5 минут жизни
    }

    # Отправляем код через бота
    try:
        await telegram_app.bot.send_message(
            chat_id=current_user.telegram_id,
            text=f"🔐 Ваш код подтверждения для включения 2FA: {code_str}"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке кода: {e}")
        return JSONResponse({"error": "Ошибка при отправке кода в Telegram"}, status_code=500)

    return JSONResponse({"message": "Код отправлен"})

@app.post("/verify_2fa")
async def verify_2fa(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get("2fa_user_id")
    if not user_id or user_id not in twofa_codes:
        return RedirectResponse("/login", status_code=303)

    entry = twofa_codes[user_id]
    if entry["code"] != code or entry["expires"] < datetime.utcnow():
        return templates.TemplateResponse("2fa.html", {
            "request": request,
            "error": "Неверный или просроченный код"
        })

    del twofa_codes[user_id]
    request.session.pop("2fa_user_id", None)

    access_token = create_access_token(data={"sub": str(user_id)})
    response = RedirectResponse(url="/profile", status_code=302)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)

    # Уведомление в Telegram
    from telegram import Bot
    bot = Bot(token=os.getenv("TG_API_TOKEN"))
    db_user = db.query(User).filter(User.id == user_id).first()
    if db_user and db_user.telegram_id:
        await bot.send_message(
            chat_id=db_user.telegram_id,
            text="✅ Был выполнен вход в ваш аккаунт. Если это не вы — смените пароль.",
        )

    return response

@app.post("/toggle_2fa")
async def toggle_2fa(
    code: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    entry = recognition_temp.get(current_user.id)
    if not entry or entry["expires"] < datetime.utcnow().timestamp():
        return RedirectResponse("/profile?telegram_error=Код+истёк+или+не+запрошен", status_code=303)

    if entry["code"] != code:
        return RedirectResponse("/profile?telegram_error=Неверный+код", status_code=303)

    # 🔥 Вот тут важно: получить user из базы, а не использовать current_user
    user = db.query(User).filter(User.id == current_user.id).first()
    user.two_step_auth = not user.two_step_auth
    db.commit()

    recognition_temp.pop(current_user.id, None)

    state = "2fa_enabled" if user.two_step_auth else "2fa_disabled"
    return RedirectResponse(f"/profile?telegram_success={state}", status_code=303)

app.mount("/known_faces", StaticFiles(directory="known_faces"), name="known_faces")
app.mount("/user_photos", StaticFiles(directory="user_photos"), name="user_photos")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/temp_cropped_faces", StaticFiles(directory="temp_cropped_faces"), name="temp_cropped_faces")

@app.on_event("startup")
async def startup_event():
    await telegram_app.initialize()
    await telegram_app.start()
    asyncio.create_task(telegram_app.updater.start_polling())

@app.on_event("shutdown")
async def shutdown_event():
    await telegram_app.updater.stop()
    await telegram_app.stop()