# Etiket Sistemi — CLAUDE.md

## Proje Amacı
Doğtaş bayiilerine özel web tabanlı fiyat etiketi yönetim sistemi.
- dogtas.com'dan fiyatları çeker → Supabase'e yazar
- Bayiiler giriş yapar, ürün seçer, PDF etiket indirir
- Multi-tenant SaaS: her bayii kendi verisini görür
- Domain: etiket.gunesler.info

## Teknik Stack
- **Backend:** FastAPI (Python)
- **Database + Auth:** Supabase
- **Deploy:** Render.com (free tier, UptimeRobot ile uyanık)
- **PDF:** ReportLab (BytesIO — diske yazılmaz, stream edilir)
- **Template:** Jinja2

## Proje Yapısı
```
Etiket/
├── main.py                  # FastAPI uygulama giriş noktası
├── requirements.txt
├── render.yaml
├── .env                     # Asla commit edilmez
├── .gitignore
│
├── core/
│   ├── config.py            # Env değişkenleri (pydantic-settings)
│   ├── supabase_client.py   # Singleton Supabase bağlantısı
│   └── auth.py              # JWT middleware, abonelik kontrolü
│
├── routers/
│   ├── auth.py              # /auth/login /auth/logout /auth/register
│   ├── products.py          # /products (listeleme, filtre)
│   ├── labels.py            # /labels (kaydet, oku)
│   ├── pdf.py               # /pdf/generate → StreamingResponse
│   └── admin.py             # /admin (scraper tetikle, kullanıcılar)
│
├── scraper/
│   └── dogtas.py            # dogtas.com → Supabase (async, aiohttp)
│
├── pdf/
│   └── generator.py         # ReportLab PDF üretici
│
├── templates/               # Jinja2 HTML
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── products.html
│   └── admin.html
│
└── static/
    ├── css/style.css
    └── js/app.js
```

## Supabase Tabloları
```sql
products       -- Ürünler (scraper yazar, tüm authenticated okur)
user_labels    -- Kullanıcı etiket seçimleri (RLS: kendi verisini görür)
subscriptions  -- Abonelik bilgisi (trial / paid)
```

## Kritik İş Kuralları
- SKU formatı: 10 haneli, 3 ile başlayan (örn: 3120028065)
- Kaydedilen sütunlar: kategori, koleksiyon, sku, urun_adi_tam, urun_adi, liste_fiyat, perakende_fiyat, urun_url
- Filtreleme: kategori == "Doğtaş Home" → ürünü kaydetme
- Duplikasyon: kategori=="Yemek Odası" + (komodin/ayna) → "Yatak Odası" olarak da ekle
- PDF hiçbir zaman diske yazılmaz, BytesIO ile stream edilir
- Supabase free tier yeterli (300 bayi << 50K MAU)

## Fiyat Çekme Stratejisi
1. JSON-LD `offers.price` → liste fiyatı (temiz decimal, parse gerekmez)
2. HTML `.discount-price` → indirimli fiyat
3. İndirim yoksa indirimli = liste

## URL Keşfi
- Önce sitemap index: `dogtas.com/sitemap.xml`
- Fallback: `/sitemap/products/N.xml` (boş gelene kadar)

## Abonelik Modeli
- 14 gün ücretsiz trial
- Aylık 149 TL (iyzico ile tahsilat)
- Trial bitti → ödeme ekranı, ödeme yapılmadan PDF üretilmez

## Ortam Değişkenleri (.env)
```
SUPABASE_URL=
SUPABASE_KEY=          # service_role key (scraper için)
SUPABASE_ANON_KEY=     # anon key (frontend için)
SECRET_KEY=            # JWT imzalama (random 32 byte hex)
IYZICO_API_KEY=
IYZICO_SECRET_KEY=
```

## Deploy Notları
- Render free tier: UptimeRobot her 5 dakikada ping atar
- Render URL: https://etiket-app.onrender.com
- Custom domain: etiket.gunesler.info → Render'a yönlendir

## Geliştirme Kuralları
- Her router kendi prefix'ini taşır (app.include_router ile)
- Supabase bağlantısı singleton — get_supabase() ile al
- PDF endpoint'i her zaman StreamingResponse döner
- Auth middleware: Authorization header'dan JWT doğrula
- Admin endpoint'leri role="admin" kontrolü yapar
