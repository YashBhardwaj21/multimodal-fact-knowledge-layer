import React, { useState, useEffect, useRef } from 'react';
import { 
  FileText, Upload, Search, MessageSquare, Database, Share2, 
  Settings, CheckCircle2, ChevronRight, ArrowLeft, Send, 
  ExternalLink, Layers, Table, Image, ShieldCheck, Sparkles, Plus,
  Bookmark, HelpCircle, HardDrive, RefreshCw, X, Folder, ChevronDown,
  Edit2, Trash2, MoreVertical
} from 'lucide-react';

export default function App() {
  // Navigation view: 'landing' | 'workspace'
  const [currentView, setCurrentView] = useState('landing');

  // Workspaces & Sessions
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState('');
  const [sessionData, setSessionData] = useState(null);
  const [storageQuota, setStorageQuota] = useState({ used_gb: 2.1, max_gb: 10.0, display_text: '2.1 GB of 10 GB', usage_percentage: 21 });
  const [showWorkspaceDropdown, setShowWorkspaceDropdown] = useState(false);
  const [contextMenu, setContextMenu] = useState(null); // { x, y, session }

  // Selected document & tab state
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [activeTab, setActiveTab] = useState('Chat'); // Chat | Key Facts | Tables | Figures | Structure | Reconciliation
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTagFilter, setSelectedTagFilter] = useState('');
  const [navSection, setNavSection] = useState('Documents'); // Documents | Ask | Knowledge Graph

  // Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const chatEndRef = useRef(null);

  // Upload modal state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const fileInputRef = useRef(null);
  const heroFileInputRef = useRef(null);

  // Extracted tables & figures
  const [sessionTables, setSessionTables] = useState([]);
  const [sessionFigures, setSessionFigures] = useState([]);
  const [sessionFacts, setSessionFacts] = useState([]);
  const [sessionComparisons, setSessionComparisons] = useState([]);

  // Close context menu & dropdown on outside click
  useEffect(() => {
    const handleGlobalClick = () => {
      setContextMenu(null);
      setShowWorkspaceDropdown(false);
    };
    window.addEventListener('click', handleGlobalClick);
    return () => window.removeEventListener('click', handleGlobalClick);
  }, []);

  // Load sessions on mount
  useEffect(() => {
    fetchSessions();
    fetchStorageQuota();
  }, []);

  // When session changes, load session details and assets
  useEffect(() => {
    if (currentSessionId) {
      loadSessionDetails(currentSessionId);
    }
  }, [currentSessionId]);

  // Auto scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  const fetchSessions = async () => {
    try {
      const res = await fetch('/api/sessions');
      const data = await res.json();
      setSessions(data);
      if (data.length > 0 && !currentSessionId) {
        setCurrentSessionId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  };

  const fetchStorageQuota = async () => {
    try {
      const res = await fetch('/api/storage/quota');
      const data = await res.json();
      setStorageQuota(data);
    } catch (err) {
      console.error('Failed to fetch storage quota:', err);
    }
  };

  const loadSessionDetails = async (sessionId, selectDocId = null) => {
    try {
      const res = await fetch(`/api/sessions/${sessionId}`);
      const data = await res.json();
      setSessionData(data);

      if (selectDocId && data.documents) {
        const target = data.documents.find(d => d.id === selectDocId);
        if (target) {
          setSelectedDoc(target);
        } else if (data.documents.length > 0) {
          setSelectedDoc(data.documents[0]);
        }
      } else if (data.documents && data.documents.length > 0) {
        setSelectedDoc(data.documents[0]);
      } else {
        setSelectedDoc(null);
      }

      // Populate chat history
      if (data.recent_messages && data.recent_messages.length > 0) {
        setChatMessages(data.recent_messages);
      } else {
        // Initial welcome chat
        setChatMessages([
          {
            id: 'welcome_1',
            role: 'assistant',
            content: `Welcome to **${data.title}**. You can ask questions about the documents uploaded in this workspace, inspect verified facts, or review cross-document reconciliations.`,
            citations: []
          }
        ]);
      }

      // Fetch facts, comparisons, tables, figures in parallel
      const [factsRes, compsRes, tablesRes, figsRes] = await Promise.all([
        fetch(`/api/sessions/${sessionId}/facts`).then(r => r.json()).catch(() => []),
        fetch(`/api/sessions/${sessionId}/comparisons`).then(r => r.json()).catch(() => []),
        fetch(`/api/sessions/${sessionId}/tables`).then(r => r.json()).catch(() => []),
        fetch(`/api/sessions/${sessionId}/figures`).then(r => r.json()).catch(() => [])
      ]);

      setSessionFacts(factsRes);
      setSessionComparisons(compsRes);
      setSessionTables(tablesRes);
      setSessionFigures(figsRes);
    } catch (err) {
      console.error('Failed to load session details:', err);
    }
  };

  const handleCreateSession = async (promptForTitle = true) => {
    let title = '';
    const defaultTitle = `Workspace ${sessions.length + 1}`;
    if (promptForTitle) {
      const input = prompt('Enter a title for the new workspace:', defaultTitle);
      if (input === null) return; // User cancelled
      title = input.trim() || defaultTitle;
    } else {
      title = defaultTitle;
    }

    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, description: 'Interactive document intelligence workspace.' })
      });
      const newSession = await res.json();
      await fetchSessions();
      setCurrentSessionId(newSession.id);
      setShowWorkspaceDropdown(false);
      setNavSection('Ask');
      setSelectedDoc(null);
    } catch (err) {
      alert('Failed to create workspace: ' + err.message);
    }
  };

  const handleRenameWorkspace = async (sessionToRename) => {
    setContextMenu(null);
    const newTitle = prompt('Enter a new name for this workspace:', sessionToRename.title);
    if (!newTitle || !newTitle.trim() || newTitle.trim() === sessionToRename.title) return;

    try {
      const res = await fetch(`/api/sessions/${sessionToRename.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to rename workspace');
      }

      await fetchSessions();
      if (currentSessionId === sessionToRename.id) {
        await loadSessionDetails(currentSessionId);
      }
    } catch (err) {
      alert('Error renaming workspace: ' + err.message);
    }
  };

  const handleDeleteWorkspace = async (sessionToDelete) => {
    setContextMenu(null);
    const confirmed = window.confirm(
      `Permanently delete workspace "${sessionToDelete.title}"?\n\nThis will completely purge all uploaded documents, vector indices, and database records with no records left.`
    );
    if (!confirmed) return;

    try {
      const res = await fetch(`/api/sessions/${sessionToDelete.id}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to delete workspace');
      }

      const updatedRes = await fetch('/api/sessions');
      const updatedSessions = await updatedRes.json();
      setSessions(updatedSessions);

      if (currentSessionId === sessionToDelete.id) {
        if (updatedSessions.length > 0) {
          setCurrentSessionId(updatedSessions[0].id);
        } else {
          setCurrentSessionId(null);
          setSessionData(null);
        }
      }
      await fetchStorageQuota();
    } catch (err) {
      alert('Error deleting workspace: ' + err.message);
    }
  };

  const handleWorkspaceContextMenu = (e, sessionItem) => {
    e.preventDefault();
    e.stopPropagation();
    const clickX = Math.min(e.clientX, window.innerWidth - 220);
    const clickY = Math.min(e.clientY, window.innerHeight - 150);
    setContextMenu({
      x: clickX,
      y: clickY,
      session: sessionItem
    });
  };

  const handleStartConversation = async () => {
    if (sessions.length > 0) {
      if (!currentSessionId) {
        setCurrentSessionId(sessions[0].id);
      }
      setCurrentView('workspace');
    } else {
      try {
        const res = await fetch('/api/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'Workspace 1', description: 'Interactive multimodal workspace.' })
        });
        if (res.ok) {
          const newSession = await res.json();
          await fetchSessions();
          setCurrentSessionId(newSession.id);
        }
      } catch (err) {
        console.error('Failed to create initial workspace:', err);
      }
      setCurrentView('workspace');
    }
  };

  const handleFileUpload = async (file) => {
    if (!file || !currentSessionId) return;
    setIsUploading(true);
    setUploadStatus(`Uploading & processing ${file.name}...`);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`/api/sessions/${currentSessionId}/documents`, {
        method: 'POST',
        body: formData
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || 'Upload failed');

      setUploadStatus(`Processed: ${result.pages} pages, ${result.blocks} blocks, ${result.tables} tables.`);
      await loadSessionDetails(currentSessionId, result.doc_id);
      await fetchStorageQuota();

      setTimeout(() => {
        setIsUploading(false);
        setUploadStatus('');
        setShowUploadModal(false);
      }, 1000);
    } catch (err) {
      setUploadStatus('Error: ' + err.message);
      setIsUploading(false);
    }
  };

  const handleSendMessage = async (queryText) => {
    const q = queryText || inputQuery;
    if (!q.trim() || isAsking || !currentSessionId) return;

    const userMsg = { id: `user_${Date.now()}`, role: 'user', content: q, citations: [] };
    setChatMessages(prev => [...prev, userMsg]);
    setInputQuery('');
    setIsAsking(true);

    try {
      const res = await fetch(`/api/sessions/${currentSessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query: q,
          document_name: selectedDoc?.filename,
          doc_id: selectedDoc?.doc_id
        })
      });
      const data = await res.json();

      const aiMsg = {
        id: `ai_${Date.now()}`,
        role: 'assistant',
        content: data.answer,
        citations: data.citations || []
      };
      setChatMessages(prev => [...prev, aiMsg]);
    } catch (err) {
      setChatMessages(prev => [
        ...prev,
        { id: `err_${Date.now()}`, role: 'assistant', content: 'Encountered error retrieving answer: ' + err.message, citations: [] }
      ]);
    } finally {
      setIsAsking(false);
    }
  };

  const allTags = Array.from(
    new Set((sessionData?.documents || []).flatMap(d => d.tags || []))
  );

  const filteredDocs = (sessionData?.documents || []).filter(d => {
    const query = searchQuery.toLowerCase();
    const matchesSearch = !searchQuery || 
      (d.title && d.title.toLowerCase().includes(query)) ||
      (d.summary && d.summary.toLowerCase().includes(query)) ||
      (d.tags && d.tags.some(t => t.toLowerCase().includes(query)));
    const matchesTag = !selectedTagFilter || (d.tags && d.tags.includes(selectedTagFilter));
    return matchesSearch && matchesTag;
  });

  const docFacts = selectedDoc
    ? sessionFacts.filter(f => !f.evidence?.document_name || f.evidence?.document_name === selectedDoc.filename)
    : sessionFacts;

  const docTables = selectedDoc
    ? sessionTables.filter(t => !t.document_name || t.document_name === selectedDoc.filename)
    : sessionTables;

  const docFigures = selectedDoc
    ? sessionFigures.filter(f => {
        if (!f.document) return true;
        const normDoc = selectedDoc.filename.replace(/\.pdf$/i, '').toLowerCase();
        return f.document.toLowerCase() === normDoc || f.document === selectedDoc.doc_id;
      })
    : sessionFigures;

  const activeSessionObj = sessions.find(s => s.id === currentSessionId) || sessionData;

  if (currentView === 'landing') {
    return (
      <div className="landing-container">
        {/* Top Navbar */}
        <header className="landing-navbar">
          <div className="landing-brand">
            <div className="landing-brand-icon">
              <FileText size={22} />
            </div>
            <div>
              <h1 className="landing-brand-title">Document Intelligence</h1>
              <p className="landing-brand-subtitle">From Documents to Knowledge</p>
            </div>
          </div>

          <nav className="landing-nav-links">
            <span className="landing-nav-item">Features</span>
            <span className="landing-nav-item">How it works</span>
            <span className="landing-nav-item">Use cases</span>
            <span className="landing-nav-item" onClick={() => window.open('/docs', '_blank')}>Docs</span>
            {sessions.length > 0 && (
              <button 
                className="landing-nav-workspace-btn" 
                onClick={() => setCurrentView('workspace')}
                title="Open active workspace"
              >
                Open Workspace &rarr;
              </button>
            )}
          </nav>
        </header>

        {/* Center Hero Body */}
        <section className="landing-hero-body">
          <div className="landing-hero-left">
            <span className="landing-eyebrow">DOCUMENTS CONTAIN KNOWLEDGE.</span>
            <h1 className="landing-main-title">
              Turn complex<br />
              documents into<br />
              <span className="landing-highlight-text">trusted knowledge.</span>
            </h1>
            <p className="landing-desc-para">
              Understand, compare, and draw insights from text,
              tables, and figures &mdash; all grounded in the original source.
            </p>
            <button className="landing-cta-link" onClick={handleStartConversation}>
              <span>Start a conversation with your documents</span>
              <span className="landing-cta-arrow">&rarr;</span>
            </button>
          </div>

          <div className="landing-hero-right">
            <div className="landing-hero-image-wrapper">
              <img 
                src="/hero-docs.jpg" 
                alt="Document Intelligence Reports" 
                className="landing-hero-image"
              />
            </div>
          </div>
        </section>

        {/* Bottom Footer Row */}
        <footer className="landing-footer-row">
          <div className="landing-footer-left">
            <span>MORE SIGNAL.</span>
            <span>A MORE INFORMED TOMORROW.</span>
          </div>

          <div className="landing-footer-right">
            <div className="landing-footer-rule"></div>
            <div className="landing-footer-right-text">
              <span>KNOWLEDGE</span>
              <span>BUILDS BRIGHTER FUTURES</span>
            </div>
          </div>
        </footer>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Top Navbar */}
      <header className="top-navbar">
        {/* Left: Brand Logo & Title - clicking takes to home/landing page */}
        <div 
          className="brand-wrapper" 
          onClick={() => setCurrentView('landing')} 
          title="Document Intelligence - Click to go to Home"
        >
          <div className="brand-icon">
            <FileText size={22} />
          </div>
          <div>
            <h1 className="brand-title">Document Intelligence</h1>
            <p className="brand-sub">From Documents to Knowledge</p>
          </div>
        </div>

        {/* Center: Expressive Workspace Pill & Dropdown */}
        <div className="workspace-center-container" onClick={(e) => e.stopPropagation()}>
          <button 
            className={`workspace-pill-btn ${showWorkspaceDropdown ? 'active' : ''}`}
            onClick={() => setShowWorkspaceDropdown(prev => !prev)}
            title="Click to switch workspace, right-click any to rename or delete"
          >
            <span className="workspace-pill-icon"><Folder size={17} /></span>
            <span className="workspace-pill-title">{activeSessionObj?.title || 'Workspace'}</span>
            <span className="workspace-pill-badge">{sessionData?.documents?.length || 0} docs</span>
            <ChevronDown size={14} className={`workspace-pill-chevron ${showWorkspaceDropdown ? 'open' : ''}`} />
          </button>

          {showWorkspaceDropdown && (
            <div className="workspace-dropdown-panel">
              <div className="workspace-dropdown-header">
                <span className="workspace-dropdown-header-title">Workspaces</span>
                <button className="workspace-dropdown-new-btn" onClick={() => handleCreateSession(true)}>
                  <Plus size={14} /> New
                </button>
              </div>
              
              <div className="workspace-dropdown-list">
                {sessions.length === 0 ? (
                  <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
                    No workspaces yet.<br />Click <strong>+ New</strong> above to create one.
                  </div>
                ) : (
                  sessions.map(s => {
                    const isActive = s.id === currentSessionId;
                    const docCount = s.total_documents ?? s.documents?.length ?? 0;
                    return (
                      <div
                        key={s.id}
                        className={`workspace-dropdown-item ${isActive ? 'active' : ''}`}
                        onClick={() => {
                          setCurrentSessionId(s.id);
                          setShowWorkspaceDropdown(false);
                        }}
                        onContextMenu={(e) => handleWorkspaceContextMenu(e, s)}
                        title="Right-click to Rename or Delete"
                      >
                        <div className="workspace-item-left">
                          <Folder size={16} color={isActive ? 'var(--primary)' : '#8c8072'} />
                          <span className="workspace-item-name">{s.title}</span>
                        </div>
                        <div className="workspace-item-meta">
                          <span>{docCount} docs</span>
                          {isActive && <CheckCircle2 size={13} color="var(--primary)" />}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <div className="workspace-dropdown-footer">
                💡 Right-click any workspace above to Rename or Delete
              </div>
            </div>
          )}
        </div>

        {/* Right: Actions */}
        <div className="nav-actions">
          <button className="btn-outline" onClick={() => handleCreateSession(true)}>
            <Plus size={16} /> New Chat
          </button>
          <button className="btn-primary" onClick={() => setShowUploadModal(true)}>
            Upload PDF
          </button>
        </div>
      </header>

      {/* Floating Context Menu for Workspace Right-Click */}
      {contextMenu && (
        <div 
          className="context-menu-floating"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="context-menu-title">
            {contextMenu.session.title}
          </div>
          <div 
            className="context-menu-item"
            onClick={() => handleRenameWorkspace(contextMenu.session)}
          >
            <Edit2 size={14} />
            <span>Rename Workspace</span>
          </div>
          <div 
            className="context-menu-item danger"
            onClick={() => handleDeleteWorkspace(contextMenu.session)}
          >
            <Trash2 size={14} />
            <span>Delete Workspace</span>
          </div>
        </div>
      )}

      {/* Main Split Workspace */}
      <main className={`workspace-container ${navSection === 'Ask' ? 'ask-mode' : ''}`}>
        {/* Left Sidebar */}
        <aside className="workspace-sidebar">
          <div className="sidebar-nav">
            <div 
              className={`sidebar-item ${navSection === 'Documents' ? 'active' : ''}`}
              onClick={() => setNavSection('Documents')}
            >
              <FileText size={18} />
              <span>Documents</span>
            </div>
            <div 
              className={`sidebar-item ${navSection === 'Ask' ? 'active' : ''}`}
              onClick={() => { setNavSection('Ask'); setActiveTab('Chat'); }}
            >
              <MessageSquare size={18} />
              <span>Ask</span>
            </div>
            <div 
              className={`sidebar-item ${navSection === 'Knowledge Graph' ? 'active' : ''}`}
              onClick={() => { setNavSection('Knowledge Graph'); setActiveTab('Reconciliation'); }}
            >
              <Share2 size={18} />
              <span>Knowledge Graph</span>
            </div>
          </div>

          <div className="sidebar-bottom">
            {/* Storage Quota Progress */}
            <div className="storage-widget">
              <div className="storage-label-row">
                <span style={{ fontWeight: 600 }}>Storage</span>
                <span>{storageQuota.display_text}</span>
              </div>
              <div className="storage-bar-bg">
                <div 
                  className="storage-bar-fill" 
                  style={{ width: `${storageQuota.usage_percentage ?? 0}%` }} 
                />
              </div>
            </div>

            {/* User Profile */}
            <div className="user-profile-row">
              <div className="user-avatar">📁</div>
              <div>
                <p className="user-meta-name">Workspace</p>
                <p className="user-meta-email">{sessionData?.title || 'Isolated Session'}</p>
              </div>
            </div>
          </div>
        </aside>

        {!currentSessionId || sessions.length === 0 ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', textAlign: 'center' }}>
            <div style={{ width: 64, height: 64, borderRadius: 16, background: 'rgba(217, 85, 34, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <Folder size={32} color="var(--primary)" />
            </div>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--text-title)', marginBottom: 8 }}>No Active Workspace</h2>
            <p style={{ color: 'var(--text-muted)', maxWidth: 420, marginBottom: 24, fontSize: '0.92rem' }}>
              Create a workspace to upload PDF documents, inspect grounded facts, and ask intelligent questions.
            </p>
            <button 
              className="landing-cta-link" 
              onClick={() => handleCreateSession(true)}
              style={{ padding: '12px 24px', fontSize: '0.95rem', display: 'inline-flex', alignItems: 'center', gap: 8 }}
            >
              <Plus size={16} />
              <span>Create New Workspace</span>
            </button>
          </div>
        ) : navSection === 'Ask' ? (
          <>
            {/* Center Clean Chat Space */}
            <section className="ask-chat-main">
              {/* Header */}
              <div className="ask-chat-header">
                <div className="ask-chat-title-group">
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-title)' }}>
                      {sessionData?.title || 'Interactive Workspace Chat'}
                    </h2>
                    <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                      Grounded cross-document questions and reasoning with verified evidence citations
                    </span>
                  </div>
                  <span className="ask-chat-scope-badge">
                    <Bookmark size={12} />
                    {selectedDoc ? `Focused: ${selectedDoc.title}` : 'All Workspace Documents'}
                  </span>
                </div>
                {selectedDoc && (
                  <button 
                    className="btn-outline" 
                    style={{ fontSize: '0.78rem', padding: '5px 12px' }}
                    onClick={() => setSelectedDoc(null)}
                  >
                    Query All Documents
                  </button>
                )}
              </div>

              {/* Chat Stream */}
              <div className="ask-stream-scrollable">
                {chatMessages.map((msg) => (
                  <div 
                    key={msg.id}
                    className={msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}
                  >
                    {msg.role === 'assistant' && (
                      <div className="ai-avatar-icon">
                        <Sparkles size={16} />
                      </div>
                    )}

                    <div className="ai-content-body">
                      <div className="ai-text-narrative">
                        {msg.content}
                      </div>

                      {/* Source Evidence Cards */}
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="source-evidence-card">
                          <div className="evidence-badge-header">
                            <span>Source Evidence</span>
                            <span className="evidence-page-chip">Page {msg.citations[0].page_number}</span>
                          </div>

                          <div className="evidence-snippet-preview">
                            <div className="evidence-mini-thumb">
                              <img 
                                src={msg.citations[0].thumbnail_url} 
                                alt="Source Page"
                                onError={(e) => { e.target.style.display = 'none'; }}
                              />
                            </div>
                            <p className="evidence-quote-text">
                              "{msg.citations[0].verbatim_quote}"
                            </p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                <div ref={chatEndRef} />
              </div>

              {/* Search Bar at Bottom Centre */}
              <div className="ask-bottom-center-wrapper">
                <div className="ask-suggestion-chips-row">
                  <button className="ask-suggest-chip" onClick={() => handleSendMessage(selectedDoc ? `Summarize ${selectedDoc.title}` : 'Summarize the documents in this workspace')}>
                    Summarize {selectedDoc ? selectedDoc.title : 'workspace'}
                  </button>
                  <button className="ask-suggest-chip" onClick={() => handleSendMessage('What are the key points, instructions, or metrics?')}>
                    Key points & instructions
                  </button>
                  <button className="ask-suggest-chip" onClick={() => handleSendMessage('What specific numbers, figures, or dates are mentioned?')}>
                    Extract metrics & numbers
                  </button>
                  <button className="ask-suggest-chip" onClick={() => handleSendMessage('Are there any conflicting figures or contradictions between documents?')}>
                    Find contradictions
                  </button>
                </div>

                <form 
                  className="ask-bottom-center-box"
                  onSubmit={(e) => { e.preventDefault(); handleSendMessage(); }}
                >
                  <Search size={18} style={{ color: 'var(--text-muted)' }} />
                  <input 
                    type="text" 
                    className="ask-bottom-input"
                    placeholder={selectedDoc ? `Ask about "${selectedDoc.title}"...` : "Ask a question across all documents in this workspace..."}
                    value={inputQuery}
                    onChange={(e) => setInputQuery(e.target.value)}
                    disabled={isAsking}
                  />
                  <button 
                    type="submit" 
                    className="ask-send-btn"
                    disabled={!inputQuery.trim() || isAsking}
                  >
                    <Send size={16} />
                  </button>
                </form>
              </div>
            </section>

            {/* Right Side: Workspace Documents List to chat for */}
            <aside className="ask-docs-sidebar">
              <div className="ask-docs-header">
                <h3 className="ask-docs-title">Documents ({sessionData?.documents?.length || 0})</h3>
                <p className="ask-docs-subtitle">
                  Select a document to focus queries, or query all.
                </p>
              </div>

              <div 
                className={`ask-docs-scope-all ${selectedDoc === null ? 'active' : ''}`}
                onClick={() => setSelectedDoc(null)}
                title="Query all documents simultaneously"
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={16} color="var(--primary)" />
                  <span style={{ fontSize: '0.86rem', fontWeight: 600 }}>All Documents (Combined)</span>
                </div>
                <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                  {sessionData?.documents?.length || 0} docs
                </span>
              </div>

              <div style={{ display: 'flex', flex: 1, flexDirection: 'column', overflowY: 'auto' }}>
                {(sessionData?.documents || []).map((doc) => {
                  const isFocused = selectedDoc?.filename === doc.filename;
                  return (
                    <div 
                      key={doc.doc_id || doc.filename}
                      className={`ask-doc-card-item ${isFocused ? 'active' : ''}`}
                      onClick={() => setSelectedDoc(doc)}
                      title={`Click to focus chat on ${doc.title}`}
                    >
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                          <FileText size={16} color={isFocused ? 'var(--primary)' : 'var(--text-muted)'} />
                          <h4 className="ask-doc-card-title">{doc.title}</h4>
                        </div>
                        {isFocused && <CheckCircle2 size={14} color="var(--primary)" style={{ flexShrink: 0, marginTop: '2px' }} />}
                      </div>
                      <div className="ask-doc-card-stats">
                        <span>{doc.pages_count} pages</span>
                        <span>&bull;</span>
                        <span>{doc.blocks_count || 0} blocks</span>
                        <span>&bull;</span>
                        <span>{doc.tables_count || 0} tables</span>
                      </div>
                    </div>
                  );
                })}

                {(!sessionData?.documents || sessionData.documents.length === 0) && (
                  <div style={{ textAlign: 'center', padding: '30px 10px', color: 'var(--text-muted)', fontSize: '0.84rem' }}>
                    No documents uploaded yet in this workspace. Click "Upload PDF" in the top right to start!
                  </div>
                )}
              </div>
            </aside>
          </>
        ) : (
          <>
            {/* Middle Panel: Documents List */}
            <section className="documents-panel">
              <div className="panel-header-row">
                <div className="panel-title">
                  <h2>Documents</h2>
                  <p>Manage your documents and extracted knowledge in this chat workspace.</p>
                </div>
              </div>

              <div className="filter-controls-row">
                <div className="search-input-box">
                  <Search size={16} className="search-icon-pos" />
                  <input 
                    type="text" 
                    placeholder="Search documents by title, tags, or content..." 
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                <select 
                  className="filter-select"
                  value={selectedTagFilter}
                  onChange={(e) => setSelectedTagFilter(e.target.value)}
                >
                  <option value="">All Documents ({sessionData?.documents?.length || 0})</option>
                  {allTags.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              {/* Document Cards List */}
              <div className="document-cards-list">
                {filteredDocs.map((doc) => {
                  const isSelected = selectedDoc?.filename === doc.filename;
                  const thumbUrl = `/api/sessions/${currentSessionId}/documents/${doc.filename.replace('.pdf', '')}/pages/1/thumbnail`;
                  return (
                    <div 
                      key={doc.doc_id || doc.filename}
                      className={`doc-card ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedDoc(doc)}
                    >
                      <div className="doc-card-thumb">
                        <img 
                          src={thumbUrl} 
                          alt="Thumbnail" 
                          onError={(e) => { e.target.style.display = 'none'; }}
                        />
                        <FileText size={24} color="#9c8e7e" />
                      </div>

                      <div className="doc-card-content">
                        <div className="doc-card-header">
                          <h3 className="doc-card-title">{doc.title}</h3>
                          <span className="status-badge-processed">
                            <CheckCircle2 size={12} /> {doc.status || 'Processed'}
                          </span>
                        </div>

                        <p className="doc-card-meta">
                          PDF &bull; {doc.pages_count} pages &bull; Processed {doc.processed_time || 'recently'}
                        </p>

                        <p className="doc-card-summary">{doc.summary}</p>

                        <div className="doc-card-footer">
                          <div className="tag-pills-row">
                            {doc.tags?.map((t, idx) => (
                              <span key={idx} className="tag-pill">{t}</span>
                            ))}
                          </div>

                          <div className="doc-stats-counts">
                            <span><strong>{doc.blocks_count ?? 0}</strong> Blocks</span>
                            <span><strong>{doc.tables_count ?? 0}</strong> Tables</span>
                            <span><strong>{doc.figures_count ?? 0}</strong> Figures</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {filteredDocs.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                    No documents found in this workspace. Upload a PDF to begin!
                  </div>
                )}
              </div>
            </section>

            {/* Right Panel: Interactive Document Inspection & Chat */}
            <section className="inspect-chat-panel">
              {selectedDoc ? (
                <>
                  {/* Header */}
                  <div className="doc-view-header">
                    <div className="back-doc-btn">
                      <ArrowLeft size={18} />
                      <span>{selectedDoc.title}</span>
                    </div>
                    <button 
                      className="btn-outline" 
                      onClick={() => window.open(`/api/sessions/${currentSessionId}/documents/${selectedDoc.filename.replace('.pdf', '')}/pages/1/thumbnail`, '_blank')}
                    >
                      <ExternalLink size={14} /> Open Preview
                    </button>
                  </div>

                  {/* View Tabs Bar */}
                  <div className="view-tabs-bar">
                    {['Chat', 'Key Facts', 'Tables', 'Figures', 'Structure', 'Reconciliation'].map((tab) => (
                      <div 
                        key={tab}
                        className={`tab-item ${activeTab === tab ? 'active' : ''}`}
                        onClick={() => setActiveTab(tab)}
                      >
                        {tab}
                      </div>
                    ))}
                  </div>

                  {/* TAB 1: Chat Stream */}
                  {activeTab === 'Chat' && (
                    <>
                      <div className="chat-stream-area">
                        {chatMessages.map((msg) => (
                          <div 
                            key={msg.id}
                            className={msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'}
                          >
                            {msg.role === 'assistant' && (
                              <div className="ai-avatar-icon">
                                <Sparkles size={16} />
                              </div>
                            )}

                            <div className="ai-content-body">
                              <div className="ai-text-narrative">
                                {msg.content}
                              </div>

                              {/* Source Evidence Cards */}
                              {msg.citations && msg.citations.length > 0 && (
                                <div className="source-evidence-card">
                                  <div className="evidence-badge-header">
                                    <span>Source Evidence</span>
                                    <span className="evidence-page-chip">Page {msg.citations[0].page_number}</span>
                                  </div>

                                  <div className="evidence-snippet-preview">
                                    <div className="evidence-mini-thumb">
                                      <img 
                                        src={msg.citations[0].thumbnail_url} 
                                        alt="Source Page"
                                        onError={(e) => { e.target.style.display = 'none'; }}
                                      />
                                    </div>
                                    <p className="evidence-quote-text">
                                      "{msg.citations[0].verbatim_quote}"
                                    </p>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                        <div ref={chatEndRef} />
                      </div>

                      {/* Chat Input Bar */}
                      <div className="chat-input-wrapper">
                        <form 
                          className="chat-input-box"
                          onSubmit={(e) => { e.preventDefault(); handleSendMessage(); }}
                        >
                          <input 
                            type="text" 
                            placeholder="Ask a question about this document..."
                            value={inputQuery}
                            onChange={(e) => setInputQuery(e.target.value)}
                            disabled={isAsking}
                          />
                          <button 
                            type="submit" 
                            className="chat-action-btn"
                            disabled={!inputQuery.trim() || isAsking}
                          >
                            <Send size={16} />
                          </button>
                        </form>

                        {/* Dynamic suggestion pills */}
                        <div className="suggestion-chips-row">
                          <button className="suggest-chip" onClick={() => handleSendMessage(`Summarize ${selectedDoc?.title || 'the document'}`)}>
                            Summarize document
                          </button>
                          <button className="suggest-chip" onClick={() => handleSendMessage('What are the key points or instructions in this document?')}>
                            Key points & instructions
                          </button>
                          <button className="suggest-chip" onClick={() => handleSendMessage('What specific metrics, numbers, or dates are mentioned?')}>
                            Extract metrics & numbers
                          </button>
                          <button className="suggest-chip" onClick={() => handleSendMessage('Are there any conflicting figures or details?')}>
                            Find contradictions
                          </button>
                        </div>
                      </div>
                    </>
                  )}

                  {/* TAB 2: Key Facts Catalog */}
                  {activeTab === 'Key Facts' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px' }}>
                        Verified Grounded Facts ({docFacts.length})
                      </h3>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {docFacts.map((f, i) => (
                          <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '14px', background: '#faf8f5' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                              <span style={{ fontWeight: 700, color: 'var(--text-title)' }}>{f.subject} &bull; {f.attribute}</span>
                              <span style={{ background: 'var(--primary-light)', color: 'var(--primary)', padding: '2px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600 }}>
                                {f.temporal_scope || 'N/A'}
                              </span>
                            </div>
                            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--primary)', marginBottom: '6px' }}>
                              {f.value} {f.context_scope && `(${f.context_scope})`}
                            </div>
                            {f.evidence && (
                              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', borderLeft: '2px solid var(--border-strong)', paddingLeft: '8px', fontStyle: 'italic' }}>
                                "{f.evidence.verbatim_quote}" &mdash; {f.evidence.document_name} (p.{f.evidence.page_number})
                              </div>
                            )}
                          </div>
                        ))}
                        {docFacts.length === 0 && (
                          <p style={{ color: 'var(--text-muted)', padding: '12px 0' }}>No structured numerical facts detected in this document.</p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* TAB 3: Tables View */}
                  {activeTab === 'Tables' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px' }}>
                        Structured Table Observations ({docTables.length})
                      </h3>
                      {docTables.map((t, i) => (
                        <div key={i} style={{ marginBottom: '20px', border: '1px solid var(--border-subtle)', borderRadius: '10px', overflow: 'hidden' }}>
                          <div style={{ background: '#f4efe6', padding: '8px 14px', fontSize: '0.8rem', fontWeight: 600 }}>
                            Table on Page {t.page_number} ({t.row_count} rows &times; {t.col_count} columns)
                          </div>
                          <div style={{ overflowX: 'auto', padding: '12px' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                              <thead>
                                <tr>
                                  {t.headers?.map((h, hi) => (
                                    <th key={hi} style={{ borderBottom: '2px solid #ddd', padding: '6px 10px', textAlign: 'left', background: '#faf8f5' }}>{h}</th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {t.rows?.map((r, ri) => (
                                  <tr key={ri} style={{ borderBottom: '1px solid #eee' }}>
                                    {r.map((cell, ci) => (
                                      <td key={ci} style={{ padding: '6px 10px' }}>{cell}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ))}
                      {docTables.length === 0 && <p style={{ color: 'var(--text-muted)' }}>No structured tables detected in this document.</p>}
                    </div>
                  )}

                  {/* TAB 4: Figures View */}
                  {activeTab === 'Figures' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px' }}>
                        Figures & Visual Diagrams ({docFigures.length})
                      </h3>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '16px' }}>
                        {docFigures.map((fig, i) => (
                          <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '10px', overflow: 'hidden', background: '#faf8f5', textAlign: 'center', padding: '10px' }}>
                            <img src={fig.url} alt={fig.figure_id} style={{ maxWidth: '100%', maxHeight: '140px', objectFit: 'contain' }} />
                            <p style={{ fontSize: '0.78rem', marginTop: '8px', color: 'var(--text-muted)' }}>{fig.figure_id}</p>
                          </div>
                        ))}
                      </div>
                      {docFigures.length === 0 && <p style={{ color: 'var(--text-muted)' }}>No figures or diagrams detected in this document.</p>}
                    </div>
                  )}

                  {/* TAB 5: Structure View */}
                  {activeTab === 'Structure' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px' }}>
                        Document Structure & Layout Outline
                      </h3>
                      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '14px' }}>
                        Canonical multimodal breakdown of sections, headings, and paragraph blocks.
                      </p>
                      <div style={{ background: '#fdfcf9', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '16px', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                        <div>Document: {selectedDoc.filename}</div>
                        <div>Total Pages: {selectedDoc.pages_count}</div>
                        <div>Blocks: {selectedDoc.blocks_count} layout elements</div>
                        <div>Status: Verified & Grounded in Object Storage</div>
                      </div>
                    </div>
                  )}

                  {/* TAB 6: Cross-Document Reconciliation */}
                  {activeTab === 'Reconciliation' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
                      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '12px' }}>
                        Cross-Document Reconciliation Matrix
                      </h3>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        {sessionComparisons.map((c, i) => (
                          <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '16px', background: '#faf8f5' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-title)' }}>{c.title}</h4>
                              <span style={{ textTransform: 'uppercase', fontSize: '0.72rem', fontWeight: 700, padding: '3px 8px', borderRadius: '4px', background: c.relationship_type === 'corroboration' ? 'var(--success-bg)' : c.relationship_type === 'contradiction' ? 'var(--danger-bg)' : 'var(--primary-light)', color: c.relationship_type === 'corroboration' ? 'var(--success)' : c.relationship_type === 'contradiction' ? 'var(--danger)' : 'var(--primary)' }}>
                                {c.relationship_type}
                              </span>
                            </div>
                            <p style={{ fontSize: '0.85rem', color: 'var(--text-body)', lineHeight: 1.5, marginBottom: '8px' }}>
                              {c.explanation}
                            </p>
                            {c.reconciliation_factor && (
                              <div style={{ fontSize: '0.8rem', background: '#f2ece2', padding: '6px 10px', borderRadius: '6px', color: 'var(--primary)', fontWeight: 600 }}>
                                Resolution: {c.reconciliation_factor}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
                  Select a document from the left list to inspect details or start chatting.
                </div>
              )}
            </section>
          </>
        )}
      </main>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="modal-backdrop" onClick={() => setShowUploadModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>Upload PDF to Workspace</h3>
              <X size={20} style={{ cursor: 'pointer' }} onClick={() => setShowUploadModal(false)} />
            </div>

            <p style={{ fontSize: '0.88rem', color: 'var(--text-muted)' }}>
              The uploaded file will be stored in isolated object storage for this chat and processed for text, tables, figures, and facts.
            </p>

            <div 
              className="dropzone-inner"
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
              }}
            >
              <Upload size={32} style={{ color: 'var(--primary)', margin: '0 auto 12px' }} />
              <p style={{ fontWeight: 600, marginBottom: '4px' }}>Click or drag PDF here to upload</p>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Stored in isolated workspace bucket</span>
              <input 
                ref={fileInputRef}
                type="file" 
                accept="application/pdf" 
                style={{ display: 'none' }}
                onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
              />
            </div>

            {uploadStatus && (
              <div style={{ fontSize: '0.85rem', padding: '10px', borderRadius: '8px', background: 'var(--surface-subtle)', color: 'var(--primary)', fontWeight: 600 }}>
                {uploadStatus}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
              <button className="btn-outline" onClick={() => setShowUploadModal(false)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
