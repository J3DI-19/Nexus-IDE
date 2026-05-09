import React from 'react';
import { Zap, AlertOctagon, ChevronRight } from 'lucide-react';

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
}

const RuntimeDiagnostics: React.FC<RuntimeDiagnosticsProps> = ({ artifacts, executionChains, hotSymbols, onClear }) => {
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
    <div className="space-y-6 max-h-[440px] overflow-y-auto pr-1 custom-scrollbar animate-in fade-in duration-400">
      <div className="flex items-center justify-between px-2">
        <div className="flex flex-col gap-0.5">
          <div className="text-[10px] uppercase font-black text-red-400 tracking-[0.15em] flex items-center gap-2">
            <AlertOctagon size={12} />
            <span>Telemetry Diagnostics</span>
          </div>
          <div className="text-[8px] opacity-40 uppercase tracking-widest font-bold">Runtime Context Overlays</div>
        </div>
        <button 
          onClick={onClear}
          className="text-[9px] uppercase font-black text-red-300 hover:text-white transition-colors bg-red-500/10 border border-red-500/20 px-3 py-1 rounded-md"
        >
          Clear Buffer
        </button>
      </div>

      {hotSymbols && hotSymbols.length > 0 && (
        <div className="bg-red-500/[0.04] border border-red-500/15 rounded-xl p-3 shadow-lg shadow-red-900/10">
          <div className="text-[9px] font-black text-red-200 uppercase mb-3 flex items-center gap-2 tracking-widest">
            <Zap size={12} className="text-red-400 drop-shadow-[0_0_5px_rgba(255,70,70,0.5)]" />
            <span>Failing Architectural Hotspots</span>
          </div>
          <div className="flex flex-wrap gap-2.5">
            {hotSymbols.map((sym, i) => (
              <div key={i} className={`text-[10px] px-2.5 py-1.5 rounded-lg border flex items-center gap-3 transition-all ${sym.is_leaf ? 'bg-red-500/15 border-red-500/40 text-red-50 shadow-inner' : 'bg-white/5 border-white/10 text-white/50'}`}>
                <span className="font-mono font-bold">{sym.name}()</span>
                <span className="h-3 w-px bg-white/10"></span>
                <span className="opacity-60 text-[9px] font-mono">{sym.hits} Hits</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {artifacts.map((art, idx) => (
          <div key={idx} className="file-bubble p-3 border-red-500/20 bg-red-500/[0.02]">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse"></div>
                <span className="text-[10px] font-black text-red-300 uppercase tracking-wider">
                  {art.artifact_type.replace('_', ' ')}
                </span>
              </div>
              {art.metadata?.lang && (
                <span className="text-[8px] px-2 py-0.5 rounded-md bg-red-500/20 text-red-200 border border-red-500/30 uppercase font-black">
                  {art.metadata.lang}
                </span>
              )}
            </div>
            <div className="text-[11px] text-red-50/80 font-mono mb-3 break-words leading-relaxed border-l-[3px] border-red-500/40 pl-3 py-0.5">
              {art.message}
            </div>

            {art.frames && art.frames.length > 0 && (
              <div className="mt-3 bg-black/40 rounded-lg border border-white/5 overflow-hidden">
                <div className="px-2 py-1 bg-white/5 text-[8px] uppercase font-bold opacity-30 tracking-widest border-bottom border-white/5">Trace Execution Path</div>
                <div className="p-2 space-y-1.5">
                  {art.frames.slice(0, 3).map((frame, i) => (
                    <div key={i} className="text-[10px] font-mono text-red-100/60 flex items-center gap-2.5">
                      <div className="text-red-500/30 font-bold">{i + 1}</div>
                      <span className="text-red-100/80 font-bold">{frame.file_path.split(/[\\/]/).pop()}</span>
                      <span className="opacity-30">:{frame.line_number}</span>
                      {frame.symbol_name && (
                        <>
                          <ChevronRight size={10} className="opacity-20" />
                          <span className="text-red-400/50 font-black italic"> {frame.symbol_name}()</span>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default RuntimeDiagnostics;
