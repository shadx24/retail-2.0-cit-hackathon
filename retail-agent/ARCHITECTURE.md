# 🏗️ Agent Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AUTONOMOUS WEB AGENT SYSTEM                         │
│                        Multi-Tenant Price Intelligence                      │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │  agent_engine.py │
                              │   Entry Point    │
                              └────────┬─────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
            CLI Arguments        Environment Vars    Default Value
            (shop_id)           (AGENT_SHOP_ID)      (shop_id=1)
                    │                  │                  │
                    └──────────────────┼──────────────────┘
                                       │
                              ┌────────▼──────────┐
                              │ parse_shop_id()   │
                              │                   │
                              │ Returns shop_id   │
                              └────────┬──────────┘
                                       │
                        ┌──────────────▼──────────────┐
                        │ AgentExecutionController    │
                        │ • Initialize database       │
                        │ • Create AgentReasoningCore │
                        │ • Run cycles forever or once│
                        └──────────────┬──────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │ AgentReasoningCore        │
                         │ (with shop_id parameter)  │
                         └──────────────┬────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
        ▼                               ▼                               ▼
┌──────────────────┐          ┌────────────────────┐        ┌──────────────────┐
│ initialize()     │          │ run_cycle()        │        │ shutdown()       │
│                  │          │                    │        │                  │
│ 1. Load Shop     │          │ ReAct Loop:        │        │ Final analytics  │
│ 2. Load Keywords │          │ • Observe          │        │ Report + close   │
│ 3. Init Filter   │          │ • Reason (LLM)     │        │                  │
└──────────────────┘          │ • Act (tools)      │        └──────────────────┘
                              │ • Evaluate         │
                              │                    │
                              │ Run Analytics      │
                              │ Print Report       │
                              └────────────────────┘
