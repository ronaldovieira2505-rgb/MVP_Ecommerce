# Máquinas de estado — Conecta Já

> Fonte oficial dos estados e transições. **Só as transições listadas aqui são válidas**; qualquer outra deve ser rejeitada com erro explícito.
> Prazos (em itálico) vêm de `PlatformParameters` — ver `docs/regras-de-negocio.md`. Nunca fixos no código.

## Regras de implementação (valem para todas as máquinas)

1. **Tabela declarativa:** cada máquina tem uma tabela `(estado_origem, evento) → estado_destino` em um único módulo de domínio (ex.: `apps/<app>/state_machine.py`). Views e serializers **nunca** alteram `status` diretamente; chamam o serviço de transição.
2. **Atômico e auditado:** a transição valida o estado de origem com `select_for_update`, executa os efeitos colaterais (ledger, notificações, criação de alocação) e grava um `StateTransition` **na mesma transação**.
3. **Ator:** cada transição registra quem a causou: usuário (empresa, prestador, admin) ou `SISTEMA` (prazo).
4. **Nada fica parado:** todo estado não final tem uma ação humana **e/ou** um prazo automático que o faz avançar. Os prazos são processados pelo comando idempotente `python manage.py processar_prazos` (aceita `--loop <segundos>` para rodar continuamente em desenvolvimento) e por um botão "Processar prazos agora" no painel do admin.
5. **Idempotência:** rodar o processamento de prazos duas vezes não pode gerar transição nem lançamento financeiro duplicado.

---

## 1. Vaga (`Vacancy`)

| De | Evento / ator | Para | Condições e efeitos |
|---|---|---|---|
| — | Empresa cria a vaga | `AGUARDANDO_PAGAMENTO` | Empresa `APROVADA`; `starts_at` ≥ agora + *antecedência mínima (12 h)*; `ends_at` > `starts_at`. Cria `Custody` `PENDENTE` |
| `AGUARDANDO_PAGAMENTO` | Empresa paga (PSP simulado) | `PUBLICADA` | Revalida a antecedência mínima. Custódia → `RETIDA`, lançamento `RETENCAO` |
| `AGUARDANDO_PAGAMENTO` | Empresa desiste | `CANCELADA` | Custódia → `CANCELADA` (nada foi cobrado) |
| `AGUARDANDO_PAGAMENTO` | SISTEMA: *prazo para pagar (24 h)* expirou ou a antecedência mínima deixou de ser possível | `CANCELADA` | Idem |
| `PUBLICADA` | Empresa remove a vaga (US24) | `CANCELADA` | Só se **nenhuma** candidatura foi aprovada. Estorno total (`ESTORNO_CONTRATANTE`); candidaturas pendentes → `EXPIRADA` |
| `PUBLICADA` | SISTEMA: agora ≥ `starts_at` − *encerramento de candidaturas (2 h)* | `CANDIDATURAS_ENCERRADAS` | Novas candidaturas bloqueadas; a empresa ainda pode aprovar as pendentes até `starts_at` |
| `CANDIDATURAS_ENCERRADAS` | SISTEMA: agora ≥ `starts_at` e há ≥ 1 alocação `CONFIRMADA` | `EM_ANDAMENTO` | — |
| `CANDIDATURAS_ENCERRADAS` | SISTEMA: agora ≥ `starts_at` e nenhuma alocação | `CANCELADA` | Estorno total; empresa notificada ("ninguém foi aprovado") |
| `EM_ANDAMENTO` | SISTEMA: todas as alocações em estado final | `FINALIZADA` | Estorna as posições não utilizadas; custódia → `ENCERRADA`; candidaturas pendentes → `EXPIRADA` |

**Reabertura por falta:** quando uma alocação vira `FALTA`, a vaga é marcada como **reaberta** (`reopened = true`) enquanto `agora < ends_at`. Nesse período ela volta à busca com o selo "Urgente", aceita novas candidaturas e a empresa pode aprovar quem estiver pendente para a posição liberada. Isso não muda o `status` da vaga.

Estados finais: `FINALIZADA`, `CANCELADA`.

---

## 2. Candidatura (`Application`)

| De | Evento / ator | Para | Condições e efeitos |
|---|---|---|---|
| — | Prestador se candidata | `PENDENTE` | Vaga `PUBLICADA` (ou reaberta por falta); prestador `APROVADO`, com chave PIX e sem suspensão; sem candidatura anterior na mesma vaga; sem outra alocação ativa em horário sobreposto |
| `PENDENTE` | Empresa aprova | `APROVADA` | Há posição livre; agora < `starts_at` (ou vaga reaberta e agora < `ends_at`). Cria `Assignment` `CONFIRMADA`; notifica o prestador |
| `PENDENTE` | Empresa recusa | `RECUSADA` | Notifica o prestador |
| `PENDENTE` | Prestador desiste | `DESISTENCIA` | Sem penalidade (ainda não havia compromisso) |
| `PENDENTE` | SISTEMA: vaga `FINALIZADA` ou `CANCELADA` | `EXPIRADA` | — |

