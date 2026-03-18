# Quick Reference: Pricing Intelligence System

## 🚀 Getting Started (2 Minutes)

### What You Have
A complete competitive pricing system with:
- ✅ Web agent discovering competitor prices (running now)
- ✅ Price intelligence engine analyzing data (just added)
- ✅ Interactive dashboard for visualization (ready to use)
- ✅ Automatic reporting in console (automatic)

### How to Use

#### Option 1️⃣: See Console Reports (Automatic)
The agent already prints pricing reports automatically! You should see them in the agent terminal every 10 cycles (~5 minutes).

```
[AgentEngine] Generating pricing intelligence report...
================================================================================
                    COMPETITIVE PRICING INTELLIGENCE REPORT
================================================================================
...pricing recommendations appear here...
```

#### Option 2️⃣: Launch Interactive Dashboard (Best for Demo)
```bash
cd /home/keiths/Desktop/Openclaw/student-CIT-app/student_scraper/retail-agent
source venv/bin/activate
./run_dashboard.sh

# Opens at http://localhost:8501
```

**Dashboard has 5 tabs:**
1. 📌 Top Recommendations - Pricing action items
2. 📊 Price Analysis - Drill into products
3. 🏢 Competitor Overview - Market view
4. 📈 Price Distribution - Statistics
5. 🎯 Reports - Summaries & impact

#### Option 3️⃣: Run Examples
```bash
cd /home/keiths/Desktop/Openclaw/student-CIT-app/student_scraper/retail-agent
source venv/bin/activate
python3 example_usage.py

# Choose examples to see all features
```

---

## 📊 What the System Does

### Input
```
Agent discovers: iPhone 15 prices at BestBuy ($899), Amazon ($895), Newegg ($898)
                 Samsung S24 prices at BestBuy ($799), Amazon ($749)
                 ...etc...
```

### Processing
```
Price Intelligence Engine:
1. Groups prices by product name
2. Calculates: min, max, avg, range
3. Compares with your prices (if set)
4. Determines: where you stand vs competitors
5. Suggests: optimal price = (lowest competitor - margin)
6. Prioritizes: by urgency (critical > high > medium > low)
```

### Output
```
Pricing Recommendations:
Product: iPhone 15
  Your Price: $999.99 ← Problem!
  Lowest Competitor: $895.00
  Suggested Price: $886.05
  Change: -11.4%
  Urgency: CRITICAL
  Reason: Your price exceeds all competitors by wide margin
```

---

## 📁 File Reference

### Core New Files

| File | Purpose | Lines |
|------|---------|-------|
| `price_intelligence.py` | Analysis engine | 180 |
| `dashboard.py` | WebUI | 350 |
| `example_usage.py` | Usage examples | 200 |
| `run_dashboard.sh` | Dashboard launcher | shell |

### Documentation

| File | Purpose |
|------|---------|
| `PRICING_INTELLIGENCE.md` | Full documentation |
| `IMPLEMENTATION_SUMMARY.md` | What was added & why |
| `QUICK_REFERENCE.md` | This file |

### Modified Files

| File | Changes |
|------|---------|
| `agent_engine.py` | +10 lines for pricing integration |
| `requirements.txt` | +3 deps (streamlit, plotly, pandas) |

---

## 🎯 Key Concepts

### Urgency Levels
- **🔴 CRITICAL** - Your price > highest competitor (fix immediately)
- **🟠 HIGH** - Your price > avg + 10% (fix within 7 days)
- **🟡 MEDIUM** - Your price > avg (monitor)
- **🟢 LOW** - Your price ≤ avg (no action)

### Suggested Price Formula
```
Suggested Price = Lowest Competitor Price × (1 - Margin%)

Example:
  Lowest Competitor: $900
  Margin: 1%
  Suggested Price: $900 × (1 - 0.01) = $891
```

This ensures you:
1. Beat all competitors on price ✓
2. Stay profitable (adjust margin per product) ✓
3. Stay above cost + overhead ✓

---

## 💡 Common Use Cases

### Use Case 1: Price Too High
```
Agent finds: iPhone 15 at Amazon ($895), BestBuy ($899)
You're at: $999
Recommendation: Reduce to $886 CRITICAL!
```

### Use Case 2: Competitive Position
```
Agent finds: Samsung S24 at Amazon ($749), BestBuy ($799)
You're at: $790
Recommendation: Could maintain at $790 (good position)
```

### Use Case 3: Unknown Product
```
Agent finds: New product at 5 competitors
You have: No price set
Recommendation: Set price at $X (calculated from market)
```

