import { useEffect, useState } from 'react'

type HealthState =
  | { kind: 'loading' }
  | { kind: 'ok'; status: string }
  | { kind: 'error' }

function App() {
  const [health, setHealth] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/health/', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<{ status: string }>
      })
      .then((data) => setHealth({ kind: 'ok', status: data.status }))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setHealth({ kind: 'error' })
      })

    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Conecta Já</h1>
      <p role="status">
        {health.kind === 'loading' && 'Verificando a API...'}
        {health.kind === 'ok' && `API: ${health.status}`}
        {health.kind === 'error' && 'API indisponível'}
      </p>
    </main>
  )
}

export default App
