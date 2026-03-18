import React from 'react';
import { Map } from 'lucide-react';

/**
 * MarketMapTab – competitor coverage breakdown.
 */
export default function MarketMapTab({ marketShare }) {
  return (
    <div className="card card-padded">
      <h3 className="card-title">
        <Map size={20} className="icon-pink" /> Competitor Coverage Map
      </h3>
      <div className="market-grid">
        {marketShare.map(([comp, count], idx) => (
          <div key={comp} className="market-card">
            <p className="market-comp-name">{comp}</p>
            <p className="market-count">{count}</p>
            <p className="market-label">Total Listings Found</p>
            <div className="market-indicator">
              <div className={`market-dot ${idx === 0 ? 'market-dot--leader' : ''}`} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
