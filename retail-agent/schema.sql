-- ============================================================
-- RETAIL PRICE MONITOR SCHEMA
-- Run this in Supabase SQL Editor:
-- https://supabase.com/dashboard/project/hqphepiyariufzvtvfre/sql/new
-- ============================================================

-- TABLE 1: Processed URLs (O(1) hash-based dedup)
create table if not exists public.processed_urls (
    id bigserial primary key,
    url_hash varchar(64) unique not null,
    canonical_url text not null,
    domain varchar(255) not null,
    processed_at timestamptz default now(),
    score integer default 0,
    spam_score integer default 0,
    is_offer boolean default false
);
create unique index if not exists idx_processed_hash on public.processed_urls(url_hash);
create index if not exists idx_processed_time on public.processed_urls(processed_at);
create index if not exists idx_processed_domain on public.processed_urls(domain);

-- TABLE 2: Archived URLs
create table if not exists public.archived_urls (
    id bigserial primary key,
    url_hash varchar(64) not null,
    canonical_url text not null,
    domain varchar(255) not null,
    processed_at timestamptz,
    score integer default 0,
    archived_at timestamptz default now()
);
create index if not exists idx_archived_hash on public.archived_urls(url_hash);

-- TABLE 3: Domain Trust Scoring
create table if not exists public.domains (
    domain varchar(255) primary key,
    trust_score float default 0,
    last_seen timestamptz default now(),
    offer_count integer default 0,
    spam_count integer default 0,
    is_blacklisted boolean default false
);
create index if not exists idx_domains_trust on public.domains(trust_score);
create index if not exists idx_domains_blacklist on public.domains(is_blacklisted) where is_blacklisted = true;

-- TABLE 4: Competitor Prices (REPLACES "offers" table)
create table if not exists public.competitor_prices (
    id bigserial primary key,
    domain varchar(255) not null references public.domains(domain),
    url text not null,
    product_name varchar(500),
    price numeric(12,2),
    currency varchar(10) default 'EUR',
    competitor_name varchar(255),
    category varchar(100),
    scraped_at timestamptz default now()
);
create index if not exists idx_prices_domain on public.competitor_prices(domain);
create index if not exists idx_prices_product on public.competitor_prices(product_name);
create index if not exists idx_prices_scraped on public.competitor_prices(scraped_at);
create index if not exists idx_prices_category on public.competitor_prices(category);

-- TABLE 5: Our Products (your own product catalog for comparison)
create table if not exists public.our_products (
    id bigserial primary key,
    product_name varchar(500) not null,
    our_price numeric(12,2) not null,
    category varchar(100),
    sku varchar(100) unique,
    is_active boolean default true,
    created_at timestamptz default now()
);

-- TABLE 6: Price Alerts (triggered when competitor price differs significantly)
create table if not exists public.price_alerts (
    id bigserial primary key,
    our_product_id bigint references public.our_products(id),
    competitor_price_id bigint references public.competitor_prices(id),
    alert_type varchar(50) not null,
    our_price numeric(12,2),
    competitor_price numeric(12,2),
    price_difference numeric(12,2),
    percentage_diff numeric(6,2),
    suggested_action text,
    is_resolved boolean default false,
    created_at timestamptz default now()
);
create index if not exists idx_alerts_unresolved on public.price_alerts(is_resolved) where is_resolved = false;
create index if not exists idx_alerts_type on public.price_alerts(alert_type);

-- TABLE 7: Keyword Pool (Max 500 terms)
create table if not exists public.keyword_pool (
    term varchar(100) primary key,
    category varchar(20) not null check (category in ('core', 'learned')),
    yield_score float default 1.0,
    usage_count integer default 0,
    last_used timestamptz default now(),
    is_active boolean default true
);
create index if not exists idx_keywords_active on public.keyword_pool(is_active, category) where is_active = true;

-- TABLE 8: Co-occurrence Learning
create table if not exists public.learned_terms (
    id bigserial primary key,
    term varchar(200) not null,
    context varchar(100),
    frequency integer default 1,
    discovered_at timestamptz default now(),
    promoted boolean default false,
    unique(term, context)
);
create index if not exists idx_learned_freq on public.learned_terms(frequency desc) where promoted = false;

