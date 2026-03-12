# Multi-User System Setup Guide

This guide explains how to configure QuantDinger for multi-user mode with PostgreSQL database.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Frontend     │────▶│  Backend API    │────▶│   PostgreSQL    │
│  (Vue.js)       │     │   (Flask)       │     │   Database      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                        ┌──────┴──────┐
                        │ User Auth   │
                        │ JWT Token   │
                        │ Role-based  │
                        │ Access      │
                        └─────────────┘
```

## Quick Start (Docker)

### 1. Update docker-compose.yml

The new `docker-compose.yml` already includes PostgreSQL. Just set the password:

```bash
# Create .env file in project root
cat > .env << EOF
POSTGRES_USER=quantdinger
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=quantdinger
EOF
```

### 2. Start Services

```bash
docker-compose up -d
```

This will:
- Start PostgreSQL database
- Initialize schema automatically (via `init.sql`)
- Start backend API connected to PostgreSQL
- Start frontend

### 3. Default Credentials

- **Username**: `admin`
- **Password**: `admin123`

**Important**: Change the admin password immediately after first login!

## Manual Setup (Development)

### 1. Install PostgreSQL

```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib

# macOS
brew install postgresql

# Windows
# Download from https://www.postgresql.org/download/windows/
```

### 2. Create Database

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create database and user
CREATE DATABASE quantdinger;
CREATE USER quantdinger WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE quantdinger TO quantdinger;
\q
```

### 3. Initialize Schema

```bash
# Run init.sql
psql -U quantdinger -d quantdinger -f backend_api_python/migrations/init.sql
```

### 4. Configure Backend

Create/update `backend_api_python/.env`:

```bash
# Database Configuration
DB_TYPE=postgresql
DATABASE_URL=postgresql://quantdinger:your_password@localhost:5432/quantdinger

# Disable single-user legacy mode
SINGLE_USER_MODE=false
```

### 5. Install Dependencies

```bash
cd backend_api_python
pip install -r requirements.txt
```

### 6. Start Backend

```bash
python run.py
```

## Migration from SQLite

If you have existing data in SQLite:

```bash
# Set environment variables
export DATABASE_URL=postgresql://quantdinger:your_password@localhost:5432/quantdinger

# Run migration script
python scripts/migrate_sqlite_to_postgres.py
```

## User Roles & Permissions

| Role    | Permissions |
|---------|-------------|
| admin   | Full access, user management, settings |
| manager | Strategy, backtest, portfolio, settings |
| user    | Strategy, backtest, portfolio (own data) |
| viewer  | View only (dashboard) |

## API Endpoints

### Authentication

```
POST /api/user/login       - Login
POST /api/user/logout      - Logout
GET  /api/user/info        - Get current user info
```

### User Management (Admin only)

```
GET    /api/users/list           - List all users
GET    /api/users/detail?id=     - Get user detail
POST   /api/users/create         - Create user
PUT    /api/users/update?id=     - Update user
DELETE /api/users/delete?id=     - Delete user
POST   /api/users/reset-password - Reset user password
GET    /api/users/roles          - Get available roles
```

### Self-Service

```
GET  /api/users/profile         - Get own profile
PUT  /api/users/profile/update  - Update own profile
POST /api/users/change-password - Change own password
```

## Security Recommendations

1. **Change default admin password** immediately
2. **Use strong passwords** (min 12 characters)
3. **Enable HTTPS** in production
4. **Restrict database access** to backend only
5. **Regular backups** of PostgreSQL data

## Troubleshooting

### Cannot connect to PostgreSQL

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection
psql -U quantdinger -d quantdinger -c "SELECT 1"
```

### Migration fails

```bash
# Check SQLite path
ls -la backend_api_python/data/quantdinger.db

# Check PostgreSQL tables
psql -U quantdinger -d quantdinger -c "\dt"
```

### Token invalid after restart

JWT tokens are validated using `SECRET_KEY`. Ensure the same key is used:

```bash
# Generate a secure key
python -c "import secrets; print(secrets.token_hex(32))"

# Set in .env
SECRET_KEY=your_generated_key
```

## Legacy Support

The system now requires PostgreSQL for multi-user support. SQLite is no longer supported.

If you need to migrate from an older SQLite-based installation, contact the project maintainers for assistance.
