import React from 'react';
import { AlertOctagon } from 'lucide-react';

interface StackTraceFrame {
  file_path: string;
  line_number: number;
  symbol_name?: string;
}

interface RuntimeArtifact {
  artifact_type: string;
  message: string;
  frames: StackTraceFrame[];
  raw_log: string;
  metadata: any;
}

interface RuntimeDiagnosticsProps {
  artifacts: RuntimeArtifact[];
  onClear: () => void;
}

const RuntimeDiagnostics: React.FC<RuntimeDiagnosticsProps> = ({ artifacts, onClear }) => {
  if (!artifacts || artifacts.length === 0) {
    return null;
  }

  return (
    <div className="panel-section border-t border-white/5 pt-4">
      <div className="panel-title mb-2 accent flex items-center gap-2">
        <AlertOctagon size={13} className="text-red-400" />
        <span className="text-red-400">Runtime Diagnostics</span>
        <button 
          onClick={onClear}
          className="ml-auto text-[9px] px-2 py-0.5 bg-white/5 hover:bg-white/10 rounded"
        >
          Clear
        </button>
      </div>

      <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto pr-1">
        {artifacts.map((art, idx) => (
          <div key={idx} className="context-card p-2 bg-red-500/5 border-red-500/10">
            <div className="flex items-center justify-between mb-1">
              <div className="text-[10px] font-semibold text-red-300 uppercase tracking-wider">
                {art.artifact_type.replace('_', ' ')}
              </div>
              {art.metadata?.lang && (
                <div className="text-[8px] px-1 rounded bg-red-500/10 text-red-400 border border-red-500/20 uppercase">
                  {art.metadata.lang}
                </div>
              )}
            </div>
            <div className="text-[11px] text-red-100/90 font-mono mb-2 break-words">
              {art.message}
            </div>

            {art.frames && art.frames.length > 0 && (
              <div className="mt-2 pl-2 border-l border-red-500/20">
                {art.frames.slice(0, 5).map((frame, i) => (
                  <div key={i} className="text-[9px] font-mono text-red-200/60 flex items-start gap-1 py-0.5">
                    <span className="opacity-50 min-w-[12px]">↳</span>
                    <span className="flex-1 break-all">
                      <span className="text-red-200/80">{frame.file_path.split(/[\\/]/).pop()}</span>
                      <span className="opacity-50">:{frame.line_number}</span>
                      {frame.symbol_name && <span className="text-red-300/60 ml-1">in {frame.symbol_name}</span>}
                    </span>
                  </div>
                ))}
                {art.frames.length > 5 && (
                  <div className="text-[8px] italic opacity-40 mt-1">
                    ... +{art.frames.length - 5} more frames
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default RuntimeDiagnostics;
