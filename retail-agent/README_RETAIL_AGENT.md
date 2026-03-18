# Retail Price Monitor Agent

## Overview

The **Retail Agent** is an autonomous, LLM-driven web agent that discovers and monitors competitor prices across retail websites. It operates in a continuous **Observe → Reason → Act → Evaluate** loop, using NVIDIA AI Endpoints for intelligent decision-making and DuckDuckGo for web search.

**Goal:** _Monitor competitor prices and discover product pricing across retail websites._

**Key Model:** moonshotai/kimi-k2-instruct via NVIDIA AI Endpoints

---

## Architecture Layers

### 1. **Agent Engine (Entry Point)**
- **File:** `agent_engine.py`
- **Role:** Top-level orchestration and lifecycle management
- **Functions:**
  - Initializes the database and LLM client
  - Runs the agent in an infinite loop with multiple cycles
  - Manages graceful shutdown and error recovery
  - Tracks cumulative statistics (cycles completed, prices found, runtime)
  - Implements randomized sleep between cycles (1-25 minutes)

### 2. **Agent Reasoning Core (The Brain)**
- **File:** `agent_core.py`
- **Role:** ReAct loop implementation — Observe → Reason → Act → Evaluate
- **Functions:**
  - **Observe:** Loads database state (URLs processed, prices collected, trusted domains, recent decisions)
  - **Reason:** Sends context to LLM to decide next action (which tool to use, which query to search, etc.)
  - **Act:** Executes the LLM's decision via tool calls (search, browse, crawl, expand keywords)
  - **Evaluate & Process:** Scores search results, stores valid competitor prices, updates domain trust
  - Max 15 actions per cycle with automatic guardrails
  - Auto-pipeline: search → browse → score → store

**SYSTEM PROMPT:** The LLM is instructed to:
- Vary queries across different product verticals (electronics, laptops, phones, appliances...)
- Use `search_web` as the primary tool (auto-processes all results)
- Use `expand_keywords` when yield is low
- Use `deep_crawl` on high-trust domains for internal pricing links
- Track progress via `query_stats`

### 3. **Agent Memory (World State)**
- **File:** `agent_memory.py`
- **Role:** Database observations and context building
- **Tracks:**
  - Total URLs processed
  - Total competitor prices collected
  - Active keywords count
  - Blacklisted domains count
  - Top trusted domains (by trust score)
  - Recent prices found (with product, price, currency)
  - Last cycle yield and discovery rate (moving average)
  - Agent decision history

**Output:** Builds a context prompt for the LLM containing the agent's "world state" to inform next decisions.

### 4. **Agent Tools**
- **File:** `agent_tools.py`
- **6 Tools Available:**

#### Tool 1: **search_web**
- Searches DuckDuckGo with rate limiting (8-12 sec between requests)
- Returns up to 10 URLs per query
- Blocks on 429/403/CAPTCHA with automatic cooldown
- Example queries: `"electronics discount price"`, `"laptop best price", "smartphone sale"`

#### Tool 2: **browse_page**
- Fetches a single URL with retry logic (max 3 retries, exponential backoff)
- Extracts: title, description, main text, outbound link count, listicle detection
- Hard rejects pages with >50 outbound links (likely content farms)
- Returns structured content for scoring

#### Tool 3: **score_page**
- Grades extracted content for pricing page quality
- Multi-factor scoring: entity match + benefit match + program phrases - spam keywords - excess links
- Returns: score, spam_score, is_offer (boolean), matches (what pricing terms were found)

#### Tool 4: **expand_keywords**
- Generates new search queries from vocabulary
- Can focus on a specific product vertical (e.g., "electronics", "laptop")
- Can expand from recent successful terms using synonyms (depth 1)
- Default: random combinations of 5 entities × 5 benefits
- Returns up to 15 new queries

#### Tool 5: **deep_crawl**
- Fetches a domain's page and extracts all internal links
- Prioritizes links with keywords: `price`, `pricing`, `product`, `shop`, `store`, `catalog`, `buy`, `deal`, `offer`, `sale`, `compare`, `checkout`
- Returns up to 10 priority links + 20 other internal links
- Used to find hidden pricing pages on trusted retailer sites

