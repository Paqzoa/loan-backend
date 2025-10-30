from fastapi import Request, Response, HTTPException, Depends, status
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.utils import verify_password, hash_password
from app.models import User
from app.database import AsyncSessionLocal
from sqlalchemy.future import select
from app.schemas import LoginRequest, ChangePasswordRequest

# ==============================
# SESSION CONFIG
# ==============================

SECRET_KEY = "super_secret_session_key_change_this"  # ⚠️ Change in production
SESSION_EXPIRE_HOURS = 6

serializer = URLSafeTimedSerializer(SECRET_KEY)


# ==============================
# SESSION HELPERS
# ==============================

def create_session_cookie(username: str):
    """Create a signed cookie containing username."""
    return serializer.dumps({"username": username})


def verify_session_cookie(cookie: str):
    """Validate session cookie and return username."""
    try:
        data = serializer.loads(cookie, max_age=SESSION_EXPIRE_HOURS * 3600)
        return data["username"]
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Session expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid session token")


# ==============================
# DATABASE DEPENDENCY
# ==============================

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ==============================
# AUTH LOGIC
# ==============================

async def login(request: Request, response: Response, username: str, password: str, db):
    """Login logic that validates credentials and sets a cookie."""
    result = await db.execute(select(User).filter_by(username=username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Create cookie
    session_token = create_session_cookie(username)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=SESSION_EXPIRE_HOURS * 3600,
        samesite="none",  # ✅ "lax" works well for local testing
        secure=True     # ✅ Change to True when you deploy with HTTPS
    )
    return {"id": user.id, "username": user.username}


async def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}


# ==============================
# AUTH DEPENDENCY
# ==============================

async def get_current_user(request: Request, db=Depends(get_db)):
    """Return the currently logged-in user from session cookie."""
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    username = verify_session_cookie(session_token)
    result = await db.execute(select(User).filter_by(username=username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ==============================
# CHANGE PASSWORD LOGIC
# ==============================

async def change_password(data: ChangePasswordRequest, current_user: User, db):
    """Change user's password after verifying old password."""
    if not verify_password(data.old_password, current_user.password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    current_user.password = hash_password(data.new_password)
    db.add(current_user)
    await db.commit()

    return {"message": "Password changed successfully"}