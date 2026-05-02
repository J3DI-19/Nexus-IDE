interface CodeViewerProps {
  selectedFile: string | null
  content: string
  isLoading: boolean
}

const CodeViewer = ({ selectedFile, content, isLoading }: CodeViewerProps) => {
  return (
    <div className="panel" style={{ borderLeft: '1px solid #30363d', borderRight: '1px solid #30363d' }}>
      <div className="panel-header">
        <span>{selectedFile || 'SELECT A FILE'}</span>
      </div>
      <div className="panel-content" style={{ padding: '0', backgroundColor: '#010409' }}>
        {isLoading ? (
          <div style={{ padding: '20px', color: '#8b949e' }}>Loading content...</div>
        ) : selectedFile ? (
          <pre style={{ padding: '16px', margin: '0', overflowX: 'auto' }}>
            <code>{content}</code>
          </pre>
        ) : (
          <div style={{ 
            height: '100%', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            color: '#8b949e',
            flexDirection: 'column',
            gap: '12px'
          }}>
            <div style={{ fontSize: '48px', opacity: 0.1 }}>LoopForge</div>
            <div style={{ fontSize: '14px' }}>Select a file from the explorer to view its content</div>
          </div>
        )}
      </div>
    </div>
  )
}

export default CodeViewer
