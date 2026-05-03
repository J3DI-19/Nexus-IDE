import React, { useState, useEffect, useRef } from 'react';
import { PanelLeft, PanelRight, Layers, ChevronDown, ChevronUp, Replace } from 'lucide-react';
import Explorer from './components/Explorer';
import Editor from './components/Editor';
import RightPanel from './components/RightPanel';
import { buildTree, FileNode } from './utils/buildTree';

const API_BASE = 'http://localhost:5000';

export type Tab = {
  path: string;
  content: string;
};

const App: React.FC = () => {
  const [tree, setTree] = useState<FileNode[]>([]);
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTabPath, setActiveTabPath] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // 🔥 FIX: useRef instead of state
  const editorRef = useRef<any>(null);

  const [showExplorer, setShowExplorer] = useState(true);
  const [showRightPanel, setShowRightPanel] = useState(true);

  useEffect(() => {
    fetchProject();
  }, []);

  const fetchProject = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/scan`);
      if (!res.ok) throw new Error('Failed to scan project');
      const data = await res.json();
      setTree(buildTree(data.files));
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = async (path: string) => {
    const existingTab = tabs.find(t => t.path === path);
    if (existingTab) {
      setActiveTabPath(path);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/file?path=${encodeURIComponent(path)}`);
      if (!res.ok) throw new Error(`Failed to load: ${res.status}`);
      const text = await res.text();

      const newTab = { path, content: text };
      setTabs(prev => [...prev, newTab]);
      setActiveTabPath(path);
    } catch (err: any) {
      console.error('[IDE] Error:', err);
    }
  };

  const handleCloseTab = (e: React.MouseEvent, path: string) => {
    e.stopPropagation();
    const newTabs = tabs.filter(t => t.path !== path);
    setTabs(newTabs);

    if (activeTabPath === path) {
      setActiveTabPath(newTabs.length ? newTabs[newTabs.length - 1].path : null);
    }
  };

  const activeTab = tabs.find(t => t.path === activeTabPath) || null;

  // ===== SEARCH ACTIONS =====
  const triggerAction = (actionId: string) => {
    const editor = editorRef.current;
    if (!editor) return;

    editor.focus();
    editor.getAction(actionId)?.run();
  };

  return (
    <div className="flex h-full w-full overflow-hidden">

      {/* ===== LEFT PANEL ===== */}
      {showExplorer && (
        <div className="sidebar flex flex-col active-context">
          <div className="sidebar-header">

            {/* LEFT SPACER */}
            <div className="header-spacer" />

            {/* CENTER TITLE */}
            <div className="explorer-title">
              Explorer
            </div>

            {/* RIGHT BUTTON */}
            <div
              className="btn-icon"
              onClick={() => setShowExplorer(false)}
            >
              <PanelLeft size={16} />
            </div>

          </div>

          <div className="flex-1 overflow-hidden pt-2">
            {loading ? (
              <div className="p-16 text-[10px] opacity-50 italic">Scanning...</div>
            ) : error ? (
              <div className="p-16 text-[10px] text-red-400">Error: {error}</div>
            ) : (
              <Explorer
                tree={tree}
                selectedPath={activeTabPath}
                onFileSelect={handleFileSelect}
              />
            )}
          </div>
        </div>
      )}

      {/* ===== MAIN AREA ===== */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* ===== HEADER ===== */}
        <div className="app-header">

          {/* LEFT */}
          <div className="header-left">
            {!showExplorer && (
              <div className="btn-icon" onClick={() => setShowExplorer(true)}>
                <PanelLeft size={16} />
              </div>
            )}

            <div className="logo-icon">{">_"}</div>
            <div className="logo-text">
              NEXUS <span className="accent">IDE</span>
            </div>
          </div>

          {/* CENTER SEARCH */}
          <div className="header-search">
            <input
              className="search-input"
              placeholder="Search in file..."
              onFocus={() => triggerAction('actions.find')}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  triggerAction('editor.action.nextMatchFindAction');
                }
              }}
            />

            <div className="search-actions">
              <button
                className="search-btn"
                onClick={() => triggerAction('editor.action.previousMatchFindAction')}
              >
                <ChevronUp size={12} />
              </button>

              <button
                className="search-btn"
                onClick={() => triggerAction('editor.action.nextMatchFindAction')}
              >
                <ChevronDown size={12} />
              </button>

              <button
                className="search-btn"
                onClick={() => triggerAction('editor.action.startFindReplaceAction')}
              >
                <Replace size={12} />
              </button>
            </div>
          </div>

          {/* RIGHT */}
          <div className="header-right">
            {!showRightPanel && (
              <div className="btn-icon" onClick={() => setShowRightPanel(true)}>
                <PanelRight size={16} />
              </div>
            )}
          </div>
        </div>

        {/* ===== EDITOR ===== */}
        <div className="flex-1 overflow-hidden">
          <Editor
            activeTab={activeTab}
            tabs={tabs}
            onSelectTab={setActiveTabPath}
            onCloseTab={handleCloseTab}
            onMount={(editor) => {
              editorRef.current = editor;
            }}
          />
        </div>
      </div>

      {/* ===== RIGHT PANEL ===== */}
      {showRightPanel && (
        <div className="right-panel flex flex-col">
          <div className="sidebar-header">

            {/* LEFT SPACER */}
            <div className="header-spacer" />

            {/* CENTER TITLE */}
            <div className="explorer-title">
              Intelligence
            </div>

            {/* RIGHT BUTTON */}
            <div className="btn-icon" onClick={() => setShowRightPanel(false)}>
              <PanelRight size={16} />
            </div>

          </div>

          <RightPanel activeTab={activeTab} />
        </div>
      )}

    </div>
  );
};

export default App;