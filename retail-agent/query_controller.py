"""
Query Budget Controller
Controls query volume, randomizes selection, tracks yield.
"""
import random
from typing import List, Dict, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from database import SupabaseStore
from config import Limits, Thresholds, CORE_VOCABULARY, SYNONYM_GRAPH


@dataclass
class Query:
    """Query with metadata."""
    query_string: str
    yield_score: float = 1.0
    consecutive_zero_yields: int = 0
    total_executions: int = 0
    total_results: int = 0


class QueryBudgetController:
    """
    Manages query execution budget.
    - 5-10 queries per cycle max
    - Randomized order
    - Track yield per query
    - Deprioritize low-yield queries
    """
    
    def __init__(self, db: SupabaseStore):
        self.db = db
        self._queries: Dict[str, Query] = {}
        self._query_history: Dict[str, List[float]] = defaultdict(list)
        self._build_query_pool()
    
    def _build_query_pool(self):
        """Build initial query pool from vocabulary + combinations."""
        entities = CORE_VOCABULARY["entities"]
        benefits = CORE_VOCABULARY["benefits"]
        verticals = CORE_VOCABULARY["verticals"]
        
        # Core queries: entity + benefit
        for entity in entities[:10]:  # Limit initial pool
            for benefit in benefits[:8]:
                query = f"{entity} {benefit}"
                self._queries[query] = Query(query_string=query)
        
        # Vertical-specific queries
        for vertical in verticals[:5]:
            for benefit in benefits[:5]:
                query = f"{vertical} {benefit} price"
                self._queries[query] = Query(query_string=query)
        
        print(f"[QueryController] Built pool of {len(self._queries)} queries")
    
    async def sync_with_db(self):
        """Load query yield data from database."""
        keywords = await self.db.get_active_keywords()
        
        for kw in keywords:
            if kw.term in self._queries:
                self._queries[kw.term].yield_score = kw.yield_score
    
    def select_queries(self, budget: int = Limits.MAX_QUERIES_PER_CYCLE) -> List[str]:
        """
        Select queries for this cycle.
        Randomized, with deprioritization of low-yield queries.
        """
        available = list(self._queries.values())
        
        # Filter out deprioritized queries
        active = [
            q for q in available
            if q.consecutive_zero_yields < Thresholds.DEPRIORITIZE_QUERY_CYCLES
        ]
        
        if not active:
            active = available  # Fallback if all deprioritized
        
        # Weighted random selection based on yield
        weights = [max(0.1, q.yield_score) for q in active]
        total_weight = sum(weights)
        
        if total_weight == 0:
            weights = [1.0] * len(active)
            total_weight = len(active)
        
        # Normalize weights
        normalized = [w / total_weight for w in weights]
        
        # Select queries
        selected = []
        remaining = active.copy()
        remaining_weights = normalized.copy()
        
        for _ in range(min(budget, len(available))):
            if not remaining:
                break
            
            # Weighted selection
            idx = random.choices(range(len(remaining)), weights=remaining_weights)[0]
            selected.append(remaining[idx].query_string)
            
            # Remove selected
            remaining.pop(idx)
            remaining_weights.pop(idx)
            
            # Renormalize
            if remaining_weights:
                w_sum = sum(remaining_weights)
                if w_sum > 0:
                    remaining_weights = [w / w_sum for w in remaining_weights]
        
        return selected
    
    def update_yield(self, query: str, new_urls: int):
        """
        Update yield score for query.
        """
        if query not in self._queries:
            return
        
        q = self._queries[query]
        q.total_executions += 1
        q.total_results += new_urls
        
        # Update yield (exponential moving average)
        current_yield = q.yield_score
        new_yield = 0.7 * current_yield + 0.3 * (1.0 if new_urls > 0 else 0)
        q.yield_score = new_yield
        
        # Track consecutive failures
        if new_urls == 0:
            q.consecutive_zero_yields += 1
        else:
            q.consecutive_zero_yields = 0
        
        # Update database (async task)
        import asyncio
        asyncio.create_task(self.db.update_keyword_yield(query, new_yield - current_yield))
    
    def expand_with_synonyms(self, query: str) -> List[str]:
        """
        Expand query with synonyms (depth 1 only).
        """
        words = query.lower().split()
        expansions = []
        
        for word in words:
            if word in SYNONYM_GRAPH:
                synonyms = SYNONYM_GRAPH[word]
                for syn in synonyms[:3]:  # Max 3 synonyms per word
                    new_query = query.replace(word, syn)
                    expansions.append(new_query)
        
        return expansions[:3]  # Max 3 expansions


class CoOccurrenceLearner:
    """
    Controlled co-occurrence learning.
    - Extract noun phrases
    - Frequency threshold
    - Contains benefit term
    - Capped promotions
    """
    
    def __init__(self, db: SupabaseStore):
        self.db = db
        self._promotions_this_cycle = 0
    
    def reset_cycle(self):
        """Reset cycle counter."""
        self._promotions_this_cycle = 0
    
    async def learn_from_content(self, content: Dict, is_valid_offer: bool):
        """
        Learn from page content.
        Only learns from valid offers.
        """
        if not is_valid_offer:
            return
        
        if self._promotions_this_cycle >= Limits.MAX_NEW_PROMOTIONS_PER_CYCLE:
            return
        
        text = content.get('text_lower', '')
        
        # Extract noun phrases
        from scorer import scorer
        phrases = scorer.extract_noun_phrases(text)
        
        # Filter for benefit-containing phrases
        benefit_phrases = [
            (phrase, count) for phrase, count in phrases
            if self._contains_benefit(phrase)
        ]
        
        # Increment frequencies
        for phrase, _ in benefit_phrases[:20]:  # Limit processing
            await self.db.increment_term_frequency(phrase, "benefit_context")
    
    def _contains_benefit(self, phrase: str) -> bool:
        """Check if phrase contains a benefit term."""
        return any(
            benefit in phrase
            for benefit in CORE_VOCABULARY["benefits"]
        )
    
    async def promote_eligible_terms(self) -> List[str]:
        """
        Promote terms that meet thresholds.
        """
        promotable = await self.db.get_promotable_terms()
        
        promoted = []
        for term in promotable:
            if self._promotions_this_cycle >= Limits.MAX_NEW_PROMOTIONS_PER_CYCLE:
                break
            
            success = await self.db.add_learned_term(term)
            if success:
                promoted.append(term)
                self._promotions_this_cycle += 1
        
        return promoted


class KeywordPruningEngine:
    """
    Removes low-performing keywords.
    - Track yield per keyword
    - Remove if 0 yield for 10 cycles
    - Preserve core vocabulary
    """
    
    def __init__(self, db: SupabaseStore):
        self.db = db
    
    async def prune_keywords(self):
        """
        Prune low-yield learned terms.
        Runs monthly.
        """
        await self.db.prune_low_yield_keywords()
    
    async def is_eligible_for_pruning(self, keyword: str) -> bool:
        """Check if keyword can be pruned."""
        # Core terms cannot be pruned
        all_core = (
            CORE_VOCABULARY["entities"] +
            CORE_VOCABULARY["benefits"] +
            CORE_VOCABULARY["program_phrases"] +
            CORE_VOCABULARY["verticals"]
        )
        return keyword not in all_core