```

---

## Agent Cycle Flow (ReAct Loop)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ONE COMPLETE AGENT CYCLE                             │
└─────────────────────────────────────────────────────────────────────────┘

    START CYCLE
        │
        ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 1: OBSERVE (Database State)              │
    ├───────────────────────────────────────────────┤
    │ • Get domain trust scores                      │
    │ • Check processed URLs                        │
    │ • Review keyword performance                  │
    │ • Count prices collected                      │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 2: REASON (LLM Decision Making)          │
    ├───────────────────────────────────────────────┤
    │ Ask LLM: "What should I do next?"             │
    │                                                │
    │ Options:                                       │
    │ • search_web (PRIMARY)                        │
    │ • expand_keywords                             │
    │ • deep_crawl (follow internal links)          │
    │ • browse_page (specific URL)                  │
    │ • query_stats (check progress)                │
    │                                                │
    │ LLM returns: { action, params, reasoning }    │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 3: ACT (Execute Tool)                    │
    ├───────────────────────────────────────────────┤
    │ Execute chosen tool                           │
    │                                                │
    │ Example: search_web("iPhone price deal")      │
    │          → Returns 15 URLs                     │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 4: EVALUATE & PROCESS RESULTS            │
    ├───────────────────────────────────────────────┤
    │ For each URL from search:                      │
    │                                                │
    │ 1. Check if duplicate                         │
    │ 2. Canonicalize & validate                    │
    │ 3. Check domain blacklist                     │
    │ 4. Browse page (fetch HTML)                   │
    │ 5. Extract content                            │
    │ 6. Score for pricing page quality             │
    │ 7. If valid offer:                            │
    │    • Extract price                            │
    │    • Tag with shop_id ◄─── MULTI-TENANT       │
    │    • Store in database                        │
    │ 8. Update domain trust score                  │
    │                                                │
    │ → Result: Prices found, domains updated       │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 5: UPDATE CONTEXT & REPEAT               │
    ├───────────────────────────────────────────────┤
    │ Add result to context for next reasoning:     │
    │ • Prices found                                │
    │ • URLs processed                              │
    │ • New queries generated                       │
    │ • Stats from database                         │
    │                                                │
    │ Repeat steps 2-5 (max 15 actions/cycle)       │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 6: RUN ANALYTICS (All 5 Features)        │
    ├───────────────────────────────────────────────┤
    │ analytics.run_full_analytics_cycle(shop_id)   │
    │                                                │
    │ ┌────────────────────────────────────────┐    │
    │ │ 🚀 Emerging Product Radar              │    │
    │ │ detect_emerging_products()             │    │
    │ │ → Find products <24h on 2+ retailers   │    │
    │ └────────────────────────────────────────┘    │
    │                                                │
    │ ┌────────────────────────────────────────┐    │
    │ │ 📈 Price Volatility Score              │    │
    │ │ calculate_price_volatility()           │    │
    │ │ → STD_DEV of prices → Level            │    │
    │ └────────────────────────────────────────┘    │
    │                                                │
    │ ┌────────────────────────────────────────┐    │
    │ │ 🏪 Competitor Coverage Map             │    │
    │ │ get_competitor_coverage_by_category()  │    │
    │ │ → Market share % per competitor        │    │
    │ └────────────────────────────────────────┘    │
    │                                                │
    │ ┌────────────────────────────────────────┐    │
    │ │ ⬇️ Price Drop Detector                 │    │
    │ │ detect_price_drops(threshold=5%)       │    │
    │ │ → Find sudden price reductions         │    │
    │ └────────────────────────────────────────┘    │
    │                                                │
    │ ┌────────────────────────────────────────┐    │
    │ │ 🔍 Automatic Product Discovery         │    │
    │ │ auto_discover_products()               │    │
    │ │ → Find new products (trending)         │    │
    │ └────────────────────────────────────────┘    │
    │                                                │
    │ → Result: Dict with all 5 feature results    │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 7: PRINT ANALYTICS REPORT                │
    ├───────────────────────────────────────────────┤
    │ ═══════════════ ANALYTICS REPORT ═══════════  │
    │                                                │
    │ 🚀 3 EMERGING PRODUCTS                         │
    │ 📈 2 HIGH VOLATILITY ITEMS                     │
    │ 🏪 Amazon: 34.7% market share                │
    │ ⬇️ 1 price drop detected                      │
    │ 🔍 8 new products discovered                  │
    │                                                │
    │ Processing time: 8.3s                         │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    ┌───────────────────────────────────────────────┐
    │ STEP 8: SLEEP & REPEAT                        │
    ├───────────────────────────────────────────────┤
    │ Wait 5-10 minutes                             │
    │ Go back to STEP 1                             │
    └────────────────┬────────────────────────────┘
                     │
                     ▼
    END CYCLE (or SHUTDOWN with final report)
```

---

## Multi-Tenant Data Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    MULTI-TENANT DATA ISOLATION                           │
└──────────────────────────────────────────────────────────────────────────┘

                              ┌────────────────┐
                              │ shops TABLE    │
                              ├────────────────┤
                              │ id: 1, 2, 3... │
                              │ shop_name      │
                              │ shop_domain    │
                              │ category       │
                              └────┬───────┬──┬───────────┐
                                   │       │  │           │
                    ┌──────────────┘       │  │           │
                    │          ┌───────────┘  │           │
                    │          │     ┌────────┘           │
                    ▼          ▼     ▼                     ▼
            
            ╔════════════════╦════════════════╦════════════════╗
            ║   SHOP 1       ║   SHOP 2       ║   SHOP 3       ║
            ║ Electronics    ║ Fashion        ║ Appliances     ║
            ╚════════════════╩════════════════╩════════════════╝
                    │                │                │
    ┌───────────────┼────────────────┼────────────────┼──────────────┐
    │               │                │                │              │
    ▼               ▼                ▼                ▼              ▼
