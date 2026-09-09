import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  FileText, Upload, Search, MessageSquare, Database, Share2,
  Settings, CheckCircle2, ChevronRight, ArrowLeft, Send,
  ExternalLink, Layers, Table, Image, ShieldCheck, Sparkles, Plus,
  Bookmark, HelpCircle, HardDrive, RefreshCw, X, Folder, ChevronDown,
  Edit2, Trash2, MoreVertical, AlertTriangle, GitCompare, ShieldAlert,
  Download, ZoomIn, RotateCcw
} from 'lucide-react';

function FormattedMarkdown({ content }) {
  if (!content) return null;

  // Pre-process markdown to ensure headings, dividers, and lists have proper blank line breaks
  const normalized = content
    .replace(/\r\n/g, '\n')
    // Guarantee empty line before headings (###) so Markdown parses them as block elements
    .replace(/([^\n])\n(#{1,6}\s)/g, '$1\n\n$2')
    // Guarantee empty line before and after dividers (---)
    .replace(/([^\n])\n(---|__|\*\*\*)\n/g, '$1\n\n$2\n\n')
    // Guarantee empty line before lists following text
    .replace(/([^\n])\n([*+-]|\d+\.)\s/g, '$1\n\n$2 ');

  try {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ node, ...props }) => <h3 className="chat-h3" {...props} />,
          h2: ({ node, ...props }) => <h3 className="chat-h3" {...props} />,
          h3: ({ node, ...props }) => <h3 className="chat-h3" {...props} />,
          h4: ({ node, ...props }) => <h4 className="chat-h4" {...props} />,
          p: ({ node, ...props }) => <p className="chat-p" {...props} />,
          ul: ({ node, ...props }) => <ul className="chat-ul" {...props} />,
          ol: ({ node, ...props }) => <ol className="chat-ol" {...props} />,
          li: ({ node, ...props }) => <li className="chat-li" {...props} />,
          hr: ({ node, ...props }) => <hr className="chat-hr" {...props} />,
          strong: ({ node, ...props }) => <strong className="chat-strong" {...props} />,
          table: ({ node, ...props }) => (
            <div className="chat-table-wrapper">
              <table className="chat-table" {...props} />
            </div>
          )
        }}
      >
        {normalized}
      </ReactMarkdown>
    );
  } catch (e) {
    return <div style={{ whiteSpace: 'pre-wrap' }}>{content}</div>;
  }
}

