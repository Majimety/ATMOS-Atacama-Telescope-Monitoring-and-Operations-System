"""
auth.py  —  ATMOS Authentication & Role-Based Access Control
=============================================================

Roles (least → most privileged):
  viewer    → read-only: telemetry, alerts, dashboards
  operator  → viewer + slew, stow, band selection
  engineer  → operator + fault injection, calibration, config changes
  admin     → engineer + user management, system shutdown

Usage:
  from auth import require_role, get_current_user, Role

  @router.post("/telescope/{dish_id}/slew")
  async def slew_telescope(dish_id: str, cmd: SlewCommand,
                            user: User = Depends(require_role(Role.OPERATOR))):
      ...

Setup:
  pip install python-jose[cryptography] passlib[bcrypt] python-multipart
  Set env vars: ATMOS_SECRET_KEY, ATMOS_ACCESS_TOKEN_EXPIRE_MINUTES (default 60)
"""

import os
import enum
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ─── Config ────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv(
    "ATMOS_SECRET_KEY", "change-this-in-production-use-openssl-rand-hex-32"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ATMOS_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

router = APIRouter(prefix="/auth", tags=["auth"])


# ─── Role hierarchy ─────────────────────────────────────────────────────────
class Role(str, enum.Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ENGINEER = "engineer"
    ADMIN = "admin"


ROLE_RANK = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.ENGINEER: 2,
    Role.ADMIN: 3,
}

# What each role can do (additive — higher roles inherit all lower permissions)
ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.VIEWER: {
        "telemetry:read",
        "alerts:read",
        "dashboard:read",
        "uv_coverage:read",
        "correlator:read",
    },
    Role.OPERATOR: {
        "telescope:slew",
        "telescope:stow",
        "telescope:band_select",
        "observation:queue_read",
        "observation:queue_write",
    },
    Role.ENGINEER: {
        "telescope:fault_inject",
        "telescope:calibrate",
        "config:write",
        "correlator:flag",
        "logs:read",
    },
    Role.ADMIN: {
        "users:manage",
        "system:shutdown",
        "system:restart",
        "audit:read",
    },
}


def has_permission(role: Role, permission: str) -> bool:
    """Check if role (or any lower role) grants a permission."""
    rank = ROLE_RANK[role]
    for r, perms in ROLE_PERMISSIONS.items():
        if ROLE_RANK[r] <= rank and permission in perms:
            return True
    return False


# ─── Models ─────────────────────────────────────────────────────────────────
class User(BaseModel):
    username: str
    role: Role
    full_name: Optional[str] = None
    disabled: bool = False


class UserInDB(User):
    hashed_password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: Role
    expires_in: int  # seconds


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[Role] = None


# ─── Demo user store (replace with PostgreSQL in production) ─────────────────
# Generate hashes: pwd_context.hash("your-password")
_DEMO_USERS: dict[str, UserInDB] = {
    "viewer": UserInDB(
        username="viewer",
        role=Role.VIEWER,
        full_name="Observation Viewer",
        hashed_password=pwd_context.hash("viewer123"),
    ),
    "operator": UserInDB(
        username="operator",
        role=Role.OPERATOR,
        full_name="Array Operator",
        hashed_password=pwd_context.hash("operator123"),
    ),
    "engineer": UserInDB(
        username="engineer",
        role=Role.ENGINEER,
        full_name="Systems Engineer",
        hashed_password=pwd_context.hash("engineer123"),
    ),
    "admin": UserInDB(
        username="admin",
        role=Role.ADMIN,
        full_name="System Administrator",
        hashed_password=pwd_context.hash("admin123"),
    ),
}


def get_user(username: str) -> Optional[UserInDB]:
    return _DEMO_USERS.get(username)


# ─── Token helpers ───────────────────────────────────────────────────────────
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    user = get_user(username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_token(data: dict, expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(username: str, role: Role) -> str:
    return create_token(
        {"sub": username, "role": role, "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(username: str, role: Role) -> str:
    return create_token(
        {"sub": username, "role": role, "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


# ─── FastAPI dependencies ────────────────────────────────────────────────────
async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        if not username or token_type != "access":
            raise credentials_error
        token_data = TokenData(username=username, role=payload.get("role"))
    except JWTError:
        raise credentials_error

    user = get_user(token_data.username)
    if not user or user.disabled:
        raise credentials_error
    return user


def require_role(minimum_role: Role):
    """
    FastAPI dependency factory. Usage:
      user: User = Depends(require_role(Role.OPERATOR))
    """

    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK[current_user.role] < ROLE_RANK[minimum_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{minimum_role}' role or higher. "
                f"Your role: '{current_user.role}'",
            )
        return current_user

    return _checker


def require_permission(permission: str):
    """
    Fine-grained permission check. Usage:
      user: User = Depends(require_permission("telescope:fault_inject"))
    """

    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: '{permission}'",
            )
        return current_user

    return _checker


# ─── WebSocket auth helper ──────────────────────────────────────────────────
async def ws_authenticate(token: str, minimum_role: Role = Role.VIEWER) -> User:
    """
    Use in WebSocket endpoints — FastAPI Depends() doesn't work with WS.

    Usage in main.py:
      @app.websocket("/ws/telemetry")
      async def telemetry_ws(ws: WebSocket, token: str = Query(...)):
          user = await ws_authenticate(token, Role.VIEWER)
          await ws.accept()
          ...
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise ValueError("no subject")
        user = get_user(username)
        if not user or user.disabled:
            raise ValueError("user not found")
        if ROLE_RANK[user.role] < ROLE_RANK[minimum_role]:
            raise ValueError("insufficient role")
        return user
    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ─── Routes ─────────────────────────────────────────────────────────────────
@router.post("/token", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(
        access_token=create_access_token(user.username, user.role),
        refresh_token=create_refresh_token(user.username, user.role),
        role=user.role,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_tok: str):
    try:
        payload = jwt.decode(refresh_tok, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise ValueError("not a refresh token")
        username = payload.get("sub")
        user = get_user(username)
        if not user or user.disabled:
            raise ValueError("user invalid")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    return Token(
        access_token=create_access_token(user.username, user.role),
        refresh_token=create_refresh_token(user.username, user.role),
        role=user.role,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/permissions")
async def get_my_permissions(current_user: User = Depends(get_current_user)):
    """Return all permissions available to the current user's role."""
    all_perms = set()
    rank = ROLE_RANK[current_user.role]
    for role, perms in ROLE_PERMISSIONS.items():
        if ROLE_RANK[role] <= rank:
            all_perms.update(perms)
    return {"role": current_user.role, "permissions": sorted(all_perms)}
