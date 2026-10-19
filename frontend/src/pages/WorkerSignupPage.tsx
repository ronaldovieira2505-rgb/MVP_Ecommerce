import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { homePathFor, useAuth } from '../authContext'
import { Alert, Button, Card, Field } from '../components/ui'
import { onlyDigits } from '../cnpj'
import { ageFrom, isValidCpf } from '../cpf'

const EMPTY = {
  full_name: '',
  cpf: '',
  phone: '',
  birth_date: '',
  email: '',
  password: '',
}

type Form = typeof EMPTY

export default function WorkerSignupPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState<Form>(EMPTY)
  const [cpfError, setCpfError] = useState('')
  const [birthError, setBirthError] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Recém-cadastrado cai no painel "Complete seu perfil"; quem já tinha conta vai para a home.
  if (user) {
    const target = user.role === 'WORKER' ? '/prestador/perfil' : homePathFor(user.role)
    return <Navigate to={target} replace />
  }

  function set(name: keyof Form) {
    return (e: { target: { value: string } }) => setForm((f) => ({ ...f, [name]: e.target.value }))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    const cpfOk = isValidCpf(form.cpf)
    const adult = form.birth_date !== '' && ageFrom(form.birth_date) >= 18
    setCpfError(cpfOk ? '' : 'CPF inválido')
    setBirthError(adult ? '' : 'É preciso ter 18 anos ou mais')
    if (!cpfOk || !adult) return

    setSubmitting(true)
    try {
      await api('/api/auth/csrf/')
      await api('/api/workers/register/', {
        method: 'POST',
        body: { ...form, cpf: onlyDigits(form.cpf) },
      })
      await login(form.email, form.password)
      navigate('/prestador/perfil')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível concluir o cadastro.')
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <h1>Cadastro de prestador</h1>
      <p>Sem currículo: informe seus dados básicos. Documentos e chave PIX ficam para a próxima etapa.</p>
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={handleSubmit}>
        <Field
          label="Nome completo"
          autoComplete="name"
          required
          value={form.full_name}
          onChange={set('full_name')}
        />
        <Field
          label="CPF"
          inputMode="numeric"
          autoComplete="off"
          required
          value={form.cpf}
          onChange={set('cpf')}
        />
        {cpfError && <Alert tone="error">{cpfError}</Alert>}
        <Field
          label="Telefone"
          type="tel"
          autoComplete="tel"
          required
          value={form.phone}
          onChange={set('phone')}
        />
        <Field
          label="Data de nascimento"
          type="date"
          autoComplete="bday"
          required
          value={form.birth_date}
          onChange={set('birth_date')}
        />
        {birthError && <Alert tone="error">{birthError}</Alert>}
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
        <p>
          <Button type="submit" busy={submitting}>
            Criar conta
          </Button>
        </p>
      </form>
      <p>
        <Link to="/login">Já tenho conta</Link>
      </p>
    </Card>
  )
}
