import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, brl, type Vacancy } from '../api'
import { CATEGORIES } from '../categories'
import { Alert, Button, Card, Field, SelectField } from '../components/ui'

/** Converte "150,50" em centavos; 0 se não for um número válido. */
function toCents(text: string): number {
  const value = Number(text.replace(/\./g, '').replace(',', '.'))
  return Number.isFinite(value) ? Math.round(value * 100) : 0
}

/** Publicar vaga: cria em AGUARDANDO_PAGAMENTO e leva ao pagamento. */
export default function CompanyVacancyNewPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    title: '',
    category: 'CARGA_DESCARGA',
    description: '',
    street: '',
    number: '',
    city: '',
    state: '',
    latitude: '',
    longitude: '',
    starts_at: '',
    ends_at: '',
    pay: '',
    positions: '1',
  })
  const [error, setError] = useState('')
  const [locating, setLocating] = useState(false)

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value })

  const perPerson = toCents(form.pay)
  const positions = Number(form.positions) || 0
  const total = perPerson * positions

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError('Seu navegador não permite obter a localização.')
      return
    }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((f) => ({
          ...f,
          latitude: pos.coords.latitude.toFixed(6),
          longitude: pos.coords.longitude.toFixed(6),
        }))
        setLocating(false)
      },
      () => {
        setError('Não foi possível obter sua localização. Informe as coordenadas.')
        setLocating(false)
      },
    )
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    const toIso = (v: string) => (v ? new Date(v).toISOString() : '')
    try {
      const vacancy = await api<Vacancy>('/api/vacancies/', {
        method: 'POST',
        body: {
          title: form.title,
          category: form.category,
          description: form.description,
          street: form.street,
          number: form.number,
          city: form.city,
          state: form.state,
          latitude: form.latitude,
          longitude: form.longitude,
          starts_at: toIso(form.starts_at),
          ends_at: toIso(form.ends_at),
          pay_per_person_cents: perPerson,
          positions,
        },
      })
      navigate(`/empresa/vagas/${vacancy.id}`)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível criar a vaga.')
    }
  }

  return (
    <Card>
      <h1>Nova vaga</h1>
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={onSubmit} noValidate>
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
        <Field label="Número" value={form.number} onChange={set('number')} />
        <Field label="Cidade" value={form.city} onChange={set('city')} />
        <Field label="UF" maxLength={2} value={form.state} onChange={set('state')} />
        <Field label="Latitude" value={form.latitude} onChange={set('latitude')} />
        <Field label="Longitude" value={form.longitude} onChange={set('longitude')} />
        <p className="sub">
          As coordenadas definem o raio do check-in: o prestador só consegue bater o ponto perto
          do local.
        </p>
        <div className="acoes">
          <Button type="button" variant="secondary" onClick={useMyLocation} disabled={locating}>
            Usar minha localização
          </Button>
        </div>
        <Field label="Início" type="datetime-local" value={form.starts_at} onChange={set('starts_at')} />
        <Field label="Fim" type="datetime-local" value={form.ends_at} onChange={set('ends_at')} />
        <Field label="Valor por pessoa (R$)" inputMode="decimal" value={form.pay} onChange={set('pay')} />
        <Field label="Número de pessoas" type="number" min={1} value={form.positions} onChange={set('positions')} />
        <p className="total" aria-live="polite">
          Total a pagar <strong>{brl(total)}</strong>
        </p>
        <p className="sub">
          O valor fica retido em custódia na publicação e é liberado conforme a presença.
        </p>
        <Button type="submit" block>
          Criar vaga
        </Button>
      </form>
    </Card>
  )
}
