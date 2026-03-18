# Retail PriceGuard — Technical Architecture & Script

> A comprehensive technical walkthrough of the autonomous competitor price monitoring system built with React, FastAPI, DuckDuckGo scraping, NVIDIA LLM reasoning, and Supabase.

---

## 1. System Architecture Overview

```
+======================================================================+
|                        RETAIL PRICEGUARD                             |
|                  Autonomous Competitor Monitoring                     |
+======================================================================+

  BROWSER (User)
      |
      |  http://localhost:5173
      v
+------------------+       Vite Proxy /api/*       +-------------------+
|                  | ---------------------------->  |                   |
|   REACT FRONTEND |       localhost:8000           |  FASTAPI BACKEND  |
|   (Vite 7.3.1)  | <----------------------------  |  (Python 3.12)    |
|                  |         JSON responses         |                   |
+------------------+                                +-------------------+
      |                                                   |    |    |
      |  Components:                              +-------+    |    +--------+
      |  - SetupView                              |            |             |
      |  - DashboardView                          v            v             v
      |    - OverviewTab (+ Inventory)    +-----------+  +-----------+  +----------+
      |    - RadarTab                     | SUPABASE  |  |  AGENT    |  |  NVIDIA  |
      |    - VolatilityTab                | (Postgres)|  |  PIPELINE |  |   LLM    |
      |    - DropsTab                     |           |  |           |  |  (Kimi   |
      |    - BusinessAdvisorTab (Chat)    | 17 tables |  | Scraper   |  |   K2)    |
      |    - AlertsTab                    +-----------+  | Fetcher   |  +----------+
      |  - AgentSidebar                                  | Scorer    |
      |                                                  | Canonicalizer
      |  Hooks:                                          +-----------+
      |  - useDashboard.js                                     |
      |                                                        v
      |                                               +---------------+
      |                                               |  DuckDuckGo   |
      |                                               |  (Web Search) |
      |                                               +---------------+
```

---

## 2. Data Flow — End-to-End

```
USER                   FRONTEND                  BACKEND                   EXTERNAL
 |                        |                         |                         |
 |  1. Pick domain,       |                         |                         |
 |     enter shop name    |                         |                         |
 |  --------------------> |                         |                         |
 |                        |  2. POST /api/shop/setup |                         |
 |                        |  ----------------------> |                         |
 |                        |                         |  3. Create shop in       |
 |                        |                         |     Supabase             |
 |                        |                         |  ----+                   |
 |                        |                         |      |                   |
 |                        |                         |  4. Init category        |
 |                        |                         |     keywords             |
 |                        |                         |  ----+                   |
 |                        |                         |      |                   |
 |                        |                         |  5. Quick Scan           |
 |                        |                         |  ----- DuckDuckGo -----> |
 |                        |                         |  <---- URLs ------------ |
 |                        |                         |  ----- Fetch pages ----> |
 |                        |                         |  <---- HTML ------------ |
 |                        |                         |  6. Score + Extract      |
 |                        |                         |     prices               |
 |                        |                         |  7. Store in Supabase    |
 |                        |                         |  8. LLM enrich          |
 |                        |                         |  ----- NVIDIA LLM ----> |
 |                        |                         |  <---- Insights -------- |
 |                        |  9. Return scraped data  |                         |
 |                        |  <--------------------- |                         |
 |  10. Render dashboard  |                         |                         |
 |  <-------------------- |                         |                         |
 |                        |                         |  11. Background agent    |
 |                        |                         |      starts (ReAct loop)|
 |                        |                         |      continuous scanning |
```

---

## 3. Technology Stack

```
+-----------------------------+------------------------------------+
| Layer                       | Technology                         |
+-----------------------------+------------------------------------+
| Frontend Framework          | React 19.2 + JSX                   |
| Build Tool                  | Vite 7.3.1                         |
| Icons                       | Lucide React 0.577                 |
| Styling                     | Vanilla CSS (1900+ lines)          |
| API Server                  | FastAPI + Uvicorn                  |
| Language                    | Python 3.12                        |
| Database                    | Supabase (hosted PostgreSQL)       |
| LLM Provider                | NVIDIA AI Endpoints                |
| LLM Model                   | Moonshotai Kimi K2 Instruct        |
| Web Search                  | DuckDuckGo HTML Scraper            |
| HTTP Client                 | aiohttp (async, 2-3 concurrency)   |
| HTML Parser                 | BeautifulSoup 4                    |
| LLM SDK                     | LangChain NVIDIA AI Endpoints      |
| Proxy                       | Vite dev server (/api -> :8000)    |
+-----------------------------+------------------------------------+
```