┌─────────┐   ┌─────────┐      ┌─────────┐     ┌─────────┐   ┌──────────┐
│KEYWORDS │   │METADATA │      │PRICES   │     │DROPPING │   │EMERGING  │
│shop_id=1│   │shop_id=1│      │shop_id=1│     │shop_id=1│   │shop_id=1 │
│         │   │         │      │         │     │         │   │          │
│iPhone   │   │iPhone   │      │Amazon   │     │iPhone   │   │Sony      │
│Samsung  │   │Samsung  │      │Flipkart│     │₹150→149 │   │WH-1000   │
│Laptop..│   │..trending│      │BestBuy..      │-0.7%   │   │..new..  │
└─────────┘   └─────────┘      └─────────┘     └─────────┘   └──────────┘
    │              │               │              │             │
    └──────────────┴───────────────┴──────────────┴─────────────┘
                           │
                    Completely Isolated
                    No Cross-Shop Data
```

---

## Tool Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         AGENT TOOLS REGISTRY                         │
│                    (Tools available to LLM agent)                    │
└──────────────────────────────────────────────────────────────────────┘

                    ┌──────────────┐
                    │ ToolRegistry │
                    └────────┬─────┘
                             │
        ┌────────────────────┼────────────────────┬─────────────────┐
        │                    │                    │                 │
        ▼                    ▼                    ▼                 ▼
    ┌────────────┐    ┌────────────┐    ┌──────────────┐    ┌────────────┐
    │ SearchTool │    │ BrowseTool │    │ KeywordTool  │    │DeepCrawlTool
    ├────────────┤    ├────────────┤    ├──────────────┤    ├────────────┤
    │ search_web │    │browse_page │    │expand_keyword│    │deep_crawl  │
    │            │    │            │    │              │    │            │
    │ DuckDuckGo │    │  Fetch HTML│    │ Generate new │    │Find internal
    │ Search     │    │  + JS      │    │ queries      │    │ links (crawl)
    │            │    │  Extract   │    │              │    │            │
    │ Returns:   │    │ content    │    │ From vocab + │    │Returns:    │
    │ 15 URLs    │    │            │    │ synonyms     │    │ Priority   │
    │            │    │ Returns:   │    │              │    │ internal   │
    └────┬───────┘    │ Title, text│    │ Returns:     │    │ links for  │
         │            │ links      │    │ 15 queries   │    │ crawling   │
         │            └────┬───────┘    └──────────────┘    └────┬───────┘
         │                 │                                       │
         └─────────────────┼─────────────────────────────────────┘
                           │
                    ┌──────▼──────────────┐
                    │   Each tool result  │
                    │   goes to EVALUATE  │
                    │                     │
                    │ Auto-Pipeline:      │
                    │ Search → Browse →   │
                    │ Score → Store       │
                    │ (all automatic)     │
                    └────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                       PIPELINE: Search Results                       │
└──────────────────────────────────────────────────────────────────────┘

    SearchTool.execute("iPhone price deal")
            │
            ├─→ DuckDuckGo API
            │   └─→ Returns 15 URLs
            │
            ▼
    For each URL:
            │
            ├─→ Canonicalize & validate
            │   └─→ Check if duplicate/seen/blacklisted
            │
            ├─→ BrowseTool.execute(url)
            │   └─→ Fetch HTML, extract content
            │
            ├─→ ScoreTool.execute(content)
            │   └─→ Score for pricing quality
            │
            ├─→ If valid offer:
            │   ├─→ Extract price
            │   ├─→ Tag with shop_id  ◄─── MULTI-TENANT KEY
            │   ├─→ CompetitorPrice(
            │   │   domain, url, product, price,
            │   │   currency, category, 
            │   │   scraped_at, shop_id ◄─ HERE
            │   │ )
            │   └─→ Insert into database
            │
            └─→ Update domain trust score

    Result: Prices collected with shop_id isolation
```

---

