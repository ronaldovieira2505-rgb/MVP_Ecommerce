import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AuthProvider from '../AuthProvider'
import AppRoutes from '../routes'

const card = {
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
  urgent: true,
  distance_km: null,
}

const calls: string[] = []

function mockApi(detail: Record<string, unknown> = {}) {
  calls.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn((path: string) => {
      calls.push(path)
      let status = 200
      let body: unknown = { results: [card] }
      if (path === '/api/auth/me/') status = 403
      else if (path === '/api/vacancies/7/')
        body = {
          ...card,
          description: 'Descarregar caminhão',
          street: 'Praça da Sé',
          number: '1',
          complement: '',
          zip_code: '',
          latitude: '-23.550520',
          longitude: '-46.633308',
          can_apply: false,
          apply_blocker: 'Entre como prestador para se candidatar.',
          ...detail,
        }
      return Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) })
    }),
  )
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('Buscar vagas (US12)', () => {
  it('mostra o valor líquido em destaque, o bruto, a taxa e os selos', async () => {
    mockApi()
    renderAt('/vagas')
    expect(await screen.findByText('Você recebe R$ 97,00')).toBeInTheDocument()
    expect(screen.getByText(/Valor do turno R\$\s100,00 · taxa 3%/)).toBeInTheDocument()
    expect(screen.getByText('Pagamento garantido')).toBeInTheDocument()
    expect(screen.getByText('Urgente')).toBeInTheDocument()
    expect(screen.getByText(/2 vagas restantes/)).toBeInTheDocument()
  })

  it('combina busca e filtros na consulta e limpa com um clique', async () => {
    mockApi()
    renderAt('/vagas')
    await screen.findByText('Você recebe R$ 97,00')
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Buscar'), 'carga')
    await user.selectOptions(screen.getByLabelText('Categoria'), 'LIMPEZA')
    await user.type(screen.getByLabelText('Receber no mínimo (R$)'), '90')
    await user.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(calls).toContain('/api/vacancies/?q=carga&category=LIMPEZA&min_pay=9000')
    await user.click(screen.getByRole('button', { name: 'Limpar filtros' }))
    expect(screen.getByLabelText('Buscar')).toHaveValue('')
    expect(calls.at(-1)).toBe('/api/vacancies/')
  })

  it('detalhe mostra taxa, valor líquido e o que falta para se candidatar', async () => {
    mockApi()
    renderAt('/vagas/7')
    expect(await screen.findByRole('heading', { name: 'Carga e descarga' })).toBeInTheDocument()
    expect(screen.getByText('Descarregar caminhão')).toBeInTheDocument()
    expect(screen.getByText('R$ 97,00')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver no mapa' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quero esta vaga' })).toBeDisabled()
    expect(screen.getByText('Entre como prestador para se candidatar.')).toBeInTheDocument()
  })
})