---

## 4. Frontend Architecture

### 4.1 Component Tree

```
App.jsx
 |
 +-- useDashboard.js (hook — ALL state lives here)
 |
 +-- [step === 'setup']
 |    |
 |    +-- SetupView.jsx
 |         - Domain picker (5 cards: Electronics, Fashion, Appliances, Gaming, Custom)
 |         - Shop name input
 |         - Custom description textarea (for Custom domain)
 |         - "Deploy Agent" button -> POST /api/shop/setup
 |
 +-- [step === 'dashboard']
      |
      +-- DashboardView.jsx
           |
           +-- Top Navigation Bar (shop name, LIVE AGENT badge, scan button)
           |
           +-- Tab Switcher (6 tabs)
           |    |
           |    +-- OverviewTab.jsx -------- Scanned products table + Inventory CRUD
           |    +-- RadarTab.jsx ----------- Emerging product radar (isNew === true)
           |    +-- VolatilityTab.jsx ------ Price activity / volatility chart
           |    +-- DropsTab.jsx ----------- Price drops ranked by % drop
           |    +-- BusinessAdvisorTab.jsx - LLM chatbot (Kimi K2)
           |    +-- AlertsTab.jsx ---------- Inventory-aware alerts
           |
           +-- AgentSidebar.jsx
                - Agent status indicator
                - Smart Whisper (strategic insight)
                - Trending items list
                - Market share breakdown
```

### 4.2 State Management — `useDashboard.js`

All application state is centralized in a single custom hook. No external state library is used.

```
useDashboard()
 |
 +-- Core State
 |    step           : 'setup' | 'dashboard'
 |    shopName       : string
 |    selectedDomain : { id, name, icon, keywords }
 |    shopId         : number (from Supabase)
 |    scrapedData    : array  (real competitor prices)
 |    inventory      : array  (user's inventory from DB)
 |    isScanning     : boolean
 |    lastScan       : string (timestamp)
 |    activeTab      : string
 |
 +-- Derived Metrics (useMemo)
 |    emergingProducts : scrapedData.filter(d => d.isNew)
 |    priceDrops       : grouped by product, cheapest vs average
 |    marketShare      : competitor listing counts
 |    alerts           : inventory-aware rules (5 alert types)
 |
 +-- Actions
      handleStartSetup() : POST /api/shop/setup -> sets shopId, scrapedData
      runScan()          : POST /api/scan/{shopId} -> refreshes scrapedData
```

### 4.3 Inventory Management — Two-Step Flow

```
USER TYPES CSV              PREVIEW TABLE               SUPABASE
      |                          |                          |
      | "iPhone 16, 25"          |                          |
      | "Samsung S24, 10, url"   |                          |
      |                          |                          |
      |-- [Add to Table] -----> |                          |
      |                         | Shows rows with           |
      |                         | yellow highlight           |
      |                         | + orange unsaved dot       |
      |                         |                           |
      |                         |-- [Save 2 Items] ------> |
      |                         |                          | INSERT rows
      |                         |                          |
      |                         | <--- refresh ----------- |
      |                         | Rows turn white           |
      |                         | (saved)                   |
```

**Key design decision**: CSV parsing is local-only. Items appear instantly in the table as "unsaved preview" rows. Only when the user clicks "Save" do they persist to the database. This gives immediate visual feedback without network delay.

### 4.4 Alert System — 5 Rule Types

The alert engine in `useDashboard.js` uses real inventory data (not simulated):

| Rule | Type | Trigger Condition | Example |
|------|------|-------------------|---------|
| A | `urgent` | High volatility (>5%) + low stock (<12 units) | "iPhone 16 surging, only 3 units left" |
| B | `warning` | Low volatility (<3%) + high stock (>30 units) | "Samsung S24 overstocked at 45 units" |
| C | `info` | Trending product NOT in inventory | "PS5 trending but you don't stock it" |
| D | `urgent` | Any inventory item < 5 units | "3 products critically low" |
| E | `info` | Amazon/Flipkart new listing + high volatility | "MacBook trending on Amazon.in" |

Alerts only generate when inventory data exists. An empty inventory produces zero alerts (no fake data).

---

## 5. Backend Architecture

### 5.1 Server Structure — `backend/server.py`

