import React, { useRef } from 'react';
import MonacoEditor from '@monaco-editor/react';
import { X, FileCode } from 'lucide-react';
import { Tab } from '../App';

interface EditorProps {
  activeTab: Tab | null;
  tabs: Tab[];
  onSelectTab: (path: string) => void;
  onCloseTab: (e: React.MouseEvent, path: string) => void;
  onContentChange?: (path: string, content: string) => void;
}

const getLanguage = (path: string | null) => {
  if (!path) return 'text';
  const fileName = path.split('/').pop()?.toLowerCase() || '';
  const ext = path.split('.').pop()?.toLowerCase();

  if (fileName === 'dockerfile') return 'dockerfile';
  if (fileName === '.env') return 'shell';
  if (fileName === 'makefile') return 'plaintext';
  if (fileName === 'cmakelists.txt') return 'cmake';

  switch (ext) {
    case 'js': return 'javascript';
    case 'jsx': return 'javascript';
    case 'ts': return 'typescript';
    case 'tsx': return 'typescript';
    case 'py': return 'python';
    case 'java': return 'java';
    case 'c': return 'c';
    case 'h': return 'c';
    case 'cpp': return 'cpp';
    case 'cc': return 'cpp';
    case 'cxx': return 'cpp';
    case 'hpp': return 'cpp';
    case 'cs': return 'csharp';
    case 'go': return 'go';
    case 'rs': return 'rust';
    case 'php': return 'php';
    case 'rb': return 'ruby';
    case 'kt': return 'kotlin';
    case 'swift': return 'swift';
    case 'sql': return 'sql';
    case 'xml': return 'xml';
    case 'yaml': return 'yaml';
    case 'yml': return 'yaml';
    case 'toml': return 'ini';
    case 'sh': return 'shell';
    case 'bash': return 'shell';
    case 'zsh': return 'shell';
    case 'ps1': return 'powershell';
    case 'env': return 'shell';
    case 'css': return 'css';
    case 'scss': return 'scss';
    case 'less': return 'less';
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
  onCloseTab,
  onContentChange
}) => {

  const editorRef = useRef<any>(null);

  // Simple Global Jump Listener (Decoupled from React state complexity)
  React.useEffect(() => {
    const handleJump = (e: any) => {
      const { path, line } = e.detail;
      if (!editorRef.current || !activeTab || activeTab.path !== path) return;

      console.log('[IDE] Global Jump Received for:', path, 'Line:', line);
      
      const editor = editorRef.current;
      
      // Delay jump slightly to ensure Monaco has finished re-rendering if the tab just changed
      setTimeout(() => {
        editor.revealLineInCenter(line);
        editor.setPosition({ lineNumber: line, column: 1 });
        editor.focus();
        
        // Force "typing mode" by simulating a small cursor movement or just ensuring focus is deep
        const domNode = editor.getDomNode();
        if (domNode) {
          const textarea = domNode.querySelector('textarea');
          if (textarea) textarea.focus();
        }
      }, 100);
    };

    window.addEventListener('nexus-editor-jump', handleJump);
    return () => window.removeEventListener('nexus-editor-jump', handleJump);
  }, [activeTab]);

  const handleEditorDidMount = (editor: any) => {
    editorRef.current = editor;
  };

  // ===== WELCOME STATE =====
  if (!activeTab && tabs.length === 0) {
    return (
      <div className="editor-root">
        <div className="welcome-container">
          <div className="welcome-inner">
            <div className="welcome-icon">{">_"}</div>
            <h1 className="welcome-title">NEXUS <span className="accent">IDE</span></h1>
            <p className="welcome-subtitle">Local AI-powered development environment</p>
            <p className="welcome-hint">Select a file from the explorer to begin</p>
          </div>
        </div>
      </div>
    );
  }

  // ===== EDITOR STATE =====
  const safeTabs = Array.isArray(tabs) ? tabs : [];

  return (
    <div className="editor-root">
      <div className="tab-bar">
        {safeTabs.map((tab) => {
          const isActive = activeTab?.path === tab.path;
          return (
            <div
              key={tab.path}
              onClick={() => onSelectTab(tab.path)}
              className={`tab ${isActive ? 'active' : ''} ${tab.isDirty ? 'dirty' : ''}`}
            >
              <FileCode size={14} className="opacity-70" />
              <span className="tab-title truncate">
                {tab.path.split('/').pop()}
                {tab.isDirty && <span className="tab-dirty-indicator">●</span>}
              </span>
              <div
                className="tab-close"
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(e, tab.path);
                }}
              >
                <X size={12} />
              </div>
            </div>
          );
        })}
      </div>

      <div className="editor-container">
        {activeTab && (
          <MonacoEditor
            key={activeTab.path} 
            height="100%"
            width="100%"
            theme="vs-dark"
            path={activeTab.path}
            language={getLanguage(activeTab.path)}
            value={activeTab.content || ""} 
            onMount={handleEditorDidMount}
            onChange={(val) => {
              if (val !== undefined && onContentChange) {
                onContentChange(activeTab.path, val);
              }
            }}
            options={{
              readOnly: false,
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
