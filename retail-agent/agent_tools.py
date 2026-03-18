"""
Agent Tools — Wraps existing modules as agent-callable tools.
Each tool has: name, description, execute(), and structured I/O.

Tools:
  1. search_web      — Search DuckDuckGo for competitor pricing URLs
  2. browse_page     — Fetch and extract content from a URL
  3. score_page      — Score extracted content for pricing page quality
  4. expand_keywords — Generate new search queries from vocabulary
  5. deep_crawl      — Find internal links on a high-trust domain
  6. query_stats     — Get current database statistics
"""
import asyncio
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin

from scraper import DuckDuckGoScraper, RateLimitError, CaptchaError
from fetcher import ContentFetcher, ContentExtractor
from canonicalizer import canonicalizer
from scorer import scorer, ScoreResult
from database import SupabaseStore
from config import CORE_VOCABULARY, SYNONYM_GRAPH, Limits


@dataclass
class ToolResult:
    """Standardized tool output."""
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    summary: str = ""


class SearchTool:
    """
    Tool 1: Search DuckDuckGo for competitor pricing URLs.
    Input:  query (str)
    Output: list of discovered URLs
    """
    name = "search_web"
    description = "Search DuckDuckGo for a query and return candidate URLs."

    def __init__(self):
        self._scraper = DuckDuckGoScraper()

    async def execute(self, query: str) -> ToolResult:
        try:
            urls = await self._scraper.search(query)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"query": query, "urls": urls, "count": len(urls)},
                summary=f"Found {len(urls)} URLs for '{query}'"
            )
        except (RateLimitError, CaptchaError) as e:
            return ToolResult(
                tool_name=self.name, success=False,
                error=str(e), summary=f"Search blocked: {e}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, success=False,
                error=str(e), summary=f"Search error: {e}"
            )

    async def close(self):
        await self._scraper.close()


class BrowseTool:
    """
    Tool 2: Fetch and extract content from a URL.
    Input:  url (str)
    Output: extracted content dict (title, text, links, etc.)
    """
    name = "browse_page"
    description = "Fetch a web page and extract its text content, title, and link counts."

    def __init__(self):
        self._fetcher = ContentFetcher()
        self._extractor = ContentExtractor()

    async def execute(self, url: str) -> ToolResult:
        try:
            response = await self._fetcher.fetch_with_retry(url)
            if response is None:
                return ToolResult(
                    tool_name=self.name, success=False,
                    error="Fetch failed", summary=f"Could not fetch {url}"
                )

            content = self._extractor.extract(response['html'], url)
            if content is None:
                return ToolResult(
                    tool_name=self.name, success=False,
                    error="Extraction failed",
                    summary=f"Content extraction failed for {url}"
                )

            return ToolResult(
                tool_name=self.name, success=True,
                data={
                    "url": url,
                    "domain": canonicalizer.extract_domain(url),
                    "title": content.get("title", ""),
                    "description": content.get("description", ""),
                    "text_snippet": content.get("text", "")[:500],
                    "outbound_links": content.get("outbound_link_count", 0),
                    "word_count": content.get("word_count", 0),
                    "is_listicle": content.get("is_listicle", False),
                    "full_content": content,  # For scoring
                },
                summary=f"Fetched '{content.get('title', '')[:50]}' from {canonicalizer.extract_domain(url)}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, success=False,
                error=str(e), summary=f"Browse error: {e}"
            )

    async def close(self):
        await self._fetcher.close()


class ScoreTool:
    """
    Tool 3: Score content for pricing page quality.
    Input:  content dict (from BrowseTool)
    Output: score result with decision
    """
    name = "score_page"
    description = "Score extracted page content to determine if it's a legitimate pricing page."

    async def execute(self, content: Dict, domain_trust: float = 0) -> ToolResult:
        try:
            result = scorer.score_content(content, domain_trust)
            benefits = scorer.get_benefits_found(content)

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "score": result.score,
                    "spam_score": result.spam_score,
                    "is_offer": result.is_offer,
                    "is_hard_rejected": result.is_hard_rejected,
                    "matches": result.matches,
                    "benefits_found": benefits,
                    "domain_bonus": result.domain_bonus,
                },
                summary=f"Score: {result.score}, Spam: {result.spam_score}, "
                         f"Offer: {result.is_offer}, Rejected: {result.is_hard_rejected}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, success=False,
                error=str(e), summary=f"Scoring error: {e}"
            )


class KeywordExpansionTool:
    """
    Tool 4: Generate new search queries from vocabulary + synonyms.
    Input:  focus_vertical (str, optional), recent_successes (list, optional)
    Output: list of new query strings
    """
    name = "expand_keywords"
    description = "Generate new search query combinations. Optionally focus on a specific vertical or expand from recent successful terms."

    async def execute(
        self,
        focus_vertical: Optional[str] = None,
        recent_terms: Optional[List[str]] = None,
    ) -> ToolResult:
        try:
            queries = []

            entities = CORE_VOCABULARY["entities"]
            benefits = CORE_VOCABULARY["benefits"]
            verticals = CORE_VOCABULARY["verticals"]

            if focus_vertical:
                # Focus on a specific vertical
                for benefit in benefits[:6]:
                    queries.append(f"{focus_vertical} {benefit} price")
                for entity in entities[:5]:
                    queries.append(f"{entity} {focus_vertical} {benefit}")
            elif recent_terms:
                # Expand from recent successful terms using synonyms
                for term in recent_terms[:5]:
                    words = term.lower().split()
                    for word in words:
                        if word in SYNONYM_GRAPH:
                            for syn in SYNONYM_GRAPH[word][:3]:
                                new_q = term.replace(word, syn)
                                queries.append(new_q)
            else:
                # Default: generate diverse combinations
                import random
                sampled_entities = random.sample(entities, min(5, len(entities)))
                sampled_benefits = random.sample(benefits, min(5, len(benefits)))
                for e in sampled_entities:
                    for b in sampled_benefits:
                        queries.append(f"{e} {b}")

            # Deduplicate
            queries = list(dict.fromkeys(queries))[:15]

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={"queries": queries, "count": len(queries)},
                summary=f"Generated {len(queries)} new queries"
                         + (f" (vertical: {focus_vertical})" if focus_vertical else "")
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, success=False,
                error=str(e), summary=f"Keyword expansion error: {e}"
            )