```
server.py (~1600 lines)
 |
 +-- IMPORTS & PATH SETUP
 |    - sys.path.insert(0, ../retail-agent/)
 |    - Load .env from retail-agent/
 |
 +-- AGENT MODULE IMPORTS
 |    - SupabaseStore, ShopManager, CategoryKeywordManager
 |    - AnalyticsEngine, DuckDuckGoScraper, ContentFetcher
 |    - ContentExtractor, MultiFactorScorer, URLCanonicalizer
 |    - AgentLLM (NVIDIA Kimi K2)
 |
 +-- SHARED STATE
 |    store          : SupabaseStore instance
 |    shop_mgr       : ShopManager instance
 |    keyword_mgr    : CategoryKeywordManager
 |    analytics      : AnalyticsEngine
 |    _agent_tasks   : Dict[shop_id -> asyncio.Task]
 |    _shop_cache    : Dict[shop_id -> shop config]
 |
 +-- LLM UTILITIES
 |    llm_generate_custom_keywords()  — LLM generates keywords for custom domains
 |    llm_enrich_products()           — LLM adds market insights to products
 |    llm_chat_response()             — LLM chatbot with market + inventory context
 |
 +-- STARTUP EVENT
 |    - Init all agent modules
 |    - Initialize keyword pool
 |    - Purge null/zero price entries
 |    - Ensure shop_inventory table exists
 |
 +-- DATA TRANSFORMATION
 |    read_frontend_data()  — Supabase rows -> frontend { id, name, price, ... }
 |
 +-- CORE FUNCTIONS
 |    run_quick_scan()      — 3 DuckDuckGo searches, real scraping
 |    run_agent_background()— Continuous ReAct agent loop
 |    run_analytics_update()— Volatility, drops, emerging products
 |    ensure_domain_exists()— Seed known competitor domains
 |
 +-- API ENDPOINTS (17 routes)
      POST /api/shop/setup
      POST /api/scan/{shop_id}
      GET  /api/data/{shop_id}
      POST /api/agent/start/{shop_id}
      GET  /api/agent/status/{shop_id}
      POST /api/agent/stop/{shop_id}
      GET  /api/analytics/volatility/{shop_id}
      GET  /api/analytics/emerging/{shop_id}
      GET  /api/analytics/drops/{shop_id}
      GET  /api/analytics/coverage/{shop_id}
      GET  /api/inventory/{shop_id}
      POST /api/inventory/{shop_id}
      PUT  /api/inventory/{shop_id}/{item_id}
      DELETE /api/inventory/{shop_id}/{item_id}
      POST /api/chat
      GET  /api/health
      GET  /api/stats
```

### 5.2 API Endpoint Reference

```
+------------------------------------------------------------------+
| METHOD | PATH                          | PURPOSE                  |
+--------+-------------------------------+--------------------------+
| POST   | /api/shop/setup               | Create shop, scan, start |
|        |                               | agent, return data       |
+--------+-------------------------------+--------------------------+
| POST   | /api/scan/{shop_id}           | Trigger manual re-scan   |
+--------+-------------------------------+--------------------------+
| GET    | /api/data/{shop_id}           | Read current prices      |
+--------+-------------------------------+--------------------------+
| POST   | /api/agent/start/{shop_id}    | Start background agent   |
+--------+-------------------------------+--------------------------+
| GET    | /api/agent/status/{shop_id}   | Check agent status       |
+--------+-------------------------------+--------------------------+
| POST   | /api/agent/stop/{shop_id}     | Stop background agent    |
+--------+-------------------------------+--------------------------+
| GET    | /api/analytics/volatility/..  | Price volatility data    |
+--------+-------------------------------+--------------------------+
| GET    | /api/analytics/emerging/..    | Emerging products        |
+--------+-------------------------------+--------------------------+
| GET    | /api/analytics/drops/..       | Price drops              |
+--------+-------------------------------+--------------------------+
| GET    | /api/analytics/coverage/..    | Competitor coverage      |
+--------+-------------------------------+--------------------------+
| GET    | /api/inventory/{shop_id}      | List inventory items     |
+--------+-------------------------------+--------------------------+
| POST   | /api/inventory/{shop_id}      | Bulk add (CSV or JSON)   |
+--------+-------------------------------+--------------------------+
| PUT    | /api/inventory/{id}/{item_id} | Update item fields       |
+--------+-------------------------------+--------------------------+
| DELETE | /api/inventory/{id}/{item_id} | Delete inventory item    |
+--------+-------------------------------+--------------------------+
| POST   | /api/chat                     | LLM chatbot endpoint     |
+--------+-------------------------------+--------------------------+
| GET    | /api/health                   | Health check             |
+--------+-------------------------------+--------------------------+
| GET    | /api/stats                    | System-wide statistics   |
+--------+-------------------------------+--------------------------+
```

---

## 6. Agent Pipeline — The Scraping Engine

### 6.1 Pipeline Architecture