#### Tool 6: **query_stats**
- Returns current database statistics
- Shows: total URLs processed, total prices collected, active keywords, blacklisted domains
- Displays top 5 trusted domains and 5 most recent prices found

---

## Scoring Engine

- **File:** `scorer.py`
- **Type:** Deterministic (no LLM required), O(text length)

### Multi-Factor Score Calculation:

| Factor | Impact | Details |
|--------|--------|---------|
| **Entity Match** | +2 | Matches: price, shop, store, product, retail, marketplace, etc. |
| **Benefit Match** | +2 | Matches: discount, sale, offer, deal, clearance, savings, cheap, etc. |
| **Program Phrases** | +3 each | Exact phrases: "price comparison", "best price", "lowest price", "price match", etc. |
| **Synonym Expansion** | +1 | Secondary matches via synonym graph (depth 1) |
| **Trusted Domain Bonus** | +2 | If domain trust_score > 5 |
| **Spam Keywords** | -2 | Matches: counterfeit, knockoff, replica, bootleg, phishing, etc. |
| **Excess Outbound Links** | -1 per excess | Pages with >30 links lose 1 point per extra link |
| **Listicle Pattern** | -2 | Detected via "top N", "best N", "N ways to" patterns |
| **Affiliate Links** | -2 each | Pages with >5 affiliate params get penalized |

**Decision Logic:**
- `is_offer = (score >= 4) AND NOT hard_rejected`
- `hard_rejected = (spam_score >= 6)`

### Price Extraction:
Regex patterns for extracting numeric prices from content:
- `$99.99` (USD with dollar sign)
- `€99.99` (EUR with euro sign)
- `£99.99` (GBP with pound sign)
- `USD 99.99` or `99.99 USD` (explicit currency codes)
- Deduplicates by amount + currency
- Sanity bounds: 0.01 to 1,000,000

---

## Data Models

### **CompetitorPrice** (Core Entity)
Stored when a pricing page is discovered:
```python
domain: str                 # e.g., "amazon.com"
url: str                    # canonical URL
product_name: str           # page title (≤450 chars)
price: Optional[float]      # extracted price value
currency: str               # "USD", "EUR", "GBP"
competitor_name: str        # domain name
category: str               # product categories found
scraped_at: datetime        # timestamp
```

### **Domain Trust Scoring**
Tracks domain reputation:
```python
domain: str                 # primary key
trust_score: float          # starts at 0, ±2 per offer/spam
offer_count: int            # valid pricing pages found
spam_count: int             # spam/hard-rejected pages
is_blacklisted: bool        # if trust_score < -10
```

**Trust Delta Updates:**
- Valid pricing page found: **+2**
- Spam detected: **-3**
- Monthly decay: **×0.95** (5% erosion)

### **Keyword Pool**
Generated/discovered during operation:
```python
term: str                   # search keyword
category: str               # "core" (never removed) or "learned"
yield_score: float          # how many results this keyword returns (0.0-1.0)
usage_count: int            # how many times searched
last_used: datetime         # most recent search
is_active: bool             # can be deactivated if low-yield
```

**Yield Tracking:**
- Exponential moving average: `new_yield = 0.7 × old_yield + 0.3 × (1 if results else 0)`
- Deprioritized after 5 consecutive zero-yield cycles
- Pruned if inactive + yield < 0.1 + used ≥10 times

---

## Database Layer

- **File:** `database.py`
- **Backend:** Supabase (PostgreSQL)
- **Tables:**

| Table | Purpose | Key Columns |
|-------|---------|------------|
| `processed_urls` | O(1) dedup cache | url_hash (unique), domain, score, is_offer |
| `archived_urls` | Old URL archive (>90 days) | url_hash, domain, processed_at |
| `domains` | Domain trust tracking | domain (PK), trust_score, offer_count, spam_count, is_blacklisted |
| `competitor_prices` | **Discovered prices** | domain, url, product_name, price, currency, scraped_at |
| `keyword_pool` | Search keywords | term (unique), category, yield_score, is_active |
| `learned_terms` | Co-occurrence learning | term, context, frequency, promoted |
| `system_stats` | Aggregate stats | stats_json |
| `price_history` | Price trends over time | domain, product_name, price, currency, recorded_at |

