import React from 'react';
import { FileCode, ChevronRight } from 'lucide-react';

interface ImpactCandidate {
  file_metadata: {
    rel_path: string;
    classification: string;
    language: string;
  };
  impact_score: number;
  affected_symbols: string[];
  relationship_path: string[];
  relationship_types: string[];
  traversal_depth: number;
}

interface ImpactAnalysisProps {
  impactCandidates: ImpactCandidate[];
  loading: boolean;
}

const ImpactAnalysis: React.FC<ImpactAnalysisProps> = ({ impactCandidates, loading }) => {
  if (loading) {
    return (
      <div className="py-16 flex flex-col items-center justify-center gap-4 bg-yellow-400/[0.02] border border-dashed border-yellow-400/20 rounded-xl animate-pulse">
        <div className="relative">
          <div className="absolute inset-0 bg-yellow-400/20 blur-xl rounded-full"></div>
          <FileCode size={32} className="text-yellow-400 relative z-10" />
        </div>
        <div className="flex flex-col items-center gap-1">
          <div className="text-[10px] uppercase font-black text-yellow-200 tracking-widest">Architectural Radar Active</div>
          <div className="text-[8px] opacity-40 uppercase font-bold">Calculating Downstream Impact Radius...</div>
        </div>
      </div>
    );
  }

  if (impactCandidates.length === 0) {
    return (
      <div className="py-12 flex flex-col items-center justify-center opacity-30 gap-3 border border-dashed border-white/5 rounded-xl bg-white/[0.01]">
        <FileCode size={24} className="opacity-20" />
        <div className="text-[10px] text-center italic">
          No significant downstream architectural impact detected.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-h-[440px] overflow-y-auto pr-1 custom-scrollbar animate-in fade-in duration-400">
      <div className="px-2 flex flex-col gap-0.5">
        <div className="text-[10px] uppercase font-black text-yellow-400 tracking-[0.15em] flex items-center gap-2">
          <FileCode size={12} />
          <span>Downstream Impact Radius</span>
        </div>
        <div className="text-[8px] opacity-40 uppercase tracking-widest font-bold">Architectural Dependency Analysis</div>
      </div>

      <div className="space-y-3">
        {impactCandidates.map((cand, idx) => (
          <div key={idx} className="file-bubble p-3 border-yellow-400/20 bg-yellow-400/[0.02] hover:bg-yellow-400/[0.04] transition-all">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="p-1.5 rounded-md bg-yellow-400/10 border border-yellow-400/20">
                  <FileCode size={12} className="text-yellow-400" />
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="text-[12px] font-black truncate text-yellow-50 tracking-tight">
                    {cand.file_metadata.rel_path.split('/').pop()}
                  </span>
                  <span className="text-[8px] opacity-40 font-mono truncate">{cand.file_metadata.rel_path}</span>
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                <div className="text-[9px] font-black text-yellow-400/80 bg-yellow-400/10 px-2 py-0.5 rounded-full border border-yellow-400/20">
                  DEPTH {cand.traversal_depth}
                </div>
                <span className="text-[7px] font-bold opacity-30 uppercase tracking-tighter">Impact Level</span>
              </div>
            </div>

            <div className="bg-black/30 rounded-lg border border-white/5 mb-3">
              <div className="px-2 py-1 bg-white/[0.03] text-[7px] uppercase font-black opacity-30 tracking-[0.2em] border-b border-white/5">Architectural Trace</div>
              <div className="p-2">
                <ConnectionChain path={cand.relationship_path} />
              </div>
            </div>

            {cand.affected_symbols && cand.affected_symbols.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[8px] uppercase font-black opacity-30 tracking-widest px-1">Affected Symbols</div>
                <div className="flex flex-wrap gap-1.5">
                  {cand.affected_symbols.slice(0, 8).map((sym, i) => (
                    <div key={i} className="text-[9px] bg-white/5 text-yellow-100/70 border border-white/5 px-2 py-1 rounded-md font-mono transition-colors hover:bg-white/10">
                      {sym}()
                    </div>
                  ))}
                  {cand.affected_symbols.length > 8 && (
                    <div className="text-[9px] bg-yellow-400/10 text-yellow-200/60 border border-yellow-400/10 px-2 py-1 rounded-md font-black">
                      +{cand.affected_symbols.length - 8} MORE
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default ImpactAnalysis;
