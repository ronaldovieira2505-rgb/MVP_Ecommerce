import { Link } from 'react-router-dom'
import { Card } from '../components/ui'

export default function SignupChoicePage() {
  return (
    <Card>
      <h1>Criar conta</h1>
      <p>
        Os dois cadastros passam por uma verificação antes de liberar o acesso. Escolha o que você
        vai fazer no Conecta Já.
      </p>
      <div className="escolhas">
        <div className="escolha">
          <h2>Contratar</h2>
          <p>
            Publique turnos, pague em custódia e confirme a presença. Pedimos o CNPJ, os dados
            fiscais e um responsável.
          </p>
          <Link to="/cadastro/empresa" className="btn btn-primary">
            Sou Empresa
          </Link>
        </div>
        <div className="escolha">
          <h2>Trabalhar</h2>
          <p>
            Encontre turnos perto de você e receba por PIX depois do check-out. Pedimos o CPF, um
            documento com foto e uma selfie.
          </p>
          <Link to="/cadastro/prestador" className="btn btn-primary">
            Sou Prestador
          </Link>
        </div>
      </div>
      <p className="sub">
        <Link to="/login">Já tenho conta</Link>
      </p>
    </Card>
  )
}
