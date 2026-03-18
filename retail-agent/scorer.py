"""
Multi-Factor Scoring Engine
Determines if page is a legitimate pricing page.
Deterministic - no LLM required.
Time complexity: O(text length)
"""
import re
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass

from config import (
    CORE_VOCABULARY, SPAM_KEYWORDS, SYNONYM_GRAPH,
    ScoringWeights, Thresholds, Limits
)


@dataclass
class ScoreResult:
    """Result of scoring."""
    score: int
    spam_score: int
    is_offer: bool
    is_hard_rejected: bool
    matches: Dict[str, List[str]]
    domain_bonus: int


@dataclass
class ExtractedPrice:
    """A price extracted from page content."""
    amount: float
    currency: str
    raw_text: str


class MultiFactorScorer:
    """
    Scores pages for competitor pricing page likelihood.
    + Entity match (retail terms)
    + Benefit match (price signals)
    + Program phrase match (price comparison patterns)
    + Trusted domain bonus
    - Spam keywords
    - Excess outbound links
    - Listicle pattern
    """
    
    # Price extraction regex patterns
    PRICE_PATTERNS = [
        # $99.99, $1,299.99
        re.compile(r'\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', re.IGNORECASE),
        # €99.99, €1.299,99
        re.compile(r'€\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', re.IGNORECASE),
        # £99.99
        re.compile(r'£\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', re.IGNORECASE),
        # ₹79,990  ₹1,29,990  ₹999  (Indian comma grouping: lakhs/crores)
        re.compile(r'₹\s?(\d{1,2}(?:,\d{2})*,\d{3}(?:\.\d{2})?|\d{1,6}(?:\.\d{2})?)', re.IGNORECASE),
        # Rs. 79990, Rs 1,29,990, INR 79990
        re.compile(r'(?:Rs\.?|INR)\s?(\d{1,2}(?:,\d{2})*,\d{3}(?:\.\d{2})?|\d{1,6}(?:\.\d{2})?)', re.IGNORECASE),
        # USD 99.99, EUR 99.99
        re.compile(r'(USD|EUR|GBP|INR)\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', re.IGNORECASE),
        # 99.99 USD
        re.compile(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s?(USD|EUR|GBP|INR)', re.IGNORECASE),
    ]
    
    CURRENCY_SYMBOLS = {'$': 'USD', '€': 'EUR', '£': 'GBP', '₹': 'INR'}
    
    def __init__(self):
        # Pre-compile patterns for O(1) lookup
        self._entity_patterns = self._compile_patterns(CORE_VOCABULARY["entities"])
        self._benefit_patterns = self._compile_patterns(CORE_VOCABULARY["benefits"])
        self._program_patterns = self._compile_program_patterns(
            CORE_VOCABULARY["program_phrases"]
        )
        self._spam_patterns = self._compile_patterns(SPAM_KEYWORDS)
        
        # Build synonym expansion
        self._synonym_map = self._build_synonym_map()
    
    def _compile_patterns(self, terms: List[str]) -> Dict[str, re.Pattern]:
        """Compile term patterns for fast matching."""
        return {
            term: re.compile(rf'\b{re.escape(term)}\b', re.IGNORECASE)
            for term in terms
        }
    
    def _compile_program_patterns(self, phrases: List[str]) -> List[re.Pattern]:
        """Compile multi-word phrase patterns."""
        return [
            re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE)
            for phrase in phrases
        ]
    
    def _build_synonym_map(self) -> Dict[str, Set[str]]:
        """Build expansion map from synonym graph."""
        expansion = {}
        for term, synonyms in SYNONYM_GRAPH.items():
            # Depth 1 only
            expansion[term] = set(synonyms) | {term}
        return expansion
    
    def _expand_term(self, term: str) -> Set[str]:
        """Expand term with synonyms (depth 1)."""
        return self._synonym_map.get(term.lower(), {term.lower()})
    
    def extract_prices(self, content: str) -> List[ExtractedPrice]:
        """
        Extract price values from page content.
        Returns list of ExtractedPrice objects with amount, currency, raw text.
        """
        prices = []
        
        for pattern in self.PRICE_PATTERNS:
            for match in pattern.finditer(content):
                raw = match.group(0)
                try:
                    # Determine currency
                    currency = 'INR'  # default to INR for Indian retail
                    for sym, cur in self.CURRENCY_SYMBOLS.items():
                        if sym in raw:
                            currency = cur
                            break
                    # Check for explicit currency codes
                    for code in ['USD', 'EUR', 'GBP', 'INR']:
                        if code in raw.upper():
                            currency = code
                            break
                    # Check for Rs. / Rs prefix
                    if 'Rs' in raw or 'rs' in raw:
                        currency = 'INR'
                    
                    # Extract numeric value
                    nums = re.findall(r'[\d,]+\.?\d*', raw)
                    if nums:
                        amount_str = nums[0].replace(',', '')
                        amount = float(amount_str)
                        if 0.01 <= amount <= 10_000_000:  # Up to 1 crore INR
                            prices.append(ExtractedPrice(
                                amount=amount,
                                currency=currency,
                                raw_text=raw.strip()
                            ))
                except (ValueError, IndexError):
                    continue
        
        # Deduplicate by amount+currency
        seen = set()
        unique = []
        for p in prices:
            key = (p.amount, p.currency)
            if key not in seen:
                seen.add(key)
                unique.append(p)
        
        return unique
    
    def score_content(self, content: Dict, domain_trust: float = 0) -> ScoreResult:
        """
        Score extracted content.
        Returns ScoreResult with decision.
        """
        text = content.get('text_lower', '')
        title = content.get('title', '').lower()
        
        matches = {
            'entities': [],
            'benefits': [],
            'program_phrases': [],
            'spam_keywords': []
        }
        
        score = 0
        spam_score = 0
        
        # 1. Entity matches (retail terms)
        for term, pattern in self._entity_patterns.items():
            if pattern.search(text) or pattern.search(title):
                matches['entities'].append(term)
                score += ScoringWeights.ENTITY_MATCH
        
        # 2. Benefit matches (price signals)
        for term, pattern in self._benefit_patterns.items():
            if pattern.search(text) or pattern.search(title):
                matches['benefits'].append(term)
                score += ScoringWeights.BENEFIT_MATCH
        
        # 3. Program phrase matches (higher weight - exact phrases)
        found_phrases = set()
        for pattern in self._program_patterns:
            if pattern.search(text):
                found_phrases.add(pattern.pattern)
            elif pattern.search(title):
                found_phrases.add(pattern.pattern)
        
        matches['program_phrases'] = list(found_phrases)
        score += len(found_phrases) * ScoringWeights.PROGRAM_PHRASE_MATCH
        
        # 4. Synonym expansion bonus (only if core term not matched)
        for term, expanded in self._synonym_map.items():
            if term not in matches['entities'] and term not in matches['benefits']:
                for syn in expanded:
                    if re.search(rf'\b{re.escape(syn)}\b', text, re.IGNORECASE):
                        if term in CORE_VOCABULARY["entities"]:
                            score += ScoringWeights.ENTITY_MATCH // 2
                            break
                        elif term in CORE_VOCABULARY["benefits"]:
                            score += ScoringWeights.BENEFIT_MATCH // 2
                            break
        
        # 5. Spam keyword penalty
        for term, pattern in self._spam_patterns.items():
            if pattern.search(text) or pattern.search(title):
                matches['spam_keywords'].append(term)
                spam_score += abs(ScoringWeights.SPAM_KEYWORD_PENALTY)
        
        # 6. Excess outbound links penalty
        outbound_count = content.get('outbound_link_count', 0)
        if outbound_count > Limits.MAX_OUTBOUND_LINKS:
            excess = outbound_count - Limits.MAX_OUTBOUND_LINKS
            score += excess * ScoringWeights.EXCESS_OUTBOUND_LINKS_PENALTY
        
        # 7. Listicle pattern penalty
        if content.get('is_listicle', False):
            score += ScoringWeights.LISTICLE_PATTERN_PENALTY
        
        # 8. Affiliate link penalty
        affiliate_count = content.get('affiliate_link_count', 0)
        if affiliate_count > 5:
            score += affiliate_count * ScoringWeights.SPAM_KEYWORD_PENALTY
        
        # 9. Trusted domain bonus
        domain_bonus = 0
        if domain_trust > 5:
            domain_bonus = ScoringWeights.TRUSTED_DOMAIN_BONUS
            score += domain_bonus
        
        # Decision logic
        is_hard_rejected = spam_score >= Thresholds.HARD_REJECT_SPAM_SCORE
        is_offer = not is_hard_rejected and score >= Thresholds.MIN_SCORE_FOR_OFFER
        
        return ScoreResult(
            score=score,
            spam_score=spam_score,
            is_offer=is_offer,
            is_hard_rejected=is_hard_rejected,
            matches=matches,
            domain_bonus=domain_bonus
        )
    
    def extract_noun_phrases(self, text: str, min_length: int = 3) -> List[Tuple[str, int]]:
        """
        Extract simple noun phrases for co-occurrence learning.
        Returns list of (phrase, word_count).
        """
        # Clean text
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        
        # Common noun patterns (simplified)
        stops = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to'}
        
        phrases = []
        current = []
        
        for word in words:
            if len(word) < min_length or word in stops:
                if len(current) >= 2:
                    phrase = ' '.join(current)
                    phrases.append((phrase, len(current)))
                current = []
            else:
                current.append(word)
        
        # Catch trailing phrase
        if len(current) >= 2:
            phrase = ' '.join(current)
            phrases.append((phrase, len(current)))
        
        return phrases
    
    def get_benefits_found(self, content: Dict) -> List[str]:
        """Extract list of matched price signal types."""
        text = content.get('text_lower', '')
        title = content.get('title', '').lower()
        
        benefits = []
        for term in CORE_VOCABULARY["benefits"]:
            if term in text or term in title:
                benefits.append(term)
        
        return list(set(benefits))


# Singleton
scorer = MultiFactorScorer()
