from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import jwt
from core.config import get_settings
from core.supabase_client import get_supabase

router    = APIRouter()
templates = Jinja2Templates(directory="templates")


def create_token(user_id: str, email: str, role: str = "user") -> str:
    settings = get_settings()
    payload  = {
        "sub"  : user_id,
        "email": email,
        "role" : role,
        "exp"  : datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.post("/login")
async def login(
    request : Request,
    email   : str = Form(...),
    password: str = Form(...),
):
    sb = get_supabase()
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        return templates.TemplateResponse(
            request, "login.html",
            {"error": "E-posta veya şifre hatalı"},
            status_code=401,
        )

    user = res.user
    role = user.app_metadata.get("role", "user")
    token = create_token(str(user.id), user.email, role)

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key      = "access_token",
        value    = token,
        httponly = True,
        samesite = "lax",
        max_age  = 7 * 24 * 3600,
    )
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.post("/register")
async def register(
    request   : Request,
    email     : str = Form(...),
    password  : str = Form(...),
    bayii_adi : str = Form(...),
):
    sb = get_supabase()
    try:
        sb.auth.sign_up({
            "email"   : email,
            "password": password,
            "options" : {"data": {"bayii_adi": bayii_adi}},
        })
    except Exception as e:
        return templates.TemplateResponse(
            request, "register.html",
            {"error": str(e)},
            status_code=400,
        )

    return templates.TemplateResponse(
        request, "login.html",
        {"success": "Kayıt başarılı! Giriş yapabilirsiniz."},
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie("access_token")
    return response
