import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, type WorkerProfile } from '../api'
import { Alert, Button, Card, Field } from '../components/ui'

const DOCUMENT_TYPES = ['jpg', 'jpeg', 'png', 'pdf']
const SELFIE_TYPES = ['jpg', 'jpeg', 'png']

function extensionOf(file: File): string {
  return file.name.split('.').pop()?.toLowerCase() ?? ''
}

/** Envio de documento (frente e verso) e selfie. O tamanho máximo é validado pelo servidor. */
export default function WorkerDocumentsPage() {
  const [front, setFront] = useState<File | null>(null)
  const [back, setBack] = useState<File | null>(null)
  const [selfie, setSelfie] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (!front || !back || !selfie) {
      setError('Envie documento (frente e verso) e selfie.')
      return
    }
    if (![front, back].every((file) => DOCUMENT_TYPES.includes(extensionOf(file)))) {
      setError('Tipo de arquivo inválido. Envie JPG, PNG ou PDF.')
      return
    }
    if (!SELFIE_TYPES.includes(extensionOf(selfie))) {
      setError('Tipo de arquivo inválido. A selfie deve ser JPG ou PNG.')
      return
    }
    const form = new FormData()
    form.append('document_front', front)
    form.append('document_back', back)
    form.append('selfie', selfie)
    setSubmitting(true)
    try {
      await api<WorkerProfile>('/api/workers/me/documents/', { method: 'POST', form })
      setSent(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível enviar os arquivos.')
    } finally {
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <Card>
        <h1>Documentos e selfie</h1>
        <Alert tone="success">Arquivos enviados. Seu cadastro está em análise.</Alert>
        <Link to="/prestador/perfil">Voltar ao perfil</Link>
      </Card>
    )
  }

  return (
    <Card>
      <h1>Documentos e selfie</h1>
      <p>Envie a frente e o verso do documento com foto (JPG, PNG ou PDF) e uma selfie.</p>
      {error && <Alert tone="error">{error}</Alert>}
      <form onSubmit={onSubmit} noValidate>
        <Field
          label="Documento (frente)"
          type="file"
          accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf"
          onChange={(e) => setFront(e.target.files?.[0] ?? null)}
        />
        <Field
          label="Documento (verso)"
          type="file"
          accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf"
          onChange={(e) => setBack(e.target.files?.[0] ?? null)}
        />
        <Field
          label="Selfie"
          type="file"
          accept="image/jpeg,image/png"
          capture="user"
          onChange={(e) => setSelfie(e.target.files?.[0] ?? null)}
        />
        <Button type="submit" block disabled={submitting}>
          Enviar
        </Button>
      </form>
    </Card>
  )
}
