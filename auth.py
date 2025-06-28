import jwt
import os
from datetime import datetime, timedelta
from passlib.hash import bcrypt
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER
from db.database import SessionLocal
from db.models import User
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status, Request
from jose import JWTError, jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)

def get_password_hash(password):
    return bcrypt.hash(password)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(request: Request, db=Depends(get_db)):
    token = get_token_from_cookie(request)
    if not token:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)

    return user

def get_current_user_optional(request: Request, db):
    token = get_token_from_cookie(request)
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user

def get_token_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        return token[7:]
    return None