```
                      AGENT PIPELINE
                      ==============

  [1] KEYWORD SELECTION
       |
       | CategoryKeywordManager picks 3 keywords
       | based on domain (electronics, fashion, gaming...)
       | or LLM-generated keywords for custom domains
       v
  [2] WEB SEARCH (DuckDuckGoScraper)
       |
       | Sends query: "{keyword} price buy online India"
       | Parses DuckDuckGo HTML response
       | Returns up to 10 URLs per query
       v
  [3] CONTENT FETCHING (ContentFetcher)
       |
       | aiohttp with 2-3 concurrency
       | 1 req/sec rate limit per worker
       | Retry with exponential backoff
       | Skips non-HTTPS, follows redirects
       v
  [4] CONTENT EXTRACTION (ContentExtractor / BeautifulSoup)
       |
       | Strips scripts, styles, nav, footer
       | Extracts: title, description, body text
       | Hard rejects: >100 outbound links (spam)
       v
  [5] MULTI-FACTOR SCORING (MultiFactorScorer)
       |
       |  Factors (deterministic, no LLM):
       |  + Entity match       (retail vocabulary)
       |  + Benefit match      (price signal words)
       |  + Program phrase     (price comparison patterns)
       |  + Trusted domain     (amazon.in, flipkart, croma...)
       |  - Spam keywords      (SEO spam, affiliate)
       |  - Excess outbound    (directory/listicle)
       |
       |  Price extraction:
       |  - Regex patterns for ₹, Rs., INR, $, €, £
       |  - Indian comma grouping (₹1,29,990)
       |  - Sanity bound: ₹0 < price < ₹1,00,00,000
       v
  [6] URL CANONICALIZATION (URLCanonicalizer)
       |
       | SHA256 hash of normalized URL
       | Deduplication via processed_urls table
       v
  [7] STORAGE (SupabaseStore)
       |
       | Insert into competitor_prices
       | Gate: skip if price <= 0 or null
       | Includes shop_id for multi-tenant isolation
       v
  [8] LLM ENRICHMENT (Optional)
       |
       | NVIDIA Kimi K2 adds:
       | - market_insight (analytical note)
       | - price_assessment (competitive?)
       | - recommendation (stock/pricing advice)
       v
  [DONE] Data ready for frontend
```

### 6.2 Agent Reasoning Core — ReAct Loop

The background agent runs continuously after shop setup:

```
  +---> OBSERVE
  |      |  Read database stats
  |      |  Check processed URL count
  |      |  Review recent discoveries
  |      v
  |    REASON (LLM)
  |      |  "Which tool should I use next?"
  |      |  "What query will yield new products?"
  |      |  Considers: coverage gaps, keyword freshness,
  |      |  domain trust scores, discovery yield
  |      v
  |    ACT
  |      |  Execute chosen tool:
  |      |  - search_web (primary)
  |      |  - expand_keywords (when yield is low)
  |      |  - deep_crawl (on high-trust domains)
  |      |  - browse_page (specific URLs)
  |      |  - query_stats (check progress)
  |      v
  |    EVALUATE
  |      |  Did we find new prices?
  |      |  Update keyword effectiveness
  |      |  Adjust strategy if needed
  |      |
  +------+  (loop continues every 60 seconds)
```

### 6.3 Scoring Deep Dive

```
PAGE SCORE CALCULATION:
=====================

  Base Score = 0

  + Entity Matches   (e.g., "price", "buy", "cart")    → +2 each (max 20)
  + Benefit Matches  (e.g., "discount", "offer")       → +3 each (max 15)
  + Program Phrases  (e.g., "compare prices")          → +5 each (max 10)
  + Domain Bonus     (amazon.in → +15, flipkart → +15) → max 15

  - Spam Keywords    (e.g., "SEO", "affiliate")        → -3 each
  - Outbound Links   (>100 links → hard reject)
  - Listicle Pattern (>30 items → -10)

  THRESHOLD: score >= 8 → valid pricing page
  SPAM GATE: spam_score > 10 → rejected

  PRICE EXTRACTION:
  - Pattern match: ₹79,990 / Rs. 1,29,990 / $99.99
  - Sanity: 0 < price < 10,000,000
  - Zero/null prices: BLOCKED at 3 layers
    1. Insert gate (run_quick_scan + agent_core)
    2. Read filter (Supabase query: .gt("price", 0))
    3. Startup purge (DELETE WHERE price <= 0)
```

---

## 7. Multi-Tenant Architecture

### 7.1 Shop Isolation

