from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Enum, BigInteger, Boolean
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import ARRAY
import datetime
import enum

Base = declarative_base()

class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    profile_photo = Column(String, nullable=True)
    role = Column(String, default="user") 

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    confirmed_matches = Column(Integer, default=0)
    rejected_matches = Column(Integer, default=0)
    face_searches = Column(Integer, default=0)

    telegram_id = Column(BigInteger, nullable=True, unique=True)
    telegram_link_token = Column(String, nullable=True, unique=True)
    two_step_auth = Column(Boolean, default=False)

    persons = relationship("Person", back_populates="user", cascade="all, delete-orphan")

class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    photo_path = Column(String, nullable=True)
    face_encoding = Column(ARRAY(Float), nullable=False)
    gender = Column(String, default="не указано")

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="persons")
