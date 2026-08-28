# Faida web

The public waitlist landing page plus the review screen and invoice list (plan.md M3).
Next.js App Router + TypeScript + Tailwind, deployable to Vercel untouched.

## Run it

```bash
cd apps/web
npm install
npm run dev        # public landing page at http://localhost:3000
```

The waitlist form sends requests to a same-origin Next.js route.
That server route forwards only the submitted JSON to FastAPI, so database credentials and the private service URL never reach the browser.
Set the backend URL in `apps/web/.env.local` when it is not running on the default port:

```bash
FAIDA_API_URL=http://127.0.0.1:8000
```

The FastAPI service persists normalized email addresses in `waitlist_signups` and gives new and duplicate signups the same response.
The table has row-level security enabled with no public policy, making the endpoint write-only to anonymous visitors.

With no invoice environment variables set, the invoice review experience runs in **mock mode**: an in-memory dataset of three invoices (all green, amber fields, cash hold) served through the same typed client the real API uses.
Edits and confirms persist for the browser session and reset on reload.

## Talking to the real API

The client implements the C6 contract (plan.md section 7.2).
To point it at the real backend, set:

```bash
NEXT_PUBLIC_MOCK_API=false                   # mock unless this is the exact string "false"
NEXT_PUBLIC_API_BASE=http://localhost:8000   # the FastAPI service, no trailing slash
NEXT_PUBLIC_API_TOKEN=<shared-secret>        # demo bearer token (API_TOKEN on the API side); real auth is M7
FAIDA_API_URL=http://localhost:8000          # server-only: the waitlist proxy target (easy to miss - not NEXT_PUBLIC_)
```

All three `NEXT_PUBLIC_*` values are inlined into the JS bundle at build time: changing one requires a rebuild, and the token is readable by anyone who loads the deployed site (accepted C6 demo posture, closed in M7).
Mock mode is the default whenever the env vars are absent.
The switch lives in `src/lib/api.ts`; nothing else in the app knows which mode it is in.
Deploying to Vercel: root directory `apps/web`, the four variables above set for Production, and the API's `WEB_ORIGIN` must equal the deployed origin exactly (see the root README).

## Rules this app holds

- Money values are strings end to end: rendered verbatim, padded to two decimals by string operations, never parsed to a float (plan.md section 3).
- Colour never carries meaning alone: every green/amber state pairs an icon with a plain-language label.
- English only, no jargon, sentence case.
- Brand tokens (Date Palm, Karak Gold, Warm Cream) come from `Docs/brand/faida-brand-guidelines.md` and live in `src/app/globals.css`.

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run build
```
