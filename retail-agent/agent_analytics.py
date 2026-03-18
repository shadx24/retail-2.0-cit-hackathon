"""
Agent-side Analytics Engine
Implements 5 core analytics features:
1. Emerging Product Radar
2. Price Volatility Score
3. Competitor Coverage Map
4. Price Drop Detector
5. Automatic Product Discovery
"""
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import statistics

from database import SupabaseStore


@dataclass
class EmergingProduct:
    """A newly discovered product appearing on multiple retailers."""
    product_name: str
    first_seen: datetime
    retailer_count: int
    retailers: List[str]
    category: str
    hours_old: int
    is_truly_emerging: bool  # <24h and ≥2 retailers


@dataclass
class PriceVolatility:
    """Price volatility metrics for a product."""
    product_name: str
    avg_price: float
    min_price: float
    max_price: float
    volatility_score: float  # std dev
    variance: float
    price_range: float
    sample_count: int
    volatility_level: str  # "Low", "Medium", "High", "Extreme"


@dataclass
class CompetitorMarketShare:
    """Competitor coverage and market dominance by category."""
    competitor_domain: str
    category: str
    product_count: int
    market_share_percent: float
    is_dominant: bool


@dataclass
class PriceDrop:
    """Detected sudden price reduction."""
    product_name: str
    competitor_domain: str
    old_price: float
    new_price: float
    price_drop: float
    drop_percent: float
    detected_at: datetime


@dataclass
class DiscoveredProduct:
    """Automatically discovered trending product."""
    product_name: str
    first_seen: datetime
    retailer_count: int
    retailer_list: List[str]
    category: str
    confidence_score: float  # Based on consistency across retailers


