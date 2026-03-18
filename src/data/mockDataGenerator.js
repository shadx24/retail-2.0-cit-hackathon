import { COMPETITORS } from './constants';

/**
 * Realistic price ranges per product keyword.
 * Each product has a base price and a variance range so competitors
 * show slightly different prices (±variance).
 */
const PRICE_MAP = {
  // Electronics
  'iPhone':          { base: 79990,  variance: 8000 },
  'Sony headphones': { base: 19990,  variance: 3000 },
  'MacBook':         { base: 129990, variance: 12000 },
  'Samsung S24':     { base: 74999,  variance: 7000 },
  'Gaming Laptop':   { base: 89990,  variance: 10000 },
  // Fashion
  'Nike Jordans':     { base: 12995, variance: 2000 },
  'Levis 501':        { base: 3499,  variance: 600 },
  'Adidas Originals': { base: 7999,  variance: 1200 },
  'Smart Watch':      { base: 24999, variance: 4000 },
  'Tote Bag':         { base: 2999,  variance: 500 },
  // Home Appliances
  'Air Fryer':        { base: 4999,  variance: 1500 },
  'Washing Machine':  { base: 28990, variance: 5000 },
  'Smart TV':         { base: 34990, variance: 6000 },
  'Microwave':        { base: 8990,  variance: 1500 },
  'AC':               { base: 35990, variance: 5000 },
  // Gaming
  'RTX 4080':             { base: 119990, variance: 10000 },
  'Mechanical Keyboard':  { base: 6999,   variance: 1500 },
  'Gaming Mouse':         { base: 3499,   variance: 800 },
  'PS5 Console':          { base: 49990,  variance: 4000 },
  'OLED Monitor':         { base: 54990,  variance: 6000 },
};

/**
 * Seeded-random helper so volatility is consistent per product+competitor
 * but still varied across the data set.
 */
function seededRandom(seed) {
  let x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

/**
 * Generate realistic mock scraped product data for a given domain.
 *
 * - Prices cluster around a realistic base per product with competitor variance
 * - Volatility is assigned logically:
 *     High (7-10) — high-demand / hype items
 *     Medium (4-7) — moderately stable
 *     Low (0-4) — everyday / stable items
 * - Model numbers are realistic suffixes (Pro, Plus, series, etc.)
 */
const MODEL_SUFFIXES = ['Pro', 'Plus', 'Ultra', 'Lite', 'Max', 'SE', 'Neo', 'Air'];

// Products that tend to have higher price volatility (demand-driven)
const HIGH_VOLATILITY_KEYWORDS = ['iPhone', 'RTX 4080', 'PS5 Console', 'Gaming Laptop', 'MacBook', 'Nike Jordans'];

export const generateScrapedData = (domain) => {
  let products = domain?.keywords || [];
  
  // If no keywords (Custom domain), use generic placeholders
  if (products.length === 0) {
    products = ['Specialty Item Alpha', 'Custom Product Beta', 'Premium Goods Gamma', 'Niche Solution Delta', 'Global Supply Echo'];
  }

  let seedCounter = 1;

  return products.flatMap((productName, pIdx) => {
    const priceInfo = PRICE_MAP[productName] || { base: 14999, variance: 3000 };
    const suffix = MODEL_SUFFIXES[pIdx % MODEL_SUFFIXES.length];
    const isHighVolatility = HIGH_VOLATILITY_KEYWORDS.includes(productName);

    return COMPETITORS.map((comp, cIdx) => {
      const seed = seedCounter++;
      const rand = seededRandom(seed);

      // Price: base ± variance, slightly different per competitor
      const priceOffset = Math.round((rand - 0.5) * 2 * priceInfo.variance);
      const price = priceInfo.base + priceOffset;

      // Volatility: logical range based on product type + small per-competitor jitter
      let volBase;
      if (isHighVolatility) {
        volBase = 6.5 + rand * 3.5;  // 6.5 – 10.0
      } else {
        volBase = 1.0 + rand * 6.0;  // 1.0 – 7.0
      }
      const volatility = Math.min(10, Math.max(0.5, volBase)).toFixed(1);

      // Emerging product: only ~15% chance, biased toward less common competitors
      const isNew = cIdx >= 3 && rand > 0.65;

      return {
        id: `${productName.replace(/\s/g, '').toLowerCase()}-${comp.replace(/[\s.]/g, '').toLowerCase()}-${seed}`,
        name: `${productName} ${suffix}`,
        price: Math.max(499, price),
        competitor: comp,
        timestamp: new Date().toISOString(),
        volatility,
        isNew,
      };
    });
  });
};
