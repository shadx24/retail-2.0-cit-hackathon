"""
URL Canonicalization Layer
Normalizes URLs to prevent duplicate variants.
Time complexity: O(L) where L = URL length
"""
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import re
import hashlib
from typing import Optional


class URLCanonicalizer:
    """
    Converts URLs into canonical form with SHA256 hashing.
    """
    
    # Tracking parameters to remove
    TRACKING_PARAMS = {
        'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
        'utm_id', 'utm_source_platform', 'utm_creative_format', 'utm_marketing_tactic',
        'fbclid', 'gclid', 'ttclid', 'wbraid', 'gbraid', 'cid',
        'mc_cid', 'mc_eid', 'ref', 'referrer', 'source',
    }
    
    def __init__(self):
        self._seen_hashes = set()
    
    def canonicalize(self, url: str) -> tuple[str, str]:
        """
        Convert URL to canonical form and compute hash.
        
        Returns:
            tuple: (canonical_url, sha256_hash)
        """
        if not url:
            return ("", "")
        
        url = url.strip()
        
        # Parse URL
        parsed = urlparse(url)
        
        # Lowercase scheme and netloc
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        
        # Force HTTPS
        if scheme == 'http':
            scheme = 'https'
        
        # Normalize www
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        
        # Lowercase path
        path = parsed.path.lower()
        
        # Remove trailing slash (except for root)
        if path != '/' and path.endswith('/'):
            path = path[:-1]
        
        # Remove fragment
        fragment = ''
        
        # Clean query parameters
        query = self._clean_query(parsed.query)
        
        # Reconstruct canonical URL
        canonical = urlunparse((
            scheme,
            netloc,
            path,
            parsed.params,
            query,
            fragment
        ))
        
        # Compute SHA256 hash
        url_hash = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        
        return (canonical, url_hash)
    
    def _clean_query(self, query: str) -> str:
        """Remove tracking parameters and sort remaining."""
        if not query:
            return ''
        
        # Parse query string
        params = parse_qs(query, keep_blank_values=False)
        
        # Remove tracking parameters
        clean_params = {
            k: v for k, v in params.items()
            if k.lower() not in self.TRACKING_PARAMS
        }
        
        # Sort by key and encode
        if clean_params:
            sorted_items = sorted(clean_params.items())
            return urlencode(sorted_items, doseq=True)
        
        return ''
    
    def is_duplicate(self, url_hash: str) -> bool:
        """Check if URL hash already seen."""
        return url_hash in self._seen_hashes
    
    def mark_seen(self, url_hash: str):
        """Mark URL hash as processed."""
        self._seen_hashes.add(url_hash)
    
    def extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    
    def is_valid_url(self, url: str) -> bool:
        """Basic URL validation."""
        parsed = urlparse(url)
        return (
            parsed.scheme in ('http', 'https') and
            parsed.netloc and
            '.' in parsed.netloc
        )


# Singleton instance
canonicalizer = URLCanonicalizer()
