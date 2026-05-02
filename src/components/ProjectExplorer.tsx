import { Folder, File, RefreshCw } from 'lucide-react'

interface ProjectExplorerProps {
  files: string[]
  selectedFile: string | null
  onFileSelect: (file: string) => void
  onRefresh: () => void
}

const ProjectExplorer = ({ files, selectedFile, onFileSelect, onRefresh }: ProjectExplorerProps) => {
  return (
    <div className="panel">
      <div className="panel-header">
        <span>PROJECT EXPLORER</span>
        <button 
          onClick={onRefresh} 
          style={{ padding: '4px', background: 'transparent' }}
          title="Refresh"
        >
          <RefreshCw size={14} color="#8b949e" />
        </button>
      </div>
      <div className="panel-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', fontSize: '13px', color: '#8b949e' }}>
          <Folder size={16} />
          <span>workspace</span>
        </div>
        {files.length === 0 ? (
          <div style={{ fontSize: '12px', color: '#8b949e', fontStyle: 'italic' }}>
            No files found. Scan to refresh.
          </div>
        ) : (
          files.map((file) => (
            <div 
              key={file} 
              className={`file-item ${selectedFile === file ? 'active' : ''}`}
              onClick={() => onFileSelect(file)}
            >
              <File size={14} style={{ marginRight: '8px', verticalAlign: 'middle' }} />
              {file}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default ProjectExplorer
