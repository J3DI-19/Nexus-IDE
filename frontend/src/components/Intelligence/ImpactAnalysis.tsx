import React from 'react';
import { Activity, AlertTriangle, FileCode } from 'lucide-react';

interface ImpactCandidate {
  file_metadata: {
    rel_path: string;
    classification: string;
    language: string;
  };
  impact_score: number;
  score_breakdown: { factor: string; points: number; reason: string }[];
  affected_symbols: string[];
  affected_artifacts: { artifact_type: string; name: string }[];
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
      <div className="panel-section border-t border-white/5 pt-4">
        <div className="panel-title mb-2">
          <Activity size={13} />
          <span>Impact Analysis</span>
        </div>
        <div className="text-[10px] opacity-60 text-center py-4 italic">Analyzing architectural impact...</div>
      </div>
    );
  }

  if (impactCandidates.length === 0) {
    return null;
  }

  return (
    <div className="panel-section border-t border-white/5 pt-4">
      <div className="panel-title mb-2 accent flex items-center gap-2">
        <AlertTriangle size={13} className="text-yellow-400" />
        <span className="text-yellow-400">Change Impact</span>
        <span className="ml-auto text-[10px] opacity-50">{impactCandidates.length} affected</span>
      </div>

      <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto pr-1">
        {impactCandidates.map((cand, idx) => (
          <div key={idx} className="context-card p-2 bg-yellow-400/5 border-yellow-400/10">
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1 min-w-0">
                <FileCode size={10} className="text-yellow-400/70" />
                <span className="text-[11px] font-medium truncate text-yellow-100">{cand.file_metadata.rel_path.split('/').pop()}</span>
                <span className="text-[9px] px-1 rounded uppercase opacity-60 border border-yellow-400/20 text-yellow-400/80">
                  {cand.file_metadata.classification}
                </span>
              </div>
              <div className="text-[9px] font-mono text-yellow-400/60">Depth: {cand.traversal_depth}</div>
            </div>

            {cand.affected_artifacts && cand.affected_artifacts.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {cand.affected_artifacts.map((a, i) => (
                  <span key={i} className="text-[8px] bg-yellow-400/10 text-yellow-300 border border-yellow-400/20 px-1 rounded">
                    {a.artifact_type}({a.name})
                  </span>
                ))}
              </div>
            )}

            {cand.affected_symbols && cand.affected_symbols.length > 0 && (
              <div className="mt-1 text-[9px] text-yellow-100/60 truncate">
                Affected: {cand.affected_symbols.join(", ")}
              </div>
            )}
            
            <div className="mt-1 text-[8px] opacity-40 font-mono break-all flex flex-wrap gap-x-1">
              Path: {cand.relationship_path.map((p, i) => (
                <React.Fragment key={i}>
                  <span className={i === cand.relationship_path.length - 1 ? "text-yellow-200" : ""}>{p.split(':').pop()}</span>
                  {i < cand.relationship_path.length - 1 && (
                    <span className="text-yellow-400/50"> --({cand.relationship_types[i] || 'dep'})--&gt; </span>
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ImpactAnalysis;
