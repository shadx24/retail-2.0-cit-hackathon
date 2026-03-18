import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Package, Plus, ExternalLink, Search, X, Trash2, Edit3, Save, ShoppingCart, Upload, CheckCircle } from 'lucide-react';

const API_BASE = '/api';

/** Parse CSV text into preview items (local only, not yet saved). */
function parseCSV(text) {
  return text.trim().split('\n').map((line, i) => {
    const cleaned = line.trim().replace(/,\s*$/, '');
    if (!cleaned) return null;
    const parts = cleaned.split(',').map(p => p.trim().replace(/^"|"$/g, '').replace(/^'|'$/g, ''));
    const name = parts[0] || '';
    const qty = parseInt(parts[1], 10) || 0;
    const url = (parts[2] || '').trim();
    if (!name) return null;
    return { _localId: `preview-${Date.now()}-${i}`, product_name: name, quantity: qty, product_url: url, price: 0, isPreview: true };
  }).filter(Boolean);
}

/**
 * OverviewTab – table of all scanned products with search + inventory management.
 */
export default function OverviewTab({ scrapedData, shopId, inventory, setInventory }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [showInventory, setShowInventory] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [previewItems, setPreviewItems] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editQty, setEditQty] = useState('');

  // Combined view: saved items + unsaved preview items
  const displayItems = useMemo(() => [
    ...previewItems,
    ...inventory,
  ], [inventory, previewItems]);

  const filteredData = useMemo(() => {
    if (!searchQuery.trim()) return scrapedData;
    const q = searchQuery.toLowerCase();
    return scrapedData.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.competitor.toLowerCase().includes(q)
    );
  }, [scrapedData, searchQuery]);

  // Fetch inventory when panel opens
  const fetchInventory = useCallback(async () => {
    if (!shopId) return;
    try {
      const res = await fetch(`${API_BASE}/inventory/${shopId}`);
      if (res.ok) {
        const data = await res.json();
        setInventory(data);
      }
    } catch (err) {
      console.error('Fetch inventory failed:', err);
    }
  }, [shopId, setInventory]);

  useEffect(() => {
    if (showInventory && shopId) fetchInventory();
  }, [showInventory, shopId, fetchInventory]);

  // Step 1: Parse CSV → show in table as preview (no DB call)
  const handleParseCSV = () => {
    if (!csvText.trim()) return;
    const parsed = parseCSV(csvText);
    setPreviewItems(prev => [...parsed, ...prev]);
    setCsvText('');
  };

  // Remove a preview item before saving
  const removePreview = (localId) => {
    setPreviewItems(prev => prev.filter(p => p._localId !== localId));
  };

  // Step 2: Save all preview items to DB
  const handleSaveAll = async () => {
    if (!previewItems.length || !shopId) return;
    setIsSaving(true);
    try {
      const csvLines = previewItems.map(p =>
        `${p.product_name},${p.quantity}${p.product_url ? ',' + p.product_url : ''}`
      ).join('\n');
      const res = await fetch(`${API_BASE}/inventory/${shopId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_text: csvLines, items: [] }),
      });
      if (res.ok) {
        setPreviewItems([]);
        await fetchInventory();
      }
    } catch (err) {
      console.error('Save inventory failed:', err);
    }
    setIsSaving(false);
  };

  // Update quantity (saved items)
  const handleUpdateQty = async (itemId) => {
    const qty = parseInt(editQty, 10);
    if (isNaN(qty) || qty < 0) return;
    try {
      await fetch(`${API_BASE}/inventory/${shopId}/${itemId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quantity: qty }),
      });
      setEditingId(null);
      setEditQty('');
      await fetchInventory();
    } catch (err) {
      console.error('Update failed:', err);
    }
  };

  // Delete item (saved items)
  const handleDelete = async (itemId) => {
    try {
      await fetch(`${API_BASE}/inventory/${shopId}/${itemId}`, { method: 'DELETE' });
      await fetchInventory();
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">
          <Package size={20} className="icon-blue" /> Scanned Products
        </h3>
        <button className="link-btn" onClick={() => setShowInventory(!showInventory)}>
          {showInventory ? <><X size={16} /> Close Inventory</> : <><Plus size={16} /> Add My Inventory</>}
        </button>
      </div>

      {/* ─── INVENTORY PANEL (light theme) ─── */}
      {showInventory && (
        <div className="inventory-panel">
          <div className="inventory-panel-header">
            <h4 className="inventory-panel-title">
              <ShoppingCart size={18} /> My Inventory
            </h4>
            <span className="inventory-count">
              {inventory.length} saved{previewItems.length > 0 ? ` · ${previewItems.length} unsaved` : ''}
            </span>
          </div>

          {/* CSV Input */}
          <div className="inventory-add-section">
            <label className="inventory-label">
              <Upload size={14} /> Paste products (one per line):
              <span className="inventory-hint">Format: Product Name, Quantity, URL (optional)</span>
            </label>
            <textarea
              className="inventory-textarea"
              placeholder={"iPhone 16 Pro, 25\nSamsung S24, 10, https://amazon.in/...\nSony WH-1000XM5, 8"}
              rows={4}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
            />
            <div className="inventory-btn-row">
              <button
                className="inventory-add-btn"
                onClick={handleParseCSV}
                disabled={!csvText.trim()}
              >
                <Plus size={14} /> Add to Table
              </button>
              {previewItems.length > 0 && (
                <button
                  className="inventory-save-btn"
                  onClick={handleSaveAll}
                  disabled={isSaving}
                >
                  <CheckCircle size={14} /> {isSaving ? 'Saving...' : `Save ${previewItems.length} Item${previewItems.length !== 1 ? 's' : ''}`}
                </button>
              )}
            </div>
          </div>

          {/* Inventory Table — shows preview + saved items */}
          {displayItems.length > 0 && (
            <div className="table-wrapper inventory-table-wrapper">
              <table className="data-table inventory-table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {displayItems.map((item) => {
                    const key = item.isPreview ? item._localId : item.id;
                    return (
                      <tr key={key} className={item.isPreview ? 'inventory-row--preview' : ''}>
                        <td className="cell-product">
                          {item.isPreview && <span className="preview-dot" title="Unsaved" />}
                          {item.product_name}
                          {item.product_url && (
                            <a href={item.product_url} target="_blank" rel="noopener noreferrer" className="inventory-link">
                              <ExternalLink size={12} />
                            </a>
                          )}
                        </td>
                        <td className="cell-qty">
                          {!item.isPreview && editingId === item.id ? (
                            <div className="qty-edit-group">
                              <input
                                type="number"
                                className="qty-input"
                                value={editQty}
                                onChange={(e) => setEditQty(e.target.value)}
                                min="0"
                                autoFocus
                              />
                              <button className="icon-btn icon-btn--save" onClick={() => handleUpdateQty(item.id)}>
                                <Save size={14} />
                              </button>
                            </div>
                          ) : (
                            <span className={`qty-badge ${item.quantity < 10 ? 'qty-low' : ''}`}>
                              {item.quantity}
                            </span>
                          )}
                        </td>
                        <td className="cell-price">
                          {item.price > 0 ? `₹${Number(item.price).toLocaleString('en-IN')}` : '—'}
                        </td>
                        <td className="cell-actions">
                          {item.isPreview ? (
                            <button
                              className="icon-btn icon-btn--danger"
                              title="Remove"
                              onClick={() => removePreview(item._localId)}
                            >
                              <X size={14} />
                            </button>
                          ) : (
                            <>
                              <button
                                className="icon-btn"
                                title="Edit quantity"
                                onClick={() => {
                                  setEditingId(item.id);
                                  setEditQty(String(item.quantity));
                                }}
                              >
                                <Edit3 size={14} />
                              </button>
                              <button
                                className="icon-btn icon-btn--danger"
                                title="Delete"
                                onClick={() => handleDelete(item.id)}
                              >
                                <Trash2 size={14} />
                              </button>
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {displayItems.length === 0 && (
            <p className="inventory-empty">No inventory yet. Paste products above to get started.</p>
          )}
        </div>
      )}

      {/* Search Bar */}
      <div className="search-bar-wrapper">
        <div className="search-input-container">
          <Search size={20} className="search-icon" />
          <input
            type="text"
            placeholder="Search products, competitors..."
            className="search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <span className="search-result-count">
              {filteredData.length} result{filteredData.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>

      <div className="table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>Product Name</th>
              <th>Competitor</th>
              <th>Price</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredData.length > 0 ? (
              filteredData.map((item) => (
                <tr key={item.id}>
                  <td className="cell-product">{item.name}</td>
                  <td>
                    <span className="competitor-badge">{item.competitor}</span>
                  </td>
                  <td className="cell-price">₹{item.price.toLocaleString('en-IN')}</td>
                  <td>
                    <button className="icon-btn">
                      <ExternalLink size={16} />
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="4" className="search-empty">
                  No products found matching "<strong>{searchQuery}</strong>"
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
