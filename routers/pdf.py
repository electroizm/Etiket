import traceback
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from io import BytesIO
from core.auth import get_current_user, require_active_subscription
from core.supabase_client import get_supabase
from pdf.generator import generate_pdf

logger = logging.getLogger(__name__)
router = APIRouter()


class PdfRequest(BaseModel):
    kategori  : str
    koleksiyon: str


@router.post("/generate")
async def pdf_generate(
    body: PdfRequest,
    user: dict = Depends(require_active_subscription),
):
    try:
        sb = get_supabase()

        # Kayıtlı etiketi al (.limit(1) kullan — .single() 0 satırda exception fırlatır)
        res = (
            sb.table("user_labels")
            .select("*")
            .eq("user_id", user["sub"])
            .eq("kategori", body.kategori)
            .eq("koleksiyon", body.koleksiyon)
            .limit(1)
            .execute()
        )

        if not res.data:
            raise HTTPException(status_code=404, detail="Bu koleksiyon için kayıtlı etiket yok")

        label_data = res.data[0]

        buffer = BytesIO()
        generate_pdf(buffer, label_data)
        buffer.seek(0)

        filename = (
            f"etiket_{body.koleksiyon}_{body.kategori}.pdf"
            .replace(" ", "_")
        )

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("PDF generate hatası:\n%s", tb)
        return JSONResponse(
            status_code=500,
            content={"detail": f"{type(e).__name__}: {e}", "traceback": tb},
        )