const UPLOAD_STAGES = [
  { id: 0, title: 'Binary Upload & Partitioning', desc: 'Streaming PDF file into isolated workspace object storage' },
  { id: 1, title: 'Layout & Text Analysis', desc: 'Extracting pages, text blocks, and coordinates via layout engine' },
  { id: 2, title: 'Tables & Visual Charts', desc: 'Parsing Markdown table grids and rendering high-resolution visual crops' },
  { id: 3, title: 'Vector Embeddings & Indexing', desc: 'Computing semantic embeddings and registering collection into vector store' },
  { id: 4, title: 'Fact Grounding & Finalizing', desc: 'Extracting grounded evidence facts and updating workspace knowledge layer' }
];

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
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStageIndex, setUploadStageIndex] = useState(0);
  const [uploadCompleted, setUploadCompleted] = useState(false);
  const [uploadResultSummary, setUploadResultSummary] = useState(null);
  const [uploadError, setUploadError] = useState('');
  const [uploadingFileName, setUploadingFileName] = useState('');
  const [showUploadModal, setShowUploadModal] = useState(false);
  const fileInputRef = useRef(null);
  const heroFileInputRef = useRef(null);

  // Extracted tables & figures
  const [sessionTables, setSessionTables] = useState([]);
  const [sessionFigures, setSessionFigures] = useState([]);
  const [sessionFacts, setSessionFacts] = useState([]);
  const [sessionComparisons, setSessionComparisons] = useState([]);
  const [previewFigure, setPreviewFigure] = useState(null);
  const [reconciliationFilter, setReconciliationFilter] = useState('all');
  const [isReconciling, setIsReconciling] = useState(false);

  // Settings modal state
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [settingsData, setSettingsData] = useState({ provider: 'builtin', is_active: false, model_name: 'builtin', has_gemini: false, masked_key: '' });
  const [inputGeminiKey, setInputGeminiKey] = useState('');
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState('');

  const fetchSettings = async () => {
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      setSettingsData(data);
    } catch (e) {
      console.error('Settings fetch error:', e);
    }
  };

  const handleSaveSettings = async (e) => {
    if (e) e.preventDefault();
    setSettingsSaving(true);
    setSettingsMessage('');
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gemini_api_key: inputGeminiKey.trim() })
      });
      const data = await res.json();
      setSettingsData(data);
      setSettingsMessage(data.has_gemini ? 'Gemini API key saved & active!' : 'API key cleared. Built-in mode active.');
      setInputGeminiKey('');
    } catch (err) {
      setSettingsMessage('Error saving key: ' + err.message);
    } finally {
      setSettingsSaving(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleRecomputeReconciliation = async () => {
    if (!currentSessionId) return;
    setIsReconciling(true);
    try {
      const res = await fetch(`/api/sessions/${currentSessionId}/reconcile`, { method: 'POST' });
      const data = await res.json();
      if (data.comparisons) {
        setSessionComparisons(data.comparisons);
      }
    } catch (e) {
      console.error('Reconciliation error:', e);
    } finally {
      setIsReconciling(false);
    }
  };

  const handleReprocessWorkspace = async () => {
    if (!currentSessionId) return;
    setIsUploading(true);
    setUploadStatus('Reprocessing documents with upgraded visual & semantic extractors...');
    try {
      const res = await fetch(`/api/sessions/${currentSessionId}/reprocess`, { method: 'POST' });
      await res.json();
      await fetchSessions();
      await loadSessionDetails(currentSessionId);
    } catch (e) {
      console.error('Reprocess error:', e);
    } finally {
      setIsUploading(false);
      setUploadStatus('');
    }
  };

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

      if (data.documents && data.documents.length > 0) {
        if (selectDocId) {
          const cleanSelect = String(selectDocId).toLowerCase().trim();
          const target = data.documents.find(d =>
            (d.doc_id && String(d.doc_id).toLowerCase() === cleanSelect) ||
            (d.id && String(d.id).toLowerCase() === cleanSelect) ||
            (d.filename && String(d.filename).toLowerCase() === cleanSelect) ||
            (d.filename && cleanSelect.includes(String(d.filename).toLowerCase())) ||
            (d.title && cleanSelect.includes(String(d.title).toLowerCase()))
          );
          if (target) {
            setSelectedDoc(target);
          } else {
            setSelectedDoc(data.documents[data.documents.length - 1]);
          }
        } else {
          setSelectedDoc(prev => {
            if (prev) {
              const stillExists = data.documents.find(d =>
                d.filename === prev.filename ||
                (d.doc_id && prev.doc_id && d.doc_id === prev.doc_id) ||
                (d.id && prev.id && d.id === prev.id)
              );
              if (stillExists) return stillExists;
            }
            return data.documents[0];
          });
        }
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
    const targetSessionId = deleteWsModal.session.id;
    try {
      const res = await fetch(`/api/sessions/${targetSessionId}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        let errDetail = 'Failed to delete workspace';
        try {
          const err = await res.json();
          errDetail = err.detail || err.message || errDetail;
        } catch {
          const text = await res.text().catch(() => '');
          if (text) errDetail = text;
        }
        if (res.status !== 404) {
          throw new Error(errDetail);
        }
      }

      const updatedRes = await fetch('/api/sessions');
      const updatedSessions = await updatedRes.json();
      setSessions(updatedSessions);

      if (currentSessionId === targetSessionId) {
        if (updatedSessions.length > 0) {
          setCurrentSessionId(updatedSessions[0].id);
        } else {
          setCurrentSessionId(null);
          setSessionData(null);
          setCurrentView('landing');
        }
      }
      await fetchStorageQuota();
      setDeleteWsModal({ isOpen: false, session: null });
      setModalError('');
    } catch (err) {
      setModalError(err.message);
      // Refresh session list just in case it was already deleted on backend
      try {
        const checkRes = await fetch('/api/sessions');
        const list = await checkRes.json();
        setSessions(list);
        if (!list.some(s => s.id === targetSessionId)) {
          setDeleteWsModal({ isOpen: false, session: null });
          setModalError('');
          if (list.length > 0) {
            setCurrentSessionId(list[0].id);
          } else {
            setCurrentSessionId(null);
            setSessionData(null);
            setCurrentView('landing');
          }
        }
      } catch (e) {
        // ignore
      }
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
        let errDetail = 'Failed to delete document';
        try {
          const err = await res.json();
          errDetail = err.detail || err.message || errDetail;
        } catch {
          const text = await res.text().catch(() => '');
          if (text) errDetail = text;
        }
        if (res.status !== 404) {
          throw new Error(errDetail);
        }
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
    setShowUploadModal(true);
    setIsUploading(true);
    setUploadProgress(15);
    setUploadStageIndex(0);
    setUploadCompleted(false);
    setUploadResultSummary(null);
    setUploadError('');
    setUploadingFileName(file.name);

    const formData = new FormData();
    formData.append('file', file);

    // Dynamic stage progression timers while backend processes
    const timer1 = setTimeout(() => {
      setUploadProgress(35);
      setUploadStageIndex(1);
    }, 700);

    const timer2 = setTimeout(() => {
      setUploadProgress(60);
      setUploadStageIndex(2);
    }, 1700);

    const timer3 = setTimeout(() => {
      setUploadProgress(82);
      setUploadStageIndex(3);
    }, 3000);

    const timer4 = setTimeout(() => {
      setUploadProgress(92);
      setUploadStageIndex(4);
    }, 4500);

    try {
      const res = await fetch(`/api/sessions/${currentSessionId}/documents`, {
        method: 'POST',
        body: formData
      });
      const result = await res.json();
      if (!res.ok) throw new Error(result.detail || 'Upload failed');

      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);

      setUploadProgress(100);
      setUploadStageIndex(5);
      setUploadCompleted(true);
      setUploadResultSummary(result);

      // AUTOMATIC STATE REFRESH:
      // 1. Fetch updated sessions list so workspace header & pill shows new doc count
      await fetchSessions();
      // 2. Load latest session details and auto-select the newly uploaded document
      await loadSessionDetails(currentSessionId, result.doc_id || result.filename || file.name);
      // 3. Update global storage quota widget
      await fetchStorageQuota();
      // 4. Ensure view is on workspace
      setCurrentView('workspace');

      // Smoothly dismiss modal after user sees the 100% completion summary
      setTimeout(() => {
        setIsUploading(false);
        setShowUploadModal(false);
        setUploadProgress(0);
        setUploadCompleted(false);
        setUploadResultSummary(null);
        setUploadingFileName('');
      }, 1500);
    } catch (err) {
      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);
      clearTimeout(timer4);
      setUploadError(err.message || 'Failed to process document');
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

  const handleResetChat = () => {
    setChatMessages([
      {
        id: `welcome_${Date.now()}`,
        role: 'assistant',
        content: `Welcome to **${sessionData?.title || 'Interactive Workspace Chat'}**. Ask any question across your uploaded documents, extracted tables, and visual charts!`,
        citations: []
      }
    ]);
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
      if (!f.document && !f.document_name) return true;
      const cleanDoc = selectedDoc.filename.replace(/\.pdf$/i, '').replace(/[-_]/g, ' ').trim().toLowerCase();
      const fDoc = (f.document || f.document_name || '').replace(/\.pdf$/i, '').replace(/[-_]/g, ' ').trim().toLowerCase();
      return fDoc === cleanDoc || (f.document && f.document === selectedDoc.doc_id) || fDoc.includes(cleanDoc) || cleanDoc.includes(fDoc);
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
          <button className="btn-outline" onClick={() => {
            if (navSection !== 'Ask') {
              setNavSection('Ask');
              setActiveTab('Chat');
            }
            handleResetChat();
          }} title="Start a fresh chat in this workspace">
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
            <div
              className="sidebar-item"
              onClick={() => { setShowSettingsModal(true); fetchSettings(); }}
              title="Configure Gemini API Key & Model Settings"
            >
              <Settings size={18} />
              <span>Settings</span>
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
          <div
            className="empty-workspace-view"
            style={{
              gridColumn: '2 / -1',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '60px 20px',
              textAlign: 'center',
              width: '100%',
              minHeight: 'calc(100vh - 100px)'
            }}
          >
            <div style={{ width: 68, height: 68, borderRadius: 18, background: 'rgba(217, 85, 34, 0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18 }}>
              <Folder size={36} color="var(--primary)" />
            </div>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-title)', marginBottom: 8 }}>No Active Workspace</h2>
            <p style={{ color: 'var(--text-muted)', maxWidth: 460, marginBottom: 26, fontSize: '0.95rem', lineHeight: 1.55 }}>
              Create a workspace to upload PDF documents, inspect grounded facts, and ask intelligent questions.
            </p>
            <button
              className="btn-primary"
              onClick={() => handleCreateSession(true)}
              style={{
                padding: '12px 28px',
                fontSize: '0.96rem',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                cursor: 'pointer'
              }}
            >
              <Plus size={18} />
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {selectedDoc && (
                    <button
                      className="btn-outline"
                      style={{ fontSize: '0.78rem', padding: '5px 12px' }}
                      onClick={() => setSelectedDoc(null)}
                    >
                      Query All Documents
                    </button>
                  )}
                  <button
                    className="btn-outline"
                    style={{ fontSize: '0.78rem', padding: '5px 12px', display: 'flex', alignItems: 'center', gap: '5px' }}
                    onClick={handleResetChat}
                    title="Clear current messages and start a fresh chat"
                  >
                    <RotateCcw size={12} />
                    <span>Reset Chat</span>
                  </button>
                </div>
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
                        {msg.role === 'assistant' ? (
                          <FormattedMarkdown content={msg.content} />
                        ) : (
                          msg.content
                        )}
                      </div>

                      {/* Source Evidence Cards */}
                      {msg.citations && msg.citations.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
                          {msg.citations.slice(0, 4).map((cit, citIdx) => {
                            const isFigure = cit.citation_type === 'figure';
                            const isTable = cit.citation_type === 'table';
                            const figImgUrl = cit.image_url || cit.thumbnail_url;
                            const caption = (cit.verbatim_quote || '')
                              .replace(/^\[Visual Asset\]\s*/i, '')
                              .replace(/^\[Structured Table\]\s*/i, '');

                            if (isFigure) {
                              return (
                                <div key={citIdx} className="evidence-figure-card">
                                  <div className="evidence-badge-header">
                                    <div className="evidence-badge-left">
                                      <Image size={14} color="var(--primary)" />
                                      <span className="evidence-type-title">Visual Evidence</span>
                                      <span className="evidence-doc-stem">{cit.document_name}</span>
                                    </div>
                                    <span className="evidence-page-chip">Page {cit.page_number}</span>
                                  </div>

                                  <div className="evidence-figure-body">
                                    <div
                                      className="evidence-figure-preview"
                                      onClick={() => setPreviewFigure({
                                        url: figImgUrl,
                                        caption: caption,
                                        page_number: cit.page_number,
                                        figure_id: 'visual_citation'
                                      })}
                                      title="Click to zoom / inspect high-resolution chart"
                                    >
                                      <img
                                        src={figImgUrl}
                                        alt={caption}
                                        className="evidence-figure-img"
                                        onError={(e) => {
                                          e.currentTarget.style.display = 'none';
                                          const fb = e.currentTarget.parentElement?.querySelector('.evidence-figure-fallback');
                                          if (fb) fb.style.display = 'flex';
                                        }}
                                      />
                                      <div className="evidence-figure-fallback" style={{ display: 'none' }}>
                                        <Image size={24} color="var(--text-muted)" />
                                        <span>Visual diagram preview</span>
                                      </div>
                                      <div className="evidence-figure-zoom-overlay">
                                        <ZoomIn size={13} /> Click to inspect high-res diagram
                                      </div>
                                    </div>

                                    <div className="evidence-figure-caption-bar">
                                      <span className="evidence-figure-caption-text">{caption}</span>
                                      <button
                                        type="button"
                                        className="evidence-inspect-btn"
                                        onClick={() => setPreviewFigure({
                                          url: figImgUrl,
                                          caption: caption,
                                          page_number: cit.page_number,
                                          figure_id: 'visual_citation'
                                        })}
                                      >
                                        <ZoomIn size={12} /> Inspect
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              );
                            }

                            return (
                              <div key={citIdx} className="source-evidence-card">
                                <div className="evidence-badge-header">
                                  <div className="evidence-badge-left">
                                    {isTable ? <Table size={13} color="var(--primary)" /> : <FileText size={13} color="var(--primary)" />}
                                    <span>{isTable ? 'Structured Table' : 'Source Evidence'}</span>
                                    <span className="evidence-doc-stem">{cit.document_name}</span>
                                  </div>
                                  <span className="evidence-page-chip">Page {cit.page_number}</span>
                                </div>

                                <div className="evidence-snippet-preview">
                                  {cit.thumbnail_url && (
                                    <div
                                      className="evidence-mini-thumb"
                                      style={{ cursor: 'pointer' }}
                                      onClick={() => setPreviewFigure({
                                        url: cit.thumbnail_url,
                                        caption: `Page ${cit.page_number} Evidence Thumbnail`,
                                        page_number: cit.page_number,
                                        figure_id: `page_${cit.page_number}`
                                      })}
                                      title="Click to inspect page thumbnail"
                                    >
                                      <img
                                        src={cit.thumbnail_url}
                                        alt="Page Evidence"
                                        onError={(e) => {
                                          if (e.currentTarget.parentElement) {
                                            e.currentTarget.parentElement.style.display = 'none';
                                          }
                                        }}
                                      />
                                    </div>
                                  )}
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', minWidth: 0, flex: 1 }}>
                                    <p className="evidence-quote-text">
                                      "{cit.verbatim_quote}"
                                    </p>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {isAsking && (
                  <div className="chat-bubble-ai thinking-bubble">
                    <div className="ai-avatar-icon">
                      <Sparkles size={16} className="spinning-sparkle" />
                    </div>
                    <div className="ai-content-body">
                      <div className="ai-thinking-indicator">
                        <span className="ai-thinking-dot"></span>
                        <span className="ai-thinking-dot"></span>
                        <span className="ai-thinking-dot"></span>
                        <span className="ai-thinking-text">Analyzing documents, tables & visual diagrams with Gemini...</span>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Search Bar at Bottom Centre */}
              <div className="ask-bottom-center-wrapper">
                {chatMessages.length <= 1 && (
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
                )}

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
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <div>
                          <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>
                            Figures & Visual Diagrams ({docFigures.length})
                          </h3>
                          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '2px 0 0 0' }}>
                            Extracted vector charts, graphs, and visual figures with exact page grounding. Click any figure to inspect in high resolution.
                          </p>
                        </div>
                        <button
                          className="modal-btn-cancel"
                          onClick={handleReprocessWorkspace}
                          disabled={isUploading}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', padding: '6px 12px' }}
                        >
                          <RefreshCw size={13} className={isUploading ? 'spin-animation' : ''} />
                          {isUploading ? 'Reprocessing...' : 'Refresh Figures'}
                        </button>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '16px' }}>
                        {docFigures.map((fig, i) => (
                          <div
                            key={i}
                            onClick={() => setPreviewFigure(fig)}
                            style={{
                              border: '1px solid var(--border-subtle)',
                              borderRadius: '12px',
                              overflow: 'hidden',
                              background: '#ffffff',
                              display: 'flex',
                              flexDirection: 'column',
                              cursor: 'pointer',
                              transition: 'all 0.2s ease',
                              boxShadow: '0 2px 8px rgba(0,0,0,0.03)'
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.transform = 'translateY(-2px)';
                              e.currentTarget.style.boxShadow = '0 6px 16px rgba(0,0,0,0.08)';
                              e.currentTarget.style.borderColor = 'var(--primary)';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.transform = 'none';
                              e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.03)';
                              e.currentTarget.style.borderColor = 'var(--border-subtle)';
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: '#faf8f5', borderBottom: '1px solid var(--border-subtle)' }}>
                              <span className="reconciliation-citation-badge page" style={{ fontSize: '0.72rem', padding: '2px 7px' }}>
                                Page {fig.page_number || '?'}
                              </span>
                              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>
                                {fig.type === 'chart' ? 'Vector Chart' : 'Embedded Visual'}
                              </span>
                            </div>
                            <div style={{ padding: '12px', background: '#fdfcf9', display: 'flex', alignItems: 'center', justifyContent: 'center', height: '170px' }}>
                              <img
                                src={fig.url}
                                alt={fig.caption || fig.figure_id}
                                style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                              />
                            </div>
                            <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border-subtle)', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                              <p style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-title)', margin: 0, lineHeight: 1.35, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                {fig.caption || fig.figure_id}
                              </p>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                                <span>{fig.width && fig.height ? `${fig.width}×${fig.height}px` : ''}</span>
                                <span style={{ color: 'var(--primary)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                  <ZoomIn size={12} /> Inspect
                                </span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                      {docFigures.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '40px 16px', background: '#faf8f5', borderRadius: '12px', border: '1px dashed var(--border-subtle)' }}>
                          <Image size={36} color="var(--text-muted)" style={{ margin: '0 auto 12px' }} />
                          <p style={{ color: 'var(--text-title)', fontWeight: 600, marginBottom: '6px' }}>No figures or diagrams loaded yet</p>
                          <p style={{ color: 'var(--text-muted)', fontSize: '0.84rem', maxWidth: '400px', margin: '0 auto 16px' }}>
                            Run the upgraded hybrid figure extractor on this document to render vector charts and embedded images.
                          </p>
                          <button className="modal-btn-primary" onClick={handleReprocessWorkspace} style={{ padding: '8px 18px', fontSize: '0.85rem' }}>
                            <RefreshCw size={14} style={{ marginRight: '6px' }} /> Extract Document Figures
                          </button>
                        </div>
                      )}
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

                  {/* TAB 5: Fact Reconciliation */}
                  {activeTab === 'Reconciliation' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 0', minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                        <div>
                          <h3 style={{ fontSize: '1.05rem', fontWeight: 700 }}>
                            {activeSessionObj?.documents?.length <= 1
                              ? `Fact Verification & Reconciliation Matrix (${sessionComparisons.length})`
                              : `Cross-Document Reconciliation Matrix (${sessionComparisons.length})`}
                          </h3>
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                            Automated semantic reasoning with exact page, table & metric citations
                          </span>
                        </div>
                        <button
                          onClick={handleRecomputeReconciliation}
                          disabled={isReconciling}
                          style={{
                            padding: '6px 12px',
                            borderRadius: '8px',
                            fontSize: '0.78rem',
                            fontWeight: 600,
                            border: '1px solid var(--border-subtle)',
                            background: '#ffffff',
                            color: 'var(--text-body)',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '6px',
                            transition: 'all 0.15s ease'
                          }}
                        >
                          <RefreshCw size={13} className={isReconciling ? 'spin-animation' : ''} />
                          {isReconciling ? 'Reconciling...' : 'Re-run Matrix'}
                        </button>
                      </div>

                      {/* Filter Chips Bar */}
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
                        {[
                          { id: 'all', label: 'All', count: sessionComparisons.length },
                          { id: 'corroboration', label: 'Corroboration', count: sessionComparisons.filter(c => c.relationship_type === 'corroboration').length },
                          { id: 'reconciled', label: 'Reconciled', count: sessionComparisons.filter(c => c.relationship_type === 'reconciled').length },
                          { id: 'contradiction', label: 'Contradiction', count: sessionComparisons.filter(c => c.relationship_type === 'contradiction').length },
                          { id: 'extraction_failure', label: 'Handled Edge Cases', count: sessionComparisons.filter(c => c.relationship_type === 'extraction_failure').length }
                        ].map(f => (
                          <button
                            key={f.id}
                            onClick={() => setReconciliationFilter(f.id)}
                            style={{
                              padding: '5px 12px',
                              borderRadius: '20px',
                              fontSize: '0.78rem',
                              fontWeight: 600,
                              border: '1px solid',
                              cursor: 'pointer',
                              transition: 'all 0.15s ease',
                              background: reconciliationFilter === f.id ? 'var(--primary)' : '#ffffff',
                              color: reconciliationFilter === f.id ? '#ffffff' : 'var(--text-body)',
                              borderColor: reconciliationFilter === f.id ? 'var(--primary)' : 'var(--border-subtle)'
                            }}
                          >
                            {f.label} ({f.count})
                          </button>
                        ))}
                      </div>

                      {/* Informative Single-Doc Banner */}
                      {activeSessionObj?.documents?.length <= 1 && (
                        <div style={{ padding: '12px 16px', background: '#fdf8ef', border: '1px solid #f0e2cc', borderRadius: '10px', marginBottom: '16px', fontSize: '0.82rem', color: '#7a5418', lineHeight: 1.45, display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontSize: '1.2rem' }}>💡</span>
                          <div>
                            <strong>Intra-Document Verification Mode:</strong> Validating consistency across text statements, tables, reporting scopes (BE vs RE vs Actuals), and accounting notation within this document. Upload a second document to compare cross-document claims!
                          </div>
                        </div>
                      )}

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        {sessionComparisons
                          .filter(c => reconciliationFilter === 'all' || c.relationship_type === reconciliationFilter)
                          .map((c, i) => (
                            <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '18px', background: '#faf8f5', boxShadow: '0 2px 8px rgba(0,0,0,0.02)' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                  {c.relationship_type === 'corroboration' && <CheckCircle2 size={17} color="var(--success)" />}
                                  {c.relationship_type === 'contradiction' && <AlertTriangle size={17} color="var(--danger)" />}
                                  {c.relationship_type === 'reconciled' && <GitCompare size={17} color="var(--primary)" />}
                                  {c.relationship_type === 'extraction_failure' && <ShieldAlert size={17} color="#d97706" />}
                                  <h4 style={{ fontSize: '0.98rem', fontWeight: 700, color: 'var(--text-title)', margin: 0 }}>{c.title}</h4>
                                </div>
                                <span style={{
                                  textTransform: 'uppercase',
                                  fontSize: '0.72rem',
                                  fontWeight: 700,
                                  padding: '4px 10px',
                                  borderRadius: '4px',
                                  background: c.relationship_type === 'corroboration' ? 'var(--success-bg)' : c.relationship_type === 'contradiction' ? 'var(--danger-bg)' : c.relationship_type === 'reconciled' ? 'var(--primary-light)' : '#fef3c7',
                                  color: c.relationship_type === 'corroboration' ? 'var(--success)' : c.relationship_type === 'contradiction' ? 'var(--danger)' : c.relationship_type === 'reconciled' ? 'var(--primary)' : '#b45309'
                                }}>
                                  {c.relationship_type.replace('_', ' ')}
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
                                <div style={{ display: 'grid', gridTemplateColumns: c.fact_b ? '1fr 1fr' : '1fr', gap: '12px', marginTop: '10px' }}>
                                  {c.fact_a && (
                                    <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
                                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                                        <span style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-title)' }}>
                                          {c.fact_a.evidence?.document_name || 'Document Citation A'}
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
                                        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontStyle: 'italic', margin: 0, lineHeight: 1.4 }}>
                                          "{c.fact_a.evidence.verbatim_quote}"
                                        </p>
                                      )}
                                    </div>
                                  )}

                                  {c.fact_b && (
                                    <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px' }}>
                                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                                        <span style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-title)' }}>
                                          {c.fact_b.evidence?.document_name || 'Document Citation B'}
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
                                        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontStyle: 'italic', margin: 0, lineHeight: 1.4 }}>
                                          "{c.fact_b.evidence.verbatim_quote}"
                                        </p>
                                      )}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}

                        {sessionComparisons.filter(c => reconciliationFilter === 'all' || c.relationship_type === reconciliationFilter).length === 0 && (
                          <div style={{ textAlign: 'center', padding: '30px 10px', color: 'var(--text-muted)', background: '#faf8f5', borderRadius: '10px', border: '1px dashed var(--border-subtle)' }}>
                            No comparisons matching '{reconciliationFilter}' found in this workspace.
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

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="modal-backdrop" onClick={() => setShowSettingsModal(false)}>
          <div className="custom-modal-card" style={{ maxWidth: '520px' }} onClick={(e) => e.stopPropagation()}>
            <div className="custom-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Settings size={18} color="var(--primary)" />
                <h3 style={{ margin: 0 }}>API & Model Settings</h3>
              </div>
              <button
                className="custom-modal-close-btn"
                onClick={() => setShowSettingsModal(false)}
              >
                <X size={16} />
              </button>
            </div>

            <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Provider Status Pill */}
              <div style={{
                background: settingsData.has_gemini ? 'var(--success-bg)' : '#f5f3ef',
                border: `1px solid ${settingsData.has_gemini ? 'var(--success)' : 'var(--border-subtle)'}`,
                borderRadius: '10px',
                padding: '12px 14px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  {settingsData.has_gemini ? <CheckCircle2 size={16} color="var(--success)" /> : <Sparkles size={16} color="var(--text-muted)" />}
                  <div>
                    <div style={{ fontSize: '0.86rem', fontWeight: 700, color: 'var(--text-title)' }}>
                      {settingsData.has_gemini ? 'Google Gemini Active' : 'Deterministic Extractor Mode'}
                    </div>
                    <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                      Model: {settingsData.model_name || 'gemini-1.5-flash'} {settingsData.masked_key ? `(${settingsData.masked_key})` : ''}
                    </div>
                  </div>
                </div>
                <span style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  padding: '3px 8px',
                  borderRadius: '4px',
                  background: settingsData.has_gemini ? '#dcfce7' : '#e5e2dc',
                  color: settingsData.has_gemini ? '#15803d' : '#6b7280'
                }}>
                  {settingsData.has_gemini ? 'ONLINE' : 'BUILTIN'}
                </span>
              </div>

              {/* API Key Form */}
              <form onSubmit={handleSaveSettings} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-title)', marginBottom: '6px' }}>
                    Google Gemini API Key
                  </label>
                  <input
                    type="password"
                    placeholder={settingsData.has_gemini ? "API Key is configured (enter new to update)..." : "Paste your GEMINI_API_KEY here..."}
                    value={inputGeminiKey}
                    onChange={(e) => setInputGeminiKey(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      border: '1px solid var(--border-subtle)',
                      background: '#ffffff',
                      fontSize: '0.88rem',
                      color: 'var(--text-title)',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                </div>

                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.4, background: '#faf8f5', padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
                  🔒 <strong>Grounded Operation Guarantee:</strong> Gemini is strictly constrained to the verified text blocks, structured tables, and visual chart crops extracted in this workspace. No heavy ungrounded computation or open web hallucination.
                </div>

                {settingsMessage && (
                  <div style={{ fontSize: '0.82rem', color: settingsMessage.includes('Error') ? 'var(--danger)' : 'var(--success)', fontWeight: 600 }}>
                    {settingsMessage}
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '4px' }}>
                  <button
                    type="button"
                    className="btn-outline"
                    onClick={() => setShowSettingsModal(false)}
                    style={{ padding: '8px 16px', fontSize: '0.84rem' }}
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    className="modal-btn-primary"
                    disabled={settingsSaving || !inputGeminiKey.trim()}
                    style={{ padding: '8px 18px', fontSize: '0.84rem' }}
                  >
                    {settingsSaving ? 'Saving...' : 'Save API Key'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Upload Modal with Multi-Stage Buffering Monitor */}
      {showUploadModal && (
        <div className="modal-backdrop" onClick={() => !isUploading && setShowUploadModal(false)}>
          <div className="modal-dialog" style={{ maxWidth: '520px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Upload size={20} color="var(--primary)" />
                {isUploading || uploadCompleted ? 'Ingesting Document' : 'Upload PDF to Workspace'}
              </h3>
              {!isUploading && (
                <X size={18} style={{ cursor: 'pointer', color: 'var(--text-muted)' }} onClick={() => setShowUploadModal(false)} />
              )}
            </div>

            {isUploading || uploadCompleted ? (
              <div className="upload-buffering-card">
                <div className="upload-buffering-header">
                  <span style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--text-title)' }}>
                    {uploadCompleted ? 'Ingestion Complete!' : (uploadingFileName || 'Processing Document...')}
                  </span>
                  <span className="upload-pct-badge">{uploadProgress}%</span>
                </div>

                {/* Progress bar track with animated shimmer */}
                <div className="upload-progress-track">
                  <div className="upload-progress-fill" style={{ width: `${uploadProgress}%` }}>
                    <div className="upload-progress-shimmer" />
                  </div>
                </div>

                {/* Current Active Stage Banner */}
                <div className="upload-active-stage-banner">
                  {uploadCompleted ? (
                    <CheckCircle2 size={24} color="var(--success)" style={{ flexShrink: 0 }} />
                  ) : (
                    <RefreshCw size={22} className="spin-animation" color="var(--primary)" style={{ flexShrink: 0 }} />
                  )}
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="upload-active-stage-title">
                      {uploadCompleted
                        ? 'Knowledge Layer Ready'
                        : UPLOAD_STAGES[Math.min(uploadStageIndex, UPLOAD_STAGES.length - 1)]?.title}
                    </div>
                    <div className="upload-active-stage-desc">
                      {uploadCompleted
                        ? 'Workspace state refreshed automatically with full visual grounding.'
                        : UPLOAD_STAGES[Math.min(uploadStageIndex, UPLOAD_STAGES.length - 1)]?.desc}
                    </div>
                  </div>
                </div>

                {/* Stepper Stage Rows */}
                <div className="upload-stepper-list">
                  {UPLOAD_STAGES.map((stg, idx) => {
                    const isDone = uploadCompleted || uploadStageIndex > idx;
                    const isActive = !uploadCompleted && uploadStageIndex === idx;
                    return (
                      <div
                        key={stg.id}
                        className={`upload-step-row ${isDone ? 'completed' : ''} ${isActive ? 'active' : ''}`}
                      >
                        {isDone ? (
                          <CheckCircle2 size={15} color="var(--success)" style={{ flexShrink: 0 }} />
                        ) : isActive ? (
                          <RefreshCw size={14} className="spin-animation" color="var(--primary)" style={{ flexShrink: 0 }} />
                        ) : (
                          <div className="upload-step-dot" />
                        )}
                        <span>{stg.title}</span>
                      </div>
                    );
                  })}
                </div>

                {/* Extracted Metrics Summary on Complete */}
                {uploadCompleted && uploadResultSummary && (
                  <div className="upload-metrics-pills">
                    <span className="upload-metric-pill">
                      <FileText size={13} /> {uploadResultSummary.pages || 1} Pages
                    </span>
                    <span className="upload-metric-pill">
                      <Layers size={13} /> {uploadResultSummary.blocks || 0} Text Blocks
                    </span>
                    <span className="upload-metric-pill">
                      <Table size={13} /> {uploadResultSummary.tables || 0} Tables
                    </span>
                    <span className="upload-metric-pill">
                      <Image size={13} /> {uploadResultSummary.figures || 0} Figures
                    </span>
                    {uploadResultSummary.new_facts > 0 && (
                      <span className="upload-metric-pill">
                        <Sparkles size={13} /> {uploadResultSummary.new_facts} Facts
                      </span>
                    )}
                  </div>
                )}
              </div>
            ) : uploadError ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', padding: '12px 0' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--danger)', background: '#fdf2f2', padding: '12px 14px', borderRadius: '8px', border: '1px solid #fecaca' }}>
                  <AlertTriangle size={20} style={{ flexShrink: 0 }} />
                  <span style={{ fontSize: '0.86rem', fontWeight: 600 }}>{uploadError}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                  <button className="btn-outline" onClick={() => { setUploadError(''); }}>
                    Try Again
                  </button>
                  <button className="modal-btn-confirm" onClick={() => setShowUploadModal(false)}>
                    Close
                  </button>
                </div>
              </div>
            ) : (
              <>
                <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
                  Select or drag a PDF document. Text, structured tables, visual figures, and grounded facts will be extracted into this workspace.
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
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Stored in isolated workspace partition</span>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="application/pdf"
                    style={{ display: 'none' }}
                    onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '16px' }}>
                  <button className="btn-outline" onClick={() => setShowUploadModal(false)}>
                    Cancel
                  </button>
                </div>
              </>
            )}
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

      {/* Figure Lightbox / Zoom Modal */}
      {previewFigure && (
        <div className="modal-backdrop" onClick={() => setPreviewFigure(null)} style={{ background: 'rgba(0, 0, 0, 0.82)', backdropFilter: 'blur(6px)', zIndex: 1100 }}>
          <div className="custom-modal-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '960px', width: '92vw', maxHeight: '92vh', display: 'flex', flexDirection: 'column', padding: '0', overflow: 'hidden' }}>
            <div className="custom-modal-header" style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)', background: '#ffffff' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span className="reconciliation-citation-badge page" style={{ fontSize: '0.8rem', padding: '3px 8px' }}>
                  Page {previewFigure.page_number}
                </span>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0, color: 'var(--text-title)' }}>
                  {previewFigure.caption || previewFigure.figure_id}
                </h3>
              </div>
              <button
                className="custom-modal-close-btn"
                onClick={() => setPreviewFigure(null)}
              >
                <X size={20} />
              </button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', background: '#f8f6f0', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
              <img
                src={previewFigure.url}
                alt={previewFigure.caption || previewFigure.figure_id}
                style={{ maxWidth: '100%', maxHeight: '68vh', objectFit: 'contain', borderRadius: '6px', boxShadow: '0 4px 20px rgba(0,0,0,0.12)' }}
              />
            </div>
            <div className="custom-modal-footer" style={{ padding: '12px 20px', background: '#ffffff', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {previewFigure.width && previewFigure.height ? `${previewFigure.width} × ${previewFigure.height} px • ` : ''}
                {previewFigure.type === 'chart' ? 'Vector Chart Clip (150 DPI)' : 'Embedded Visual Asset'}
              </span>
              <div style={{ display: 'flex', gap: '10px' }}>
                <a
                  href={previewFigure.url}
                  target="_blank"
                  rel="noreferrer"
                  className="modal-btn-cancel"
                  style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
                >
                  <ExternalLink size={15} /> Open Full Size
                </a>
                <a
                  href={previewFigure.url}
                  download={`${previewFigure.figure_id}.png`}
                  className="modal-btn-primary"
                  style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'var(--primary)', color: '#fff', padding: '8px 14px', borderRadius: '8px', fontSize: '0.85rem', fontWeight: 600 }}
                >
                  <Download size={15} /> Download PNG
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
