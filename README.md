# Faida

Profit visibility for GCC cafeterias and multi-branch chains, fed through WhatsApp.

- **`plan.md`** — the live build plan. Read it first; update it in the same commit as your change.
- **`Docs/PRD.md`** — product intent.

```
apps/api    FastAPI backend: WhatsApp webhook, job worker, (M1+) extraction pipeline
apps/web    Next.js review screen, raw-material mapping (M5), dashboard (later)
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
| `API_TOKEN` | the review screen's shared secret (`openssl rand -hex 32`); empty fail-closes every `/api` route. Must equal the web deploy's `NEXT_PUBLIC_API_TOKEN` |
| `WEB_ORIGIN` | the deployed web origin, scheme+host only, no trailing slash (e.g. `https://faida-web.vercel.app`). CORS allows exactly this one origin; a leftover `http://localhost:3000` from `.env` silently breaks the deployed review screen |

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
| Meta logs the event but nothing reaches the service at all | the app is not subscribed to the WABA - see Meta step 6 |
| A `POST /webhook` appears in the logs with **403** | signature rejected - re-copy `META_APP_SECRET` |
| Ack never arrives, no error on the phone | access token expired - check `expires_at` per Meta step 3 |
| `{"ok":true,"db":false}` | `DATABASE_URL` wrong: brackets, password, or transaction pooler |

Cost is roughly $5/month for an always-on service.

**Deploy the web app (Vercel).**
Create the Vercel project with **Root Directory** `apps/web` (standalone npm project, stock `next build`, no monorepo config).
Set four Production environment variables: `NEXT_PUBLIC_MOCK_API=false` (the exact string), `NEXT_PUBLIC_API_BASE` (the Railway host, `https://`, no trailing slash), `NEXT_PUBLIC_API_TOKEN` (same value as Railway's `API_TOKEN`), and `FAIDA_API_URL` (the Railway host again; server-only, powers the waitlist proxy - forgetting it silently 503s every signup).
The three `NEXT_PUBLIC_*` values are baked into the bundle at build time, so any change to them needs a redeploy; the token is readable in the shipped JS (accepted C6 demo posture until M7).
Then set `WEB_ORIGIN` on Railway to the Vercel production origin - preview deployments will fail CORS by design, demo from the production URL only.

### 3. Meta WhatsApp Cloud API (free test number)
1. developers.facebook.com → Create app → type **Business** → add the **WhatsApp** product.
2. WhatsApp → API setup: note the **Phone number ID** and the **WhatsApp Business Account (WABA) ID**.
3. Generate a **permanent** access token, not the temporary one.
   Use *Step 2. Production setup → Send message → Generate token*, or Business settings → Users →
   System users with expiration **Never** and scopes `whatsapp_business_messaging` +
   `whatsapp_business_management`.
   The dashboard's *Step 1 → Generate token* button issues a **24-hour** token that expires on a
   fixed boundary - it can die in under two hours, and every symptom of an expired token is
   silence on the phone rather than an error anywhere you would think to look.
   Verify with `expires_at: 0`:

   ```bash
   curl -s "https://graph.facebook.com/v26.0/debug_token?input_token=$TOKEN&access_token=$TOKEN" \
     | python3 -m json.tool     # expires_at: 0  means never expires
   ```
4. App settings → Basic: copy the **App secret** (signature verification fails closed without it).
5. WhatsApp → Configuration → Webhook: callback URL `https://<host>/webhook`,
   verify token = your `META_VERIFY_TOKEN` value → Verify and save → subscribe to the
   **messages** webhook field.
6. **Subscribe the app to the WABA. This is a separate step and the dashboard never mentions it.**

   ```bash
   curl -X POST "https://graph.facebook.com/v26.0/<WABA_ID>/subscribed_apps" \
     -H "Authorization: Bearer $META_ACCESS_TOKEN"          # -> {"success": true}

   curl -s "https://graph.facebook.com/v26.0/<WABA_ID>/subscribed_apps" \
     -H "Authorization: Bearer $META_ACCESS_TOKEN"          # your app must appear here
   ```

   Configuring the callback URL in step 5 tells the *app* where to deliver. It does not tell the
   *WhatsApp Business Account* to route anything to your app. Until this POST runs, the only
   subscriber is Meta's own `WA DevX Webhook Events 1P App`, so real forwards are recorded in the
   dashboard's "Check test webhooks" panel and delivered nowhere. The dashboard's **Test** button
   still works, because that is a direct app-level delivery that bypasses WABA routing - which
   makes this failure look like a signature or deploy problem for as long as you are willing to
   chase it.

   You do **not** need to publish the app or complete business verification for this. Publishing
   is an M5 concern (plan.md §11).
7. API setup → add the demo phone(s) as recipients (up to 5) and confirm the code sent to them.

### 4. Prove M0 (the "done when")
From a demo phone, send any photo to the test number. Within seconds you should get
*"Got it — invoice received and saved…"*.
With `ANTHROPIC_API_KEY` set, a second reply follows once extraction finishes; without it that
second reply is the failure message, since the pipeline job has no provider.
In Supabase: one row in `wa_messages` (in),
one `documents` row with `sha256` + `storage_path`, the image in the `documents` bucket,
one `jobs` row `done`, one `wa_messages` (out). Send the same message content again —
count stays the same. Send a text — you get the onboarding reply.

Note on the dashboard **Test** button: Meta's sample payload carries a **fixed** message id, so the
first press stores a row and every later press is correctly skipped as a duplicate. A success
notification with no new row therefore proves dedupe, not delivery. Use it once, then trust only a
real forward.

Then tick the M0 boxes in `plan.md` and commit.
