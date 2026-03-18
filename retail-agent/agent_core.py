"""
Agent Reasoning Core — The brain of the web agent.
Implements the ReAct loop: Observe → Reason → Act → Evaluate.

Uses the LLM to make strategic decisions about:
  - Which tool to use next
  - What queries to search
  - Which domains to explore deeper
  - When to adjust keyword strategy
"""
import json
import asyncio
import traceback
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass

from llm_client import agent_llm, LLMResponse
from agent_tools import ToolRegistry, ToolResult
from agent_memory import AgentMemory, AgentState
from database import SupabaseStore, CompetitorPrice
from canonicalizer import canonicalizer
from config import Limits, TrustDecay, Thresholds
from shop_manager import ShopManager, CategoryKeywordManager, ProductDiscoveryFilter
from agent_analytics import AnalyticsEngine


SYSTEM_PROMPT = """You are an autonomous web agent whose goal is:

  "Monitor competitor prices and discover product pricing across retail websites."

You operate in a Observe → Reason → Act loop. Each cycle, you analyze the current
state of your database and decide your next action.

Available tools:
1. search_web — Search DuckDuckGo for a query. Returns URLs AND auto-fetches, scores, and stores valid prices.
2. browse_page — Fetch a single URL and score it. Use for specific URLs you want to check.
3. expand_keywords — Generate new search query combinations, optionally focused on a vertical.
4. deep_crawl — Crawl a domain page to find internal pricing/product links and auto-score them.
5. query_stats — Get current database statistics.

STRATEGY GUIDELINES:
- search_web is your PRIMARY tool. It auto-processes all results (fetch + score + store).
- Use expand_keywords when yield is low to discover new query angles.
- Use deep_crawl on high-trust domains to find more pricing pages.
- Use browse_page only for specific URLs not from search results.
- Use query_stats to check progress.
- Vary your queries: try different verticals (electronics, laptops, phones, appliances, etc.).
- Avoid repeating the exact same queries.

IMPORTANT RULES:
- Always respond with valid JSON only. No text before or after.
- Choose ONE action per step.
- Never generate harmful, offensive, or illegal queries.

Your JSON response MUST follow this schema:
{
  "reasoning": "Brief explanation of why you chose this action",
  "action": "tool_name",
  "parameters": { ... }
}

Parameter schemas:
- search_web: {"query": "search string"}
- browse_page: {"url": "https://..."}
- expand_keywords: {"focus_vertical": "optional vertical", "recent_terms": ["optional", "terms"]}
- deep_crawl: {"url": "https://..."}
- query_stats: {}
"""


@dataclass
class AgentDecision:
    """Parsed agent decision."""
    reasoning: str
    action: str
    parameters: Dict
    raw_response: str


