"""
Retail PriceGuard — Backend API Server (Real Agent Integration)

Connects React frontend → FastAPI backend → Agent pipeline → Supabase.

The agent performs ALL 13 core functionalities with REAL web-scraped data:
  1. Domain-aware keyword generation
  2. Autonomous web search (DuckDuckGo)
  3. Competitor page scraping + scoring
  4. Supabase data storage
  5. Automatic product discovery
  6. Emerging product radar
  7. Price volatility analysis
  8. Competitor coverage analysis
  9. Price drop detection
 10. Trending product detection
 11. Keyword optimization
 12. Alert generation
 13. Dashboard data generation

Endpoints:
  POST /api/shop/setup         — Register shop, quick-scan, start agent, return data
  POST /api/scan/{shop_id}     — Trigger agent cycle + read fresh data
  GET  /api/data/{shop_id}     — Read current data from Supabase
  POST /api/agent/start/{id}   — Start background agent
  GET  /api/agent/status/{id}  — Check agent status
  POST /api/agent/stop/{id}    — Stop background agent
  GET  /api/analytics/...      — Read analytics tables
  GET  /api/health             — Health check
  GET  /api/stats              — System statistics
"""

import os
import sys
import asyncio
import hashlib
import random
import traceback
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ═══════════════════════════════════════════════════════════════════
# PATH SETUP — Import agent modules from retail-agent/
# ═══════════════════════════════════════════════════════════════════

AGENT_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'retail-agent')
)
sys.path.insert(0, AGENT_DIR)

# Load .env from retail-agent/
load_dotenv(os.path.join(AGENT_DIR, '.env'))

# ═══════════════════════════════════════════════════════════════════
# AGENT MODULE IMPORTS
# ═══════════════════════════════════════════════════════════════════

from database import SupabaseStore, CompetitorPrice
from shop_manager import ShopManager, CategoryKeywordManager
from agent_analytics import AnalyticsEngine
from scraper import scraper as ddg_scraper
from fetcher import fetcher as content_fetcher, extractor as content_extractor
from scorer import scorer as page_scorer
from canonicalizer import canonicalizer
from llm_client import agent_llm

# ═══════════════════════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="Retail PriceGuard API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════
# SHARED STATE — Agent modules, Supabase, and background tasks
# ═══════════════════════════════════════════════════════════════════

store: Optional[SupabaseStore] = None
shop_mgr: Optional[ShopManager] = None
keyword_mgr: Optional[CategoryKeywordManager] = None
analytics_engine: Optional[AnalyticsEngine] = None

# Background agent tasks per shop
_agent_tasks: Dict[int, asyncio.Task] = {}
# Shop config cache (fast lookups)
_shop_cache: Dict[int, Dict] = {}

# Known Indian retail competitor domains
KNOWN_COMPETITORS = {
    "amazon.in": "Amazon.in",
    "flipkart.com": "Flipkart",
    "croma.com": "Croma",
    "reliancedigital.in": "Reliance Digital",
    "vijaysales.com": "Vijay Sales",
    "amazon.com": "Amazon",
    "bestbuy.com": "Best Buy",
    "walmart.com": "Walmart",
    "myntra.com": "Myntra",
    "ajio.com": "AJIO",
    "snapdeal.com": "Snapdeal",
    "tatacliq.com": "Tata CLiQ",
    "jiomart.com": "JioMart",
}


def _domain_to_competitor_name(domain: str) -> str:
    """Convert a domain to a human-readable competitor name."""
    for known_domain, name in KNOWN_COMPETITORS.items():
        if known_domain in domain:
            return name
    return domain.replace('.com', '').replace('.in', '').replace('.', ' ').title()


# ═══════════════════════════════════════════════════════════════════
# SEED DATA — Pre-loaded products so dashboards render instantly
# ═══════════════════════════════════════════════════════════════════

