import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, brl, formatShift, type Vacancy, type VacancyList } from '../api'
import { Alert, Badge, Card, Loading, Slots } from '../components/ui'
import { badgeToneFor, toneFor } from '../status'

/** Uma vaga por ficha: estado na lombada, valor por pessoa e posições. */
function VacancyRow({ vacancy }: { vacancy: Vacancy }) {
  return (
    <li>
      <article className={`row row-${toneFor(vacancy.status)}`}>
        <div>
          <h2 className="row-titulo">
            <Link to={`/empresa/vagas/${vacancy.id}`}>{vacancy.title}</Link>
            <Badge tone={badgeToneFor(vacancy.status)}>{vacancy.status_label}</Badge>
          </h2>
          <p className="row-quando">{formatShift(vacancy.starts_at, vacancy.ends_at)}</p>
        </div>
        <div className="row-lado">
          <span className="row-valor">
            {brl(vacancy.pay_per_person_cents)}
            <small>por pessoa</small>
          </span>
          <Slots filled={vacancy.filled_positions} total={vacancy.positions} />
        </div>
      </article>
    </li>
  )
}

/** Minhas vagas: total retido em custódia e uma ficha por vaga. */
export default function CompanyVacanciesPage() {
  const [data, setData] = useState<VacancyList | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<VacancyList>('/api/company/vacancies/')
      .then(setData)
      .catch(() => setError('Não foi possível carregar as suas vagas.'))
  }, [])

  if (!data && !error) return <Loading />

  return (
    <>
      <Card tone="carimbo">
        <h1>Minhas vagas</h1>
        <p>
          Total retido em custódia
          <strong className="dinheiro">{brl(data?.total_retained_cents ?? 0)}</strong>
          <span className="dinheiro-nota">
            O dinheiro fica no PSP até a presença ser confirmada.
          </span>
        </p>
        <div className="acoes">
          <Link to="/empresa/vagas/nova" className="btn btn-primary">
            Nova vaga
          </Link>
        </div>
      </Card>

      {error && <Alert tone="error">{error}</Alert>}

      {data &&
        (data.results.length === 0 ? (
          <Card>
            <div className="vazio">
              <h2>Publique o primeiro turno</h2>
              <p>
                Descreva o serviço, diga quantas pessoas precisa e pague em custódia. A vaga fica
                visível para os prestadores aprovados assim que o pagamento é confirmado.
              </p>
              <Link to="/empresa/vagas/nova" className="btn btn-primary">
                Nova vaga
              </Link>
            </div>
          </Card>
        ) : (
          <ul className="row-list">
            {data.results.map((v) => (
              <VacancyRow key={v.id} vacancy={v} />
            ))}
          </ul>
        ))}
    </>
  )
}
