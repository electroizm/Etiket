"""
generator.py — ReportLab PDF üretici
etiketYazdir.py mantığını BytesIO stream'e taşır (diske yazmaz).
"""

import os
import re
from io import BytesIO
from datetime import datetime
from typing import Optional

import requests
import qrcode
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ── Google Drive görsel URL'leri ─────────────────────────────────────────────
ETIKET_BASLIK_URL = (
    "https://drive.google.com/file/d/1RSP3YaCUNqy9Nedaaz5OUlKq9855Glh9"
    "/view?usp=drive_link"
)
YERLI_URETIM_URL = (
    "https://drive.google.com/file/d/1pYA85nxhmU6yhWJ3n0jIz1zAkTUeY--8"
    "/view?usp=drive_link"
)

# Modül düzeyinde görsel önbelleği
_IMAGE_CACHE: dict = {}

# Kullanılacak font isimleri (setup sonrası güncellenir)
_FONT_NORMAL = "Helvetica"
_FONT_BOLD   = "Helvetica-Bold"
_FONTS_READY = False


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

def _convert_gdrive_url(url: str) -> str:
    """Google Drive görüntüleme linkini doğrudan indirme linkine çevirir."""
    if "uc?export=download" in url:
        return url
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    return url


def _load_image(url: str) -> Optional[ImageReader]:
    """Google Drive URL'den görsel indir, önbellekle döndür."""
    if url in _IMAGE_CACHE:
        return _IMAGE_CACHE[url]
    try:
        dl  = _convert_gdrive_url(url)
        r   = requests.get(dl, timeout=10)
        if r.status_code == 200:
            img = ImageReader(BytesIO(r.content))
            _IMAGE_CACHE[url] = img
            return img
    except Exception:
        pass
    return None


