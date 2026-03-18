"""
Streamlit Dashboard for Pricing Intelligence
Real-time visualization of competitor prices and pricing recommendations.
"""
import asyncio
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from database import SupabaseStore
from price_intelligence import PriceIntelligenceEngine


@st.cache_resource
def get_db():
    """Cache database connection."""
    return SupabaseStore()


@st.cache_resource
def get_engine():
    """Cache price intelligence engine."""
    db = get_db()
    return PriceIntelligenceEngine(db, margin_percent=1.0)


async def load_recommendations():
    """Load pricing recommendations asynchronously."""
    engine = get_engine()
    return await engine.generate_recommendations(min_competitor_count=2)


async def load_competitors():
    """Load top competitors."""
    engine = get_engine()
    return await engine.get_top_competitors(limit=15)


async def load_analyses():
    """Load all product analyses."""
    engine = get_engine()
    return await engine.get_all_product_analyses()


def main():
    st.set_page_config(
        page_title="Competitive Pricing Intelligence",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Header
    st.title("💰 Competitive Pricing Intelligence Dashboard")
    st.markdown("""
    Real-time pricing analysis and recommendations for competitor price monitoring.
    """)

    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ Settings")
        min_competitors = st.slider(
            "Minimum competitors for recommendation",
            min_value=1,
            max_value=10,
            value=2
        )
        margin_percent = st.slider(
            "Margin below lowest competitor (%)",
            min_value=0.0,
            max_value=10.0,
            value=1.0,
            step=0.1
        )
        refresh_interval = st.selectbox(
            "Auto-refresh interval",
            ["Never", "Every 1 min", "Every 5 min", "Every 30 min"]
        )

        if st.button("🔄 Refresh Now", use_container_width=True):
            st.rerun()

    # Load data
    try:
        # Run async functions
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        recommendations = loop.run_until_complete(load_recommendations())
        competitors = loop.run_until_complete(load_competitors())
        analyses = loop.run_until_complete(load_analyses())

        loop.close()

        if not recommendations:
            st.warning("⏳ No pricing data available yet. The agent is still discovering competitor prices...")
            st.info("Check back in a few minutes when the agent has collected more data.")
            return

        # Metrics row
        col1, col2, col3, col4 = st.columns(4)

        critical_count = len([r for r in recommendations if r.urgency == "critical"])
        high_count = len([r for r in recommendations if r.urgency == "high"])
        medium_count = len([r for r in recommendations if r.urgency == "medium"])
        low_count = len([r for r in recommendations if r.urgency == "low"])

        with col1:
            st.metric("Total Products", len(recommendations))
        with col2:
            st.metric("🔴 Critical", critical_count)
        with col3:
            st.metric("🟠 High Priority", high_count)
        with col4:
            st.metric("🟡 Medium Priority", medium_count)

        # Tabs for different views
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📌 Top Recommendations",
            "📊 Price Analysis",
            "🏢 Competitor Overview",
            "📈 Price Distribution",
            "🎯 Detailed Reports"
        ])

        # ─────────────────────────────────────────────────────────────
        with tab1:
            st.header("Top Pricing Recommendations")

            # Filter by urgency
            urgency_filter = st.selectbox(
                "Filter by urgency:",
                ["All", "Critical", "High", "Medium", "Low"],
                key="urgency_filter"
            )

            filtered_recs = recommendations
            if urgency_filter != "All":
                filtered_recs = [r for r in recommendations if r.urgency.lower() == urgency_filter.lower()]

            if filtered_recs:
                # Create recommendation dataframe
                data = []
                for rec in filtered_recs[:20]:
                    data.append({
                        "Product": rec.product_name[:50],
                        "Our Price": f"${rec.our_price:.2f}",
                        "Lowest Competitor": f"${rec.lowest_competitor:.2f}",
                        "Average Competitor": f"${rec.average_competitor:.2f}",
                        "Suggested Price": f"${rec.suggested_price:.2f}",
                        "Savings": f"{rec.price_change_percent:.1f}%",
                        "Competitors": rec.competitor_count,
                        "Urgency": rec.urgency.upper()
                    })

                df = pd.DataFrame(data)
                st.dataframe(df, use_container_width=True)

                # Show reasoning for selected product
                selected_idx = st.slider(
                    "View details for recommendation #",
                    0,
                    len(filtered_recs) - 1
                )
                rec = filtered_recs[selected_idx]

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader(f"📦 {rec.product_name}")
                    st.write(f"**Reasoning:** {rec.reasoning}")
                with col2:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=["Our Price", "Lowest Comp", "Avg Comp", "Suggested"],
                        y=[rec.our_price, rec.lowest_competitor, rec.average_competitor, rec.suggested_price],
                        marker_color=["red", "green", "blue", "orange"]
                    ))
                    fig.update_layout(
                        title=f"Price Comparison for {rec.product_name}",
                        yaxis_title="Price ($)",
                        height=300,
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"No {urgency_filter.lower()} priority products found.")

        # ─────────────────────────────────────────────────────────────
        with tab2:
            st.header("Price Analysis by Product")

            if analyses:
                # Select product to analyze
                product_names = [a.product_name for a in analyses]
                selected_product = st.selectbox("Select product:", product_names)

                analysis = next((a for a in analyses if a.product_name == selected_product), None)

                if analysis:
                    col1, col2 = st.columns([1, 2])

                    with col1:
                        st.subheader("📊 Statistics")
                        st.metric("Our Price", f"${analysis.our_price:.2f}" if analysis.our_price else "N/A")
                        st.metric("Lowest", f"${analysis.lowest_price:.2f}")
                        st.metric("Average", f"${analysis.average_price:.2f}")
                        st.metric("Highest", f"${analysis.highest_price:.2f}")
                        st.metric("Range", f"${analysis.price_range:.2f}")
                        st.metric("Competitors", analysis.competitor_count)

                    with col2:
                        # Visualize distribution
                        prices = [cp.price for cp in analysis.competitor_prices]
                        domains = [cp.domain for cp in analysis.competitor_prices]

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            x=domains,
                            y=prices,
                            mode='markers',
                            marker=dict(size=10, color=prices, colorscale='Viridis'),
                            text=domains,
                            hovertemplate="<b>%{text}</b><br>Price: $%{y:.2f}"
                        ))
                        if analysis.our_price:
                            fig.add_hline(
                                y=analysis.our_price,
                                annotation_text="Our Price",
                                annotation_position="right",
                                line_dash="dash",
                                line_color="red"
                            )
                        fig.update_layout(
                            title=f"Competitor Prices for {selected_product}",
                            xaxis_title="Competitor",
                            yaxis_title="Price ($)",
                            height=400,
                            xaxis_tickangle=-45
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    # Show competitor prices table
                    st.subheader("🏪 Competitor Prices")
                    comp_data = []
                    for cp in analysis.competitor_prices:
                        comp_data.append({
                            "Competitor": cp.competitor_name,
                            "Domain": cp.domain,
                            "Price": f"${cp.price:.2f}",
                            "Currency": cp.currency,
                            "Last Scraped": cp.scraped_at.strftime("%Y-%m-%d %H:%M")
                        })
                    st.dataframe(pd.DataFrame(comp_data), use_container_width=True)

        # ─────────────────────────────────────────────────────────────
        with tab3:
            st.header("🏢 Competitor Overview")

            if competitors:
                # Top competitors bar chart
                comp_names = list(competitors.keys())
                comp_counts = list(competitors.values())

                fig = px.bar(
                    x=comp_names,
                    y=comp_counts,
                    title="Competitors by Products Monitored",
                    labels={"x": "Competitor", "y": "Product Count"},
                    color=comp_counts,
                    color_continuous_scale="Blues"
                )
                fig.update_layout(height=500, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

                # Competitor details table
                st.subheader("📋 Competitor Details")
                comp_data = []
                for domain, count in competitors.items():
                    comp_data.append({
                        "Competitor": domain,
                        "Products with Prices": count,
                        "Market Share (%)": f"{(count / sum(comp_counts) * 100):.1f}%"
                    })
                st.dataframe(pd.DataFrame(comp_data), use_container_width=True)

        # ─────────────────────────────────────────────────────────────
        with tab4:
            st.header("📈 Price Distribution")

            if analyses:
                # Create histogram of all prices
                all_prices = []
                all_products = []
                for analysis in analyses:
                    for cp in analysis.competitor_prices:
                        all_prices.append(cp.price)
                        all_products.append(analysis.product_name[:30])

                if all_prices:
                    fig = px.histogram(
                        x=all_prices,
                        nbins=30,
                        title="Distribution of All Competitor Prices",
                        labels={"x": "Price ($)", "y": "Frequency"},
                        color_discrete_sequence=["#636EFA"]
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Price statistics
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Min Price", f"${min(all_prices):.2f}")
                    with col2:
                        st.metric("Max Price", f"${max(all_prices):.2f}")
                    with col3:
                        avg = sum(all_prices) / len(all_prices)
                        st.metric("Avg Price", f"${avg:.2f}")
                    with col4:
                        st.metric("Total Prices", len(all_prices))

        # ─────────────────────────────────────────────────────────────
        with tab5:
            st.header("📑 Detailed Reports")

            report_type = st.selectbox(
                "Select report type:",
                ["Summary", "By Urgency Level", "Price Adjustment Impact"]
            )

            if report_type == "Summary":
                st.subheader("Summary Report")
                st.write(f"""
                **Analysis Summary:**
                - Total products with competitor prices: {len(analyses)}
                - Total recommendations: {len(recommendations)}
                - Critical issues: {critical_count}
                - High priority: {high_count}
                - Medium priority: {medium_count}
                - Low priority: {low_count}

                **Top 5 Competitors Monitored:**
                """)
                for i, (domain, count) in enumerate(list(competitors.items())[:5], 1):
                    st.write(f"{i}. **{domain}** - {count} products")

            elif report_type == "By Urgency Level":
                st.subheader("Breakdown by Urgency Level")

                urgency_data = [
                    {"Urgency": "Critical", "Count": critical_count, "Color": "red"},
                    {"Urgency": "High", "Count": high_count, "Color": "orange"},
                    {"Urgency": "Medium", "Count": medium_count, "Color": "yellow"},
                    {"Urgency": "Low", "Count": low_count, "Color": "green"}
                ]

                fig = px.pie(
                    values=[critical_count, high_count, medium_count, low_count],
                    names=["Critical", "High", "Medium", "Low"],
                    color=["red", "orange", "yellow", "green"],
                    title="Recommendations by Urgency"
                )
                st.plotly_chart(fig, use_container_width=True)

            elif report_type == "Price Adjustment Impact":
                st.subheader("Potential Revenue Impact")

                if recommendations:
                    total_savings = sum(r.price_change_percent * r.our_price / 100 for r in recommendations)
                    avg_savings = total_savings / len(recommendations)

                    st.write(f"""
                    **Financial Impact of Recommended Price Adjustments:**
                    - Average price reduction per product: ${avg_savings:.2f}
                    - Total potential savings: ${total_savings:.2f}
                    - This would make you more competitive vs {len(competitors)} competitors
                    """)

                    # If this was actual implementation
                    st.info("""
                    **Implementation Note:**
                    These are competitor monitoring metrics. In a live system,
                    you would carefully implement price changes considering:
                    - Profit margins
                    - Inventory levels
                    - Market demand
                    - Customer loyalty
                    """)

    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.info("Make sure the agent has discovered competitor prices and the database has data.")


if __name__ == "__main__":
    main()
