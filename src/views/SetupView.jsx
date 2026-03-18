import React from 'react';
import { Zap } from 'lucide-react';
import { DOMAINS } from '../data/constants';

/**
 * SetupView – the onboarding screen where users enter shop name and domain.
 */
export default function SetupView({ 
  shopName, 
  setShopName, 
  selectedDomain, 
  setSelectedDomain, 
  customDescription,
  setCustomDescription,
  onStart 
}) {
  const isCustom = selectedDomain?.id === 'custom';

  return (
    <div className="setup-container">
      <div className="setup-card">
        <div className="setup-header">
          <div className="setup-icon">
            <Zap size={32} />
          </div>
          <h1 className="setup-title">Retail PriceGuard</h1>
          <p className="setup-subtitle">Your autonomous market intelligence agent.</p>
        </div>

        <div className="setup-form">
          <div className="form-group">
            <label className="form-label">Domain of Expertise</label>
            <div className="domain-grid">
              {DOMAINS.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDomain(d)}
                  className={`domain-button ${selectedDomain?.id === d.id ? 'domain-button--active' : ''}`}
                >
                  <span className="domain-icon">{d.icon}</span>
                  <span className="domain-name">{d.name}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">{isCustom ? 'Custom Retail Name' : 'Shop Name'}</label>
            <input
              type="text"
              placeholder={isCustom ? "e.g. My Specialty Store" : "e.g. Nithya's Tech Hub"}
              className="form-input"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
            />
          </div>

          {isCustom && (
            <div className="form-group animate-fade-in">
              <label className="form-label">Describe the retail idea</label>
              <textarea
                placeholder="e.g. A store focused on vintage mechanical keyboards and artisan keycaps, selling brands like Keychron, HHKB, and GMK keycap sets..."
                className="form-input form-textarea"
                value={customDescription}
                onChange={(e) => setCustomDescription(e.target.value)}
                rows={4}
              />
              <p style={{ fontSize: '0.75rem', color: '#8b8fa3', marginTop: '0.5rem' }}>
                Be specific — our AI will find real products, competitors, and prices for your niche from the web.
              </p>
            </div>
          )}

          <button
            disabled={!shopName || !selectedDomain || (isCustom && !customDescription)}
            onClick={onStart}
            className="setup-submit"
          >
            {isCustom ? 'Initialize Custom Agent' : 'Deploy My Agent'}
          </button>
        </div>
      </div>
    </div>
  );
}
