import { useRef, useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api, ApiError, type CnpjLookupResult } from '../api'
import { homePathFor, useAuth } from '../authContext'
import { Alert, Button, Card, Field, SelectField } from '../components/ui'
import { isValidCnpj, onlyDigits } from '../cnpj'

const STEPS = ['CNPJ', 'Dados', 'Pagamento', 'Acesso'] as const

const EMPTY = {
  cnpj: '',
  legal_name: '',
  trade_name: '',
  registration_status: '',
  street: '',
  number: '',
  complement: '',
  district: '',
  city: '',
  state: '',
  zip_code: '',
  state_registration: '',
  tax_regime: '',
  phone: '',
  preferred_payment_method: '',
  owner_name: '',
  email: '',
  password: '',
}

type Form = typeof EMPTY

export default function CompanySignupPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [form, setForm] = useState<Form>(EMPTY)
  const [cnpjError, setCnpjError] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [lookingUp, setLookingUp] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const lookup = useRef<{ cnpj: string; promise: Promise<boolean> } | null>(null)

  if (user) return <Navigate to={homePathFor(user.role)} replace />

  function set(name: keyof Form) {
    return (e: { target: { value: string } }) => setForm((f) => ({ ...f, [name]: e.target.value }))
  }

  /** Valida o CNPJ e, se estiver livre, consulta a BrasilAPI. Devolve se pode continuar. */
  function checkCnpj(): Promise<boolean> {
    setNotice('')
    if (!isValidCnpj(form.cnpj)) {
      setCnpjError('CNPJ inválido')
      return Promise.resolve(false)
    }
    setCnpjError('')
    const cnpj = onlyDigits(form.cnpj)
    // O blur e o clique em "Continuar" disparam juntos: compartilham a mesma consulta.
    if (lookup.current?.cnpj === cnpj) return lookup.current.promise
    const promise = runLookup(cnpj)
    lookup.current = { cnpj, promise }
    return promise
  }

  async function runLookup(cnpj: string): Promise<boolean> {
    setLookingUp(true)
    try {
      const result = await api<CnpjLookupResult>(`/api/cnpj/${cnpj}/`)
      if (result.found) {
        setForm((f) => ({ ...f, ...result.data }))
      } else if (result.detail) {
        setNotice(result.detail)
      }
      return true
    } catch (e) {
      lookup.current = null
      setCnpjError(e instanceof ApiError ? e.message : 'Não foi possível consultar o CNPJ.')
      return false
    } finally {
      setLookingUp(false)
    }
  }

  async function handleNext(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (step === 0) {
      if (!(await checkCnpj())) return
    }
    setStep((s) => s + 1)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await api('/api/auth/csrf/')
      await api('/api/companies/register/', {
        method: 'POST',
        body: { ...form, cnpj: onlyDigits(form.cnpj) },
      })
      await login(form.email, form.password)
      navigate('/empresa/vagas')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível concluir o cadastro.')
      setSubmitting(false)
    }
  }

  const isLast = step === STEPS.length - 1

  return (
    <Card>
      <h1>Cadastro de empresa</h1>
      <p aria-label="Etapa atual">
        Etapa {step + 1} de {STEPS.length}: {STEPS[step]}
      </p>
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={isLast ? handleSubmit : handleNext}>
        {step === 0 && (
          <>
            <Field
              label="CNPJ"
              inputMode="numeric"
              autoComplete="off"
              required
              value={form.cnpj}
              onChange={set('cnpj')}
              onBlur={() => form.cnpj && void checkCnpj()}
            />
            {cnpjError && <Alert tone="error">{cnpjError}</Alert>}
            {notice && <Alert tone="info">{notice}</Alert>}
            {lookingUp && <p role="status">Consultando CNPJ...</p>}
          </>
        )}
        {step === 1 && (
          <>
            {notice && <Alert tone="info">{notice}</Alert>}
            <Field label="Razão social" required value={form.legal_name} onChange={set('legal_name')} />
            <Field label="Nome fantasia" value={form.trade_name} onChange={set('trade_name')} />
            <Field
              label="Situação cadastral"
              value={form.registration_status}
              onChange={set('registration_status')}
            />
            <Field label="Logradouro" value={form.street} onChange={set('street')} />
            <Field label="Número" value={form.number} onChange={set('number')} />
            <Field label="Complemento" value={form.complement} onChange={set('complement')} />
            <Field label="Bairro" value={form.district} onChange={set('district')} />
            <Field label="Cidade" value={form.city} onChange={set('city')} />
            <Field label="UF" maxLength={2} value={form.state} onChange={set('state')} />
            <Field label="CEP" value={form.zip_code} onChange={set('zip_code')} />
            <Field
              label="Inscrição estadual (ou ISENTO)"
              required
              value={form.state_registration}
              onChange={set('state_registration')}
            />
            <SelectField
              label="Regime tributário"
              required
              value={form.tax_regime}
              onChange={set('tax_regime')}
            >
              <option value="">Selecione</option>
              <option value="SIMPLES">Simples Nacional</option>
              <option value="NORMAL">Normal</option>
            </SelectField>
          </>
        )}
        {step === 2 && (
          <>
            <Field
              label="Telefone"
              type="tel"
              autoComplete="tel"
              required
              value={form.phone}
              onChange={set('phone')}
            />
            <SelectField
              label="Meio de pagamento preferido"
              required
              value={form.preferred_payment_method}
              onChange={set('preferred_payment_method')}
            >
              <option value="">Selecione</option>
              <option value="PIX">PIX</option>
              <option value="BOLETO">Boleto</option>
              <option value="CARTAO">Cartão</option>
            </SelectField>
            <p>Guardamos só a sua preferência. Nenhum dado de cartão é coletado.</p>
          </>
        )}
        {step === 3 && (
          <>
            <Field
              label="Nome do responsável"
              autoComplete="name"
              required
              value={form.owner_name}
              onChange={set('owner_name')}
            />
            <Field
              label="E-mail"
              type="email"
              autoComplete="email"
              required
              value={form.email}
              onChange={set('email')}
            />
            <Field
              label="Senha"
              type="password"
              autoComplete="new-password"
              minLength={8}
              required
              value={form.password}
              onChange={set('password')}
            />
          </>
        )}
        <p>
          {step > 0 && (
            <Button type="button" variant="secondary" onClick={() => setStep((s) => s - 1)}>
              Voltar
            </Button>
          )}{' '}
          <Button type="submit" disabled={submitting}>
            {isLast ? 'Criar conta' : 'Continuar'}
          </Button>
        </p>
      </form>
      <p>
        <Link to="/login">Já tenho conta</Link>
      </p>
    </Card>
  )
}
