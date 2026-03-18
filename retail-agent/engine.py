"""
Stable Execution Controller
Main orchestration with safety guarantees.
"""
import asyncio
import random
import time
import traceback
import gc
from datetime import datetime
from typing import List, Dict, Optional
import json

from config import (
    Limits, Timing, TrustDecay
)
from database import SupabaseStore, CompetitorPrice
from scraper import scraper, RateLimitError, CaptchaError
from fetcher import fetcher, extractor
from canonicalizer import canonicalizer
from scorer import scorer, ScoreResult
from query_controller import QueryBudgetController, CoOccurrenceLearner, KeywordPruningEngine


class ExecutionController:
    """
    Main execution loop with stability guarantees.
    - try/except wrapped
    - Error logging
    - Automatic cooldown
    - Memory cleanup
    - Randomized sleep
    """
    
    def __init__(self):
        self.db = SupabaseStore()
        self.query_controller = QueryBudgetController(self.db)
        self.cooc_learner = CoOccurrenceLearner(self.db)
        self.pruner = KeywordPruningEngine(self.db)
        
        self._cycle_count = 0
        self._error_count = 0
        self._start_time = datetime.utcnow()
        self._running = False
    
    async def initialize(self):
        """Initialize database and load state."""
        print("[Engine] Initializing...")
        
        # Seed keywords
        await self.db.initialize_keyword_pool()
        
        # Sync query controller
        await self.query_controller.sync_with_db()
        
        print("[Engine] Initialized successfully")
    
    async def run_cycle(self):
        """
        Execute one complete scraping cycle.
        """
        cycle_start = time.time()
        self._cycle_count += 1
        
        print(f"\n{'='*60}")
        print(f"[Engine] Cycle #{self._cycle_count} | Time: {datetime.utcnow().isoformat()}")
        print(f"{'='*60}")
        
        try:
            # Reset cycle counters
            self.cooc_learner.reset_cycle()
            
            # Step 1: Select queries
            selected_queries = self.query_controller.select_queries()
            print(f"[Engine] Selected {len(selected_queries)} queries")
            
            # Step 2: Search DuckDuckGo
            try:
                results = await scraper.search_batch(selected_queries)
            except (RateLimitError, CaptchaError) as e:
                print(f"[Engine] Search blocked: {e}")
                await self._cooldown(Timing.COOLDOWN_ON_429)
                return
            
            # Collect all URLs
            all_urls = []
            for query, urls in results.items():
                all_urls.extend(urls)
                self.query_controller.update_yield(query, len(urls))
            
            print(f"[Engine] Total URLs discovered: {len(all_urls)}")
            
            if not all_urls:
                print("[Engine] No URLs found, skipping to next cycle")
                return
            
            # Step 3: Canonicalize and deduplicate
            unique_urls = await self._deduplicate_urls(all_urls)
            print(f"[Engine] Unique URLs after dedup: {len(unique_urls)}")
            
            # Step 4: Filter blacklisted domains
            filtered_urls = await self._filter_domains(unique_urls)
            print(f"[Engine] URLs after domain filter: {len(filtered_urls)}")
            
            # Step 5: Fetch content
            fetched = await fetcher.fetch_batch(filtered_urls)
            print(f"[Engine] Successfully fetched: {len(fetched)}")
            
            # Step 6: Process and score
            prices_found = 0
            for response in fetched:
                try:
                    price = await self._process_response(response)
                    if price:
                        prices_found += 1
                except Exception as e:
                    print(f"[Engine] Error processing response: {e}")
                    continue
            
            print(f"[Engine] Valid prices found: {prices_found}")
            
            # Step 7: Promote learned terms
            promoted = await self.cooc_learner.promote_eligible_terms()
            if promoted:
                print(f"[Engine] Promoted {len(promoted)} new terms: {promoted}")
            
            # Step 8: Flush batch inserts
            await self.db.flush_batch()
            
            # Step 9: Periodic maintenance
            if self._cycle_count % 100 == 0:
                await self._maintenance()
            
            # Reset error count on success
            self._error_count = 0
            
        except Exception as e:
            self._error_count += 1
            print(f"[Engine] Cycle error: {e}")
            traceback.print_exc()
            
            if self._error_count >= 3:
                print("[Engine] Multiple errors detected, entering cooldown")
                await self._cooldown(300)  # 5 min cooldown
                self._error_count = 0
    
    async def _deduplicate_urls(self, urls: List[str]) -> List[str]:
        """Canonicalize and deduplicate URLs."""
        unique = []
        
        for url in urls:
            if not canonicalizer.is_valid_url(url):
                continue
            
            canonical, url_hash = canonicalizer.canonicalize(url)
            
            # Layer 1: In-memory check
            if canonicalizer.is_duplicate(url_hash):
                continue
            
            # Layer 2: Database check
            if await self.db.is_url_processed(url_hash):
                canonicalizer.mark_seen(url_hash)
                continue
            
            canonicalizer.mark_seen(url_hash)
            unique.append(canonical)
        
        return unique
    
    async def _filter_domains(self, urls: List[str]) -> List[str]:
        """Filter out blacklisted domains."""
        filtered = []
        
        for url in urls:
            domain = canonicalizer.extract_domain(url)
            
            if await self.db.is_domain_blacklisted(domain):
                print(f"[Engine] Skipping blacklisted domain: {domain}")
                continue
            
            filtered.append(url)
        
        return filtered
    
    async def _process_response(self, response: Dict) -> Optional[CompetitorPrice]:
        """
        Process a single HTTP response.
        Extract, score, store competitor price if valid.
        """
        url = response['url']
        html = response['html']
        domain = canonicalizer.extract_domain(url)
        
        # Get domain trust
        domain_obj = await self.db.get_domain(domain)
        domain_trust = domain_obj.trust_score if domain_obj else 0
        
        # Extract content
        content = extractor.extract(html, url)
        if content is None:
            return None
        
        # Score content
        score_result = scorer.score_content(content, domain_trust)
        
        # Canonicalize for storage
        canonical, url_hash = canonicalizer.canonicalize(url)
        
        # Create processed URL record
        await self.db.batch_insert_urls([{
            'url_hash': url_hash,
            'canonical_url': canonical,
            'domain': domain,
            'processed_at': datetime.utcnow().isoformat(),
            'score': score_result.score,
            'spam_score': score_result.spam_score,
            'is_offer': score_result.is_offer
        }])
        
        # Handle hard rejections
        if score_result.is_hard_rejected:
            print(f"[Engine] Hard rejected (spam): {domain}")
            await self.db.create_or_update_domain(
                domain,
                trust_delta=TrustDecay.SPAM_DETECTION_PENALTY,
                is_spam=True
            )
            return None
        
        # Update domain
        if score_result.is_offer:
            await self.db.create_or_update_domain(
                domain,
                trust_delta=TrustDecay.VALID_OFFER_BONUS,
                is_offer=True
            )
        
        # Store valid competitor price
        if score_result.is_offer:
            benefits = scorer.get_benefits_found(content)
            
            # Extract prices from the page content
            extracted_prices = scorer.extract_prices(content.get('text', ''))
            price_val = extracted_prices[0].amount if extracted_prices else None
            currency = extracted_prices[0].currency if extracted_prices else 'USD'
            
            competitor_price = CompetitorPrice(
                domain=domain,
                url=canonical,
                product_name=content.get('title', '')[:450],
                price=price_val,
                currency=currency,
                competitor_name=domain,
                category=', '.join(benefits[:3]) if benefits else 'general',
                scraped_at=datetime.utcnow()
            )
            
            await self.db.insert_competitor_price(competitor_price)
            print(f"[Engine] ✓ Price stored: {canonical[:60]}...")
            
            # Learn from content
            await self.cooc_learner.learn_from_content(content, True)
            
            return competitor_price
        
        # Learn from rejections too (but don't promote)
        await self.cooc_learner.learn_from_content(content, False)
        
        return None
    
    async def _cooldown(self, seconds: int):
        """Cooldown with progress indicator."""
        print(f"[Engine] Cooling down for {seconds}s...")
        await asyncio.sleep(seconds)
    
    async def _maintenance(self):
        """Periodic maintenance tasks."""
        print("[Engine] Running maintenance...")
        
        # Archive old URLs
        await self.db.archive_old_urls()
        
        # Apply trust decay
        await self.db.apply_trust_decay()
        
        # Prune low-yield keywords
        await self.pruner.prune_keywords()
        
        # Memory cleanup
        gc.collect()
        
        print("[Engine] Maintenance complete")
    
    async def run_forever(self):
        """Main execution loop."""
        await self.initialize()
        
        self._running = True
        
        while self._running:
            try:
                await self.run_cycle()
                
                # Randomized sleep between cycles
                sleep_minutes = random.randint(
                    Timing.CYCLE_MIN_SLEEP,
                    Timing.CYCLE_MAX_SLEEP
                )
                print(f"[Engine] Sleeping {sleep_minutes} minutes until next cycle...")
                
                # Sleep in chunks to allow graceful shutdown
                for _ in range(sleep_minutes * 6):  # Check every 10 seconds
                    if not self._running:
                        break
                    await asyncio.sleep(10)
                    
            except KeyboardInterrupt:
                print("[Engine] Interrupted, shutting down...")
                break
            except Exception as e:
                print(f"[Engine] Critical error: {e}")
                traceback.print_exc()
                await self._cooldown(300)
        
        await self.shutdown()
    
    def stop(self):
        """Signal graceful shutdown."""
        self._running = False
    
    async def shutdown(self):
        """Clean shutdown."""
        print("[Engine] Shutting down...")
        
        # Flush remaining batches
        await self.db.flush_batch()
        
        # Close connections
        await scraper.close()
        await fetcher.close()
        
        # Final cleanup
        gc.collect()
        
        # Stats
        runtime = datetime.utcnow() - self._start_time
        print(f"[Engine] Total cycles: {self._cycle_count}")
        print(f"[Engine] Total runtime: {runtime}")
        print("[Engine] Shutdown complete")


def run():
    """Entry point."""
    controller = ExecutionController()
    
    try:
        asyncio.run(controller.run_forever())
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    run()