## Database Schema Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                      DATABASE SCHEMA STRUCTURE                       │
│                     (Supabase / PostgreSQL)                          │
└──────────────────────────────────────────────────────────────────────┘

CORE TABLES (Multi-Tenant - shop_id FK):
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   shops ◄───────┐─────────────────────────────────────────────┐    │
│   ┌──────────┐  │                                             │    │
│   │ id       │  │  Foreign Key Relationships                │    │
│   │ name     │  │                                             │    │
│   │ domain   │  │                                             │    │
│   │ category │  │                                             │    │
│   └──────────┘  │                                             │    │
│        │        │                                             │    │
│        └────┬───┴───────────────────────────────────────┬────┘    │
│             │                                           │         │
│             ▼                                           ▼         │
│   ┌─────────────────┐                          ┌──────────────┐  │
│   │ keyword_pool    │                          │competitor_   │  │
│   │                 │                          │prices        │  │
│   │ shop_id (FK)    │                          │              │  │
│   │ category        │                          │ shop_id (FK) │  │
│   │ term            │                          │ domain       │  │
│   │ yield_score     │                          │ product_name │  │
│   │ is_active       │                          │ price        │  │
│   └─────────────────┘                          │ currency     │  │
│                                                │ category     │  │
│   ┌─────────────────┐                          │ scraped_at   │  │
│   │ product_        │                          └──────────────┘  │
│   │ metadata        │                                             │
│   │                 │                          ┌──────────────┐  │
│   │ shop_id (FK)    │                          │ price_history│  │
│   │ product_name    │                          │              │  │
│   │ first_seen      │                          │ shop_id (FK) │  │
│   │ is_emerging     │                          │ domain       │  │
│   │ trending_score  │                          │ product_name │  │
│   └─────────────────┘                          │ price @ date │  │
│                                                └──────────────┘  │
└──────────────────────────────────────────────────────────────────────┘

ANALYTICS TABLES (shop_id FK):
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐   │
│   │ product_         │  │ competitor_      │  │ emerging_      │   │
│   │ volatility       │  │ coverage         │  │ products       │   │
│   │                  │  │                  │  │                │   │
│   │ shop_id (FK)     │  │ shop_id (FK)     │  │ shop_id (FK)   │   │
│   │ product_name     │  │ competitor_domain│  │ product_name   │   │
│   │ avg_price        │  │ category         │  │ first_seen     │   │
│   │ volatility_score │  │ product_count    │  │ retailer_count │   │
│   │ variance         │  │ market_share_%   │  │ retailer_list  │   │
│   │ sample_count     │  │                  │  │ alert_sent     │   │
│   └──────────────────┘  └──────────────────┘  └────────────────┘   │
│                                                                      │
│   ┌──────────────────┐  ┌──────────────────────────────────────┐   │
│   │ price_drops      │  │ product_discovery_log                │   │
│   │                  │  │                                      │   │
│   │ shop_id (FK)     │  │ shop_id (FK)                         │   │
│   │ product_name     │  │ discovery_cycle                      │   │
│   │ competitor_domain│  │ products_found                       │   │
│   │ old_price        │  │ emerging_products                    │   │
│   │ new_price        │  │ price_drops_detected                 │   │
│   │ drop_percent     │  │ process_time_seconds                 │   │
│   │ alert_sent       │  │ completed_at                         │   │
│   └──────────────────┘  └──────────────────────────────────────┘   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

CONTROL TABLES (No shop_id - shared):
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   ┌──────────────┐         ┌──────────────┐                         │
│   │ domains      │         │ urls_       │                         │
│   │              │         │ processed    │                         │
│   │ domain (PK)  │         │              │                         │
│   │ trust_score  │         │ url_hash(PK) │                         │
│   │ offer_count  │         │ canonical_url│                         │
│   │ spam_count   │         │ domain       │                         │
│   │ is_blacklist │         │ score        │                         │
│   │ is_offer     │         │ spam_score   │                         │
│   └──────────────┘         │ processed_at │                         │
│                            └──────────────┘                         │
│                                                                      │
│   (These are shared across all shops - no shop_id)                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

