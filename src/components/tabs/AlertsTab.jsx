import React from 'react';
import { Bell, Package, Percent, TrendingUp, AlertCircle, ArrowRight, ExternalLink, Sparkles, Search } from 'lucide-react';

/**
 * AlertsTab – specialized view for urgent retail notifications and strategic actions.
 */
export default function AlertsTab({ alerts = [] }) {
  const [expandedAlert, setExpandedAlert] = React.useState(null);

  const getAlertIcon = (iconName) => {
    switch (iconName) {
      case 'package': return <Package size={20} />;
      case 'percent': return <Percent size={20} />;
      case 'trending': return <TrendingUp size={20} />;
      default: return <Bell size={20} />;
    }
  };

  const getPriorityClass = (type) => {
    switch (type) {
      case 'urgent': return 'alert-card--urgent';
      case 'warning': return 'alert-card--warning';
      default: return 'alert-card--info';
    }
  };

  const toggleExpand = (id) => {
    setExpandedAlert(expandedAlert === id ? null : id);
  };

  if (alerts.length === 0) {
    return (
      <div className="empty-state-container">
        <div className="empty-state-icon">
          <Bell size={48} />
        </div>
        <h3 className="empty-state-title">No Urgent Alerts</h3>
        <p className="empty-state-text">Everything is running smoothly. Your market intelligence agent will notify you as soon as strategic actions are identified.</p>
      </div>
    );
  }

  return (
    <div className="alerts-tab-container">
      <header className="alerts-header">
        <div className="alerts-title-group">
          <h2 className="tab-section-title">Urgent Intelligence</h2>
          <p className="tab-section-subtitle">Prioritized actions based on market demand and inventory levels.</p>
        </div>
      </header>

      <div className="alerts-grid">
        {alerts.map((alert) => {
          const isExpanded = expandedAlert === alert.id;
          return (
            <div key={alert.id} className={`alert-card ${getPriorityClass(alert.type)} animate-fade-in ${isExpanded ? 'alert-card--expanded' : ''}`}>
              <div className={`alert-badge alert-badge--${alert.type}`}>
                {alert.type === 'urgent' && <AlertCircle size={12} />}
                {alert.type.toUpperCase()}
              </div>
              
              <div className="alert-content">
                <div className="alert-icon-wrapper">
                  {getAlertIcon(alert.icon)}
                </div>
                <div className="alert-body">
                  <h3 className="alert-title">{alert.title}</h3>
                  <p className="alert-message">{alert.message}</p>
                  
                  <div className="alert-footer">
                    <button className="alert-action-btn" onClick={() => toggleExpand(alert.id)}>
                      {isExpanded ? 'Close Detail' : 'Analyze Strategy'} <ArrowRight size={14} className={isExpanded ? 'rotate-90' : ''} />
                    </button>
                    {alert.action && (
                      <button className="alert-details-link">
                        {alert.action} <ExternalLink size={14} />
                      </button>
                    )}
                  </div>

                  {isExpanded && alert.details && (
                    <div className="alert-strategy-detail animate-slide-down">
                      <div className="strategy-divider"></div>
                      <div className="strategy-section">
                        <h4 className="strategy-label"><Sparkles size={14} /> Strategic Rationale</h4>
                        <p className="strategy-text">{alert.details.rationale}</p>
                      </div>
                      <div className="strategy-section">
                        <h4 className="strategy-label"><TrendingUp size={14} /> Market Recommendation</h4>
                        <p className="strategy-text">{alert.details.recommendation}</p>
                      </div>
                      <div className="strategy-section">
                        <h4 className="strategy-label"><Search size={14} /> Competitor Signal</h4>
                        <p className="strategy-text">{alert.details.marketSignal}</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="alerts-footer-info">
        <AlertCircle size={16} />
        <span>Alerts are generated autonomously by analyzing 5+ competitive signals including Amazon, Flipkart, and Croma.</span>
      </div>
    </div>
  );
}
