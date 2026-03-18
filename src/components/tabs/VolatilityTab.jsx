import React, { useMemo } from 'react';
import { AlertTriangle, Eye, CheckCircle, TrendingUp } from 'lucide-react';

/**
 * PriceActivityTab – groups products into three volatility zones.
 */
export default function PriceActivityTab({ scrapedData }) {
  const zones = useMemo(() => {
    const action = [];
    const watch = [];
    const stable = [];

    scrapedData.forEach((item) => {
      const v = parseFloat(item.volatility);
      if (v > 7) action.push(item);
      else if (v > 4) watch.push(item);
      else stable.push(item);
    });

    // Sort each zone by volatility descending
    action.sort((a, b) => b.volatility - a.volatility);
    watch.sort((a, b) => b.volatility - a.volatility);
    stable.sort((a, b) => b.volatility - a.volatility);

    return { action, watch, stable };
  }, [scrapedData]);

  return (
    <div className="card card-padded">
      <h3 className="card-title">
        <TrendingUp size={22} className="icon-purple" /> Price Activity Zones
      </h3>
      <p className="price-activity-desc">
        We've grouped products based on how often competitors change their prices. Focus on the red zone first to stay competitive.
      </p>

      <div className="zones-grid">
        {/* Action Needed Zone */}
        <div className="zone zone--danger">
          <div className="zone-header">
            <h4 className="zone-title zone-title--danger">
              <AlertTriangle size={18} /> Action Needed
            </h4>
            <p className="zone-desc">Competitors are actively changing prices for these items right now.</p>
          </div>
          <div className="zone-card-list">
            {zones.action.length > 0 ? (
              zones.action.map((item) => (
                <div key={item.id} className="zone-card zone-card--danger">
                  <div className="zone-card-name">{item.name}</div>
                  <div className="zone-card-footer">
                    <span className="zone-card-competitor">{item.competitor}</span>
                    <span className="zone-card-price zone-card-price--danger">₹{item.price.toLocaleString('en-IN')}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="zone-empty">No items in this zone</p>
            )}
          </div>
        </div>

        {/* Keep an Eye Zone */}
        <div className="zone zone--warn">
          <div className="zone-header">
            <h4 className="zone-title zone-title--warn">
              <Eye size={18} /> Keep an Eye
            </h4>
            <p className="zone-desc">Prices shift occasionally. Good to review before restocking.</p>
          </div>
          <div className="zone-card-list">
            {zones.watch.length > 0 ? (
              zones.watch.map((item) => (
                <div key={item.id} className="zone-card zone-card--warn">
                  <div className="zone-card-name">{item.name}</div>
                  <div className="zone-card-footer">
                    <span className="zone-card-competitor">{item.competitor}</span>
                    <span className="zone-card-price zone-card-price--warn">₹{item.price.toLocaleString('en-IN')}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="zone-empty">No items in this zone</p>
            )}
          </div>
        </div>

        {/* Stable Prices Zone */}
        <div className="zone zone--safe">
          <div className="zone-header">
            <h4 className="zone-title zone-title--safe">
              <CheckCircle size={20} /> Stable Prices
            </h4>
            <p className="zone-desc">Prices rarely change here. You are generally safe.</p>
          </div>
          <div className="zone-card-list">
            {zones.stable.length > 0 ? (
              zones.stable.map((item) => (
                <div key={item.id} className="zone-card zone-card--safe">
                  <div className="zone-card-name">{item.name}</div>
                  <div className="zone-card-footer">
                    <span className="zone-card-competitor">{item.competitor}</span>
                    <span className="zone-card-price zone-card-price--safe">₹{item.price.toLocaleString('en-IN')}</span>
                  </div>
                </div>
              ))
            ) : (
              <p className="zone-empty">No items in this zone</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
