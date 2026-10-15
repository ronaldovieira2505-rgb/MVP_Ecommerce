import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      const handler = handlers[key]
      if (!handler) throw new Error(`Chamada inesperada: ${key}`)
      const { status = 200, body } = handler(init)
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(body),
      })
    }),
  )
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const vacancy = {
  id: 7,
  title: 'Carga e descarga',
  category_label: 'Carga e descarga',
  description: 'Descarregar caminhão',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  pay_per_person_cents: 10000,
  positions: 3,
  filled_positions: 0,
  total_cents: 30000,
  retained_cents: 0,
  status: 'AGUARDANDO_PAGAMENTO',
  status_label: 'Aguardando pagamento',
  payment_method: 'PIX',
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Vagas da empresa', () => {
  it('mostra o total a pagar (valor × pessoas) e cria a vaga', async () => {
    let sent: Record<string, unknown> = {}
    mockApi({
      ...session,
      'POST /api/vacancies/': (init) => {
        sent = JSON.parse(init?.body as string)
        return { status: 201, body: vacancy }
      },
      'GET /api/vacancies/7/': () => ({ body: vacancy }),
    })
    renderAt('/empresa/vagas/nova')

    await userEvent.type(await screen.findByLabelText('Título'), 'Carga e descarga')
    await userEvent.type(screen.getByLabelText('Descrição do escopo'), 'Descarregar')
    await userEvent.type(screen.getByLabelText('Latitude'), '-23.55')
    await userEvent.type(screen.getByLabelText('Longitude'), '-46.63')
    await userEvent.type(screen.getByLabelText('Início'), '2026-11-03T09:00')
    await userEvent.type(screen.getByLabelText('Fim'), '2026-11-03T13:00')
    await userEvent.type(screen.getByLabelText('Valor por pessoa (R$)'), '100,00')
    await userEvent.clear(screen.getByLabelText('Número de pessoas'))
    await userEvent.type(screen.getByLabelText('Número de pessoas'), '3')

    expect(screen.getByText(/Total a pagar/)).toHaveTextContent('R$ 300,00')
    await userEvent.click(screen.getByRole('button', { name: 'Criar vaga' }))

    expect(await screen.findByRole('button', { name: 'Pagar e publicar' })).toBeInTheDocument()
    expect(sent.pay_per_person_cents).toBe(10000)
    expect(sent.positions).toBe(3)
  })

  it('mostra o erro do servidor quando a vaga é recusada', async () => {
    mockApi({
      ...session,
      'POST /api/vacancies/': () => ({ status: 403, body: { detail: 'Cadastro em análise' } }),
    })
    renderAt('/empresa/vagas/nova')

    await userEvent.click(await screen.findByRole('button', { name: 'Criar vaga' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Cadastro em análise')
  })

  it('paga e publica a vaga', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: vacancy }),
      'POST /api/vacancies/7/pay/': () => ({
        body: { ...vacancy, status: 'PUBLICADA', status_label: 'Publicada', retained_cents: 30000 },
      }),
    })
    renderAt('/empresa/vagas/7')

    await userEvent.click(await screen.findByRole('button', { name: 'Pagar e publicar' }))

    expect(await screen.findByText('Pagamento confirmado. A vaga foi publicada.')).toBeInTheDocument()
    expect(screen.getByText('Publicada')).toBeInTheDocument()
  })

  it('edita a vaga publicada com valor e pessoas somente leitura', async () => {
    const published = {
      ...vacancy,
      category: 'CARGA_DESCARGA',
      street: '',
      city: '',
      state: '',
      latitude: '-23.550520',
      longitude: '-46.633308',
      status: 'PUBLICADA',
      status_label: 'Publicada',
    }
    let sent: Record<string, unknown> = {}
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: published }),
      'PATCH /api/vacancies/7/': (init) => {
        sent = JSON.parse(init?.body as string)
        return { body: { ...published, title: 'Novo título' } }
      },
    })
    renderAt('/empresa/vagas/7')

    await userEvent.click(await screen.findByRole('button', { name: 'Editar' }))
    expect(screen.getByLabelText('Valor por pessoa')).toHaveAttribute('readonly')
    expect(screen.getByLabelText('Número de pessoas')).toHaveAttribute('readonly')
    expect(screen.getByText(/remova o anúncio \(estorno total\)/)).toBeInTheDocument()

    await userEvent.clear(screen.getByLabelText('Título'))
    await userEvent.type(screen.getByLabelText('Título'), 'Novo título')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar alterações' }))

    expect(await screen.findByText('Alterações salvas.')).toBeInTheDocument()
    expect(sent.title).toBe('Novo título')
    expect(sent).not.toHaveProperty('positions')
    expect(sent).not.toHaveProperty('pay_per_person_cents')
  })

  it('mostra o bloqueio quando já há prestador aprovado', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: { ...vacancy, status: 'PUBLICADA', status_label: 'Publicada' } }),
      'POST /api/vacancies/7/remove/': () => ({
        status: 409,
        body: { detail: 'Não é possível alterar: já há prestador aprovado' },
      }),
    })
    renderAt('/empresa/vagas/7')

    await userEvent.click(await screen.findByRole('button', { name: 'Remover anúncio' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar remoção' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Não é possível alterar: já há prestador aprovado',
    )
  })

  it('remove o anúncio após confirmar', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: { ...vacancy, status: 'PUBLICADA', status_label: 'Publicada' } }),
      'POST /api/vacancies/7/remove/': () => ({
        body: { ...vacancy, status: 'CANCELADA', status_label: 'Cancelada' },
      }),
    })
    renderAt('/empresa/vagas/7')

    await userEvent.click(await screen.findByRole('button', { name: 'Remover anúncio' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar remoção' }))

    expect(await screen.findByText('Anúncio removido. O valor foi estornado.')).toBeInTheDocument()
    expect(screen.getByText('Cancelada')).toBeInTheDocument()
  })

  it('lista as vagas com posições e total retido', async () => {
    mockApi({
      ...session,
      'GET /api/company/vacancies/': () => ({
        body: {
          total_retained_cents: 30000,
          results: [{ ...vacancy, status: 'PUBLICADA', status_label: 'Publicada', filled_positions: 1 }],
        },
      }),
    })
    renderAt('/empresa/vagas')

    expect(await screen.findByText('Publicada')).toBeInTheDocument()
    expect(screen.getByText(/1\/3 posições/)).toBeInTheDocument()
    expect(screen.getByText(/Total retido em custódia/)).toHaveTextContent('R$ 300,00')
  })
})
