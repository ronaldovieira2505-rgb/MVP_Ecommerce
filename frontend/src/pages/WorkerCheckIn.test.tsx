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

const base = {
  kind: 'assignment',
  id: 31,
  vacancy_id: 7,
  title: 'Carga e descarga',
  company_name: 'Mercado Bom',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  gross_cents: 10000,
  net_cents: 9700,
  status: 'CONFIRMADA',
  status_label: 'Confirmada',
  can_withdraw: false,
  can_check_in: true,
  can_check_out: false,
  check_in_opens_at: '2026-11-03T11:30:00Z',
  check_in_closes_at: '2026-11-03T12:30:00Z',
  check_in_at: null,
  check_out_at: null,
  check_out_auto: false,
}

type Groups = Record<string, unknown[]>

const empty: Groups = { waiting: [], upcoming: [], in_progress: [], completed: [], closed: [] }

function jobsWith(groups: Groups) {
  return () => ({ body: { groups: { ...empty, ...groups } } })
}

function renderJobs() {
  render(
    <MemoryRouter initialEntries={['/meus-trabalhos']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

function stubGeolocation(result: 'ok' | 'denied') {
  const getCurrentPosition = vi.fn((success: PositionCallback, failure: PositionErrorCallback) => {
    if (result === 'ok') {
      success({
        coords: { latitude: -23.55052, longitude: -46.633308, accuracy: 12 },
      } as GeolocationPosition)
    } else {
      failure({ code: 1, message: 'denied' } as GeolocationPositionError)
    }
  })
  vi.stubGlobal('navigator', { ...navigator, geolocation: { getCurrentPosition } })
  return getCurrentPosition
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Check-in e check-out (US50/US54)', () => {
  it('mostra "Cheguei" dentro da janela e registra o check-in com as coordenadas', async () => {
    stubGeolocation('ok')
    let done = false
    const running = {
      ...base,
      status: 'EM_EXECUCAO',
      status_label: 'Em execução',
      can_check_in: false,
      can_check_out: true,
      check_in_at: '2026-11-03T12:05:00Z',
    }
    const fetchMock = mockApi({
      ...session,
      'GET /api/workers/me/jobs/': () =>
        done ? jobsWith({ in_progress: [running] })() : jobsWith({ upcoming: [base] })(),
      'POST /api/assignments/31/check-in/': () => {
        done = true
        return { body: running }
      },
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Cheguei' }))

    expect((await screen.findAllByText(/Check-in feito às 09:05/)).length).toBeGreaterThan(0)
    const call = fetchMock.mock.calls.find(([path]) => path === '/api/assignments/31/check-in/')
    expect(JSON.parse((call?.[1] as RequestInit).body as string)).toEqual({
      lat: -23.55052,
      lng: -46.633308,
      accuracy: 12,
    })
    expect(screen.queryByRole('button', { name: 'Cheguei' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Encerrar turno' })).toBeInTheDocument()
  })

  it('mostra a distância devolvida pelo servidor e não muda nada', async () => {
    stubGeolocation('ok')
    mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobsWith({ upcoming: [base] }),
      'POST /api/assignments/31/check-in/': () => ({
        status: 409,
        body: { detail: 'Você está a 222 m do local. Aproxime-se para registrar a chegada.' },
      }),
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Cheguei' }))

    expect(
      await screen.findByText('Você está a 222 m do local. Aproxime-se para registrar a chegada.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cheguei' })).toBeInTheDocument()
  })

  it('explica como ativar a localização quando a permissão é negada, sem chamar a API', async () => {
    stubGeolocation('denied')
    const fetchMock = mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobsWith({ upcoming: [base] }),
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Cheguei' }))

    expect(await screen.findByText(/permissão de localização está bloqueada/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('check-in'))).toBe(false)
  })

  it('fora da janela não mostra "Cheguei" e explica quando abre', async () => {
    const future = {
      ...base,
      can_check_in: false,
      check_in_opens_at: '2099-11-03T11:30:00Z',
      check_in_closes_at: '2099-11-03T12:30:00Z',
    }
    mockApi({ ...session, 'GET /api/workers/me/jobs/': jobsWith({ upcoming: [future] }) })
    renderJobs()

    expect(await screen.findByText('O check-in abre às 08:30.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cheguei' })).not.toBeInTheDocument()
  })

  it('encerra o turno depois de confirmar e mostra entrada e saída', async () => {
    let done = false
    const running = {
      ...base,
      status: 'EM_EXECUCAO',
      status_label: 'Em execução',
      can_check_in: false,
      can_check_out: true,
      check_in_at: '2026-11-03T12:05:00Z',
    }
    const finished = {
      ...running,
      status: 'AGUARDANDO_VALIDACAO',
      status_label: 'Aguardando validação',
      can_check_out: false,
      check_out_at: '2026-11-03T16:02:00Z',
    }
    const fetchMock = mockApi({
      ...session,
      'GET /api/workers/me/jobs/': () =>
        done ? jobsWith({ in_progress: [finished] })() : jobsWith({ in_progress: [running] })(),
      'POST /api/assignments/31/check-out/': () => {
        done = true
        return { body: finished }
      },
    })
    renderJobs()

    await userEvent.click(await screen.findByRole('button', { name: 'Encerrar turno' }))
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('check-out'))).toBe(false)
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar encerramento' }))

    expect(await screen.findByText(/Saída às 13:02/)).toBeInTheDocument()
    expect(screen.getByText(/Check-in feito às 09:05/)).toBeInTheDocument()
    expect(screen.getByText('Aguardando validação')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Encerrar turno' })).not.toBeInTheDocument()
  })

  it('indica a saída registrada automaticamente', async () => {
    mockApi({
      ...session,
      'GET /api/workers/me/jobs/': jobsWith({
        in_progress: [
          {
            ...base,
            status: 'AGUARDANDO_VALIDACAO',
            status_label: 'Aguardando validação',
            can_check_in: false,
            check_in_at: '2026-11-03T12:05:00Z',
            check_out_at: '2026-11-03T16:00:00Z',
            check_out_auto: true,
          },
        ],
      }),
    })
    renderJobs()

    expect(
      await screen.findByText(/Saída às 13:00 \(registrada automaticamente\)/),
    ).toBeInTheDocument()
  })
})
