import { Link } from 'react-router-dom'
import { Card } from '../components/ui'

type PlaceholderProps = {
  title: string
  issue: string
  /** O que a pessoa pode fazer enquanto esta tela não existe. */
  next?: { to: string; label: string; hint: string }
}

/** Tela ainda não implementada; diz o que falta e para onde ir enquanto isso. */
export default function Placeholder({ title, issue, next }: PlaceholderProps) {
  return (
    <Card>
      <h1>{title}</h1>
      <div className="vazio">
        <p>Esta tela será entregue em {issue}.</p>
        {next && (
          <>
            <p>{next.hint}</p>
            <Link to={next.to} className="btn btn-secondary">
              {next.label}
            </Link>
          </>
        )}
      </div>
    </Card>
  )
}