```
  USER A: "GameVault" (Gaming)         USER B: "StyleHub" (Fashion)
       |                                    |
       v                                    v
  shop_id = 5                          shop_id = 8
  keywords: RTX 4080, PS5...          keywords: Nike, Levis...
       |                                    |
       v                                    v
  competitor_prices                    competitor_prices
  WHERE shop_id = 5                    WHERE shop_id = 8
  (PS5, keyboards, monitors)          (Jordans, jeans, watches)
       |                                    |
       v                                    v
  shop_inventory                       shop_inventory
  WHERE shop_id = 5                    WHERE shop_id = 8
  (user's gaming stock)                (user's fashion stock)
```

**Isolation rules:**
- Same shop name + same domain → reuses existing shop (idempotent)
- Same shop name + different domain → creates NEW shop
- All queries filter by `shop_id`
- Keyword pool is per-shop
- Background agent is per-shop (separate `asyncio.Task`)

### 7.2 Domain-Aware Keyword Strategy

```
  +---------------------+
  | Frontend sends      |
  | domain + keywords   |
  +---------------------+
           |
           v
  +---------------------+
  | CategoryKeyword     |     Built-in categories:
  | Manager             |     - Electronics (16 product + 8 competitor keywords)
  |                     |     - Fashion (16 + 8)
  | Picks keywords      |     - Appliances (16 + 8)
  | from category pool  |     - Gaming (16 + 8)
  +---------------------+
           |
           v
  +---------------------+
  | For "Custom" domain |
  | LLM generates       |
  | 30-50 keywords from |
  | user's description  |
  +---------------------+
           |
           v
  +---------------------+
  | Quick Scan uses     |
  | frontend keywords   |
  | FIRST, then falls   |
  | back to category    |
  | keywords            |
  +---------------------+
```

---

## 8. Database Schema

### 8.1 Supabase Tables (17 total)

```
+========================+==========================================+
|  TABLE                 |  PURPOSE                                 |
+========================+==========================================+
|  BASE TABLES (10)                                                 |
+------------------------+------------------------------------------+
|  domains               |  Known competitor domains + trust scores |
|  processed_urls        |  URL dedup (SHA256 hash index)           |
|  archived_urls         |  Expired/stale URLs                      |
|  competitor_prices     |  Scraped prices (core data, has shop_id) |
|  our_products          |  Reference products                      |
|  price_alerts          |  System-generated alerts                 |
|  keyword_pool          |  Active keywords (per shop_id)           |
|  learned_terms         |  Auto-discovered keywords                |
|  system_stats          |  Agent run statistics                    |
|  price_history         |  Historical price tracking               |
+------------------------+------------------------------------------+
|  ANALYTICS TABLES (6)                                             |
+------------------------+------------------------------------------+
|  shops                 |  Multi-tenant shop registry              |
|  product_metadata      |  First-seen dates, emerging flags        |
|  product_volatility    |  Price std dev, min/max/avg              |
|  competitor_coverage   |  Market share percentages                |
|  emerging_products     |  New product discoveries                 |
|  price_drops           |  Detected price decreases                |
+------------------------+------------------------------------------+
|  INVENTORY TABLE (1)                                              |
+------------------------+------------------------------------------+
|  shop_inventory        |  User's stock (product, qty, url, price) |
+========================+==========================================+
```

### 8.2 Key Table: `competitor_prices`

```sql
competitor_prices
  id            BIGSERIAL PRIMARY KEY
  shop_id       BIGINT          -- multi-tenant isolation
  product_name  VARCHAR(500)    -- extracted product name
  price         NUMERIC(12,2)   -- extracted price in INR
  competitor    VARCHAR(255)    -- "Amazon.in", "Flipkart", etc.
  url           TEXT            -- source URL
  domain        VARCHAR(255)    -- domain name
  scraped_at    TIMESTAMPTZ     -- when price was found
```

### 8.3 Key Table: `shop_inventory`

```sql
shop_inventory
  id            BIGSERIAL PRIMARY KEY
  shop_id       BIGINT NOT NULL     -- links to shops table
  product_name  TEXT NOT NULL       -- what the user stocks
  quantity      INT DEFAULT 0       -- current stock count
  product_url   TEXT DEFAULT ''     -- optional product link
  price         NUMERIC DEFAULT 0   -- user's selling price
  category      TEXT DEFAULT ''     -- product category
  notes         TEXT DEFAULT ''     -- free-form notes
  created_at    TIMESTAMPTZ         -- insertion time
  updated_at    TIMESTAMPTZ         -- last modification
```

---

## 9. LLM Integration — NVIDIA Kimi K2

### 9.1 Three LLM Use Cases

