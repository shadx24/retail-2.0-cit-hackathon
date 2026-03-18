"""
AGENT INTEGRATION GUIDE - Multi-Tenant Analytics System

This guide shows how to integrate the new components into the agent:
1. Shop Manager (multi-tenant setup)
2. Category Keyword Manager (category-specific keywords)
3. Analytics Engine (5 analytics features)
4. Product Discovery Filter (shop-specific filtering)

AGENT WORKFLOW:
Shop A (Electronics) --\
                        |---> Initialize Keywords for Category
Shop B (Fashion) ------/
                        |---> Run Agent Cycle
                        |
                        v
  Search with category keywords
  |
  v
  Filter by category
  |
  v
  Store prices (with shop_id)
  |
  v
  Run Analytics (5 features)
  |
  v
  Generate Report
"""

# ==============================================================
# EXAMPLE 1: Initialize a Shop and Keywords
# ==============================================================

"""
async def initialize_shop_for_agent(shop_name: str, category: str):
    '''
    One-time setup for a new shop/tenant.
    '''
    from database import SupabaseStore
    from shop_manager import ShopManager, CategoryKeywordManager
    
    db = SupabaseStore()
    shop_mgr = ShopManager(db)
    keyword_mgr = CategoryKeywordManager(db)
    
    # 1. Create shop
    shop = await shop_mgr.create_shop(
        shop_name=shop_name,
        shop_domain=f"{shop_name.lower()}.com",
        category=category,
        description=f"Monitoring {category} products"
    )
    
    print(f"✓ Created shop: {shop.shop_name} (ID: {shop.id})")
    
    # 2. Initialize keywords for shop's category
    await keyword_mgr.initialize_shop_keywords(shop.id, category)
    
    keywords = await keyword_mgr.get_active_keywords_for_shop(
        shop.id, 
        category, 
        limit=50
    )
    
    print(f"✓ Added {len(keywords)} keywords for {category}")
    print(f"  Sample keywords: {keywords[:5]}")
    
    return shop
"""


# ==============================================================
# EXAMPLE 2: Agent Cycle with Analytics
# ==============================================================

"""
async def run_agent_cycle_with_analytics(shop_id: int):
    '''
    Run a complete agent cycle for a shop with all 5 analytics features.
    
    This replaces the generic agent cycle with shop-specific operations.
    '''
    from database import SupabaseStore
    from shop_manager import ShopManager, CategoryKeywordManager, ProductDiscoveryFilter
    from agent_analytics import AnalyticsEngine
    
    db = SupabaseStore()
    shop_mgr = ShopManager(db)
    keyword_mgr = CategoryKeywordManager(db)
    analytics = AnalyticsEngine(db)
    
    # 1. Get shop and category
    shop = await shop_mgr.get_shop(shop_id)
    if not shop:
        print(f"Shop {shop_id} not found")
        return
    
    print(f"\\n{'='*80}")
    print(f"  AGENT CYCLE: {shop.shop_name} ({shop.category.upper()})")
    print(f"{'='*80}\\n")
    
    # Mark shop as active
    await shop_mgr.update_shop_last_active(shop_id)
    
    # 2. Get category-specific keywords
    keywords = await keyword_mgr.get_active_keywords_for_shop(
        shop_id,
        shop.category,
        limit=100
    )
    
    print(f"[Agent] Using {len(keywords)} keywords for {shop.category}")
    
    # 3. Search with filtered keywords (agent does searches here)
    #    Each search should tag results with shop_id
    search_results = await agent_tools.search_web(
        query=" ".join(keywords[:5]),  # Top 5 keywords
        shop_id=shop_id
    )
    
    # 4. Filter and store competitor prices (not our own domain)
    filter = ProductDiscoveryFilter(shop)
    filtered_competitors = filter.filter_competitors(
        [domain for domain in search_results],
        shop.shop_domain
    )
    
    # Store prices with shop_id
    for domain in filtered_competitors:
        # Store price data with shop_id
        pass
    
    # 5. Run full analytics suite
    analytics_results = await analytics.run_full_analytics_cycle(shop_id)
    
    # 6. Print analytics report
    report = analytics.format_analytics_report(analytics_results, shop_id)
    print(report)
    
    return analytics_results
"""


# ==============================================================
# EXAMPLE 3: Query Structure (what agent stores)
# ==============================================================

