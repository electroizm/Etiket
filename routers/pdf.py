from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any
from io import BytesIO
from core.auth import get_current_user, require_active_subscription
from core.supabase_client import get_supabase
from pdf.generator import generate_pdf

router = APIRouter()


class PdfRequest(BaseModel):
    kategori  : str
    koleksiyon: str


@router.post("/generate")
async def pdf_generate(
    body: PdfRequest,
    user: dict = Depends(require_active_subscription),   # Trial/paid kontrolü
):
    """
    Kaydedilmiş etiket seçiminden PDF üret → tarayıcıya stream et.
    Dosya diske yazılmaz.
    """
    sb = get_supabase()

    # Kullanıcının bu koleksiyon için kayıtlı etiketini al
    res = (
        sb.table("user_labels")
        .select("*")
        .eq("user_id", user["sub"])
        .eq("kategori", body.kategori)
        .eq("koleksiyon", body.koleksiyon)
        .single()
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="Bu koleksiyon için kayıtlı etiket yok")

    label_data = res.data

    # PDF üret (BytesIO — diske yazmaz)
    buffer = BytesIO()
    generate_pdf(buffer, label_data)
    buffer.seek(0)

    filename = f"etiket_{body.koleksiyon}_{body.kategori}.pdf".replace(" ", "_")

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/preview")
async def pdf_preview(
    body: PdfRequest,
    user: dict = Depends(require_active_subscription),
):
    """PDF'i tarayıcıda göster (indirme yerine)"""
    sb = get_supabase()

    res = (
        sb.table("user_labels")
        .select("*")
        .eq("user_id", user["sub"])
        .eq("kategori", body.kategori)
        .eq("koleksiyon", body.koleksiyon)
        .single()
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="Etiket bulunamadı")

    buffer = BytesIO()
    generate_pdf(buffer, res.data)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )
