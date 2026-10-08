# Conecta Já — guia para o Claude

Marketplace que conecta empresas (**Contratantes**, com CNPJ) a trabalhadores autônomos (**Contratados**, pessoa física com CPF) para serviços manuais de curta duração no Brasil. Projeto acadêmico (repositório `MVP_Ecommerce`) com meta de virar produto depois do semestre.

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
| Testes backend | `cd backend && pytest` |
| Lint backend | `cd backend && ruff check .` |
| Migrations pendentes? | `cd backend && python manage.py makemigrations --check --dry-run` |
| Lint / testes / build frontend | `cd frontend && npm run lint && npm test && npm run build` |

`npm test` deve rodar uma vez e terminar (sem modo watch). Dependências do backend: `requirements.txt` (runtime) e `requirements-dev.txt` (inclui o anterior + pytest, pytest-django, ruff). O backend lê a configuração de variáveis de ambiente (`SECRET_KEY`, `DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`); nunca coloque segredos no código, use `.env.example` para documentar.

## Regras de negócio travadas (não alterar sem decisão do PO)

- **Identidade:** Contratante exige CNPJ. Contratado é pessoa física com CPF e chave PIX validada contra a identidade.
- **Pagamento (escrow):** a empresa paga **antes** de a vaga ser publicada. O dinheiro fica retido pelo PSP (a plataforma **não** custodia fundos) e é liberado ao Contratado após a aprovação do turno, ou automaticamente após 24 h de silêncio da empresa. O PSP ainda não foi escolhido.
- **Candidatura:** o Contratado se candidata e o Contratante aprova (autocandidatura com aprovação). Não há despacho algorítmico.
- **Entrevista virtual:** flag opcional por vaga; link externo (Google Meet ou Jitsi); contatos mascarados até a alocação do Contratado.
- **Prazos e limites:** publicação com no mínimo 12 h de antecedência; candidaturas encerram 2 h antes do início do turno; ausência de 30 min dispara reabertura automática da vaga; geofence de 150 m para registrar chegada; janela de contestação de 24 h (silêncio = aprovação); suspensão automática após 2 ausências em 30 dias.
- **Limitações trabalhistas** são premissas documentadas do projeto, não problemas a resolver no código.

## Diretrizes de arquitetura

- **Máquinas de estado:** Vaga, Turno, Candidatura e Pagamento têm estados e transições explícitos. Toda transição passa por um único serviço de domínio, valida o estado de origem e grava histórico (quem, quando, de, para). Nenhum estado não final pode ficar sem saída: todo estado "em andamento" precisa de prazo/timeout ou de uma ação que o faça avançar, para nada ficar "processando" para sempre. A definição oficial fica em `docs/maquina-de-estados.md`; se o arquivo não existir ou não cobrir o caso, pare e pergunte.
- **Parâmetros configuráveis:** prazos, limites e taxa da plataforma **nunca** ficam fixos no código. Leia de um modelo de parâmetros editável pelo Admin (US79), com os valores acima como padrão inicial.
- **Dinheiro:** valores em centavos (inteiro) ou `Decimal`, nunca `float`. Operações financeiras idempotentes (chave de idempotência) e registradas em um livro-razão imutável.
- **Integrações externas** (PSP, consulta de CNPJ, SMS, verificação de documento, geolocalização, notificações): sempre atrás de uma interface em `backend/integrations/`, com implementação *fake* para desenvolvimento e testes. Os testes nunca chamam serviços externos.
- **Três atores, responsabilidades separadas:** Contratante, Contratado e Admin têm áreas e permissões distintas. A autorização é verificada no servidor, por objeto; nunca confie no cliente. Várias pessoas e várias unidades por empresa (US02, US03) via vínculo (membership), não via compartilhamento de login.
- **LGPD:** colete o mínimo; mascare CPF e PIX em logs e respostas; documentos e selfies em armazenamento privado. A exclusão de conta anonimiza os dados pessoais e preserva os registros financeiros e fiscais sem identificação direta.
- **Datas:** armazene em UTC, exiba em `America/Sao_Paulo`.

## Convenções

- Código (identificadores, commits, nomes de branch) em inglês; textos de interface, documentação e descrições de PR em português.
- Glossário (use estes nomes no código): Contratante = `Company`; Contratado = `Worker`; Unidade = `Site`; Vaga = `Vacancy`; Turno = `Shift`; Candidatura = `Application`; Pagamento = `Payment`; Admin = `Admin`. Acrescente novos termos aqui via PR do PO.
- Mudanças de banco sempre com migration versionada. API REST sob `/api/`, JSON, erros em formato consistente.

> Diretrizes ainda não confirmadas pelo grupo (revisar): idioma do código, glossário em inglês, anonimização na exclusão de conta, uso de livro-razão, frontend em Vite + TypeScript.