```
  +-------------------------------------------------------------------+
  | USE CASE 1: Custom Domain Keywords                                |
  |                                                                   |
  | Input:  "I sell organic skincare and Ayurvedic products"          |
  | Output: {                                                         |
  |   "core_keywords": ["organic cream price", "buy skincare"...],    |
  |   "product_keywords": ["Biotique", "Forest Essentials"...],       |
  |   "competitor_keywords": ["Nykaa skincare", "Amazon ayurvedic"..] |
  | }                                                                 |
  +-------------------------------------------------------------------+

  +-------------------------------------------------------------------+
  | USE CASE 2: Product Enrichment                                    |
  |                                                                   |
  | Input:  Scraped product list with prices                          |
  | Output: Each product gets:                                        |
  |   - market_insight: "This is 12% below market average"            |
  |   - price_assessment: "Competitive"                               |
  |   - recommendation: "Stock 40 units, high demand expected"        |
  +-------------------------------------------------------------------+

  +-------------------------------------------------------------------+
  | USE CASE 3: Business Advisor Chatbot                              |
  |                                                                   |
  | System prompt includes:                                           |
  |   - LIVE MARKET DATA (price ranges, competitors, volatility)      |
  |   - YOUR INVENTORY (stock levels, low-stock items)                |
  |   - Chat history (last 6 messages)                                |
  |                                                                   |
  | The model gives inventory-aware, data-driven strategic advice.    |
  +-------------------------------------------------------------------+
```

### 9.2 LLM Guardrails

```
  +---------------------------+
  | Rate Limit               |  60 calls/hour max
  +---------------------------+
  | Token Cap                |  2048 max completion tokens
  +---------------------------+
  | Temperature              |  0.6 (balanced creativity)
  +---------------------------+
  | Non-Blocking             |  areason() runs in thread executor
  |                          |  (asyncio.run_in_executor)
  |                          |  Server never blocks on LLM calls
  +---------------------------+
  | Retry                    |  Graceful degradation on failure
  +---------------------------+
  | JSON Parsing             |  Regex extraction from markdown
  |                          |  code blocks as fallback
  +---------------------------+
```

---

## 10. Frontend Tab Functionalities

### 10.1 Overview Tab

**Purpose**: Central hub showing all scraped competitor prices + inventory management.

**Functionality**:
- Searchable product table (filter by name or competitor)
- Each row shows: Product Name, Competitor, Price (₹ formatted), External link
- "+ Add My Inventory" button toggles the inventory panel
- Inventory panel (light/opaque theme):
  - CSV textarea for bulk paste (format: `Name, Quantity, URL`)
  - Two-step flow: "Add to Table" (local preview) → "Save Items" (persist to DB)
  - Unsaved rows appear with yellow highlight + orange dot
  - Inline quantity editing (click pencil → enter number → save)
  - Delete items with trash icon

### 10.2 Radar Tab

**Purpose**: Spot newly discovered products across competitors.

**Functionality**:
- Filters `scrapedData` for items where `isNew === true`
- Products are flagged as "emerging" when first seen within 24 hours across 2+ retailers
- Powered by `product_metadata.is_emerging` in Supabase

### 10.3 Price Activity (Volatility) Tab

**Purpose**: Identify products with the most price fluctuation.

**Functionality**:
- Shows volatility score per product (standard deviation of prices)
- Helps identify products where competitors are actively adjusting prices
- Data from `product_volatility` table

### 10.4 Price Drops Tab

**Purpose**: Rank products by how much cheaper the lowest competitor price is vs average.

**Functionality**:
- Groups products by name across all competitors
- Calculates: `dropPercent = (avgPrice - cheapestPrice) / avgPrice * 100`
- Filters out drops < 2% (noise)
- Sorted by largest drop first
- Shows old price (average) vs current best price

### 10.5 Business Advisor Tab (Chatbot)

**Purpose**: AI-powered strategic advisor using real market data + inventory.

**Functionality**:
- Chat interface with message bubbles (user = right, agent = left)
- Messages sent to `POST /api/chat`
- LLM receives full context:
  - Price ranges, top competitors, volatile products
  - Emerging products, market insights
  - User's inventory (all items with quantities)
  - Last 6 chat messages for continuity
- Markdown rendering: **bold**, *italic*, `code`, bullet lists, numbered lists
- Responses reference actual data (competitor names, prices, inventory levels)

### 10.6 Alerts Tab

**Purpose**: Actionable notifications based on inventory levels + market signals.

