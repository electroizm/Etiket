from datetime import datetime, timezone
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from core.config import get_settings
from core.supabase_client import get_supabase

security = HTTPBearer(auto_error=False)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz token"
        )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict:
    """Cookie veya Authorization header'dan kullanıcıyı al"""
    token = None

    # Önce cookie'ye bak (tarayıcı istekleri)
    token = request.cookies.get("access_token")

    # Cookie yoksa Authorization header'a bak (API istekleri)
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Giriş yapmanız gerekiyor"
        )

    return decode_token(token)


async def require_active_subscription(
    user: dict = Depends(get_current_user)
) -> dict:
    """Aktif aboneliği olan kullanıcıları geçirir, olmayanları ödeme sayfasına yönlendirir"""
    user_id = user.get("sub")
    sb = get_supabase()

    result = sb.table("subscriptions").select("*").eq("user_id", user_id).limit(1).execute()

    if not result.data:
        raise HTTPException(status_code=402, detail="Abonelik bulunamadı")

    sub = result.data[0]
    now = datetime.now(timezone.utc)

    # Trial kontrolü
    if sub["plan"] == "trial":
        trial_ends = datetime.fromisoformat(sub["trial_ends"].replace("Z", "+00:00"))
        if now > trial_ends:
            raise HTTPException(status_code=402, detail="Trial süreniz doldu")

    # Ödeme yapılmış plan kontrolü
    elif sub["plan"] == "paid":
        paid_until = datetime.fromisoformat(sub["paid_until"].replace("Z", "+00:00"))
        if now > paid_until:
            raise HTTPException(status_code=402, detail="Aboneliğiniz sona erdi")

    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Sadece admin rolündeki kullanıcıları geçirir"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Yetkiniz yok")
    return user
