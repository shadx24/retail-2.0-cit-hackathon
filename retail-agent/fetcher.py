"""
Async Fetch Layer
Concurrent page fetching with retry logic.
Max concurrency: 2-3, 1 req/sec per worker.
"""
import asyncio
import random
import time
from typing import Optional, Dict, List
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from config import Timing, Limits
from canonicalizer import canonicalizer


class FetchError(Exception):
    """Fetch error."""
    pass


class ContentFetcher:
    """
    Fetches page content with controlled concurrency.
    - Max 2-3 concurrent requests
    - 1 req/sec per worker
    - Retry with exponential backoff
    - Skip non-HTTPS
    """
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(Limits.MAX_CONCURRENCY)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create session."""
        if self._session is None or self._session.closed:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            connector = aiohttp.TCPConnector(
                limit=Limits.MAX_CONCURRENCY,
                limit_per_host=2,
                enable_cleanup_closed=True,
                force_close=True,
            )
            
            timeout = aiohttp.ClientTimeout(total=Timing.REQUEST_TIMEOUT)
            
            self._session = aiohttp.ClientSession(
                headers=headers,
                connector=connector,
                timeout=timeout
            )
        
        return self._session
    
    async def fetch_with_retry(self, url: str) -> Optional[Dict]:
        """
        Fetch URL with retry logic.
        Returns dict with content or None on failure.
        """
        session = await self._get_session()
        
        for attempt in range(Limits.MAX_RETRIES):
            try:
                async with self._semaphore:
                    # Enforce rate limit per worker
                    await asyncio.sleep(1.0 / Timing.REQUESTS_PER_SECOND_PER_WORKER)
                    
                    async with session.get(url, ssl=False) as response:
                        if response.status == 200:
                            html = await response.text()
                            return {
                                'url': url,
                                'html': html,
                                'status': response.status,
                                'content_type': response.headers.get('content-type', '')
                            }
                        
                        elif response.status in (429, 503, 502, 504):
                            # Server issues - exponential backoff
                            backoff = (Timing.RETRY_BACKOFF_BASE ** attempt) + random.uniform(0, 2)
                            await asyncio.sleep(backoff)
                            continue
                        
                        else:
                            return None
                            
            except asyncio.TimeoutError:
                if attempt == Limits.MAX_RETRIES - 1:
                    return None
                await asyncio.sleep(Timing.RETRY_BACKOFF_BASE ** attempt)
            
            except Exception as e:
                print(f"[Fetcher] Error fetching {url}: {e}")
                if attempt == Limits.MAX_RETRIES - 1:
                    return None
                await asyncio.sleep(2 ** attempt)
        
        return None
    
    async def fetch_batch(self, urls: List[str]) -> List[Dict]:
        """
        Fetch multiple URLs with controlled concurrency.
        """
        # Filter non-HTTPS
        valid_urls = [u for u in urls if u.startswith('https://')]
        if len(valid_urls) != len(urls):
            print(f"[Fetcher] Filtered {len(urls) - len(valid_urls)} non-HTTPS URLs")
        
        tasks = [self.fetch_with_retry(url) for url in valid_urls]
        results = await asyncio.gather(*tasks)
        
        # Filter successful results
        successful = [r for r in results if r is not None]
        print(f"[Fetcher] Successfully fetched {len(successful)}/{len(valid_urls)} URLs")
        
        return successful
    
    async def close(self):
        """Close session and free memory."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        
        # Force garbage collection hint
        import gc
        gc.collect()


class ContentExtractor:
    """
    Extract meaningful content from HTML.
    - Main text extraction
    - Outbound link counting
    - Listicle pattern detection
    - Affiliate link detection
    """
    
    # Listicle patterns
    LISTICLE_PATTERNS = [
        r'top\s+\d+',
        r'best\s+\d+',
        r'\d+\s+best',
        r'\d+\s+ways?\s+to',
        r'\d+\s+tips',
        r'\d+\s+tricks',
    ]
    
    # Affiliate patterns
    AFFILIATE_PARAMS = ['ref', 'affiliate', 'aff', 'tag', 'sponsored']
    
    def extract(self, html: str, base_url: str) -> Optional[Dict]:
        """
        Extract content from HTML.
        Returns dict with extracted data or None if rejected.
        """
        try:
            soup = BeautifulSoup(html, 'lxml')
            
            # Remove script, style, nav, footer, header
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe']):
                tag.decompose()
            
            # Get body content
            body = soup.find('body')
            if not body:
                return None
            
            # Extract text
            text = body.get_text(separator=' ', strip=True)
            text_lower = text.lower()
            
            # Count outbound links
            links = body.find_all('a', href=True)
            outbound_count = len(links)
            
            # Count affiliate links
            affiliate_count = 0
            for link in links:
                href = link.get('href', '').lower()
                if any(param in href for param in self.AFFILIATE_PARAMS):
                    affiliate_count += 1
            
            # Detect listicle pattern
            is_listicle = self._detect_listicle(text_lower)
            
            # Hard reject on too many outbound links
            if outbound_count > Limits.HARD_REJECT_OUTBOUND_LINKS:
                print(f"[Extractor] Hard reject: {outbound_count} outbound links")
                return None
            
            # Get title
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else ""
            
            # Get meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            description = meta_desc.get('content', '') if meta_desc else ''
            
            return {
                'title': title_text,
                'description': description,
                'text': text[:5000],  # Limit text size
                'text_lower': text_lower,
                'outbound_link_count': outbound_count,
                'affiliate_link_count': affiliate_count,
                'is_listicle': is_listicle,
                'word_count': len(text.split())
            }
            
        except Exception as e:
            print(f"[Extractor] Error: {e}")
            return None
    
    def _detect_listicle(self, text: str) -> bool:
        """Detect if content is a listicle."""
        import re
        for pattern in self.LISTICLE_PATTERNS:
            if re.search(pattern, text):
                return True
        return False


# Singletons
fetcher = ContentFetcher()
extractor = ContentExtractor()
