"""
DuckDuckGo Scraper (Hardened)
Rate limited, CAPTCHA-aware, defensive by design.
"""
import asyncio
import random
import time
from typing import List, Optional, Dict
from urllib.parse import unquote
import re

import aiohttp
from bs4 import BeautifulSoup

from config import DDG_URL, USER_AGENTS, Timing, Limits


class ScrapingError(Exception):
    """Base scraping exception."""
    pass


class RateLimitError(ScrapingError):
    """Rate limit or block detected."""
    pass


class CaptchaError(ScrapingError):
    """CAPTCHA detected."""
    pass


class DuckDuckGoScraper:
    """
    Hardened DuckDuckGo HTML scraper.
    - 1 req / 8-12 sec (randomized)
    - CAPTCHA pattern detection
    - Automatic cooldown on 429/403
    - Single page pagination only
    """
    
    def __init__(self):
        self._last_request_time = 0
        self._session: Optional[aiohttp.ClientSession] = None
        self._cooldown_until = 0
        
        # CAPTCHA detection patterns
        self._captcha_patterns = [
            r'captcha',
            r'are you human',
            r'prove you.*human',
            r'security check',
            r'verification required',
            r'please wait',
        ]
        
        # Block patterns
        self._block_patterns = [
            r'rate limit',
            r'too many requests',
            r'access denied',
            r'blocked',
        ]
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
            }
            
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=Timing.REQUEST_TIMEOUT)
            )
        
        return self._session
    
    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        now = time.time()
        
        # Check cooldown
        if now < self._cooldown_until:
            wait = self._cooldown_until - now
            print(f"[Scraper] Cooldown active: waiting {wait:.1f}s")
            await asyncio.sleep(wait)
        
        # Enforce min interval
        elapsed = now - self._last_request_time
        min_interval = random.uniform(
            Timing.SEARCH_MIN_INTERVAL,
            Timing.SEARCH_MAX_INTERVAL
        )
        
        if elapsed < min_interval:
            wait = min_interval - elapsed
            await asyncio.sleep(wait)
        
        self._last_request_time = time.time()
    
    def _check_for_captcha(self, html: str) -> bool:
        """Detect CAPTCHA or block pages."""
        text_lower = html.lower()
        
        for pattern in self._captcha_patterns:
            if re.search(pattern, text_lower):
                return True
        
        for pattern in self._block_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _extract_urls_from_html(self, html: str) -> List[str]:
        """Extract redirect URLs from DDG HTML response."""
        urls = []
        soup = BeautifulSoup(html, 'lxml')
        
        # Find result links
        for link in soup.find_all('a', class_='result__a'):
            href = link.get('href', '')
            if href:
                # DDG uses redirect URLs
                if 'uddg=' in href:
                    # Extract actual URL from redirect
                    match = re.search(r'uddg=([^&]+)', href)
                    if match:
                        actual_url = unquote(match.group(1))
                        urls.append(actual_url)
                elif href.startswith('http'):
                    urls.append(href)
        
        return urls
    
    async def search(self, query: str) -> List[str]:
        """
        Execute a single search query.
        Returns list of candidate URLs.
        """
        await self._rate_limit()
        
        session = await self._get_session()
        
        # Rotate user agent
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Referer': 'https://duckduckgo.com/',
            'Accept-Encoding': 'gzip, deflate'
        }

        payload = {
            'q': query,
            'kl': 'us-en',  # Region
        }
        
        try:
            async with session.post(
                DDG_URL,
                data=payload,
                headers=headers,
                ssl=False  # Some environments need this
            ) as response:
                
                status = response.status
                html = await response.text()
                
                # Log for monitoring
                print(f"[Scraper] Query: '{query[:50]}...' | Status: {status}")
                
                # Handle various status codes
                if status == 429:
                    self._cooldown_until = time.time() + Timing.COOLDOWN_ON_429
                    raise RateLimitError(f"Rate limited (429). Cooldown: {Timing.COOLDOWN_ON_429}s")
                
                if status == 403:
                    self._cooldown_until = time.time() + Timing.COOLDOWN_ON_429
                    raise RateLimitError(f"Blocked (403). Cooldown: {Timing.COOLDOWN_ON_429}s")
                
                if status != 200:
                    return []
                
                # Check for CAPTCHA
                if self._check_for_captcha(html):
                    self._cooldown_until = time.time() + Timing.COOLDOWN_ON_429
                    raise CaptchaError("CAPTCHA or challenge detected")
                
                # Extract URLs
                urls = self._extract_urls_from_html(html)
                print(f"[Scraper] Found {len(urls)} URLs")
                
                return urls
                
        except asyncio.TimeoutError:
            print(f"[Scraper] Timeout for query: {query[:50]}")
            return []
        
        except Exception as e:
            print(f"[Scraper] Error: {e}")
            return []
    
    async def search_batch(self, queries: List[str]) -> Dict[str, List[str]]:
        """
        Execute multiple queries sequentially (not parallel to avoid blocks).
        """
        results = {}
        
        for query in queries[:Limits.MAX_QUERIES_PER_CYCLE]:
            try:
                urls = await self.search(query)
                results[query] = urls
                
                # Add jitter between requests
                await asyncio.sleep(random.uniform(1.0, 3.0))
                
            except (RateLimitError, CaptchaError) as e:
                print(f"[Scraper] Stopped batch: {e}")
                break
        
        return results
    
    async def close(self):
        """Close session."""
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton
scraper = DuckDuckGoScraper()
