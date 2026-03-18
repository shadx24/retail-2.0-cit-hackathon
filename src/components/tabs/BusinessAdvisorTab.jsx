import React, { useState, useEffect, useRef } from 'react';
import { Send, Briefcase, User, Sparkles, TrendingUp, Package, Percent } from 'lucide-react';

/**
 * BusinessAdvisorTab – Strategic AI interface for retail insights.
 * Connects to NVIDIA Kimi K2 LLM via /api/chat for real-time business advice.
 */
export default function BusinessAdvisorTab({ scrapedData, shopName, shopId }) {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: 'agent',
      text: `Hello, ${shopName}! I'm your AI Business Strategist powered by real-time market intelligence. I have access to ${scrapedData?.length || 0} live competitor data points. Ask me anything about pricing strategy, inventory, market trends, or competitive analysis.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);

  /**
   * Lightweight markdown → HTML renderer for chat bubbles.
   * Handles: **bold**, *italic*, `code`, bullet lists (- / •), numbered lists, \n
   */
  const renderMarkdown = (text) => {
    if (!text) return null;

    // Split into lines
    const lines = text.split('\n');
    const elements = [];
    let listItems = [];
    let listType = null; // 'ul' or 'ol'

    const flushList = () => {
      if (listItems.length > 0) {
        const Tag = listType === 'ol' ? 'ol' : 'ul';
        elements.push(
          <Tag key={`list-${elements.length}`} className="chat-md-list">
            {listItems.map((item, i) => (
              <li key={i}>{parseInline(item)}</li>
            ))}
          </Tag>
        );
        listItems = [];
        listType = null;
      }
    };

    const parseInline = (line) => {
      // Process inline markdown: **bold**, *italic*, `code`
      const parts = [];
      let remaining = line;
      let key = 0;

      while (remaining.length > 0) {
        // Bold: **text**
        const boldMatch = remaining.match(/\*\*(.+?)\*\*/);
        // Italic: *text*
        const italicMatch = remaining.match(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/);
        // Code: `text`
        const codeMatch = remaining.match(/`(.+?)`/);

        // Find earliest match
        const matches = [
          boldMatch ? { type: 'bold', match: boldMatch, idx: boldMatch.index } : null,
          italicMatch ? { type: 'italic', match: italicMatch, idx: italicMatch.index } : null,
          codeMatch ? { type: 'code', match: codeMatch, idx: codeMatch.index } : null,
        ].filter(Boolean).sort((a, b) => a.idx - b.idx);

        if (matches.length === 0) {
          parts.push(<span key={key++}>{remaining}</span>);
          break;
        }

        const first = matches[0];
        // Text before match
        if (first.idx > 0) {
          parts.push(<span key={key++}>{remaining.slice(0, first.idx)}</span>);
        }

        const innerText = first.match[1];
        if (first.type === 'bold') {
          parts.push(<strong key={key++}>{innerText}</strong>);
        } else if (first.type === 'italic') {
          parts.push(<em key={key++}>{innerText}</em>);
        } else if (first.type === 'code') {
          parts.push(<code key={key++} className="chat-md-code">{innerText}</code>);
        }

        remaining = remaining.slice(first.idx + first.match[0].length);
      }

      return parts;
    };

    lines.forEach((line, lineIdx) => {
      const trimmed = line.trim();

      // Blank line → flush list + add spacing
      if (!trimmed) {
        flushList();
        elements.push(<div key={`br-${lineIdx}`} className="chat-md-break" />);
        return;
      }

      // Unordered list: - item, • item, * item (but not **bold**)
      const ulMatch = trimmed.match(/^[-•]\s+(.+)/);
      const starListMatch = !trimmed.startsWith('**') && trimmed.match(/^\*\s+(.+)/);
      if (ulMatch || starListMatch) {
        if (listType === 'ol') flushList();
        listType = 'ul';
        listItems.push((ulMatch || starListMatch)[1]);
        return;
      }

      // Ordered list: 1. item, 2) item
      const olMatch = trimmed.match(/^\d+[.)]\s+(.+)/);
      if (olMatch) {
        if (listType === 'ul') flushList();
        listType = 'ol';
        listItems.push(olMatch[1]);
        return;
      }

      // Regular paragraph
      flushList();
      elements.push(
        <p key={`p-${lineIdx}`} className="chat-md-p">{parseInline(trimmed)}</p>
      );
    });

    flushList();
    return elements;
  };

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const sendMessage = async (text) => {
    if (!text.trim()) return;

    const userMsg = {
      id: Date.now(),
      role: 'user',
      text: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMsg]);
    setIsTyping(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          shopId: shopId || 0,
          shopName: shopName || 'Shop',
          history: messages.slice(-6).map(m => ({ role: m.role, text: m.text })),
        }),
      });

      let responseText;
      if (res.ok) {
        const data = await res.json();
        responseText = data.response || "I couldn't generate a response. Please try again.";
      } else {
        responseText = "I'm having trouble connecting to my analysis engine. Please try again in a moment.";
      }

      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'agent',
        text: responseText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }]);
    } catch (err) {
      console.error('Chat error:', err);
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'agent',
        text: "Connection error. Please check that the server is running and try again.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }]);
    }

    setIsTyping(false);
  };

  const handleSend = (e) => {
    e.preventDefault();
    sendMessage(input);
    setInput('');
  };

  const quickActions = [
    { label: 'Inventory Analysis', icon: <Package size={14} />, query: 'Analyze my inventory and stock levels' },
    { label: 'Pricing Strategy', icon: <Percent size={14} />, query: 'What is our best pricing move now?' },
    { label: 'Demand Forecast', icon: <TrendingUp size={14} />, query: 'Which items are in high demand?' },
  ];

  return (
    <div className="chat-tab-container">
      <div className="chat-header">
        <div className="chat-header-info">
          <div className="chat-avatar-main advisor-avatar">
            <Briefcase size={22} />
            <div className="chat-online-dot"></div>
          </div>
          <div>
            <h3 className="chat-header-title">Senior Business Advisor</h3>
            <p className="chat-header-status">Consultation Active • Strategic Mode</p>
          </div>
        </div>
        <div className="chat-header-actions">
          <Sparkles size={18} className="icon-amber-fill" />
        </div>
      </div>

      <div className="chat-messages" ref={scrollRef}>
        <div className="advisor-welcome-cards">
          {quickActions.map(action => (
            <button key={action.label} className="quick-action-card" onClick={() => { sendMessage(action.query); }}>
              <span className="quick-action-icon">{action.icon}</span>
              <span className="quick-action-label">{action.label}</span>
            </button>
          ))}
        </div>

        {messages.map((msg) => (
          <div key={msg.id} className={`chat-bubble-row ${msg.role === 'user' ? 'chat-bubble-row--user' : ''}`}>
            {msg.role === 'agent' && (
              <div className="chat-mini-avatar advisor-mini">
                <Briefcase size={12} />
              </div>
            )}
            <div className={`chat-bubble ${msg.role === 'user' ? 'chat-bubble--user' : 'chat-bubble--agent advisor-bubble'}`}>
              <div className="chat-bubble-text">
                {msg.role === 'agent' ? renderMarkdown(msg.text) : msg.text}
              </div>
              <span className="chat-bubble-time">{msg.timestamp}</span>
            </div>
          </div>
        ))}
        
        {isTyping && (
          <div className="chat-bubble-row">
            <div className="chat-mini-avatar advisor-mini">
              <Briefcase size={12} />
            </div>
            <div className="chat-bubble chat-bubble--agent">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}
      </div>

      <form className="chat-input-area" onSubmit={handleSend}>
        <input
          type="text"
          placeholder="Ask for business advice..."
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="chat-send-btn advisor-send" disabled={!input.trim() || isTyping}>
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