class DeepCrawlTool:
    """
    Tool 5: Find internal links on a domain's page.
    Input:  url (str) — a page on the target domain
    Output: list of internal links (pricing/product pages prioritized)
    """
    name = "deep_crawl"
    description = "Fetch a page and extract internal links, prioritizing paths that look like pricing/product pages."

    def __init__(self):
        self._fetcher = ContentFetcher()

    async def execute(self, url: str) -> ToolResult:
        try:
            response = await self._fetcher.fetch_with_retry(url)
            if response is None:
                return ToolResult(
                    tool_name=self.name, success=False,
                    error="Fetch failed", summary=f"Could not fetch {url}"
                )

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response['html'], 'lxml')
            base_domain = canonicalizer.extract_domain(url)

            internal_links = []
            priority_links = []
            priority_keywords = [
                'price', 'pricing', 'product', 'shop', 'store',
                'catalog', 'buy', 'deal', 'offer', 'sale',
                'compare', 'checkout', 'cart', 'category'
            ]

            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                full_url = urljoin(url, href)
                link_domain = canonicalizer.extract_domain(full_url)

                if link_domain == base_domain and full_url.startswith('https://'):
                    path_lower = urlparse(full_url).path.lower()
                    text_lower = a_tag.get_text(strip=True).lower()

                    if any(kw in path_lower or kw in text_lower
                           for kw in priority_keywords):
                        priority_links.append(full_url)
                    else:
                        internal_links.append(full_url)

            # Deduplicate, prioritize
            priority_links = list(dict.fromkeys(priority_links))[:10]
            internal_links = list(dict.fromkeys(internal_links))[:20]

            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "domain": base_domain,
                    "priority_links": priority_links,
                    "other_links": internal_links,
                    "total": len(priority_links) + len(internal_links),
                },
                summary=f"Found {len(priority_links)} priority + {len(internal_links)} other links on {base_domain}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, success=False,
                error=str(e), summary=f"Deep crawl error: {e}"
            )

    async def close(self):
        await self._fetcher.close()


class StatsTool:
    """
    Tool 6: Get current database statistics for reasoning.
    Input:  none
    Output: stats dict
    """
    name = "query_stats"
    description = "Get current database statistics: total URLs processed, prices found, top domains, keyword performance."

    def __init__(self, db: SupabaseStore):
        self.db = db

    async def execute(self) -> ToolResult:
        try:
            total_urls = await self.db.count_processed()
            total_prices = await self.db.count_prices()

            # Top domains by trust
            top_domains_result = self.db.client.table("domains") \
                .select("domain, trust_score, offer_count, spam_count") \
                .order("trust_score", desc=True) \
                .limit(10) \
                .execute()

            # Recent competitor prices
            recent_prices_result = self.db.client.table("competitor_prices") \
                .select("domain, product_name, price, currency, scraped_at") \
                .order("scraped_at", desc=True) \
                .limit(5) \
                .execute()

            # Active keyword count
            active_kw = self.db.client.table("keyword_pool") \
                .select("*", count="exact") \
                .eq("is_active", True) \
                .execute()

            # Blacklisted domains
            blacklisted = self.db.client.table("domains") \
                .select("*", count="exact") \
                .eq("is_blacklisted", True) \
                .execute()

            stats = {
                "total_urls_processed": total_urls,
                "total_prices_collected": total_prices,
                "active_keywords": active_kw.count or 0,
                "blacklisted_domains": blacklisted.count or 0,
                "top_domains": top_domains_result.data[:5],
                "recent_prices": [
                    {
                        "domain": p["domain"],
                        "product": (p.get("product_name") or "")[:60],
                        "price": p.get("price"),
                        "currency": p.get("currency", "USD"),
                    }
                    for p in (recent_prices_result.data or [])
                ],
            }

            return ToolResult(
                tool_name=self.name,
                success=True,
                data=stats,
                summary=f"Processed: {total_urls} URLs, Collected: {total_prices} prices, "
                         f"Active Keywords: {active_kw.count or 0}"
            )
        except Exception as e:
            return ToolResult(
                tool_name=self.name, success=False,
                error=str(e), summary=f"Stats error: {e}"
            )


class ToolRegistry:
    """Registry of all available agent tools."""

    def __init__(self, db: SupabaseStore):
        self.search = SearchTool()
        self.browse = BrowseTool()
        self.score = ScoreTool()
        self.keywords = KeywordExpansionTool()
        self.deep_crawl = DeepCrawlTool()
        self.stats = StatsTool(db)

        self._tools = {
            "search_web": self.search,
            "browse_page": self.browse,
            "score_page": self.score,
            "expand_keywords": self.keywords,
            "deep_crawl": self.deep_crawl,
            "query_stats": self.stats,
        }

    def get(self, name: str):
        return self._tools.get(name)

    def list_tools(self) -> List[Dict]:
        """Return tool descriptions for the LLM prompt."""
        return [
            {"name": name, "description": tool.description}
            for name, tool in self._tools.items()
        ]

    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    async def close_all(self):
        await self.search.close()
        await self.browse.close()
        await self.deep_crawl.close()
