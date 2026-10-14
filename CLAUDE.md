# Conecta Já — guia para o Claude

Marketplace que conecta empresas (**Contratantes**, com CNPJ) a trabalhadores autônomos (**Prestadores**, pessoa física com CPF) para turnos de trabalho de curta duração no Brasil. Projeto acadêmico (repositório `MVP_Ecommerce`) com meta de virar produto depois do semestre. Escopo e ordem do MVP: `docs/mvp.md`.

## Como trabalhar neste repositório

1. Leia a issue inteira. A história e os **critérios de aceite** são o escopo: implemente só isso.
2. Se faltarem critérios de aceite, houver ambiguidade de regra de negócio ou conflito com as regras abaixo, **não adivinhe**: comente na issue com as perguntas e pare.
3. Trabalhe em branch (`claude/...`), nunca na `main`. Um PR por issue.
4. Todo PR inclui testes que cobrem os critérios de aceite e passa no CI (lint, testes, build).
5. Descrição do PR em português: o que foi feito, como testar, o que ficou de fora, dúvidas.
6. Não altere `.github/`, este `CLAUDE.md`, arquivos de deploy nem secrets. Se for necessário, peça na issue.
7. Não adicione dependências sem justificar no PR.

## Stack e comandos

- Backend: Python, Django + Django REST Framework, PostgreSQL, em `backend/`.
- Frontend: React, em `frontend/`.
- Documentação de domínio: `docs/` (entidades, máquina de estados, regras de negócio).

| O quê | Comando (a partir da pasta indicada) |
|---|---|
| Testes backend | `pytest backend` |
| Lint backend | `ruff check backend` |
| Migrations pendentes? | `python backend/manage.py makemigrations --check --dry-run` |
| Lint / testes / build frontend | `npm --prefix frontend run lint`, `npm --prefix frontend test`, `npm --prefix frontend run build` |
| Processar prazos | `python backend/manage.py processar_prazos` (`--loop 15` em desenvolvimento) |

No GitHub Actions, rode um comando por vez, sem `cd`, `&&` ou ambiente virtual (as dependências já estão no ambiente).

`npm test` deve rodar uma vez e terminar (sem modo watch). Dependências do backend: `requirements.txt` (runtime) e `requirements-dev.txt` (inclui o anterior + pytest, pytest-django, ruff). O backend lê a configuração de variáveis de ambiente (`SECRET_KEY`, `DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`); nunca coloque segredos no código, use `.env.example` para documentar.

## Regras de negócio travadas (não alterar sem decisão do PO)

As regras completas, com os valores padrão, estão em `docs/regras-de-negocio.md`. As transições oficiais estão em `docs/maquina-de-estados.md` e os modelos em `docs/entidades.md`. **Esses três arquivos prevalecem** sobre qualquer suposição. Se não cobrirem o caso, pergunte na issue.

- **Identidade e login:** login por e-mail + senha. Contratante exige CNPJ (consultado na BrasilAPI). Prestador é pessoa física com CPF, 18 anos ou mais, documento com foto, selfie e chave PIX do próprio titular. A triagem é **manual** pelo admin.
- **Receita:** a empresa paga **exatamente** o valor anunciado, sem acréscimo e **sem mensalidade**. A única receita é a taxa de **3%** sobre o valor bruto do turno, descontada no repasse ao prestador (R$ 100 → prestador R$ 97, plataforma R$ 3).
- **Pagamento (escrow):** a vaga só é publicada **depois** do pagamento. O dinheiro fica retido pelo PSP (a plataforma **não** custodia fundos) e é liberado ao prestador após a empresa confirmar a presença, ou automaticamente após a janela de contestação. No MVP o PSP é **simulado** (`backend/integrations/payments/`).
- **Candidatura:** o prestador se candidata e a empresa aprova. Não há despacho algorítmico. Contatos ficam ocultos até a alocação.
- **Turno:** valor fixo pelas horas do anúncio. Não há hora extra no MVP.
- **Limitações trabalhistas** são premissas documentadas do projeto, não problemas a resolver no código.

## Diretrizes de arquitetura

- **Máquinas de estado:** Vaga, Turno, Candidatura e Pagamento têm estados e transições explícitos. Toda transição passa por um único serviço de domínio, valida o estado de origem e grava histórico (quem, quando, de, para). Nenhum estado não final pode ficar sem saída: todo estado "em andamento" precisa de prazo/timeout ou de uma ação que o faça avançar, para nada ficar "processando" para sempre. A definição oficial fica em `docs/maquina-de-estados.md`; se o arquivo não existir ou não cobrir o caso, pare e pergunte.
- **Parâmetros configuráveis:** prazos, limites e taxa da plataforma **nunca** ficam fixos no código. Leia de `PlatformParameters`, editável pelo Admin (US79), com os padrões de `docs/regras-de-negocio.md`.
- **Dinheiro:** valores em centavos (inteiro) ou `Decimal`, nunca `float`. Operações financeiras idempotentes (chave de idempotência) e registradas em um livro-razão imutável.
- **Integrações externas** (PSP, consulta de CNPJ, SMS, verificação de documento, geolocalização, notificações): sempre atrás de uma interface em `backend/integrations/`, com implementação *fake* para desenvolvimento e testes. Os testes nunca chamam serviços externos.
- **Três atores, responsabilidades separadas:** Contratante, Prestador e Admin têm áreas e permissões distintas. A autorização é verificada no servidor, por objeto; nunca confie no cliente. Várias pessoas e várias unidades por empresa (US02, US03) via vínculo (membership), não via compartilhamento de login.
- **LGPD:** colete o mínimo; mascare CPF e PIX em logs e respostas; documentos e selfies em armazenamento privado. A exclusão de conta anonimiza os dados pessoais e preserva os registros financeiros e fiscais sem identificação direta.
- **Datas:** armazene em UTC, exiba em `America/Sao_Paulo`.

## Convenções

- Código (identificadores, commits, nomes de branch) em inglês; textos de interface, documentação e descrições de PR em português.
- Glossário (use estes nomes no código): Contratante/Empresa = `Company`; Prestador = `Worker`; Vaga (um turno com N posições) = `Vacancy`; Candidatura = `Application`; Alocação (o turno de um prestador) = `Assignment`; Custódia = `Custody`; Lançamento do livro-razão = `LedgerEntry`; Unidade = `Site` [pós-MVP]. Na interface, use sempre "Prestador" (nunca "Contratado").
- Mudanças de banco sempre com migration versionada. API REST sob `/api/`, JSON, erros em formato consistente. Autenticação por sessão do Django + CSRF (frontend no mesmo domínio via proxy).
- Área do admin: Django admin customizado em português (`/admin`).
- Interface: web responsiva (mobile-first), em pt-BR, com os tokens de design definidos na BASE-02.
