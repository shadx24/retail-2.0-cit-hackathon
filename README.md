         # Student Benefits Scraper

A hardened, controlled web scraping system designed to discover student discount and benefit pages. Built with defensive architecture, bounded growth, and continuous safe operation guarantees.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│ CONTROLLED KEYWORD DATASET (Max 500 terms)                   │
│ ▸ Core static vocabulary (never removed)                     │
│ ▸ Dynamic learned terms (capped + thresholded)             │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ SYNONYM GRAPH (STATIC, Depth=1)                              │
│ ▸ Controlled term expansion only                           │
│ ▸ No recursive chaining                                      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ QUERY BUDGET CONTROLLER (Max 10/cycle)                       │
│ ▸ Randomized query selection                                 │
│ ▸ Yield tracking + deprioritization                          │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ DUCKDUCKGO SCRAPER (Hardened)                                │
│ ▸ 1 req / 8–12 sec (randomized)                            │
│ ▸ CAPTCHA detection + auto-cooldown                          │
│ ▸ Pagination limited to 1 page                               │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ URL CANONICALIZATION (SHA256)                                │
│ ▸ Remove tracking params, normalize HTTPS                    │
│ ▸ Hash-based deduplication                                   │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ MULTI-LAYER DEDUP ENGINE                                     │
│ ▸ Layer 1: In-memory hash set (O(1))                       │
│ ▸ Layer 2: Supabase UNIQUE index                           │
│ ▸ Layer 3: Domain blacklist (O(1))                           │
│ ▸ Batch inserts (size=50)                                    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ DOMAIN TRUST SCORING                                         │
│ ▸ +2 for valid offer, -3 for spam                            │
│ ▸ Auto-blacklist if score < -10                              │
│ ▸ 5% monthly decay                                           │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ ASYNC FETCH LAYER (Max 3 concurrent)                         │
│ ▸ 1 req/sec per worker                                       │
│ ▸ Timeout + retry (max 3)                                    │
│ ▸ Skip non-HTTPS                                             │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ CONTENT EXTRACTION                                             │
│ ▸ Main text extraction                                       │
│ ▸ Outbound link counting (< 30 threshold)                    │
│ ▸ Listicle pattern detection                                 │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ MULTI-FACTOR SCORING ENGINE                                  │
│ ▸ Entity + benefit + program phrase matching                 │
│ ▸ Domain trust bonus                                         │
│ ▸ Spam keyword + affiliate penalties                         │
│ ▸ Hard reject if spam_score ≥ 6                              │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ SUPABASE DATABASE                                            │
│ ▸ processed_urls (hash UNIQUE indexed)                       │
│ ▸ domains (trust_score indexed)                              │
│ ▸ offers (domain_id indexed)                                 │
│ ▸ keyword_pool + learned_terms                               │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ CONTROLLED CO-OCCURRENCE LEARNING                            │
│ ▸ Extract noun phrases                                       │
│ ▸ Promote only if ≥ 5 frequency + has benefit term         │
│ ▸ Max 10 promotions/cycle                                    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ KEYWORD PRUNING ENGINE                                       │
│ ▸ Remove low-yield terms (0 yield for 10 cycles)             │
│ ▸ Preserve core vocabulary                                   │
│ ▸ Run weekly                                                 │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ STABLE EXECUTION CONTROLLER                                  │
│ ▸ try/except wrapped cycles                                  │
│ ▸ Error logging + cooldown on failure                      │
│ ▸ Sleep 45–75 min randomized between cycles                  │
│ ▸ Memory cleanup per batch                                   │
└──────────────────────────────────────────────────────────────┘
```

## Project Structure

```
student_scraper/
├── config.py              # All limits, thresholds, vocabulary
├── database.py           # Supabase interface with caching
├── canonicalizer.py    # URL normalization + SHA256
├── scraper.py          # DuckDuckGo scraper (hardened)
├── fetcher.py          # Async HTTP + content extraction
├── scorer.py           # Multi-factor scoring engine
├── query_controller.py # Query budget + co-occurrence learning
├── engine.py           # Main execution controller
├── schema.sql          # Supabase DDL
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your Supabase credentials

# Initialize database
# Run schema.sql in Supabase SQL Editor
```

## Configuration

All hard limits are in `config.py`:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `MAX_KEYWORDS` | 500 | Total active keywords |
| `MAX_QUERIES_PER_CYCLE` | 10 | Search queries per cycle |
| `MAX_CONCURRENCY` | 3 | Concurrent fetch workers |
| `BATCH_SIZE` | 50 | Database batch insert size |
| `ARCHIVE_DAYS` | 90 | URL retention period |
| `MIN_SCORE_FOR_OFFER` | 4 | Valid offer threshold |
| `HARD_REJECT_SPAM_SCORE` | 6 | Auto-reject threshold |
| `BLACKLIST_DOMAIN_SCORE` | -10 | Domain blacklist threshold |

## Running

```bash
# Standard run
python engine.py

# With systemd (production)
systemctl enable student-scraper
systemctl start student-scraper
```

## System Guarantees

- **Deterministic**: Same query → same results
- **Bounded growth**: 500 keyword cap, 300 learned term cap
- **Self-learning**: Promotes terms from valid offers only
- **Low memory**: ~8MB per 100k URLs in-memory cache
- **Blocking-resistant**: Rate limits, randomized timing, auto-cooldown
- **Spam-resistant**: Multi-factor scoring, domain trust, hard rejects

## Monitoring

```sql
-- Get stats summary
select * from public.get_stats_summary();

-- Check active keywords
select * from keyword_pool where is_active = true order by yield_score desc;

-- View recent offers
select * from offers order by discovered_at desc limit 10;

-- Blacklisted domains
select * from domains where is_blacklisted = true;
```

## Multi-Factor Scoring

Weights (configurable in `config.py`):

```python
+2  Entity match (student, university, etc.)
+2  Benefit match (discount, offer, etc.)
+3  Program phrase match ("student discount")
+2  Trusted domain bonus
-2  Spam keyword penalty
-1  Excess outbound links
-2  Listicle pattern penalty
```

Offer must score ≥ 4 with spam_score < 6.

## Domain Trust Algorithm

```python
Initial score: 0
+2 for each valid offer found
-3 for spam detection
Monthly decay: 5%
Auto-blacklist if score < -10
```

## Query Yield Tracking

```
yield_score = 0.7 * old_score + 0.3 * (1 if results > 0 else 0)
Deprioritize after 5 consecutive zero-yield cycles
```

## Co-Occurrence Learning

Only promotes terms that:
1. Appear ≥ 5 times
2. Contain a benefit-type term
3. Not in spam blacklist
4. Under promotion cap (10/cycle)

## Troubleshooting

**Rate limited / CAPTCHA detected:**
- Automatic 10-minute cooldown triggers
- Check logs for `[Scraper] Cooldown active`

**No URLs found:**
- Verify keywords exist: `select count(*) from keyword_pool`
- Check query yield: `select * from keyword_pool order by yield_score`

**Memory usage high:**
- In-memory cache auto-clears at 200k entries
- Manual flush: restart process

## License

MIT. Use at your own risk. Respect robots.txt and ToS.
                     │
                              ▼
