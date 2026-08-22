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

### 2. Deploy the API (Railway or Fly)
1. New service from this repo, root `apps/api` (the Dockerfile is picked up automatically).
2. Set every variable from `.env.example`.
3. Note the public URL — you need `https://<host>/webhook` for Meta.
4. Check `https://<host>/health` returns `{"ok": true, "db": true}`.

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
*"Got it — invoice received and saved…"*, and in Supabase: one row in `wa_messages` (in),
one `documents` row with `sha256` + `storage_path`, the image in the `documents` bucket,
one `jobs` row `done`, one `wa_messages` (out). Send the same message content again —
count stays the same. Send a text — you get the onboarding reply.

Then tick the M0 boxes in `plan.md` and commit.
