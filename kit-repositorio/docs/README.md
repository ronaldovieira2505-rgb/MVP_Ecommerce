# Documentação de domínio

O Claude lê esta pasta antes de implementar qualquer US. Quanto mais fiel for ela ao que o grupo decidiu, menos o código foge das regras.

Arquivos esperados (adicione conforme ficarem prontos, por exemplo a partir do relatório N1):

- `entidades.md`: modelo de entidades e relacionamentos.
- `maquina-de-estados.md`: estados e transições de Vaga, Turno, Candidatura e Pagamento (inclusive timeouts).
- `regras-de-negocio.md`: tabela de regras (prazos, taxas, penalidades) com o valor padrão de cada uma.

Se um destes arquivos não existir ou não cobrir um caso, o Claude deve perguntar na issue em vez de inventar.
