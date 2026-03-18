import React from 'react';
import { useDashboard } from './hooks/useDashboard';
import SetupView from './views/SetupView';
import DashboardView from './views/DashboardView';

/**
 * RETAIL PRICEGUARD - AUTONOMOUS COMPETITOR MONITORING
 * Root App component that delegates to SetupView or DashboardView.
 */
const App = () => {
  const dashboard = useDashboard();

  return (
    <div className="app-root">
      {dashboard.step === 'setup' ? (
        <SetupView
          shopName={dashboard.shopName}
          setShopName={dashboard.setShopName}
          selectedDomain={dashboard.selectedDomain}
          setSelectedDomain={dashboard.setSelectedDomain}
          customDescription={dashboard.customDescription}
          setCustomDescription={dashboard.setCustomDescription}
          onStart={dashboard.handleStartSetup}
        />
      ) : (
        <DashboardView
          shopName={dashboard.shopName}
          selectedDomain={dashboard.selectedDomain}
          isScanning={dashboard.isScanning}
          lastScan={dashboard.lastScan}
          scrapedData={dashboard.scrapedData}
          activeTab={dashboard.activeTab}
          setActiveTab={dashboard.setActiveTab}
          runScan={dashboard.runScan}
          emergingProducts={dashboard.emergingProducts}
          priceDrops={dashboard.priceDrops}
          marketShare={dashboard.marketShare}
          alerts={dashboard.alerts}
          shopId={dashboard.shopId}
          inventory={dashboard.inventory}
          setInventory={dashboard.setInventory}
        />
      )}
    </div>
  );
};

export default App;
