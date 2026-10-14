# Escopo do MVP — Conecta Já

> Objetivo: executar o **ciclo completo de um turno** de ponta a ponta. A empresa publica e paga em custódia, o prestador encontra a vaga e se candidata, a empresa aprova, o prestador faz check-in validado por localização e check-out, a empresa confirma a presença (ou silencia) e o pagamento é liberado na carteira, com tudo registrado na trilha de auditoria.

## Fluxos obrigatórios (definidos com o professor)

| Prestador | Contratante |
|---|---|
| Login | Login |
| Triagem (verificação do cadastro) | Triagem (verificação do cadastro) |
| Procura de trabalho | Adicionar ou remover serviços no catálogo (vagas) |
| Check-in e check-out | Confirmar presença da mão de obra |
| Carteira | |

## Ordem de execução (uma de cada vez, nesta ordem)

| # | Issue | Entrega | Fecha também |
|---|---|---|---|
| 1 | BASE-01 | Modelos, máquinas de estado, auditoria, livro-razão, `processar_prazos` | — |
| 2 | BASE-02 | Login, papéis, layout e identidade visual | — |
| 3 | US79 | Parâmetros editáveis pelo admin (permite a demo com prazos curtos) | — |
| 4 | US01 | Cadastro da empresa (CNPJ via BrasilAPI, dados fiscais) | — |
| 5 | US04 | Cadastro do prestador | — |
| 6 | US05 | Documentos, selfie e chave PIX | US06 |
| 7 | US73 | Fila de verificação do admin (triagem) | — |
| 8 | US20 | Publicar vaga com N pessoas e pagar em custódia | US21 |
| 9 | US24 | Editar ou remover vaga sem aprovados | — |
| 10 | US12 | Busca, filtros, proximidade e valor líquido | US13, US14, US17 |
| 11 | US37 | Candidatura e "Meus trabalhos" | US38 |
| 12 | US42 | Aprovar ou recusar candidatos | — |
| 13 | US50 | Check-in por localização e check-out | US54 |
| 14 | US55 | Falta, reabertura e suspensão automática | — |
| 15 | US56 | Confirmar presença e aprovação automática | US59 |
| 16 | US60 | Carteira | — |
| 17 | BASE-03 | Dados de demonstração e roteiro | — |
| extra | US57, US75 | Contestação e histórico do turno, se sobrar tempo | — |

Das 20 US marcadas como MVP no relatório N1, ficaram para depois US23, US40, US45 (reunião e avaliação) e US57 e US75 (viraram extras). Entraram cadastro, login e triagem (US01, US04, US05, US06), remoção de anúncio (US24), busca por texto (US12) e valor líquido (US17), exigidos pelo fluxo acima.

## Roteiro de demonstração (12 passos)

1. Admin ativa os **prazos curtos** de demonstração (US79).
2. Empresa se cadastra pelo CNPJ, com dados preenchidos pela BrasilAPI (US01).
3. Prestador se cadastra, envia documento e selfie e cadastra a chave PIX (US04, US05).
4. Admin aprova os dois na fila de verificação (US73).
5. Empresa publica uma vaga de R$ 100,00 para 2 pessoas e paga em custódia (US20).
6. Prestador busca e filtra vagas, vê a mais próxima com "Você recebe R$ 97,00" e o selo "Pagamento garantido" (US12).
7. Dois prestadores se candidatam e acompanham o status (US37).
8. Empresa aprova os dois (US42).
9. No horário, o prestador A faz check-in dentro de 150 m (US50).
10. O prestador B não comparece: falta registrada, posição reaberta e empresa avisada (US55).
11. Prestador A faz check-out e a empresa confirma a presença (ou espera a aprovação automática) (US56).
12. A carteira do prestador A mostra R$ 97,00 liberados, e o admin vê a trilha de auditoria e o estorno da posição não usada (US60).