"""
COMPETITOR_PRICES table now includes:
├─ shop_id (NEW) - Which shop this data is for
├─ domain - Competitor domain (e.g., amazon.com)
├─ product_name - Product found
├─ price - Price discovered
├─ category - Product category (e.g., "electronic", "laptop")
├─ scraped_at - When it was found
└─ (other existing fields)

Example INSERT:
INSERT INTO competitor_prices (shop_id, domain, product_name, price, category, scraped_at)
VALUES (
    1,                           -- ElectroHub
    'amazon.com',
    'iPhone 15',
    ₹150000,
    'electronics',
    NOW()
);
"""


# ==============================================================
# EXAMPLE 4: Modified Agent Search (with shop_id)
# ==============================================================

"""
Modified agent_tools.search_web():

async def search_web_for_shop(query: str, shop_id: int, competitors_only: bool = True) -> List[str]:
    '''
    Search web for products relevant to a specific shop.
    '''
    from shop_manager import ShopManager, ProductDiscoveryFilter
    
    shop = await ShopManager(db).get_shop(shop_id)
    filter = ProductDiscoveryFilter(shop)
    
    # 1. Enhance query with category
    enhanced_query = filter.format_search_query(query)
    # "iPhone 15" becomes "iPhone 15 electronics price deal"
    
    # 2. Do web search
    urls = await duckduckgo_search(enhanced_query)
    
    # 3. Filter out shop's own domain
    filtered_urls = []
    for url in urls:
        domain = extract_domain(url)
        if filter.filter_competitors([domain], shop.shop_domain):
            filtered_urls.append(url)
        else:
            print(f"[Filter] Skipped own domain: {domain}")
    
    # 4. Return competitor-only URLs
    return filtered_urls
"""


# ==============================================================
# EXAMPLE 5: Running Concurrent Shops
# ==============================================================

"""
async def run_multi_shop_agent_cycle():
    '''
    Run agent for multiple shops concurrently.
    Each shop gets its own cycle with independent keywords and analytics.
    '''
    from database import SupabaseStore
    from shop_manager import ShopManager
    import asyncio
    
    db = SupabaseStore()
    shop_mgr = ShopManager(db)
    
    # Get all active shops
    shops = await shop_mgr.list_shops(active_only=True)
    
    print(f"[Agent] Running cycles for {len(shops)} shops")
    
    # Run cycles concurrently
    tasks = []
    for shop in shops:
        task = run_agent_cycle_with_analytics(shop.id)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    print(f"\\n[Agent] Completed {len(results)} shop cycles")
    
    # Aggregate results
    total_emerging = sum(len(r['emerging_products']) for r in results)
    total_drops = sum(len(r['price_drops']) for r in results)
    
    print(f"  Total emerging products: {total_emerging}")
    print(f"  Total price drops: {total_drops}")
"""


# ==============================================================
# DATABASE MIGRATION STEPS
# ==============================================================

"""
STEP 1: Run schema additions
   Run SCHEMA_ADDITIONS.sql in Supabase SQL editor

STEP 2: Add shop_id to existing tables
   ALTER TABLE competitor_prices ADD COLUMN shop_id BIGINT;
   ALTER TABLE keyword_pool ADD COLUMN shop_id BIGINT;
   ALTER TABLE price_history ADD COLUMN shop_id BIGINT;

STEP 3: Create initial shops
   INSERT INTO shops (shop_name, shop_domain, category, is_active)
   VALUES ('Shop A', 'shopa.com', 'electronics', true);

STEP 4: Initialize keywords for each shop
   Run: keyword_mgr.initialize_shop_keywords(shop_id, category)

STEP 5: Start agent with shop context
   Run: run_agent_cycle_with_analytics(shop_id)
"""


# ==============================================================
# AGENT CORE MODIFICATIONS NEEDED
# ==============================================================

