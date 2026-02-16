# Budget App — Build Walkthrough

A comprehensive guide to constructing this personal finance application from scratch. This walkthrough covers the full stack: Python/FastAPI backend, React frontend, Plaid bank integration, Claude AI categorization, and Electron desktop packaging.

## Architecture Overview

The app is a desktop application built with three main layers:

- **Backend**: Python (FastAPI + SQLAlchemy + SQLite) running on localhost:8000
- **Frontend**: React (Vite + Recharts + React Router) running on localhost:5173
- **Desktop Shell**: Electron wraps both into a native macOS/Windows app

Data flows through the system like this:

```
Bank Accounts (Plaid API)
        ↓
  FastAPI Backend → SQLite Database (~/BudgetApp/budget.db)
        ↓
  3-Tier Categorization Engine
    1. Amount Rules (exact match)
    2. Merchant Mappings (pattern match)
    3. Claude AI (fallback)
        ↓
  React Dashboard (charts, tables, review queue)
        ↓
  Electron Window (native desktop app)
```

## Walkthrough Parts

| Part | Topic | What You'll Build |
|------|-------|-------------------|
| [Part 1](01-project-setup.md) | Project Setup & Foundation | Repository, dependencies, dev tooling, environment config |
| [Part 2](02-database-and-models.md) | Database Models & Backend Core | SQLite setup, all ORM models, FastAPI app skeleton |
| [Part 3](03-plaid-integration.md) | Plaid Integration & Account Management | Bank linking, encrypted token storage, transaction sync |
| [Part 4](04-categorization-engine.md) | Transaction Processing & Categorization | 3-tier engine, review workflow, CSV import, seed data |
| [Part 5](05-frontend-react.md) | Frontend & React UI | All 13+ pages, routing, charts, styles |
| [Part 6](06-advanced-features.md) | Advanced Features | AI insights, investment tracking, background sync, sync history |
| [Part 7](07-electron-and-deployment.md) | Electron Desktop App & Deployment | Native window, backend management, build & packaging |

## Tech Stack Summary

**Backend (Python 3.10+)**

- FastAPI — Web framework and API
- SQLAlchemy 2.0 — ORM with SQLite
- Plaid Python SDK — Bank account integration
- Anthropic SDK — Claude AI for categorization and insights
- yfinance — Stock price data
- APScheduler — Background job scheduling
- Cryptography (Fernet) — Token encryption at rest
- Pandas — Data manipulation for imports

**Frontend (Node.js 18+)**

- React 18 — UI framework
- React Router 6 — Client-side routing
- Recharts — Charts and data visualization
- Lucide React — Icon library
- React Plaid Link — Bank connection widget
- Vite 6 — Build tool and dev server

**Desktop**

- Electron 33 — Native desktop shell
- electron-builder — App packaging (DMG, NSIS)
- PyInstaller — Bundle Python backend as standalone binary

## Prerequisites

Before starting, you'll need:

- Python 3.10+ with [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+ with npm
- A [Plaid](https://dashboard.plaid.com) account (free sandbox, paid for production)
- An [Anthropic](https://console.anthropic.com) API key (for Claude AI features)
- macOS or Linux for development (Windows works but untested for Electron build)
