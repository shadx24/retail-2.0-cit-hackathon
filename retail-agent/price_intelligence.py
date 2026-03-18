"""
Price Intelligence Module
Analyzes competitor prices and suggests pricing adjustments.

Converts raw price data into competitive pricing intelligence.
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import statistics

from database import SupabaseStore
from config import Thresholds


@dataclass
class CompetitorPricePoint:
    """A single competitor price for a product."""
    domain: str
    competitor_name: str
    price: float
    currency: str
    scraped_at: datetime
    url: str


@dataclass
class ProductPriceAnalysis:
    """Complete price analysis for a single product."""
    product_name: str
    our_price: Optional[float]
    competitor_prices: List[CompetitorPricePoint]
    lowest_price: float
    average_price: float
    highest_price: float
    price_range: float
    our_price_position: str  # "below_average", "at_average", "above_average", "above_highest"
    suggested_price: Optional[float]
    margin_vs_lowest: float
    competitor_count: int
    analysis_time: datetime


@dataclass
class PricingRecommendation:
    """A single pricing recommendation for a product."""
    product_name: str
    our_price: Optional[float]
    lowest_competitor: float
    average_competitor: float
    suggested_price: float
    price_change_percent: float
    reasoning: str
    urgency: str  # "critical", "high", "medium", "low"
    competitor_count: int


class PriceIntelligenceEngine:
    """
    Analyzes competitor prices and generates pricing recommendations.
    """

    def __init__(self, db: SupabaseStore, margin_percent: float = 1.0):
        """
        Initialize the engine.

        Args:
            db: SupabaseStore instance
            margin_percent: Margin below lowest competitor (default: 1% undercut)
        """
        self.db = db
        self.margin_percent = margin_percent

    async def analyze_product(self, product_name: str) -> Optional[ProductPriceAnalysis]:
        """
        Analyze all competitor prices for a single product.

        Returns:
            ProductPriceAnalysis with complete price breakdown, or None if no data.
        """
        # Get competitor prices for this product
        competitor_data = self.db.client.table("competitor_prices")\
            .select("*")\
            .ilike("product_name", f"%{product_name}%")\
            .order("scraped_at", desc=True)\
            .limit(100)\
            .execute()

        if not competitor_data.data:
            return None

        # Get our price (if product exists in our catalog)
        our_product = self.db.client.table("our_products")\
            .select("*")\
            .ilike("product_name", f"%{product_name}%")\
            .limit(1)\
            .execute()

        our_price = None
        if our_product.data:
            our_price = float(our_product.data[0]["our_price"])

        # Parse competitor prices
        competitor_prices = []
        for row in competitor_data.data:
            if row["price"] is not None:
                cp = CompetitorPricePoint(
                    domain=row["domain"],
                    competitor_name=row["competitor_name"] or row["domain"],
                    price=float(row["price"]),
                    currency=row["currency"],
                    scraped_at=datetime.fromisoformat(row["scraped_at"]),
                    url=row["url"]
                )
                competitor_prices.append(cp)

        if not competitor_prices:
            return None

        # Calculate statistics
        prices = [cp.price for cp in competitor_prices]
        lowest_price = min(prices)
        highest_price = max(prices)
        average_price = statistics.mean(prices)
        price_range = highest_price - lowest_price

        # Determine our position
        if our_price is None:
            position = "unknown"
        elif our_price < average_price:
            position = "below_average"
        elif our_price == average_price:
            position = "at_average"
        elif our_price < highest_price:
            position = "above_average"
        else:
            position = "above_highest"

        # Suggested price = lowest - margin
        margin_amount = lowest_price * (self.margin_percent / 100.0)
        suggested_price = lowest_price - margin_amount

        margin_vs_lowest = ((lowest_price - our_price) / our_price * 100) if our_price else 0

        analysis = ProductPriceAnalysis(
            product_name=product_name,
            our_price=our_price,
            competitor_prices=competitor_prices,
            lowest_price=lowest_price,
            average_price=average_price,
            highest_price=highest_price,
            price_range=price_range,
            our_price_position=position,
            suggested_price=suggested_price,
            margin_vs_lowest=margin_vs_lowest,
            competitor_count=len(competitor_prices),
            analysis_time=datetime.utcnow()
        )

        return analysis

    async def get_all_product_analyses(self) -> List[ProductPriceAnalysis]:
        """
        Analyze all products with competitor prices.

        Returns:
            List of ProductPriceAnalysis, sorted by our_price descending.
        """
        # Get unique product names from competitor_prices
        products = self.db.client.table("competitor_prices")\
            .select("product_name")\
            .neq("product_name", None)\
            .order("product_name")\
            .execute()

        product_names = list(set([p["product_name"] for p in products.data if p["product_name"]]))

        # Analyze each product
        analyses = []
        for name in product_names[:50]:  # Limit to 50 products for performance
            analysis = await self.analyze_product(name)
            if analysis:
                analyses.append(analysis)

        # Sort by our_price descending
        analyses.sort(
            key=lambda a: a.our_price if a.our_price else 0,
            reverse=True
        )

        return analyses

    async def generate_recommendations(self, min_competitor_count: int = 2) -> List[PricingRecommendation]:
        """
        Generate pricing recommendations for products with sufficient competitor data.

        Args:
            min_competitor_count: Minimum competitors to generate recommendation

        Returns:
            List of PricingRecommendation sorted by urgency.
        """
        analyses = await self.get_all_product_analyses()
        recommendations = []

        for analysis in analyses:
            # Only recommend if we have sufficient competitor data and our price exists
            if analysis.competitor_count < min_competitor_count or analysis.our_price is None:
                continue

            # Calculate price change percentage
            price_change = ((analysis.our_price - analysis.suggested_price) / analysis.our_price) * 100

            # Determine urgency
            if analysis.our_price > analysis.highest_price:
                urgency = "critical"
                reasoning = f"Our price ${analysis.our_price:.2f} is above all competitors (highest: ${analysis.highest_price:.2f})"
            elif analysis.our_price > analysis.average_price * 1.10:
                urgency = "high"
                reasoning = f"Our price ${analysis.our_price:.2f} is >10% above average (${analysis.average_price:.2f})"
            elif analysis.our_price > analysis.average_price:
                urgency = "medium"
                reasoning = f"Our price ${analysis.our_price:.2f} is above average (${analysis.average_price:.2f})"
            else:
                urgency = "low"
                reasoning = f"Our price is competitive (below average)"

            recommendation = PricingRecommendation(
                product_name=analysis.product_name,
                our_price=analysis.our_price,
                lowest_competitor=analysis.lowest_price,
                average_competitor=analysis.average_price,
                suggested_price=analysis.suggested_price,
                price_change_percent=price_change,
                reasoning=reasoning,
                urgency=urgency,
                competitor_count=analysis.competitor_count
            )

            recommendations.append(recommendation)

        # Sort by urgency level then by price_change_percent
        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        recommendations.sort(
            key=lambda r: (urgency_order[r.urgency], -r.price_change_percent)
        )

        return recommendations

    async def create_price_alerts(self, threshold_percent: float = 5.0) -> int:
        """
        Create price alerts for products where we're significantly overpriced.

        Args:
            threshold_percent: Alert if our price is > X% above lowest competitor

        Returns:
            Number of alerts created.
        """
        recommendations = await self.generate_recommendations()
        alerts_created = 0

        for rec in recommendations:
            # Check if price difference exceeds threshold
            if rec.price_change_percent < threshold_percent:
                continue

            # Find our product in database
            our_product = self.db.client.table("our_products")\
                .select("id")\
                .ilike("product_name", f"%{rec.product_name}%")\
                .limit(1)\
                .execute()

            if not our_product.data:
                continue

            product_id = our_product.data[0]["id"]

            # Create alert
            alert_data = {
                "our_product_id": product_id,
                "alert_type": rec.urgency,
                "our_price": rec.our_price,
                "competitor_price": rec.lowest_competitor,
                "price_difference": rec.our_price - rec.lowest_competitor,
                "percentage_diff": rec.price_change_percent,
                "suggested_action": f"Lower price to {rec.suggested_price:.2f} (currently {rec.our_price:.2f})",
                "is_resolved": False
            }

            self.db.client.table("price_alerts")\
                .insert(alert_data)\
                .execute()

            alerts_created += 1

        return alerts_created

    async def get_top_competitors(self, limit: int = 10) -> Dict[str, int]:
        """
        Get the top competitors by number of products monitored.

        Returns:
            Dict mapping competitor domain to product count.
        """
        result = self.db.client.table("competitor_prices")\
            .select("domain")\
            .neq("domain", None)\
            .execute()

        domain_counts = {}
        for row in result.data:
            domain = row["domain"]
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # Sort by count descending
        sorted_competitors = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_competitors[:limit])

    async def get_price_trends(self, product_name: str, days: int = 30) -> Optional[Dict]:
        """
        Analyze price trends for a product over time.

        Returns:
            Dict with price_history, trend_direction, volatility.
        """
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        history = self.db.client.table("price_history")\
            .select("old_price, new_price, change_percent, recorded_at")\
            .ilike("product_name", f"%{product_name}%")\
            .gte("recorded_at", cutoff_date)\
            .order("recorded_at")\
            .execute()

        if not history.data:
            return None

        changes = [h["change_percent"] for h in history.data if h["change_percent"]]
        trend_direction = "up" if statistics.mean(changes) > 0 else "down"
        volatility = statistics.stdev(changes) if len(changes) > 1 else 0

        return {
            "product_name": product_name,
            "history_count": len(history.data),
            "days": days,
            "avg_change_percent": statistics.mean(changes),
            "trend_direction": trend_direction,
            "volatility": volatility
        }


async def print_pricing_report(db: SupabaseStore):
    """
    Print a human-readable pricing intelligence report.
    """
    engine = PriceIntelligenceEngine(db, margin_percent=1.0)

    print("\n" + "=" * 80)
    print("                    COMPETITIVE PRICING INTELLIGENCE REPORT")
    print("=" * 80)

    # Get recommendations
    recommendations = await engine.generate_recommendations(min_competitor_count=2)

    if not recommendations:
        print("\nNo pricing recommendations available yet.")
        print("The agent needs to discover more competitor prices first.")
        print("=" * 80 + "\n")
        return

    print(f"\nTotal products analyzed: {len(recommendations)}")
    print(f"Products needing price adjustment: {len([r for r in recommendations if r.urgency in ['critical', 'high']])}")
    print()

    # Show critical and high urgency items
    critical_items = [r for r in recommendations if r.urgency == "critical"]
    high_items = [r for r in recommendations if r.urgency == "high"]
    medium_items = [r for r in recommendations if r.urgency == "medium"]

    def print_recommendation(rec: PricingRecommendation, rank: int):
        print(f"\n{rank}. {rec.product_name}")
        print(f"   └─ Status: {rec.urgency.upper()}")
        print(f"   ├─ Our Price: ${rec.our_price:.2f}")
        print(f"   ├─ Lowest Competitor: ${rec.lowest_competitor:.2f}")
        print(f"   ├─ Average Competitor: ${rec.average_competitor:.2f}")
        print(f"   ├─ Suggested Price: ${rec.suggested_price:.2f}")
        print(f"   ├─ Price Reduction: {rec.price_change_percent:.1f}%")
        print(f"   ├─ Competitors: {rec.competitor_count}")
        print(f"   └─ Reason: {rec.reasoning}")

    if critical_items:
        print("\n⚠️  CRITICAL PRICING ISSUES (Immediate action recommended):")
        print("─" * 80)
        for i, rec in enumerate(critical_items[:5], 1):
            print_recommendation(rec, i)

    if high_items:
        print("\n\n🔴 HIGH PRIORITY (Review within 7 days):")
        print("─" * 80)
        for i, rec in enumerate(high_items[:5], 1):
            print_recommendation(rec, i)

    if medium_items:
        print("\n\n🟡 MEDIUM PRIORITY (Monitor):")
        print("─" * 80)
        for i, rec in enumerate(medium_items[:3], 1):
            print_recommendation(rec, i)

    # Top competitors
    print("\n\n" + "=" * 80)
    print("TOP COMPETITORS BY PRODUCTS MONITORED")
    print("=" * 80)
    competitors = await engine.get_top_competitors(limit=10)
    for i, (domain, count) in enumerate(competitors.items(), 1):
        print(f"{i:2d}. {domain:40s} | {count:3d} products")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    import asyncio
    from database import SupabaseStore

    async def main():
        db = SupabaseStore()
        await print_pricing_report(db)

    asyncio.run(main())
