import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  brl,
  formatShift,
  formatTime,
  type JobGroupKey,
  type JobItem,
  type MyJobs,
} from '../api'
import { Alert, Badge, Button, Card, Loading } from '../components/ui'

const GROUPS: { key: JobGroupKey; title: string; empty: string }[] = [
  { key: 'waiting', title: 'Aguardando', empty: 'Nenhuma candidatura aguardando resposta.' },
  {
    key: 'upcoming',
    title: 'Aprovadas / Próximos turnos',
    empty: 'Nenhum turno confirmado por enquanto.',
  },
  { key: 'in_progress', title: 'Em andamento', empty: 'Nenhum turno em andamento.' },
  { key: 'completed', title: 'Concluídas', empty: 'Nenhum turno concluído ainda.' },
  { key: 'closed', title: 'Encerradas', empty: 'Nenhuma candidatura encerrada.' },
]

function badgeTone(status: string): 'neutral' | 'success' | 'warning' | 'info' {
  if (status === 'PENDENTE') return 'warning'
  if (['CONFIRMADA', 'PAGA', 'APROVADA'].includes(status)) return 'success'
  if (['EM_EXECUCAO', 'AGUARDANDO_VALIDACAO', 'CONTESTADA'].includes(status)) return 'info'
  return 'neutral'
}

/** Meus trabalhos (US38): candidaturas e alocações do prestador agrupadas por situação. */
export default function MyJobsPage() {
  const [jobs, setJobs] = useState<MyJobs | null>(null)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [notes, setNotes] = useState<
    Record<number, { tone: 'error' | 'success'; text: string } | undefined>
  >({})
  const [busyId, setBusyId] = useState<number | null>(null)
  const [confirmingId, setConfirmingId] = useState<number | null>(null)

  function load() {
    return api<MyJobs>('/api/workers/me/jobs/')
      .then(setJobs)
      .catch((err: Error) => setError(err.message))
  }

  useEffect(() => {
    void load()
  }, [])

  function say(item: JobItem, tone: 'error' | 'success', text: string) {
    setNotes((current) => ({ ...current, [item.id]: { tone, text } }))
  }

  async function checkIn(item: JobItem) {
    setNotes((current) => ({ ...current, [item.id]: undefined }))
    if (!navigator.geolocation) {
      say(item, 'error', 'Seu navegador não oferece localização. Use outro navegador ou aparelho.')
      return
    }
    setBusyId(item.id)
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const done = await api<JobItem>(`/api/assignments/${item.id}/check-in/`, {
            method: 'POST',
            body: {
              lat: position.coords.latitude,
              lng: position.coords.longitude,
              accuracy: position.coords.accuracy,
            },
          })
          await load()
          say(item, 'success', `Check-in feito às ${formatTime(done.check_in_at ?? '')}`)
        } catch (err) {
          say(item, 'error', (err as Error).message)
        } finally {
          setBusyId(null)
        }
      },
      (geoError) => {
        setBusyId(null)
        say(
          item,
          'error',
          geoError.code === 1
            ? 'A permissão de localização está bloqueada. Ative a localização para este site nas configurações do navegador (cadeado ao lado do endereço) e tente de novo.'
            : 'Não foi possível obter sua localização. Verifique o GPS e tente de novo.',
        )
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    )
  }

  async function checkOut(item: JobItem) {
    setConfirmingId(null)
    setBusyId(item.id)
    try {
      await api(`/api/assignments/${item.id}/check-out/`, { method: 'POST' })
      await load()
    } catch (err) {
      say(item, 'error', (err as Error).message)
    } finally {
      setBusyId(null)
    }
  }

  async function withdraw(item: JobItem) {
    setActionError('')
    try {
      await api(`/api/applications/${item.id}/withdraw/`, { method: 'POST' })
      await load()
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  if (error) return <Alert tone="error">{error}</Alert>
  if (!jobs) return <Loading />

  return (
    <>
      <h1>Meus trabalhos</h1>
      {actionError && <Alert tone="error">{actionError}</Alert>}
      {GROUPS.map((group) => {
        const items = jobs.groups[group.key]
        return (
          <section key={group.key} aria-labelledby={`grupo-${group.key}`}>
            <h2 id={`grupo-${group.key}`}>{group.title}</h2>
            {items.length === 0 && <p>{group.empty}</p>}
            {items.map((item) => (
              <Card key={`${item.kind}-${item.id}`}>
                <h3>
                  <Link to={`/vagas/${item.vacancy_id}`}>{item.title}</Link>
                </h3>
                <p className="marcadores">
                  <Badge tone={badgeTone(item.status)}>{item.status_label}</Badge>
                </p>
                <dl className="linhas">
                  <div>
                    <dt>Empresa</dt>
                    <dd>{item.company_name}</dd>
                  </div>
                  <div>
                    <dt>Turno</dt>
                    <dd>{formatShift(item.starts_at, item.ends_at)}</dd>
                  </div>
                  <div>
                    <dt>Você recebe</dt>
                    <dd>{brl(item.net_cents)}</dd>
                  </div>
                </dl>
                {item.kind === 'assignment' && (
                  <>
                    {item.status === 'CONFIRMADA' && item.can_check_in && (
                      <div className="acoes">
                        <Button busy={busyId === item.id} onClick={() => checkIn(item)}>
                          Cheguei
                        </Button>
                      </div>
                    )}
                    {item.status === 'CONFIRMADA' &&
                      !item.can_check_in &&
                      item.check_in_opens_at &&
                      item.check_in_closes_at &&
                      Date.now() < new Date(item.check_in_closes_at).getTime() && (
                        <p>O check-in abre às {formatTime(item.check_in_opens_at)}.</p>
                      )}
                    {item.check_in_at && (
                      <p>
                        Check-in feito às {formatTime(item.check_in_at)}
                        {item.check_out_at &&
                          ` · Saída às ${formatTime(item.check_out_at)}${
                            item.check_out_auto ? ' (registrada automaticamente)' : ''
                          }`}
                      </p>
                    )}
                    {item.can_check_out &&
                      (confirmingId === item.id ? (
                        <div className="acoes">
                          <Button busy={busyId === item.id} onClick={() => checkOut(item)}>
                            Confirmar encerramento
                          </Button>
                          <Button variant="secondary" onClick={() => setConfirmingId(null)}>
                            Voltar
                          </Button>
                        </div>
                      ) : (
                        <div className="acoes">
                          <Button onClick={() => setConfirmingId(item.id)}>Encerrar turno</Button>
                        </div>
                      ))}
                    {notes[item.id] && (
                      <Alert tone={notes[item.id]!.tone}>{notes[item.id]!.text}</Alert>
                    )}
                  </>
                )}
                {item.can_withdraw && (
                  <div className="acoes">
                    <Button variant="secondary" onClick={() => withdraw(item)}>
                      Desistir
                    </Button>
                  </div>
                )}
              </Card>
            ))}
          </section>
        )
      })}
    </>
  )
}
