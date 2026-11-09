# Campus Complaint Management System (CCMS) — Deployment & Operations Guide

## 1. Architecture Overview

CCMS is architected as a containerized multi-tier cloud-ready web application:

```
[ Client Browser ]
        │
        ▼ (Port 80/443)
[ Nginx Reverse Proxy / Static Host (Frontend) ]
        │
        ├─> Static SPA files (React 18 + Vite)
        │
        └─> Proxy /api/* ───> [ FastAPI Backend (Uvicorn) ] (Port 8000)
                                      │
                                      ▼ (Port 5432)
                            [ PostgreSQL 16 DB ]
                                      ▲
                                      │ (Port 8080 - Debug Profile)
                            [ Adminer Web GUI ]
```

---

## 2. Prerequisites

- **Docker Engine**: version 24.0+
- **Docker Compose**: version 2.20+
- Minimum Server Specs:
  - 2 vCPU
  - 4 GB RAM
  - 20 GB SSD storage
  - Ubuntu 22.04 LTS or Debian 12 recommended

---

## 3. Quick Start (Single Node Docker Compose)

### Step 1: Clone Repository & Configure Environment
```bash
git clone https://github.com/TakshChauhan/Campus-Complaint-Management-System.git
cd Campus-Complaint-Management-System

# Create deployment environment file
cp .env.docker.example .env
```

### Step 2: Set Secrets in `.env`
Edit `.env` to configure production credentials:
- Set strong random values for `POSTGRES_PASSWORD` and `SECRET_KEY`.
- Set `CORS_ORIGINS` to your domain names (e.g. `https://ccms.dau.ac.in`).

### Step 3: Build & Launch Containers
```bash
# Build and start services in detached mode
docker compose up -d --build

# Verify running containers
docker compose ps
```

### Step 4: Verify Deployment
Run the automated deployment verifier:
```bash
python scripts/verify_deployment.py
```

Expected output:
```
[*] Checking Backend Health Endpoint at http://localhost:8000/health...
    [+] PASS: Backend Health Endpoint responded with HTTP 200
[*] Checking Frontend Web Application at http://localhost:3000...
    [+] PASS: Frontend Web Application responded with HTTP 200
[*] Checking Backend Swagger UI at http://localhost:8000/docs...
    [+] PASS: Backend Swagger UI responded with HTTP 200
ALL CHECKS PASSED: CCMS deployment is healthy and ready for traffic!
```

---

## 4. Database Migrations & Seeding

Migrations run automatically on backend startup via the container entrypoint:
```bash
alembic upgrade head && python -m app.scripts.seed_departments
```

To run manual migration or inspection:
```bash
# Open interactive shell in backend container
docker compose exec backend bash

# Check current Alembic revision
alembic current

# Run manual migration check
alembic check
```

---

## 5. Production Operations & Maintenance

### 5.1 Backing Up Database
```bash
# Create timestamped database dump
docker compose exec postgres pg_dump -U ccms_user -d ccms_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

### 5.2 Restoring Database
```bash
cat backup_file.sql | docker compose exec -T postgres psql -U ccms_user -d ccms_db
```

### 5.3 Viewing Logs
```bash
# Follow all container logs
docker compose logs -f

# Follow backend logs specifically
docker compose logs -f backend
```

### 5.4 Graceful Teardown
```bash
docker compose down
```
*(To preserve database volume, do NOT pass `-v` flag)*

---

## 6. Staging Environment Checklist

| Item | Validation Method | Responsible Role |
| :--- | :--- | :--- |
| Database Migration Integrity | `alembic current` matches repository head | Backend / DevOps |
| Seed Data Verification | Department and Hostel lookup tables populated | Backend / DevOps |
| Frontend Asset Compression | Gzip enabled in Nginx response headers | Frontend / DevOps |
| SSL / HTTPS Termination | Reverse proxy TLS cert validation | DevOps |
| Concurrency Lock Verification | S3-15 multi-session decision barrier test | QA / Backend |
| Active Coverage Service | S4-07 coverage gap active staff filter | QA / Backend |