**Constraints:**
- Unique URL hashes prevent duplicate processing
- Domain references enable trust cascading
- Soft deletes (mark inactive) instead of hard deletes for learned terms
- Batch inserts (50 at a time) for performance

---

## Core Vocabulary & Configuration

- **File:** `config.py`

### **Entities** (Competitor/Retailer Terms)
```
price, pricing, cost, retail, shop, store, buy, purchase, product, item, 
listing, marketplace, vendor
```

### **Benefits** (Price-Related Signals)
```
discount, sale, offer, deal, clearance, savings, cheap, lowest, best price, 
reduced, promotion, coupon, markdown, bargain, value
```

### **Program Phrases** (Exact Price Patterns)
```
price comparison, compare prices, best price, lowest price, price match, 
price drop, competitor price, price check, price alert
```

### **Verticals** (Product Categories)
```
electronics, laptop, smartphone, headphones, tablet, camera, monitor, 
keyboard, mouse, speaker, accessories, gaming, appliances, furniture
```

### **Spam Keywords** (Hard Rejects)
```
counterfeit, knockoff, replica, bootleg, phishing, malware, virus, scam, 
fraud, fake, illegal, pirated, unauthorized, suspicious, dangerous, toxic
```

### **System Limits**
```
MAX_QUERIES_PER_CYCLE: 10              (max searches per cycle)
MAX_CONCURRENCY: 3                     (parallel fetches)
MAX_RETRIES: 3                         (fetch attempts)
BATCH_SIZE: 50                         (DB insert batch)
MAX_OUTBOUND_LINKS: 30                 (page quality threshold)
HARD_REJECT_OUTBOUND_LINKS: 50         (auto-reject threshold)
CYCLE_MIN_SLEEP: 45 minutes            (between cycles)
CYCLE_MAX_SLEEP: 75 minutes
SEARCH_MIN_INTERVAL: 8 sec             (rate limiting)
SEARCH_MAX_INTERVAL: 12 sec
COOLDOWN_ON_429: 600 sec               (10 min on rate limit)
```

---

## Web Scraping Pipeline

### **DuckDuckGo Scraper** (`scraper.py`)
- Hit `https://html.duckduckgo.com/html/` (not JavaScript)
- Rate limited: 1 req every 8-12 seconds (randomized)
- CAPTCHA detection: checks for "captcha", "are you human", "proof you", etc.
- Automatic cooldown on 429/403/CAPTCHA (600 seconds)
- Extracts URLs from HTML redirect links

### **Content Fetcher** (`fetcher.py`)
- Max 3 concurrent requests (semaphore-controlled)
- 1 req/sec per worker (rate limiting)
- Retries with exponential backoff (2^N seconds)
- Filters non-HTTPS URLs
- Timeout: 10 seconds per request
- Returns: status, HTML, content-type

### **Content Extractor** (`fetcher.py`)
- Parses HTML with BeautifulSoup + lxml
- Removes: `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, `<iframe>`
- Extracts: title, meta description, main text (first 5000 chars)
- Counts: outbound links, affiliate links, listicle patterns
- Word count for content length assessment

### **URL Canonicalizer** (`canonicalizer.py`)
- Normalizes URLs to prevent duplicates
- Removes tracking parameters (utm_*, fbclid, gclid, etc.)
- Converts to lowercase, removes fragments, sorts query params
- Computes SHA256 hash for O(1) lookups
- Three dedup layers:
  1. **Layer 1:** In-memory cache (≤200k URLs)
  2. **Layer 2:** Database unique index on url_hash
  3. **Layer 3:** Domain reputation (skip blacklisted domains)

---

## Language Model Integration

- **File:** `llm_client.py`
- **Provider:** NVIDIA AI Endpoints
- **Model:** `moonshotai/kimi-k2-instruct`
- **Temperature:** 0.6 (balanced reasoning)
- **Top-p:** 0.9 (nucleus sampling)
- **Max tokens:** 2048
- **Rate Limit:** 60 reasoning calls per hour (guardrail)

**Response Format:** Strict JSON
```json
{
  "reasoning": "Brief explanation of why this action...",
  "action": "search_web|browse_page|expand_keywords|deep_crawl|query_stats",
  "parameters": { "query": "...", "url": "...", "focus_vertical": "..." }
}
```

**Error Handling:**
- Fallback decision: random search from core vocabulary if LLM fails
- JSON parsing: tries direct parse, then markdown code blocks, then raw object extraction
- Retry with backoff on API errors

---

## Execution Flow (Simplified)

```
START agent_engine.py
  ↓
