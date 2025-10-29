# routes/auth_routes.py
from fastapi import APIRouter, Response, Depends,Request
from app.auth import login, logout, get_current_user, change_password
from app.schemas import LoginRequest,ChangePasswordRequest
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login")
async def login_route(
    request: Request,
    response: Response,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    return await login(request=request, response=response, username=data.username, password=data.password, db=db)


@router.post("/logout")
async def logout_route(response: Response):
    return await logout(response)


@router.get("/me")
async def me_route(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
    }

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "created_at": current_user.created_at}


@router.put("/change-password")
async def change_password_route(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await change_password(data=data, current_user=current_user, db=db)