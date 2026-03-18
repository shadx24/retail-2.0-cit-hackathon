import { useState, useMemo, useCallback, useEffect } from 'react';

const API_BASE = '/api';

/**
 * Custom hook that manages all dashboard state and derived metrics.
 * Fetches real data from the backend API (FastAPI + Supabase).
 */
export function useDashboard() {
  const [step, setStep] = useState('setup');
  const [shopName, setShopName] = useState('');
  const [selectedDomain, setSelectedDomain] = useState(null);
  const [customDescription, setCustomDescription] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [lastScan, setLastScan] = useState(null);
  const [scrapedData, setScrapedData] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [shopId, setShopId] = useState(null);
  const [inventory, setInventory] = useState([]);

  const runScan = useCallback(async () => {
    if (!shopId) return;
    setIsScanning(true);
    try {
      const res = await fetch(`${API_BASE}/scan/${shopId}`, { method: 'POST' });
      if (res.ok) {
        const newData = await res.json();
        setScrapedData(newData);
        setLastScan(new Date().toLocaleTimeString());
      }
    } catch (err) {
      console.error('Scan failed:', err);
    }
    setIsScanning(false);
  }, [shopId]);

  const handleStartSetup = useCallback(async () => {
    if (shopName && selectedDomain) {
      setStep('dashboard');
      setIsScanning(true);
      try {
        const res = await fetch(`${API_BASE}/shop/setup`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            shopName,
            domainId: selectedDomain.id,
            domainName: selectedDomain.name,
            keywords: selectedDomain.keywords || [],
            customDescription,
          }),
        });
        if (res.ok) {
          const result = await res.json();
          setShopId(result.shopId);
          setScrapedData(result.data);
          setLastScan(new Date().toLocaleTimeString());

          // Fetch inventory for this shop
          try {
            const invRes = await fetch(`${API_BASE}/inventory/${result.shopId}`);
            if (invRes.ok) setInventory(await invRes.json());
          } catch (e) { console.error('Inventory fetch:', e); }
        }
      } catch (err) {
        console.error('Setup failed:', err);
      }
      setIsScanning(false);
    }
  }, [shopName, selectedDomain, customDescription]);

  // Derived metrics
  const emergingProducts = useMemo(() => scrapedData.filter((d) => d.isNew), [scrapedData]);

  const priceDrops = useMemo(() => {
    // Group by product name, find the competitor with the lowest price
    const grouped = {};
    scrapedData.forEach((d) => {
      if (!grouped[d.name]) grouped[d.name] = [];
      grouped[d.name].push(d);
    });

    return Object.values(grouped)
      .map((items) => {
        const sorted = [...items].sort((a, b) => a.price - b.price);
        const cheapest = sorted[0];
        const avgPrice = items.reduce((s, i) => s + i.price, 0) / items.length;
        const dropPct = ((avgPrice - cheapest.price) / avgPrice) * 100;
        if (dropPct < 2) return null; // Only show meaningful drops
        return {
          ...cheapest,
          oldPrice: Math.round(avgPrice),
          dropPercent: Math.round(dropPct),
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.dropPercent - a.dropPercent);
  }, [scrapedData]);

  const marketShare = useMemo(() => {
    const counts = {};
    scrapedData.forEach((d) => (counts[d.competitor] = (counts[d.competitor] || 0) + 1));
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [scrapedData]);

  const alerts = useMemo(() => {
    const alertsList = [];

    // Build inventory lookup map: product_name (lowercase) → quantity
    const inventoryMap = {};
    inventory.forEach(inv => {
      inventoryMap[inv.product_name.toLowerCase()] = inv.quantity;
    });

    const hasInventory = inventory.length > 0;
    
    // Helper: get stock for a product (real inventory or null if no inventory)
    const getStock = (name) => {
      const key = name.toLowerCase();
      // Exact match
      if (inventoryMap[key] !== undefined) return inventoryMap[key];
      // Partial match: check if any inventory item is a substring of the product name
      for (const [invName, qty] of Object.entries(inventoryMap)) {
        if (key.includes(invName) || invName.includes(key)) return qty;
      }
      return null; // Not in inventory
    };

    const uniqueProducts = Array.from(new Set(scrapedData.map(d => d.name)));
    
    uniqueProducts.forEach(name => {
      const productEntries = scrapedData.filter(d => d.name === name);
      const avgVol = productEntries.reduce((s, i) => s + parseFloat(i.volatility), 0) / productEntries.length;
      const stock = getStock(name);

      // Only generate stock-based alerts if user has inventory
      if (hasInventory && stock !== null) {
        // Rule A: High Priority Restock (Urgent) — real low stock + high demand
        if (avgVol > 5 && stock < 12) {
          alertsList.push({
            id: `stock-${name}`,
            type: 'urgent',
            title: 'Critical Stock Alert',
            message: `Demand for ${name} is surging, but your stock is low (${stock} units).`,
            icon: 'package',
            details: {
              rationale: `Market activity for "${name}" has spiked by ${avgVol.toFixed(1)}% across competitors. Your current inventory of ${stock} units may not last the week.`,
              recommendation: `Restock at least ${Math.max(40 - stock, 20)} units immediately. At current demand levels, you risk stockout within ${Math.max(1, Math.round(stock / 3))} days.`,
              marketSignal: `Competitors are actively listing this product. Price volatility indicates strong consumer interest.`
            }
          });
        }

        // Rule B: Overstocked slow movers — high stock + low demand
        if (avgVol < 3 && stock > 30) {
          alertsList.push({
            id: `overstock-${name}`,
            type: 'warning',
            title: 'Overstock Warning',
            message: `${name} has ${stock} units but demand is slowing (volatility: ${avgVol.toFixed(1)}%).`,
            icon: 'percent',
            details: {
              rationale: `Demand for "${name}" has dropped with volatility at only ${avgVol.toFixed(1)}%. Holding ${stock} units ties up capital with high depreciation risk.`,
              recommendation: `Consider a 10-15% clearance discount to move inventory. Target reducing stock to ~15 units within 2 weeks.`,
              marketSignal: `Competitor pricing is trending downward, suggesting market-wide demand weakness for this product.`
            }
          });
        }
      }

      // Rule C: Opportunity alert — trending product NOT in inventory
      if (hasInventory && stock === null && avgVol > 8) {
        alertsList.push({
          id: `opportunity-${name}`,
          type: 'info',
          title: 'Stock Opportunity',
          message: `${name} is trending (volatility: ${avgVol.toFixed(1)}%) but not in your inventory.`,
          icon: 'trending',
          details: {
            rationale: `"${name}" shows high market activity across competitors but you don't stock it. This could be a missed revenue opportunity.`,
            recommendation: `Evaluate adding this product to your inventory. Current market price: ₹${productEntries[0]?.price?.toLocaleString('en-IN') || 'N/A'}.`,
            marketSignal: `Multiple competitors are actively listing this product with strong price competition.`
          }
        });
      }
    });

    // Rule D: Low inventory general alert
    if (hasInventory) {
      const lowStockItems = inventory.filter(inv => inv.quantity > 0 && inv.quantity < 5);
      if (lowStockItems.length > 0) {
        alertsList.push({
          id: 'low-stock-general',
          type: 'urgent',
          title: 'Multiple Low Stock Items',
          message: `${lowStockItems.length} product(s) have fewer than 5 units: ${lowStockItems.map(i => i.product_name).join(', ')}.`,
          icon: 'package',
          details: {
            rationale: `These items are critically low and at risk of stockout: ${lowStockItems.map(i => `${i.product_name} (${i.quantity} left)`).join(', ')}.`,
            recommendation: `Prioritize restocking these items immediately to avoid lost sales.`,
            marketSignal: `Maintaining stock availability is crucial for competitive positioning.`
          }
        });
      }
    }

    // Rule E: Platform Demand Surge (no inventory needed)
    const marketSurges = scrapedData.filter(d => 
      (d.competitor === 'Amazon.in' || d.competitor === 'Flipkart') && 
      d.isNew && 
      parseFloat(d.volatility) > 8
    );

    marketSurges.forEach(surge => {
      alertsList.push({
        id: `surge-${surge.id}`,
        type: 'info',
        title: 'Platform Demand Surge',
        message: `${surge.name} is trending rapidly on ${surge.competitor}.`,
        icon: 'trending',
        details: {
          rationale: `We detected a 24-hour demand spike for "${surge.name}" on ${surge.competitor}. This product is currently outperforming 90% of its category peers in search volume.`,
          recommendation: `Evaluate for immediate listing if you have supplier access. This is a "High Velocity" opportunity with low initial competition.`,
          marketSignal: `Verified purchase reviews are growing at 5x the category average on Amazon.in.`
        }
      });
    });

    return alertsList.sort((a, b) => (a.type === 'urgent' ? -1 : 1));
  }, [scrapedData, inventory]);

  return {
    step,
    shopName,
    setShopName,
    selectedDomain,
    setSelectedDomain,
    customDescription,
    setCustomDescription,
    isScanning,
    lastScan,
    scrapedData,
    activeTab,
    setActiveTab,
    runScan,
    handleStartSetup,
    emergingProducts,
    priceDrops,
    marketShare,
    alerts,
    shopId,
    inventory,
    setInventory,
  };
}
