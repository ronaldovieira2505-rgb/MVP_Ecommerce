import { useEffect, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { api, ApiError, brl, formatDateTime, type Vacancy } from '../api'
import { CATEGORIES } from '../categories'
import { Alert, Badge, Button, Card, Field, SelectField } from '../components/ui'

const METHODS: Record<string, string> = { PIX: 'PIX', BOLETO: 'boleto', CARTAO: 'cartão' }
const READ_ONLY_HINT =
  'Para alterar valor ou número de pessoas, remova o anúncio (estorno total) e publique um novo.'

/** Converte um ISO UTC no valor de um input datetime-local (horário local). */
function toLocalInput(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Detalhe da vaga; aguardando pagamento mostra "Pagar e publicar" (PSP simulado). */
export default function CompanyVacancyDetailPage() {
  const { id } = useParams()
  const [vacancy, setVacancy] = useState<Vacancy | null>(null)
  const [error, setError] = useState('')
  const [paid, setPaid] = useState(false)
  const [saved, setSaved] = useState(false)
  const [editing, setEditing] = useState(false)
  const [confirmingRemove, setConfirmingRemove] = useState(false)
  const [removed, setRemoved] = useState(false)
  const [form, setForm] = useState({
    title: '',
    category: '',
    description: '',
    street: '',
    city: '',
    state: '',
    latitude: '',
    longitude: '',
    starts_at: '',
    ends_at: '',
  })

  useEffect(() => {
    api<Vacancy>(`/api/vacancies/${id}/`)
      .then(setVacancy)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Não foi possível carregar a vaga.'))
  }, [id])

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value })

  async function pay() {
    setError('')
    try {
      setVacancy(await api<Vacancy>(`/api/vacancies/${id}/pay/`, { method: 'POST' }))
      setPaid(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível concluir o pagamento.')
    }
  }

  function startEditing(v: Vacancy) {
    setForm({
      title: v.title,
      category: v.category,
      description: v.description,
      street: v.street ?? '',
      city: v.city ?? '',
      state: v.state ?? '',
      latitude: v.latitude ?? '',
      longitude: v.longitude ?? '',
      starts_at: toLocalInput(v.starts_at),
      ends_at: toLocalInput(v.ends_at),
    })
    setError('')
    setSaved(false)
    setConfirmingRemove(false)
    setEditing(true)
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setError('')
    try {
      setVacancy(
        await api<Vacancy>(`/api/vacancies/${id}/`, {
          method: 'PATCH',
          body: {
            ...form,
            starts_at: new Date(form.starts_at).toISOString(),
            ends_at: new Date(form.ends_at).toISOString(),
          },
        }),
      )
      setEditing(false)
      setSaved(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível salvar as alterações.')
    }
  }

  async function remove() {
    setError('')
    try {
      setVacancy(await api<Vacancy>(`/api/vacancies/${id}/remove/`, { method: 'POST' }))
      setRemoved(true)
      setEditing(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível remover o anúncio.')
    } finally {
      setConfirmingRemove(false)
    }
  }

  if (!vacancy && !error) return <p role="status">Carregando...</p>

  return (
    <Card>
      {error && <Alert tone="error">{error}</Alert>}
      {paid && <Alert tone="success">Pagamento confirmado. A vaga foi publicada.</Alert>}
      {saved && <Alert tone="success">Alterações salvas.</Alert>}
      {removed && <Alert tone="success">Anúncio removido. O valor foi estornado.</Alert>}
      {vacancy && editing && (
        <form onSubmit={save} noValidate>
          <h1>Editar vaga</h1>
          <Field label="Título" value={form.title} onChange={set('title')} />
          <SelectField label="Categoria" value={form.category} onChange={set('category')}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </SelectField>
          <Field label="Descrição do escopo" value={form.description} onChange={set('description')} />
          <Field label="Endereço" value={form.street} onChange={set('street')} />
          <Field label="Cidade" value={form.city} onChange={set('city')} />
          <Field label="UF" maxLength={2} value={form.state} onChange={set('state')} />
          <Field label="Latitude" value={form.latitude} onChange={set('latitude')} />
          <Field label="Longitude" value={form.longitude} onChange={set('longitude')} />
          <Field label="Início" type="datetime-local" value={form.starts_at} onChange={set('starts_at')} />
          <Field label="Fim" type="datetime-local" value={form.ends_at} onChange={set('ends_at')} />
          <Field label="Valor por pessoa" value={brl(vacancy.pay_per_person_cents)} readOnly />
          <Field label="Número de pessoas" value={String(vacancy.positions)} readOnly />
          <p>{READ_ONLY_HINT}</p>
          <Button type="submit">Salvar alterações</Button>{' '}
          <Button type="button" variant="secondary" onClick={() => setEditing(false)}>
            Cancelar
          </Button>
        </form>
      )}
      {vacancy && !editing && (
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
          {vacancy.status === 'PUBLICADA' && (
            <>
              <Button variant="secondary" onClick={() => startEditing(vacancy)}>
                Editar
              </Button>{' '}
              {!confirmingRemove ? (
                <Button variant="secondary" onClick={() => setConfirmingRemove(true)}>
                  Remover anúncio
                </Button>
              ) : (
                <Alert tone="info">
                  Remover o anúncio estorna o valor integral e expira as candidaturas pendentes.{' '}
                  <Button onClick={remove}>Confirmar remoção</Button>{' '}
                  <Button variant="secondary" onClick={() => setConfirmingRemove(false)}>
                    Voltar
                  </Button>
                </Alert>
              )}
            </>
          )}
        </>
      )}
    </Card>
  )
}
