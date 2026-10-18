import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { ApiError } from '../api'
import { homePathFor, useAuth } from '../authContext'
import { Alert, Button, Card, Field } from '../components/ui'

export default function LoginPage() {
  const { user, login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate to={homePathFor(user.role)} replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await login(email, password)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível entrar. Tente novamente.')
      setSubmitting(false)
    }
  }

  return (
    <div className="entrada">
      <Card tone="colete">
        <h1>Entrar</h1>
        {error && <Alert tone="error">{error}</Alert>}
        <form onSubmit={handleSubmit}>
          <Field
            label="E-mail"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Field
            label="Senha"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Button type="submit" block disabled={submitting}>
            Entrar
          </Button>
        </form>
        <div className="acoes">
          <Link to="/cadastro" className="btn btn-secondary btn-block">
            Criar conta
          </Link>
        </div>
      </Card>
      <aside className="promessa">
        <p className="promessa-garantia">Pagamento garantido</p>
        <h2>O valor do turno é retido antes de alguém começar a trabalhar.</h2>
        <p>
          A empresa paga no momento em que publica a vaga. O dinheiro fica em custódia e só é
          liberado para o prestador quando a presença é confirmada.
        </p>
        <p>Turnos de carga e descarga, obra, limpeza, varejo e eventos.</p>
      </aside>
    </div>
  )
}
