import React from 'react';
import { FileCode, ChevronRight } from 'lucide-react';
import { ConnectionChain } from './CandidateList';

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
    <div className="space-y-4 pr-1 animate-in fade-in duration-400">
      <div className="space-y-3">
        {impactCandidates.map((cand, idx) => {
          const relPath = cand.file_metadata.rel_path;
          const fileName = relPath.split('/').pop();

          return (
            <div key={idx} className="file-bubble status-impact">
              <div className="file-bubble-header cursor-default">
                {/* Visual Icon */}
                <div className="candidate-toggle selected pointer-events-none" style={{ borderColor: 'rgba(255, 202, 58, 0.3)', background: 'rgba(255, 202, 58, 0.1)', color: 'var(--color-dependency)' }}>
                  <FileCode size={14} />
                </div>

                <div className="file-bubble-meta">
                  {/* Row 1: Identity & Depth */}
                  <div className="flex items-start justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="candidate-name">{fileName}</span>
                      <span className="candidate-badge accent">{cand.file_metadata.classification}</span>
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <div className="impact-depth-badge">
                        DEPTH {cand.traversal_depth}
                      </div>
                      
                      {cand.affected_symbols && cand.affected_symbols.length > 0 && (
                        <div className="flex flex-wrap gap-1 justify-end max-w-[180px]">
                          {cand.affected_symbols.slice(0, 5).map((sym, i) => (
                            <div key={i} className="impact-symbol-pill">
                              {sym}()
                            </div>
                          ))}
                          {cand.affected_symbols.length > 5 && (
                            <div className="text-[8px] bg-yellow-400/10 text-yellow-200/60 border border-yellow-400/10 px-1.5 py-0.5 rounded-md font-black">
                              +{cand.affected_symbols.length - 5}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Row 2: Context & Trace */}
                  <div className="flex items-center gap-2">
                    <div className="candidate-path">{relPath}</div>
                    {cand.relationship_path?.length > 1 && (
                      <ConnectionChain path={cand.relationship_path} />
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ImpactAnalysis;
