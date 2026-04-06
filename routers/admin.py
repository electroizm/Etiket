import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from core.auth import require_admin
from core.supabase_client import get_supabase

router    = APIRouter()
templates = Jinja2Templates(directory="templates")

_scraper_running = False   # Basit lock (tek instance için yeterli)


@router.get("/", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    user   : dict = Depends(require_admin),
):
    sb = get_supabase()

    # Özet istatistikler
    product_count = sb.table("products").select("sku", count="exact").execute().count
    user_count    = sb.table("subscriptions").select("user_id", count="exact").execute().count
    trial_count   = sb.table("subscriptions").select("user_id", count="exact").eq("plan", "trial").execute().count
    paid_count    = sb.table("subscriptions").select("user_id", count="exact").eq("plan", "paid").execute().count

    # Son kayıtlı kullanıcılar
    users_res = (
        sb.table("subscriptions")
        .select("user_id, bayii_adi, plan, trial_ends, paid_until, created_at")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return templates.TemplateResponse(request, "admin.html", {
        "product_count": product_count,
        "user_count"   : user_count,
        "trial_count"  : trial_count,
        "paid_count"   : paid_count,
        "users"        : users_res.data,
        "scraper_running": _scraper_running,
    })


@router.post("/scraper/start")
async def start_scraper(
    background_tasks: BackgroundTasks,
    user            : dict = Depends(require_admin),
):
    """Scraper'ı arka planda başlat"""
    global _scraper_running
    if _scraper_running:
        raise HTTPException(status_code=409, detail="Scraper zaten çalışıyor")

    def run_scraper():
        global _scraper_running
        _scraper_running = True
        try:
            from scraper.dogtas import run
            run()
        finally:
            _scraper_running = False

    background_tasks.add_task(run_scraper)
    return {"ok": True, "message": "Scraper başlatıldı"}


@router.get("/scraper/status")
async def scraper_status(user: dict = Depends(require_admin)):
    return {"running": _scraper_running}


@router.get("/kullanicilar")
async def list_users(user: dict = Depends(require_admin)):
    sb  = get_supabase()
    res = (
        sb.table("subscriptions")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return {"users": res.data}


@router.post("/kullanici/{user_id}/paid")
async def set_paid(
    user_id   : str,
    gun        : int = 30,
    admin_user : dict = Depends(require_admin),
):
    """Kullanıcıyı paid plana geçir"""
    from datetime import datetime, timedelta, timezone
    sb        = get_supabase()
    paid_until = (datetime.now(timezone.utc) + timedelta(days=gun)).isoformat()
    sb.table("subscriptions").update({
        "plan"      : "paid",
        "paid_until": paid_until,
    }).eq("user_id", user_id).execute()
    return {"ok": True, "paid_until": paid_until}