Initialize Database (seed keywords, load state)
  ↓
LOOP:
  ┌─────────────────────────────────────────┐
  │ CYCLE START (ReAct Loop)                │
  │                                         │
  │ 1. OBSERVE                              │
  │    - Load: URLs processed, prices      │
  │    - Load: top domains, recent prices  │
  │    - Build context prompt              │
  │                                         │
  │ 2. REASONING (up to 15 actions)         │
  │    ┌─ Ask LLM: "What next?"            │
  │    ├─ Receive JSON decision            │
  │    └─ Fallback on parse failure        │
  │                                         │
  │ 3. ACTION (one per step)                │
  │    ├─ search_web → [URLs]              │
  │    ├─ browse_page → [Content]          │
  │    ├─ score_page → [Score Result]      │
  │    ├─ expand_keywords → [Queries]      │
  │    ├─ deep_crawl → [Internal Links]    │
  │    └─ query_stats → [DB Stats]         │
  │                                         │
  │ 4. EVALUATE & PROCESS                  │
  │    For each URL found:                 │
  │    ├─ Canonicalize URL                 │
  │    ├─ Check dedup cache (3 layers)     │
  │    ├─ Check domain blacklist           │
  │    ├─ Fetch content                    │
  │    ├─ Extract text/title/links         │
  │    ├─ Score content                    │
  │    ├─ Update domain trust              │
  │    ├─ Extract prices (regex)           │
  │    └─ Insert competitor_prices record  │
  │                                         │
  │ 5. RECORD & FLUSH                      │
  │    - Save cycle yield (prices found)   │
  │    - Flush batch inserts to DB         │
  │    - Update keyword yield scores       │
  │                                         │
  │ 6. PERIODIC MAINTENANCE (every 100)    │
  │    - Archive URLs > 90 days            │
  │    - Apply 5% trust decay              │
  │    - Prune low-yield keywords          │
  │                                         │
  │ 7. SLEEP (1-25 min, randomized)        │
  └─────────────────────────────────────────┘
  ↓
UNTIL interrupted (Ctrl+C)
  ↓
SHUTDOWN
  - Flush remaining batch inserts
  - Close HTTP connections
  - Garbage collect
  - Print final stats
