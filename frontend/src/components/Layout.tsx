import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import type { Role } from '../api'
import { useAuth } from '../authContext'
import NotificationBell from './NotificationBell'
import { Alert, Button } from './ui'

const MENU: Record<Role, { to: string; label: string }[]> = {
  COMPANY: [
    { to: '/empresa/vagas', label: 'Minhas vagas' },
    { to: '/empresa/perfil', label: 'Perfil da empresa' },
  ],
  WORKER: [
    { to: '/vagas', label: 'Buscar vagas' },
    { to: '/meus-trabalhos', label: 'Meus trabalhos' },
    { to: '/prestador/perfil', label: 'Meu perfil' },
  ],
  ADMIN: [],
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <>
      <a className="pular" href="#conteudo">
        Ir para o conteúdo
      </a>
      <header className="app-header">
        <Link to="/" className="app-brand">
          Conecta Já
        </Link>
        {user && (
          <nav className="app-nav" aria-label="Menu principal">
            {MENU[user.role].map((item) => (
              <NavLink key={item.to} to={item.to}>
                {item.label}
              </NavLink>
            ))}
            {user.role === 'ADMIN' && <a href="/admin/">Painel administrativo</a>}
          </nav>
        )}
        <div className="app-header-actions">
          {user ? (
            <>
              <NotificationBell />
              <Button variant="ghost" onClick={handleLogout}>
                Sair
              </Button>
            </>
          ) : (
            <Link to="/login" className="btn btn-ghost">
              Entrar
            </Link>
          )}
        </div>
      </header>
      <main className="app-main" id="conteudo">
        {user?.role === 'COMPANY' && user.verification_status === 'PENDENTE' && (
          <Alert tone="info">
            Cadastro em análise: você poderá publicar vagas após a aprovação
          </Alert>
        )}
        <Outlet />
      </main>
    </>
  )
}
