-- ============================================================
-- RETAIL AGENT - MULTI-TENANT & ANALYTICS SCHEMA ADDITIONS
-- Add to existing schema.sql
-- ============================================================

-- ============================================================
-- TABLE 1: Shops (Multi-Tenant Support)
-- ============================================================
create table if not exists public.shops (
    id bigserial primary key,
    shop_name varchar(255) not null unique,
    shop_domain varchar(255),
    category varchar(100) not null,  -- e.g., 'electronics', 'fashion', 'appliances'
    description text,
    is_active boolean default true,
    created_at timestamptz default now(),
    last_active timestamptz default now()
);
create index if not exists idx_shops_active on public.shops(is_active);
create index if not exists idx_shops_category on public.shops(category);

-- ============================================================
-- TABLE 2: Product Metadata (Track first-seen, discovery status)
-- ============================================================
create table if not exists public.product_metadata (
    id bigserial primary key,
    shop_id bigint not null references public.shops(id),
    product_name varchar(500) not null,
    category varchar(100),
    first_seen timestamptz default now(),
    is_emerging boolean default true,  -- true if <24h old and ≥2 retailers
    emerging_detected_at timestamptz,
    trending_score float default 0,    -- based on retailer count
    unique(shop_id, product_name)
);
create index if not exists idx_product_meta_shop on public.product_metadata(shop_id);
create index if not exists idx_product_meta_emerging on public.product_metadata(is_emerging) where is_emerging = true;
create index if not exists idx_product_meta_first_seen on public.product_metadata(first_seen desc);

-- ============================================================
-- TABLE 3: Product Volatility Tracking
-- ============================================================
create table if not exists public.product_volatility (
    id bigserial primary key,
    shop_id bigint not null references public.shops(id),
    product_name varchar(500) not null,
    avg_price numeric(12,2),
    min_price numeric(12,2),
    max_price numeric(12,2),
    volatility_score float default 0,  -- std dev of prices
    price_variance float default 0,     -- variance metric
    sample_count integer default 0,     -- how many prices sampled
    last_calculated timestamptz default now(),
    unique(shop_id, product_name)
);
create index if not exists idx_volatility_shop on public.product_volatility(shop_id);
create index if not exists idx_volatility_score on public.product_volatility(volatility_score desc);

-- ============================================================
-- TABLE 4: Competitor Coverage Map
-- ============================================================
create table if not exists public.competitor_coverage (
    id bigserial primary key,
    shop_id bigint not null references public.shops(id),
    competitor_domain varchar(255) not null,
    category varchar(100) not null,
    product_count integer default 0,
    last_updated timestamptz default now(),
    market_share_percent float default 0,
    unique(shop_id, competitor_domain, category)
);
create index if not exists idx_coverage_shop_cat on public.competitor_coverage(shop_id, category);
create index if not exists idx_coverage_market_share on public.competitor_coverage(market_share_percent desc);

-- ============================================================
-- TABLE 5: Emerging Products Alert
-- ============================================================
create table if not exists public.emerging_products (
    id bigserial primary key,
    shop_id bigint not null references public.shops(id),
    product_name varchar(500) not null,
    first_seen timestamptz not null default now(),
    retailer_count integer default 0,
    retailer_list text,  -- comma-separated list of retailers
    category varchar(100),
    alert_sent boolean default false,
    alert_sent_at timestamptz,
    created_at timestamptz default now()
);
create index if not exists idx_emerging_shop on public.emerging_products(shop_id);
create index if not exists idx_emerging_unsent on public.emerging_products(alert_sent) where alert_sent = false;

-- ============================================================
-- TABLE 6: Price Drop Detection
-- ============================================================
create table if not exists public.price_drops (
    id bigserial primary key,
    shop_id bigint not null references public.shops(id),
    product_name varchar(500) not null,
    competitor_domain varchar(255) not null,
    old_price numeric(12,2) not null,
    new_price numeric(12,2) not null,
    price_drop numeric(12,2),
    drop_percent float,
    detected_at timestamptz default now(),
    alert_sent boolean default false
);
create index if not exists idx_price_drop_shop on public.price_drops(shop_id);
create index if not exists idx_price_drop_unsent on public.price_drops(alert_sent) where alert_sent = false;
create index if not exists idx_price_drop_time on public.price_drops(detected_at desc);

-- ============================================================
-- TABLE 7: Product Discovery Log (Track discovery process)
-- ============================================================
create table if not exists public.product_discovery_log (
    id bigserial primary key,
    shop_id bigint not null references public.shops(id),
    discovery_cycle integer,
    products_found integer default 0,
    new_products integer default 0,
    emerging_products integer default 0,
    price_drops_detected integer default 0,
    process_time_seconds integer,
    completed_at timestamptz default now()
);
create index if not exists idx_discovery_shop on public.product_discovery_log(shop_id);
create index if not exists idx_discovery_time on public.product_discovery_log(completed_at desc);

-- ============================================================
-- TABLE 8: Competitor Prices - Extended (add shop_id)
-- ============================================================
-- MIGRATION: If competitor_prices exists, add shop_id column
alter table if exists public.competitor_prices 
add column if not exists shop_id bigint references public.shops(id);

-- Index for shop-based queries
create index if not exists idx_competitor_prices_shop on public.competitor_prices(shop_id);
create index if not exists idx_competitor_prices_shop_category on public.competitor_prices(shop_id, category);

-- ============================================================
-- TABLE 9: Keyword Pool - Extended (shop_id for category-specific keywords)
-- ============================================================
alter table if exists public.keyword_pool 
add column if not exists shop_id bigint references public.shops(id),
add column if not exists product_category varchar(100);

