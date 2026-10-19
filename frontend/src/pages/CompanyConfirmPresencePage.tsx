import { Card } from '../components/ui'
import PendingAssignmentsSection from './PendingAssignments'

/** `/empresa/confirmar-presenca`: horas de todas as vagas aguardando conferência (US56). */
export default function CompanyConfirmPresencePage() {
  return (
    <Card>
      <h1>Confirmar presença</h1>
      <p>
        Confira as horas registradas antes de liberar o pagamento. Sem manifestação dentro do
        prazo, as horas são aprovadas automaticamente.
      </p>
      <PendingAssignmentsSection />
    </Card>
  )
}
