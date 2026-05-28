"""Authentication service"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

from ..db.connection import get_db
from ..db.models import User

# JWT config
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "30"))

# Password encryption
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    user_id: Optional[int] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str  # Min 6 chars


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime


class AuthService:
    """Authentication service class"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password"""
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT token"""
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=JWT_EXPIRATION_MINUTES))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[TokenData]:
        """Decode JWT token"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id: int = payload.get("sub")
            if user_id is None:
                return None
            return TokenData(user_id=user_id)
        except JWTError:
            return None

    async def register(self, email: str, password: str) -> Optional[User]:
        """Register new user"""
        async with get_db() as db:
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.email == email))
            existing_user = result.scalar_one_or_none()

            if existing_user:
                return None

            user = User(
                email=email,
                password_hash=self.hash_password(password),
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return user

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Verify user login"""
        async with get_db() as db:
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

            if not user or not user.is_active:
                return None
            if not self.verify_password(password, user.password_hash):
                return None

            return user

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID"""
        async with get_db() as db:
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()


auth_service = AuthService()