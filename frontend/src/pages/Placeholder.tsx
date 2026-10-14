import { Alert, Card } from '../components/ui'

/** Tela ainda não implementada; será entregue pela issue indicada. */
export default function Placeholder({ title, issue }: { title: string; issue: string }) {
  return (
    <Card>
      <h1>{title}</h1>
      <Alert tone="info">Esta tela será entregue em {issue}.</Alert>
    </Card>
  )
}
