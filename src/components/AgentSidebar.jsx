import React from 'react';
import { AlertCircle, TrendingUp, Zap } from 'lucide-react';

/**
 * AgentSidebar – right-hand sidebar with agent status & trending items.
 */
export default function AgentSidebar({ shopName, selectedDomain, isScanning, scrapedData, marketShare }) {
  const trending = scrapedData.filter((d) => d.volatility > 8).slice(0, 3);

  return (
    <div className="sidebar">
      {/* Agent Status Card */}
      <div className="card card-padded">
        <div className="sidebar-header">
          <h3 className="sidebar-section-title">Agent Intelligence</h3>
          <div className={`status-dot ${isScanning ? 'status-dot--scanning' : 'status-dot--idle'}`} />
        </div>
        <div className="sidebar-info-list">
          <div className="sidebar-info-row">
            <AlertCircle size={16} className="icon-blue" />
            <div>
              <p className="sidebar-info-label">Status</p>
              <p className="sidebar-info-value">
                {isScanning ? 'Agent is currently scanning Amazon.in & Flipkart...' : 'Idle. Waiting for next cycle (45m).'}
              </p>
            </div>
          </div>
          <div className="sidebar-info-row">
            <TrendingUp size={16} className="icon-purple" />
            <div>
              <p className="sidebar-info-label">Domain Focus</p>
              <p className="sidebar-info-value italic">
                {selectedDomain?.id === 'custom' 
                  ? `"Custom domain: analyzing your niche across web retailers"`
                  : `"Targeting ${selectedDomain?.name} keywords across 5 retailers"`}
              </p>
            </div>
          </div>
        </div>
        <div className="whisper-box">
          <p className="whisper-label">Smart Whisper</p>
          <p className="whisper-text">
            "Hey {shopName.split(' ')[0]}, prices on {marketShare[0]?.[0]} are falling. Ready to match?"
          </p>
        </div>
      </div>

      {/* Trending Now Card */}
      <div className="card card-padded">
        <h3 className="card-title">
          <Zap size={16} className="icon-amber-fill" /> Trending Now
        </h3>
        <div className="trending-list">
          {trending.map((item) => (
            <div key={item.id} className="trending-row">
              <div className="trending-avatar">{item.name.charAt(0)}</div>
              <div className="trending-info">
                <p className="trending-name">{item.name}</p>
                <p className="trending-sub">Seen on {item.competitor}</p>
              </div>
              <div className="trending-price">₹{item.price.toLocaleString('en-IN')}</div>
            </div>
          ))}
        </div>
        <button className="view-report-btn">View Full Market Report</button>
      </div>
    </div>
  );
}
