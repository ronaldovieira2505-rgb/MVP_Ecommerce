import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import type { Role } from './api'
import { homePathFor, useAuth } from './authContext'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import CompanyConfirmPresencePage from './pages/CompanyConfirmPresencePage'
import CompanySignupPage from './pages/CompanySignupPage'
import CompanyVacanciesPage from './pages/CompanyVacanciesPage'
import CompanyVacancyDetailPage from './pages/CompanyVacancyDetailPage'
import CompanyVacancyNewPage from './pages/CompanyVacancyNewPage'
import LoginPage from './pages/LoginPage'
import MyJobsPage from './pages/MyJobsPage'
import WorkerWalletPage from './pages/WorkerWalletPage'
import Placeholder from './pages/Placeholder'
import VacancyPublicDetailPage from './pages/VacancyPublicDetailPage'
import VacancySearchPage from './pages/VacancySearchPage'
import SignupChoicePage from './pages/SignupChoicePage'
import WorkerDocumentsPage from './pages/WorkerDocumentsPage'
import WorkerHomePage from './pages/WorkerHomePage'
import WorkerPixPage from './pages/WorkerPixPage'
import WorkerSignupPage from './pages/WorkerSignupPage'

/** Manda para o login quem não está autenticado e para a home do papel quem não tem acesso. */
function RequireRole({ role }: { role: Role }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading rows={1} />
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== role) return <Navigate to={homePathFor(user.role)} replace />
  return <Outlet />
}

function Home() {
  const { user, loading } = useAuth()
  if (loading) return <Loading rows={1} />
  return <Navigate to={user ? homePathFor(user.role) : '/login'} replace />
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="cadastro" element={<SignupChoicePage />} />
        <Route path="cadastro/empresa" element={<CompanySignupPage />} />
        <Route path="cadastro/prestador" element={<WorkerSignupPage />} />
        {/* Busca pública: quem não pode se candidatar vê o que falta (US12). */}
        <Route path="vagas" element={<VacancySearchPage />} />
        <Route path="vagas/:id" element={<VacancyPublicDetailPage />} />
        <Route element={<RequireRole role="COMPANY" />}>
          <Route path="empresa/vagas" element={<CompanyVacanciesPage />} />
          <Route path="empresa/vagas/nova" element={<CompanyVacancyNewPage />} />
          <Route path="empresa/vagas/:id" element={<CompanyVacancyDetailPage />} />
          <Route path="empresa/confirmar-presenca" element={<CompanyConfirmPresencePage />} />
          <Route
            path="empresa/perfil"
            element={
              <Placeholder
                title="Perfil da empresa"
                issue="uma próxima issue"
                next={{
                  to: '/empresa/vagas',
                  label: 'Ir para minhas vagas',
                  hint: 'Os dados do cadastro já valem para publicar turnos e pagar em custódia.',
                }}
              />
            }
          />
        </Route>
        <Route element={<RequireRole role="WORKER" />}>
          <Route path="prestador/vagas" element={<Navigate to="/vagas" replace />} />
          <Route path="meus-trabalhos" element={<MyJobsPage />} />
          <Route path="carteira" element={<WorkerWalletPage />} />
          <Route path="prestador/perfil"element={<WorkerHomePage />} />
          <Route path="perfil/documentos" element={<WorkerDocumentsPage />} />
          <Route path="perfil/pix" element={<WorkerPixPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
