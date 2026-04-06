from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from core.auth import get_current_user
from core.supabase_client import get_supabase

router = APIRouter()


@router.get("/kategoriler")
async def get_kategoriler(user: dict = Depends(get_current_user)):
    """Benzersiz kategori listesi döner"""
    sb  = get_supabase()
    res = sb.table("products").select("kategori").execute()
    kategoriler = sorted({r["kategori"] for r in res.data if r.get("kategori")})
    return {"kategoriler": kategoriler}


@router.get("/koleksiyonlar")
async def get_koleksiyonlar(
    kategori: str = Query(...),
    user    : dict = Depends(get_current_user),
):
    """Kategoriye göre benzersiz koleksiyon listesi döner"""
    sb  = get_supabase()
    res = (
        sb.table("products")
        .select("koleksiyon")
        .eq("kategori", kategori)
        .execute()
    )
    koleksiyonlar = sorted({r["koleksiyon"] for r in res.data if r.get("koleksiyon")})
    return {"koleksiyonlar": koleksiyonlar}


@router.get("/liste")
async def get_products(
    kategori  : str | None = Query(None),
    koleksiyon: str | None = Query(None),
    q         : str | None = Query(None),   # Serbest metin arama
    user      : dict = Depends(get_current_user),
):
    """
    Ürün listesi. Filtreler:
      - kategori
      - koleksiyon
      - q (ürün adı veya SKU'da arama)
    """
    sb    = get_supabase()
    query = sb.table("products").select(
        "sku, urun_adi, urun_adi_tam, koleksiyon, kategori, liste_fiyat, perakende_fiyat, urun_url"
    )

    if kategori:
        query = query.eq("kategori", kategori)
    if koleksiyon:
        query = query.eq("koleksiyon", koleksiyon)
    if q:
        # Supabase ilike ile basit arama (ürün adı)
        query = query.ilike("urun_adi_tam", f"%{q}%")

    query = query.order("urun_adi_tam")
    res   = query.execute()
    return {"products": res.data, "count": len(res.data)}
