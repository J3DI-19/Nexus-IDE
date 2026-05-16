import React from 'react';
import { AlertOctagon, Sparkles } from 'lucide-react';

interface GlobalIntelligenceProps {
  runtimeCount: number;
  impactCount: number;
  activeView: 'none' | 'runtime' | 'impact';
  setActiveView: (view: 'none' | 'runtime' | 'impact') => void;
}

const GlobalIntelligence: React.FC<GlobalIntelligenceProps> = ({ 
  runtimeCount, 
  impactCount, 
  activeView, 
  setActiveView 
}) => {
  return (
    <div className="global-intelligence-dashboard">
      <button 
        className={`global-stat-card status-runtime ${activeView === 'runtime' ? 'active' : ''} ${runtimeCount > 0 ? 'has-data' : 'is-empty'}`}
        onClick={() => setActiveView(activeView === 'runtime' ? 'none' : 'runtime')}
        type="button"
      >
        <div className="flex items-center gap-2 text-[10px] uppercase font-black tracking-widest label-text">
          <AlertOctagon size={12} strokeWidth={2.5} />
          <span>Runtime Issues</span>
        </div>
        <div className="stat-value">{runtimeCount}</div>
      </button>

      <button 
        className={`global-stat-card status-impact ${activeView === 'impact' ? 'active' : ''} ${impactCount > 0 ? 'has-data' : 'is-empty'}`}
        onClick={() => setActiveView(activeView === 'impact' ? 'none' : 'impact')}
        type="button"
      >
        <div className="flex items-center gap-2 text-[10px] uppercase font-black tracking-widest label-text">
          <Sparkles size={12} strokeWidth={2.5} />
          <span>Change Impact</span>
        </div>
        <div className="stat-value">{impactCount}</div>
      </button>
    </div>
  );
};

export default GlobalIntelligence;
