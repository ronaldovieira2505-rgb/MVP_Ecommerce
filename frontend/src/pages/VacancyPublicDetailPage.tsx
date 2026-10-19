import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, brl, formatShift, type JobItem, type VacancyPublicDetail } from '../api'
import { Alert, Badge, Button, Card } from '../components/ui'

/** Detalhe da vaga para o prestador: descrição, endereço com mapa e valor líquido (US17). */
export default function VacancyPublicDetailPage() {
  const { id } = useParams()
  const [vacancy, setVacancy] = useState<VacancyPublicDetail | null>(null)
  const [error, setError] = useState('')
  const [applying, setApplying] = useState(false)
  const [applyError, setApplyError] = useState('')

  useEffect(() => {
    api<VacancyPublicDetail>(`/api/vacancies/${id}/`)
      .then(setVacancy)
      .catch((err: Error) => setError(err.message))
  }, [id])

  async function handleApply() {
    setApplying(true)
    setApplyError('')
    try {
      const application = await api<JobItem>(`/api/vacancies/${id}/apply/`, { method: 'POST' })
      setVacancy((current) =>
        current && {
          ...current,
          can_apply: false,
          apply_blocker: 'Você já se candidatou a esta vaga.',
          my_application: {
            id: application.id,
            status: application.status,
            status_label: application.status_label,
          },
        },
      )
    } catch (err) {
      setApplyError((err as Error).message)
    } finally {
      setApplying(false)
    }
  }

  if (error) return <Alert tone="error">{error}</Alert>
  if (!vacancy) return <p role="status">Carregando...</p>

  const sent = Boolean(vacancy.my_application)

  const address = [
    [vacancy.street, vacancy.number].filter(Boolean).join(', '),
    vacancy.complement,
    vacancy.district,
    [vacancy.city, vacancy.state].filter(Boolean).join('/'),
  ]
    .filter(Boolean)
    .join(' · ')
  const mapUrl = `https://www.openstreetmap.org/?mlat=${vacancy.latitude}&mlon=${vacancy.longitude}#map=17/${vacancy.latitude}/${vacancy.longitude}`

  return (
    <Card tone={vacancy.payment_guaranteed ? 'carimbo' : undefined}>
      <p>
        <Link to="/vagas">Voltar para a busca</Link>
      </p>
      <h1>{vacancy.title}</h1>
      <p className="marcadores">
        {vacancy.urgent && <Badge tone="warning">Urgente</Badge>}
        {vacancy.payment_guaranteed && <Badge tone="success">Pagamento garantido</Badge>}
      </p>
      <p className="descricao">{vacancy.description}</p>
      <dl className="linhas">
        <div>
          <dt>Contratante</dt>
          <dd>{vacancy.company_name}</dd>
        </div>
        <div>
          <dt>Serviço</dt>
          <dd>{vacancy.category_label}</dd>
        </div>
        <div>
          <dt>Turno</dt>
          <dd>{formatShift(vacancy.starts_at, vacancy.ends_at)}</dd>
        </div>
        <div>
          <dt>Local</dt>
          <dd>
            {address}{' '}
            <a href={mapUrl} target="_blank" rel="noreferrer">
              Ver no mapa
            </a>
          </dd>
        </div>
        <div>
          <dt>Em aberto</dt>
          <dd>
            {vacancy.remaining_positions}{' '}
            {vacancy.remaining_positions === 1 ? 'vaga restante' : 'vagas restantes'}
          </dd>
        </div>
      </dl>
      <dl className="linhas">
        <div>
          <dt>Valor do turno</dt>
          <dd>{brl(vacancy.gross_cents)}</dd>
        </div>
        <div>
          <dt>Taxa da plataforma ({vacancy.fee_percent}%)</dt>
          <dd>− {brl(vacancy.fee_cents)}</dd>
        </div>
        <div className="linha-total">
          <dt>Você recebe</dt>
          <dd>
            <strong>{brl(vacancy.net_cents)}</strong>
          </dd>
        </div>
      </dl>
      <div className="acoes">
        <Button disabled={!vacancy.can_apply || applying} onClick={handleApply}>
          {sent ? 'Candidatura enviada' : 'Quero esta vaga'}
        </Button>
      </div>
      {sent && vacancy.my_application?.status === 'PENDENTE' && (
        <Alert tone="success">
          Candidatura enviada! Acompanhe em <Link to="/meus-trabalhos">Meus trabalhos</Link>.
        </Alert>
      )}
      {applyError && <Alert tone="error">{applyError}</Alert>}
      {vacancy.apply_blocker && !applyError && <Alert>{vacancy.apply_blocker}</Alert>}
    </Card>
  )
}
