import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

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
    <MemoryRouter initialEntries={['/cadastro/empresa']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

const CNPJ = '11222333000181'
const anonymous = () => ({ status: 403, body: { detail: 'Não autenticado' } })
const found = () => ({
  body: {
    found: true,
    available: true,
    data: {
      legal_name: 'Padaria Pão Quente LTDA',
      trade_name: 'Pão Quente',
      registration_status: 'ATIVA',
      street: 'Rua das Flores',
      number: '100',
      complement: '',
      district: 'Centro',
      city: 'São Paulo',
      state: 'SP',
      zip_code: '01001000',
    },
  },
})

async function typeCnpjAndContinue(value: string) {
  await userEvent.type(await screen.findByLabelText('CNPJ'), value)
  await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))
}

describe('Cadastro de empresa', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('preenche a razão social pela consulta ao sair do campo e deixa editar', async () => {
    mockApi({ 'GET /api/auth/me/': anonymous, [`GET /api/cnpj/${CNPJ}/`]: found })
    renderSignup()

    await userEvent.type(await screen.findByLabelText('CNPJ'), CNPJ)
    await userEvent.tab()
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))

    const legalName = await screen.findByLabelText('Razão social')
    expect(legalName).toHaveValue('Padaria Pão Quente LTDA')
    expect(screen.getByLabelText('Regime tributário')).toBeInTheDocument()
    expect(screen.queryByLabelText('Logradouro')).not.toBeInTheDocument()
    await userEvent.clear(legalName)
    await userEvent.type(legalName, 'Outro Nome')
    expect(legalName).toHaveValue('Outro Nome')
  })

  it('mostra "CNPJ inválido" e não consulta quando os dígitos não fecham', async () => {
    const fetchMock = mockApi({ 'GET /api/auth/me/': anonymous })
    renderSignup()

    await typeCnpjAndContinue('11222333000182')

    expect(await screen.findByRole('alert')).toHaveTextContent('CNPJ inválido')
    expect(fetchMock).toHaveBeenCalledTimes(1) // só o /api/auth/me/
  })

  it('avisa quando já existe conta para o CNPJ', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      [`GET /api/cnpj/${CNPJ}/`]: () => ({
        status: 409,
        body: { detail: 'Já existe uma conta para este CNPJ' },
      }),
    })
    renderSignup()

    await typeCnpjAndContinue(CNPJ)

    expect(await screen.findByRole('alert')).toHaveTextContent('Já existe uma conta para este CNPJ')
    expect(screen.queryByLabelText('Razão social')).not.toBeInTheDocument()
  })

  it('com a BrasilAPI fora do ar mostra aviso e permite preencher manualmente', async () => {
    mockApi({
      'GET /api/auth/me/': anonymous,
      [`GET /api/cnpj/${CNPJ}/`]: () => ({
        body: {
          found: false,
          available: false,
          detail: 'Não foi possível consultar o CNPJ agora. Preencha os dados manualmente.',
        },
      }),
    })
    renderSignup()

    await typeCnpjAndContinue(CNPJ)

    const legalName = await screen.findByLabelText('Razão social')
    expect(screen.getByRole('status')).toHaveTextContent('Preencha os dados manualmente')
    await userEvent.type(legalName, 'Empresa Manual LTDA')
    expect(legalName).toHaveValue('Empresa Manual LTDA')
  })

  it('conclui o cadastro em 3 etapas e mostra o aviso de cadastro em análise', async () => {
    let registered: unknown
    mockApi({
      'GET /api/auth/me/': anonymous,
      [`GET /api/cnpj/${CNPJ}/`]: found,
      'GET /api/auth/csrf/': () => ({ body: {} }),
      'POST /api/companies/register/': (init) => {
        registered = JSON.parse(String(init?.body))
        return { status: 201, body: { id: 1, verification_status: 'PENDENTE' } }
      },
      'POST /api/auth/login/': () => ({
        body: {
          id: 1,
          name: 'Padaria Pão Quente LTDA',
          email: 'maria@example.com',
          role: 'COMPANY',
          verification_status: 'PENDENTE',
        },
      }),
      'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
    })
    renderSignup()

    await typeCnpjAndContinue(CNPJ)
    expect(await screen.findByText(/Etapa 2 de 3/)).toBeInTheDocument()
    expect(screen.getByLabelText('Razão social')).toHaveValue('Padaria Pão Quente LTDA')
    await userEvent.selectOptions(screen.getByLabelText('Regime tributário'), 'SIMPLES')
    await userEvent.click(screen.getByRole('button', { name: 'Continuar' }))

    expect(await screen.findByText(/Etapa 3 de 3/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/cartão|número do cartão/i)).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Nome'), 'Maria Souza')
    await userEvent.type(screen.getByLabelText('E-mail'), 'maria@example.com')
    await userEvent.type(screen.getByLabelText('Senha'), 'senha-forte-123')
    await userEvent.click(screen.getByRole('button', { name: 'Criar conta' }))

    expect(await screen.findByText(/Cadastro em análise/)).toHaveTextContent(
      'Cadastro em análise: você poderá publicar vagas após a aprovação',
    )
    expect(registered).toMatchObject({
      cnpj: CNPJ,
      legal_name: 'Padaria Pão Quente LTDA',
      tax_regime: 'SIMPLES',
      city: 'São Paulo',
      owner_name: 'Maria Souza',
      email: 'maria@example.com',
    })
  })
})