def _setup_fonts():
    """Arial (Windows) veya DejaVu (Linux/Render) fontlarını kaydet.
    Bulunamazsa ReportLab built-in Helvetica kullanılır."""
    global _FONT_NORMAL, _FONT_BOLD, _FONTS_READY
    if _FONTS_READY:
        return
    font_pairs = [
        ("C:/Windows/Fonts/arial.ttf",    "C:/Windows/Fonts/arialbd.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for reg_path, bold_path in font_pairs:
        if os.path.exists(reg_path) and os.path.exists(bold_path):
            try:
                pdfmetrics.registerFont(TTFont("Arial",      reg_path))
                pdfmetrics.registerFont(TTFont("Arial-Bold", bold_path))
                _FONT_NORMAL = "Arial"
                _FONT_BOLD   = "Arial-Bold"
                _FONTS_READY = True
                return
            except Exception:
                continue
    # Fallback: Helvetica her zaman mevcut (ReportLab built-in)
    _FONT_NORMAL = "Helvetica"
    _FONT_BOLD   = "Helvetica-Bold"
    _FONTS_READY = True


def _font(bold: bool = False) -> str:
    """Kayıtlı font adını döner (setup'tan sonra gerçek değer)."""
    return _FONT_BOLD if bold else _FONT_NORMAL


def _make_qr(url: str) -> ImageReader:
    """URL'den QR kod görüntüsü üret → ImageReader döner."""
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def _format_price(price) -> str:
    """12500 → '12.500 TL'"""
    try:
        return f"{int(float(price)):,} TL".replace(",", ".")
    except (TypeError, ValueError):
        return "0 TL"


# ─────────────────────────────────────────────────────────────────────────────
# Çizim fonksiyonları
# ─────────────────────────────────────────────────────────────────────────────

def _draw_cutting_lines(c, page_width: float, page_height: float):
    """Köşe kesim çizgilerini çizer (etiketYazdir.py ile birebir)."""
    L = 60
    c.setLineWidth(2)
    c.setStrokeColorRGB(0, 0, 0)
    # Sol Üst
    c.line(10, page_height - 10, 10 + L, page_height - 10)
    c.line(10, page_height - 10, 10, page_height - 10 - L)
    # Sağ Üst
    c.line(page_width - 10, page_height - 10, page_width - 10 - L, page_height - 10)
    c.line(page_width - 10, page_height - 10, page_width - 10, page_height - 10 - L)
    # Sol Alt
    c.line(10, 10, 10 + L, 10)
    c.line(10, 10, 10, 10 + L)
    # Sağ Alt
    c.line(page_width - 10, 10, page_width - 10 - L, 10)
    c.line(page_width - 10, 10, page_width - 10, 10 + L)


def _draw_discount_badge(c, page_height: float, indirim_yuzde: int):
    """Siyah eğik indirim etiketi çizer (etiketYazdir.py ile birebir)."""
    etiket_width  = 110
    etiket_height = 45
    etiket_x      = 510
    etiket_y      = page_height - 140

    c.saveState()
    c.translate(etiket_x, etiket_y)
    c.rotate(-17)

    # Koyu arka plan
    c.setFillColorRGB(0.07, 0.07, 0.07)
    c.roundRect(0, 0, etiket_width, etiket_height, 8, fill=1, stroke=0)

    # Beyaz yazı
    c.setFillColorRGB(1, 1, 1)
    c.setFont(_font(bold=True), 36)
    text = f"-{indirim_yuzde}%"
    tw   = c.stringWidth(text, _font(bold=True), 36)
    c.drawString((etiket_width - tw) / 2, etiket_height / 2 - 13, text)

    c.restoreState()


def _draw_table(c, label_data: dict, page_width: float, page_height: float):
    """Fiyat tablosunu çizer (etiketYazdir.py ile birebir)."""
    styles     = getSampleStyleSheet()
    koleksiyon = label_data.get("koleksiyon", "")
    kategori   = label_data.get("kategori", "")
    urunler    = label_data.get("urunler", []) or []
    takim_sku  = label_data.get("takim_sku", {}) or {}

    # ── Başlık satırı ────────────────────────────────────────────────────────
    title_text = takim_sku.get("urun_adi_tam") or f"{koleksiyon} {kategori}"
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Normal"],
        fontName=_font(bold=True),
        fontSize=16,
        leading=18,
        textColor=colors.HexColor("#000000"),
        alignment=0,
    )
    title_para = Paragraph(title_text, title_style)
    data = [[title_para, "İNDİRİMLİ FİYAT", "LİSTE FİYATI"]]

    # ── Ürün satırları ───────────────────────────────────────────────────────
    product_style = ParagraphStyle(
        "ProductStyle",
        parent=styles["Normal"],
        fontName=_font(bold=False),
        fontSize=10,
        leading=12,
        textColor=colors.black,
    )
    for urun in urunler:
        name = Paragraph(urun.get("urun_adi_tam", ""), product_style)
        data.append([
            name,
            _format_price(urun.get("perakende_fiyat", 0)),
            _format_price(urun.get("liste_fiyat", 0)),
        ])

    product_count = len(urunler)

    # ── Takım / kombinasyon satırı (bold, büyük) ─────────────────────────────
    # Sadece takim_sku'nun fiyatı bireysel üründen farklıysa ekle
    takim_liste     = takim_sku.get("liste_fiyat", 0)
    takim_perakende = takim_sku.get("perakende_fiyat", 0)
    takim_adi       = (
        label_data.get("takim_adi", "")
        or takim_sku.get("urun_adi_tam", "")
    )
    first_liste = urunler[0].get("liste_fiyat", 0) if urunler else 0
    show_takim  = bool(takim_liste and takim_liste != first_liste and takim_adi)

    aciklama_style = ParagraphStyle(
        "AciklamaStyle",
        parent=styles["Normal"],
        fontName=_font(bold=True),
        fontSize=14,
        leading=16,
        textColor=colors.HexColor("#000000"),
        spaceBefore=10,
        spaceAfter=10,
    )
    if show_takim:
        para = Paragraph(takim_adi, aciklama_style)
        data.append([
            para,
            _format_price(takim_perakende),
            _format_price(takim_liste),
        ])

    # ── Tablo stili (etiketYazdir.py ile birebir) ─────────────────────────────
    table_style = TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  colors.HexColor("#D3D3D3")),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.black),
        ("ALIGN",          (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",          (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME",       (0, 0), (-1, 0),  _font(bold=True)),
        ("FONTSIZE",       (0, 0), (-1, 0),  16),
        ("BOTTOMPADDING",  (0, 0), (-1, 0),  12),
        ("BACKGROUND",     (0, 1), (-1, -1), colors.white),
        ("GRID",           (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F5F5F5"), colors.white]),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        # Takım satırları bold
        ("FONTNAME",       (0, product_count + 1), (-1, -1), _font(bold=True)),
        ("FONTSIZE",       (0, product_count + 1), (-1, -1), 14),
    ])

    col_widths  = [page_width - 425, 135, 125]
    row_heights = [30] + [17] * product_count
    if show_takim:
        row_heights += [20]

    table = Table(data, colWidths=col_widths, rowHeights=row_heights)
    table.setStyle(table_style)
    table.wrapOn(c, page_width, page_height)
    table.drawOn(c, 80, page_height - 180 - table._height)


# ─────────────────────────────────────────────────────────────────────────────
# Ana fonksiyon
# ─────────────────────────────────────────────────────────────────────────────

def generate_pdf(buffer: BytesIO, label_data: dict) -> None:
    """
    label_data: user_labels tablosundan gelen satır.
    {
      "kategori"  : "Oturma Grubu",
      "koleksiyon": "CALMERA",
      "takim_adi" : "",           # opsiyonel kombinasyon adı
      "urunler"   : [...],        # bireysel ürün listesi
      "takim_sku" : {...},        # set bilgisi (url, indirim_yuzde, fiyatlar)
    }
    PDF BytesIO stream'e yazılır, diske dokunulmaz.
    """
    _setup_fonts()

    page_width, page_height = landscape(A4)   # 841.89 × 595.27 pt
    c = canvas.Canvas(buffer, pagesize=landscape(A4))

    takim_sku = label_data.get("takim_sku", {}) or {}
    urunler   = label_data.get("urunler", []) or []

    # ── 1. Kesim çizgileri ────────────────────────────────────────────────────
    _draw_cutting_lines(c, page_width, page_height)

    # ── 2. Başlık resmi (Google Drive) ───────────────────────────────────────
    header_img = _load_image(ETIKET_BASLIK_URL)
    if header_img:
        c.drawImage(
            header_img, -10, page_height - 175,
            width=590, height=90, preserveAspectRatio=True,
        )

    # ── 3. QR Kodu ────────────────────────────────────────────────────────────
    qr_url = (
        takim_sku.get("urun_url")
        or takim_sku.get("url")
        or (urunler[0].get("urun_url") if urunler else None)
    )
    if qr_url:
        try:
            qr_img = _make_qr(qr_url)
            c.drawImage(
                qr_img, page_width - 185, page_height - 175,
                width=100, height=100,
            )
        except Exception:
            pass

    # ── 4. İndirim yüzdesi etiketi ────────────────────────────────────────────
    indirim_yuzde = int(takim_sku.get("indirim_yuzde") or 0)
    if not indirim_yuzde and urunler:
        liste_f = float(urunler[0].get("liste_fiyat") or 0)
        perak_f = float(urunler[0].get("perakende_fiyat") or 0)
        if liste_f and perak_f and liste_f != perak_f:
            indirim_yuzde = round((1 - perak_f / liste_f) * 100)
    if indirim_yuzde > 0:
        _draw_discount_badge(c, page_height, indirim_yuzde)

    # ── 5. Fiyat tablosu ──────────────────────────────────────────────────────
    _draw_table(c, label_data, page_width, page_height)

    # ── 6. Dipnot ─────────────────────────────────────────────────────────────
    tarih  = datetime.now().strftime("%d.%m.%Y")
    dipnot = (
        f"Fiyat Değişiklik Tarihi: {tarih} / "
        "Fiyatlara KDV dahildir / Üretim Yeri: TÜRKİYE"
    )
    c.setFont(_font(bold=False), 9)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(100, 80, dipnot)

    # ── 7. Yerli Üretim logosu (Google Drive) ────────────────────────────────
    logo_img = _load_image(YERLI_URETIM_URL)
    if logo_img:
        c.drawImage(logo_img, page_width - 180, 80, width=100, height=30)

    c.save()
