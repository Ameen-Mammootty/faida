# Faida

Profit visibility for GCC cafeterias and multi-branch chains, fed through WhatsApp.

- **`plan.md`** — the live build plan. Read it first; update it in the same commit as your change.
- **`Docs/PRD.md`** — product intent.

```
apps/api    FastAPI backend: WhatsApp webhook, job worker, (M1+) extraction pipeline
apps/web    Next.js review screen + dashboard (arrives M3)
supabase/   SQL migrations + demo seed
eval/       invoice extraction eval harness (arrives M1)
```

## Local development

```bash
# 1. Postgres (any local instance or Docker)
createdb faida
psql faida -f supabase/migrations/0001_init.sql
psql faida -f supabase/seed.sql          # edit the demo phone first

# 2. API
cd apps/api
pip install -e '.[dev]'
cp ../../.env.example .env               # fill in values
uvicorn faida_api.main:app --reload

# 3. Tests (pure tests always run; flow tests need a DB)
export TEST_DATABASE_URL=postgresql://localhost:5432/faida_test  # gets wiped every test!
pytest
ruff check . && ruff format --check .
```

## M0 setup — one-time, needs your accounts (~1–2 hours)

### 1. Supabase
1. Create a project at supabase.com (region: closest to UAE).
2. SQL editor → run `supabase/migrations/0001_init.sql`, then `supabase/seed.sql`
   (set the branch phone to the demo phone that will forward invoices — digits only, e.g. `9715xxxxxxxx`).
3. Storage → create a **private** bucket named `documents`.
4. Collect: the database connection string (Settings → Database) and the
   `service_role` key + project URL (Settings → API).

### 2. Deploy the API (Railway)

Do this before the Meta step: the webhook configuration needs the deployed URL.
The Dockerfile is the deploy artifact and has been verified to build and boot against the live
Supabase project.

**Create the service.**
Push your branch first, since Railway deploys from the remote, not your working tree.
At railway.app: New Project → Deploy from GitHub repo → pick this repo.
Then open the service's Settings → Source and set **Root Directory** to `apps/api`.
Railway auto-detects the Dockerfile there; you do not need a build command or a start command.
Under Settings → Region, pick the one closest to your Supabase project (Singapore for
`ap-south-1`), so worker-to-Postgres round trips stay short.

**Set the variables.**
Open the Variables tab and use the Raw Editor to paste your local `apps/api/.env` in one go,
then fix up three things:

| Variable | Value |
|---|---|
| `WORKER_ENABLED` | `true` — locally it is often `false`; in production the worker must run |
| `DATABASE_URL` | the session-pooler URI with the real password and **no `[ ]` brackets** |
| `PORT` | do not set it — Railway injects it and the container's CMD already honours it |

Everything else (`SUPABASE_*`, `META_*`, `ANTHROPIC_API_KEY`, `STORAGE_BUCKET`) carries over
from `.env` unchanged.
Keep the service at a single replica for the demo.

**Expose it.**
Settings → Networking → Generate Domain.
That public hostname is what Meta will call.

**Verify before touching Meta.**

```bash
curl https://<host>/health
# {"ok":true,"db":true}   <- db:true means the pooler URI and password are right

curl "https://<host>/webhook?hub.mode=subscribe&hub.verify_token=<META_VERIFY_TOKEN>&hub.challenge=ping"
# ping                    <- echoes the challenge; this is exactly what Meta does on Verify and save
```

If `/health` returns `{"ok":true,"db":false}` the service is up but Postgres is not reachable:
re-check `DATABASE_URL` for leftover brackets, a wrong password, or the transaction pooler
(port 6543) instead of the session pooler.

**Startup timing.**
The container needs 6-10 seconds to bind — pip-installed app plus the asyncpg pool handshake to
Supabase both run before uvicorn listens.
If you configure a health-check path, leave the timeout generous; a check that fires inside that
window will mark a healthy service dead and restart-loop it, which looks exactly like a broken
build.

**Troubleshooting.**

| Symptom | Cause |
|---|---|
| Deploy log stops after `Started server process` | normal — the next line arrives once the DB pool connects |
| Log pane empty | needs `PYTHONUNBUFFERED=1`, already set in the Dockerfile |
| Restart loop, service otherwise fine | health check firing before the 6-10 s bind |
| Meta shows deliveries sent, nothing in `wa_messages` | signature rejected — re-copy `META_APP_SECRET` |
| `{"ok":true,"db":false}` | `DATABASE_URL` wrong: brackets, password, or transaction pooler |

Cost is roughly $5/month for an always-on service.

### 3. Meta WhatsApp Cloud API (free test number)
1. developers.facebook.com → Create app → type **Business** → add the **WhatsApp** product.
2. WhatsApp → API setup: note the **Phone number ID** and a **temporary access token**
   (24 h — fine for day one; create a system-user token before the demo so it doesn't expire mid-run).
3. App settings → Basic: copy the **App secret** (signature verification fails closed without it).
4. WhatsApp → Configuration → Webhook: callback URL `https://<host>/webhook`,
   verify token = your `META_VERIFY_TOKEN` value → Verify and save → subscribe to the
   **messages** webhook field.
5. API setup → add the demo phone(s) as recipients (up to 5) and confirm the code sent to them.

### 4. Prove M0 (the "done when")
From a demo phone, send any photo to the test number. Within seconds you should get
*"Got it — invoice received and saved…"*.
With `ANTHROPIC_API_KEY` set, a second reply follows once extraction finishes; without it that
second reply is the failure message, since the pipeline job has no provider.
In Supabase: one row in `wa_messages` (in),
one `documents` row with `sha256` + `storage_path`, the image in the `documents` bucket,
one `jobs` row `done`, one `wa_messages` (out). Send the same message content again —
count stays the same. Send a text — you get the onboarding reply.

Then tick the M0 boxes in `plan.md` and commit.
