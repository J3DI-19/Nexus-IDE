import { useState, useEffect } from 'react'
import ProjectExplorer from './components/ProjectExplorer'
import CodeViewer from './components/CodeViewer'
import ControlPanel from './components/ControlPanel'

function App() {
  const [files, setFiles] = useState<string[]>([])
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string>('')
  const [isLoading, setIsLoading] = useState(false)

  const scanProject = async () => {
    try {
      const response = await fetch('/scan')
      const data = await response.json()
      setFiles(data.files || [])
    } catch (error) {
      console.error('Error scanning project:', error)
    }
  }

  useEffect(() => {
    scanProject()
  }, [])

  const handleFileSelect = async (file: string) => {
    setSelectedFile(file)
    setIsLoading(true)
    try {
      // Assuming a simple way to get file content, maybe the backend has GET /file?path=...
      // But the prompt doesn't specify how to GET file content. 
      // I'll assume for now that if I click a file, I might need an endpoint or 
      // maybe I'll mock it if not specified.
      // Re-reading requirements: "Click a file → loads it in center panel"
      // API Contract only shows GET /scan. I'll assume GET /file?path=... or similar
      // is available or I'll just show a placeholder if I don't know the endpoint.
      // Wait, let's look at the requirements again. 
      // "API Contract (assume backend exists) ... GET /scan ... POST /prompt ... POST /apply ... POST /run"
      // It doesn't mention GET /file. I'll assume GET /file?path=file exists for the sake of functionality.
      
      const response = await fetch(`/file?path=${encodeURIComponent(file)}`)
      if (response.ok) {
        const content = await response.text()
        setFileContent(content)
      } else {
        setFileContent(`// Error loading ${file}\n// Make sure GET /file?path=... is implemented on backend.`)
      }
    } catch (error) {
      setFileContent(`// Error: ${error}`)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app-container">
      <ProjectExplorer 
        files={files} 
        selectedFile={selectedFile} 
        onFileSelect={handleFileSelect}
        onRefresh={scanProject}
      />
      <CodeViewer 
        selectedFile={selectedFile} 
        content={fileContent} 
        isLoading={isLoading}
      />
      <ControlPanel 
        selectedFile={selectedFile}
      />
    </div>
  )
}

export default App
