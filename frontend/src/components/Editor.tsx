import React from 'react';
import MonacoEditor from '@monaco-editor/react';
import { X, FileCode } from 'lucide-react';
import { Tab } from '../App';

interface EditorProps {
  activeTab: Tab | null;
  tabs: Tab[];
  onSelectTab: (path: string) => void;
  onCloseTab: (e: React.MouseEvent, path: string) => void;
}

const getLanguage = (path: string | null) => {
  if (!path) return 'text';
  const ext = path.split('.').pop()?.toLowerCase();

  switch (ext) {
    case 'js': return 'javascript';
    case 'jsx': return 'javascript';
    case 'ts': return 'typescript';
    case 'tsx': return 'typescript';
    case 'py': return 'python';
    case 'css': return 'css';
    case 'html': return 'html';
    case 'json': return 'json';
    case 'md': return 'markdown';
    default: return 'text';
  }
};

const Editor: React.FC<EditorProps> = ({
  activeTab,
  tabs,
  onSelectTab,
  onCloseTab
}) => {

  // ===== WELCOME STATE =====
  if (!activeTab && tabs.length === 0) {
    return (
      <div className="editor-root">
        <div className="welcome-container">
          <div className="welcome-inner">

            <div className="welcome-icon">{">_"}</div>

            <h1 className="welcome-title">
              NEXUS <span className="accent">IDE</span>
            </h1>

            <p className="welcome-subtitle">
              Local AI-powered development environment
            </p>

            <p className="welcome-hint">
              Select a file from the explorer to begin
            </p>

          </div>
        </div>
      </div>
    );
  }

  // ===== EDITOR STATE =====
  return (
    <div className="editor-root">

      {/* TAB BAR */}
      <div className="tab-bar">
        {tabs.map((tab) => {
          const isActive = activeTab?.path === tab.path;

          return (
            <div
              key={tab.path}
              onClick={() => onSelectTab(tab.path)}
              className={`tab ${isActive ? 'active' : ''}`}
            >
              <FileCode size={14} className="opacity-70" />

              <span className="truncate">
                {tab.path.split('/').pop()}
              </span>

              <div
                className="tab-close"
                onClick={(e) => {
                  e.stopPropagation(); // 🔥 IMPORTANT FIX
                  onCloseTab(e, tab.path);
                }}
              >
                <X size={12} />
              </div>
            </div>
          );
        })}
      </div>

      {/* MONACO */}
      <div className="editor-container">
        {activeTab && (
          <MonacoEditor
            key={activeTab.path} // 🔥 FORCE CLEAN RE-MOUNT (fixes black screen)
            height="100%"
            width="100%"
            theme="vs-dark"
            path={activeTab.path}
            language={getLanguage(activeTab.path)}
            value={activeTab.content || ""} // 🔥 SAFETY FIX
            options={{
              readOnly: true,
              minimap: { enabled: true },
              fontSize: 14,
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 2,
              wordWrap: 'on',
              lineNumbers: 'on',
              padding: { top: 16 },
              fontFamily: "var(--font-mono)",
              renderLineHighlight: 'all'
            }}
          />
        )}
      </div>

    </div>
  );
};

export default Editor;
