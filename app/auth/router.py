import hashlib
import secrets
import time
from typing import Annotated, Optional
import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.config import get_settings, Settings
from app.core.database import get_async_session, bind_tenant, bind_auth_email
from app.auth.models import User, UserRole, SubscriptionTier
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    token_type: str = "Bearer"
    expires_in: int
    user: User


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    )
    return key.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    key, _ = hash_password(password, salt)
    return secrets.compare_digest(key, stored_hash)


def create_access_token(user_id: str, email: str, role: str, tier: str, secret: str, expires_in_seconds: int = 86400 * 7) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "app_metadata": {
            "tier": tier,
        },
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    await bind_auth_email(db, data.email)
    # Check if user already exists
    stmt_check = text("SELECT id_usuario FROM core.usuario WHERE email = :email LIMIT 1")
    res_check = await db.execute(stmt_check, {"email": data.email.lower().strip()})
    if res_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma conta cadastrada com este endereço de e-mail.",
        )

    pwd_hash, salt = hash_password(data.password)

    # Insert user into core.usuario
    stmt_insert = text(
        """
        INSERT INTO core.usuario (
            nome, email, password_hash, salt, role, tier, status, data_cadastro
        ) VALUES (
            :name, :email, :pwd_hash, :salt, 'user', 'free', 'Ativo', NOW()
        )
        RETURNING id_usuario, nome, email, role, tier;
        """
    )
    res_user = await db.execute(
        stmt_insert,
        {
            "name": data.name.strip(),
            "email": data.email.lower().strip(),
            "pwd_hash": pwd_hash,
            "salt": salt,
        },
    )
    user_row = res_user.mappings().one()
    user_id = str(user_row["id_usuario"])

    await bind_tenant(db, user_id)
    # Create default user wallet
    stmt_wallet = text(
        """
        INSERT INTO core.carteira (id_usuario, nome_carteira, principal)
        VALUES (:user_id, 'Minha Carteira', TRUE);
        """
    )
    await db.execute(stmt_wallet, {"user_id": user_id})
    await db.commit()

    # Generate JWT Token
    jwt_secret = settings.SUPABASE_JWT_SECRET
    expires_in = 86400 * 7
    token = create_access_token(
        user_id=user_id,
        email=user_row["email"],
        role=user_row["role"],
        tier=user_row["tier"],
        secret=jwt_secret,
        expires_in_seconds=expires_in,
    )

    user_obj = User(
        id=user_id,
        email=user_row["email"],
        name=user_row["nome"],
        role=UserRole(user_row["role"]),
        tier=SubscriptionTier(user_row["tier"]),
        is_active=True,
    )

    # Set secure HttpOnly cookie
    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=expires_in,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )

    return AuthResponse(token=token, expires_in=expires_in, user=user_obj)


@router.post("/login", response_model=AuthResponse)
async def login(
    data: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    await bind_auth_email(db, data.email)
    stmt = text(
        """
        SELECT id_usuario, nome, email, password_hash, salt, role, tier, status
        FROM core.usuario
        WHERE email = :email
        LIMIT 1;
        """
    )
    res = await db.execute(stmt, {"email": data.email.lower().strip()})
    row = res.mappings().first()

    if not row or not row.get("password_hash") or not row.get("salt"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    if not verify_password(data.password, row["password_hash"], row["salt"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
        )

    user_id = str(row["id_usuario"])

    # Update last access
    await db.execute(
        text("UPDATE core.usuario SET ultimo_acesso = NOW() WHERE id_usuario = :uid"),
        {"uid": user_id},
    )
    await db.commit()

    jwt_secret = settings.SUPABASE_JWT_SECRET
    expires_in = 86400 * 7
    token = create_access_token(
        user_id=user_id,
        email=row["email"],
        role=row["role"] or "user",
        tier=row["tier"] or "free",
        secret=jwt_secret,
        expires_in_seconds=expires_in,
    )

    user_obj = User(
        id=user_id,
        email=row["email"],
        name=row["nome"],
        role=UserRole(row["role"] or "user"),
        tier=SubscriptionTier(row["tier"] or "free"),
        is_active=row["status"] == "Ativo",
    )

    response.set_cookie(
        key="auth_token",
        value=token,
        max_age=expires_in,
        httponly=True,
        samesite="lax",
        secure=settings.ENVIRONMENT == "production",
    )

    return AuthResponse(token=token, expires_in=expires_in, user=user_obj)


@router.get("/me", response_model=User)
async def get_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="auth_token")
    return {"logged_out": True}
