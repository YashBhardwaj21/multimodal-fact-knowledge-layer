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
  const [activeTab, setActiveTab] = useState('Key Facts'); // Key Facts | Tables | Figures | Structure | Reconciliation
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTagFilter, setSelectedTagFilter] = useState('');
  const [navSection, setNavSection] = useState('Documents'); // Documents | Ask | Knowledge Graph

  // Custom Themed Modals
  const [createWsModal, setCreateWsModal] = useState({ isOpen: false, title: '' });
  const [renameWsModal, setRenameWsModal] = useState({ isOpen: false, session: null, newTitle: '' });
  const [deleteWsModal, setDeleteWsModal] = useState({ isOpen: false, session: null });
  const [deleteDocModal, setDeleteDocModal] = useState({ isOpen: false, doc: null });
  const [modalError, setModalError] = useState('');

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

  const handleOpenCreateModal = () => {
    setModalError('');
    setCreateWsModal({ isOpen: true, title: `Workspace ${sessions.length + 1}` });
  };

  const handleCreateSession = () => {
    handleOpenCreateModal();
  };

  const executeCreateWorkspace = async () => {
    const title = createWsModal.title.trim() || `Workspace ${sessions.length + 1}`;
    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, description: 'Interactive document intelligence workspace.' })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create workspace');
      }
      const newSession = await res.json();
      await fetchSessions();
      setCurrentSessionId(newSession.id);
      setShowWorkspaceDropdown(false);
      setNavSection('Documents');
      setSelectedDoc(null);
      setCreateWsModal({ isOpen: false, title: '' });
      setModalError('');
    } catch (err) {
      setModalError(err.message);
    }
  };

  const handleOpenRenameModal = (sessionToRename) => {
    setContextMenu(null);
    setModalError('');
    setRenameWsModal({ isOpen: true, session: sessionToRename, newTitle: sessionToRename.title });
  };

  const executeRenameWorkspace = async () => {
    if (!renameWsModal.session) return;
    const cleanTitle = renameWsModal.newTitle.trim();
    if (!cleanTitle) {
      setModalError('Workspace title cannot be empty.');
      return;
    }

    try {
      const res = await fetch(`/api/sessions/${renameWsModal.session.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: cleanTitle })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to rename workspace');
      }

      await fetchSessions();
      if (currentSessionId === renameWsModal.session.id) {
        await loadSessionDetails(currentSessionId);
      }
      setRenameWsModal({ isOpen: false, session: null, newTitle: '' });
      setModalError('');
    } catch (err) {
      setModalError(err.message);
    }
  };

  const handleOpenDeleteModal = (sessionToDelete) => {
    setContextMenu(null);
    setModalError('');
    setDeleteWsModal({ isOpen: true, session: sessionToDelete });
  };

  const executeDeleteWorkspace = async () => {
    if (!deleteWsModal.session) return;
    try {
      const res = await fetch(`/api/sessions/${deleteWsModal.session.id}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to delete workspace');
      }

      const updatedRes = await fetch('/api/sessions');
      const updatedSessions = await updatedRes.json();
      setSessions(updatedSessions);

      if (currentSessionId === deleteWsModal.session.id) {
        if (updatedSessions.length > 0) {
          setCurrentSessionId(updatedSessions[0].id);
        } else {
          setCurrentSessionId(null);
          setSessionData(null);
        }
      }
      await fetchStorageQuota();
      setDeleteWsModal({ isOpen: false, session: null });
      setModalError('');
    } catch (err) {
      setModalError(err.message);
    }
  };

  const handleOpenDeleteDocModal = (e, doc) => {
    if (e && e.stopPropagation) e.stopPropagation();
    setModalError('');
    setDeleteDocModal({ isOpen: true, doc });
  };

  const executeDeleteDocument = async () => {
    if (!deleteDocModal.doc || !currentSessionId) return;
    try {
      const docId = deleteDocModal.doc.id || deleteDocModal.doc.doc_id || deleteDocModal.doc.filename;
      const res = await fetch(`/api/sessions/${currentSessionId}/documents/${encodeURIComponent(docId)}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to delete document');
      }

      if (selectedDoc && (selectedDoc.id === docId || selectedDoc.filename === deleteDocModal.doc.filename)) {
        setSelectedDoc(null);
      }
      setDeleteDocModal({ isOpen: false, doc: null });
      setModalError('');
      await loadSessionDetails(currentSessionId);
      await fetchStorageQuota();
    } catch (err) {
      setModalError(err.message);
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
            <img src="/globe-logo.png" alt="Meridian" className="landing-brand-logo" />
            <h1 className="landing-brand-title">Meridian</h1>
          </div>

          <nav className="landing-nav-links">
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
            <h1 className="landing-main-title">
              Turn complex<br />
              documents into<br />
              <span className="landing-highlight-text">trusted knowledge.</span>
            </h1>
            <button className="landing-cta-link" onClick={handleStartConversation}>
              <span>Start a conversation with your documents</span>
              <span className="landing-cta-arrow">&rarr;</span>
            </button>
          </div>

          <div className="landing-hero-right">
            <div className="landing-hero-image-wrapper">
              <img
                src="/books-transparent.png"
                alt="Meridian Books"
                className="landing-hero-image"
              />
            </div>
          </div>
        </section>

        {/* Bottom Footer Row */}
        <footer className="landing-footer-row">
          <div className="landing-footer-left"></div>

          <div className="landing-footer-right">
            <div className="landing-footer-right-text">
              <span>MORE SIGNAL.</span>
              <span>A MORE INFORMED TOMORROW.</span>
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
          title="Meridian - Click to go to Home"
        >
          <img src="/globe-logo.png" alt="Meridian" className="brand-logo-img" />
          <div>
            <h1 className="brand-title">Meridian</h1>
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
            onClick={() => handleOpenRenameModal(contextMenu.session)}
          >
            <Edit2 size={14} />
            <span>Rename Workspace</span>
          </div>
          <div
            className="context-menu-item danger"
            onClick={() => handleOpenDeleteModal(contextMenu.session)}
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
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span className="status-badge-processed">
                              <CheckCircle2 size={12} /> {doc.status || 'Processed'}
                            </span>
                            <button
                              className="doc-delete-btn"
                              title="Delete document from workspace & storage"
                              onClick={(e) => handleOpenDeleteDocModal(e, doc)}
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        className="btn-primary"
                        style={{ padding: '6px 14px', fontSize: '0.82rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                        onClick={() => {
                          setNavSection('Ask');
                        }}
                        title="Open conversational Q&A focused on this document"
                      >
                        <MessageSquare size={14} />
                        <span>Ask about this doc</span>
                      </button>
                      <button
                        className="btn-outline"
                        onClick={() => window.open(`/api/sessions/${currentSessionId}/documents/${selectedDoc.filename.replace('.pdf', '')}/pages/1/thumbnail`, '_blank')}
                      >
                        <ExternalLink size={14} /> Open Preview
                      </button>
                    </div>
                  </div>

                  {/* View Tabs Bar - Focused on Knowledge & Inspection */}
                  <div className="view-tabs-bar">
                    {['Key Facts', 'Tables', 'Figures', 'Structure', 'Reconciliation'].map((tab) => (
                      <div
                        key={tab}
                        className={`tab-item ${activeTab === tab ? 'active' : ''}`}
                        onClick={() => setActiveTab(tab)}
                      >
                        {tab}
                      </div>
                    ))}
                  </div>

                  {/* TAB 1: Key Facts Catalog */}
                  {activeTab === 'Key Facts' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>
                          Verified Grounded Facts ({docFacts.length})
                        </h3>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          Canonical structured entities extracted with evidence quotes
                        </span>
                      </div>
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
                          <p style={{ color: 'var(--text-muted)', padding: '20px 0', textAlign: 'center' }}>
                            No structured numerical facts detected in this document.
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* TAB 2: Tables View */}
                  {activeTab === 'Tables' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0', minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>
                          Structured Table Observations ({docTables.length})
                        </h3>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          Extracted from layout blocks with clean tabular formatting
                        </span>
                      </div>

                      {docTables.map((t, i) => (
                        <div key={i} className="table-scroll-wrapper">
                          <div style={{ background: '#f7f4ee', padding: '10px 16px', fontSize: '0.82rem', fontWeight: 700, display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)' }}>
                            <span style={{ color: 'var(--text-title)' }}>
                              Table on Page {t.page_number}
                            </span>
                            <span style={{ fontSize: '0.74rem', background: '#ece5d8', padding: '2px 8px', borderRadius: '4px', color: 'var(--text-muted)' }}>
                              {t.row_count || t.rows?.length || 0} rows &times; {t.col_count || t.headers?.length || (t.rows?.[0]?.length || 0)} cols
                            </span>
                          </div>
                          <div style={{ overflowX: 'auto', width: '100%' }}>
                            <table className="clean-data-table">
                              {t.headers && t.headers.length > 0 && (
                                <thead>
                                  <tr>
                                    {t.headers.map((h, hi) => (
                                      <th key={hi}>{h || `Col ${hi + 1}`}</th>
                                    ))}
                                  </tr>
                                </thead>
                              )}
                              <tbody>
                                {t.rows?.map((r, ri) => (
                                  <tr key={ri}>
                                    {r.map((cell, ci) => (
                                      <td key={ci}>{cell}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      ))}
                      {docTables.length === 0 && (
                        <p style={{ color: 'var(--text-muted)', padding: '20px 0', textAlign: 'center' }}>
                          No structured tables detected in this document.
                        </p>
                      )}
                    </div>
                  )}

                  {/* TAB 3: Figures View */}
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

                  {/* TAB 4: Structure View */}
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

                  {/* TAB 5: Cross-Document Reconciliation */}
                  {activeTab === 'Reconciliation' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0', minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>
                          Cross-Document Reconciliation Matrix ({sessionComparisons.length})
                        </h3>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                          Automated reasoning with exact page & table citations
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {sessionComparisons.map((c, i) => (
                          <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '18px', background: '#faf8f5' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                              <h4 style={{ fontSize: '0.98rem', fontWeight: 700, color: 'var(--text-title)' }}>{c.title}</h4>
                              <span style={{ textTransform: 'uppercase', fontSize: '0.72rem', fontWeight: 700, padding: '4px 10px', borderRadius: '4px', background: c.relationship_type === 'corroboration' ? 'var(--success-bg)' : c.relationship_type === 'contradiction' ? 'var(--danger-bg)' : 'var(--primary-light)', color: c.relationship_type === 'corroboration' ? 'var(--success)' : c.relationship_type === 'contradiction' ? 'var(--danger)' : 'var(--primary)' }}>
                                {c.relationship_type}
                              </span>
                            </div>

                            <p style={{ fontSize: '0.88rem', color: 'var(--text-body)', lineHeight: 1.5, marginBottom: '12px' }}>
                              {c.explanation}
                            </p>

                            {c.reconciliation_factor && (
                              <div style={{ fontSize: '0.82rem', background: '#f2ece2', padding: '8px 12px', borderRadius: '6px', color: 'var(--primary)', fontWeight: 600, marginBottom: '12px' }}>
                                Resolution: {c.reconciliation_factor}
                              </div>
                            )}

                            {/* Grounded Dual Evidence Comparison */}
                            {(c.fact_a || c.fact_b) && (
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '10px' }}>
                                {c.fact_a && (
                                  <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-title)' }}>
                                        {c.fact_a.evidence?.document_name || 'Document A'}
                                      </span>
                                      {c.fact_a.evidence?.page_number && (
                                        <span className="reconciliation-citation-badge page">
                                          Page {c.fact_a.evidence.page_number}
                                        </span>
                                      )}
                                    </div>

                                    {c.fact_a.evidence?.table_citation && (
                                      <div style={{ marginBottom: '6px' }}>
                                        <span className="reconciliation-citation-badge table">
                                          <Table size={12} /> {c.fact_a.evidence.table_citation}
                                        </span>
                                      </div>
                                    )}

                                    {c.fact_a.evidence?.image_citation && (
                                      <div style={{ marginBottom: '6px' }}>
                                        <span className="reconciliation-citation-badge image">
                                          <Image size={12} /> {c.fact_a.evidence.image_citation}
                                        </span>
                                      </div>
                                    )}

                                    <div style={{ fontSize: '0.86rem', fontWeight: 700, color: 'var(--primary)', margin: '4px 0' }}>
                                      {c.fact_a.subject} &bull; {c.fact_a.attribute}: {c.fact_a.value}
                                    </div>

                                    {c.fact_a.evidence?.verbatim_quote && (
                                      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontStyle: 'italic', margin: 0 }}>
                                        "{c.fact_a.evidence.verbatim_quote}"
                                      </p>
                                    )}
                                  </div>
                                )}

                                {c.fact_b && (
                                  <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                                      <span style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-title)' }}>
                                        {c.fact_b.evidence?.document_name || 'Document B'}
                                      </span>
                                      {c.fact_b.evidence?.page_number && (
                                        <span className="reconciliation-citation-badge page">
                                          Page {c.fact_b.evidence.page_number}
                                        </span>
                                      )}
                                    </div>

                                    {c.fact_b.evidence?.table_citation && (
                                      <div style={{ marginBottom: '6px' }}>
                                        <span className="reconciliation-citation-badge table">
                                          <Table size={12} /> {c.fact_b.evidence.table_citation}
                                        </span>
                                      </div>
                                    )}

                                    {c.fact_b.evidence?.image_citation && (
                                      <div style={{ marginBottom: '6px' }}>
                                        <span className="reconciliation-citation-badge image">
                                          <Image size={12} /> {c.fact_b.evidence.image_citation}
                                        </span>
                                      </div>
                                    )}

                                    <div style={{ fontSize: '0.86rem', fontWeight: 700, color: 'var(--primary)', margin: '4px 0' }}>
                                      {c.fact_b.subject} &bull; {c.fact_b.attribute}: {c.fact_b.value}
                                    </div>

                                    {c.fact_b.evidence?.verbatim_quote && (
                                      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontStyle: 'italic', margin: 0 }}>
                                        "{c.fact_b.evidence.verbatim_quote}"
                                      </p>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}

                        {sessionComparisons.length === 0 && (
                          <div style={{ textAlign: 'center', padding: '30px 10px', color: 'var(--text-muted)' }}>
                            No cross-document reconciliations yet.<br />
                            Upload multiple documents with overlapping financial or operational metrics to see automated corroborations and contradictions with exact table and page citations.
                          </div>
                        )}
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
      {/* Create Workspace Modal */}
      {createWsModal.isOpen && (
        <div className="modal-backdrop" onClick={() => setCreateWsModal({ isOpen: false, title: '' })}>
          <div className="custom-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="custom-modal-header">
              <h3><Folder size={18} color="var(--primary)" /> Create New Workspace</h3>
              <button
                className="custom-modal-close-btn"
                onClick={() => setCreateWsModal({ isOpen: false, title: '' })}
              >
                <X size={18} />
              </button>
            </div>
            <div className="custom-modal-body">
              <p>Workspaces provide isolated document ingestion, grounded facts, knowledge graphs, and conversational Q&A.</p>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-title)', marginBottom: '6px' }}>
                Workspace Title
              </label>
              <input
                type="text"
                className="custom-modal-input"
                placeholder="e.g. FY24 Financial Reports"
                value={createWsModal.title}
                onChange={(e) => setCreateWsModal(prev => ({ ...prev, title: e.target.value }))}
                onKeyDown={(e) => { if (e.key === 'Enter') executeCreateWorkspace(); }}
                autoFocus
              />
              {modalError && (
                <div style={{ color: '#d93822', fontSize: '0.8rem', marginTop: '8px' }}>
                  {modalError}
                </div>
              )}
            </div>
            <div className="custom-modal-footer">
              <button
                className="modal-btn-cancel"
                onClick={() => setCreateWsModal({ isOpen: false, title: '' })}
              >
                Cancel
              </button>
              <button
                className="modal-btn-confirm"
                onClick={executeCreateWorkspace}
              >
                <Plus size={16} /> Create Workspace
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rename Workspace Modal */}
      {renameWsModal.isOpen && (
        <div className="modal-backdrop" onClick={() => setRenameWsModal({ isOpen: false, session: null, newTitle: '' })}>
          <div className="custom-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="custom-modal-header">
              <h3><Edit2 size={18} color="var(--primary)" /> Rename Workspace</h3>
              <button
                className="custom-modal-close-btn"
                onClick={() => setRenameWsModal({ isOpen: false, session: null, newTitle: '' })}
              >
                <X size={18} />
              </button>
            </div>
            <div className="custom-modal-body">
              <p>Update the name of this workspace.</p>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-title)', marginBottom: '6px' }}>
                New Title
              </label>
              <input
                type="text"
                className="custom-modal-input"
                value={renameWsModal.newTitle}
                onChange={(e) => setRenameWsModal(prev => ({ ...prev, newTitle: e.target.value }))}
                onKeyDown={(e) => { if (e.key === 'Enter') executeRenameWorkspace(); }}
                autoFocus
              />
              {modalError && (
                <div style={{ color: '#d93822', fontSize: '0.8rem', marginTop: '8px' }}>
                  {modalError}
                </div>
              )}
            </div>
            <div className="custom-modal-footer">
              <button
                className="modal-btn-cancel"
                onClick={() => setRenameWsModal({ isOpen: false, session: null, newTitle: '' })}
              >
                Cancel
              </button>
              <button
                className="modal-btn-confirm"
                onClick={executeRenameWorkspace}
              >
                Save Name
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Workspace Modal */}
      {deleteWsModal.isOpen && (
        <div className="modal-backdrop" onClick={() => setDeleteWsModal({ isOpen: false, session: null })}>
          <div className="custom-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="custom-modal-header">
              <h3 style={{ color: '#d93822' }}><Trash2 size={18} color="#d93822" /> Delete Workspace</h3>
              <button
                className="custom-modal-close-btn"
                onClick={() => setDeleteWsModal({ isOpen: false, session: null })}
              >
                <X size={18} />
              </button>
            </div>
            <div className="custom-modal-body">
              <p>
                Are you sure you want to permanently delete <strong>{deleteWsModal.session?.title}</strong>?
              </p>
              <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
                This action will completely purge all documents. This cannot be undone.
              </p>
              {modalError && (
                <div style={{ color: '#d93822', fontSize: '0.8rem', marginTop: '8px' }}>
                  {modalError}
                </div>
              )}
            </div>
            <div className="custom-modal-footer">
              <button
                className="modal-btn-cancel"
                onClick={() => setDeleteWsModal({ isOpen: false, session: null })}
              >
                Cancel
              </button>
              <button
                className="modal-btn-danger"
                onClick={executeDeleteWorkspace}
              >
                <Trash2 size={16} /> Delete Workspace
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Document Modal */}
      {deleteDocModal.isOpen && (
        <div className="modal-backdrop" onClick={() => setDeleteDocModal({ isOpen: false, doc: null })}>
          <div className="custom-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="custom-modal-header">
              <h3 style={{ color: '#d93822' }}><Trash2 size={18} color="#d93822" /> Delete Document</h3>
              <button
                className="custom-modal-close-btn"
                onClick={() => setDeleteDocModal({ isOpen: false, doc: null })}
              >
                <X size={18} />
              </button>
            </div>
            <div className="custom-modal-body">
              <p>
                Permanently delete <strong>{deleteDocModal.doc?.title}</strong> (<code>{deleteDocModal.doc?.filename}</code>)?
              </p>
              <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>
                This removes the document from this workspace, deletes its extracted pages, facts, and evidence from SQLite, purges its vector embeddings, and removes its stored PDF and image assets from Object Storage.
              </p>
              {modalError && (
                <div style={{ color: '#d93822', fontSize: '0.8rem', marginTop: '8px' }}>
                  {modalError}
                </div>
              )}
            </div>
            <div className="custom-modal-footer">
              <button
                className="modal-btn-cancel"
                onClick={() => setDeleteDocModal({ isOpen: false, doc: null })}
              >
                Cancel
              </button>
              <button
                className="modal-btn-danger"
                onClick={executeDeleteDocument}
              >
                <Trash2 size={16} /> Delete Document
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