Estados finais: `APROVADA` (o acompanhamento continua na alocação), `RECUSADA`, `DESISTENCIA`, `EXPIRADA`.

---

## 3. Alocação (`Assignment`): o turno de um prestador

| De | Evento / ator | Para | Condições e efeitos |
|---|---|---|---|
| — | Candidatura aprovada | `CONFIRMADA` | — |
| `CONFIRMADA` | Prestador faz check-in (US50) | `EM_EXECUCAO` | Agora entre `starts_at` − *antecedência do check-in (30 min)* e `starts_at` + *tolerância de falta (30 min)*; distância até a vaga ≤ *raio (150 m)* (fórmula de Haversine). Guarda horário, coordenadas e distância |
| `CONFIRMADA` | SISTEMA: agora > `starts_at` + *tolerância de falta (30 min)* sem check-in | `FALTA` | Libera a posição, reabre a vaga, notifica a empresa (US55), conta para a suspensão automática |
| `CONFIRMADA` | Prestador cancela [pós-MVP: US72] | `CANCELADA_PRESTADOR` | ≥ *24 h* antes: sem penalidade. Menos de 24 h: bloqueio de *7 dias* + rebaixamento de status. Libera a posição |
| `CONFIRMADA` | Empresa cancela [pós-MVP: US71] | `CANCELADA_EMPRESA` | Estorno da posição |
| `EM_EXECUCAO` | Prestador faz check-out (US54) | `AGUARDANDO_VALIDACAO` | Guarda o horário de saída |
| `EM_EXECUCAO` | SISTEMA: agora > `ends_at` + *check-out automático (2 h)* | `AGUARDANDO_VALIDACAO` | `check_out_at = ends_at`, `check_out_auto = true` |
| `AGUARDANDO_VALIDACAO` | Empresa aprova as horas (US56) | `APROVADA` | — |
| `AGUARDANDO_VALIDACAO` | SISTEMA: *janela de contestação (24 h)* após o check-out sem manifestação (US59) | `APROVADA` | `validated_by = SISTEMA`, motivo "aprovação por decurso de prazo" |
| `AGUARDANDO_VALIDACAO` | Empresa contesta com motivo (US57) [extra] | `CONTESTADA` | Notifica o prestador e o admin |
| `CONTESTADA` | Admin decide a favor do prestador | `APROVADA` | Motivo obrigatório. A equipe administrativa contata as partes por fora |
| `CONTESTADA` | Admin decide a favor da empresa | `ESTORNADA` | Motivo obrigatório; valor da posição volta à empresa |
| `APROVADA` | SISTEMA: liquidação | `PAGA` | Lançamentos `REPASSE_PRESTADOR` (valor − 3%) e `TAXA_PLATAFORMA` (3%), com chave de idempotência por alocação. Se o PSP falhar, continua `APROVADA` e o próximo processamento tenta de novo |

Estados finais: `PAGA`, `FALTA`, `ESTORNADA`, `CANCELADA_PRESTADOR`, `CANCELADA_EMPRESA`.
`CONTESTADA` depende de ação do admin. O painel deve destacar contestações abertas há mais de 48 h.

---

## 4. Custódia (`Custody`)

| De | Evento | Para | Efeito |
|---|---|---|---|
| — | Vaga criada | `PENDENTE` | — |
| `PENDENTE` | Pagamento confirmado | `RETIDA` | `RETENCAO` = valor × posições |
| `PENDENTE` | Vaga cancelada antes do pagamento | `CANCELADA` | — |
| `RETIDA` | Cada alocação `PAGA` ou `ESTORNADA` | `RETIDA` | Lançamentos parciais |
| `RETIDA` | Vaga `FINALIZADA` ou `CANCELADA` | `ENCERRADA` | Estorno do saldo restante. Invariante: `RETENCAO = REPASSES + TAXAS + ESTORNOS` |

---

## 5. Verificação de cadastro (triagem)

**Empresa:** `PENDENTE` → `APROVADA` | `REJEITADA` (admin, motivo obrigatório) · `REJEITADA` → `PENDENTE` (empresa corrige os dados).
**Prestador:** `PENDENTE_DOCUMENTOS` → `EM_ANALISE` (enviou documento frente, verso e selfie) → `APROVADO` | `REJEITADO` (admin, motivo obrigatório) · `REJEITADO` → `EM_ANALISE` (reenvio).

O que cada um pode fazer antes da aprovação:
- **Empresa:** navegar e configurar o perfil; **não** publica vagas.
- **Prestador:** buscar e ver vagas; **não** se candidata.

---

## 6. Suspensão automática do prestador

SISTEMA: ao registrar uma `FALTA`, se o prestador tiver ≥ *2 faltas em 30 dias*, define `suspended_until = agora + duração da suspensão (15 dias)` e o notifica. Suspenso, ele não se candidata e não pode ser aprovado. O admin pode suspender ou reativar manualmente [pós-MVP: US76].
