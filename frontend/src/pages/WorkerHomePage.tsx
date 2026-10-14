import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type WorkerProfile } from '../api'
import { Alert, Badge, Card } from '../components/ui'

const DOCUMENT_STATUS: Record<string, string> = {
  PENDENTE_DOCUMENTOS: 'Pendente',
  EM_ANALISE: 'Em análise',
  APROVADO: 'Aprovado',
  REJEITADO: 'Rejeitado',
}

/** Painel inicial do prestador. Enquanto o perfil estiver incompleto, mostra o passo a passo. */
export default function WorkerHomePage() {
  const [profile, setProfile] = useState<WorkerProfile | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<WorkerProfile>('/api/workers/me/')
      .then(setProfile)
      .catch(() => setError('Não foi possível carregar o seu perfil.'))
  }, [])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!profile) return <p role="status">Carregando...</p>

  return (
    <Card>
      <h1>Complete seu perfil</h1>
      <p>CPF {profile.cpf}</p>
      <ol aria-label="Etapas do perfil">
        {profile.profile_steps.map((step, index) => {
          const label =
            step.key === 'documentos'
              ? (DOCUMENT_STATUS[step.status ?? ''] ?? 'Pendente')
              : step.done
                ? 'Concluída'
                : 'Pendente'
          return (
            <li key={step.key}>
              {index + 1}) {step.label}{' '}
              <Badge tone={step.done ? 'success' : 'warning'}>{label}</Badge>{' '}
              <Link to={step.key === 'documentos' ? '/perfil/documentos' : '/perfil/pix'}>
                {step.done ? 'Ver' : 'Completar'}
              </Link>
            </li>
          )
        })}
      </ol>
      {profile.verification_message && <Alert tone="info">{profile.verification_message}</Alert>}
    </Card>
  )
}
