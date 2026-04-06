"""
dogtas.py — dogtas.com scraper (Supabase versiyonu)

Akış:
  1. Sitemap XML → tüm ürün URL'leri
  2. Her URL için: JSON-LD (primary) + HTML fallback
  3. Filtreleme + duplikasyon kuralları
  4. Supabase products tablosuna bulk upsert
"""

import asyncio
import aiohttp
import json
import re
import random
import logging
from datetime import datetime, timezone
from typing import Optional
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import requests as sync_requests

from core.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

CONCURRENT   = 2          # Aynı anda kaç istek
DELAY_MIN    = 1.5        # İstek arası min bekleme (jitter)
DELAY_MAX    = 3.0        # İstek arası max bekleme
BATCH_SIZE   = 200        # Supabase upsert batch boyutu

FILTER_CATEGORIES = {"Doğtaş Home"}   # Bu kategoriler kaydedilmez
FILTER_KEYWORDS   = [                 # Boş kategoride filtrele
    "Abajur", "Halı", "Biblo", "Kırlent", "Tablo", "Sarkıt",
    "Çerçeve", "Vazo", "Mum", "Obje", "Küp", "Saat",
    "Lambader", "Tabak", "Şamdan",
]


# ---------------------------------------------------------------------------
# Sitemap — URL Keşfi
# ---------------------------------------------------------------------------

def get_all_product_urls() -> list[str]:
    """
    Sitemap index'ten tüm ürün URL'lerini dinamik olarak topla.
    Önce dogtas.com/sitemap.xml → index parse.
    Başarısız olursa /sitemap/products/N.xml fallback (boş gelene kadar).
    """
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    ns      = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    all_urls: list[str] = []

    # --- Primary: sitemap index ---
    try:
        r = sync_requests.get("https://www.dogtas.com/sitemap.xml",
                              headers=headers, timeout=20)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            child_sitemaps = [
                loc.text.strip()
                for loc in root.findall(".//s:loc", ns)
                if loc.text and "products" in loc.text
            ]
            if child_sitemaps:
                logger.info(f"[Sitemap Index] {len(child_sitemaps)} alt sitemap bulundu")
                for sm_url in child_sitemaps:
                    urls = _fetch_sitemap_urls(sm_url, headers, ns)
                    logger.info(f"  {sm_url} → {len(urls)} URL")
                    all_urls.extend(urls)
                logger.info(f"Toplam {len(all_urls)} ürün URL'si (index)")
                return all_urls
    except Exception as e:
        logger.warning(f"[Sitemap Index] Hata: {e} — fallback'e geçiliyor")

    # --- Fallback: /sitemap/products/N.xml ---
    for i in range(1, 30):
        url  = f"https://www.dogtas.com/sitemap/products/{i}.xml"
        urls = _fetch_sitemap_urls(url, headers, ns)
        if not urls:
            logger.info(f"[Sitemap {i}] Boş — duruyoruz")
            break
        logger.info(f"[Sitemap {i}] {len(urls)} URL")
        all_urls.extend(urls)

    logger.info(f"Toplam {len(all_urls)} ürün URL'si (fallback)")
    return all_urls


