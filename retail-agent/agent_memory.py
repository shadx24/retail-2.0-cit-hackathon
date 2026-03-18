"""
Agent Memory — Observes database state and builds context for reasoning.
Provides the agent with awareness of what has happened, what's working,
and what needs attention.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from database import SupabaseStore


@dataclass
class AgentState:
    """Snapshot of the agent's current world-state."""
    cycle_number: int = 0
    total_urls_processed: int = 0
    total_prices_collected: int = 0
    active_keywords: int = 0
    blacklisted_domains: int = 0
    top_domains: List[Dict] = field(default_factory=list)
    recent_prices: List[Dict] = field(default_factory=list)
    last_cycle_yield: int = 0
    consecutive_low_yield: int = 0
    discovery_rate: float = 0.0      # prices per cycle (moving avg)
    spam_rate: float = 0.0           # spam per cycle (moving avg)
    agent_decisions_log: List[Dict] = field(default_factory=list)


class AgentMemory:
    """
    Memory layer for the web agent.
    Observes database, tracks performance, and provides context.
    """

    def __init__(self, db: SupabaseStore):
        self.db = db
        self.state = AgentState()
        self._decision_log: List[Dict] = []
        self._cycle_yields: List[int] = []
        self._max_decision_log = 50

    async def observe(self) -> AgentState:
        """
        Observe current database state and return AgentState.
        This is step 1 of the Observe → Think → Act loop.
        """
        try:
            # Counts
            self.state.total_urls_processed = await self.db.count_processed()
            self.state.total_prices_collected = await self.db.count_prices()

            # Active keywords
            kw_result = self.db.client.table("keyword_pool") \
                .select("*", count="exact") \
                .eq("is_active", True) \
                .execute()
            self.state.active_keywords = kw_result.count or 0

            # Blacklisted
            bl_result = self.db.client.table("domains") \
                .select("*", count="exact") \
                .eq("is_blacklisted", True) \
                .execute()
            self.state.blacklisted_domains = bl_result.count or 0

            # Top domains
            top_result = self.db.client.table("domains") \
                .select("domain, trust_score, offer_count, spam_count") \
                .eq("is_blacklisted", False) \
                .order("trust_score", desc=True) \
                .limit(10) \
                .execute()
            self.state.top_domains = top_result.data or []

            # Recent competitor prices
            recent_result = self.db.client.table("competitor_prices") \
                .select("domain, product_name, price, currency, scraped_at") \
                .order("scraped_at", desc=True) \
                .limit(10) \
                .execute()
            self.state.recent_prices = [
                {
                    "domain": p["domain"],
                    "product": (p.get("product_name") or "")[:60],
                    "price": p.get("price"),
                    "currency": p.get("currency", "USD"),
                }
                for p in (recent_result.data or [])
            ]

            # Discovery rate (moving average)
            if self._cycle_yields:
                self.state.discovery_rate = sum(self._cycle_yields[-5:]) / len(self._cycle_yields[-5:])

            # Recent decisions
            self.state.agent_decisions_log = self._decision_log[-5:]

        except Exception as e:
            print(f"[Memory] Observation error: {e}")

        return self.state

    def record_cycle_yield(self, prices_found: int):
        """Record how many prices were found this cycle."""
        self._cycle_yields.append(prices_found)
        self.state.last_cycle_yield = prices_found

        if prices_found == 0:
            self.state.consecutive_low_yield += 1
        else:
            self.state.consecutive_low_yield = 0

    def record_decision(self, decision: Dict):
        """Record an agent decision for context."""
        entry = {
            "cycle": self.state.cycle_number,
            "time": datetime.utcnow().isoformat(),
            **decision,
        }
        self._decision_log.append(entry)
        if len(self._decision_log) > self._max_decision_log:
            self._decision_log = self._decision_log[-self._max_decision_log:]

    def build_context_prompt(self) -> str:
        """
        Build a context string for the LLM reasoning prompt.
        Summarizes the agent's current world-state.
        """
        s = self.state

        top_domains_str = ""
        if s.top_domains:
            top_domains_str = "\n".join(
                f"  - {d['domain']}: trust={d['trust_score']}, offers={d['offer_count']}, spam={d['spam_count']}"
                for d in s.top_domains[:5]
            )

        recent_prices_str = ""
        if s.recent_prices:
            recent_prices_str = "\n".join(
                f"  - {p['domain']}: {p['product']} — {p.get('currency', 'USD')} {p.get('price', 'N/A')}"
                for p in s.recent_prices[:5]
            )

        recent_decisions_str = ""
        if s.agent_decisions_log:
            recent_decisions_str = "\n".join(
                f"  - Cycle {d.get('cycle', '?')}: action={d.get('action', '?')}, "
                f"result={d.get('result_summary', '?')}"
                for d in s.agent_decisions_log
            )

        return f"""=== PRICE MONITOR STATE (Cycle #{s.cycle_number}) ===

Performance:
  Total URLs processed: {s.total_urls_processed}
  Total prices collected: {s.total_prices_collected}
  Last cycle yield: {s.last_cycle_yield} prices
  Consecutive low-yield cycles: {s.consecutive_low_yield}
  Discovery rate (avg): {s.discovery_rate:.1f} prices/cycle
  Active keywords: {s.active_keywords}
  Blacklisted domains: {s.blacklisted_domains}

Top Trusted Domains:
{top_domains_str or "  (none yet)"}

Recent Prices Collected:
{recent_prices_str or "  (none yet)"}

Recent Agent Decisions:
{recent_decisions_str or "  (none yet)"}
"""
