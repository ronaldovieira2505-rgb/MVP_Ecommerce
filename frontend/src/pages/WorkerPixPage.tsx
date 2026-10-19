import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type WorkerProfile } from '../api'
import { Alert, Button, Card, Field, Loading, SelectField } from '../components/ui'

const KEY_TYPES = [
  { value: 'CPF', label: 'CPF' },
  { value: 'EMAIL', label: 'E-mail' },
  { value: 'TELEFONE', label: 'Telefone' },
  { value: 'ALEATORIA', label: 'Aleatória' },
]

/** Cadastro e troca da chave PIX. A chave é sempre exibida mascarada. */
export default function WorkerPixPage() {
  const [profile, setProfile] = useState<WorkerProfile | null>(null)
  const [keyType, setKeyType] = useState('CPF')
  const [key, setKey] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api<WorkerProfile>('/api/workers/me/')
      .then(setProfile)
      .catch(() => setError('Não foi possível carregar o seu perfil.'))
  }, [])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSaved(false)
    try {
      const body: Record<string, string> = { key_type: keyType, key }
      if (profile?.pix_key) body.current_password = password
      const updated = await api<WorkerProfile>('/api/workers/me/pix/', { method: 'PUT', body })
      setProfile(updated)
      setKey('')
      setPassword('')
      setSaved(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível salvar a chave PIX.')
    }
  }

  if (!profile && !error) return <Loading rows={1} />
  const hasKey = Boolean(profile?.pix_key)

  return (
    <Card>
      <h1>Chave PIX</h1>
      {hasKey && <p>Chave atual: {profile?.pix_key}</p>}
      {saved && <Alert tone="success">Chave PIX salva.</Alert>}
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={onSubmit} noValidate>
        <SelectField
          label="Tipo da chave"
          value={keyType}
          onChange={(e) => setKeyType(e.target.value)}
        >
          {KEY_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </SelectField>
        <Field label="Chave PIX" value={key} onChange={(e) => setKey(e.target.value)} />
        {hasKey && (
          <Field
            label="Senha atual"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        )}
        <Button type="submit" block>
          Salvar chave
        </Button>
      </form>
    </Card>
  )
}