-- TABLE 9: System Stats
create table if not exists public.system_stats (
    id bigserial primary key,
    cycle_number integer,
    urls_discovered integer default 0,
    urls_processed integer default 0,
    offers_found integer default 0,
    errors_count integer default 0,
    runtime_seconds integer,
    recorded_at timestamptz default now()
);

-- TABLE 10: Price History (tracks price changes over time)
create table if not exists public.price_history (
    id bigserial primary key,
    domain varchar(255) not null,
    product_name varchar(500),
    old_price numeric(12,2),
    new_price numeric(12,2),
    change_percent numeric(6,2),
    recorded_at timestamptz default now()
);
create index if not exists idx_history_product on public.price_history(product_name);
create index if not exists idx_history_time on public.price_history(recorded_at);

-- ============================================================
-- SEED RETAIL KEYWORDS
-- ============================================================
insert into public.keyword_pool (term, category, yield_score, is_active) values
-- Price-comparison phrases
('competitor price', 'core', 1.5, true),
('price comparison', 'core', 1.5, true),
('product pricing', 'core', 1.5, true),
('buy online', 'core', 1.0, true),
('shop online', 'core', 1.0, true),
('best price', 'core', 1.5, true),
('lowest price', 'core', 1.5, true),
('price drop', 'core', 1.0, true),
('sale', 'core', 1.0, true),
('clearance', 'core', 1.0, true),
-- Price-related
('price', 'core', 1.0, true),
('cost', 'core', 1.0, true),
('discount', 'core', 1.0, true),
('offer', 'core', 1.0, true),
('deal', 'core', 1.0, true),
('promotion', 'core', 1.0, true),
('coupon', 'core', 1.0, true),
('savings', 'core', 1.0, true),
-- Product categories
('electronics', 'core', 1.0, true),
('laptop', 'core', 1.0, true),
('smartphone', 'core', 1.0, true),
('headphones', 'core', 1.0, true),
('tablet', 'core', 1.0, true),
('camera', 'core', 1.0, true),
('monitor', 'core', 1.0, true),
('keyboard', 'core', 1.0, true),
('mouse', 'core', 1.0, true),
('speaker', 'core', 1.0, true)
on conflict (term) do nothing;

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

CREATE OR REPLACE FUNCTION public.get_stats_summary()
RETURNS TABLE (total_urls bigint, total_prices bigint, total_domains bigint, active_keywords bigint, blacklisted bigint) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (SELECT COUNT(*) FROM public.processed_urls),
        (SELECT COUNT(*) FROM public.competitor_prices),
        (SELECT COUNT(*) FROM public.domains),
        (SELECT COUNT(*) FROM public.keyword_pool WHERE is_active = true),
        (SELECT COUNT(*) FROM public.domains WHERE is_blacklisted = true);
END;
$$ language plpgsql;

CREATE OR REPLACE FUNCTION public.archive_old_urls(cutoff_days int default 90)
RETURNS int AS $$
DECLARE
    archived_count int;
BEGIN
    INSERT INTO public.archived_urls (url_hash, canonical_url, domain, processed_at, score)
    SELECT url_hash, canonical_url, domain, processed_at, score
    FROM public.processed_urls
    WHERE processed_at < now() - (cutoff_days || ' days')::interval;
    GET DIAGNOSTICS archived_count = ROW_COUNT;
    DELETE FROM public.processed_urls WHERE processed_at < now() - (cutoff_days || ' days')::interval;
    RETURN archived_count;
END;
$$ language plpgsql;

CREATE OR REPLACE FUNCTION public.apply_trust_decay()
RETURNS void AS $$
BEGIN
    UPDATE public.domains SET trust_score = GREATEST(0, trust_score * 0.95) WHERE trust_score > 0;
END;
$$ language plpgsql;

-- VERIFY
SELECT 'Retail schema created successfully' as status;
SELECT COUNT(*) as keywords_seeded FROM public.keyword_pool;