**Functionality**:
- 5 alert rule types (see Section 4.4)
- Each alert has: type badge, title, message, expandable strategy detail
- Strategy detail includes: Rationale, Market Recommendation, Competitor Signal
- Alerts only trigger when inventory exists (zero fake data)
- Badge count shown on tab + mobile nav

### 10.7 Agent Sidebar

**Purpose**: Real-time agent status and quick market intelligence.

**Functionality**:
- Agent status indicator (running/idle)
- Smart Whisper: top strategic insight from scraped data
- Trending items: products with highest volatility
- Market share: competitor listing counts visualized

---

## 11. Inventory System — Complete Flow

### 11.1 Architecture

```
  +-------------------+     +-------------------+     +-------------------+
  |  CSV TEXT INPUT    |     |  PREVIEW TABLE    |     |  SUPABASE DB      |
  |                   |     |                   |     |                   |
  | "iPhone,25"       |     | [yellow row]      |     | shop_inventory    |
  | "Galaxy,10,url"   | --> | iPhone    25  --  | --> | id=1 iPhone 25    |
  |                   |     | Galaxy    10  url |     | id=2 Galaxy 10    |
  |   [Add to Table]  |     |                   |     |                   |
  |                   |     |  [Save 2 Items]   |     |  Background:      |
  |                   |     |                   |     |  auto-search for  |
  |                   |     |                   |     |  URL + price if   |
  |                   |     |                   |     |  not provided     |
  +-------------------+     +-------------------+     +-------------------+
```

### 11.2 Auto-Search Enrichment

When a product is saved without a URL:
1. Items are inserted immediately (no blocking)
2. A background `asyncio.Task` launches
3. For each item without a URL:
   - DuckDuckGo search: `"{product name}" price buy India`
   - Fetch top 5 results
   - Extract price using MultiFactorScorer
   - Update the inventory row with found URL + price

### 11.3 Inventory → Alerts Pipeline

```
  shop_inventory (Supabase)
       |
       | GET /api/inventory/{shop_id}
       v
  useDashboard.js: inventory state
       |
       | useMemo with [scrapedData, inventory]
       v
  Alert Rules Engine
       |
       | Product name matching:
       | 1. Exact match (lowercase)
       | 2. Partial match (substring)
       |
       | Cross-reference:
       | - inventory.quantity (your stock)
       | - scrapedData.volatility (market demand)
       v
  alerts[] -> AlertsTab.jsx
```

### 11.4 Inventory → Chatbot Pipeline

```
  shop_inventory
       |
       | Direct Supabase query in /api/chat handler
       v
  llm_chat_response() system prompt:
       |
       | === YOUR INVENTORY ===
       | Total SKUs: 12, Total units: 340
       | Low stock items (<10): iPhone 16 (3 units)
       | * iPhone 16: 3 units (₹79,990)
       | * Samsung S24: 45 units (₹64,999)
       | ...
       | === END INVENTORY ===
       v
  LLM gives inventory-aware advice:
  "Your iPhone 16 stock is critically low at 3 units.
   Given the 8.5% market volatility, restock 40 units
   immediately — competitors are listing at ₹82,990."
```

---

## 12. Network Architecture

```
  Browser (:5173)
     |
     | /api/* requests
     |
     v
  Vite Dev Server (:5173)
     |
     | proxy: /api -> http://localhost:8000
     | (configured in vite.config.js)
     |
     v
  FastAPI + Uvicorn (:8000)
     |
     +-------+----------+-----------+
     |       |          |           |
     v       v          v           v
  Supabase  DDG       NVIDIA    aiohttp
  REST API  HTML      AI API    fetcher
  (HTTPS)   Scraper   (HTTPS)   (HTTPS)
     |       |          |           |
     v       v          v           v
  Postgres  DuckDuckGo NVIDIA    Target
  (hosted)  Servers    Endpoints  Retail
                                 Sites
```

---

## 13. Security & Guardrails

```
  +----------------------------------+------------------------------------+
  | Measure                          | Implementation                     |
  +----------------------------------+------------------------------------+
  | API Keys                         | Stored in .env, loaded via dotenv  |
  | CORS                             | Allow all origins (dev mode)       |
  | Rate Limiting (LLM)              | 60 calls/hour, tracked in memory  |
  | Rate Limiting (Scraper)          | 1 req/sec per worker, semaphore   |
  | Concurrency Control              | asyncio.Semaphore(3)              |
  | Price Sanity                     | 0 < price < ₹1,00,00,000         |
  | Zero Price Blocking              | 3-layer gate (insert/read/purge)  |
  | Spam Detection                   | Multi-factor scorer, hard reject  |
  | URL Deduplication                | SHA256 hash + processed_urls DB   |
  | Request Timeout                  | aiohttp total timeout configured  |
  | LLM Token Cap                    | 2048 max completion tokens        |
  | Non-Blocking LLM                 | run_in_executor (thread pool)     |
  | Multi-Tenant Isolation           | All queries filter by shop_id     |
  +----------------------------------+------------------------------------+
```

