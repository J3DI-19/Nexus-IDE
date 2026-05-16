import React from 'react';
import { ChevronRight, GitBranch, Route, Sigma } from 'lucide-react';

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
  onJumpToFile?: (path: string, line?: number) => void;
}

const formatImpactNode = (node: string) => {
  if (node.includes(':')) return node.split(':').pop() || node;
  return node.split(/[\\/]/).pop() || node;
};

const ImpactAnalysis: React.FC<ImpactAnalysisProps> = ({ impactCandidates, loading, onJumpToFile }) => {
  if (loading) {
    return (
      <div className="py-16 flex flex-col items-center justify-center gap-4 bg-yellow-400/[0.02] border border-dashed border-yellow-400/20 rounded-xl animate-pulse">
        <div className="relative">
          <div className="absolute inset-0 bg-yellow-400/20 blur-xl rounded-full"></div>
          <GitBranch size={32} className="text-yellow-400 relative z-10" />
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
        <GitBranch size={24} className="opacity-20" />
        <div className="text-[10px] text-center italic">
          No significant downstream architectural impact detected.
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 pr-1 animate-in fade-in duration-400">
      <div className="flex flex-col gap-3">
        {impactCandidates.map((cand, idx) => {
          const relPath = cand.file_metadata.rel_path;
          const fileName = relPath.split('/').pop();
          const affectedCount = cand.affected_symbols?.length || 0;
          const topRelationship = cand.relationship_types?.[0]?.replace('_', ' ') || 'graph edge';

          const handleDoubleClick = () => {
            if (onJumpToFile) {
              let path = relPath.replace(/\\/g, '/');
              ['/workspace/', 'workspace/', './'].forEach(delim => {
                if (path.includes(delim)) path = path.split(delim).pop() || path;
              });
              if (path.startsWith('/')) path = path.substring(1);
              const line = 1;

              onJumpToFile(path);

              setTimeout(() => {
                const event = new CustomEvent('nexus-editor-jump', { 
                  detail: { path, line } 
                });
                window.dispatchEvent(event);
              }, 50);
            }
          };

          return (
            <div 
              key={idx} 
              className="file-bubble status-impact interactive-diagnostic"
              onDoubleClick={handleDoubleClick}
              title="Double-click to navigate to file"
            >
              <div className="file-bubble-header cursor-pointer">
                <div className="impact-file-icon">
                  <GitBranch size={14} />
                </div>

                <div className="file-bubble-meta">
                  <div className="impact-bubble-topline">
                    <div className="impact-file-identity">
                      <span className="candidate-name">{fileName}</span>
                      <span className="candidate-badge accent">{cand.file_metadata.classification}</span>
                      <span className="impact-relation-pill">
                        <Route size={9} />
                        {topRelationship}
                      </span>
                    </div>
                    <div className="impact-metric-stack">
                      <div className="impact-score-badge">
                        <Sigma size={10} />
                        {Math.round(cand.impact_score)} pts
                      </div>
                      <div className="impact-depth-badge">D{cand.traversal_depth}</div>
                    </div>
                  </div>

                  <div className="impact-bubble-context">
                    <div className="candidate-path" title={relPath}>{relPath}</div>
                  </div>

                  {cand.relationship_path?.length > 1 && (
                    <div className="impact-relationship-path">
                      <div className="impact-relationship-label">
                        <Route size={10} />
                        <span>Impact path</span>
                      </div>
                      <div className="impact-relationship-chain">
                        {cand.relationship_path.map((node, i) => (
                          <React.Fragment key={`${node}-${i}`}>
                            <span className={`impact-chain-node ${i === cand.relationship_path.length - 1 ? 'active' : ''}`} title={node}>
                              {formatImpactNode(node)}
                            </span>
                            {i < cand.relationship_path.length - 1 && <ChevronRight size={9} className="impact-chain-arrow" />}
                          </React.Fragment>
                        ))}
                      </div>
                    </div>
                  )}

                  {affectedCount > 0 && (
                    <div className="impact-symbol-strip">
                      {cand.affected_symbols.slice(0, 5).map((sym, i) => (
                        <div key={i} className="impact-symbol-pill">
                          {sym}()
                        </div>
                      ))}
                      {affectedCount > 5 && (
                        <div className="impact-symbol-more">
                          +{affectedCount - 5}
                        </div>
                      )}
                    </div>
                  )}
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