def _fetch_sitemap_urls(url: str, headers: dict, ns: dict) -> list[str]:
    try:
        r = sync_requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        return [
            loc.text.strip()
            for loc in root.findall("s:url/s:loc", ns)
            if loc.text
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Fiyat Parse
# ---------------------------------------------------------------------------

def _parse_tr_price(text: str) -> Optional[float]:
    """'44.724,03 TL' → 44724.03"""
    clean = re.sub(r"[^\d,.]", "", text)
    if not clean:
        return None
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    elif "." in clean:
        if len(clean.split(".")[-1]) != 2:
            clean = clean.replace(".", "")
    try:
        val = float(clean)
        return val if 10 <= val <= 2_000_000 else None
    except ValueError:
        return None


def parse_prices(soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
    """
    Döner: (liste_fiyat, perakende_fiyat)

    Öncelik:
      1. JSON-LD offers.price  → liste (temiz decimal, parse gerekmez)
      2. HTML .discount-price  → perakende (yoksa = liste)
      3. HTML .sale-price      → fallback (her ikisi için)
    """
    liste    : Optional[float] = None
    perakende: Optional[float] = None

    # 1. JSON-LD (primary)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if data.get("@type") != "Product":
                continue
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0]
            p = offers.get("price")
            if p:
                liste = float(p)
            break
        except Exception:
            continue

    # 2. HTML indirimli fiyat
    el = soup.select_one(".discount-price, .new-sale-price")
    if el:
        perakende = _parse_tr_price(el.get_text(strip=True))

    # İndirim yoksa perakende = liste
    if perakende is None:
        perakende = liste

    # 3. Fallback: JSON-LD boşsa HTML'den liste
    if liste is None:
        el2 = soup.select_one(".sale-price.sale-variant-price, .sale-price.blc")
        if el2:
            liste = _parse_tr_price(el2.get_text(strip=True))
        perakende = perakende or liste

    return liste, perakende


# ---------------------------------------------------------------------------
# Ürün Parse
# ---------------------------------------------------------------------------

def parse_product(html: str, url: str) -> Optional[dict]:
    """HTML'den tam ürün verisini çıkar. Eksik zorunlu alan varsa None döner."""
    soup = BeautifulSoup(html, "html.parser")

    sku      : Optional[str]   = None
    ad       : Optional[str]   = None
    koleksiyon: str            = ""
    kategori  : str            = ""

    # --- JSON-LD (primary: sku, ad) ---
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if data.get("@type") != "Product":
                continue
            sku = data.get("sku")
            ad  = data.get("name")
            break
        except Exception:
            continue

    # --- HTML fallback: SKU ---
    if not sku:
        el = soup.find(class_="sku")
        if el:
            m = re.search(r"\d{6,}", el.get_text())
            if m:
                sku = m.group()

    # --- HTML fallback: Başlık → koleksiyon + urun_adi ---
    h1 = soup.find("h1", class_="title")
    urun_adi = ""
    if h1:
        span = h1.find("span")
        if span:
            koleksiyon = span.get_text(strip=True)
            sib = span.next_sibling
            urun_adi = sib.strip() if sib and isinstance(sib, str) else ""
        if not urun_adi:
            urun_adi = h1.get_text(strip=True)
        if not ad:
            ad = f"{koleksiyon} {urun_adi}".strip() if koleksiyon else urun_adi

    # Koleksiyon JSON-LD'den gelmediyse başlıktan türet
    if not koleksiyon and ad:
        parts = ad.split(" ", 1)
        koleksiyon = parts[0] if len(parts) > 1 else ""

    # --- Kategori (breadcrumb) ---
    breadcrumb = soup.find("ol", class_="breadcrumb")
    if breadcrumb:
        items = [
            li.get_text(strip=True)
            for li in breadcrumb.find_all("li")
            if li.get_text(strip=True) not in ("Ana Sayfa", "Home")
        ]
        if items:
            kategori = items[0]

    # --- Fiyatlar ---
    liste_fiyat, perakende_fiyat = parse_prices(soup)

    # --- Zorunlu alan kontrolü ---
    if not sku or not ad or liste_fiyat is None:
        return None

    return {
        "sku"             : sku,
        "urun_adi"        : urun_adi or ad,
        "urun_adi_tam"    : ad,
        "koleksiyon"      : koleksiyon,
        "kategori"        : kategori,
        "liste_fiyat"     : int(liste_fiyat),
        "perakende_fiyat" : int(perakende_fiyat) if perakende_fiyat else int(liste_fiyat),
        "urun_url"        : url,
        "scraped_at"      : datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Filtreleme + Duplikasyon
# ---------------------------------------------------------------------------

def should_filter(product: dict) -> bool:
    """True → ürünü kaydetme"""
    if product["kategori"] in FILTER_CATEGORIES:
        return True
    if not product["kategori"]:
        name = product["urun_adi_tam"].lower()
        if any(kw.lower() in name for kw in FILTER_KEYWORDS):
            return True
    return False


def apply_duplication(products: list[dict]) -> list[dict]:
    """Yemek Odası + (komodin/ayna) → Yatak Odası olarak da ekle"""
    result = []
    for p in products:
        result.append(p)
        if p["kategori"] == "Yemek Odası":
            name = p["urun_adi_tam"].lower()
            if "komodin" in name or "ayna" in name:
                dup = p.copy()
                dup["kategori"] = "Yatak Odası"
                result.append(dup)
    return result


# ---------------------------------------------------------------------------
# Async Fetch
# ---------------------------------------------------------------------------

async def fetch_url(
    session: aiohttp.ClientSession,
    sem    : asyncio.Semaphore,
    url    : str,
    attempt: int = 1,
) -> Optional[str]:
    """Tek URL'yi çek, retry ile. HTML döner veya None."""
    max_attempts = 3
    async with sem:
        await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        try:
            headers = {"User-Agent": random.choice(USER_AGENTS)}
            timeout = aiohttp.ClientTimeout(total=30 * attempt)
            async with session.get(url, headers=headers, timeout=timeout) as r:
                if r.status == 429:
                    # Rate limit — daha uzun bekle
                    wait = 10 * attempt
                    logger.warning(f"[429] {url} — {wait}s bekleniyor")
                    await asyncio.sleep(wait)
                    if attempt < max_attempts:
                        return await fetch_url(session, sem, url, attempt + 1)
                    return None
                if r.status != 200:
                    logger.debug(f"[{r.status}] {url}")
                    return None
                return await r.text()
        except asyncio.TimeoutError:
            if attempt < max_attempts:
                await asyncio.sleep(2 ** attempt)
                return await fetch_url(session, sem, url, attempt + 1)
            logger.error(f"[TIMEOUT] {url}")
            return None
        except Exception as e:
            if attempt < max_attempts:
                await asyncio.sleep(attempt * 1.5)
                return await fetch_url(session, sem, url, attempt + 1)
            logger.error(f"[ERR] {url}: {e}")
            return None


# ---------------------------------------------------------------------------
# Supabase Kayıt
# ---------------------------------------------------------------------------

def save_to_supabase(products: list[dict]) -> int:
    """Batch upsert — SKU primary key. Kaydedilen satır sayısını döner."""
    if not products:
        return 0

    sb = get_supabase()
    saved = 0

    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i : i + BATCH_SIZE]
        sb.table("products").upsert(batch, on_conflict="sku").execute()
        saved += len(batch)
        logger.info(f"[Supabase] {saved}/{len(products)} kaydedildi")

    return saved


# ---------------------------------------------------------------------------
# Ana Scraper
# ---------------------------------------------------------------------------

async def scrape_all(max_urls: Optional[int] = None) -> int:
    """
    Tüm siteyi tara → Supabase'e yaz.
    Döner: kaydedilen ürün sayısı.
    """
    # 1. URL'leri topla
    logger.info("Sitemap taranıyor...")
    urls = get_all_product_urls()
    if max_urls:
        urls = urls[:max_urls]
    logger.info(f"{len(urls)} URL taranacak")

    if not urls:
        logger.error("Hiç URL bulunamadı — sitemap erişilemiyor olabilir")
        return 0

    # 2. Async fetch — URL'yi task ile birlikte tut
    sem       = asyncio.Semaphore(CONCURRENT)
    products  : list[dict] = []
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=3)

    async def fetch_with_url(session, sem, url):
        html = await fetch_url(session, sem, url)
        return url, html

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_with_url(session, sem, url) for url in urls]
        total = len(tasks)

        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            url, html = await coro
            if not html:
                continue

            product = parse_product(html, url)
            if product and not should_filter(product):
                products.append(product)

            if i % 50 == 0:
                logger.info(f"  {i}/{total} işlendi — {len(products)} ürün bulundu")

    logger.info(f"Tarama bitti: {len(products)} ürün")

    # 3. Duplikasyon kuralları
    products = apply_duplication(products)
    logger.info(f"Duplikasyon sonrası: {len(products)} ürün")

    # 4. Supabase'e yaz
    saved = save_to_supabase(products)
    logger.info(f"Tamamlandı: {saved} ürün Supabase'e kaydedildi")
    return saved


def run(max_urls: Optional[int] = None) -> int:
    """Sync wrapper — admin panel ve CLI'dan çağırmak için"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
    return asyncio.run(scrape_all(max_urls))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