KEY PRINCIPLE:
═══════════════════════════════════════════════════════════════════════════
Every analytics table has: shop_id (BIGINT) REFERENCES shops(id)
This ensures complete data isolation between shops.
```

---

## Analytics Processing Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│               ANALYTICS ENGINE - 5 FEATURES PIPELINE                 │
└──────────────────────────────────────────────────────────────────────┘

Input: shop_id (filters all data to this shop only)
  │
  ├─────────────────────────────────────────────────────────────┐
  │                                                             │
  ▼                                                             ▼
┌─────────────────────────────┐                    ┌──────────────────────┐
│ 🚀 EMERGING PRODUCTS        │                    │ 📈 VOLATILITY SCORE  │
├─────────────────────────────┤                    ├──────────────────────┤
│ Query: competitor_prices    │                    │ Query: competitor_    │
│        WHERE shop_id=$id    │                    │        prices WHERE   │
│        AND scraped_at >     │                    │        shop_id=$id    │
│        (now - 24h)          │                    │                      │
│                             │                    │ For each product:     │
│ Group by: product_name      │                    │ • Collect all prices │
│ Count: retailers (WHERE     │                    │ • Calculate mean     │
│        domain != own)       │                    │ • Calculate std_dev  │
│                             │                    │ • Classify:          │
│ Filter: retailer_count >= 2 │                    │   - Low: < 5%        │
│ Sort: by hours_old DESC     │                    │   - Med: 5-15%       │
│                             │                    │   - High: 15-30%     │
│ Output: List[Emerging       │                    │   - Extreme: > 30%   │
│         Product]            │                    │                      │
│ Store: emerging_products    │                    │ Output: List[Price   │
│        table                │                    │         Volatility]  │
│                             │                    │ Store: product_      │
│                             │                    │        volatility tbl│
└─────────────────────────────┘                    └──────────────────────┘
  │                                                  │
  └──────────────────────────┬───────────────────────┘
                             │
                             ▼
┌───────────────────────────────────────────────────────────────┐
│ 🏪 COMPETITOR COVERAGE MAP                                   │
├───────────────────────────────────────────────────────────────┤
│ Query: competitor_prices WHERE shop_id=$id                   │
│ GROUP BY: domain, category                                   │
│ COUNT: products per domain per category                       │
│                                                               │
│ For each (domain, category):                                 │
│ • Count products in category (all domains)                   │
│ • Calculate market_share = (domain_count / total) × 100      │
│ • Identify dominant (> 20%)                                  │
│                                                               │
│ Output: Dict[category → List[CompetitorMarketShare]]         │
│ Store: competitor_coverage table                             │
└───────────────────────────────────────────────────────────────┘
  │
  └────────────────────────┬──────────────────────┐
                           │                      │
                           ▼                      ▼
        ┌──────────────────────────┐   ┌─────────────────────┐
        │ ⬇️ PRICE DROP DETECTOR   │   │ 🔍 PRODUCT DISCVRY  │
        ├──────────────────────────┤   ├─────────────────────┤
        │ Query: price_drops WHERE │   │ Query: competitor_  │
        │        shop_id=$id       │   │        prices WHERE  │
        │ AND old_price >          │   │        shop_id=$id   │
        │     new_price × 1.05     │   │                     │
        │                          │   │ GROUP BY product    │
        │ Calculate drop_percent = │   │ COUNT distinct      │
        │ (old-new)/old × 100      │   │ retailers (>= 2)    │
        │                          │   │                     │
        │ Filter: drop % >= 5.0    │   │ Calculate:          │
        │ Sort: by drop % DESC     │   │ confidence_score =  │
        │                          │   │ retailer_count×20   │
        │ Output: List[PriceDrop]  │   │            (max 100)│
        │ Store: price_drops table │   │                     │
        │         + alert_sent     │   │ Output: List[       │
        │                          │   │ Discovered Product] │
        │                          │   │ Store: product_     │
        │                          │   │ metadata table      │
        └──────────────────────────┘   └─────────────────────┘
  │                                         │
  └──────────────────┬──────────────────────┘
                     │
                     ▼
    ┌────────────────────────────────────┐
    │ AGGREGATE ALL 5 FEATURES           │
    ├────────────────────────────────────┤
    │ Combine results into single Dict:  │
    │ {                                  │
    │   'emerging_products': [...],      │
    │   'volatilities': [...],           │
    │   'competitor_coverage': {...},    │
    │   'price_drops': [...],            │
    │   'discovered_products': [...],    │
    │   'cycle_time_seconds': 2.3        │
    │ }                                  │
    │                                    │
    │ Log cycle to:                      │
    │ product_discovery_log table        │
    │                                    │
    │ Format for display:                │
    │ format_analytics_report()          │
    └────────────────────────────────────┘
                     │
                     ▼
    ┌────────────────────────────────────┐
    │ RETURN TO AGENT                    │
    │ Print report + return summary      │
    │                                    │
    │ Output as:                         │
    │ ═════════════════════════          │
    │ 🚀 3 EMERGING PRODUCTS              │
    │ 📈 2 HIGH VOLATILITY                │
    │ 🏪 Amazon: 34.7%                   │
    │ ⬇️ 1 price drop                     │
    │ 🔍 8 new products                   │
    │ ═════════════════════════          │
    └────────────────────────────────────┘
```

