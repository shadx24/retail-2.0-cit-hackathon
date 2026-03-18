# 🚀 QUICK START GUIDE - Multi-Tenant Agent

## 5-Minute Setup

### Step 1: Deploy Database Schema (1 min)

Copy entire content of `SCHEMA_ADDITIONS.sql` and paste into Supabase SQL editor:

```bash
# Verify SCHEMA_ADDITIONS.sql exists
ls SCHEMA_ADDITIONS.sql
```

Then in Supabase:
1. Open SQL Editor
2. Create new query
3. Paste entire file content
4. Click "Run"

**Result**: 7 new tables + functions created ✅

---

### Step 2: Create Your First Shop (1 min)

```bash
python3 -c "
from shop_manager import ShopManager
from database import SupabaseStore
import asyncio

async def create_shop():
    db = SupabaseStore()
    mgr = ShopManager(db)
    
    # Create shop
    shop = await mgr.create_shop(
        shop_name='ElectroHub',
        shop_domain='electrohub.com',
        category='electronics',
        description='Electronics price monitoring'
    )
    
    print(f'✅ Shop created!')
    print(f'   ID: {shop.id}')
    print(f'   Name: {shop.shop_name}')
    print(f'   Domain: {shop.shop_domain}')
    print(f'   Category: {shop.category}')

asyncio.run(create_shop())
"
```

**Output**:
```
✅ Shop created!
   ID: 1
   Name: ElectroHub
   Domain: electrohub.com
   Category: electronics
```

---

### Step 3: Start Agent for Shop (1 min)

```bash
# Run agent for shop ID 1
python3 agent_engine.py 1
```

**Output** (first cycle):
```
================================================================================
  GOAL-ORIENTED AUTONOMOUS WEB AGENT
  Objective: Monitor competitor prices and pricing trends
  Model: moonshotai/kimi-k2-instruct (NVIDIA)
  Shop ID: 1
================================================================================

[AgentEngine] Initializing database...
[AgentEngine] Ready.

[Agent] Initializing shop 1...
[Agent] Loaded shop: ElectroHub (electronics)
[Agent] Initialized 50 keywords for electronics
[Agent] Sample keywords: ['iPhone 15', 'Samsung Galaxy', 'laptop price deal', ...]
[Agent] Shop 1 initialized and ready

============================================================
[Agent] Cycle #1 | Shop: ElectroHub | 2026-03-06T14:23:45
============================================================

[Agent] Observing database state...
[Agent] Decision: search_web — Searching for electronics products with competitive pricing
[Agent] Processing 15 search results...
✓ Price: amazon.com/iphone-15-price...
✓ Price: flipkart.com/samsung-s24-deal...
...

Cycle #1 complete: 12 actions, 45 prices, 8.3s

Running analytics for ElectroHub...

================================================================================
                    PRODUCT ANALYTICS REPORT
================================================================================

📊 CYCLE SUMMARY
Processing time: 8.3s

🚀 EMERGING PRODUCTS (3)
  1. Sony WH-1000XM6 (3h old, 3 retailers)
     └─ amazon.com, flipkart.com, bestbuy.com

📈 PRICE VOLATILITY - HIGH RISK (1)
  1. iPhone 15 (Volatility: 45.23, Range: ₹150000-₹165000)

🏪 COMPETITOR COVERAGE BY CATEGORY
  electronics:
    • amazon.com: 156 products (34.7%)
    • flipkart.com: 142 products (31.6%)

⬇️ PRICE DROPS DETECTED (0)
  None

🔍 AUTO-DISCOVERED PRODUCTS (5 new)
  1. Samsung Galaxy S24 (Confidence: 100%)
     └─ 5 retailers: amazon, flipkart, bestbuy, newegg, walmart

================================================================================

[AgentEngine] Cumulative: 1 cycles, 45 prices, runtime: 0:00:12
[AgentEngine] Sleeping 5 minutes...
```

**Agent now running** ✅ Will run continuously until stopped with Ctrl+C

---

## Advanced: Multiple Shops

### Create Shop 2 (Fashion)

```bash
python3 -c "
from shop_manager import ShopManager
from database import SupabaseStore
import asyncio

async def create_shop():
    db = SupabaseStore()
    mgr = ShopManager(db)
    shop = await mgr.create_shop('FashionPro', 'fashionpro.com', 'fashion')
    print(f'✅ Shop {shop.id} created: {shop.shop_name}')

asyncio.run(create_shop())
"
```

