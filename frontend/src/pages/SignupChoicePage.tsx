import { Link } from 'react-router-dom'
import { Card } from '../components/ui'

export default function SignupChoicePage() {
  return (
    <Card>
      <h1>Criar conta</h1>
      <p>Como você quer usar o Conecta Já?</p>
      <p>
        <Link to="/cadastro/empresa" className="btn btn-primary btn-block">
          Sou Empresa
        </Link>
      </p>
      <p>
        <Link to="/cadastro/prestador" className="btn btn-primary btn-block">
          Sou Prestador
        </Link>
      </p>
      <p>
        <Link to="/login">Já tenho conta</Link>
      </p>
    </Card>
  )
}
