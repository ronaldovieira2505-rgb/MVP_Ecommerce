# Regras de negócio — Conecta Já

> Fonte oficial das regras e dos valores padrão. Tudo que tiver **chave** é parâmetro de `PlatformParameters`, editável pelo admin (US79) e **nunca fixo no código**.
> Para a demonstração, o admin pode reduzir os prazos para minutos (ex.: janela de contestação de 2 min), sem mudar código.

## 1. Modelo de receita

Conforme o relatório N1, a **única receita** é uma taxa percentual sobre o valor bruto de cada turno, **descontada no repasse ao prestador**. Não há mensalidade, plano nem cobrança de entrada.

**Empresa (contratante):** paga exatamente o valor anunciado do turno, **sem acréscimo**.

**Prestador:** a plataforma retém **3%** do valor recebido (`worker_fee_percent` = 3).
Exemplo: vaga de R$ 100,00 → empresa paga R$ 100,00 → prestador recebe R$ 97,00 → plataforma fica com R$ 3,00.
Arredondamento: taxa = 3% do valor em centavos, arredondada para o centavo mais próximo (meio para cima); prestador = valor − taxa.

## 2. Parâmetros (valores padrão)

| Chave | Padrão | Regra |
|---|---|---|
| `min_publish_lead_minutes` | 720 (12 h) | Antecedência mínima entre a publicação e o início do turno |
| `payment_deadline_minutes` | 1440 (24 h) | Prazo para pagar uma vaga criada; depois ela é cancelada |
| `applications_close_minutes_before` | 120 (2 h) | Candidaturas encerram X min antes do início |
| `checkin_open_minutes_before` | 30 | Check-in liberado a partir de X min antes do início |
| `no_show_tolerance_minutes` | 30 | Sem check-in até X min após o início = falta |
| `geofence_radius_m` | 150 | Distância máxima para aceitar o check-in |
| `auto_checkout_minutes_after_end` | 120 (2 h) | Sem check-out até X min após o fim = check-out automático no horário previsto |
| `contest_window_minutes` | 1440 (24 h) | Janela para a empresa aprovar ou contestar; silêncio = aprovação |
| `no_show_limit` / `no_show_window_days` | 2 / 30 | Faltas que geram suspensão automática, e a janela considerada |
| `suspension_days` | 15 | Duração da suspensão automática |
| `free_cancel_minutes_before` | 1440 (24 h) | Cancelamento sem penalidade até X min antes [pós-MVP] |
| `late_cancel_block_days` | 7 | Bloqueio por cancelamento tardio [pós-MVP] |
| `worker_fee_percent` | 3 | Taxa retida do prestador |

**Unidades e validação (US79):** todo prazo que era em horas passou a ser em **minutos** (os prazos em dias continuam em dias), o que permite demonstrar janelas curtas (ex.: contestação de 2 min). O admin edita os valores em "Parâmetros da plataforma"; a alteração vale de imediato e fica auditada (quem, quando, valor anterior e novo). Valores negativos são rejeitados. Exigem valor maior que zero: `payment_deadline_minutes`, `geofence_radius_m`, `contest_window_minutes`, `no_show_limit`, `no_show_window_days` e `suspension_days`. Os demais prazos aceitam 0. `worker_fee_percent` é inteiro entre 0 e 100.

## 3. Cadastro e triagem

- **Login:** e-mail + senha para empresa e prestador. O admin usa o painel administrativo.
- **Empresa:** CNPJ (validado e consultado na **BrasilAPI**, que preenche razão social, nome fantasia, endereço e situação), inscrição estadual (aceita "ISENTO"), regime tributário (Simples ou Normal), dados cadastrais gerais, meio de pagamento preferido. Uma conta por CNPJ. Se a BrasilAPI estiver fora do ar, o cadastro continua com preenchimento manual e a empresa fica marcada para conferência do admin.
- **Prestador:** nome completo, CPF (dígitos verificadores validados; um CPF por conta), telefone, data de nascimento (mínimo 18 anos), documento com foto (frente e verso) e selfie, e chave PIX.
- **Verificação de identidade (triagem):** **manual**, feita pela equipe administrativa na fila de verificação (US73). O admin compara a selfie com a foto do documento e confere os dados. Empresas são conferidas pelos dados da BrasilAPI. Biometria automática por serviço pago (ex.: idwall, unico) fica para o pós-MVP.
- **Dados de pagamento:** a empresa informa só a preferência (PIX, boleto ou cartão). **Nunca** armazenar número de cartão ou dados bancários: no produto real, o PSP faz isso.
- **Troca de chave PIX:** no MVP, a confirmação por código é **simulada** (o código aparece na tela em modo demonstração) [US07, pós-MVP].

## 4. Vagas (catálogo da empresa)

- Campos obrigatórios: título, categoria, descrição do escopo, endereço com ponto no mapa, início, fim, valor por pessoa (≥ R$ 1,00) e número de pessoas (≥ 1).
- As horas do turno são as do anúncio; o pagamento é o **valor fixo do turno**, não por hora trabalhada.
- A vaga só é publicada **depois** do pagamento (custódia).
- **Editar ou remover** só enquanto nenhuma candidatura tiver sido aprovada. A remoção gera estorno total.

## 5. Candidatura e seleção

- Candidatura voluntária com aprovação da empresa. Não há despacho automático.
- O prestador vê, antes de se candidatar, o **valor líquido** (com os 3% descontados) e o selo "Pagamento garantido" (custódia retida).
- Não é permitido ter duas alocações com horários sobrepostos.

## 6. Execução, validação e pagamento

- **Check-in:** geolocalização do navegador, até 150 m do ponto da vaga. Fora do raio, a mensagem mostra a distância.
- **Check-out:** botão do prestador, com check-out automático como rede de segurança.
- **Validação:** a empresa confere entrada e saída e aprova. Se não se manifestar em 24 h, a aprovação é automática.
- **Contestação [extra]:** a empresa contesta com motivo; a equipe administrativa contata as partes e decide.
- **Liberação:** prestador recebe 97% e a plataforma retém 3% (lançamentos no livro-razão).

## 7. Hora extra: decisão

**MVP:** não há hora extra. O turno tem as horas do anúncio, e o check-out registra a saída real só para conferência.

**Pós-MVP (US52/US53), recomendado:** a empresa solicita a extensão **antes** de o turno terminar, informando as horas e o valor. O prestador aceita ou recusa no app, sem penalidade se recusar. A empresa **paga a extensão em custódia** antes de ela começar. Assim a garantia de pagamento continua valendo. Descartamos a cobrança automática por tempo excedido: ela cobraria a empresa sem consentimento e o valor não estaria garantido ao prestador.

## 8. Notificações

Somente dentro do app (sino com contador): aprovação ou recusa de candidatura, falta (para a empresa), vaga reaberta, aprovação de horas, pagamento liberado e resultado da verificação.

## 9. Fora do produto (decisões do PO)

- **Cupom de desconto (US28):** removido por decisão do PO.
- **Impulsionamento (US33–US36):** créditos comprados, como nos marketplaces tradicionais. A duração e o posicionamento ficam a cargo de um algoritmo interno [pós-MVP].
- **Níveis e selo (US65/US66):** métricas a definir. Avaliações não são obrigatórias, mas contam para o status [pós-MVP].
- **Lista de espera (US43):** chamada automática do próximo candidato [pós-MVP].
