import React from 'react';
import { Zap, RefreshCcw, Settings, BarChart3, Search, TrendingUp, ArrowDown, Briefcase, Bell, Store } from 'lucide-react';
import OverviewTab from '../components/tabs/OverviewTab';
import RadarTab from '../components/tabs/RadarTab';
import VolatilityTab from '../components/tabs/VolatilityTab';
import DropsTab from '../components/tabs/DropsTab';
import BusinessAdvisorTab from '../components/tabs/BusinessAdvisorTab';
import AlertsTab from '../components/tabs/AlertsTab';
import AgentSidebar from '../components/AgentSidebar';

const TABS = [
  { id: 'overview', label: 'Overview', icon: <BarChart3 size={16} /> },
  { id: 'radar', label: 'Radar', icon: <Search size={16} /> },
  { id: 'volatility', label: 'Price Activity', icon: <TrendingUp size={16} /> },
  { id: 'drops', label: 'Price Drops', icon: <ArrowDown size={16} /> },
  { id: 'advisor', label: 'Advisor', icon: <Briefcase size={16} /> },
  { id: 'alerts', label: 'Alerts', icon: <Bell size={16} /> },
];

/**
 * DashboardView – the main dashboard after setup.
 */
export default function DashboardView({
  shopName,
  selectedDomain,
  isScanning,
  lastScan,
  scrapedData,
  activeTab,
  setActiveTab,
  runScan,
  emergingProducts,
  priceDrops,
  marketShare,
  alerts,
  shopId,
  inventory,
  setInventory,
}) {
  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return <OverviewTab scrapedData={scrapedData} shopId={shopId} inventory={inventory} setInventory={setInventory} />;
      case 'radar':
        return <RadarTab emergingProducts={emergingProducts} />;
      case 'volatility':
        return <VolatilityTab scrapedData={scrapedData} />;
      case 'drops':
        return <DropsTab priceDrops={priceDrops} />;
      case 'advisor':
        return <BusinessAdvisorTab scrapedData={scrapedData} shopName={shopName} shopId={shopId} />;
      case 'alerts':
        return <AlertsTab alerts={alerts} />;
      default:
        return null;
    }
  };

  return (
    <div className="dashboard">
      {/* Top Navigation Bar */}
      <nav className="topbar">
        <div className="topbar-left">
          <Zap className="topbar-logo-icon" size={24} />
          <h1 className="topbar-title">{shopName}</h1>
          <span className="topbar-badge">LIVE AGENT</span>
        </div>
        <div className="topbar-right">
          <div className="topbar-scan-info">
            <p className="topbar-scan-label">Last Scanned</p>
            <p className="topbar-scan-time">{lastScan || 'Initializing...'}</p>
          </div>
          <button onClick={runScan} disabled={isScanning} className={`topbar-btn ${isScanning ? 'spinning' : ''}`}>
            <RefreshCcw size={18} />
          </button>
          <div className="topbar-settings">
            <Settings size={16} />
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="dashboard-content">
        {/* Tab Switcher */}
        <div className="tab-bar">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`tab-button ${activeTab === tab.id ? 'tab-button--active' : ''}`}
            >
              <div className="tab-button-content">
                {tab.icon} {tab.label}
                {tab.id === 'alerts' && alerts.length > 0 && (
                  <span className="nav-badge nav-badge--desktop">{alerts.length}</span>
                )}
              </div>
            </button>
          ))}
        </div>

        {/* Grid: main content + sidebar */}
        <div className="dashboard-grid">
          <div className="dashboard-main">{renderTabContent()}</div>
          <AgentSidebar
            shopName={shopName}
            selectedDomain={selectedDomain}
            isScanning={isScanning}
            scrapedData={scrapedData}
            marketShare={marketShare}
          />
        </div>
      </div>

      {/* Mobile Bottom Nav */}
      <div className="mobile-nav">
        <button onClick={() => setActiveTab('overview')} className={`mobile-nav-btn ${activeTab === 'overview' ? 'mobile-nav-btn--active' : ''}`}>
          <BarChart3 size={20} />
        </button>
        <button onClick={() => setActiveTab('radar')} className={`mobile-nav-btn ${activeTab === 'radar' ? 'mobile-nav-btn--active' : ''}`}>
          <Search size={20} />
        </button>
        <button onClick={() => setActiveTab('drops')} className={`mobile-nav-btn ${activeTab === 'drops' ? 'mobile-nav-btn--active' : ''}`}>
          <ArrowDown size={20} />
        </button>
        <button onClick={() => setActiveTab('advisor')} className={`mobile-nav-btn ${activeTab === 'advisor' ? 'mobile-nav-btn--active' : ''}`}>
          <Briefcase size={20} />
        </button>
        <button onClick={() => setActiveTab('alerts')} className={`mobile-nav-btn ${activeTab === 'alerts' ? 'mobile-nav-btn--active' : ''} mobile-nav-btn--alerts`}>
          <Bell size={20} />
          {alerts.length > 0 && <span className="nav-badge nav-badge--mobile">{alerts.length}</span>}
        </button>
      </div>
    </div>
  );
}
