import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

type Handler = (init?: RequestInit) => { status?: number; body?: unknown }

function mockApi(handlers: Record<string, Handler>) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? 'GET'} ${path}`
      calls.push(key)
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
  return calls
}

const pending = {
  id: 21,
  vacancy_id: 7,
  vacancy_title: 'Carga e descarga',
  worker_first_name: 'Maria',
  starts_at: '2026-11-03T12:00:00Z',
  ends_at: '2026-11-03T16:00:00Z',
  check_in_at: '2026-11-03T12:05:00Z',
  check_out_at: '2026-11-03T16:00:00Z',
  check_out_auto: false,
  check_in_distance_m: 78,
  gross_cents: 10000,
  auto_approve_at: '2026-11-04T16:00:00Z',
  auto_approve_in_seconds: 23 * 3600 + 10 * 60,
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({
    body: { id: 1, name: 'Acme', email: 'a@acme.com', role: 'COMPANY', verification_status: 'APROVADA' },
  }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
}

const PENDING = 'GET /api/company/assignments/pending/'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/empresa/confirmar-presenca']}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Confirmar presença', () => {
  it('mostra previsto × registrado, distância e prazo da aprovação automática', async () => {
    mockApi({ ...session, [PENDING]: () => ({ body: { results: [pending] } }) })
    renderPage()

    expect(await screen.findByText('Maria')).toBeInTheDocument()
    expect(screen.getByText('Previsto')).toBeInTheDocument()
    expect(screen.getByText('Registrado')).toBeInTheDocument()
    expect(screen.getByText('78 m')).toBeInTheDocument()
    expect(screen.getByText('Aprovação automática em 23 h 10 min')).toBeInTheDocument()
    expect(screen.queryByText('Check-out automático')).not.toBeInTheDocument()
  })

  it('indica o check-out automático', async () => {
    mockApi({
      ...session,
      [PENDING]: () => ({ body: { results: [{ ...pending, check_out_auto: true }] } }),
    })
    renderPage()

    expect(await screen.findByText('Check-out automático')).toBeInTheDocument()
  })

  it('confirma a presença, libera o pagamento e remove o item da lista', async () => {
    let approved = false
    const calls = mockApi({
      ...session,
      [PENDING]: () => ({ body: { results: approved ? [] : [pending] } }),
      'POST /api/assignments/21/approve/': () => {
        approved = true
        return { body: { id: 21, status: 'PAGA', payment_pending: false } }
      },
    })
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Confirmar presença e liberar pagamento' }),
    )

    expect(await screen.findByText('Presença confirmada e pagamento liberado.')).toBeInTheDocument()
    expect(screen.getByText('Nenhuma presença aguardando confirmação.')).toBeInTheDocument()
    expect(calls).toContain('POST /api/assignments/21/approve/')
  })

  it('avisa quando o PSP falhou e o pagamento fica para o próximo processamento', async () => {
    let approved = false
    mockApi({
      ...session,
      [PENDING]: () => ({ body: { results: approved ? [] : [pending] } }),
      'POST /api/assignments/21/approve/': () => {
        approved = true
        return { body: { id: 21, status: 'APROVADA', payment_pending: true } }
      },
    })
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Confirmar presença e liberar pagamento' }),
    )

    expect(await screen.findByText(/próximo processamento/)).toBeInTheDocument()
  })

  it('mostra o erro da API ao aprovar', async () => {
    mockApi({
      ...session,
      [PENDING]: () => ({ body: { results: [pending] } }),
      'POST /api/assignments/21/approve/': () => ({
        status: 404,
        body: { detail: 'Alocação não encontrada.' },
      }),
    })
    renderPage()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Confirmar presença e liberar pagamento' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Alocação não encontrada.')
  })
})
