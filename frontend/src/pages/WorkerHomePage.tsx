import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type WorkerProfile } from '../api'
import { Alert, Badge, Card } from '../components/ui'
import type { Tone } from '../status'

const DOCUMENT_STATUS: Record<string, string> = {
  PENDENTE_DOCUMENTOS: 'Pendente',
  EM_ANALISE: 'Em análise',
  APROVADO: 'Aprovado',
  REJEITADO: 'Rejeitado',
}

/** A lombada acompanha a verificação: colete enquanto depende do prestador. */
const PROFILE_TONES: Record<string, Tone> = {
  PENDENTE_DOCUMENTOS: 'colete',
  EM_ANALISE: 'uniforme',
  APROVADO: 'carimbo',
  REJEITADO: 'encerrada',
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

  const pending = profile.profile_steps.filter((step) => !step.done).length

  return (
    <Card tone={PROFILE_TONES[profile.verification_status] ?? 'colete'}>
      <h1>Complete seu perfil</h1>
      <p>
        {pending === 0
          ? 'Tudo enviado. Avisamos assim que a verificação terminar.'
          : 'Você precisa terminar estas etapas para poder se candidatar a turnos.'}
      </p>
      <ol className="etapas" aria-label="Etapas do perfil">
        {profile.profile_steps.map((step, index) => {
          const label =
            step.key === 'documentos'
              ? (DOCUMENT_STATUS[step.status ?? ''] ?? 'Pendente')
              : step.done
                ? 'Concluída'
                : 'Pendente'
          return (
            <li key={step.key} className={step.done ? 'feita' : ''}>
              <span className="etapa-num" aria-hidden="true">
                {index + 1})
              </span>{' '}
              <span className="etapa-nome">{step.label}</span>
              <Badge tone={step.done ? 'success' : 'warning'}>{label}</Badge>
              <Link to={step.key === 'documentos' ? '/perfil/documentos' : '/perfil/pix'}>
                {step.done ? 'Ver' : 'Completar'}
              </Link>
            </li>
          )
        })}
      </ol>
      <p className="sub">CPF {profile.cpf}</p>
      {profile.verification_message && <Alert tone="info">{profile.verification_message}</Alert>}
    </Card>
  )
}