### Run Both Shops Concurrently

**Terminal 1** (Electronics):
```bash
python3 agent_engine.py 1
```

**Terminal 2** (Fashion):
```bash
python3 agent_engine.py 2
```

Each runs independently with:
- Different keywords (electronics vs fashion)
- Different category filtering
- Independent analytics reports
- Separate database isolation

---

## Verify It's Working

### Check Database

```bash
# View created shops
python3 -c "
from shop_manager import ShopManager
from database import SupabaseStore
import asyncio

async def list_shops():
    db = SupabaseStore()
    mgr = ShopManager(db)
    shops = await mgr.list_shops()
    for shop in shops:
        print(f'{shop.id}. {shop.shop_name} ({shop.category})')

asyncio.run(list_shops())
"
```

### Check Prices Collected

```bash
# In Supabase SQL editor
SELECT COUNT(*) as total_prices FROM competitor_prices WHERE shop_id = 1;
SELECT COUNT(DISTINCT product_name) as unique_products FROM competitor_prices WHERE shop_id = 1;
```

### Check Analytics Results

```bash
# In Supabase SQL editor
SELECT * FROM emerging_products WHERE shop_id = 1 LIMIT 5;
SELECT * FROM product_volatility WHERE shop_id = 1 LIMIT 5;
SELECT * FROM competitor_coverage WHERE shop_id = 1 LIMIT 5;
```

---

## Environment Variables (Optional)

```bash
# Set default shop
export AGENT_SHOP_ID=1

# Then just run without argument
python3 agent_engine.py  # Uses shop 1
```

---

## Troubleshooting

### Shop not found error
```
ERROR: Shop 1 not found
```
**Solution**: Create shop first (Step 2 above)

### No prices being found
**Check**:
1. Supabase connection is working
2. Keywords were initialized (look for "Initialized X keywords" in output)
3. DuckDuckGo isn't rate-limiting you (wait a few minutes)

### Analytics not calculating
**Check**:
1. Prices have been collected (take 2-3 cycles)
2. Multiple retailers have same product (needed for volatility)
3. Check logs for errors starting with "[Agent] Analytics error"

---

## Understanding the Output

### Key Metrics

**🚀 Emerging Products**
- Products found in last 24h
- On 2+ retailers
- Potential trending items

**📈 Price Volatility**
- HIGH = Unstable price (>30 std dev)
- Good for identifying price wars

**🏪 Competitor Coverage**  
- Market share by competitor
- Shows dominant players

**⬇️ Price Drops**
- Price reduced by 5%+ in recent check
- Competitive threat indicator

**🔍 Discovered Products**
- New products found across retailers
- Confidence based on # of retailers

---

## Next Steps

1. **Let it run** - First 5-10 cycles build up data
2. **Monitor shop** - Check analytics each cycle
3. **Add more shops** - Create shop 2, 3, etc with different categories
4. **Check database** - Query emerging_products, price_drops tables
5. **Tune keywords** - Adjust category keywords for better results

---

## File Organization

```
agent_engine.py          ← Main entry point
  ↓ (starts)
agent_core.py            ← Agent reasoning loop
  ├─ shop_manager.py     ← Multi-tenant management
  ├─ agent_analytics.py  ← 5 Analytics features
  ├─ agent_tools.py      ← Search, browse, score
  └─ database.py         ← Supabase connection

SCHEMA_ADDITIONS.sql     ← Database migrations
AGENT_REQUIREMENTS.md    ← Detailed requirements
AGENT_INTEGRATION_GUIDE.md ← Integration examples
```

---

## Summary

| Step | Time | Command |
|------|------|---------|
| 1. Deploy schema | 1 min | Supabase SQL editor |
| 2. Create shop | 1 min | `python3 create_shop.py` |
| 3. Start agent | <30 sec | `python3 agent_engine.py 1` |
| **Total** | **3 min** | **Ready!** |

---

**Status**: ✅ Ready to monitor competitors!

See documentation files for more details:
- `AGENT_REQUIREMENTS.md` - Full requirements
- `AGENT_INTEGRATION_GUIDE.md` - Integration examples
- `IMPLEMENTATION_COMPLETE.md` - What was implemented
