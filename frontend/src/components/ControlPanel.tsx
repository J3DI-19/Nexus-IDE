import { useState } from 'react'
import { Sparkles, Clipboard, Check, Play, Zap } from 'lucide-react'
import Console from './Console'

interface ControlPanelProps {
  selectedFile: string | null
}

const ControlPanel = ({ selectedFile }: ControlPanelProps) => {
  const [generatedPrompt, setGeneratedPrompt] = useState('')
  const [diffContent, setDiffContent] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [isApplying, setIsApplying] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [runOutput, setRunOutput] = useState({ output: '', error: '' })
  const [copied, setCopied] = useState(false)

  const handleGeneratePrompt = async () => {
    if (!selectedFile) return
    setIsGenerating(true)
    try {
      const response = await fetch('/prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: selectedFile })
      })
      const data = await response.json()
      setGeneratedPrompt(data.prompt || '')
    } catch (error) {
      console.error('Error generating prompt:', error)
    } finally {
      setIsGenerating(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(generatedPrompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleApplyPatch = async () => {
    if (!diffContent) return
    setIsApplying(true)
    try {
      const response = await fetch('/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ diff: diffContent })
      })
      if (response.ok) {
        alert('Patch applied successfully!')
        setDiffContent('')
      } else {
        alert('Failed to apply patch.')
      }
    } catch (error) {
      console.error('Error applying patch:', error)
    } finally {
      setIsApplying(false)
    }
  }

  const handleRun = async () => {
    setIsRunning(true)
    try {
      const response = await fetch('/run', { method: 'POST' })
      const data = await response.json()
      setRunOutput({ output: data.output || '', error: data.error || '' })
    } catch (error) {
      setRunOutput({ output: '', error: `Execution error: ${error}` })
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <span>LOOPFORGE CONTROL</span>
      </div>
      <div className="panel-content">
        {/* Prompt Section */}
        <div className="control-section">
          <div className="section-title">1. Generate AI Prompt</div>
          <button 
            onClick={handleGeneratePrompt} 
            disabled={!selectedFile || isGenerating}
            style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', marginBottom: '8px' }}
          >
            <Sparkles size={16} />
            {isGenerating ? 'Generating...' : 'Generate Prompt'}
          </button>
          
          {generatedPrompt && (
            <div style={{ position: 'relative' }}>
              <textarea 
                rows={6} 
                value={generatedPrompt} 
                readOnly 
                placeholder="Generated prompt will appear here..."
              />
              <button 
                onClick={handleCopy}
                style={{ 
                  position: 'absolute', 
                  top: '8px', 
                  right: '8px', 
                  padding: '4px 8px', 
                  fontSize: '11px',
                  backgroundColor: 'rgba(255,255,255,0.1)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
              >
                {copied ? <Check size={12} /> : <Clipboard size={12} />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          )}
        </div>

        {/* Patch Section */}
        <div className="control-section">
          <div className="section-title">2. Paste AI Response (Diff)</div>
          <textarea 
            rows={6} 
            value={diffContent} 
            onChange={(e) => setDiffContent(e.target.value)}
            placeholder="Paste the diff response from AI here..."
            style={{ marginBottom: '8px' }}
          />
          <button 
            onClick={handleApplyPatch} 
            disabled={!diffContent || isApplying}
            style={{ 
              width: '100%', 
              backgroundColor: '#3fb950', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              gap: '8px' 
            }}
          >
            <Zap size={16} />
            {isApplying ? 'Applying...' : 'Apply Patch'}
          </button>
        </div>

        {/* Run Section */}
        <div className="control-section">
          <div className="section-title">3. Test & Validate</div>
          <button 
            onClick={handleRun} 
            disabled={isRunning}
            style={{ 
              width: '100%', 
              backgroundColor: '#8957e5', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              gap: '8px' 
            }}
          >
            <Play size={16} />
            {isRunning ? 'Running...' : 'Run Project'}
          </button>
          
          <Console output={runOutput.output} error={runOutput.error} />
        </div>
      </div>
    </div>
  )
}

export default ControlPanel
