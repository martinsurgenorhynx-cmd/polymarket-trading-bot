# QuantDinger Python API (backend)

Flask-based backend for QuantDinger: market data, indicators, AI analysis, backtesting, and a strategy runtime with multi-user support.

## What you get

- **Multi-market data layer**: factory-based providers (crypto / US stocks / forex / futures, etc.)
- **Indicators + backtesting**: persisted runs/history in PostgreSQL
- **AI multi-agent analysis**: optional web search + OpenRouter LLM integration
- **Strategy runtime**: thread-based executor, with optional auto-restore on startup
- **Pending orders worker (optional)**: polls queued orders and dispatches signals (webhook/notifications)
- **Multi-user authentication**: role-based access control (admin/manager/user/viewer)
- **User management**: admin can create/edit/delete users and reset passwords

## Project layout

```text
backend_api_python/
├─ app/
│  ├─ __init__.py                 # Flask app factory + startup hooks
│  ├─ config/                     # Settings (env-driven)
│  ├─ data_sources/               # Data sources + factory
│  ├─ routes/                     # REST endpoints
│  ├─ services/                   # Analysis, agents, strategies, search, user_service
│  └─ utils/                      # PostgreSQL helpers, config loader, logging, HTTP utils
├─ migrations/
│  └─ init.sql                    # PostgreSQL schema initialization
├─ env.example                    # Copy to .env for local config
├─ requirements.txt
├─ run.py                         # Entrypoint (loads .env, applies proxy env, starts Flask)
├─ gunicorn_config.py             # Optional production config
└─ README.md
```

## Quick start (Docker - Recommended)

### 1) Configure environment

Create `.env` file in project root:

```bash
# Database
POSTGRES_USER=quantdinger
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DB=quantdinger

# Admin account (created on first startup)
ADMIN_USER=admin
ADMIN_PASSWORD=your_admin_password

# Optional
OPENROUTER_API_KEY=your_api_key
```

### 2) Start services

```bash
docker-compose up -d
```

This will:
- Start PostgreSQL database (port 5432)
- Initialize database schema automatically
- Start backend API (port 5000)
- Start frontend (port 8888)
- Create admin user from `ADMIN_USER`/`ADMIN_PASSWORD`

### 3) Access the system

- Frontend: `http://localhost:8888`
- Backend API: `http://localhost:5000`
- Login with your configured admin credentials

## Quick start (Local Development)

### Prerequisites

- Python 3.10+ recommended
- PostgreSQL 14+ installed and running

### 1) Setup PostgreSQL

```bash
# Create database and user
sudo -u postgres psql
CREATE DATABASE quantdinger;
CREATE USER quantdinger WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE quantdinger TO quantdinger;
\q

# Initialize schema
psql -U quantdinger -d quantdinger -f migrations/init.sql
```

### 2) Install dependencies

```bash
cd backend_api_python
pip install -r requirements.txt
```

### 3) Create your local `.env`

Windows (CMD):
```bash
copy env.example .env
```

Windows (PowerShell):
```bash
Copy-Item env.example .env
```

Then edit `.env` and set:

```bash
# Required
DATABASE_URL=postgresql://quantdinger:your_password@localhost:5432/quantdinger
SECRET_KEY=your-secret-key-change-me
ADMIN_USER=admin
ADMIN_PASSWORD=your_admin_password

# Optional but recommended
OPENROUTER_API_KEY=your_api_key
```

### 4) Start the API server

```bash
python run.py
```

Default address: `http://localhost:5000`

## Database (PostgreSQL)

- Connection: configured via `DATABASE_URL` environment variable
- Schema: initialized via `migrations/init.sql`
- Tables are managed with foreign key constraints and indexes for performance
- User data isolation via `user_id` column in relevant tables

## User Roles & Permissions

| Role | Permissions |
|------|-------------|
| admin | Full access + user management |
| manager | Strategy, backtest, portfolio, settings |
| user | Strategy, backtest, portfolio (own data) |
| viewer | Dashboard view only |

## API Endpoints

### Authentication
```text
POST /api/user/login      - User login
POST /api/user/logout     - User logout
GET  /api/user/info       - Get current user info
```

### User Management (Admin only)
```text
GET    /api/users/list           - List all users
POST   /api/users/create         - Create user
PUT    /api/users/update?id=     - Update user
DELETE /api/users/delete?id=     - Delete user
POST   /api/users/reset-password - Reset password
```

### Self-Service
```text
GET  /api/users/profile         - Get own profile
PUT  /api/users/profile/update  - Update own profile
POST /api/users/change-password - Change own password
```

### Other Endpoints
```text
GET  /api/health
GET  /api/indicator/kline
POST /api/analysis/multi
```

## AI memory augmentation

This backend includes a lightweight, privacy-first **memory-augmented multi-agent** system:

- Memory DBs stored in PostgreSQL
- API hooks:
  - `POST /api/analysis/multi` (main entry)
  - `POST /api/analysis/reflect` (manual learn from post-trade outcomes)
- Controls in `.env`:
  - `ENABLE_AGENT_MEMORY`, `AGENT_MEMORY_*`
  - `ENABLE_REFLECTION_WORKER`, `REFLECTION_WORKER_INTERVAL_SEC`

## Frontend integration

For Vue dev server:
- Frontend: `http://localhost:8000`
- Backend: `http://localhost:5000`
- Proxy config: `quantdinger_vue/vue.config.js`

## Production (Gunicorn)

```bash
gunicorn -c gunicorn_config.py "run:app"
```

## Troubleshooting

- **Database connection failed**: Check `DATABASE_URL` format and PostgreSQL service status
- **Outbound requests fail**: Configure `PROXY_PORT` or `PROXY_URL` in `.env`
- **Disable auto-restore**: Set `DISABLE_RESTORE_RUNNING_STRATEGIES=true`
- **Disable pending-order worker**: Set `ENABLE_PENDING_ORDER_WORKER=false`

## License

Apache License 2.0. See repository root `LICENSE`.
