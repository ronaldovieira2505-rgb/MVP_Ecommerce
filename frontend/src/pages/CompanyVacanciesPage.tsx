import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, brl, formatDateTime, type VacancyList } from '../api'
import { Alert, Badge, Card } from '../components/ui'

/** Minhas vagas: status, data, valor, posições preenchidas/total e total retido. */
export default function CompanyVacanciesPage() {
  const [data, setData] = useState<VacancyList | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<VacancyList>('/api/company/vacancies/')
      .then(setData)
      .catch(() => setError('Não foi possível carregar as suas vagas.'))
  }, [])

  if (!data && !error) return <p role="status">Carregando...</p>

  return (
    <Card>
      <h1>Minhas vagas</h1>
      <p>
        <Link to="/empresa/vagas/nova">Nova vaga</Link>
      </p>
      {error && <Alert tone="error">{error}</Alert>}
      {data && (
        <>
          <p>
            Total retido em custódia: <strong>{brl(data.total_retained_cents)}</strong>
          </p>
          {data.results.length === 0 && <p>Você ainda não publicou vagas.</p>}
          <ul>
            {data.results.map((v) => (
              <li key={v.id}>
                <Link to={`/empresa/vagas/${v.id}`}>{v.title}</Link> <Badge>{v.status_label}</Badge>
                <div>
                  {formatDateTime(v.starts_at)} · {brl(v.pay_per_person_cents)} por pessoa ·{' '}
                  {v.filled_positions}/{v.positions} posições
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}