---

## Module Dependency Graph

```
┌────────────────────────────────────────────────────────────────┐
│                   MODULE DEPENDENCY GRAPH                      │
└────────────────────────────────────────────────────────────────┘

                      agent_engine.py
                      ▲
                      │ uses
                      │
                      ▼
        ┌─────────────────────────────┐
        │  AgentExecutionController   │
        │  • initialize()             │
        │  • run_forever()            │
        │  • shutdown()               │
        └──────────────┬──────────────┘
                       │
                       │ creates
                       ▼
        ┌──────────────────────────────┐
        │  agent_core.py               │
        │  AgentReasoningCore          │
        │  • initialize()              │
        │  • run_cycle()               │
        │  • shutdown()                │
        └──────────────┬───────────────┘
                       │
        ┌──────────────┼──────────────┬──────────────┐
        │              │              │              │
        ▼              ▼              ▼              ▼
    ┌─────────┐  ┌──────────┐  ┌─────────────┐  ┌──────────────┐
    │ database│  │agent_    │  │shop_manager │  │agent_        │
    │ .py     │  │tools.py  │  │.py          │  │analytics.py  │
    │         │  │          │  │             │  │              │
    │Supabase │  │Tool      │  │ShopManager  │  │Analytics     │
    │Store    │  │Registry  │  │Category     │  │Engine        │
    │         │  │          │  │KeywordMgr   │  │              │
    │Insert   │  │Search    │  │Product      │  │5 Features    │
    │Prices   │  │Browse    │  │Filter       │  │              │
    │Domain   │  │Score     │  │             │  │Emerging      │
    │Trust    │  │Keyword   │  │             │  │Volatility    │
    │         │  │Crawl     │  │             │  │Coverage      │
    │         │  │Stats     │  │             │  │Drops         │
    │         │  │          │  │             │  │Discovery     │
    └─────────┘  └──────────┘  └─────────────┘  └──────────────┘
        │              │              │              │
        └──────────────┼──────────────┴──────────────┘
                       │
                       ▼
    ┌────────────────────────────────────┐
    │ Supabase (PostgreSQL)              │
    │ • shops                            │
    │ • competitor_prices  (with shop_id)│
    │ • keyword_pool       (with shop_id)│
    │ • emerging_products  (shop_id FK)  │
    │ • product_volatility (shop_id FK)  │
    │ • competitor_coverage(shop_id FK)  │
    │ • price_drops        (shop_id FK)  │
    │ • product_discovery_log            │
    │ And helper functions               │
    └────────────────────────────────────┘
```