```

---

## Key Features

### ✅ **Autonomous Decision-Making**
- LLM-driven action selection via ReAct
- Adaptive query expansion based on low yield
- Self-aware: reads database state to inform decisions

### ✅ **Intelligent Deduplication**
- 3-layer URL dedup: in-memory (fast) → database (safe) → domain trust (quality)
- SHA256 canonicalization prevents variant duplicates
- Unique constraints in database

### ✅ **Domain Trust System**
- Automatic trust scoring (+2 per valid price, -3 per spam)
- Blacklisting for low-trust domains
- Monthly 5% decay to refresh sources
- Cascading: high-trust domains get bonus points

### ✅ **Rate Limiting & Safety**
- 8-12 sec randomized intervals between searches
- 600 sec (10 min) cooldown on 429/403/CAPTCHA
- 3 concurrent fetches max
- Max 10 queries per cycle
- LLM rate cap: 60 calls/hour

### ✅ **Multi-Factor Content Scoring**
- 9 scoring factors (entities, benefits, phrases, spam, links, listicles, affiliates, domain bonus)
- Deterministic (no LLM in scoring loop)
- O(text length) complexity

### ✅ **Price Extraction**
- 5 regex patterns for $, €, £, USD, EUR, GBP
- Deduplication by amount + currency
- Sanity bounds: 0.01 to 1M

### ✅ **Learn & Adapt**
- Co-occurrence learning: track term frequencies in valid pages
- Auto-promote terms that meet frequency thresholds
- Deprioritize low-yield keywords
- Capped learning (max 300 learned terms to prevent explosion)

### ✅ **Graceful Failure Recovery**
- Try/except wrapped execution
- Error counters trigger cooldown on 3+ errors
- Automatic retry with exponential backoff
- Fallback LLM decision on parse failure
- Atomic domain trust updates

---

## File Manifest

| File | Purpose |
|------|---------|
| `agent_engine.py` | Entry point, lifecycle management |
| `agent_core.py` | ReAct reasoning loop + evaluation |
| `agent_memory.py` | Database observation & context building |
| `agent_tools.py` | 6 callable tools (search, browse, score, expand, crawl, stats) |
| `database.py` | Supabase client + data models |
| `scorer.py` | Multi-factor scoring + price extraction |
| `config.py` | Vocabulary, limits, thresholds, timing |
| `scraper.py` | DuckDuckGo HTML scraper (rate-limited) |
| `fetcher.py` | Async HTTP fetch + content extraction |
| `canonicalizer.py` | URL normalization + dedup |
| `llm_client.py` | NVIDIA AI Endpoints client |
| `query_controller.py` | Query budget + keyword expansion + co-occurrence learning |
| `health.py` | HTTP health check server |
| `schema.sql` | Supabase table definitions |
| `.env` | Supabase credentials + NVIDIA API key |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Multi-container orchestration |

---

## Environment Variables

```bash
SUPABASE_URL=https://hqphepiyariufzvtvfre.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
NVIDIA_API_KEY=nvapi-...
```

---

## Execution

```bash
# Setup
cd retail-agent/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run agent
python3 agent_engine.py

# Docker
docker-compose up --build
```

---

## Monitoring & Logs

**Agent logs include:**
- Cycle #, timestamp, duration
- LLM latency per reasoning step
- Actions taken (search query, URLs found, prices stored)
- Hard rejections (spam, excess links, etc.)
- Domain trust updates
- Cumulative progress (cycles, prices, runtime)

**Typical cycle output:**
```
============================================================
[Agent] Cycle #52 | 2026-03-06T15:30:45.123456
============================================================
[Agent] Observing database state...
[Agent] Decision: search_web — Found low-yield queries...
[Scraper] Query: 'electronics discount price...' | Status: 200
[Scraper] Found 10 URLs
[Agent] Processing 10 search results...
[Agent] ✓ Price: https://amazon.com/dp/B0ABC123XYZ...
[Agent] Decision: expand_keywords — Generated 11 new...
...
[Agent] Cycle #52 complete: 8 actions, 3 prices, 12.4s

[AgentEngine] Cumulative: 52 cycles, 187 prices, runtime: 5:42:30
[AgentEngine] Sleeping 15 minutes...
```

---

## Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Typical cycle time** | 10-20 seconds | Depends on LLM latency (1-3 sec/call) & fetch times |
| **Cycle frequency** | 1-3 per hour | 45-75 min randomized sleep between cycles |
| **Concurrent fetches** | 3 max | Semaphore-controlled |
| **URL dedup cache** | ≤200k in-memory | Spills to DB beyond that |
| **Search rate limit** | 1 req / 8-12 sec | Randomized interval |
| **LLM calls/hour** | ≤60 | Hard cap to control costs |
| **Database writes** | Batched (50 at a time) | Minimizes round trips |
| **Memory growth** | Stable | Cache clears at 200k URLs |

---

## Summary

The **Retail Agent** is a production-ready, autonomous price monitoring system that:

1. **Searches** DuckDuckGo for competitor pricing pages
2. **Evaluates** page quality via multi-factor scoring
3. **Extracts** prices using regex patterns
4. **Stores** findings in Supabase with domain trust tracking
5. **Learns** from success/failure to refine future searches
6. **Reasons** via LLM about which verticals and keywords to explore next
7. **Operates** 24/7 with built-in rate limiting, error recovery, and safety guardrails

**Tech Stack:** Python 3.11, asyncio, Supabase, NVIDIA LLM, DuckDuckGo, aiohttp, BeautifulSoup, langchain

---

*Generated March 6, 2026*
