-- ============================================================
-- Etiket Sistemi — Supabase Kurulum SQL
-- Supabase Dashboard → SQL Editor'da çalıştır
-- ============================================================

-- ============================================================
-- 1. TABLOLAR
-- ============================================================

-- Ürünler (scraper yazar, tüm authenticated kullanıcılar okur)
CREATE TABLE IF NOT EXISTS products (
    sku              TEXT PRIMARY KEY,
    urun_adi         TEXT,
    urun_adi_tam     TEXT NOT NULL,
    koleksiyon       TEXT DEFAULT '',
    kategori         TEXT DEFAULT '',
    liste_fiyat      NUMERIC,
    perakende_fiyat  NUMERIC,
    urun_url         TEXT,
    scraped_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Kullanıcı etiket seçimleri (her kullanıcı kendi satırlarını görür)
CREATE TABLE IF NOT EXISTS user_labels (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    kategori     TEXT NOT NULL,
    koleksiyon   TEXT NOT NULL,
    takim_adi    TEXT DEFAULT '',
    urunler      JSONB DEFAULT '[]',   -- [{sku, urun_adi_tam, liste_fiyat, perakende_fiyat, miktar}]
    takim_sku    JSONB DEFAULT '{}',   -- {sku, urun_adi_tam, liste_fiyat, perakende_fiyat, indirim_yuzde}
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, kategori, koleksiyon)
);

-- Abonelikler
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id      UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    bayii_adi    TEXT DEFAULT '',
    plan         TEXT DEFAULT 'trial' CHECK (plan IN ('trial', 'paid', 'cancelled')),
    trial_ends   TIMESTAMPTZ DEFAULT NOW() + INTERVAL '14 days',
    paid_until   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 2. INDEX'LER (Hız için)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_products_kategori   ON products(kategori);
CREATE INDEX IF NOT EXISTS idx_products_koleksiyon ON products(koleksiyon);
CREATE INDEX IF NOT EXISTS idx_products_scraped_at ON products(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_labels_user_id ON user_labels(user_id);

-- ============================================================
-- 3. ROW LEVEL SECURITY
-- ============================================================

-- Products: herkes okur, sadece service_role yazar
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

CREATE POLICY "products_select" ON products
    FOR SELECT USING (auth.role() = 'authenticated');

-- service_role RLS'i bypass eder — scraper doğrudan yazar

-- user_labels: kullanıcı sadece kendi satırlarını görür/yazar
ALTER TABLE user_labels ENABLE ROW LEVEL SECURITY;

CREATE POLICY "labels_select" ON user_labels
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "labels_insert" ON user_labels
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "labels_update" ON user_labels
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "labels_delete" ON user_labels
    FOR DELETE USING (auth.uid() = user_id);

-- subscriptions: kullanıcı kendi aboneliğini görür
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "subscriptions_select" ON subscriptions
    FOR SELECT USING (auth.uid() = user_id);

-- ============================================================
-- 4. OTOMATİK updated_at TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_labels_updated_at
    BEFORE UPDATE ON user_labels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- 5. YENİ KULLANICI KAYIT TRIGGER
-- Kullanıcı kayıt olunca subscriptions tablosuna otomatik ekle
-- ============================================================

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.subscriptions (user_id, bayii_adi, plan, trial_ends)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'bayii_adi', ''),
        'trial',
        NOW() + INTERVAL '14 days'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================================
-- 6. ADMIN KULLANICISI (İlk kurulumda çalıştır)
-- Dashboard → Authentication → Users'dan manuel ekle,
-- sonra aşağıdaki komutu o kullanıcının ID'siyle çalıştır:
-- ============================================================

-- UPDATE auth.users SET raw_app_meta_data = raw_app_meta_data || '{"role": "admin"}'
-- WHERE email = 'admin@gunesler.info';
