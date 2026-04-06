"""
generator.py — ReportLab PDF üretici
Mevcut etiketYazdir.py mantığını BytesIO ile stream'e taşır.
Diske hiçbir şey yazılmaz.
"""

from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
import qrcode
from PIL import Image
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_font():
    """Sistem fontunu yükle"""
    # Windows'ta Arial, Linux'ta DejaVu
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("EtiketFont", path))
                return "EtiketFont"
            except Exception:
                continue
    return "Helvetica-Bold"   # Fallback


def _make_qr(url: str) -> BytesIO:
    """URL'den QR kod üret → BytesIO döner"""
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img   = qr.make_image(fill_color="black", back_color="white")
    buf   = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _format_price(price: float) -> str:
    """12500 → '12.500'"""
    return f"{int(price):,}".replace(",", ".")


def generate_pdf(buffer: BytesIO, label_data: dict) -> None:
    """
    label_data yapısı (user_labels tablosundan gelen):
    {
        "kategori"  : "Yatak Odası",
        "koleksiyon": "Svea",
        "takim_adi" : "6 Kapaklı, Karyola",
        "urunler"   : [
            {"sku": "...", "urun_adi_tam": "...", "liste_fiyat": 12500,
             "perakende_fiyat": 11250, "miktar": 1}
        ],
        "takim_sku" : {"sku": "...", "liste_fiyat": ..., "perakende_fiyat": ..., "indirim_yuzde": 10}
    }
    """
    font_name  = _get_font()
    page_w, page_h = landscape(A4)   # 297 × 210 mm

    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    kategori   = label_data.get("kategori", "")
    koleksiyon = label_data.get("koleksiyon", "")
    takim_adi  = label_data.get("takim_adi", "")
    urunler    = label_data.get("urunler", [])
    takim_sku  = label_data.get("takim_sku", {})
    tarih      = datetime.now().strftime("%d.%m.%Y")

    # ----------------------------------------------------------------
    # Sayfa düzeni — basit grid (max 11 ürün, 3 sütun)
    # ----------------------------------------------------------------
    margin    = 10 * mm
    card_w    = (page_w - 2 * margin) / 3
    card_h    = (page_h - 2 * margin) / 4
    cols      = 3

    for idx, urun in enumerate(urunler[:11]):
        col = idx % cols
        row = idx // cols

        x = margin + col * card_w
        y = page_h - margin - (row + 1) * card_h

        _draw_card(c, x, y, card_w, card_h, urun, font_name,
                   kategori, koleksiyon, takim_adi, tarih)

    c.save()


def _draw_card(c, x, y, w, h, urun, font_name,
               kategori, koleksiyon, takim_adi, tarih):
    """Tek ürün kartını çiz"""
    pad = 3 * mm

    # Çerçeve
    c.setStrokeColor(colors.HexColor("#2c3e50"))
    c.setLineWidth(1)
    c.rect(x, y, w, h)

    # Koleksiyon başlık bandı
    c.setFillColor(colors.HexColor("#2c3e50"))
    c.rect(x, y + h - 10 * mm, w, 10 * mm, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont(font_name, 9)
    c.drawString(x + pad, y + h - 7 * mm, f"{koleksiyon}  |  {kategori}")

    # Ürün adı
    c.setFillColor(colors.HexColor("#2c3e50"))
    c.setFont(font_name, 8)
    urun_adi = urun.get("urun_adi_tam", "")[:50]
    c.drawString(x + pad, y + h - 15 * mm, urun_adi)

    # SKU
    c.setFont(font_name, 7)
    c.setFillColor(colors.HexColor("#7f8c8d"))
    c.drawString(x + pad, y + h - 20 * mm, f"SKU: {urun.get('sku', '')}")

    # Fiyatlar
    liste      = urun.get("liste_fiyat", 0)
    perakende  = urun.get("perakende_fiyat", 0)
    indirim    = int((1 - perakende / liste) * 100) if liste and liste != perakende else 0

    if indirim > 0:
        # Üstü çizili liste fiyatı
        c.setFont(font_name, 8)
        c.setFillColor(colors.HexColor("#95a5a6"))
        liste_str = f"{_format_price(liste)} TL"
        c.drawString(x + pad, y + h - 27 * mm, liste_str)
        # Üstü çizili çizgi
        tw = c.stringWidth(liste_str, font_name, 8)
        c.line(x + pad, y + h - 26 * mm, x + pad + tw, y + h - 26 * mm)

        # İndirim etiketi
        c.setFillColor(colors.HexColor("#e74c3c"))
        c.roundRect(x + w - 18 * mm, y + h - 30 * mm, 16 * mm, 8 * mm, 2 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(font_name, 8)
        c.drawCentredString(x + w - 10 * mm, y + h - 27 * mm, f"%{indirim}")

    # Perakende fiyat (büyük)
    c.setFillColor(colors.HexColor("#2c3e50"))
    c.setFont(font_name, 14)
    c.drawString(x + pad, y + h - 37 * mm, f"{_format_price(perakende)} TL")

    # Miktar
    miktar = urun.get("miktar", 1)
    if int(miktar) > 1:
        c.setFont(font_name, 8)
        c.setFillColor(colors.HexColor("#27ae60"))
        c.drawString(x + pad, y + h - 43 * mm, f"Adet: {miktar}")

    # QR kod (ürün URL'si varsa)
    url = urun.get("urun_url", "")
    if url:
        try:
            qr_buf = _make_qr(url)
            from reportlab.lib.utils import ImageReader
            qr_img = ImageReader(qr_buf)
            qr_size = 15 * mm
            c.drawImage(qr_img, x + w - qr_size - pad, y + pad,
                        width=qr_size, height=qr_size)
        except Exception:
            pass

    # Tarih
    c.setFont(font_name, 6)
    c.setFillColor(colors.HexColor("#bdc3c7"))
    c.drawString(x + pad, y + pad, tarih)
