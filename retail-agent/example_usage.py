#!/usr/bin/env python3
"""
Example: How to use the Price Intelligence Engine
Shows all major features with minimal code.
"""
import asyncio
from database import SupabaseStore
from price_intelligence import (
    PriceIntelligenceEngine,
    print_pricing_report
)


async def example_1_analyze_single_product():
    """Example 1: Analyze a single product"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Analyze a Single Product")
    print("="*80 + "\n")

    db = SupabaseStore()
    engine = PriceIntelligenceEngine(db)

    # Analyze an iPhone
    analysis = await engine.analyze_product("iPhone 15")

    if analysis:
        print(f"Product: {analysis.product_name}")
        print(f"  Our Price: ${analysis.our_price:.2f}" if analysis.our_price else "  Our Price: Not listed")
        print(f"  Competitor Prices: {analysis.competitor_count} found")
        print(f"    └─ Range: ${analysis.lowest_price:.2f} - ${analysis.highest_price:.2f}")
        print(f"    └─ Average: ${analysis.average_price:.2f}")
        print(f"  Suggested Price: ${analysis.suggested_price:.2f}")
        print(f"  Market Position: {analysis.our_price_position}")
    else:
        print("No competitor prices found for this product yet.")


async def example_2_get_all_analyses():
    """Example 2: Analyze all products with competitor data"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Analyze All Products")
    print("="*80 + "\n")

    db = SupabaseStore()
    engine = PriceIntelligenceEngine(db)

    analyses = await engine.get_all_product_analyses()

    print(f"Found {len(analyses)} products with competitor prices\n")
    print("Top 5 by our_price (descending):")
    print("-" * 80)

    for i, analysis in enumerate(analyses[:5], 1):
        print(f"\n{i}. {analysis.product_name}")
        print(f"   Our: ${analysis.our_price:.2f}" if analysis.our_price else "   Our: Not set")
        print(f"   Min: ${analysis.lowest_price:.2f} | Avg: ${analysis.average_price:.2f} | Max: ${analysis.highest_price:.2f}")
        print(f"   Competitors: {analysis.competitor_count}")


async def example_3_generate_recommendations():
    """Example 3: Generate pricing recommendations"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Generate Pricing Recommendations")
    print("="*80 + "\n")

    db = SupabaseStore()
    engine = PriceIntelligenceEngine(db, margin_percent=1.0)

    recommendations = await engine.generate_recommendations(min_competitor_count=2)

    if not recommendations:
        print("No recommendations available (need more data or products in our_products table)")
        return

    print(f"Generated {len(recommendations)} recommendations\n")

    # Group by urgency
    critical = [r for r in recommendations if r.urgency == "critical"]
    high = [r for r in recommendations if r.urgency == "high"]
    medium = [r for r in recommendations if r.urgency == "medium"]
    low = [r for r in recommendations if r.urgency == "low"]

    print(f"Critical: {len(critical)} | High: {len(high)} | Medium: {len(medium)} | Low: {len(low)}\n")

    # Show critical items
    if critical:
        print("🔴 CRITICAL - Immediate Action Needed:")
        print("-" * 80)
        for rec in critical[:3]:
            print(f"\n{rec.product_name}")
            print(f"  Current Price: ${rec.our_price:.2f}")
            print(f"  Suggested Price: ${rec.suggested_price:.2f}")
            print(f"  Change: {rec.price_change_percent:.1f}%")
            print(f"  Reason: {rec.reasoning}")


async def example_4_top_competitors():
    """Example 4: Identify top competitors"""
    print("\n" + "="*80)
    print("EXAMPLE 4: Top Competitors by Market Coverage")
    print("="*80 + "\n")

    db = SupabaseStore()
    engine = PriceIntelligenceEngine(db)

    competitors = await engine.get_top_competitors(limit=10)

    if not competitors:
        print("No competitor data available yet")
        return

    print("Top 10 Competitors:")
    print("-" * 80)
    for rank, (domain, count) in enumerate(competitors.items(), 1):
        pct = (count / sum(competitors.values()) * 100)
        print(f"{rank:2d}. {domain:40s} {count:4d} products ({pct:5.1f}%)")


async def example_5_price_trends():
    """Example 5: Analyze price trends"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Price Trends over Time")
    print("="*80 + "\n")

    db = SupabaseStore()
    engine = PriceIntelligenceEngine(db)

    trend = await engine.get_price_trends("iPhone 15", days=30)

    if trend:
        print(f"Product: {trend['product_name']}")
        print(f"Time Period: Last {trend['days']} days")
        print(f"Price changes found: {trend['history_count']}")
        print(f"Trend Direction: {trend['trend_direction'].upper()}")
        print(f"Average Change: {trend['avg_change_percent']:.2f}%")
        print(f"Volatility (std dev): {trend['volatility']:.2f}%")
    else:
        print("No trend history available for this product yet")


async def example_6_create_alerts():
    """Example 6: Automatically create price alerts"""
    print("\n" + "="*80)
    print("EXAMPLE 6: Create Price Alerts")
    print("="*80 + "\n")

    db = SupabaseStore()
    engine = PriceIntelligenceEngine(db)

    # Create alerts for products >5% above lowest competitor
    alerts_created = await engine.create_price_alerts(threshold_percent=5.0)

    print(f"Created {alerts_created} new price alerts")
    print("\nAlerts are stored in the 'price_alerts' table")
    print("They can be reviewed in the dashboard or exported for management review")


async def example_7_full_report():
    """Example 7: Generate full pricing intelligence report"""
    print("\n" + "="*80)
    print("EXAMPLE 7: Full Pricing Intelligence Report")
    print("="*80)

    db = SupabaseStore()
    await print_pricing_report(db)


async def main():
    """Run all examples"""
    print("\n" + "="*80)
    print("PRICE INTELLIGENCE MODULE - USAGE EXAMPLES")
    print("="*80)

    examples = [
        ("Analyze Single Product", example_1_analyze_single_product),
        ("Analyze All Products", example_2_get_all_analyses),
        ("Generate Recommendations", example_3_generate_recommendations),
        ("Top Competitors", example_4_top_competitors),
        ("Price Trends", example_5_price_trends),
        ("Create Alerts", example_6_create_alerts),
        ("Full Report", example_7_full_report),
    ]

    print("\nAvailable examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    print(f"  {len(examples) + 1}. Run all examples")

    choice = input("\nSelect example (1-8, or Enter for all): ").strip()

    if not choice or choice == str(len(examples) + 1):
        # Run all
        for name, func in examples:
            await func()
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(examples):
                await examples[idx][1]()
            else:
                print("Invalid choice")
        except ValueError:
            print("Invalid input")

    print("\n" + "="*80)
    print("Examples complete! For more info, see PRICING_INTELLIGENCE.md")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