class AgentReasoningCore:
    """
    The reasoning engine of the web agent.
    Implements the full ReAct cycle.
    Now with multi-tenant support for multiple shops.
    """

    def __init__(self, db: SupabaseStore, shop_id: int = 1):
        self.db = db
        self.shop_id = shop_id
        self.tools = ToolRegistry(db)
        self.memory = AgentMemory(db)
        self._max_actions_per_cycle = 15  # Guardrail: max tool calls per cycle
        self._cycle_count = 0
        
        # Multi-tenant managers
        self.shop_mgr = ShopManager(db)
        self.keyword_mgr = CategoryKeywordManager(db)
        self.analytics = AnalyticsEngine(db)
        self.filter: Optional[ProductDiscoveryFilter] = None
        self.shop = None
        self._initialized = False

    async def initialize(self):
        """
        Initialize agent for a specific shop.
        Load shop configuration and category keywords.
        """
        try:
            print(f"[Agent] Initializing shop {self.shop_id}...")
            
            # Load shop configuration
            self.shop = await self.shop_mgr.get_shop(self.shop_id)
            if not self.shop:
                print(f"[Agent] ERROR: Shop {self.shop_id} not found")
                raise ValueError(f"Shop {self.shop_id} not found")
            
            print(f"[Agent] Loaded shop: {self.shop.shop_name} ({self.shop.category})")
            
            # Create product filter for this shop
            self.filter = ProductDiscoveryFilter(self.shop)
            
            # Initialize keywords for shop's category
            await self.keyword_mgr.initialize_shop_keywords(self.shop_id, self.shop.category)
            
            keywords = await self.keyword_mgr.get_active_keywords_for_shop(
                self.shop_id,
                self.shop.category,
                limit=50
            )
            print(f"[Agent] Initialized {len(keywords)} keywords for {self.shop.category}")
            print(f"[Agent] Sample keywords: {keywords[:5]}")
            
            # Mark shop as active
            await self.shop_mgr.update_shop_last_active(self.shop_id)
            
            self._initialized = True
            print(f"[Agent] Shop {self.shop_id} initialized and ready")
        except Exception as e:
            print(f"[Agent] Initialization error: {e}")
            traceback.print_exc()
            raise

    async def run_cycle(self) -> Dict:
        """
        Execute one complete agent reasoning cycle.
        Returns cycle summary with analytics.
        """
        # Ensure initialized
        if not self._initialized:
            await self.initialize()
        
        self._cycle_count += 1
        self.memory.state.cycle_number = self._cycle_count
        cycle_start = datetime.utcnow()
        actions_taken = 0
        prices_found = 0
        urls_processed = 0

        print(f"\n{'='*60}")
        print(f"[Agent] Cycle #{self._cycle_count} | Shop: {self.shop.shop_name} | {cycle_start.isoformat()}")
        print(f"{'='*60}")

        # Step 1: Observe
        print("[Agent] Observing database state...")
        state = await self.memory.observe()
        context = self.memory.build_context_prompt()

        # Step 2: Multi-step ReAct loop
        while actions_taken < self._max_actions_per_cycle:
            try:
                # Reason
                decision = await self._reason(context, actions_taken)
                if decision is None:
                    print("[Agent] LLM reasoning failed, falling back to default search")
                    decision = self._fallback_decision()

                print(f"[Agent] Decision: {decision.action} — {decision.reasoning[:80]}")

                # Act
                result = await self._execute_action(decision)
                actions_taken += 1

                # Evaluate & process result
                cycle_prices = await self._evaluate_and_process(decision, result)
                prices_found += cycle_prices

                # Record decision
                self.memory.record_decision({
                    "action": decision.action,
                    "params": str(decision.parameters)[:100],
                    "result_summary": result.summary[:100],
                    "prices": cycle_prices,
                })

                # Update context with result for next reasoning step
                context = self._update_context(context, decision, result)

                # Exit conditions
                if decision.action == "query_stats":
                    continue  # Stats don't count, keep going
                if actions_taken >= 3 and decision.action == "expand_keywords":
                    continue  # Keyword expansion leads to more searches
                if actions_taken >= self._max_actions_per_cycle:
                    print("[Agent] Max actions per cycle reached")
                    break

                # After a search → browse → score chain, do a few more
                if actions_taken >= 8:
                    # Check if we should keep going
                    if prices_found == 0 and actions_taken >= 10:
                        print("[Agent] No prices after 10 actions, ending cycle")
                        break

            except Exception as e:
                print(f"[Agent] Action error: {e}")
                traceback.print_exc()
                actions_taken += 1
                if actions_taken >= 3:
                    break

        # Step 3: Flush and record
        await self.db.flush_batch()
        self.memory.record_cycle_yield(prices_found)
        
        # Step 4: Mark shop active and run analytics
        await self.shop_mgr.update_shop_last_active(self.shop_id)

        cycle_time = (datetime.utcnow() - cycle_start).total_seconds()

        summary = {
            "cycle": self._cycle_count,
            "shop_id": self.shop_id,
            "shop_name": self.shop.shop_name,
            "actions_taken": actions_taken,
            "prices_found": prices_found,
            "duration_seconds": cycle_time,
            "llm_calls_remaining": agent_llm.calls_remaining,
        }

        print(f"\n[Agent] Cycle #{self._cycle_count} complete: "
              f"{actions_taken} actions, {prices_found} prices, "
              f"{cycle_time:.1f}s")
        
        # Run analytics suite (all 5 features)
        try:
            print(f"\n[Agent] Running analytics for {self.shop.shop_name}...")
            analytics_results = await self.analytics.run_full_analytics_cycle(self.shop_id)
            summary["analytics"] = analytics_results
            
            # Print analytics report
            report = self.analytics.format_analytics_report(analytics_results, self.shop_id)
            print(f"\n{report}")
        except Exception as e:
            print(f"[Agent] Analytics error: {e}")
            traceback.print_exc()

        return summary

    async def _reason(self, context: str, step: int) -> Optional[AgentDecision]:
        """
        Ask the LLM to reason about the next action.
        Uses async areason() to avoid blocking the event loop.
        """
        user_prompt = f"""{context}

Step {step + 1} of this cycle. What should I do next?
Respond with JSON only."""

        response = await agent_llm.areason(SYSTEM_PROMPT, user_prompt)

        if not response.success:
            print(f"[Agent] LLM error: {response.error}")
            return None

        print(f"[Agent] LLM latency: {response.latency_ms:.0f}ms")

        if response.parsed:
            try:
                return AgentDecision(
                    reasoning=response.parsed.get("reasoning", ""),
                    action=response.parsed.get("action", "search_web"),
                    parameters=response.parsed.get("parameters", {}),
                    raw_response=response.raw,
                )
            except Exception:
                pass

        # Failed to parse structured output
        print(f"[Agent] Could not parse LLM output: {response.raw[:200]}")
        return None

    def _fallback_decision(self) -> AgentDecision:
        """Fallback when LLM fails — do a default search."""
        import random
        from config import CORE_VOCABULARY
        entity = random.choice(CORE_VOCABULARY["entities"][:5])
        benefit = random.choice(CORE_VOCABULARY["benefits"][:5])
        query = f"{entity} {benefit}"

        return AgentDecision(
            reasoning="LLM fallback: random search query",
            action="search_web",
            parameters={"query": query},
            raw_response="",
        )

    async def _execute_action(self, decision: AgentDecision) -> ToolResult:
        """Execute the decided action using the appropriate tool."""
        action = decision.action
        params = decision.parameters

        if action == "search_web":
            query = params.get("query", "price comparison electronics")
            return await self.tools.search.execute(query)

        elif action == "browse_page":
            url = params.get("url", "")
            if not url or not url.startswith("http"):
                return ToolResult(
                    tool_name=action, success=False,
                    error="Invalid URL", summary="Invalid URL provided"
                )
            return await self.tools.browse.execute(url)

        elif action == "score_page":
            # LLM should not call score_page directly;
            # redirect to browse_page which auto-scores
            url = params.get("url", "")
            if url and url.startswith("http"):
                return await self.tools.browse.execute(url)
            return ToolResult(
                tool_name=action, success=False,
                error="Scoring is automatic via search_web and browse_page",
                summary="Use search_web or browse_page instead"
            )

        elif action == "expand_keywords":
            return await self.tools.keywords.execute(
                focus_vertical=params.get("focus_vertical"),
                recent_terms=params.get("recent_terms"),
            )

        elif action == "deep_crawl":
            url = params.get("url", "")
            if not url:
                return ToolResult(
                    tool_name=action, success=False,
                    error="No URL", summary="No URL for deep crawl"
                )
            return await self.tools.deep_crawl.execute(url)

        elif action == "query_stats":
            return await self.tools.stats.execute()

        else:
            return ToolResult(
                tool_name=action, success=False,
                error=f"Unknown action: {action}",
                summary=f"Unknown action: {action}"
            )

    async def _evaluate_and_process(
        self, decision: AgentDecision, result: ToolResult
    ) -> int:
        """
        Evaluate a tool result and process it.
        For search results: auto-browse and score top URLs.
        Returns number of prices found.
        """
        prices_found = 0

        if not result.success:
            print(f"[Agent] Tool failed: {result.error}")
            return 0

        # AUTO-PIPELINE: search → browse → score → store
        if decision.action == "search_web" and result.data:
            urls = result.data.get("urls", [])
            print(f"[Agent] Processing {len(urls)} search results...")

            for url in urls[:10]:  # Cap per search
                try:
                    # Canonicalize and dedup
                    if not canonicalizer.is_valid_url(url):
                        continue
                    canonical, url_hash = canonicalizer.canonicalize(url)
                    if canonicalizer.is_duplicate(url_hash):
                        continue
                    if await self.db.is_url_processed(url_hash):
                        canonicalizer.mark_seen(url_hash)
                        continue
                    canonicalizer.mark_seen(url_hash)

                    domain = canonicalizer.extract_domain(canonical)
                    
                    # Filter: Skip our own domain (competitors only)
                    if self.filter and domain == self.shop.shop_domain:
                        print(f"[Agent] Skipped own domain: {domain}")
                        continue
                    
                    if await self.db.is_domain_blacklisted(domain):
                        continue

                    # Browse
                    browse_result = await self.tools.browse.execute(canonical)
                    if not browse_result.success:
                        continue

                    content = browse_result.data.get("full_content")
                    if not content:
                        continue

                    # Get domain trust
                    domain_obj = await self.db.get_domain(domain)
                    domain_trust = domain_obj.trust_score if domain_obj else 0

                    # Score
                    score_result = await self.tools.score.execute(content, domain_trust)
                    if not score_result.success:
                        continue

                    score_data = score_result.data

                    # Store processed URL
                    await self.db.batch_insert_urls([{
                        'url_hash': url_hash,
                        'canonical_url': canonical,
                        'domain': domain,
                        'processed_at': datetime.utcnow().isoformat(),
                        'score': score_data['score'],
                        'spam_score': score_data['spam_score'],
                        'is_offer': score_data['is_offer'],
                    }])

                    # Handle results
                    if score_data['is_hard_rejected']:
                        await self.db.create_or_update_domain(
                            domain,
                            trust_delta=TrustDecay.SPAM_DETECTION_PENALTY,
                            is_spam=True,
                        )
                        continue

                    if score_data['is_offer']:
                        await self.db.create_or_update_domain(
                            domain,
                            trust_delta=TrustDecay.VALID_OFFER_BONUS,
                            is_offer=True,
                        )

                        # Extract prices from page content
                        from scorer import scorer as _scorer
                        extracted_prices = _scorer.extract_prices(
                            browse_result.data.get("text_snippet", "")
                        )
                        price_val = extracted_prices[0].amount if extracted_prices else None
                        currency = extracted_prices[0].currency if extracted_prices else 'USD'

                        # Skip entries with no real price
                        if not price_val or price_val <= 0:
                            print(f"[Agent] ✗ Skipped (no price): {canonical[:60]}")
                            continue

                        price = CompetitorPrice(
                            domain=domain,
                            url=canonical,
                            product_name=browse_result.data.get("title", "")[:450],
                            price=price_val,
                            currency=currency,
                            competitor_name=domain,
                            category=', '.join(score_data.get("benefits_found", [])[:3]) or 'general',
                            scraped_at=datetime.utcnow(),
                            shop_id=self.shop_id,  # Tag with shop_id for multi-tenant
                        )
                        await self.db.insert_competitor_price(price)
                        prices_found += 1
                        print(f"[Agent] ✓ Price: {canonical[:70]}...")

                except Exception as e:
                    print(f"[Agent] Error processing URL: {e}")
                    continue

        elif decision.action == "deep_crawl" and result.data:
            # Process priority links from deep crawl
            priority = result.data.get("priority_links", [])
            print(f"[Agent] Deep crawl found {len(priority)} priority links")

            for url in priority[:5]:
                try:
                    canonical, url_hash = canonicalizer.canonicalize(url)
                    if canonicalizer.is_duplicate(url_hash):
                        continue
                    if await self.db.is_url_processed(url_hash):
                        canonicalizer.mark_seen(url_hash)
                        continue
                    canonicalizer.mark_seen(url_hash)

                    domain = canonicalizer.extract_domain(canonical)

                    browse_result = await self.tools.browse.execute(canonical)
                    if not browse_result.success:
                        continue

                    content = browse_result.data.get("full_content")
                    if not content:
                        continue

                    domain_obj = await self.db.get_domain(domain)
                    domain_trust = domain_obj.trust_score if domain_obj else 0

                    score_result = await self.tools.score.execute(content, domain_trust)
                    if not score_result.success:
                        continue

                    score_data = score_result.data

                    await self.db.batch_insert_urls([{
                        'url_hash': url_hash,
                        'canonical_url': canonical,
                        'domain': domain,
                        'processed_at': datetime.utcnow().isoformat(),
                        'score': score_data['score'],
                        'spam_score': score_data['spam_score'],
                        'is_offer': score_data['is_offer'],
                    }])

                    if score_data['is_offer']:
                        await self.db.create_or_update_domain(
                            domain,
                            trust_delta=TrustDecay.VALID_OFFER_BONUS,
                            is_offer=True,
                        )

                        from scorer import scorer as _scorer
                        extracted_prices = _scorer.extract_prices(
                            browse_result.data.get("text_snippet", "")
                        )
                        price_val = extracted_prices[0].amount if extracted_prices else None
                        currency = extracted_prices[0].currency if extracted_prices else 'USD'

                        # Skip entries with no real price
                        if not price_val or price_val <= 0:
                            print(f"[Agent] ✗ Skipped (no price): {canonical[:60]}")
                            continue

                        price = CompetitorPrice(
                            domain=domain,
                            url=canonical,
                            product_name=browse_result.data.get("title", "")[:450],
                            price=price_val,
                            currency=currency,
                            competitor_name=domain,
                            category=', '.join(score_data.get("benefits_found", [])[:3]) or 'general',
                            scraped_at=datetime.utcnow(),
                            shop_id=self.shop_id,  # Tag with shop_id for multi-tenant
                        )
                        await self.db.insert_competitor_price(price)
                        prices_found += 1
                        print(f"[Agent] ✓ Deep crawl price: {canonical[:70]}...")

                except Exception as e:
                    print(f"[Agent] Deep crawl URL error: {e}")
                    continue

        elif decision.action == "expand_keywords" and result.data:
            queries = result.data.get("queries", [])
            print(f"[Agent] Generated {len(queries)} new queries, will search top ones")
            # The next reasoning step will pick these up from context

        return prices_found

    def _update_context(
        self, context: str, decision: AgentDecision, result: ToolResult
    ) -> str:
        """Append the latest action+result to context for next reasoning step."""
        result_summary = result.summary
        if result.data and decision.action == "search_web":
            urls = result.data.get("urls", [])
            result_summary += f"\nURLs found: {[u[:60] for u in urls[:5]]}"
        elif result.data and decision.action == "expand_keywords":
            queries = result.data.get("queries", [])
            result_summary += f"\nGenerated queries: {queries[:8]}"
        elif result.data and decision.action == "deep_crawl":
            plinks = result.data.get("priority_links", [])
            result_summary += f"\nPriority links: {[u[:60] for u in plinks[:5]]}"
        elif result.data and decision.action == "query_stats":
            result_summary += f"\nStats: {json.dumps(result.data, default=str)[:400]}"

        update = f"""
--- Action Taken ---
Tool: {decision.action}
Params: {json.dumps(decision.parameters, default=str)[:200]}
Result: {result_summary}
Success: {result.success}
"""
        return context + update

    async def shutdown(self):
        """Clean shutdown with final analytics run."""
        try:
            if self._initialized and self.shop_id:
                print(f"[Agent] Final analytics run for {self.shop.shop_name}...")
                final_results = await self.analytics.run_full_analytics_cycle(self.shop_id)
                report = self.analytics.format_analytics_report(final_results, self.shop_id)
                print(f"\n{report}")
        except Exception as e:
            print(f"[Agent] Final analytics error: {e}")
        
        await self.tools.close_all()
        await self.db.flush_batch()
        print(f"[Agent] Shutdown complete for shop {self.shop_id}")
