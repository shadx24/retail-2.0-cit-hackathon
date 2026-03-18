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