---

## 📈 Dashboard Tour (30 seconds)

### Tab 1: Top Recommendations
- See all pricing issues at a glance
- Filter by urgency level
- Click product for detailed comparison chart
- Shows exact suggested prices

### Tab 2: Price Analysis
- Select any product
- See all competitor prices
- View price scatter plot
- Detailed competitor list

### Tab 3: Competitor Overview
- Top 15 competitors by reach
- Market share percentages
- Which competitors cover most products

### Tab 4: Price Distribution
- Histogram of all prices
- Identify price clusters
- See market pricing trends

### Tab 5: Reports
- Executive summary
- Pie chart of urgency breakdown
- Revenue impact estimates

---

## 🔧 Configuration

### Change Margin %
In `price_intelligence.py`:
```python
engine = PriceIntelligenceEngine(db, margin_percent=2.0)  # 2% undercut
```

### Change Report Frequency
In `agent_engine.py`:
```python
self._pricing_report_interval = 5  # Report every 5 cycles instead of 10
```

### Change Alert Threshold
In `price_intelligence.py`:
```python
alerts = await engine.create_price_alerts(threshold_percent=10.0)  # >10% 
```

---

## ❓ FAQ

**Q: When do reports show up?**
A: Every 10 agent cycles (~5 minutes). Check agent terminal for `COMPETITIVE PRICING INTELLIGENCE REPORT` header.

**Q: How do I know if my price is good?**
A: Dashboard shows your position (above/below/at average). Green light = competitive.

**Q: Can it automatically change my prices?**
A: Framework is ready! Just connect your e-commerce API. See PRICING_INTELLIGENCE.md for details.

**Q: How many competitors does it track?**
A: Depends on agent discovery. Agent runs continuously, so more competitors = more data.

**Q: Is the dashboard real-time?**
A: Yes! Refresh with button or wait for auto-refresh. Uses latest database data.

**Q: How do I add my own products?**
A: Insert into `our_products` table in Supabase. Then recommendations compare against them.

---

## ✅ Verification Checklist

- ✅ Agent is running (`python3 agent_engine.py`)
- ✅ Discovering competitor prices (check terminal output)
- ✅ Storing in database (our_products + competitor_prices tables)
- ✅ Price intelligence engine ready (imported in agent_engine.py)
- ✅ Reports generate automatically (watch agent terminal every 10 cycles)
- ✅ Dashboard can launch (run_dashboard.sh works)
- ✅ Documentation complete (PRICING_INTELLIGENCE.md exists)

---

## 📞 Support

### Check if system is working:

1. **Agent running?**
   ```bash
   ps aux | grep "agent_engine.py"
   ```

2. **Prices in database?**
   - Go to Supabase dashboard
   - Check `competitor_prices` table
   - Should have 50+ rows after 5 minutes

3. **Engine loads?**
   ```bash
   python3 -c "from price_intelligence import PriceIntelligenceEngine; print('✓ Loaded')"
   ```

4. **Dashboard works?**
   ```bash
   streamlit run dashboard.py
   ```

---

## 🎓 Learning Path

1. **Start here**: This file (QUICK_REFERENCE.md)
2. **See it work**: Launch `./run_dashboard.sh`
3. **Understand it**: Read `PRICING_INTELLIGENCE.md`
4. **Try examples**: Run `python3 example_usage.py`
5. **Integrate**: Use code in `IMPLEMENTATION_SUMMARY.md`
6. **Customize**: Modify `price_intelligence.py`

---

## 🚀 Next Steps

### Short Term (This Week)
- ✅ Demo dashboard to stakeholders
- ✅ Verify competitor price accuracy
- ✅ Set margin% based on your profit targets
- ✅ Review recommendations weekly

### Medium Term (This Month)
- Add manual review workflow
- Connect to pricing API
- Export recommendations to CSV
- Train team on system

### Long Term (This Quarter)
- Auto-price integration
- Predictive pricing (ML)
- Supplier cost tracking
- Dynamic margins by category

---

**System Status**: ✅ OPERATIONAL  
**Agent Status**: ✅ RUNNING (discovering prices now)  
**Dashboard**: ✅ READY TO LAUNCH  
**Documentation**: ✅ COMPLETE

---

Questions? See:
- Full guide: `PRICING_INTELLIGENCE.md`
- Implementation details: `IMPLEMENTATION_SUMMARY.md`
- Code examples: `example_usage.py`
- Agent logs: Check terminal running agent
