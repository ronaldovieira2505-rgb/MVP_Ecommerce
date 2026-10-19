import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, brl, formatDateTime, formatShift, type Wallet } from '../api'
import { Alert, Badge, Card } from '../components/ui'

/** Carteira do prestador (US60): a receber, liberado e taxas retidas. */
export default function WorkerWalletPage() {
  const [wallet, setWallet] = useState<Wallet | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<Wallet>('/api/workers/me/wallet/')
      .then(setWallet)
      .catch((err: Error) => setError(err.message))
  }, [])

  if (error) return <Alert tone="error">{error}</Alert>
  if (!wallet) return <p role="status">Carregando...</p>

  const { totals } = wallet

  return (
    <>
      <h1>Carteira</h1>
      <dl className="linhas" aria-label="Totais">
        <div>
          <dt>A receber</dt>
          <dd data-testid="total-receivable">{brl(totals.receivable_cents)}</dd>
        </div>
        <div>
          <dt>Liberado</dt>
          <dd data-testid="total-released">{brl(totals.released_cents)}</dd>
        </div>
        <div>
          <dt>Taxas retidas ({wallet.fee_percent}%)</dt>
          <dd data-testid="total-fees">{brl(totals.fees_cents)}</dd>
        </div>
      </dl>

      <section aria-labelledby="carteira-a-receber">
        <h2 id="carteira-a-receber">A receber</h2>
        {wallet.receivable.length === 0 && <p>Nenhum valor a receber por enquanto.</p>}
        {wallet.receivable.map((item) => (
          <Card key={item.assignment_id}>
            <h3>
              <Link to={`/vagas/${item.vacancy_id}`}>{item.title}</Link>
            </h3>
            <p className="marcadores">
              <Badge tone="info">{item.status_label}</Badge>
            </p>
            <dl className="linhas">
              <div>
                <dt>Empresa</dt>
                <dd>{item.company_name}</dd>
              </div>
              <div>
                <dt>Turno</dt>
                <dd>{formatShift(item.starts_at, item.ends_at)}</dd>
              </div>
              <div>
                <dt>Valor líquido</dt>
                <dd>{brl(item.net_cents)}</dd>
              </div>
              <div>
                <dt>Previsão de liberação</dt>
                <dd>
                  {item.expected_release_at
                    ? formatDateTime(item.expected_release_at)
                    : item.release_note}
                </dd>
              </div>
            </dl>
          </Card>
        ))}
      </section>

      <section aria-labelledby="carteira-liberado">
        <h2 id="carteira-liberado">Liberado</h2>
        {wallet.released.length === 0 && <p>Nenhum valor liberado ainda.</p>}
        {wallet.released.map((item) => (
          <Card key={item.assignment_id}>
            <h3>
              <Link to={`/vagas/${item.vacancy_id}`}>{item.title}</Link>
            </h3>
            <dl className="linhas">
              <div>
                <dt>Liberado em</dt>
                <dd>{formatDateTime(item.released_at)}</dd>
              </div>
              <div>
                <dt>Valor bruto</dt>
                <dd>{brl(item.gross_cents)}</dd>
              </div>
              <div>
                <dt>Taxa</dt>
                <dd>{brl(item.fee_cents)}</dd>
              </div>
              <div>
                <dt>Valor líquido</dt>
                <dd>{brl(item.net_cents)}</dd>
              </div>
            </dl>
            {item.pix_destination && <p>Enviado para PIX {item.pix_destination} (simulado)</p>}
          </Card>
        ))}
      </section>
    </>
  )
}