---

## Multi-Tenant Flow Example

```
┌────────────────────────────────────────────────────────────────┐
│         CONCURRENT MULTI-TENANT AGENT EXECUTION               │
└────────────────────────────────────────────────────────────────┘

Terminal 1:                     Terminal 2:                     Terminal 3:
python3 agent_eng.py 1          python3 agent_eng.py 2         python3 agent_eng.py 3
    │                               │                               │
    ▼                               ▼                               ▼
┌──────────────────┐          ┌──────────────────┐          ┌──────────────────┐
│ Shop 1           │          │ Shop 2           │          │ Shop 3           │
│ Electronics      │          │ Fashion          │          │ Appliances       │
└────────────────┬─┘          └────────────────┬─┘          └────────────────┬─┘
                 │                            │                             │
    ┌────────────▼──────────┐     ┌───────────▼──────────┐     ┌──────────▼──┐
    │Initialize(shop_id=1)  │     │Initialize(shop_id=2)│     │Initialize  │
    │ Load: Electronics kw   │     │ Load: Fashion kw     │     │(shop_id=3) │
    │ Filter: own domain     │     │ Filter: own domain   │     │ Load:Apps  │
    └────────────┬──────────┘     └───────────┬──────────┘     └──────────┬──┘
                 │                            │                           │
    ┌────────────▼──────────────────────────────────────────────────────┬─┘
    │            │                            │                        │
    │    ┌───────▼──────────┐     ┌───────────▼──────────┐   ┌────────▼──┐
    │    │ Run Cycle        │     │ Run Cycle            │   │ Run Cycle │
    │    │ • search_web     │     │ • search_web         │   │ • search  │
    │    │   (keywords=elec)│     │  (keywords=fashion)  │   │   keywords│
    │    │ • browse/score   │     │ • browse/score       │   │ • browse  │
    │    │ • store prices   │     │ • store prices       │   │ • store   │
    │    │  (shop_id=1)     │     │  (shop_id=2)         │   │  (shop_id)│
    │    └───────┬──────────┘     └───────────┬──────────┘   └────────┬──┘
    │            │                            │                       │
    │    ┌───────▼──────────┐     ┌───────────▼──────────┐   ┌────────▼──┐
    │    │Analytics Engine  │     │Analytics Engine      │   │Analytics  │
    │    │(shop_id=1 data)  │     │(shop_id=2 data)      │   │(shop_id=3)│
    │    │ 🚀 Emerging      │     │ 🚀 Emerging          │   │ 🚀 ...     │
    │    │ 📈 Volatility    │     │ 📈 Volatility        │   │ 📈 ...     │
    │    │ 🏪 Coverage      │     │ 🏪 Coverage          │   │ 🏪 ...     │
    │    │ ⬇️ Drops         │     │ ⬇️ Drops             │   │ ⬇️ ...     │
    │    │ 🔍 Discovery     │     │ 🔍 Discovery         │   │ 🔍 ...     │
    │    └───────┬──────────┘     └───────────┬──────────┘   └────────┬──┘
    │            │                            │                       │
    │    ┌───────▼──────────────────────────────────────────────────┬─┘
    │    │       Print Report          Print Report       Print Rpt │
    │    │   [Shop 1 Analysis]       [Shop 2 Analysis]   [Shop 3]   │
    │    │  ═══════════════════════════════════════════════════════│
    │    │  🚀 3 products NEW        🚀 2 products NEW    🚀 5 ...  │
    │    │  📈 2 HIGH volatility     📈 1 HIGH volatility 📈 3 ...  │
    │    │  🏪 Amazon 34.7% lead     🏪 Shein 45% lead    🏪 ...    │
    │    │  ⬇️ 1 price drop detected  ⬇️ 0 drops          ⬇️ ...     │
    │    │  🔍 8 discovered items    🔍 12 discovered     🔍 ...    │
    │    └───────┬────────────────────────────┬──────────────┬──────┘
    │            │                            │              │
    │    ┌───────▼──────────┐     ┌───────────▼──────────┐   ┌──────▼─┐
    │    │ Sleep 5 min      │     │ Sleep 5 min          │   │ Sleep  │
    │    │ Repeat Cycle     │     │ Repeat Cycle         │   │ Cycle  │
    │    └──────────────────┘     └──────────────────────┘   └────────┘
    │            │                            │                       │
    └────────────┼────────────────────────────┼───────────────────────┘
                 │                            │
         ╔═══════╩════════════╦═══════════════╩═════════╦═════════════╗
         ║                    ║                         ║             ║
         ╠════════════════════╫═════════════════════════╫═════════════╣
         ║  SUPABASE (One Database, Isolated by shop_id)             ║
         ╠════════════════════╫═════════════════════════╫═════════════╣
         ║                    ║                         ║             ║
         ║  competitor_prices ║  product_volatility    ║emerging_    ║
         ║  ├─ shop_id=1      ║  ├─ shop_id=1          ║products    ║
         ║  ├─ shop_id=2      ║  ├─ shop_id=2          ║├─shop_id=1 ║
         ║  └─ shop_id=3      ║  └─ shop_id=3          ║├─shop_id=2 ║
         ║                    ║                         ║└─shop_id=3 ║
         ║  + Other analytics tables similarly isolated by shop_id    ║
         ║                                                            ║
         ║                NO CROSS-SHOP DATA LEAKAGE                 ║
         ║                                                            ║
         ╚════════════════════════════════════════════════════════════╝
```

