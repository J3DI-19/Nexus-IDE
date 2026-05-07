import React from 'react';
import { Info, FileCode } from 'lucide-react';
import { Tab } from '../../App';

interface ActiveFileContextProps {
  activeTab: Tab | null;
}

const ActiveFileContext: React.FC<ActiveFileContextProps> = ({ activeTab }) => {
  return (
    <div className="panel-section opacity-80 mt-auto border-t border-white/5 pt-4">
      <div className="panel-title">
        <Info size={13} />
        <span>Active File</span>
      </div>
      <div className="panel-card mt-2">
        <div className="panel-file-row">
          <FileCode size={14} className="text-blue-400" />
          <span className="panel-file">
            {activeTab ? activeTab.path.split('/').pop() : 'None'}
          </span>
        </div>
        {activeTab && (
          <div className="panel-path opacity-40">
            {activeTab.path}
          </div>
        )}
      </div>
    </div>
  );
};

export default ActiveFileContext;
