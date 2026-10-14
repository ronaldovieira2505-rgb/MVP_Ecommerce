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

const worker = {
  id: 1,
  name: 'João da Silva',
  email: 'joao@example.com',
  role: 'WORKER',
  verification_status: 'PENDENTE_DOCUMENTOS',
}

const baseProfile = {
  id: 1,
  full_name: 'João da Silva',
  cpf: '***.456.789-**',
  phone: '****8888',
  verification_status: 'PENDENTE_DOCUMENTOS',
  pix_key_type: '',
  pix_key: '',
  verification_message: '',
  profile_steps: [
    { key: 'documentos', label: 'Documentos e selfie', done: false, status: 'PENDENTE_DOCUMENTOS' },
    { key: 'pix', label: 'Chave PIX', done: false },
  ],
}

const session: Record<string, Handler> = {
  'GET /api/auth/me/': () => ({ body: worker }),
  'GET /api/notifications/': () => ({ body: { unread_count: 0, results: [] } }),
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

function pngFile(name: string) {
  return new File([new Uint8Array([137, 80, 78, 71])], name, { type: 'image/png' })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Documentos e selfie', () => {
  it('envia frente, verso e selfie e confirma a análise', async () => {
    let sent: FormData | undefined
    mockApi({
      ...session,
      'POST /api/workers/me/documents/': (init) => {
        sent = init?.body as FormData
        return { body: { ...baseProfile, verification_status: 'EM_ANALISE' } }
      },
    })
    renderAt('/perfil/documentos')

    await userEvent.upload(await screen.findByLabelText('Documento (frente)'), pngFile('f.png'))
    await userEvent.upload(screen.getByLabelText('Documento (verso)'), pngFile('v.png'))
    await userEvent.upload(screen.getByLabelText('Selfie'), pngFile('s.png'))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Seu cadastro está em análise')
    expect(sent?.get('document_front')).toBeInstanceOf(File)
    expect(sent?.get('document_back')).toBeInstanceOf(File)
    expect(sent?.get('selfie')).toBeInstanceOf(File)
  })

  it('mostra erro de tipo inválido e não chama a API', async () => {
    const fetchMock = mockApi(session)
    renderAt('/perfil/documentos')

    await userEvent.upload(await screen.findByLabelText('Documento (frente)'), pngFile('f.gif'), {
      applyAccept: false,
    })
    await userEvent.upload(screen.getByLabelText('Documento (verso)'), pngFile('v.png'))
    await userEvent.upload(screen.getByLabelText('Selfie'), pngFile('s.png'))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Tipo de arquivo inválido. Envie JPG, PNG ou PDF.',
    )
    expect(fetchMock).toHaveBeenCalledTimes(2) // /api/auth/me/ e notificações
  })

  it('mostra a mensagem do servidor para arquivo grande demais', async () => {
    mockApi({
      ...session,
      'POST /api/workers/me/documents/': () => ({
        status: 400,
        body: { detail: 'O arquivo excede o tamanho máximo de 5 MB.' },
      }),
    })
    renderAt('/perfil/documentos')

    await userEvent.upload(await screen.findByLabelText('Documento (frente)'), pngFile('f.png'))
    await userEvent.upload(screen.getByLabelText('Documento (verso)'), pngFile('v.png'))
    await userEvent.upload(screen.getByLabelText('Selfie'), pngFile('s.png'))
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('excede o tamanho máximo de 5 MB')
  })
})

describe('Chave PIX', () => {
  it('salva a chave e mostra apenas a versão mascarada', async () => {
    let sent: unknown
    mockApi({
      ...session,
      'GET /api/workers/me/': () => ({ body: baseProfile }),
      'PUT /api/workers/me/pix/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { body: { ...baseProfile, pix_key_type: 'CPF', pix_key: '***.456.789-**' } }
      },
    })
    renderAt('/perfil/pix')

    await userEvent.type(await screen.findByLabelText('Chave PIX'), '12345678909')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar chave' }))

    expect(await screen.findByText(/Chave atual: \*\*\*\.456\.789-\*\*/)).toBeInTheDocument()
    expect(sent).toEqual({ key_type: 'CPF', key: '12345678909' })
    expect(screen.queryByText('12345678909')).not.toBeInTheDocument()
  })

  it('mostra o erro de titularidade do CPF', async () => {
    mockApi({
      ...session,
      'GET /api/workers/me/': () => ({ body: baseProfile }),
      'PUT /api/workers/me/pix/': () => ({
        status: 400,
        body: { detail: 'A chave PIX do tipo CPF precisa ser o seu próprio CPF' },
      }),
    })
    renderAt('/perfil/pix')

    await userEvent.type(await screen.findByLabelText('Chave PIX'), '52998224725')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar chave' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A chave PIX do tipo CPF precisa ser o seu próprio CPF',
    )
  })

  it('pede a senha atual para trocar uma chave existente', async () => {
    let sent: unknown
    mockApi({
      ...session,
      'GET /api/workers/me/': () => ({
        body: { ...baseProfile, pix_key_type: 'EMAIL', pix_key: 'j***@example.com' },
      }),
      'PUT /api/workers/me/pix/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { body: { ...baseProfile, pix_key_type: 'TELEFONE', pix_key: '****8888' } }
      },
    })
    renderAt('/perfil/pix')

    await userEvent.selectOptions(await screen.findByLabelText('Tipo da chave'), 'TELEFONE')
    await userEvent.type(screen.getByLabelText('Chave PIX'), '11999998888')
    await userEvent.type(screen.getByLabelText('Senha atual'), 'senha-forte-123')
    await userEvent.click(screen.getByRole('button', { name: 'Salvar chave' }))

    expect(await screen.findByText(/Chave atual: \*\*\*\*8888/)).toBeInTheDocument()
    expect(sent).toEqual({
      key_type: 'TELEFONE',
      key: '11999998888',
      current_password: 'senha-forte-123',
    })
  })
})

describe('Painel "Complete seu perfil"', () => {
  it('mostra as duas etapas concluídas e "Aguardando verificação"', async () => {
    mockApi({
      ...session,
      'GET /api/workers/me/': () => ({
        body: {
          ...baseProfile,
          verification_status: 'EM_ANALISE',
          verification_message: 'Aguardando verificação',
          profile_steps: [
            { key: 'documentos', label: 'Documentos e selfie', done: true, status: 'EM_ANALISE' },
            { key: 'pix', label: 'Chave PIX', done: true },
          ],
        },
      }),
    })
    renderAt('/prestador/perfil')

    const steps = await screen.findByRole('list', { name: 'Etapas do perfil' })
    expect(steps).toHaveTextContent('Em análise')
    expect(steps).toHaveTextContent('Concluída')
    expect(screen.getByText('Aguardando verificação')).toBeInTheDocument()
  })
})
