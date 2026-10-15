import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError, brl, formatDateTime, type Vacancy } from '../api'
import { Alert, Badge, Button, Card } from '../components/ui'

const METHODS: Record<string, string> = { PIX: 'PIX', BOLETO: 'boleto', CARTAO: 'cartão' }

/** Detalhe da vaga; aguardando pagamento mostra "Pagar e publicar" (PSP simulado). */
export default function CompanyVacancyDetailPage() {
  const { id } = useParams()
  const [vacancy, setVacancy] = useState<Vacancy | null>(null)
  const [error, setError] = useState('')
  const [paid, setPaid] = useState(false)

  useEffect(() => {
    api<Vacancy>(`/api/vacancies/${id}/`)
      .then(setVacancy)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Não foi possível carregar a vaga.'))
  }, [id])

  async function pay() {
    setError('')
    try {
      setVacancy(await api<Vacancy>(`/api/vacancies/${id}/pay/`, { method: 'POST' }))
      setPaid(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível concluir o pagamento.')
    }
  }

  if (!vacancy && !error) return <p role="status">Carregando...</p>

  return (
    <Card>
      {error && <Alert tone="error">{error}</Alert>}
      {paid && <Alert tone="success">Pagamento confirmado. A vaga foi publicada.</Alert>}
      {vacancy && (
        <>
          <h1>{vacancy.title}</h1>
          <Badge>{vacancy.status_label}</Badge>
          <p>{vacancy.description}</p>
          <p>
            {vacancy.category_label} · {formatDateTime(vacancy.starts_at)} a{' '}
            {formatDateTime(vacancy.ends_at)}
          </p>
          <p>
            {brl(vacancy.pay_per_person_cents)} por pessoa · {vacancy.filled_positions}/
            {vacancy.positions} posições
          </p>
          <p>
            Total a pagar: <strong>{brl(vacancy.total_cents)}</strong>
          </p>
          {vacancy.status === 'AGUARDANDO_PAGAMENTO' && (
            <>
              {vacancy.payment_method && (
                <p>Meio de pagamento preferido: {METHODS[vacancy.payment_method] ?? vacancy.payment_method}</p>
              )}
              <Button onClick={pay}>Pagar e publicar</Button>
            </>
          )}
        </>
      )}
    </Card>
  )
}
