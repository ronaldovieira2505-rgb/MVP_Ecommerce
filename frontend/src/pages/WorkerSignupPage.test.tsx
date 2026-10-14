import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'
import { ageFrom, isValidCpf } from '../cpf'

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

function renderSignup() {
  return render(
    <MemoryRouter initialEntries={['/cadastro/prestador']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

const anonymous = () => ({ status: 403, body: { detail: 'Não autenticado' } })
const CPF = '12345678909'

async function fill({ cpf = CPF, birth = '1990-05-20' } = {}) {
  await userEvent.type(await screen.findByLabelText('Nome completo'), 'João da Silva')
  await userEvent.type(screen.getByLabelText('CPF'), cpf)
  await userEvent.type(screen.getByLabelText('Telefone'), '11999998888')
  await userEvent.type(screen.getByLabelText('Data de nascimento'), birth)
  await userEvent.type(screen.getByLabelText('E-mail'), 'joao@example.com')
  await userEvent.type(screen.getByLabelText('Senha'), 'senha-forte-123')
  await userEvent.click(screen.getByRole('button', { name: 'Criar conta' }))
}

describe('validação local', () => {
  it('valida os dígitos verificadores do CPF', () => {
    expect(isValidCpf(CPF)).toBe(true)
    expect(isValidCpf('123.456.789-09')).toBe(true)
    expect(isValidCpf('12345678900')).toBe(false)
    expect(isValidCpf('11111111111')).toBe(false)
  })

  it('calcula a idade completa', () => {
    const today = new Date(2026, 9, 14)
    expect(ageFrom('2008-10-14', today)).toBe(18)
    expect(ageFrom('2008-10-15', today)).toBe(17)
  })
})

describe('Cadastro de prestador', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('cria a conta, entra e mostra o passo a passo "Complete seu perfil"', async () => {
    let registered: unknown
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/auth/csrf/': () => ({ body: {} }),
      'POST /api/workers/register/': (init) => {
        registered = JSON.parse(String(init?.body))
        return { status: 201, body: { id: 1, cpf: '***.456.789-**' } }
      },
      'POST /api/auth/login/': () => ({
        body: {
          id: 1,
          name: 'João da Silva',
          email: 'joao@example.com',
          role: 'WORKER',
          verification_status: 'PENDENTE_DOCUMENTOS',
        },
      }),
      'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
      'GET /api/workers/me/': () => ({
        body: {
          id: 1,
          full_name: 'João da Silva',
          cpf: '***.456.789-**',
          phone: '****8888',
          verification_status: 'PENDENTE_DOCUMENTOS',
          profile_steps: [
            { key: 'documentos', label: 'Documentos e selfie', done: false, status: 'PENDENTE_DOCUMENTOS' },
            { key: 'pix', label: 'Chave PIX', done: false },
          ],
        },
      }),
    })
    renderSignup()

    await fill()

    expect(await screen.findByRole('heading', { name: 'Complete seu perfil' })).toBeInTheDocument()
    const steps = screen.getByRole('list', { name: 'Etapas do perfil' })
    expect(steps).toHaveTextContent('1) Documentos e selfie')
    expect(steps).toHaveTextContent('2) Chave PIX')
    expect(steps).toHaveTextContent('Pendente')
    expect(screen.getByText(/\*\*\*\.456\.789-\*\*/)).toBeInTheDocument()
    expect(registered).toMatchObject({
      full_name: 'João da Silva',
      cpf: CPF,
      phone: '11999998888',
      birth_date: '1990-05-20',
      email: 'joao@example.com',
    })
  })

  it('mostra "CPF inválido" e não envia o cadastro', async () => {
    const fetchMock = mockApi({ 'GET /api/auth/me/': anonymous })
    renderSignup()

    await fill({ cpf: '12345678900' })

    expect(await screen.findByRole('alert')).toHaveTextContent('CPF inválido')
    expect(fetchMock).toHaveBeenCalledTimes(1) // só o /api/auth/me/
  })

  it('mostra "É preciso ter 18 anos ou mais" para menores', async () => {
    const fetchMock = mockApi({ 'GET /api/auth/me/': anonymous })
    renderSignup()
    const year = new Date().getFullYear() - 10

    await fill({ birth: `${year}-01-01` })

    expect(await screen.findByRole('alert')).toHaveTextContent('É preciso ter 18 anos ou mais')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('mostra a mensagem do servidor quando CPF ou e-mail já existem', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      'GET /api/auth/csrf/': () => ({ body: {} }),
      'POST /api/workers/register/': () => ({
        status: 409,
        body: { detail: 'Já existe uma conta para este CPF' },
      }),
    })
    renderSignup()

    await fill()

    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe uma conta para este CPF')
  })
})
