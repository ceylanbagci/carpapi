# CarPapi Web (`/web`)

Django + React + PostgreSQL admin app, with a **Demo4-inspired dark sidebar
layout** (open-source Bootstrap 5 implementation — not the licensed Metronic
assets).

```
web/
├── backend/         Django + DRF, read-only API over the existing carpapi DB
├── frontend/        Vite + React 18 + React Router, demo4-themed pages
└── legacy_chat/     The previous static chat UI (preserved, not wired in)
```

## Pages

| Route        | Source                                                  |
| ------------ | ------------------------------------------------------- |
| `/`          | Dashboard tiles + quick links                           |
| `/cars`      | Distinct `(year, make, model, trim)` from `listings`    |
| `/listings`  | Raw `public.listings` rows                              |
| `/dealers`   | `public.dealers` roster                                 |
| `/makes`     | Distinct makes (joined from listings + dealer roster)   |
| `/models`    | Distinct `(make, model)` pairs from `listings`          |

The schema is **owned by `carpapi/db/schema.sql`** — Django models here use
`managed = False`, so `manage.py migrate` won't touch the live tables.

## 1. Backend (Django)

```bash
cd web/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # edit if your Postgres lives elsewhere
python manage.py runserver 0.0.0.0:8000
```

Default Postgres connection (matches `carpapi/db`):

```
PGPASSWORD=carpapi psql -h localhost -p 5433 -U carpapi -d carpapi
```

Override any of these with env vars: `CARPAPI_DB_HOST`, `CARPAPI_DB_PORT`,
`CARPAPI_DB_NAME`, `CARPAPI_DB_USER`, `CARPAPI_DB_PASSWORD`.

Endpoints:

- `GET /api/stats/` — counts for the dashboard
- `GET /api/dealers/` — paginated, searchable dealer list
- `GET /api/listings/` — paginated, searchable listing list
- `GET /api/cars/` — distinct (year, make, model, trim) groupings
- `GET /api/makes/` — distinct makes with listing+dealer counts
- `GET /api/models/` — distinct (make, model) pairs

## 2. Frontend (React + Vite)

```bash
cd web/frontend
npm install
npm run dev          # listens on 0.0.0.0:5173
```

The dev server proxies `/api/*` → `http://localhost:8000` (override with
`VITE_API_TARGET`). For production-style preview:

```bash
npm run build && npm run preview     # serves on 0.0.0.0:4173
```

## 3. Reaching it from another computer on your home network

Both servers bind to `0.0.0.0`, so any device on your LAN can hit them.

1. Find this host's LAN IP:

   ```bash
   ipconfig getifaddr en0          # macOS Wi-Fi
   ```

2. From the other computer's browser:

   - Frontend (dev):     `http://<lan-ip>:5173/`
   - Backend (API):      `http://<lan-ip>:8000/api/stats/`

3. **Postgres on the other machine.** If the database lives on a *different*
   computer than the Django host, point `CARPAPI_DB_HOST` at that IP **and**
   make sure Postgres is configured to accept it:

   - `postgresql.conf` → `listen_addresses = '*'`
   - `pg_hba.conf` → `host all all 192.168.0.0/16 scram-sha-256`
   - Reload Postgres.

   Same connection string from the remote box:

   ```bash
   PGPASSWORD=carpapi psql -h <db-host-lan-ip> -p 5433 -U carpapi -d carpapi
   ```

4. macOS firewall: System Settings → Network → Firewall → allow
   `python` (Django) and `node` (Vite) inbound.

## Layout components

| File                                | Role                                |
| ----------------------------------- | ----------------------------------- |
| `frontend/index.html`               | HTML entry, Bootstrap + icons CDN   |
| `frontend/src/main.jsx`             | React + Router bootstrap            |
| `frontend/src/App.jsx`              | Routes                              |
| `frontend/src/components/Layout.jsx`| Base shell (sidebar + header + content + footer) |
| `frontend/src/components/Sidebar.jsx`| Dark sidebar / menu               |
| `frontend/src/components/Header.jsx` | Top header                        |
| `frontend/src/components/Footer.jsx` | Footer                            |
| `frontend/src/components/DataTable.jsx` | Reusable paginated table       |
| `frontend/src/styles/theme.css`     | Demo4-inspired CSS                  |

## Notes on the “Demo4” theme

The visual idiom (dark navy sidebar, light content area, round-corner cards,
3699FF accent) follows the *Metronic Demo 4* layout pattern. The actual
Metronic source is commercial, so this implementation is a clean
Bootstrap 5 + Bootstrap Icons rewrite with no Metronic assets bundled. If
you have a Metronic license, you can swap `theme.css` for the licensed
stylesheet and the existing component structure will line up.
