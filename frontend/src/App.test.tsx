import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from './AuthProvider'
import AppRoutes from './routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  const fetchMock = vi.fn((path: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${path}`
    const handler = handlers[key]
    if (!handler) throw new Error(`Chamada inesperada: ${key}`)
    const { status = 200, body } = handler(init)
    return Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

const company = {
  id: 1,
  name: 'Empresa 1 LTDA',
  email: 'e@example.com',
  role: 'COMPANY',
  verification_status: 'APROVADA',
}
const worker = { ...company, id: 2, name: 'Maria', role: 'WORKER', verification_status: 'APROVADO' }
const noNotifications = () => ({ body: { unread_count: 0, results: [] } })
const anonymous = () => ({ status: 403, body: { detail: 'Não autenticado' } })

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('manda visitante de rota protegida para o login', async () => {
    mockApi({ 'GET /api/auth/me/': anonymous })

    renderApp('/empresa/vagas')

    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Criar conta' })).toBeInTheDocument()
  })

  it('mostra a marca Conecta Já no cabeçalho', async () => {
    mockApi({ 'GET /api/auth/me/': anonymous })

    renderApp('/login')

    expect(await screen.findByRole('link', { name: 'Conecta Já' })).toBeInTheDocument()
  })

  it('exibe mensagem de erro quando as credenciais são inválidas', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/auth/csrf/': () => ({ body: {} }),
      'POST /api/auth/login/': () => ({ status: 400, body: { detail: 'E-mail ou senha inválidos' } }),
    })
    renderApp('/login')

    await userEvent.type(await screen.findByLabelText('E-mail'), 'x@example.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'errada')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('E-mail ou senha inválidos')
  })

  it('redireciona a empresa para "Minhas vagas" após o login', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/auth/csrf/': () => ({ body: {} }),
      'POST /api/auth/login/': () => ({ body: company }),
      'GET /api/notifications/': noNotifications,
    })
    renderApp('/login')

    await userEvent.type(await screen.findByLabelText('E-mail'), 'e@example.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-forte-123')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('heading', { name: 'Minhas vagas' })).toBeInTheDocument()
  })

  it('redireciona o prestador para "Buscar vagas" após o login', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/auth/csrf/': () => ({ body: {} }),
      'POST /api/auth/login/': () => ({ body: worker }),
      'GET /api/notifications/': noNotifications,
    })
    renderApp('/login')

    await userEvent.type(await screen.findByLabelText('E-mail'), 'm@example.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-forte-123')
    await userEvent.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByRole('heading', { name: 'Buscar vagas' })).toBeInTheDocument()
  })

  it('"Criar conta" leva à escolha entre Empresa e Prestador', async () => {
    mockApi({ 'GET /api/auth/me/': anonymous })
    renderApp('/login')

    await userEvent.click(await screen.findByRole('link', { name: 'Criar conta' }))

    expect(await screen.findByRole('link', { name: 'Sou Empresa' })).toHaveAttribute(
      'href',
      '/cadastro/empresa',
    )
    expect(screen.getByRole('link', { name: 'Sou Prestador' })).toHaveAttribute(
      'href',
      '/cadastro/prestador',
    )
  })

  it('mostra o menu do papel e impede acesso à área de outro papel', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({ body: worker }),
      'GET /api/notifications/': noNotifications,
    })

    renderApp('/empresa/vagas')

    expect(await screen.findByRole('heading', { name: 'Buscar vagas' })).toBeInTheDocument()
    const menu = screen.getByRole('navigation', { name: 'Menu principal' })
    expect(menu).toHaveTextContent('Buscar vagas')
    expect(menu).not.toHaveTextContent('Minhas vagas')
  })

  it('mostra contador do sino e marca notificação como lida', async () => {
    let unread = true
    mockApi({
      'GET /api/auth/me/': () => ({ body: company }),
      'GET /api/notifications/': () => ({
        body: {
          unread_count: unread ? 1 : 0,
          results: [
            {
              id: 7,
              kind: 'x',
              title: 'Vaga paga',
              message: '',
              link: '',
              read: !unread,
              created_at: '2026-11-01T12:00:00Z',
            },
          ],
        },
      }),
      'POST /api/notifications/7/read/': () => {
        unread = false
        return { body: {} }
      },
    })
    renderApp('/empresa/vagas')

    const bell = await screen.findByRole('button', { name: /Notificações \(1 não lidas\)/ })
    await userEvent.click(bell)
    expect(await screen.findByText('Vaga paga')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Marcar como lida' }))

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /Notificações \(0 não lidas\)/ }),
      ).toBeInTheDocument(),
    )
  })

  it('encerra a sessão ao sair', async () => {
    mockApi({
      'GET /api/auth/me/': () => ({ body: company }),
      'GET /api/notifications/': noNotifications,
      'POST /api/auth/logout/': () => ({ status: 204 }),
    })
    renderApp('/empresa/vagas')

    await userEvent.click(await screen.findByRole('button', { name: 'Sair' }))

    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
  })
})
