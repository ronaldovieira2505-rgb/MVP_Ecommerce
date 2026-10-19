import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  api,
  brl,
  formatShift,
  type JobGroupKey,
  type JobItem,
  type MyJobs,
} from '../api'
import { Alert, Badge, Button, Card } from '../components/ui'

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

  function load() {
    return api<MyJobs>('/api/workers/me/jobs/')
      .then(setJobs)
      .catch((err: Error) => setError(err.message))
  }

  useEffect(() => {
    void load()
  }, [])

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
  if (!jobs) return <p role="status">Carregando...</p>

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