-- Index for shop-specific keywords
create index if not exists idx_keywords_shop_category on public.keyword_pool(shop_id, product_category) where is_active = true;

-- ============================================================
-- HELPER FUNCTIONS FOR ANALYTICS
-- ============================================================

-- Function: Calculate Price Volatility
CREATE OR REPLACE FUNCTION public.calculate_price_volatility(p_shop_id bigint, p_product_name varchar)
RETURNS TABLE (
    avg_price numeric,
    min_price numeric,
    max_price numeric,
    volatility_score float,
    sample_count integer
) AS $$
DECLARE
    v_avg numeric;
    v_min numeric;
    v_max numeric;
    v_stddev float;
    v_count integer;
BEGIN
    SELECT 
        AVG(price), 
        MIN(price), 
        MAX(price),
        STDDEV_POP(price),
        COUNT(*)
    INTO v_avg, v_min, v_max, v_stddev, v_count
    FROM public.competitor_prices
    WHERE shop_id = p_shop_id AND product_name ILIKE p_product_name;
    
    RETURN QUERY SELECT v_avg, v_min, v_max, COALESCE(v_stddev, 0)::float, v_count;
END;
$$ language plpgsql;

-- Function: Detect Emerging Products
CREATE OR REPLACE FUNCTION public.detect_emerging_products(p_shop_id bigint)
RETURNS TABLE (
    product_name varchar,
    first_seen timestamptz,
    retailer_count integer,
    is_emerging boolean
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pm.product_name,
        pm.first_seen,
        COUNT(DISTINCT cp.domain)::integer as retailer_count,
        (pm.first_seen > now() - interval '24 hours' AND COUNT(DISTINCT cp.domain) >= 2)::boolean as is_emerging
    FROM public.product_metadata pm
    LEFT JOIN public.competitor_prices cp ON pm.shop_id = cp.shop_id AND pm.product_name = cp.product_name
    WHERE pm.shop_id = p_shop_id
    GROUP BY pm.product_name, pm.first_seen
    HAVING COUNT(DISTINCT cp.domain) >= 2;
END;
$$ language plpgsql;

-- Function: Calculate Competitor Coverage by Category
CREATE OR REPLACE FUNCTION public.calculate_competitor_coverage(p_shop_id bigint)
RETURNS void AS $$
BEGIN
    -- Update competitor_coverage table
    WITH coverage AS (
        SELECT 
            shop_id,
            domain,
            category,
            COUNT(DISTINCT product_name) as product_count
        FROM public.competitor_prices
        WHERE shop_id = p_shop_id
        GROUP BY shop_id, domain, category
    )
    INSERT INTO public.competitor_coverage (shop_id, competitor_domain, category, product_count, last_updated)
    SELECT shop_id, domain, category, product_count, now()
    FROM coverage
    ON CONFLICT (shop_id, competitor_domain, category) 
    DO UPDATE SET 
        product_count = EXCLUDED.product_count,
        last_updated = now();
END;
$$ language plpgsql;

-- Function: Detect Price Drops
CREATE OR REPLACE FUNCTION public.detect_price_drops(p_shop_id bigint, p_threshold_percent float default 5.0)
RETURNS TABLE (
    product_name varchar,
    competitor_domain varchar,
    old_price numeric,
    new_price numeric,
    drop_percent float
) AS $$
BEGIN
    RETURN QUERY
    WITH recent_prices AS (
        SELECT 
            product_name,
            domain,
            price,
            LAG(price) OVER (PARTITION BY product_name, domain ORDER BY scraped_at) as prev_price,
            scraped_at
        FROM public.competitor_prices
        WHERE shop_id = p_shop_id
        ORDER BY scraped_at DESC
        LIMIT 10000
    )
    SELECT 
        rp.product_name,
        rp.domain,
        rp.prev_price::numeric,
        rp.price,
        ((rp.prev_price - rp.price) / rp.prev_price * 100)::float as drop_percent
    FROM recent_prices rp
    WHERE rp.prev_price IS NOT NULL 
    AND rp.price < rp.prev_price
    AND ((rp.prev_price - rp.price) / rp.prev_price * 100) >= p_threshold_percent;
END;
$$ language plpgsql;

-- Function: Get Competitor Market Share by Category
CREATE OR REPLACE FUNCTION public.get_competitor_market_share(p_shop_id bigint, p_category varchar)
RETURNS TABLE (
    competitor_domain varchar,
    product_count integer,
    market_share_percent float
) AS $$
DECLARE
    v_total_count integer;
BEGIN
    SELECT COUNT(DISTINCT product_name)::integer INTO v_total_count
    FROM public.competitor_prices
    WHERE shop_id = p_shop_id AND category = p_category;
    
    RETURN QUERY
    SELECT 
        cp.domain,
        COUNT(DISTINCT cp.product_name)::integer as product_count,
        (COUNT(DISTINCT cp.product_name)::float / v_total_count * 100)::float as market_share_percent
    FROM public.competitor_prices cp
    WHERE cp.shop_id = p_shop_id AND cp.category = p_category
    GROUP BY cp.domain
    ORDER BY product_count DESC;
END;
$$ language plpgsql;

-- ============================================================
-- VERIFY INSTALLATION
-- ============================================================
SELECT 'Multi-tenant analytics schema added successfully' as status;
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('shops', 'product_metadata', 'product_volatility', 'competitor_coverage', 'emerging_products', 'price_drops', 'product_discovery_log')
ORDER BY table_name;
