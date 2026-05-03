import React from 'react';
import { Sparkles, Settings, Info, FileCode } from 'lucide-react';
import { Tab } from '../App';

interface RightPanelProps {
  activeTab: Tab | null;
}

const RightPanel: React.FC<RightPanelProps> = ({ activeTab }) => {
  return (
    <div className="right-panel-root">

      {/* ===== CONTENT ===== */}
      <div className="right-panel-content">

        {/* AI ACTIONS */}
        <div className="panel-section">
          <div className="panel-title accent">
            <Sparkles size={13} />
            <span>AI Actions</span>
          </div>

          <div className="panel-actions">
            <button className="btn btn-primary">
              Generate Prompt
            </button>

            <button className="btn" disabled>
              Apply Patch
            </button>
          </div>
        </div>

        {/* CONTEXT */}
        <div className="panel-section">
          <div className="panel-title">
            <Info size={13} />
            <span>Context</span>
          </div>

          <div className="panel-card">

            <div className="panel-sub mb-6">Active File</div>

            <div className="panel-file-row">
              <FileCode size={14} />
              <span className="panel-file">
                {activeTab ? activeTab.path.split('/').pop() : 'None'}
              </span>
            </div>

            {activeTab && (
              <div className="panel-path">
                {activeTab.path}
              </div>
            )}

          </div>
        </div>

        {/* SETTINGS */}
        <div className="panel-section">
          <div className="panel-title">
            <Settings size={13} />
            <span>Settings</span>
          </div>

          <button className="btn">
            Project Config
          </button>
        </div>

      </div>

      {/* FOOTER */}
      <div className="panel-footer">
        NEXUS IDE v0.1.0
      </div>

    </div>
  );
};

export default RightPanel;