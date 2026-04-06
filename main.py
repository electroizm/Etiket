from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse

from routers import auth, products, labels, pdf, admin

app = FastAPI(
    title="Etiket Sistemi",
    description="Doğtaş bayii etiket yönetim sistemi",
    version="1.0.0",
    docs_url="/docs",       # Geliştirme sırasında açık, prod'da kapatılabilir
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Router'ları kaydet
app.include_router(auth.router,     prefix="/auth",     tags=["Auth"])
app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(labels.router,   prefix="/labels",   tags=["Labels"])
app.include_router(pdf.router,      prefix="/pdf",      tags=["PDF"])
app.include_router(admin.router,    prefix="/admin",    tags=["Admin"])


@app.get("/")
async def root(request: Request):
    """Ana sayfa — giriş yapılmamışsa login'e yönlendir"""
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/health")
async def health():
    """Render + UptimeRobot ping endpoint'i"""
    return {"status": "ok"}


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    # API isteği ise JSON dön, sayfa isteği ise login'e yönlendir
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"detail": str(exc.detail)}, status_code=401)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/auth/login")


@app.exception_handler(402)
async def payment_required_handler(request: Request, exc):
    return templates.TemplateResponse(
        request, "payment.html",
        {"message": str(exc.detail)},
        status_code=402,
    )
