"""
Supabase database interface with batch operations.
Optimized for minimal queries and O(1) lookups.
"""
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import asyncio

from supabase import create_client, Client

from config import (
    SUPABASE_URL, SUPABASE_KEY, Limits, Thresholds, SPAM_KEYWORDS, CORE_VOCABULARY
)


@dataclass
class ProcessedURL:
    url_hash: str
    canonical_url: str
    domain: str
    processed_at: datetime
    score: int
    spam_score: int
    is_offer: bool


@dataclass  
class Domain:
    domain: str
    trust_score: float
    last_seen: datetime
    offer_count: int
    spam_count: int
    is_blacklisted: bool


@dataclass
class CompetitorPrice:
    """A discovered competitor price record."""
    domain: str
    url: str
    product_name: str
    price: Optional[float]
    currency: str
    competitor_name: str
    category: str
    scraped_at: datetime
    shop_id: Optional[int] = None  # Multi-tenant: which shop this price is for


@dataclass
class Keyword:
    term: str
    category: str  # 'core', 'learned'
    yield_score: float
    usage_count: int
    last_used: datetime
    is_active: bool


class SupabaseStore:
    """Database layer with batch operations and deduplication."""
    
    def __init__(self):
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self._memory_cache: Set[str] = set()
        self._domain_cache: Dict[str, Domain] = {}
        self._batch_buffer: List[Dict] = []
    
    # ─────────────────────────────────────────────────────────────────
    # URL Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def is_url_processed(self, url_hash: str) -> bool:
        """O(1) check via memory cache + DB unique index."""
        if url_hash in self._memory_cache:
            return True
        
        result = self.client.table("processed_urls")\
            .select("url_hash")\
            .eq("url_hash", url_hash)\
            .limit(1)\
            .execute()
        
        return len(result.data) > 0
    
    def add_to_memory_cache(self, url_hash: str):
        """Add to Layer 1 in-memory cache."""
        self._memory_cache.add(url_hash)
        
        # Memory cap: ~8MB per 100k URLs (64 hex chars = 32 bytes + overhead)
        if len(self._memory_cache) > 200000:  # Hard limit
            self._memory_cache.clear()  # Reset when full
    
    async def batch_insert_urls(self, urls: List[Dict], force: bool = False):
        """Batch insert with conflict handling."""
        self._batch_buffer.extend(urls)
        
        if len(self._batch_buffer) >= Limits.BATCH_SIZE or force:
            if not self._batch_buffer:
                return
            
            # ON CONFLICT DO NOTHING via upsert with ignore
            try:
                self.client.table("processed_urls")\
                    .upsert(self._batch_buffer, on_conflict="url_hash")\
                    .execute()
                
                # Update memory cache
                for url in self._batch_buffer:
                    self._memory_cache.add(url["url_hash"])
                    
            except Exception as e:
                print(f"Batch insert error: {e}")
            
            self._batch_buffer = []
    
    async def flush_batch(self):
        """Force flush remaining batch."""
        await self.batch_insert_urls([], force=True)
    
    async def archive_old_urls(self):
        """Move URLs older than 90 days to archive table."""
        cutoff = datetime.utcnow() - timedelta(days=Limits.ARCHIVE_DAYS)
        
        # Select old URLs
        old_urls = self.client.table("processed_urls")\
            .select("*")\
            .lt("processed_at", cutoff.isoformat())\
            .execute()
        
        if old_urls.data:
            # Insert into archive
            self.client.table("archived_urls")\
                .insert(old_urls.data)\
                .execute()
            
            # Delete from processed
            for url in old_urls.data:
                self.client.table("processed_urls")\
                    .delete()\
                    .eq("url_hash", url["url_hash"])\
                    .execute()
    
    # ─────────────────────────────────────────────────────────────────
    # Domain Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def get_domain(self, domain: str) -> Optional[Domain]:
        """Get domain with caching."""
        if domain in self._domain_cache:
            return self._domain_cache[domain]
        
        result = self.client.table("domains")\
            .select("*")\
            .eq("domain", domain)\
            .limit(1)\
            .execute()
        
        if result.data:
            d = result.data[0]
            domain_obj = Domain(
                domain=d["domain"],
                trust_score=d["trust_score"],
                last_seen=datetime.fromisoformat(d["last_seen"]),
                offer_count=d["offer_count"],
                spam_count=d["spam_count"],
                is_blacklisted=d["is_blacklisted"]
            )
            self._domain_cache[domain] = domain_obj
            return domain_obj
        
        return None
    
    async def create_or_update_domain(self, domain: str, 
                                       trust_delta: int = 0,
                                       is_offer: bool = False,
                                       is_spam: bool = False):
        """Update domain trust score atomically."""
        existing = await self.get_domain(domain)
        
        if existing:
            new_trust = existing.trust_score + trust_delta
            new_offers = existing.offer_count + (1 if is_offer else 0)
            new_spam = existing.spam_count + (1 if is_spam else 0)
            is_blacklisted = new_trust < Thresholds.BLACKLIST_DOMAIN_SCORE
            
            self.client.table("domains")\
                .update({
                    "trust_score": new_trust,
                    "last_seen": datetime.utcnow().isoformat(),
                    "offer_count": new_offers,
                    "spam_count": new_spam,
                    "is_blacklisted": is_blacklisted
                })\
                .eq("domain", domain)\
                .execute()
            
            # Update cache
            existing.trust_score = new_trust
            existing.offer_count = new_offers
            existing.spam_count = new_spam
            existing.is_blacklisted = is_blacklisted
        else:
            # New domain
            is_blacklisted = trust_delta < Thresholds.BLACKLIST_DOMAIN_SCORE
            self.client.table("domains")\
                .insert({
                    "domain": domain,
                    "trust_score": trust_delta,
                    "last_seen": datetime.utcnow().isoformat(),
                    "offer_count": 1 if is_offer else 0,
                    "spam_count": 1 if is_spam else 0,
                    "is_blacklisted": is_blacklisted
                })\
                .execute()
    
    async def is_domain_blacklisted(self, domain: str) -> bool:
        """O(1) blacklist check."""
        domain_obj = await self.get_domain(domain)
        return domain_obj.is_blacklisted if domain_obj else False
    
    async def apply_trust_decay(self):
        """Apply monthly 5% trust decay to all domains."""
        domains = self.client.table("domains")\
            .select("*")\
            .execute()
        
        for d in domains.data:
            if d["trust_score"] > 0:
                new_score = d["trust_score"] * 0.95
                self.client.table("domains")\
                    .update({"trust_score": new_score})\
                    .eq("domain", d["domain"])\
                    .execute()
    
    # ─────────────────────────────────────────────────────────────────
    # Competitor Price Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def insert_competitor_price(self, price: CompetitorPrice):
        """Insert discovered competitor price with multi-tenant shop_id."""
        record = {
            "domain": price.domain,
            "url": price.url,
            "product_name": price.product_name,
            "price": price.price,
            "currency": price.currency,
            "competitor_name": price.competitor_name,
            "category": price.category,
            "scraped_at": price.scraped_at.isoformat(),
        }
        if price.shop_id is not None:
            record["shop_id"] = price.shop_id
        self.client.table("competitor_prices")\
            .insert(record)\
            .execute()
    
    # ─────────────────────────────────────────────────────────────────
    # Keyword Operations
    # ─────────────────────────────────────────────────────────────────
    
    async def initialize_keyword_pool(self):
        """Seed database with core vocabulary."""
        existing = self.client.table("keyword_pool")\
            .select("term")\
            .execute()
        
        existing_terms = {k["term"] for k in existing.data}
        
        new_keywords = []
        for category, terms in CORE_VOCABULARY.items():
            for term in terms:
                if term not in existing_terms:
                    new_keywords.append({
                        "term": term,
                        "category": "core",
                        "yield_score": 1.0,
                        "usage_count": 0,
                        "last_used": datetime.utcnow().isoformat(),
                        "is_active": True
                    })
        
        if new_keywords:
            self.client.table("keyword_pool")\
                .insert(new_keywords)\
                .execute()
    
    async def get_active_keywords(self, limit: int = Limits.MAX_KEYWORDS) -> List[Keyword]:
        """Get active keywords sorted by yield."""
        result = self.client.table("keyword_pool")\
            .select("*")\
            .eq("is_active", True)\
            .order("yield_score", desc=True)\
            .limit(limit)\
            .execute()
        
        return [
            Keyword(
                term=k["term"],
                category=k["category"],
                yield_score=k["yield_score"],
                usage_count=k["usage_count"],
                last_used=datetime.fromisoformat(k["last_used"]),
                is_active=k["is_active"]
            )
            for k in result.data
        ]
    
    async def update_keyword_yield(self, term: str, yield_delta: float):
        """Update keyword yield score."""
        result = self.client.table("keyword_pool")\
            .select("yield_score, usage_count")\
            .eq("term", term)\
            .limit(1)\
            .execute()
        
        if result.data:
            k = result.data[0]
            new_yield = max(0.0, k["yield_score"] + yield_delta)
            new_count = k["usage_count"] + 1
            
            self.client.table("keyword_pool")\
                .update({
                    "yield_score": new_yield,
                    "usage_count": new_count,
                    "last_used": datetime.utcnow().isoformat()
                })\
                .eq("term", term)\
                .execute()
    
    async def add_learned_term(self, term: str):
        """Add new learned term if under cap."""
        # Check current count
        count = self.client.table("keyword_pool")\
            .select("*", count="exact")\
            .eq("category", "learned")\
            .execute()
        
        if count.count >= Limits.MAX_LEARNED_TERMS:
            return False
        
        # Check if exists
        existing = self.client.table("keyword_pool")\
            .select("term")\
            .eq("term", term)\
            .limit(1)\
            .execute()
        
        if existing.data:
            return False
        
        # Check not spam
        if any(spam in term.lower() for spam in SPAM_KEYWORDS):
            return False
        
        self.client.table("keyword_pool")\
            .insert({
                "term": term,
                "category": "learned",
                "yield_score": 0.5,
                "usage_count": 0,
                "last_used": datetime.utcnow().isoformat(),
                "is_active": True
            })\
            .execute()
        
        return True
    
    async def prune_low_yield_keywords(self):
        """Remove learned keywords with 0 yield for 10 cycles."""
        # Mark inactive instead of delete
        result = self.client.table("keyword_pool")\
            .select("*")\
            .eq("category", "learned")\
            .eq("is_active", True)\
            .lt("yield_score", 0.1)\
            .gte("usage_count", Limits.PRUNE_KEYWORD_CYCLES)\
            .execute()
        
        for k in result.data:
            self.client.table("keyword_pool")\
                .update({"is_active": False})\
                .eq("term", k["term"])\
                .execute()
    
    # ─────────────────────────────────────────────────────────────────
    # Learned Terms (Co-occurrence)
    # ─────────────────────────────────────────────────────────────────
    
    async def increment_term_frequency(self, term: str, context: str):
        """Track term frequency for co-occurrence learning."""
        # Simple frequency tracking
        result = self.client.table("learned_terms")\
            .select("frequency")\
            .eq("term", term)\
            .eq("context", context)\
            .limit(1)\
            .execute()
        
        if result.data:
            new_freq = result.data[0]["frequency"] + 1
            self.client.table("learned_terms")\
                .update({"frequency": new_freq})\
                .eq("term", term)\
                .eq("context", context)\
                .execute()
        else:
            self.client.table("learned_terms")\
                .insert({
                    "term": term,
                    "context": context,
                    "frequency": 1,
                    "discovered_at": datetime.utcnow().isoformat(),
                    "promoted": False
                })\
                .execute()
    
    async def get_promotable_terms(self) -> List[str]:
        """Get terms eligible for promotion to keyword pool."""
        result = self.client.table("learned_terms")\
            .select("*")\
            .gte("frequency", Limits.MIN_FREQUENCY_FOR_PROMOTION)\
            .eq("promoted", False)\
            .limit(Limits.MAX_NEW_PROMOTIONS_PER_CYCLE)\
            .execute()
        
        promotable = []
        for t in result.data:
            # Check contains benefit term
            if any(benefit in t["term"].lower() 
                   for benefit in CORE_VOCABULARY["benefits"]):
                promotable.append(t["term"])
                
                # Mark as promoted
                self.client.table("learned_terms")\
                    .update({"promoted": True})\
                    .eq("term", t["term"])\
                    .eq("context", t["context"])\
                    .execute()
        
        return promotable

    async def count_processed(self) -> int:
        """Count total processed URLs."""
        result = self.client.table("processed_urls")\
            .select("*", count="exact")\
            .execute()
        return result.count or 0
    
    async def count_prices(self) -> int:
        """Count total competitor prices collected."""
        result = self.client.table("competitor_prices")\
            .select("*", count="exact")\
            .execute()
        return result.count or 0
