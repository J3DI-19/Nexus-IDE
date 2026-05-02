interface ConsoleProps {
  output: string
  error: string
}

const Console = ({ output, error }: ConsoleProps) => {
  if (!output && !error) return null

  return (
    <div className="console-box">
      {output && <div className="success-text">{output}</div>}
      {error && <div className="error-text">{error}</div>}
    </div>
  )
}

export default Console
