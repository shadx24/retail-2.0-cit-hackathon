import React from 'react';

/**
 * RadarTab – shows emerging/newly spotted products.
 */
export default function RadarTab({ emergingProducts }) {
  return (
    <div className="tab-content-space">
      <div className="radar-hero">
        <h3 className="radar-hero-title">Emerging Product Radar</h3>
        <p className="radar-hero-desc">These items were first seen on the web in the last 24 hours. Stock them before they go viral!</p>
      </div>
      <div className="radar-grid">
        {emergingProducts.map((item) => (
          <div key={item.id} className="radar-card">
            <div className="radar-hot-badge">HOT</div>
            <h4 className="radar-card-name">{item.name}</h4>
            <div className="radar-card-footer">
              <div>
                <p className="radar-label">Spotted On</p>
                <p className="radar-value">{item.competitor}</p>
              </div>
              <div className="radar-price">₹{item.price.toLocaleString('en-IN')}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