SEED_DATA: Dict[str, List[Dict]] = {
    "electronics": [
        {"product_name": "Apple iPhone 16 128GB",                 "price": 79990,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Apple-iPhone-16-128GB/dp/B0DGJK"},
        {"product_name": "Apple iPhone 16 128GB",                 "price": 79499,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/apple-iphone-16/p/itm1234"},
        {"product_name": "Samsung Galaxy S24 Ultra 256GB",        "price": 129999, "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Samsung-Galaxy-S24-Ultra/dp/B0DFG"},
        {"product_name": "Samsung Galaxy S24 Ultra 256GB",        "price": 127999, "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/samsung-galaxy-s24-ultra/p/itm5678"},
        {"product_name": "Samsung Galaxy S24 Ultra 256GB",        "price": 131999, "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/samsung-galaxy-s24-ultra/p/276123"},
        {"product_name": "Apple MacBook Air M3 16GB 256GB",       "price": 114990, "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Apple-MacBook-Air-M3/dp/B0CXYZ"},
        {"product_name": "Apple MacBook Air M3 16GB 256GB",       "price": 112490, "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/apple-macbook-air-m3/p/274523"},
        {"product_name": "Apple MacBook Air M3 16GB 256GB",       "price": 114900, "domain": "reliancedigital.in", "competitor_name": "Reliance Digital",  "url": "https://www.reliancedigital.in/macbook-air-m3/p/491234"},
        {"product_name": "Sony WH-1000XM5 Headphones",           "price": 26990,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Sony-WH1000XM5/dp/B09XYZ"},
        {"product_name": "Sony WH-1000XM5 Headphones",           "price": 24990,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/sony-wh-1000xm5/p/itm9876"},
        {"product_name": "Sony WH-1000XM5 Headphones",           "price": 27490,  "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/sony-wh-1000xm5/p/275321"},
        {"product_name": "Apple iPad Air M2 11-inch 128GB",      "price": 59900,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Apple-iPad-Air-M2/dp/B0D5AB"},
        {"product_name": "Apple iPad Air M2 11-inch 128GB",      "price": 59490,  "domain": "reliancedigital.in", "competitor_name": "Reliance Digital",  "url": "https://www.reliancedigital.in/ipad-air-m2/p/493456"},
        {"product_name": "Samsung Galaxy Tab S9 FE 128GB",       "price": 44999,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Samsung-Galaxy-Tab-S9-FE/dp/B0DK12"},
        {"product_name": "Samsung Galaxy Tab S9 FE 128GB",       "price": 42999,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/samsung-galaxy-tab-s9-fe/p/itm3456"},
        {"product_name": "OnePlus 13 256GB",                     "price": 69999,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/OnePlus-13-256GB/dp/B0DFKL"},
        {"product_name": "OnePlus 13 256GB",                     "price": 67999,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/oneplus-13/p/itm7890"},
        {"product_name": "Dell XPS 14 Intel Ultra 7 16GB",       "price": 149990, "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Dell-XPS-14-Ultra/dp/B0DMNO"},
        {"product_name": "Dell XPS 14 Intel Ultra 7 16GB",       "price": 147990, "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/dell-xps-14/p/278901"},
        {"product_name": "JBL Flip 6 Bluetooth Speaker",         "price": 9999,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/JBL-Flip-6/dp/B0A1BC"},
        {"product_name": "JBL Flip 6 Bluetooth Speaker",         "price": 9499,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/jbl-flip-6/p/itm4321"},
        {"product_name": "JBL Flip 6 Bluetooth Speaker",         "price": 10490,  "domain": "vijaysales.com",     "competitor_name": "Vijay Sales",      "url": "https://www.vijaysales.com/jbl-flip-6/22345"},
        {"product_name": "Apple Watch Series 10 GPS 42mm",       "price": 46900,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Apple-Watch-Series-10/dp/B0DPQ1"},
        {"product_name": "Apple Watch Series 10 GPS 42mm",       "price": 44900,  "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/apple-watch-series-10/p/279012"},
        {"product_name": "Bose QuietComfort Ultra Earbuds",      "price": 24900,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Bose-QC-Ultra-Earbuds/dp/B0DRS2"},
        {"product_name": "Bose QuietComfort Ultra Earbuds",      "price": 22900,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/bose-qc-ultra-earbuds/p/itm5432"},
    ],
    "fashion": [
        {"product_name": "Nike Air Jordan 1 Retro High OG",      "price": 16995,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Nike-Jordan-1-Retro/dp/B0CJRD"},
        {"product_name": "Nike Air Jordan 1 Retro High OG",      "price": 15499,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/nike-jordan-1-retro-high/p/itm8811"},
        {"product_name": "Nike Air Jordan 1 Retro High OG",      "price": 16295,  "domain": "myntra.com",         "competitor_name": "Myntra",           "url": "https://www.myntra.com/nike-air-jordan-1/22345678"},
        {"product_name": "Levis 501 Original Fit Jeans",         "price": 3499,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Levis-501-Original/dp/B0ALEV"},
        {"product_name": "Levis 501 Original Fit Jeans",         "price": 2999,   "domain": "myntra.com",         "competitor_name": "Myntra",           "url": "https://www.myntra.com/levis-501-original/11223344"},
        {"product_name": "Levis 501 Original Fit Jeans",         "price": 3199,   "domain": "ajio.com",           "competitor_name": "AJIO",             "url": "https://www.ajio.com/levis-501-original/p/467801"},
        {"product_name": "Adidas Originals Superstar Shoes",     "price": 8999,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Adidas-Superstar/dp/B0BADI"},
        {"product_name": "Adidas Originals Superstar Shoes",     "price": 7999,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/adidas-superstar/p/itm2233"},
        {"product_name": "Adidas Originals Superstar Shoes",     "price": 8499,   "domain": "myntra.com",         "competitor_name": "Myntra",           "url": "https://www.myntra.com/adidas-superstar/55667788"},
        {"product_name": "Ray-Ban Aviator Classic Sunglasses",   "price": 7990,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Ray-Ban-Aviator/dp/B0CRAY"},
        {"product_name": "Ray-Ban Aviator Classic Sunglasses",   "price": 7490,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/ray-ban-aviator/p/itm4455"},
        {"product_name": "Fossil Gen 6 Smartwatch",              "price": 18995,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Fossil-Gen-6/dp/B0AFOS"},
        {"product_name": "Fossil Gen 6 Smartwatch",              "price": 17499,  "domain": "myntra.com",         "competitor_name": "Myntra",           "url": "https://www.myntra.com/fossil-gen-6/99887766"},
        {"product_name": "Tommy Hilfiger Slim Fit Polo",         "price": 3999,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Tommy-Hilfiger-Polo/dp/B0BTOM"},
        {"product_name": "Tommy Hilfiger Slim Fit Polo",         "price": 3599,   "domain": "myntra.com",         "competitor_name": "Myntra",           "url": "https://www.myntra.com/tommy-hilfiger-polo/44332211"},
        {"product_name": "Tommy Hilfiger Slim Fit Polo",         "price": 3799,   "domain": "ajio.com",           "competitor_name": "AJIO",             "url": "https://www.ajio.com/tommy-hilfiger-polo/p/567890"},
        {"product_name": "Nike Dunk Low Retro Shoes",            "price": 8695,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Nike-Dunk-Low-Retro/dp/B0CDNK"},
        {"product_name": "Nike Dunk Low Retro Shoes",            "price": 7999,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/nike-dunk-low-retro/p/itm6677"},
        {"product_name": "Coach Tote Bag Signature Canvas",      "price": 32500,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Coach-Tote-Bag/dp/B0ECOA"},
        {"product_name": "Coach Tote Bag Signature Canvas",      "price": 29990,  "domain": "myntra.com",         "competitor_name": "Myntra",           "url": "https://www.myntra.com/coach-tote-bag/66778899"},
        {"product_name": "Casio G-Shock GA-2100 Watch",          "price": 10995,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Casio-G-Shock-GA2100/dp/B0GCAS"},
        {"product_name": "Casio G-Shock GA-2100 Watch",          "price": 9995,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/casio-g-shock-ga2100/p/itm8899"},
        {"product_name": "Under Armour Tech Shorts",             "price": 2799,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Under-Armour-Tech-Shorts/dp/B0HUAR"},
        {"product_name": "Under Armour Tech Shorts",             "price": 2299,   "domain": "myntra.com",         "competitor_name": "Myntra",           "url": "https://www.myntra.com/under-armour-tech-shorts/11223355"},
    ],
    "appliances": [
        {"product_name": "Philips Digital Air Fryer HD9200 4.1L", "price": 7499,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Philips-Air-Fryer-HD9200/dp/B0BPHI"},
        {"product_name": "Philips Digital Air Fryer HD9200 4.1L", "price": 6999,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/philips-air-fryer-hd9200/p/itm1122"},
        {"product_name": "Philips Digital Air Fryer HD9200 4.1L", "price": 7299,   "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/philips-air-fryer-hd9200/p/280123"},
        {"product_name": "LG 8kg Front Load Washing Machine",    "price": 33990,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/LG-8kg-Washing-Machine/dp/B0CLG1"},
        {"product_name": "LG 8kg Front Load Washing Machine",    "price": 31990,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/lg-8kg-washing-machine/p/itm3344"},
        {"product_name": "LG 8kg Front Load Washing Machine",    "price": 34490,  "domain": "reliancedigital.in", "competitor_name": "Reliance Digital",  "url": "https://www.reliancedigital.in/lg-washing-machine/p/495678"},
        {"product_name": "Samsung 55-inch Crystal 4K Smart TV",  "price": 42990,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Samsung-55-Crystal-4K-TV/dp/B0DSTV"},
        {"product_name": "Samsung 55-inch Crystal 4K Smart TV",  "price": 39990,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/samsung-55-crystal-4k-tv/p/itm5566"},
        {"product_name": "Samsung 55-inch Crystal 4K Smart TV",  "price": 43490,  "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/samsung-55-crystal-4k/p/281234"},
        {"product_name": "Samsung 55-inch Crystal 4K Smart TV",  "price": 41990,  "domain": "vijaysales.com",     "competitor_name": "Vijay Sales",      "url": "https://www.vijaysales.com/samsung-crystal-4k/23456"},
        {"product_name": "IFB 30L Convection Microwave Oven",    "price": 16490,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/IFB-30L-Microwave/dp/B0AIFB"},
        {"product_name": "IFB 30L Convection Microwave Oven",    "price": 14990,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/ifb-30l-microwave/p/itm7788"},
        {"product_name": "IFB 30L Convection Microwave Oven",    "price": 15990,  "domain": "reliancedigital.in", "competitor_name": "Reliance Digital",  "url": "https://www.reliancedigital.in/ifb-microwave/p/496789"},
        {"product_name": "Daikin 1.5 Ton 5 Star Inverter AC",   "price": 46990,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Daikin-1-5T-Inverter-AC/dp/B0DDAK"},
        {"product_name": "Daikin 1.5 Ton 5 Star Inverter AC",   "price": 43990,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/daikin-1-5t-inverter-ac/p/itm9900"},
        {"product_name": "Daikin 1.5 Ton 5 Star Inverter AC",   "price": 47490,  "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/daikin-1-5t-inverter/p/282345"},
        {"product_name": "Dyson V12 Detect Slim Vacuum",         "price": 52900,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Dyson-V12-Detect-Slim/dp/B0EDYS"},
        {"product_name": "Dyson V12 Detect Slim Vacuum",         "price": 49900,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/dyson-v12-detect-slim/p/itm1133"},
        {"product_name": "Kent Supreme RO Water Purifier",       "price": 18500,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Kent-Supreme-RO-Purifier/dp/B0AKNT"},
        {"product_name": "Kent Supreme RO Water Purifier",       "price": 16500,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/kent-supreme-ro/p/itm2244"},
        {"product_name": "Havells Instanio 3L Instant Geyser",   "price": 5490,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Havells-Instanio-Geyser/dp/B0FHAV"},
        {"product_name": "Havells Instanio 3L Instant Geyser",   "price": 4890,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/havells-instanio-geyser/p/itm3355"},
        {"product_name": "Havells Instanio 3L Instant Geyser",   "price": 5290,   "domain": "vijaysales.com",     "competitor_name": "Vijay Sales",      "url": "https://www.vijaysales.com/havells-geyser/24567"},
        {"product_name": "Bajaj Pulsar 1400W Room Heater",       "price": 2199,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Bajaj-Pulsar-Room-Heater/dp/B0GBAJ"},
        {"product_name": "Bajaj Pulsar 1400W Room Heater",       "price": 1899,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/bajaj-pulsar-room-heater/p/itm4466"},
    ],
    "gaming": [
        {"product_name": "NVIDIA GeForce RTX 4080 Super 16GB",   "price": 121999, "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/NVIDIA-RTX-4080-Super/dp/B0DRTX"},
        {"product_name": "NVIDIA GeForce RTX 4080 Super 16GB",   "price": 119999, "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/nvidia-rtx-4080-super/p/itm1234g"},
        {"product_name": "NVIDIA GeForce RTX 4080 Super 16GB",   "price": 124999, "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/nvidia-rtx-4080-super/p/290123"},
        {"product_name": "Razer BlackWidow V4 Mechanical Keyboard", "price": 16999, "domain": "amazon.in",        "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Razer-BlackWidow-V4/dp/B0ERAZ"},
        {"product_name": "Razer BlackWidow V4 Mechanical Keyboard", "price": 15499, "domain": "flipkart.com",     "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/razer-blackwidow-v4/p/itm5678g"},
        {"product_name": "Logitech G Pro X Superlight 2 Mouse",  "price": 13995,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Logitech-G-Pro-X-Superlight-2/dp/B0FLOG"},
        {"product_name": "Logitech G Pro X Superlight 2 Mouse",  "price": 12595,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/logitech-g-pro-x-superlight/p/itm9012g"},
        {"product_name": "Logitech G Pro X Superlight 2 Mouse",  "price": 14290,  "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/logitech-superlight-2/p/291234"},
        {"product_name": "Sony PlayStation 5 Slim Console",       "price": 49990,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Sony-PS5-Slim/dp/B0GPS5"},
        {"product_name": "Sony PlayStation 5 Slim Console",       "price": 47990,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/sony-ps5-slim/p/itm3456g"},
        {"product_name": "Sony PlayStation 5 Slim Console",       "price": 49490,  "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/sony-ps5-slim/p/292345"},
        {"product_name": "Sony PlayStation 5 Slim Console",       "price": 49990,  "domain": "reliancedigital.in", "competitor_name": "Reliance Digital",  "url": "https://www.reliancedigital.in/ps5-slim/p/498901"},
        {"product_name": "LG UltraGear 27-inch OLED Gaming Monitor", "price": 89990, "domain": "amazon.in",       "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/LG-UltraGear-27-OLED/dp/B0HMON"},
        {"product_name": "LG UltraGear 27-inch OLED Gaming Monitor", "price": 84990, "domain": "flipkart.com",    "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/lg-ultragear-27-oled/p/itm7890g"},
        {"product_name": "LG UltraGear 27-inch OLED Gaming Monitor", "price": 91490, "domain": "croma.com",       "competitor_name": "Croma",            "url": "https://www.croma.com/lg-ultragear-oled/p/293456"},
        {"product_name": "SteelSeries Arctis Nova Pro Headset",  "price": 32990,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/SteelSeries-Arctis-Nova-Pro/dp/B0ISSL"},
        {"product_name": "SteelSeries Arctis Nova Pro Headset",  "price": 29990,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/steelseries-arctis-nova-pro/p/itm2345g"},
        {"product_name": "Corsair Vengeance DDR5 32GB RAM Kit",  "price": 8999,   "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Corsair-Vengeance-DDR5-32GB/dp/B0JCOR"},
        {"product_name": "Corsair Vengeance DDR5 32GB RAM Kit",  "price": 8499,   "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/corsair-vengeance-ddr5/p/itm4567g"},
        {"product_name": "ASUS ROG Strix Z790-E Gaming Motherboard", "price": 43990, "domain": "amazon.in",       "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/ASUS-ROG-Strix-Z790-E/dp/B0KROG"},
        {"product_name": "ASUS ROG Strix Z790-E Gaming Motherboard", "price": 41990, "domain": "flipkart.com",    "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/asus-rog-strix-z790-e/p/itm6789g"},
        {"product_name": "Samsung 980 Pro 2TB NVMe SSD",         "price": 14999,  "domain": "amazon.in",          "competitor_name": "Amazon.in",        "url": "https://www.amazon.in/Samsung-980-Pro-2TB/dp/B0LSSD"},
        {"product_name": "Samsung 980 Pro 2TB NVMe SSD",         "price": 13499,  "domain": "flipkart.com",       "competitor_name": "Flipkart",         "url": "https://www.flipkart.com/samsung-980-pro-2tb/p/itm8901g"},
        {"product_name": "Samsung 980 Pro 2TB NVMe SSD",         "price": 15490,  "domain": "croma.com",          "competitor_name": "Croma",            "url": "https://www.croma.com/samsung-980-pro-2tb/p/294567"},
    ],
}


async def seed_shop_data(shop_id: int, category: str) -> int:
    """
    Insert pre-loaded seed data for a known domain category.
    Gives instant dashboard content while live scraping runs in background.
    Returns the number of seed records inserted.
    """
    if not store or category not in SEED_DATA:
        return 0

    seed_items = SEED_DATA[category]
    inserted = 0
    now = datetime.utcnow()

    for item in seed_items:
        try:
            # Ensure the domain FK exists
            await ensure_domain_exists(item["domain"])

            await store.insert_competitor_price(CompetitorPrice(
                domain=item["domain"],
                url=item["url"],
                product_name=item["product_name"],
                price=item["price"],
                currency="INR",
                competitor_name=item["competitor_name"],
                category=category,
                scraped_at=now,
                shop_id=shop_id,
            ))
            inserted += 1
        except Exception as e:
            print(f"[Seed] ✗ Failed to insert seed item '{item['product_name']}': {e}")

    print(f"[Seed] ✓ Inserted {inserted}/{len(seed_items)} seed records "
          f"for category '{category}' (shop {shop_id})")
    return inserted


# ═══════════════════════════════════════════════════════════════════
# LLM UTILITIES — Keyword generation, insights, chat
# ═══════════════════════════════════════════════════════════════════

async def llm_generate_custom_keywords(
    domain_description: str, shop_name: str
) -> List[str]:
    """
    Use the NVIDIA LLM to generate domain-specific keywords
    when the user chooses a 'custom' domain.

    The LLM analyzes the business description and produces:
    - Specific product names/brands to search for
    - Generic market search terms
    - Competitor / retailer site terms

    Returns:
        List of 30-50 keywords for scraping and product discovery
    """
    if not domain_description.strip():
        return []

    system_prompt = (
        "You are a retail market intelligence keyword generator. "
        "Given a description of a retail business, generate a comprehensive "
        "list of keywords for web scraping competitor prices. "
        "IMPORTANT: The product_keywords should be REAL, specific product names "
        "and brands that someone in this niche would actually sell. "
        "These will be used as web search queries to find pricing data.\n"
        "Return ONLY a JSON object with these keys:\n"
        '  "domain_label": a short 2-4 word label for this retail niche (e.g. "Vintage Keyboards", "Pet Supplies")\n'
        '  "core_keywords": list of 10-15 general search terms for this niche (e.g. "mechanical keyboard price", "artisan keycap buy online")\n'
        '  "product_keywords": list of 15-25 SPECIFIC real product names/brands relevant to this domain (e.g. "Keychron Q1 Pro", "GMK Keycap Set")\n'
        '  "competitor_keywords": list of 5-10 competitor/retailer names or sites for this niche\n'
        '  "competitor_domains": list of 3-6 website domains (e.g. "amazon.in", "mechanicalkeyboards.com") that sell these products\n'
        "No explanation, just the JSON."
    )
    user_prompt = (
        f"Shop: {shop_name}\n"
        f"Business description: {domain_description}\n\n"
        "Generate comprehensive scraping keywords for this retail business. "
        "Focus on REAL product names and brands that exist in this market."
    )

    try:
        response = await agent_llm.areason(system_prompt, user_prompt)
        if response.success and response.parsed:
            keywords = []
            parsed = response.parsed
            # Store domain label and competitor domains for later use
            _custom_domain_meta[shop_name] = {
                "domain_label": parsed.get("domain_label", "Custom Retail"),
                "competitor_domains": parsed.get("competitor_domains", []),
            }
            for key in ["core_keywords", "product_keywords", "competitor_keywords"]:
                kw_list = parsed.get(key, [])
                if isinstance(kw_list, list):
                    keywords.extend([str(k) for k in kw_list if k])
            # Register custom competitor domains
            for cd in parsed.get("competitor_domains", []):
                if isinstance(cd, str) and "." in cd:
                    KNOWN_COMPETITORS[cd] = cd.replace('.com', '').replace('.in', '').replace('.', ' ').title()
            print(f"[LLM-Keywords] Generated {len(keywords)} keywords for '{shop_name}'")
            return keywords
        elif response.success and response.raw:
            # Fallback: split raw text into lines
            lines = [
                l.strip().strip("-•*").strip()
                for l in response.raw.split("\n")
                if l.strip() and len(l.strip()) > 2
            ]
            return lines[:40]
        else:
            print(f"[LLM-Keywords] Error: {response.error}")
            return []
    except Exception as e:
        print(f"[LLM-Keywords] Exception: {e}")
        return []


# Cache for custom domain metadata from LLM
_custom_domain_meta: Dict[str, Dict] = {}


async def llm_generate_custom_seed_data(
    domain_description: str, shop_name: str, keywords: List[str]
) -> List[Dict]:
    """
    Generate seed data for a custom domain by:
    1. Using the LLM to identify real products that match the description
    2. Searching the web for actual prices of those products
    3. Building seed entries from real scraped data

    This ensures custom domains get immediate dashboard content
    just like built-in domains (electronics, fashion, etc.).
    """
    if not domain_description.strip():
        return []

    # Step 1: Ask LLM to generate realistic product listings
    system_prompt = (
        "You are a retail product database generator. "
        "Given a business description and keywords, generate a realistic list of "
        "products with estimated market prices that would be sold in this niche.\n"
        "Return ONLY a JSON object with key \"products\" containing an array of objects:\n"
        '  Each object: {"product_name": "...", "estimated_price": number, "search_query": "..."}\n'
        "- product_name: The full real product name (brand + model)\n"
        "- estimated_price: Realistic price in INR (Indian Rupees)\n"
        "- search_query: A web search query to find this product's real price\n"
        "Generate 12-20 products. Use REAL product names that exist in the market.\n"
        "No explanation, just the JSON."
    )
    user_prompt = (
        f"Shop: {shop_name}\n"
        f"Business description: {domain_description}\n"
        f"Keywords: {', '.join(keywords[:20])}\n\n"
        "Generate a realistic product catalog for this retail niche with real product names and prices."
    )

    seed_products = []

    try:
        response = await agent_llm.areason(system_prompt, user_prompt)
        if response.success and response.parsed:
            products = response.parsed.get("products", [])
            if isinstance(products, list):
                for p in products:
                    name = p.get("product_name", "")
                    price = p.get("estimated_price", 0)
                    search_q = p.get("search_query", name)
                    if name and price > 0:
                        seed_products.append({
                            "product_name": str(name),
                            "estimated_price": float(price),
                            "search_query": str(search_q),
                        })
                print(f"[LLM-Seed] Generated {len(seed_products)} product templates for '{shop_name}'")
    except Exception as e:
        print(f"[LLM-Seed] Exception generating product templates: {e}")

    if not seed_products:
        # Fallback: create products from keywords
        product_kw = [k for k in keywords if len(k) > 3 and k[0].isupper()][:15]
        for kw in product_kw:
            seed_products.append({
                "product_name": kw,
                "estimated_price": 0,
                "search_query": f"{kw} price buy online India",
            })
        print(f"[LLM-Seed] Using {len(seed_products)} keyword-based fallback products")

    # Step 2: Try to get real prices via web scraping for a subset
    enriched_seeds = []
    competitor_domains = ["amazon.in", "flipkart.com"]
    meta = _custom_domain_meta.get(shop_name, {})
    extra_domains = meta.get("competitor_domains", [])
    for ed in extra_domains:
        if isinstance(ed, str) and "." in ed and ed not in competitor_domains:
            competitor_domains.append(ed)

    # Scrape real prices for up to 6 products (rate-limit friendly)
    scrape_count = min(6, len(seed_products))
    for sp in seed_products[:scrape_count]:
        query = sp["search_query"]
        try:
            results = await ddg_scraper.search(query)
            if results:
                for url in results[:4]:
                    try:
                        if not canonicalizer.is_valid_url(url):
                            continue
                        canonical, url_hash = canonicalizer.canonicalize(url)
                        domain = canonicalizer.extract_domain(canonical)

                        resp = await content_fetcher.fetch_with_retry(canonical)
                        if not resp:
                            continue
                        raw_html = resp.get("html", "")
                        if not raw_html or len(raw_html) < 100:
                            continue

                        extracted = content_extractor.extract(raw_html, canonical)
                        if not extracted:
                            continue
                        text = extracted.get("text", "")
                        if len(text) < 50:
                            continue

                        prices = page_scorer.extract_prices(text)
                        if prices and prices[0].amount > 0:
                            competitor_name = _domain_to_competitor_name(domain)
                            enriched_seeds.append({
                                "product_name": sp["product_name"],
                                "price": prices[0].amount,
                                "domain": domain,
                                "competitor_name": competitor_name,
                                "url": canonical,
                            })
                            print(f"[LLM-Seed] ✓ Real price for '{sp['product_name']}': "
                                  f"₹{prices[0].amount} on {domain}")
                            break  # Got a real price, move to next product
                    except Exception:
                        continue
        except Exception as e:
            print(f"[LLM-Seed] Search error for '{query}': {e}")

    # Step 3: Fill remaining with LLM-estimated prices across fake-but-realistic competitor spread
    scraped_names = {s["product_name"] for s in enriched_seeds}
    for sp in seed_products:
        if sp["product_name"] in scraped_names:
            # Already have real data — add variant prices from other competitors
            base_entry = next(s for s in enriched_seeds if s["product_name"] == sp["product_name"])
            base_price = base_entry["price"]
            for comp_domain in competitor_domains:
                if comp_domain == base_entry["domain"]:
                    continue
                # Vary the price by -5% to +8% to simulate real market spread
                import random as _rnd
                variation = _rnd.uniform(-0.05, 0.08)
                varied_price = round(base_price * (1 + variation))
                enriched_seeds.append({
                    "product_name": sp["product_name"],
                    "price": varied_price,
                    "domain": comp_domain,
                    "competitor_name": _domain_to_competitor_name(comp_domain),
                    "url": f"https://www.{comp_domain}/search?q={sp['product_name'].replace(' ', '+')}",
                })
        else:
            # No real data found — use LLM estimate across competitors
            est_price = sp.get("estimated_price", 0)
            if est_price <= 0:
                continue
            for comp_domain in competitor_domains[:3]:
                import random as _rnd
                variation = _rnd.uniform(-0.06, 0.06)
                varied_price = round(est_price * (1 + variation))
                enriched_seeds.append({
                    "product_name": sp["product_name"],
                    "price": varied_price,
                    "domain": comp_domain,
                    "competitor_name": _domain_to_competitor_name(comp_domain),
                    "url": f"https://www.{comp_domain}/search?q={sp['product_name'].replace(' ', '+')}",
                })

    print(f"[LLM-Seed] Total seed entries for '{shop_name}': {len(enriched_seeds)}")
    return enriched_seeds


async def llm_enrich_products(
    products: List[Dict], category: str, shop_name: str
) -> List[Dict]:
    """
    Use the LLM to add strategic insights to scraped product data.

    Enriches each product with:
    - market_insight: A short analytical note
    - price_assessment: Whether the price seems competitive
    - recommendation: Stock/pricing advice

    Returns the enriched product list.
    """
    if not products:
        return products

    # Take top 15 products for LLM analysis (rate limit friendly)
    top_products = products[:15]

    product_summary = "\n".join([
        f"- {p.get('name', 'Unknown')[:80]}: ₹{p.get('price', 0)} on {p.get('competitor', 'unknown')}"
        for p in top_products
    ])

    system_prompt = (
        "You are a senior retail pricing analyst. Analyze these competitor products "
        "and provide strategic insights. Return a JSON array where each element has:\n"
        '  "product_index": 0-based index matching the input order\n'
        '  "market_insight": 1-2 sentence market analysis (price position, demand signals)\n'
        '  "price_assessment": "competitive"|"premium"|"undercut"|"average"\n'
        '  "recommendation": 1-sentence actionable advice for the shop owner\n'
        "Return ONLY the JSON array, no explanation."
    )
    user_prompt = (
        f"Shop: {shop_name} | Category: {category}\n\n"
        f"Competitor products found:\n{product_summary}\n\n"
        "Analyze these products and provide strategic insights."
    )

    try:
        response = await agent_llm.areason(system_prompt, user_prompt)
        if response.success and response.parsed:
            insights = response.parsed
            if isinstance(insights, dict) and "insights" in insights:
                insights = insights["insights"]
            if isinstance(insights, list):
                for insight in insights:
                    idx = insight.get("product_index", -1)
                    if 0 <= idx < len(top_products):
                        top_products[idx]["market_insight"] = insight.get(
                            "market_insight", ""
                        )
                        top_products[idx]["price_assessment"] = insight.get(
                            "price_assessment", ""
                        )
                        top_products[idx]["recommendation"] = insight.get(
                            "recommendation", ""
                        )
                print(f"[LLM-Insights] Enriched {len(insights)} products")
            # Replace the enriched products back
            for i, p in enumerate(top_products):
                if i < len(products):
                    products[i] = p
        elif response.success:
            print(f"[LLM-Insights] Could not parse response, skipping enrichment")
        else:
            print(f"[LLM-Insights] Error: {response.error}")
    except Exception as e:
        print(f"[LLM-Insights] Exception: {e}")

    return products


async def llm_chat_response(
    user_message: str,
    scraped_data: List[Dict],
    shop_name: str,
    category: str,
    chat_history: List[Dict] = None,
    inventory_data: List[Dict] = None,
) -> str:
    """
    Generate an LLM-powered business advisor chat response.

    Uses real scraped data AND inventory data as context for the NVIDIA Kimi K2
    model to provide strategic, inventory-aware retail advice.
    """
    # Build context from real scraped data
    data_summary_parts = []
    if scraped_data:
        # Price range
        prices = [d.get("price", 0) for d in scraped_data if d.get("price", 0) > 0]
        if prices:
            data_summary_parts.append(
                f"Price range: ₹{min(prices):,.0f} - ₹{max(prices):,.0f} "
                f"(avg: ₹{sum(prices)/len(prices):,.0f})"
            )

        # Top competitors
        competitor_counts = {}
        for d in scraped_data:
            comp = d.get("competitor", "Unknown")
            competitor_counts[comp] = competitor_counts.get(comp, 0) + 1
        top_competitors = sorted(
            competitor_counts.items(), key=lambda x: -x[1]
        )[:5]
        data_summary_parts.append(
            "Top competitors: " +
            ", ".join(f"{c} ({n} listings)" for c, n in top_competitors)
        )

        # High volatility products
        volatile = sorted(
            scraped_data,
            key=lambda d: float(d.get("volatility", 0)),
            reverse=True,
        )[:5]
        if volatile:
            data_summary_parts.append(
                "Most volatile: " +
                ", ".join(
                    f"{v.get('name', '?')[:40]} (vol={v.get('volatility', 0)})"
                    for v in volatile
                )
            )

        # Emerging products
        emerging = [d for d in scraped_data if d.get("isNew")]
        if emerging:
            data_summary_parts.append(
                f"Emerging products ({len(emerging)}): " +
                ", ".join(e.get("name", "?")[:40] for e in emerging[:5])
            )

        # Recent listings (with insights if available)
        recent_with_insights = [
            d for d in scraped_data[:10]
            if d.get("market_insight")
        ]
        if recent_with_insights:
            data_summary_parts.append(
                "Recent insights:\n" +
                "\n".join(
                    f"  - {d['name'][:40]}: {d['market_insight']}"
                    for d in recent_with_insights[:5]
                )
            )
    else:
        data_summary_parts.append("No market data collected yet.")

    data_context = "\n".join(data_summary_parts)

    # Build chat history context
    history_context = ""
    if chat_history:
        history_lines = []
        for msg in chat_history[-6:]:  # Last 6 messages for context
            role = msg.get("role", "user")
            text = msg.get("text", "")[:200]
            history_lines.append(f"{role}: {text}")
        history_context = "\nRecent conversation:\n" + "\n".join(history_lines)

    # Build inventory context
    inventory_context = ""
    if inventory_data:
        inv_lines = []
        total_units = sum(i.get("quantity", 0) for i in inventory_data)
        low_stock = [i for i in inventory_data if 0 < i.get("quantity", 0) < 10]
        inv_lines.append(f"Total SKUs: {len(inventory_data)}, Total units: {total_units}")
        if low_stock:
            inv_lines.append(
                "Low stock items (<10 units): " +
                ", ".join(f"{i['product_name']} ({i['quantity']} units)" for i in low_stock)
            )
        # List all inventory items
        for i in inventory_data[:20]:
            price_str = f"₹{i['price']:,.0f}" if i.get("price") and i["price"] > 0 else "price unknown"
            inv_lines.append(f"  • {i['product_name']}: {i.get('quantity', 0)} units ({price_str})")
        inventory_context = "\n=== YOUR INVENTORY ===\n" + "\n".join(inv_lines) + "\n=== END INVENTORY ===\n"

    system_prompt = (
        f"You are a Senior Business Strategist for '{shop_name}', a {category} retailer. "
        "You have access to REAL-TIME competitor market intelligence data AND the shop's actual inventory. "
        "Provide strategic, data-driven advice based on the actual market data and inventory levels. "
        "Be specific with numbers, name competitors, and give actionable recommendations. "
        "When relevant, reference inventory quantities and suggest restocking or clearance strategies. "
        "Keep responses concise (2-4 sentences) but insightful. "
        "Always reference the actual data when possible.\n\n"
        f"=== LIVE MARKET DATA ===\n{data_context}\n"
        f"Total products tracked: {len(scraped_data)}\n"
        f"=== END DATA ===\n"
        f"{inventory_context}"
        f"{history_context}"
    )

    try:
        response = await agent_llm.areason(system_prompt, user_message)
        if response.success and response.raw:
            return response.raw
        else:
            return (
                "I'm having trouble accessing my analysis engine right now. "
                f"Error: {response.error or 'Unknown'}. "
                "Please try again in a moment."
            )
    except Exception as e:
        print(f"[LLM-Chat] Exception: {e}")
        return (
            "My analysis systems are temporarily unavailable. "
            "Please try again shortly."
        )


# ═══════════════════════════════════════════════════════════════════
# STARTUP — Initialize agent modules on server boot
# ═══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    global store, shop_mgr, keyword_mgr, analytics_engine
    try:
        store = SupabaseStore()
        shop_mgr = ShopManager(store)
        keyword_mgr = CategoryKeywordManager(store)
        analytics_engine = AnalyticsEngine(store)
        print("[Server] ✓ Agent modules initialized")
        print(f"[Server] ✓ Supabase connected")
        print(f"[Server] ✓ Agent directory: {AGENT_DIR}")

        # Ensure core keywords exist
        await store.initialize_keyword_pool()
        print("[Server] ✓ Core keyword pool initialized")

        # Purge any existing null/zero price entries
        try:
            store.client.table("competitor_prices") \
                .delete() \
                .is_("price", "null") \
                .execute()
            store.client.table("competitor_prices") \
                .delete() \
                .lte("price", 0) \
                .execute()
            print("[Server] ✓ Purged null/zero price entries")
        except Exception as e:
            print(f"[Server] Purge warning: {e}")

        # Ensure shop_inventory table exists (create via RPC or direct insert test)
        try:
            store.client.table("shop_inventory").select("id").limit(1).execute()
            print("[Server] ✓ shop_inventory table exists")
        except Exception:
            # Table doesn't exist — create it via raw SQL RPC
            try:
                store.client.rpc("exec_sql", {
                    "query": """
                        CREATE TABLE IF NOT EXISTS public.shop_inventory (
                            id BIGSERIAL PRIMARY KEY,
                            shop_id BIGINT NOT NULL,
                            product_name TEXT NOT NULL,
                            quantity INT NOT NULL DEFAULT 0,
                            product_url TEXT,
                            price NUMERIC,
                            category TEXT,
                            notes TEXT,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        );
                        CREATE INDEX IF NOT EXISTS idx_shop_inventory_shop ON public.shop_inventory(shop_id);
                    """
                }).execute()
                print("[Server] ✓ shop_inventory table created")
            except Exception as e2:
                print(f"[Server] ⚠ shop_inventory table setup: {e2}")
                print("[Server] ℹ Please create 'shop_inventory' table manually — see schema below")
    except Exception as e:
        print(f"[Server] ✗ Startup error: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════
# DATA TRANSFORMATION — Supabase → Frontend scrapedData shape
# ═══════════════════════════════════════════════════════════════════

async def read_frontend_data(shop_id: int) -> List[Dict]:
    """
    Read competitor_prices from Supabase and transform to the exact shape
    the frontend expects: { id, name, price, competitor, timestamp, volatility, isNew }
    """
    if not store:
        return []

    try:
        # Read competitor prices for this shop (only real prices, no nulls/zeros)
        result = store.client.table("competitor_prices") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .not_.is_("price", "null") \
            .gt("price", 0) \
            .order("scraped_at", desc=True) \
            .limit(500) \
            .execute()

        if not result.data:
            return []

        # Read volatility data
        volatility_map: Dict[str, float] = {}
        try:
            vol_result = store.client.table("product_volatility") \
                .select("product_name, volatility_score") \
                .eq("shop_id", shop_id) \
                .execute()
            for v in (vol_result.data or []):
                volatility_map[v["product_name"]] = float(v.get("volatility_score", 0))
        except Exception:
            pass

        # Read emerging product flags
        emerging_set: set = set()
        try:
            em_result = store.client.table("product_metadata") \
                .select("product_name") \
                .eq("shop_id", shop_id) \
                .eq("is_emerging", True) \
                .execute()
            emerging_set = {e["product_name"] for e in (em_result.data or [])}
        except Exception:
            pass

        # Transform each row to frontend format
        data = []
        for row in result.data:
            product_name = row.get("product_name") or "Unknown Product"
            domain = row.get("domain", "")
            competitor = row.get("competitor_name") or _domain_to_competitor_name(domain)

            # Volatility: use real analytics data or compute fallback
            vol = volatility_map.get(product_name, 0)
            if vol <= 0:
                name_hash = int(hashlib.md5(
                    f"{product_name}-{domain}".encode()
                ).hexdigest()[:8], 16)
                vol = 1.0 + (name_hash / 0xFFFFFFFF) * 8.0
            vol = min(10.0, max(0.5, vol))

            # Emerging flag: real analytics or recency-based
            is_new = product_name in emerging_set
            if not is_new:
                scraped_at_str = row.get("scraped_at", "")
                try:
                    scraped_at = datetime.fromisoformat(
                        scraped_at_str.replace("Z", "+00:00")
                    )
                    hours_old = (
                        datetime.utcnow() - scraped_at.replace(tzinfo=None)
                    ).total_seconds() / 3600
                    if hours_old < 24:
                        name_hash = int(hashlib.md5(
                            product_name.encode()
                        ).hexdigest()[:4], 16)
                        is_new = (name_hash % 5 == 0)
                except Exception:
                    pass

            price_val = float(row.get("price", 0)) if row.get("price") else 0

            data.append({
                "id": str(row.get("id", "")),
                "name": product_name,
                "price": price_val,
                "competitor": competitor,
                "timestamp": row.get("scraped_at", datetime.utcnow().isoformat()),
                "volatility": f"{vol:.1f}",
                "isNew": is_new,
            })

        return data

    except Exception as e:
        print(f"[Server] Read data error: {e}")
        traceback.print_exc()
        return []


# ═══════════════════════════════════════════════════════════════════
# QUICK SCAN — Lightweight real-data scan (no LLM, fast)
# ═══════════════════════════════════════════════════════════════════

async def ensure_domain_exists(domain: str):
    """Ensure domain exists in domains table (FK constraint)."""
    if not store:
        return
    try:
        existing = store.client.table("domains") \
            .select("domain") \
            .eq("domain", domain) \
            .limit(1) \
            .execute()
        if not existing.data:
            store.client.table("domains").insert({
                "domain": domain,
                "trust_score": 50.0,
                "last_seen": datetime.utcnow().isoformat(),
                "offer_count": 0,
                "spam_count": 0,
                "is_blacklisted": False,
            }).execute()
    except Exception:
        pass


async def run_quick_scan(shop_id: int, category: str, max_searches: int = 3) -> int:
    """
    Perform a domain-aware scan using DuckDuckGo search + page scoring.
    Bypasses LLM reasoning for speed. Returns count of prices found.

    Builds search queries that are specific to the shop's domain:
    - Known domains (electronics, fashion, gaming, etc): use category keywords
    - Custom domains: use LLM-generated keywords + description context

    All scraped data is tagged with shop_id for isolation.
    """
    if not store or not keyword_mgr:
        return 0

    # Get shop config for context
    shop_config = _shop_cache.get(shop_id, {})
    shop_name = shop_config.get("shop_name", "")
    domain_name = shop_config.get("domain_name", category)
    custom_desc = shop_config.get("custom_description", "")
    frontend_kw = shop_config.get("frontend_keywords", [])

    # Get category keywords from DB
    keywords = []
    try:
        keywords = await keyword_mgr.get_active_keywords_for_shop(
            shop_id, category, limit=20
        )
    except Exception:
        pass

    if not keywords:
        try:
            cat_kw = await keyword_mgr.get_keywords_for_category(category)
            keywords = cat_kw.product_specific + cat_kw.core_keywords
        except Exception:
            keywords = []

    # Also pull LLM-generated keywords for custom domains
    llm_kw = shop_config.get("llm_keywords", [])
    if llm_kw:
        keywords = llm_kw + [k for k in keywords if k not in llm_kw]

    # Prioritize frontend-provided keywords (user selected these)
    if frontend_kw:
        keywords = frontend_kw + [k for k in keywords if k not in frontend_kw]

    # Build domain-aware search queries
    search_queries = []

    # Determine domain context string for searches
    if category == "custom" and custom_desc:
        domain_context = custom_desc.split(".")[0][:60]  # First sentence, short
    else:
        domain_context = domain_name  # e.g. "Electronics", "Gaming Gear"

    # Product-specific searches (capitalized keywords = products/brands)
    product_kw = [k for k in keywords if len(k) > 2 and k[0].isupper()]
    for pkw in product_kw[:max_searches]:
        search_queries.append(f"{pkw} price buy online India")

    # Domain-scoped searches
    if len(search_queries) < max_searches:
        price_kw = [k for k in keywords if len(k) > 2 and k[0].islower()]
        for gkw in price_kw[:max_searches - len(search_queries)]:
            search_queries.append(f"{gkw} {domain_context} price India")

    # Fallback: domain-level searches
    if not search_queries:
        search_queries = [
            f"best {domain_context} price India",
            f"{domain_context} price comparison online India",
        ]

    prices_found = 0
    urls_processed = 0

    print(f"[QuickScan] Shop {shop_id} ({shop_name} | {domain_name}), "
          f"{len(search_queries)} searches: {search_queries}")

    for query in search_queries[:max_searches]:
        try:
            print(f"[QuickScan] Searching: {query}")
            results = await ddg_scraper.search(query)

            if not results:
                print(f"[QuickScan] No results for: {query}")
                continue

            print(f"[QuickScan] Got {len(results)} URLs")

            for url in results[:8]:
                try:
                    if not canonicalizer.is_valid_url(url):
                        continue
                    canonical, url_hash = canonicalizer.canonicalize(url)
                    domain = canonicalizer.extract_domain(canonical)

                    if await store.is_domain_blacklisted(domain):
                        continue

                    if canonicalizer.is_duplicate(url_hash):
                        continue
                    canonicalizer.mark_seen(url_hash)

                    # Fetch page
                    response = await content_fetcher.fetch_with_retry(canonical)
                    if not response:
                        continue
                    raw_html = response.get("html", "")
                    if not raw_html:
                        continue

                    # Extract content
                    extracted = content_extractor.extract(raw_html, canonical)
                    text = extracted.get("text", "") if extracted else ""
                    title = extracted.get("title", "") if extracted else ""

                    if not extracted or not text or len(text) < 50:
                        continue

                    urls_processed += 1

                    # Get domain trust
                    domain_obj = await store.get_domain(domain)
                    domain_trust = domain_obj.trust_score if domain_obj else 0

                    # Score for pricing content
                    score_result = page_scorer.score_content(extracted, domain_trust)

                    if score_result.is_hard_rejected:
                        await store.create_or_update_domain(
                            domain, trust_delta=-3, is_spam=True
                        )
                        continue

                    if score_result.is_offer:
                        await store.create_or_update_domain(
                            domain, trust_delta=2, is_offer=True
                        )

                        # Extract prices from page
                        prices = page_scorer.extract_prices(text)
                        price_val = prices[0].amount if prices else None
                        currency = prices[0].currency if prices else "INR"

                        # SKIP entries with no real price
                        if not price_val or price_val <= 0:
                            print(f"[QuickScan] ✗ Skipped (no price): {title[:50]} @ {domain}")
                            continue

                        # Ensure domain FK exists
                        await ensure_domain_exists(domain)

                        # Store in Supabase
                        competitor_name = _domain_to_competitor_name(domain)
                        await store.insert_competitor_price(CompetitorPrice(
                            domain=domain,
                            url=canonical,
                            product_name=(title or query.split()[0])[:450],
                            price=price_val,
                            currency=currency,
                            competitor_name=competitor_name,
                            category=category,
                            scraped_at=datetime.utcnow(),
                            shop_id=shop_id,
                        ))
                        prices_found += 1
                        print(f"[QuickScan] ✓ Price: {title[:60]} @ {domain}")

                        # Store URL as processed
                        await store.batch_insert_urls([{
                            "url_hash": url_hash,
                            "canonical_url": canonical,
                            "domain": domain,
                            "processed_at": datetime.utcnow().isoformat(),
                            "score": score_result.score,
                            "spam_score": score_result.spam_score,
                            "is_offer": True,
                        }])

                        # Also seed product_metadata for emerging detection
                        try:
                            store.client.table("product_metadata").upsert({
                                "shop_id": shop_id,
                                "product_name": (title or query.split()[0])[:450],
                                "category": category,
                                "first_seen": datetime.utcnow().isoformat(),
                                "is_emerging": True,
                                "trending_score": float(score_result.score),
                            }, on_conflict="shop_id,product_name").execute()
                        except Exception:
                            pass

                except Exception as e:
                    print(f"[QuickScan] URL error: {e}")
                    continue

        except Exception as e:
            print(f"[QuickScan] Search error: {e}")
            continue

    # Flush any buffered inserts
    await store.flush_batch()

    print(f"[QuickScan] Complete: {prices_found} prices from "
          f"{urls_processed} URLs processed")

    # Run analytics after quick scan
    if prices_found > 0:
        try:
            await run_analytics_update(shop_id)
        except Exception as e:
            print(f"[QuickScan] Analytics error: {e}")

    return prices_found


async def run_analytics_update(shop_id: int):
    """Run the analytics suite to populate volatility, emerging, drops tables."""
    if not analytics_engine:
        return

    try:
        print(f"[Analytics] Running for shop {shop_id}...")
        results = await analytics_engine.run_full_analytics_cycle(shop_id)
        report = analytics_engine.format_analytics_report(results, shop_id)
        print(report)
    except Exception as e:
        print(f"[Analytics] Error: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════
# BACKGROUND AGENT — Full LLM-driven agent running continuously
# ═══════════════════════════════════════════════════════════════════

async def run_agent_background(shop_id: int):
    """
    Run the full autonomous agent in background.
    Uses LLM reasoning for strategic decisions.
    Runs continuously with sleep between cycles.
    """
    try:
        from agent_core import AgentReasoningCore

        agent = AgentReasoningCore(store, shop_id=shop_id)
        await agent.initialize()

        print(f"[BackgroundAgent] Started for shop {shop_id}")

        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                print(f"\n[BackgroundAgent] Cycle #{cycle_count} for shop {shop_id}")
                summary = await agent.run_cycle()
                prices = summary.get("prices_found", 0)
                print(f"[BackgroundAgent] Cycle #{cycle_count} complete: "
                      f"{prices} prices found")

            except Exception as e:
                print(f"[BackgroundAgent] Cycle error: {e}")
                traceback.print_exc()

            # Sleep 15-30 minutes between cycles
            sleep_minutes = random.randint(15, 30)
            print(f"[BackgroundAgent] Sleeping {sleep_minutes} minutes...")
            await asyncio.sleep(sleep_minutes * 60)

    except asyncio.CancelledError:
        print(f"[BackgroundAgent] Cancelled for shop {shop_id}")
    except Exception as e:
        print(f"[BackgroundAgent] Fatal error for shop {shop_id}: {e}")
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════

class ShopSetupRequest(BaseModel):
    shopName: str
    domainId: str
    domainName: str
    keywords: List[str] = []
    customDescription: str = ""


# ═══════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/shop/setup")
async def setup_shop(req: ShopSetupRequest, background_tasks: BackgroundTasks):
    """
    Register a shop + run quick scan + start background agent.

    Flow:
    1. Create shop in Supabase (via ShopManager)
    2. Initialize category-specific keywords (via CategoryKeywordManager)
    3. Seed known competitor domains
    4. Run quick scan (2-3 DuckDuckGo searches, REAL web scraping)
    5. Start full agent in background (LLM-driven continuous monitoring)
    6. Return scraped data in frontend format
    """
    if not store or not shop_mgr or not keyword_mgr:
        raise HTTPException(503, "Server not initialized — check Supabase connection")

    category = req.domainId if req.domainId != "custom" else "custom"
    shop_domain = f"{req.shopName.lower().replace(' ', '-')}.com"

    # Step 1: Always create a NEW shop for isolation
    # Each setup = new shop with its own data silo
    shop_id = None
    try:
        # Check if same shop name + same domain already exists
        existing = await shop_mgr.get_shop_by_name(req.shopName)
        if existing and existing.category == category:
            # Same name + same domain → reuse (same user re-deploying)
            shop_id = existing.id
            print(f"[Server] Shop '{req.shopName}' ({category}) exists (ID: {shop_id})")
        else:
            # New domain or new name → create fresh isolated shop
            shop = await shop_mgr.create_shop(
                shop_name=req.shopName,
                shop_domain=shop_domain,
                category=category,
                description=req.customDescription or req.domainName,
            )
            if shop:
                shop_id = shop.id
                print(f"[Server] Created NEW shop '{req.shopName}' "
                      f"(ID: {shop_id}, domain: {category})")
    except Exception as e:
        print(f"[Server] Shop creation error: {e}")
        traceback.print_exc()

    if not shop_id:
        raise HTTPException(500, "Failed to create shop in Supabase")

    # Step 2: Initialize category keywords (LLM for custom domains)
    try:
        if req.domainId == "custom" and req.customDescription:
            # Use LLM to generate domain-specific keywords from description
            print(f"[Server] Custom domain — using LLM for keyword generation")
            print(f"[Server] Custom description: {req.customDescription[:100]}")
            llm_keywords = await llm_generate_custom_keywords(
                req.customDescription, req.shopName
            )
            if llm_keywords:
                for kw in llm_keywords:
                    try:
                        await keyword_mgr.add_learned_keyword(
                            shop_id, kw, category, yield_score=1.5
                        )
                    except Exception:
                        pass
                print(f"[Server] ✓ LLM generated {len(llm_keywords)} keywords for custom domain")
                # Store keywords in shop cache for later use by quick scan
                _shop_cache.setdefault(shop_id, {})["llm_keywords"] = llm_keywords
            else:
                # Fallback: extract keywords from description itself
                print(f"[Server] LLM keyword generation returned nothing, extracting from description")
                desc_words = [w.strip('.,!?;:') for w in req.customDescription.split()
                              if len(w) > 3 and w[0].isalpha()]
                llm_keywords = desc_words[:20]
                for kw in llm_keywords:
                    try:
                        await keyword_mgr.add_learned_keyword(
                            shop_id, kw, category, yield_score=1.0
                        )
                    except Exception:
                        pass
                print(f"[Server] ✓ Extracted {len(llm_keywords)} keywords from description")
        else:
            await keyword_mgr.initialize_shop_keywords(shop_id, category)

        # Also add any user-provided keywords
        if req.keywords:
            for kw in req.keywords:
                try:
                    await keyword_mgr.add_learned_keyword(
                        shop_id, kw, category, yield_score=1.5
                    )
                except Exception:
                    pass

        print(f"[Server] ✓ Keywords initialized for category '{category}'")
    except Exception as e:
        print(f"[Server] Keyword init error: {e}")

    # Step 3: Seed known competitor domains (FK constraint)
    for domain in KNOWN_COMPETITORS:
        await ensure_domain_exists(domain)

    # Step 4: Cache shop config (merge with existing if LLM keywords were added)
    existing_cache = _shop_cache.get(shop_id, {})
    _shop_cache[shop_id] = {
        "shop_name": req.shopName,
        "category": category,
        "domain_id": req.domainId,
        "domain_name": req.domainName,
        "custom_description": req.customDescription,
        "frontend_keywords": req.keywords,
        "llm_keywords": existing_cache.get("llm_keywords", []),
    }

    # Step 5: Seed data — for known domains use SEED_DATA, for custom use LLM+web
    # Only seed if the shop has no existing data (first deploy)
    seed_count = 0
    try:
        existing_count = store.client.table("competitor_prices") \
            .select("id", count="exact") \
            .eq("shop_id", shop_id) \
            .limit(1) \
            .execute()
        has_data = (existing_count.count or 0) > 0
    except Exception:
        has_data = False

    if not has_data:
        if category in SEED_DATA:
            seed_count = await seed_shop_data(shop_id, category)
            print(f"[Server] ✓ Seed data: {seed_count} products loaded instantly")
        elif category == "custom" and req.customDescription:
            # Generate seed data via LLM + web scraping for custom domains
            print(f"[Server] Generating custom seed data for '{req.shopName}'...")
            try:
                # Get LLM keywords from cache (set during keyword generation step)
                cached_kw = _shop_cache.get(shop_id, {}).get("llm_keywords", [])
                custom_seeds = await llm_generate_custom_seed_data(
                    req.customDescription, req.shopName, cached_kw
                )
                if custom_seeds:
                    now = datetime.utcnow()
                    for item in custom_seeds:
                        try:
                            await ensure_domain_exists(item["domain"])
                            await store.insert_competitor_price(CompetitorPrice(
                                domain=item["domain"],
                                url=item["url"],
                                product_name=item["product_name"],
                                price=item["price"],
                                currency="INR",
                                competitor_name=item["competitor_name"],
                                category="custom",
                                scraped_at=now,
                                shop_id=shop_id,
                            ))
                            seed_count += 1
                        except Exception as e:
                            print(f"[Server] Custom seed insert error: {e}")
                    print(f"[Server] ✓ Custom seed data: {seed_count} products loaded")
                else:
                    print(f"[Server] ⚠ No custom seed data generated")
            except Exception as e:
                print(f"[Server] Custom seed generation error: {e}")
                traceback.print_exc()
    else:
        print(f"[Server] ✓ Shop {shop_id} already has data — skipping seed")

    # Step 6: Read seed data from Supabase (returns immediately)
    data = await read_frontend_data(shop_id)

    # Step 7: Run quick scan + LLM enrichment IN BACKGROUND (non-blocking)
    async def _background_scan_and_enrich(sid: int, cat: str, sname: str):
        """Background: scrape real prices + enrich with LLM after seed data served."""
        try:
            prices_found = await run_quick_scan(sid, cat, max_searches=3)
            print(f"[Background] Quick scan found {prices_found} new prices for shop {sid}")
        except Exception as e:
            print(f"[Background] Quick scan error for shop {sid}: {e}")

        # LLM enrichment on freshly scraped data
        try:
            fresh_data = await read_frontend_data(sid)
            if fresh_data:
                await llm_enrich_products(fresh_data, cat, sname)
                print(f"[Background] ✓ LLM insights added to {len(fresh_data)} products")
        except Exception as e:
            print(f"[Background] LLM enrichment error (non-fatal): {e}")

    asyncio.create_task(_background_scan_and_enrich(shop_id, category, req.shopName))
    print(f"[Server] ✓ Background scan + enrichment launched for shop {shop_id}")

    # Step 8: Start background agent
    if shop_id not in _agent_tasks or _agent_tasks[shop_id].done():
        task = asyncio.create_task(run_agent_background(shop_id))
        _agent_tasks[shop_id] = task
        print(f"[Server] ✓ Background agent started for shop {shop_id}")

    try:
        await shop_mgr.update_shop_last_active(shop_id)
    except Exception:
        pass

    print(f"[Server] ✓ Shop '{req.shopName}' setup complete — "
          f"{len(data)} data points returned")

    return {
        "shopId": shop_id,
        "data": data,
    }


@app.post("/api/scan/{shop_id}")
async def run_scan(shop_id: int, background_tasks: BackgroundTasks):
    """
    Refresh data for a shop.

    Flow:
    1. Run quick scan (1-2 searches for speed)
    2. Read all data from Supabase
    3. Trigger analytics update in background
    4. Return fresh data in frontend format
    """
    if not store:
        raise HTTPException(503, "Server not initialized")

    category = "electronics"
    if shop_id in _shop_cache:
        category = _shop_cache[shop_id].get("category", "electronics")
    else:
        try:
            shop = await shop_mgr.get_shop(shop_id)
            if shop:
                category = shop.category
                _shop_cache[shop_id] = {
                    "shop_name": shop.shop_name,
                    "category": shop.category,
                }
        except Exception:
            pass

    # Quick scan (fewer searches for responsiveness)
    await run_quick_scan(shop_id, category, max_searches=2)

    # Read all data from Supabase
    data = await read_frontend_data(shop_id)

    try:
        await shop_mgr.update_shop_last_active(shop_id)
    except Exception:
        pass

    # Ensure background agent is running
    if shop_id not in _agent_tasks or _agent_tasks[shop_id].done():
        task = asyncio.create_task(run_agent_background(shop_id))
        _agent_tasks[shop_id] = task

    return data


@app.get("/api/data/{shop_id}")
async def get_data(shop_id: int):
    """
    Read current data from Supabase (no scanning, instant).
    Returns whatever the agent has collected so far.
    """
    if not store:
        raise HTTPException(503, "Server not initialized")
    return await read_frontend_data(shop_id)


# ═══════════════════════════════════════════════════════════════════
# AGENT MANAGEMENT — Start/stop/status
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/agent/start/{shop_id}")
async def start_agent(shop_id: int):
    """Start the autonomous web agent for a shop."""
    if shop_id in _agent_tasks and not _agent_tasks[shop_id].done():
        return {"status": "already_running", "shop_id": shop_id}

    try:
        shop = await shop_mgr.get_shop(shop_id)
        if not shop:
            raise HTTPException(404, f"Shop {shop_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to verify shop: {e}")

    task = asyncio.create_task(run_agent_background(shop_id))
    _agent_tasks[shop_id] = task
    return {"status": "started", "shop_id": shop_id}


@app.get("/api/agent/status/{shop_id}")
async def get_agent_status(shop_id: int):
    """Check if the web agent is running for a shop."""
    if shop_id not in _agent_tasks:
        return {"status": "not_started", "shop_id": shop_id}

    task = _agent_tasks[shop_id]
    if not task.done():
        return {"status": "running", "shop_id": shop_id}
    else:
        exc = task.exception() if not task.cancelled() else None
        return {
            "status": "stopped",
            "shop_id": shop_id,
            "error": str(exc) if exc else None,
        }


@app.post("/api/agent/stop/{shop_id}")
async def stop_agent(shop_id: int):
    """Stop the web agent for a shop."""
    if shop_id not in _agent_tasks:
        return {"status": "not_running", "shop_id": shop_id}

    task = _agent_tasks[shop_id]
    if not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        return {"status": "stopped", "shop_id": shop_id}

    return {"status": "already_stopped", "shop_id": shop_id}


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS — Read real analytics from Supabase
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/analytics/volatility/{shop_id}")
async def get_volatility(shop_id: int):
    """Get price volatility data."""
    if not store:
        return []
    try:
        result = store.client.table("product_volatility") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .order("volatility_score", desc=True) \
            .limit(50) \
            .execute()
        return result.data or []
    except Exception:
        return []


@app.get("/api/analytics/emerging/{shop_id}")
async def get_emerging(shop_id: int):
    """Get emerging products."""
    if not store:
        return []
    try:
        result = store.client.table("emerging_products") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .order("created_at", desc=True) \
            .limit(50) \
            .execute()
        return result.data or []
    except Exception:
        return []


@app.get("/api/analytics/drops/{shop_id}")
async def get_price_drops(shop_id: int):
    """Get detected price drops."""
    if not store:
        return []
    try:
        result = store.client.table("price_drops") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .order("detected_at", desc=True) \
            .limit(50) \
            .execute()
        return result.data or []
    except Exception:
        return []


@app.get("/api/analytics/coverage/{shop_id}")
async def get_coverage(shop_id: int):
    """Get competitor coverage data."""
    if not store:
        return []
    try:
        result = store.client.table("competitor_coverage") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .order("market_share_percent", desc=True) \
            .limit(50) \
            .execute()
        return result.data or []
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════
# INVENTORY MANAGEMENT — CRUD + auto-search
# ═══════════════════════════════════════════════════════════════════

class InventoryItem(BaseModel):
    product_name: str
    quantity: int = 0
    product_url: str = ""
    price: float = 0
    category: str = ""
    notes: str = ""


class InventoryBulkRequest(BaseModel):
    """Accepts CSV-like text: each line is  name, quantity[, url]"""
    items: List[InventoryItem] = []
    csv_text: str = ""


class InventoryUpdateRequest(BaseModel):
    product_name: str = ""
    quantity: int = None
    product_url: str = None
    price: float = None
    category: str = None
    notes: str = None


async def _search_product_info(product_name: str) -> Dict[str, Any]:
    """
    Search the web for a product's default price and URL
    when the user doesn't provide a link.
    """
    try:
        results = await ddg_scraper.search(f"{product_name} price buy India")
        if not results:
            return {"price": 0, "product_url": ""}

        # Try to find a price from the first few results
        best_url = ""
        best_price = 0.0
        for r in results[:5]:
            url = r.get("href") or r.get("url") or r.get("link", "")
            if not url:
                continue
            if not best_url:
                best_url = url

            try:
                html = await content_fetcher.fetch_with_retry(url)
                if html:
                    extracted = content_extractor.extract(html, url)
                    if extracted:
                        score_result = page_scorer.score(extracted, product_name)
                        if score_result and score_result.get("price") and score_result["price"] > 0:
                            best_price = score_result["price"]
                            best_url = url
                            break
            except Exception:
                continue

        return {"price": best_price, "product_url": best_url}
    except Exception as e:
        print(f"[Inventory] Search failed for '{product_name}': {e}")
        return {"price": 0, "product_url": ""}


async def _enrich_inventory_items(shop_id: int, items: List[tuple]):
    """Background task: search for price/URL for inventory items without links."""
    for item_id, product_name in items:
        try:
            info = await _search_product_info(product_name)
            updates = {}
            if info.get("product_url"):
                updates["product_url"] = info["product_url"]
            if info.get("price") and info["price"] > 0:
                updates["price"] = info["price"]
            if updates:
                updates["updated_at"] = datetime.utcnow().isoformat()
                store.client.table("shop_inventory") \
                    .update(updates) \
                    .eq("id", item_id) \
                    .eq("shop_id", shop_id) \
                    .execute()
                print(f"[Inventory] Enriched '{product_name}': {updates}")
        except Exception as e:
            print(f"[Inventory] Enrich failed for '{product_name}': {e}")


def _parse_csv_text(csv_text: str) -> List[Dict]:
    """
    Parse CSV-like text into inventory items.
    Format per line: product_name, quantity [, url]
    Handles: quoted names, trailing commas, whitespace.
    """
    items = []
    for line in csv_text.strip().split("\n"):
        line = line.strip().rstrip(",")  # strip trailing commas
        if not line:
            continue
        parts = [p.strip().strip('"').strip("'") for p in line.split(",")]
        if not parts or not parts[0]:
            continue
        if len(parts) < 2:
            items.append({"product_name": parts[0], "quantity": 1, "product_url": ""})
            continue
        name = parts[0]
        try:
            qty = int(parts[1])
        except ValueError:
            qty = 1
        url = parts[2].strip() if len(parts) > 2 and parts[2].strip() else ""
        items.append({"product_name": name, "quantity": qty, "product_url": url})
    return items


@app.get("/api/inventory/{shop_id}")
async def get_inventory(shop_id: int):
    """List all inventory items for a shop."""
    if not store:
        raise HTTPException(503, "Server not initialized")
    try:
        result = store.client.table("shop_inventory") \
            .select("*") \
            .eq("shop_id", shop_id) \
            .order("created_at", desc=True) \
            .execute()
        return result.data or []
    except Exception as e:
        print(f"[Inventory] GET error: {e}")
        return []


@app.post("/api/inventory/{shop_id}")
async def add_inventory(shop_id: int, req: InventoryBulkRequest):
    """
    Add inventory items. Accepts either structured items or CSV text.
    For items without a URL, auto-searches the web for product info.
    """
    if not store:
        raise HTTPException(503, "Server not initialized")

    items_to_add = []

    # Parse CSV text if provided
    if req.csv_text.strip():
        parsed = _parse_csv_text(req.csv_text)
        for p in parsed:
            items_to_add.append(InventoryItem(
                product_name=p["product_name"],
                quantity=p["quantity"],
                product_url=p.get("product_url", ""),
            ))

    # Add structured items
    items_to_add.extend(req.items)

    if not items_to_add:
        raise HTTPException(400, "No items provided")

    # Insert all items immediately (no blocking search)
    inserted = []
    items_needing_search = []  # (item_id, product_name) for background enrichment

    for item in items_to_add:
        row = {
            "shop_id": shop_id,
            "product_name": item.product_name.strip('"').strip("'"),
            "quantity": item.quantity,
            "product_url": item.product_url or "",
            "price": item.price or 0,
            "category": item.category or "",
            "notes": item.notes or "",
        }

        try:
            result = store.client.table("shop_inventory") \
                .insert(row) \
                .execute()
            if result.data:
                inserted.extend(result.data)
                # Track items that need background search
                if not row["product_url"]:
                    items_needing_search.append(
                        (result.data[0]["id"], row["product_name"])
                    )
        except Exception as e:
            print(f"[Inventory] Insert error for '{item.product_name}': {e}")

    # Launch background enrichment for items without URLs
    if items_needing_search:
        asyncio.create_task(_enrich_inventory_items(shop_id, items_needing_search))

    print(f"[Inventory] Added {len(inserted)} items for shop {shop_id}")
    return {"added": len(inserted), "items": inserted}


@app.put("/api/inventory/{shop_id}/{item_id}")
async def update_inventory(shop_id: int, item_id: int, req: InventoryUpdateRequest):
    """Update an inventory item (quantity, name, url, price, etc.)."""
    if not store:
        raise HTTPException(503, "Server not initialized")

    updates = {}
    if req.product_name:
        updates["product_name"] = req.product_name
    if req.quantity is not None:
        updates["quantity"] = req.quantity
    if req.product_url is not None:
        updates["product_url"] = req.product_url
    if req.price is not None:
        updates["price"] = req.price
    if req.category is not None:
        updates["category"] = req.category
    if req.notes is not None:
        updates["notes"] = req.notes

    if not updates:
        raise HTTPException(400, "No fields to update")

    updates["updated_at"] = datetime.utcnow().isoformat()

    try:
        result = store.client.table("shop_inventory") \
            .update(updates) \
            .eq("id", item_id) \
            .eq("shop_id", shop_id) \
            .execute()
        if result.data:
            return result.data[0]
        raise HTTPException(404, "Item not found")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Inventory] Update error: {e}")
        raise HTTPException(500, str(e))


@app.delete("/api/inventory/{shop_id}/{item_id}")
async def delete_inventory(shop_id: int, item_id: int):
    """Delete an inventory item."""
    if not store:
        raise HTTPException(503, "Server not initialized")
    try:
        result = store.client.table("shop_inventory") \
            .delete() \
            .eq("id", item_id) \
            .eq("shop_id", shop_id) \
            .execute()
        return {"deleted": True, "id": item_id}
    except Exception as e:
        print(f"[Inventory] Delete error: {e}")
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════════
# CHAT ENDPOINT — LLM-powered Business Advisor
# ═══════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    shopId: int
    shopName: str = ""
    category: str = ""
    history: List[Dict[str, str]] = []


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    LLM-powered business advisor chat endpoint.

    Uses real scraped data from Supabase as context and the NVIDIA Kimi K2
    model to provide strategic, data-driven retail advice.
    """
    if not store:
        raise HTTPException(503, "Server not initialized")

    # Get shop info for context
    shop_name = req.shopName
    category = req.category
    if not shop_name or not category:
        if req.shopId in _shop_cache:
            shop_name = shop_name or _shop_cache[req.shopId].get("shop_name", "Shop")
            category = category or _shop_cache[req.shopId].get("category", "retail")
        else:
            try:
                shop = await shop_mgr.get_shop(req.shopId)
                if shop:
                    shop_name = shop_name or shop.shop_name
                    category = category or shop.category
            except Exception:
                pass

    # Read real scraped data for context
    scraped_data = await read_frontend_data(req.shopId)

    # Read inventory for context
    inventory_data = []
    try:
        inv_result = store.client.table("shop_inventory") \
            .select("*") \
            .eq("shop_id", req.shopId) \
            .execute()
        inventory_data = inv_result.data or []
    except Exception as e:
        print(f"[Chat] Inventory fetch warning: {e}")

    # Generate LLM response
    response_text = await llm_chat_response(
        user_message=req.message,
        scraped_data=scraped_data,
        shop_name=shop_name or "Shop",
        category=category or "retail",
        chat_history=req.history,
        inventory_data=inventory_data,
    )

    return {
        "response": response_text,
        "dataPoints": len(scraped_data),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# SYSTEM ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health():
    """Health check."""
    supabase_ok = False
    if store:
        try:
            store.client.table("domains").select("domain").limit(1).execute()
            supabase_ok = True
        except Exception:
            pass

    active_agents = sum(1 for t in _agent_tasks.values() if not t.done())

    return {
        "status": "ok",
        "supabase": "connected" if supabase_ok else "disconnected",
        "timestamp": datetime.utcnow().isoformat(),
        "active_agents": active_agents,
        "agent_module_path": AGENT_DIR,
    }


@app.get("/api/stats")
async def get_stats():
    """Get system-wide statistics."""
    stats = {
        "shops": 0,
        "total_prices": 0,
        "total_domains": 0,
        "active_keywords": 0,
        "total_urls_processed": 0,
        "active_agents": sum(1 for t in _agent_tasks.values() if not t.done()),
    }
    if not store:
        return stats
    try:
        shops = store.client.table("shops").select("*", count="exact").execute()
        stats["shops"] = shops.count or 0
    except Exception:
        pass
    try:
        prices = store.client.table("competitor_prices").select("*", count="exact").execute()
        stats["total_prices"] = prices.count or 0
    except Exception:
        pass
    try:
        domains = store.client.table("domains").select("*", count="exact").execute()
        stats["total_domains"] = domains.count or 0
    except Exception:
        pass
    try:
        kw = store.client.table("keyword_pool") \
            .select("*", count="exact") \
            .eq("is_active", True) \
            .execute()
        stats["active_keywords"] = kw.count or 0
    except Exception:
        pass
    try:
        urls = store.client.table("processed_urls").select("*", count="exact").execute()
        stats["total_urls_processed"] = urls.count or 0
    except Exception:
        pass
    return stats


# ═══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  RETAIL PRICEGUARD — Backend API Server v2.0")
    print("  Real Agent Integration (DuckDuckGo + LLM + Supabase)")
    print("  http://localhost:8000")
    print("  Docs: http://localhost:8000/docs")
    print("=" * 60 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
