import React from 'react';
import { ArrowDown } from 'lucide-react';

/**
 * DropsTab – shows products where a competitor has the lowest price vs. average.
 */
export default function DropsTab({ priceDrops }) {
  if (priceDrops.length === 0) {
    return (
      <div className="card card-padded" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
        <h3 className="card-title" style={{ justifyContent: 'center', marginBottom: '1rem' }}>
          <ArrowDown size={20} className="icon-blue" /> Price Drops
        </h3>
        <p style={{ color: 'var(--color-text-muted)', fontSize: '1rem' }}>
          No significant price drops detected in this scan. All competitors are priced within normal range.
        </p>
      </div>
    );
  }

  return (
    <div className="tab-content-space">
      <div className="drop-header-info">
        <h3 className="card-title">
          <ArrowDown size={20} className="icon-blue" /> Best Prices Found
        </h3>
        <p className="drop-header-desc">
          Products where a competitor is offering significantly lower prices than the market average.
        </p>
      </div>
      {priceDrops.map((item) => (
        <div key={item.id} className="drop-card">
          <div className="drop-card-left">
            <div className="drop-icon-box">
              <ArrowDown size={24} />
            </div>
            <div>
              <h4 className="drop-name">{item.name}</h4>
              <p className="drop-competitor">
                Cheapest on <span className="fw-bold">{item.competitor}</span>
              </p>
            </div>
          </div>
          <div className="drop-card-right">
            <p className="drop-old-price">Avg: ₹{item.oldPrice.toLocaleString('en-IN')}</p>
            <p className="drop-new-price">₹{item.price.toLocaleString('en-IN')}</p>
            <span className="drop-badge">-{item.dropPercent}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}
