import { render, screen, within } from '@testing-library/react'
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

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: {
      id: 1,
      name: 'João',
      email: 'joao@example.com',
      role: 'WORKER',
      verification_status: 'APROVADO',
    },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const vacancy = {
  id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  category: 'CARGA_DESCARGA',
  category_label: 'Carga e descarga',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  district: 'Sé',
  city: 'São Paulo',
  state: 'SP',
  gross_cents: 10000,
  fee_percent: 3,
  fee_cents: 300,
  net_cents: 9700,
  remaining_positions: 2,
  payment_guaranteed: true,
  urgent: false,
  distance_km: null,
  description: 'Descarregar caminhão',
  street: 'Praça da Sé',
  number: '1',
  complement: '',
  zip_code: '',
  latitude: '-23.550520',
  longitude: '-46.633308',
  can_apply: true,
  apply_blocker: null,
  my_application: null,
}

const job = {
  kind: 'application',
  id: 11,
  vacancy_id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  gross_cents: 10000,
  net_cents: 9700,
  status: 'PENDENTE',
  status_label: 'Pendente',
  can_withdraw: true,
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

afterEach(() => vi.unstubAllGlobals())

describe('Candidatar-se (US37)', () => {
  it('candidata com um clique, confirma sem sair da página e passa a "Candidatura enviada"', async () => {
    const fetchMock = mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: vacancy }),
      'POST /api/vacancies/7/apply/': () => ({ status: 201, body: job }),
    })
    renderAt('/vagas/7')

    await userEvent.click(await screen.findByRole('button', { name: 'Quero esta vaga' }))

    expect(await screen.findByText(/Candidatura enviada!/)).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Candidatura enviada' })
    expect(button).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/vacancies/7/apply/',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('mostra "Candidatura enviada" quando já se candidatou', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({
        body: {
          ...vacancy,
          can_apply: false,
          apply_blocker: 'Você já se candidatou a esta vaga.',
          my_application: { id: 11, status: 'PENDENTE', status_label: 'Pendente' },
        },
      }),
    })
    renderAt('/vagas/7')
    expect(await screen.findByRole('button', { name: 'Candidatura enviada' })).toBeDisabled()
  })

  it('mostra o erro do servidor quando há turno em horário sobreposto', async () => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({ body: vacancy }),
      'POST /api/vacancies/7/apply/': () => ({
        status: 409,
        body: { detail: 'Você já tem um turno nesse horário.' },
      }),
    })
    renderAt('/vagas/7')
    await userEvent.click(await screen.findByRole('button', { name: 'Quero esta vaga' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Você já tem um turno nesse horário.',
    )
  })

  it.each([
    'As candidaturas desta vaga estão encerradas.',
    'Esta vaga está lotada.',
    'Sua conta está suspensa até 10/11/2026.',
  ])('desabilita o botão e explica o motivo: %s', async (reason) => {
    mockApi({
      ...session,
      'GET /api/vacancies/7/': () => ({
        body: { ...vacancy, can_apply: false, apply_blocker: reason },
      }),
    })
    renderAt('/vagas/7')
    expect(await screen.findByRole('button', { name: 'Quero esta vaga' })).toBeDisabled()
    expect(screen.getByText(reason)).toBeInTheDocument()
  })
})

describe('Meus trabalhos (US38)', () => {
  const groups = {
    waiting: [job],
    upcoming: [
      { ...job, kind: 'assignment', id: 21, status: 'CONFIRMADA', status_label: 'Confirmada', can_withdraw: false, title: 'Turno confirmado' },
    ],
    in_progress: [],
    completed: [
      { ...job, kind: 'assignment', id: 22, status: 'PAGA', status_label: 'Paga', can_withdraw: false, title: 'Turno pago' },
    ],
    closed: [
      { ...job, id: 12, status: 'RECUSADA', status_label: 'Recusada', can_withdraw: false, title: 'Vaga recusada' },
    ],
  }

  it('agrupa candidaturas e alocações com empresa, data e valor líquido', async () => {
    mockApi({ ...session, 'GET /api/workers/me/jobs/': () => ({ body: { groups } }) })
    renderAt('/meus-trabalhos')

    for (const title of [
      'Aguardando',
      'Aprovadas / Próximos turnos',
      'Em andamento',
      'Concluídas',
      'Encerradas',
    ]) {
      expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
    }
    const waiting = screen.getByRole('region', { name: 'Aguardando' })
    expect(within(waiting).getByText('Mercado Bom')).toBeInTheDocument()
    expect(within(waiting).getByText(/R\$\s97,00/)).toBeInTheDocument()
    expect(within(waiting).getByText('Pendente')).toBeInTheDocument()
    expect(screen.getByText('Turno confirmado')).toBeInTheDocument()
    expect(screen.getByText('Turno pago')).toBeInTheDocument()
    expect(screen.getByText('Vaga recusada')).toBeInTheDocument()
    expect(screen.getByText('Nenhum turno em andamento.')).toBeInTheDocument()
  })

  it('desiste de uma candidatura pendente e recarrega a lista', async () => {
    let withdrawn = false
    const fetchMock = mockApi({
      ...session,
      'GET /api/workers/me/jobs/': () => ({
        body: {
          groups: withdrawn
            ? {
                ...groups,
                waiting: [],
                closed: [
                  { ...job, status: 'DESISTENCIA', status_label: 'Desistência', can_withdraw: false },
                ],
              }
            : groups,
        },
      }),
      'POST /api/applications/11/withdraw/': () => {
        withdrawn = true
        return { body: { ...job, status: 'DESISTENCIA', can_withdraw: false } }
      },
    })
    renderAt('/meus-trabalhos')

    await userEvent.click(await screen.findByRole('button', { name: 'Desistir' }))

    expect(await screen.findByText('Desistência')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Desistir' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/applications/11/withdraw/',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
