# Conecta Já

Marketplace que conecta empresas (Contratantes) a trabalhadores autônomos (Contratados) para
serviços manuais de curta duração. Projeto acadêmico (`MVP_Ecommerce`).

- `backend/`: Django + Django REST Framework + PostgreSQL
- `frontend/`: React + TypeScript (Vite)
- `docs/`: documentação de domínio
- `CLAUDE.md`: regras do projeto

## Pré-requisitos (Windows)

- Python 3.12
- Node.js LTS
- PostgreSQL 16 instalado, **ou** Docker Desktop (para usar o `docker-compose.yml`)

Os comandos abaixo são para o **PowerShell**, a partir da raiz do repositório.

## Banco de dados

Opção 1 — Docker (recomendado):

```powershell
docker compose up -d
```

Opção 2 — PostgreSQL instalado: crie o usuário e o banco `conectaja` (senha `conectaja`) ou
ajuste `DATABASE_URL`.

## Backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt

$env:SECRET_KEY = "dev-secret"
$env:DEBUG = "true"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgres://conectaja:conectaja@localhost:5432/conectaja"

python backend\manage.py migrate
python backend\manage.py runserver
```

O backend não carrega o arquivo `.env` sozinho; as variáveis precisam estar no ambiente
(veja `.env.example` para a lista). Teste em <http://localhost:8000/api/health/>: deve
responder `200` com `{"status": "ok"}`.

## Frontend

Em outro terminal:

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

Abra <http://localhost:5173>. O Vite encaminha `/api` para `http://localhost:8000`
(mude com `VITE_API_PROXY_TARGET`). A página inicial mostra o status de `/api/health/`.

## Testes e qualidade

Backend (com o ambiente virtual ativo e as variáveis acima definidas):

```powershell
ruff check backend
pytest backend
python backend\manage.py makemigrations --check --dry-run
```

Frontend:

```powershell
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

`npm test` roda os testes uma vez e termina (sem modo watch). O CI executa todos esses comandos.

## Integrações externas

Ficam em `backend/integrations/`, atrás de uma interface com implementação fake. Veja o
`README.md` da pasta.