"""
Files to modify in agent_core.py:

1. Add imports:
   from shop_manager import ShopManager, CategoryKeywordManager, ProductDiscoveryFilter
   from agent_analytics import AnalyticsEngine

2. Add to AgentReasoningCore.__init__():
   self.shop_id = shop_id  # Pass from agent_engine
   self.shop_mgr = ShopManager(self.db)
   self.keyword_mgr = CategoryKeywordManager(self.db)
   self.analytics = AnalyticsEngine(self.db)
   self.filter = None  # Will be set in initialize()

3. Add to initialize():
   shop = await self.shop_mgr.get_shop(self.shop_id)
   self.filter = ProductDiscoveryFilter(shop)
   keywords = await self.keyword_mgr.get_active_keywords_for_shop(
       self.shop_id, shop.category
   )

4. Modify search_web() to:
   - Use shop-specific keywords
   - Filter out own domain
   - Tag results with shop_id

5. Modify run_cycle() to:
   - Call analytics.run_full_analytics_cycle() at end
   - Print analytics report instead of just price count
"""


# ==============================================================
# ENVIRONMENT VARIABLES
# ==============================================================

"""
Add to .env:

# Agent Shop Configuration
AGENT_SHOP_ID=1
AGENT_SHOP_NAME=ElectroHub
AGENT_SHOP_CATEGORY=electronics

Or pass via command line:
python3 agent_engine.py --shop-id=1
"""


# ==============================================================
# SAMPLE AGENT INITIALIZATION
# ==============================================================

"""
# In agent_engine.py, modify AgentExecutionController.__init__():

def __init__(self, shop_id: int = None):
    self.shop_id = shop_id or os.getenv('AGENT_SHOP_ID', 1)
    self.db = SupabaseStore()
    self.agent = AgentReasoningCore(self.db, shop_id=self.shop_id)
    
    # ... rest of init
    
    print(f"[AgentEngine] Running for Shop ID: {self.shop_id}")

# Then in agent_engine.py main:
if __name__ == "__main__":
    import sys
    shop_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    controller = AgentExecutionController(shop_id=shop_id)
    asyncio.run(controller.run_forever())

# Usage:
# python3 agent_engine.py 1  # Run for shop ID 1
# python3 agent_engine.py 2  # Run for shop ID 2
"""


# ==============================================================
# 5 ANALYTICS FEATURES SUMMARY
# ==============================================================

"""
1️⃣  EMERGING PRODUCT RADAR
   - Detects products <24h old on ≥2 retailers
   - Use case: Find trending products before they go mainstream
   - Output: emerging_products table + console alerts

2️⃣  PRICE VOLATILITY SCORE
   - Measures price instability (standard deviation)
   - Use case: Identify products with frequent price wars
   - Output: product_volatility table + volatility classification

3️⃣  COMPETITOR COVERAGE MAP
   - Shows market dominance by category
   - Use case: Understand competitor reach in your category
   - Output: competitor_coverage table + market share %

4️⃣  PRICE DROP DETECTOR
   - Detects sudden price reductions (≥5% drops)
   - Use case: Alert on competitive pricing threats
   - Output: price_drops table + alert notifications

5️⃣  AUTOMATIC PRODUCT DISCOVERY
   - Finds trending products across retailers
   - Use case: Discover new products to monitor
   - Output: product_metadata table + confidence scores
"""


# ==============================================================
# COMPLETE AGENT CYCLE WITH ANALYTICS
# ==============================================================

"""
FULL WORKFLOW:

1. Start Agent
   └─ Load Shop (category: electronics)
   
2. Get Keywords
   └─ 100 category-specific keywords (electronics)
   
3. Search & Crawl
   └─ Search "iPhone 15 electronics price"
   └─ Extract prices from competitors
   └─ Tag with shop_id=1
   
4. Filter & Store
   └─ Remove our own domain
   └─ Store competitor prices: shop_id=1
   
5. Calculate Analytics (all 5 features)
   ├─ 🚀 Emerging Products
   │  └─ Sony WH-1000XM6 found on 3 retailers (3h old)
   ├─ 📈 Price Volatility
   │  └─ iPhone 15: volatility_score=45.3 (HIGH)
   ├─ 🏪 Competitor Coverage
   │  └─ Amazon: 156/450 (34.7%) - DOMINANT
   ├─ ⬇️  Price Drops
   │  └─ Samsung S24: ₹72000→₹69999 (-2.8%)
   └─ 🔍 Discovered Products
      └─ 42 products found across 5 retailers
   
6. Report & Alert
   └─ Print analytics report
   └─ Create database alerts
   └─ Log cycle metrics
   
7. Sleep & Repeat
   └─ Wait cooldown (e.g., 30 minutes)
   └─ Start next cycle
"""

print(__doc__)