---

## 14. File Map

```
retail-agent-3-/
 |
 +-- index.html                 # Entry point
 +-- package.json               # React 19, Vite 7.3, Lucide
 +-- vite.config.js             # Proxy /api -> :8000
 +-- tsconfig.json              # TypeScript config (JSX used)
 |
 +-- src/
 |    +-- main.jsx              # ReactDOM.createRoot
 |    +-- App.jsx               # Root component (setup vs dashboard)
 |    +-- index.css             # All styles (~2000 lines)
 |    |
 |    +-- hooks/
 |    |    +-- useDashboard.js  # Central state + alerts + derived metrics
 |    |
 |    +-- views/
 |    |    +-- SetupView.jsx    # Domain picker, shop name
 |    |    +-- DashboardView.jsx# Tab container, top nav, sidebar
 |    |
 |    +-- components/
 |    |    +-- AgentSidebar.jsx # Status, whisper, trending
 |    |    +-- tabs/
 |    |         +-- OverviewTab.jsx         # Product table + inventory CRUD
 |    |         +-- RadarTab.jsx            # Emerging products
 |    |         +-- VolatilityTab.jsx       # Price activity
 |    |         +-- DropsTab.jsx            # Price drops
 |    |         +-- BusinessAdvisorTab.jsx  # LLM chatbot
 |    |         +-- AlertsTab.jsx           # Inventory-aware alerts
 |    |         +-- MarketMapTab.jsx        # Market share (unused in nav)
 |    |
 |    +-- data/
 |         +-- constants.js     # DOMAINS, COMPETITORS arrays
 |         +-- mockDataGenerator.js  # (legacy, not used)
 |
 +-- backend/
 |    +-- server.py             # FastAPI server (~1600 lines)
 |    +-- server.py.bak         # Old fake-data backup
 |    +-- venv/                 # Python virtual environment
 |
 +-- retail-agent/
      +-- .env                  # SUPABASE_URL, SUPABASE_KEY, NVIDIA_API_KEY
      +-- database.py           # SupabaseStore (CRUD operations)
      +-- scraper.py            # DuckDuckGoScraper (async)
      +-- fetcher.py            # ContentFetcher (aiohttp + retry)
      +-- scorer.py             # MultiFactorScorer (price extraction)
      +-- canonicalizer.py      # URLCanonicalizer (SHA256 dedup)
      +-- llm_client.py         # AgentLLM (NVIDIA Kimi K2, async)
      +-- agent_core.py         # AgentReasoningCore (ReAct loop)
      +-- agent_tools.py        # ToolRegistry (5 agent tools)
      +-- agent_memory.py       # AgentMemory + AgentState
      +-- agent_analytics.py    # AnalyticsEngine (4 analytics)
      +-- agent_engine.py       # Agent orchestrator
      +-- shop_manager.py       # ShopManager + CategoryKeywordManager
      +-- config.py             # Constants, thresholds, timing
      +-- engine.py             # Legacy engine
      +-- schema.sql            # Base 10-table schema
      +-- SCHEMA_ADDITIONS.sql  # 7 analytics table additions
      +-- requirements.txt      # Python dependencies
      +-- Dockerfile            # Container build
      +-- docker-compose.yml    # Docker compose config
```

---

## 15. Running the Application

```bash
# Terminal 1 — Backend
cd backend
source venv/bin/activate
python server.py
# -> FastAPI on http://localhost:8000

# Terminal 2 — Frontend
npm run dev
# -> Vite on http://localhost:5173

# Open browser: http://localhost:5173
```

**Startup sequence:**
1. Backend initializes Supabase connection
2. Keyword pool seeded with core vocabulary
3. Null/zero price entries purged
4. Inventory table verified
5. Frontend serves React app
6. Vite proxies `/api/*` to backend

**User flow:**
1. Choose domain (Electronics / Fashion / Appliances / Gaming / Custom)
2. Enter shop name
3. Click "Deploy Agent"
4. Backend creates shop → seeds keywords → runs 3 DuckDuckGo searches → scrapes prices → stores in Supabase → LLM enriches → returns data
5. Dashboard renders with real competitor prices
6. Background agent continues scanning autonomously
7. User can add inventory, chat with advisor, view alerts

---

*Generated from live codebase analysis — March 7, 2026*
