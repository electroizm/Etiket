from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any
from core.auth import get_current_user
from core.supabase_client import get_supabase

router = APIRouter()


class LabelSaveRequest(BaseModel):
    kategori  : str
    koleksiyon: str
    takim_adi : str = ""
    urunler   : list[dict[str, Any]] = []
    takim_sku : dict[str, Any] = {}


@router.get("/")
async def get_labels(user: dict = Depends(get_current_user)):
    """Kullanıcının tüm etiket seçimlerini döner"""
    sb  = get_supabase()
    res = (
        sb.table("user_labels")
        .select("*")
        .eq("user_id", user["sub"])
        .order("updated_at", desc=True)
        .execute()
    )
    return {"labels": res.data}


@router.get("/{kategori}/{koleksiyon}")
async def get_label(
    kategori  : str,
    koleksiyon: str,
    user      : dict = Depends(get_current_user),
):
    """Belirli kategori + koleksiyon için kayıtlı etiketi döner"""
    sb  = get_supabase()
    res = (
        sb.table("user_labels")
        .select("*")
        .eq("user_id", user["sub"])
        .eq("kategori", kategori)
        .eq("koleksiyon", koleksiyon)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Etiket bulunamadı")
    return res.data


@router.post("/kaydet")
async def save_label(
    body: LabelSaveRequest,
    user: dict = Depends(get_current_user),
):
    """Etiket seçimini kaydet veya güncelle (upsert)"""
    sb = get_supabase()

    row = {
        "user_id"   : user["sub"],
        "kategori"  : body.kategori,
        "koleksiyon": body.koleksiyon,
        "takim_adi" : body.takim_adi,
        "urunler"   : body.urunler,
        "takim_sku" : body.takim_sku,
    }

    sb.table("user_labels").upsert(
        row,
        on_conflict="user_id,kategori,koleksiyon"
    ).execute()

    return {"ok": True, "message": f"{body.koleksiyon} / {body.kategori} kaydedildi"}


@router.delete("/{kategori}/{koleksiyon}")
async def delete_label(
    kategori  : str,
    koleksiyon: str,
    user      : dict = Depends(get_current_user),
):
    """Etiket seçimini sil"""
    sb = get_supabase()
    sb.table("user_labels").delete().eq("user_id", user["sub"]).eq(
        "kategori", kategori
    ).eq("koleksiyon", koleksiyon).execute()
    return {"ok": True}
