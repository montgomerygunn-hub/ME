# ME Dashboard

Hosted web app for the Gunn Group Massage Envy clinic dashboard (and, soon,
the FDA/Manager sales dashboard). Replaces the local `me_dashboard.py` /
`sales_dashboard.py` scripts with a browser-based upload + view flow,
password-protected, still emailing the team on generation.

## Local dev

    pip install -r requirements.txt
    playwright install chromium
    export APP_USERNAME=brett
    export APP_PASSWORD=changeme
    export SMTP_USERNAME=... SMTP_PASSWORD=...
    export ANTHROPIC_API_KEY=...
    python app.py

## Deploy (Render)

Deployed via Docker (see `Dockerfile`) with a Persistent Disk mounted at
`/var/data` for the SQLite database (`render.yaml` blueprint included).

Required environment variables:
- `APP_USERNAME`, `APP_PASSWORD` — site login
- `SECRET_KEY` — Flask session secret
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM` — outbound email
- `ANTHROPIC_API_KEY` — per-clinic AI synopsis generation
- `DB_PATH` — set to `/var/data/dashboard.db` in production