---

## Key Architectural Components Summary

```
┌──────────────────────────────────────────────┐
│            COMPONENT OVERVIEW               │
└──────────────────────────────────────────────┘

LAYER 1: ENTRY POINT
└─ agent_engine.py
   └─ AgentExecutionController

LAYER 2: AGENT CORE
└─ agent_core.py
   └─ AgentReasoningCore
      ├─ ReAct Loop (Observe, Reason, Act, Evaluate)
      └─ Cycle Management

LAYER 3: MULTI-TENANT MANAGEMENT
├─ shop_manager.py
│  ├─ ShopManager (CRUD operations)
│  ├─ CategoryKeywordManager (Dynamic keywords)
│  └─ ProductDiscoveryFilter (Category filtering)
│
└─ agent_analytics.py (ANALYTICS ENGINE)
   ├─ EmergingProduct (🚀)
   ├─ PriceVolatility (📈)
   ├─ CompetitorMarketShare (🏪)
   ├─ PriceDrop (⬇️)
   ├─ DiscoveredProduct (🔍)
   └─ AnalyticsEngine (orchestrator)

LAYER 4: AGENT TOOLS
└─ agent_tools.py
   ├─ SearchTool (DuckDuckGo)
   ├─ BrowseTool (Fetch HTML)
   ├─ ScoreTool (Relevance scoring)
   ├─ KeywordExpansionTool (New queries)
   ├─ DeepCrawlTool (Internal links)
   └─ StatsTool (Database stats)

LAYER 5: PERSISTENCE
├─ database.py
│  └─ SupabaseStore
│
└─ Supabase (PostgreSQL)
   ├─ Core tables (shops, prices, keywords)
   ├─ Analytics tables (emerging, volatility, etc.)
   └─ Control tables (domains, urls_processed)

LAYER 6: EXTERNAL SERVICES
├─ DuckDuckGo API (Search)
├─ NVIDIA AI Endpoints (LLM - moonshotai/kimi-k2)
└─ Supabase (Database)
```
