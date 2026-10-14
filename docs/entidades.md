# Modelo de entidades — Conecta Já

> Fonte oficial do modelo de dados. Nomes de classe em inglês (código) e termos de negócio em português (interface).
> Valores monetários sempre em **centavos (inteiro)**. Datas em UTC no banco, exibidas em `America/Sao_Paulo`.
> Itens marcados **[pós-MVP]** podem existir como campo/modelo vazio, mas não precisam de tela nem regra agora.

## Visão geral

```
User ─┬─ 1:1 ─ Worker (Prestador) ── 1:N ─ WorkerDocument
      │                         └── 1:N ─ Application ── 0..1 ─ Assignment
      └─ N:1 ─ CompanyMember ── N:1 ─ Company (Contratante)
                                         └── 1:N ─ Vacancy (Vaga/turno) ── 1:1 ─ Custody ── 1:N ─ LedgerEntry
                                                        ├── 1:N ─ Application
                                                        └── 1:N ─ Assignment (Alocação)
StateTransition (auditoria de qualquer entidade com estado) · PlatformParameters (singleton) · Notification · VerificationReview
```

## Identidade e acesso

### User (`accounts.User`, já existe)
Login por **e-mail + senha** (e-mail único, case-insensitive). Campo `role`: `COMPANY`, `WORKER` ou `ADMIN`. Admin = `is_staff`.

### Company — Contratante
| Campo | Observação |
|---|---|
| `cnpj` | único, só dígitos, dígitos verificadores validados |
| `legal_name` (razão social), `trade_name` (nome fantasia) | preenchidos pela BrasilAPI, editáveis |
| `state_registration` (inscrição estadual) | texto; aceita "ISENTO" |
| `tax_regime` | `SIMPLES` ou `NORMAL` |
| `registration_status` | situação cadastral retornada pela BrasilAPI (ex.: ATIVA) |
| endereço (`street`, `number`, `complement`, `district`, `city`, `state`, `zip_code`), `phone` | dados cadastrais gerais |
| `preferred_payment_method` | `PIX`, `BOLETO` ou `CARTAO` — **só a preferência**; nunca armazenar dados de cartão ou conta (no futuro o PSP tokeniza) |
| `verification_status` | `PENDENTE`, `APROVADA`, `REJEITADA` (ver `VerificationReview`) |
| `description` | descrição da empresa exibida ao prestador [pós-MVP: US15] |

### CompanyMember
Vínculo `User` ↔ `Company` com `role`: `OWNER` (MVP) ou `MANAGER` [pós-MVP: US03]. Nunca compartilhar login.

### Worker — Prestador
| Campo | Observação |
|---|---|
| `full_name`, `cpf` (único, dígitos verificadores validados), `phone`, `birth_date` | idade mínima 18 anos |
| `verification_status` | `PENDENTE_DOCUMENTOS`, `EM_ANALISE`, `APROVADO`, `REJEITADO` |
| `pix_key_type` (`CPF`, `EMAIL`, `TELEFONE`, `ALEATORIA`), `pix_key` | sempre mascarada em respostas e logs |
| `home_latitude`, `home_longitude` | opcional; para ordenar vagas por proximidade |
| `suspended_until` | preenchido por suspensão automática ou manual |
| `level` | `NOVO` (MVP); níveis [pós-MVP: US65] |
| `skills`, `availability`, portfólio | [pós-MVP: US08–US10] |

### WorkerDocument
`worker`, `kind` (`DOC_FRENTE`, `DOC_VERSO`, `SELFIE`), `file` (**armazenamento privado**, nunca URL pública; acesso só pelo dono e pelo admin), `uploaded_at`.

### VerificationReview
Decisão do admin na fila de verificação (US73): `subject_type` (`COMPANY`/`WORKER`), `subject_id`, `reviewer`, `decision` (`APROVADO`/`REJEITADO`), `reason` (obrigatório na rejeição), `created_at`.

## Vagas e execução

### Vacancy — Vaga (um turno com N posições)
| Campo | Observação |
|---|---|
| `company`, `title`, `category`, `description` (escopo do serviço) | categoria de uma lista fixa (ex.: Ajudante de obra, Carga e descarga, Varejo, Eventos, Fotografia, Limpeza, Outros) |
| endereço + `latitude`, `longitude` | ponto escolhido no mapa (OpenStreetMap/Leaflet) ou "usar minha localização" |
| `starts_at`, `ends_at` | horas do turno definidas no anúncio |
| `pay_per_person_cents` | valor bruto por pessoa (o que a empresa paga) |
| `positions` | número de pessoas (≥ 1) |
| `requires_meeting` | [pós-MVP: US23] |
| `status` | ver `docs/maquina-de-estados.md` |

Calculados: `filled_positions` (alocações ativas), `worker_net_cents` = valor − taxa do prestador (ex.: R$ 100 → R$ 97).

### Application — Candidatura
`vacancy`, `worker`, `status`, `created_at`, `decided_at`, `decided_by`. Único por (`vacancy`, `worker`).

### Assignment — Alocação (o turno de um prestador)
Criada quando a candidatura é aprovada. Campos: `vacancy`, `worker`, `application`, `status`,
`check_in_at`, `check_in_lat`, `check_in_lng`, `check_in_distance_m`, `check_out_at`, `check_out_auto` (bool),
`validated_at`, `validated_by` (usuário ou `SISTEMA`).

## Dinheiro (simulado no MVP, mesmo desenho do PSP real)

### Custody — Custódia da vaga
`vacancy` (1:1), `amount_cents` (= valor por pessoa × posições), `status`, `psp_reference` (id do PSP fake), `idempotency_key` (único).
A plataforma **não** guarda dinheiro: a custódia representa o valor retido no PSP.

### LedgerEntry — Livro-razão (imutável, só inserção)
`custody`, `assignment` (opcional), `kind`, `amount_cents` (> 0), `idempotency_key` (único), `created_at`.
`kind`: `RETENCAO` (empresa pagou), `REPASSE_PRESTADOR` (97%), `TAXA_PLATAFORMA` (3%), `ESTORNO_CONTRATANTE` (posições não usadas ou cancelamento).
Invariante: `RETENCAO = REPASSE + TAXA + ESTORNO` quando a custódia é encerrada.

### Carteira do prestador (não é tabela — é visão calculada)
- **A receber:** alocações confirmadas/em validação × valor líquido, com data prevista de liberação.
- **Liberado:** soma dos `REPASSE_PRESTADOR` do prestador, com data de cada lançamento.

## Transversais

### StateTransition — trilha de auditoria
`entity_type`, `entity_id`, `from_state`, `to_state`, `actor` (usuário ou nulo = `SISTEMA`), `reason`, `created_at`. Gravada **na mesma transação** de toda mudança de estado.

### PlatformParameters — parâmetros editáveis (singleton)
Todos os prazos, limites e taxas de `docs/regras-de-negocio.md`. Editável pelo admin (US79). O código **sempre** lê daqui.

### Notification — notificações dentro do app
`user`, `kind`, `title`, `message`, `link`, `read_at`, `created_at`. Sem e-mail ou push no MVP.

### Review — avaliação bilateral [pós-MVP: US63/US64]
Nota de 1 a 5 + comentário opcional; não obrigatória; conta para o status.
