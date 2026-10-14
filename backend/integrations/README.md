# Integrações externas

Toda integração com serviço externo (PSP, consulta de CNPJ, SMS, verificação de documento,
geolocalização, notificações) fica aqui, no padrão **adaptador**:

- **Interface:** uma classe abstrata (ou `Protocol`) que descreve o que o domínio precisa,
  sem detalhes do fornecedor. Ex.: `integrations/cnpj/base.py`.
- **Implementação real:** fala com o fornecedor. Ex.: `integrations/cnpj/receitaws.py`.
- **Implementação fake:** determinística, sem rede, usada em desenvolvimento e nos testes.
  Ex.: `integrations/cnpj/fake.py`.

O código de domínio depende só da interface; a implementação é escolhida por configuração.
**Os testes nunca chamam serviços externos** — usam a implementação fake.

Integrações existentes: `payments/` (PSP: interface + fake, escolhida por `PAYMENT_GATEWAY`) e
`geo/` (distância de Haversine). As demais entram junto das histórias que as usam.
