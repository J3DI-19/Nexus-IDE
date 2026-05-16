import React from 'react';
import { Zap, AlertOctagon } from 'lucide-react';

interface StackTraceFrame {
  file_path: string;
  line_number: number;
  symbol_name?: string;
}

interface RuntimeArtifact {
  artifact_type: string;
  message: string;
  frames: StackTraceFrame[];
  metadata: any;
}

interface RuntimeDiagnosticsProps {
  artifacts: RuntimeArtifact[];
  executionChains?: string[][];
  hotSymbols?: { name: string; file: string; hits: number; is_leaf: boolean }[];
  onClear: () => void;
  onJumpToFile?: (path: string, line: number) => void;
}

const RuntimeDiagnostics: React.FC<RuntimeDiagnosticsProps> = ({ artifacts, hotSymbols, onClear, onJumpToFile }) => {
  if (!artifacts || artifacts.length === 0) {
    return (
      <div className="py-12 flex flex-col items-center justify-center opacity-30 gap-3 border border-dashed border-white/5 rounded-xl bg-white/[0.01]">
        <AlertOctagon size={24} className="opacity-20" />
        <div className="text-[10px] text-center italic">
          No active runtime telemetry or execution failures in current buffer.
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 pr-1 animate-in fade-in duration-400">
      <div className="flex items-center justify-end">
        <button 
          onClick={onClear}
          className="text-[9px] uppercase font-black text-red-300 hover:text-white transition-colors bg-red-500/10 border border-red-500/20 px-3 py-1 rounded-md"
        >
          Clear Buffer
        </button>
      </div>

      {hotSymbols && hotSymbols.length > 0 && (
        <div className="runtime-hotspot-card">
          <div className="text-[9px] font-black text-red-200 uppercase mb-3 flex items-center gap-2 tracking-widest">
            <Zap size={12} className="text-red-400" />
            <span>Failing Architectural Hotspots</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {hotSymbols.map((sym, i) => (
              <div key={i} className={`hotspot-pill ${sym.is_leaf ? 'leaf' : 'branch'}`}>
                <span className="font-mono">{sym.name}()</span>
                <span className="opacity-40 text-[9px]">{sym.hits} Hits</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4">
        {artifacts.map((art, idx) => {
          const primaryFrame = art.frames && art.frames.length > 0 ? art.frames[0] : null;

          const handleDoubleClick = () => {
            if (primaryFrame && onJumpToFile) {
              // 1. Normalize Path for the jump
              let path = primaryFrame.file_path.replace(/\\/g, '/');
              ['/workspace/', 'workspace/', './'].forEach(delim => {
                if (path.includes(delim)) path = path.split(delim).pop() || path;
              });
              if (path.startsWith('/')) path = path.substring(1);

              // 2. Trigger the "File Select" logic normally (opens tab)
              onJumpToFile(path, primaryFrame.line_number);

              // 3. Broadcast Global Event for the Editor to handle the jump/focus
              // We do this after a small delay to ensure the tab has started changing
              setTimeout(() => {
                const event = new CustomEvent('nexus-editor-jump', { 
                  detail: { path, line: primaryFrame.line_number } 
                });
                window.dispatchEvent(event);
              }, 50);
            }
          };

          return (
            <div 
              key={idx} 
              className="file-bubble status-error interactive-diagnostic"
              onDoubleClick={handleDoubleClick}
              title="Double-click to navigate to source"
            >
              <div className="file-bubble-header cursor-pointer">
                <div className="candidate-toggle selected pointer-events-none" style={{ borderColor: 'rgba(255, 75, 75, 0.3)', background: 'rgba(255, 75, 75, 0.1)', color: 'var(--color-runtime)' }}>
                  <AlertOctagon size={14} />
                </div>

                <div className="file-bubble-meta">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="candidate-name">{art.artifact_type.replace('_', ' ')}</span>
                      {art.metadata?.lang && <span className="candidate-badge accent">{art.metadata.lang}</span>}
                    </div>
                    <div className="candidate-score-badge" style={{ color: '#ff8e8e', background: 'rgba(255, 75, 75, 0.1)', borderColor: 'rgba(255, 75, 75, 0.2)' }}>
                      CRITICAL
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="candidate-path truncate max-w-[400px]" title={art.message}>{art.message}</div>
                  </div>
                </div>
              </div>

              {art.frames && art.frames.length > 0 && (
                <div className="px-3 pb-3 border-t border-white/5 mt-1">
                  <div className="trace-path-container">
                    <div className="trace-path-header">Execution Trace</div>
                    {art.frames.slice(0, 4).map((frame, i) => (
                      <div key={i} className="trace-step border-b border-white/[0.03] last:border-0">
                        <span className="opacity-20 font-black">{i + 1}</span>
                        <div className="truncate">
                          <b>{frame.file_path.split(/[\\/]/).pop()}</b>
                          <span className="opacity-30 mx-1">:</span>
                          <span className="opacity-50">{frame.line_number}</span>
                        </div>
                        {frame.symbol_name && (
                          <div className="ml-auto">
                            <i>{frame.symbol_name}()</i>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default RuntimeDiagnostics;