class AnalyticsEngine:
    """
    Core analytics engine for 5 agent-side features.
    Works with multi-tenant data (shop_id).
    """

    def __init__(self, db: SupabaseStore):
        self.db = db
        self.volatility_threshold = {
            "Low": (0, 10),
            "Medium": (10, 25),
            "High": (25, 50),
            "Extreme": (50, float('inf'))
        }

    # ─────────────────────────────────────────────────────────────────
    # FEATURE 1: Emerging Product Radar
    # ─────────────────────────────────────────────────────────────────

    async def detect_emerging_products(self, shop_id: int, hours: int = 24) -> List[EmergingProduct]:
        """
        Detect new products entering the market.
        
        Criteria:
        - Product first seen < X hours ago
        - Appears on ≥2 retailers
        
        Returns:
            List of emerging products, sorted by retailer count desc
        """
        # Get products first seen recently
        products = self.db.client.table("product_metadata")\
            .select("*")\
            .eq("shop_id", shop_id)\
            .gte("first_seen", (datetime.utcnow() - timedelta(hours=hours)).isoformat())\
            .execute()

        emerging = []

        for product in products.data:
            product_name = product["product_name"]
            first_seen_str = product["first_seen"]
            try:
                first_seen = datetime.fromisoformat(first_seen_str.replace("Z", "+00:00"))
                first_seen = first_seen.replace(tzinfo=None)  # Make naive for comparison
            except Exception:
                first_seen = datetime.utcnow()
            hours_old = int((datetime.utcnow() - first_seen).total_seconds() / 3600)

            # Count retailers carrying this product
            retailers = self.db.client.table("competitor_prices")\
                .select("domain")\
                .eq("shop_id", shop_id)\
                .eq("product_name", product_name)\
                .execute()

            retailer_list = list(set([r["domain"] for r in retailers.data if r["domain"]]))
            retailer_count = len(retailer_list)

            # Check if truly emerging (≥2 retailers)
            is_emerging = retailer_count >= 2

            if is_emerging:
                ep = EmergingProduct(
                    product_name=product_name,
                    first_seen=first_seen,
                    retailer_count=retailer_count,
                    retailers=retailer_list,
                    category=product.get("category", "unknown"),
                    hours_old=hours_old,
                    is_truly_emerging=True
                )
                emerging.append(ep)

        # Sort by retailer count descending
        emerging.sort(key=lambda x: x.retailer_count, reverse=True)
        return emerging

    async def log_emerging_product_alert(self, shop_id: int, product: EmergingProduct) -> bool:
        """Create alert record for emerging product."""
        self.db.client.table("emerging_products").insert({
            "shop_id": shop_id,
            "product_name": product.product_name,
            "first_seen": product.first_seen.isoformat(),
            "retailer_count": product.retailer_count,
            "retailer_list": ",".join(product.retailers),
            "category": product.category,
            "alert_sent": False
        }).execute()
        return True

    # ─────────────────────────────────────────────────────────────────
    # FEATURE 2: Price Volatility Score
    # ─────────────────────────────────────────────────────────────────

    async def calculate_price_volatility(self, shop_id: int, product_name: str) -> Optional[PriceVolatility]:
        """
        Measure how unstable a product's price is across retailers.
        
        Formula: volatility_score = std_dev(all_prices)
        
        Returns:
            PriceVolatility with scores and classification
        """
        # Get all prices for this product
        prices_data = self.db.client.table("competitor_prices")\
            .select("price")\
            .eq("shop_id", shop_id)\
            .ilike("product_name", f"%{product_name}%")\
            .not_.is_("price", "null")\
            .execute()

        if not prices_data.data or len(prices_data.data) < 2:
            return None

        prices = [float(p["price"]) for p in prices_data.data]
        sample_count = len(prices)

        # Calculate metrics
        avg_price = statistics.mean(prices)
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price

        # Calculate volatility (std dev)
        if sample_count > 1:
            volatility_score = statistics.stdev(prices)
        else:
            volatility_score = 0.0

        # Calculate variance
        if sample_count > 1:
            variance = statistics.variance(prices)
        else:
            variance = 0.0

        # Classify volatility level
        volatility_level = "Low"
        for level, (min_v, max_v) in self.volatility_threshold.items():
            if min_v <= volatility_score < max_v:
                volatility_level = level
                break

        vol = PriceVolatility(
            product_name=product_name,
            avg_price=avg_price,
            min_price=min_price,
            max_price=max_price,
            volatility_score=volatility_score,
            variance=variance,
            price_range=price_range,
            sample_count=sample_count,
            volatility_level=volatility_level
        )

        return vol

    async def get_all_volatilities(self, shop_id: int, min_sample_count: int = 3) -> List[PriceVolatility]:
        """
        Calculate volatility for all products with sufficient price samples.
        
        Args:
            shop_id: Shop ID
            min_sample_count: Minimum prices needed for analysis
            
        Returns:
            List sorted by volatility_score descending (most volatile first)
        """
        # Get unique product names
        products = self.db.client.table("competitor_prices")\
            .select("product_name")\
            .eq("shop_id", shop_id)\
            .neq("product_name", None)\
            .execute()

        product_names = list(set([p["product_name"] for p in products.data if p["product_name"]]))

        volatilities = []
        for name in product_names[:100]:  # Limit for performance
            vol = await self.calculate_price_volatility(shop_id, name)
            if vol and vol.sample_count >= min_sample_count:
                volatilities.append(vol)

        # Sort by volatility score descending
        volatilities.sort(key=lambda v: v.volatility_score, reverse=True)
        return volatilities

    # ─────────────────────────────────────────────────────────────────
    # FEATURE 3: Competitor Coverage Map
    # ─────────────────────────────────────────────────────────────────

    async def get_competitor_coverage_by_category(self, shop_id: int, category: str) -> List[CompetitorMarketShare]:
        """
        Show which competitors dominate which product categories.
        
        Returns:
            Competitors sorted by market_share_percent descending
        """
        # Count products per competitor in category
        coverage = self.db.client.table("competitor_prices")\
            .select("domain")\
            .eq("shop_id", shop_id)\
            .eq("category", category)\
            .execute()

        if not coverage.data:
            return []

        # Count by domain
        domain_counts = {}
        for row in coverage.data:
            domain = row["domain"]
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        total_products = sum(domain_counts.values())

        # Calculate market share
        competitors = []
        for domain, count in domain_counts.items():
            market_share = (count / total_products * 100) if total_products > 0 else 0
            is_dominant = market_share > 25  # >25% considered dominant

            cms = CompetitorMarketShare(
                competitor_domain=domain,
                category=category,
                product_count=count,
                market_share_percent=market_share,
                is_dominant=is_dominant
            )
            competitors.append(cms)

        # Sort by market share descending
        competitors.sort(key=lambda c: c.market_share_percent, reverse=True)
        return competitors

    async def get_coverage_map_all_categories(self, shop_id: int) -> Dict[str, List[CompetitorMarketShare]]:
        """
        Get competitor coverage map for all categories.
        
        Returns:
            Dict mapping category → list of competitors by market share
        """
        # Get all categories
        categories = self.db.client.table("competitor_prices")\
            .select("category")\
            .eq("shop_id", shop_id)\
            .neq("category", None)\
            .execute()

        unique_categories = list(set([c["category"] for c in categories.data if c["category"]]))

        coverage_map = {}
        for category in unique_categories:
            coverage_map[category] = await self.get_competitor_coverage_by_category(shop_id, category)

        return coverage_map

    async def update_coverage_table(self, shop_id: int) -> int:
        """Update the competitor_coverage table."""
        await self.get_coverage_map_all_categories(shop_id)
        # Trigger the SQL function to populate the table
        self.db.client.rpc("calculate_competitor_coverage", {"p_shop_id": shop_id}).execute()
        return 1

    # ─────────────────────────────────────────────────────────────────
    # FEATURE 4: Price Drop Detector
    # ─────────────────────────────────────────────────────────────────

    async def detect_price_drops(self, shop_id: int, threshold_percent: float = 5.0) -> List[PriceDrop]:
        """
        Detect sudden price reductions across competitors.
        
        Logic:
        - Compare recent price to previous price
        - Flag if drop >= threshold_percent
        
        Args:
            shop_id: Shop ID
            threshold_percent: Minimum drop % to flag (e.g., 5.0 = 5%)
            
        Returns:
            List of detected price drops, sorted by drop_percent descending
        """
        # Get recent price history (last 30 days)
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()

        history = self.db.client.table("price_history")\
            .select("*")\
            .eq("shop_id", shop_id)\
            .gte("recorded_at", cutoff)\
            .execute()

        drops = []

        for record in history.data:
            if record["old_price"] and record["new_price"]:
                old = float(record["old_price"])
                new = float(record["new_price"])

                if new < old:
                    drop = old - new
                    drop_percent = (drop / old) * 100

                    if drop_percent >= threshold_percent:
                        try:
                            detected = datetime.fromisoformat(
                                record["recorded_at"].replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except Exception:
                            detected = datetime.utcnow()
                        pd = PriceDrop(
                            product_name=record.get("product_name", "unknown"),
                            competitor_domain=record.get("domain", "unknown"),
                            old_price=old,
                            new_price=new,
                            price_drop=drop,
                            drop_percent=drop_percent,
                            detected_at=detected
                        )
                        drops.append(pd)

        # Sort by drop_percent descending
        drops.sort(key=lambda d: d.drop_percent, reverse=True)
        return drops

    async def log_price_drop_alert(self, shop_id: int, drop: PriceDrop) -> bool:
        """Create alert record for price drop."""
        self.db.client.table("price_drops").insert({
            "shop_id": shop_id,
            "product_name": drop.product_name,
            "competitor_domain": drop.competitor_domain,
            "old_price": drop.old_price,
            "new_price": drop.new_price,
            "price_drop": drop.price_drop,
            "drop_percent": drop.drop_percent,
            "detected_at": drop.detected_at.isoformat(),
            "alert_sent": False
        }).execute()
        return True

    # ─────────────────────────────────────────────────────────────────
    # FEATURE 5: Automatic Product Discovery
    # ─────────────────────────────────────────────────────────────────

    async def auto_discover_products(self, shop_id: int) -> List[DiscoveredProduct]:
        """
        Automatically discover trending products.
        
        Logic:
        - Product appearing on ≥2 retailers
        - High confidence if consistent pricing
        - Higher score if on 3+ retailers
        
        Returns:
            List of discovered products by confidence score
        """
        # Get all products with multiple retailers
        products = self.db.client.table("competitor_prices")\
            .select("product_name")\
            .eq("shop_id", shop_id)\
            .neq("product_name", None)\
            .execute()

        product_names = [p["product_name"] for p in products.data]

        discovered = []
        seen = set()

        for name in product_names:
            if name in seen:
                continue
            seen.add(name)

            # Get retailers for this product
            retailers = self.db.client.table("competitor_prices")\
                .select("domain, price, category, scraped_at")\
                .eq("shop_id", shop_id)\
                .eq("product_name", name)\
                .execute()

            retailer_list = [r["domain"] for r in retailers.data if r["domain"]]
            retailer_count = len(set(retailer_list))

            # Only include if on ≥2 retailers
            if retailer_count < 2:
                continue

            # Get first seen time
            try:
                first_seen = min([
                    datetime.fromisoformat(
                        r["scraped_at"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    for r in retailers.data if r["scraped_at"]
                ])
            except Exception:
                first_seen = datetime.utcnow()

            # Calculate confidence score
            # Higher score = more retailers = more confident trending product
            confidence_score = min(100, retailer_count * 20)

            # Get category
            category = next((r["category"] for r in retailers.data if r["category"]), "unknown")

            dp = DiscoveredProduct(
                product_name=name,
                first_seen=first_seen,
                retailer_count=retailer_count,
                retailer_list=list(set(retailer_list)),
                category=category,
                confidence_score=confidence_score
            )
            discovered.append(dp)

        # Sort by confidence score descending
        discovered.sort(key=lambda d: d.confidence_score, reverse=True)
        return discovered[:100]  # Top 100

    async def log_discovered_product(self, shop_id: int, product: DiscoveredProduct) -> bool:
        """Log discovered product to product_metadata."""
        self.db.client.table("product_metadata").insert({
            "shop_id": shop_id,
            "product_name": product.product_name,
            "category": product.category,
            "first_seen": product.first_seen.isoformat(),
            "is_emerging": True,
            "trending_score": product.confidence_score
        }).upsert(on_conflict="shop_id,product_name").execute()
        return True

    # ─────────────────────────────────────────────────────────────────
    # Batch Analytics (Run all 5 features for a shop)
    # ─────────────────────────────────────────────────────────────────

    async def run_full_analytics_cycle(self, shop_id: int) -> Dict:
        """
        Run a full analytics cycle on all 5 features.
        
        Returns:
            Dict with results from each feature
        """
        cycle_start = datetime.utcnow()

        # 1. Detect emerging products
        emerging = await self.detect_emerging_products(shop_id)
        for product in emerging:
            await self.log_emerging_product_alert(shop_id, product)

        # 2. Calculate price volatilities (top 20)
        volatilities = await self.get_all_volatilities(shop_id)
        high_volatility = [v for v in volatilities if v.volatility_level in ["High", "Extreme"]][:20]

        # 3. Get competitor coverage map
        coverage_map = await self.get_coverage_map_all_categories(shop_id)

        # 4. Detect price drops
        price_drops = await self.detect_price_drops(shop_id, threshold_percent=5.0)
        for drop in price_drops:
            await self.log_price_drop_alert(shop_id, drop)

        # 5. Auto-discover products
        discovered = await self.auto_discover_products(shop_id)

        cycle_end = datetime.utcnow()
        duration = (cycle_end - cycle_start).total_seconds()

        # Log cycle
        self.db.client.table("product_discovery_log").insert({
            "shop_id": shop_id,
            "products_found": len(discovered),
            "new_products": len([e for e in emerging if e.hours_old < 3]),
            "emerging_products": len(emerging),
            "price_drops_detected": len(price_drops),
            "process_time_seconds": int(duration),
            "completed_at": cycle_end.isoformat()
        }).execute()

        return {
            "emerging_products": emerging,
            "volatilities": high_volatility,
            "competitor_coverage": coverage_map,
            "price_drops": price_drops,
            "discovered_products": discovered[:20],
            "cycle_time_seconds": duration
        }

    # ─────────────────────────────────────────────────────────────────
    # Reporting functions
    # ─────────────────────────────────────────────────────────────────

    def format_analytics_report(self, results: Dict, shop_id: int = None) -> str:
        """Format analytics cycle results as human-readable report."""
        report = f"""
{'='*80}
                    PRODUCT ANALYTICS REPORT
{'='*80}

📊 CYCLE SUMMARY
{'─'*80}
Processing time: {results['cycle_time_seconds']:.1f}s

🚀 EMERGING PRODUCTS ({len(results['emerging_products'])})
{self._format_emerging(results['emerging_products'])}

📈 PRICE VOLATILITY - HIGH RISK ({len(results['volatilities'])} products)
{self._format_volatility(results['volatilities'])}

🏪 COMPETITOR COVERAGE BY CATEGORY
{self._format_coverage(results['competitor_coverage'])}

⬇️ PRICE DROPS DETECTED ({len(results['price_drops'])})
{self._format_price_drops(results['price_drops'])}

🔍 AUTO-DISCOVERED PRODUCTS ({len(results['discovered_products'])} top items)
{self._format_discovered(results['discovered_products'])}

{'='*80}
"""
        return report

    def _format_emerging(self, products: List[EmergingProduct]) -> str:
        if not products:
            return "  No emerging products detected.\n"
        text = ""
        for i, p in enumerate(products[:10], 1):
            text += f"  {i}. {p.product_name} ({p.hours_old}h old, {p.retailer_count} retailers)\n"
            text += f"     └─ {', '.join(p.retailers[:3])}\n"
        return text

    def _format_volatility(self, products: List[PriceVolatility]) -> str:
        if not products:
            return "  No volatile products detected.\n"
        text = ""
        for i, p in enumerate(products[:10], 1):
            text += f"  {i}. {p.product_name} (Volatility: {p.volatility_score:.2f})\n"
            text += f"     └─ Range: ₹{p.min_price:.2f} - ₹{p.max_price:.2f} ({p.sample_count} prices)\n"
        return text

    def _format_coverage(self, coverage_map: Dict) -> str:
        text = ""
        for category, competitors in list(coverage_map.items())[:5]:
            text += f"  {category}:\n"
            for comp in competitors[:3]:
                text += f"    • {comp.competitor_domain}: {comp.product_count} products ({comp.market_share_percent:.1f}%)\n"
        return text

    def _format_price_drops(self, drops: List[PriceDrop]) -> str:
        if not drops:
            return "  No price drops detected.\n"
        text = ""
        for i, d in enumerate(drops[:10], 1):
            text += f"  {i}. {d.product_name} @ {d.competitor_domain}\n"
            text += f"     └─ ₹{d.old_price:.2f} → ₹{d.new_price:.2f} ({d.drop_percent:.1f}% drop)\n"
        return text

    def _format_discovered(self, products: List[DiscoveredProduct]) -> str:
        if not products:
            return "  No new products discovered.\n"
        text = ""
        for i, p in enumerate(products[:10], 1):
            text += f"  {i}. {p.product_name} (Confidence: {p.confidence_score:.0f}%)\n"
            text += f"     └─ {p.retailer_count} retailers: {', '.join(p.retailer_list[:2])}\n"
        return text


if __name__ == "__main__":
    import asyncio
    from database import SupabaseStore

    async def test():
        db = SupabaseStore()
        engine = AnalyticsEngine(db)
        
        shop_id = 1  # Replace with actual shop_id
        results = await engine.run_full_analytics_cycle(shop_id)
        print(engine.format_analytics_report(results, shop_id))

    asyncio.run(test())
