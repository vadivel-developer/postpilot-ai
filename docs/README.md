# LearnToPost AI

Turns a YouTube channel's latest video into a fact-checked, editable LinkedIn
post with a branded image — nothing is ever published without an explicit
click on "Publish to LinkedIn".

## How it works (agent pipeline)

1. **Extract** — Playwright drives a real Chromium browser to YouTube's
   transcript panel and scrapes it (there is no official captions API access
   for arbitrary third-party creators, so this is UI automation, not an API
   call). If the panel isn't available (no captions, bot-check, etc.) the
   draft stops here with a clear error and an option to paste a transcript
   manually.
2. **Translate** — Gemini detects the transcript's language and translates
   to English only if needed, preserving segment markers.
3. **Summarize** — Gemini produces a structured summary and key points.
4. **Draft post** — Gemini writes an original LinkedIn post from the
   summary. It is explicitly instructed never to invent personal
   experience, metrics, or achievements, and never to copy long passages
   verbatim from the transcript.
5. **Verify** — Gemini checks the drafted post against the translated
   transcript only. This is a self-consistency check, not independent
   fact-checking — the UI never claims otherwise.
6. **Image copy** — Gemini proposes a short headline and takeaway bullets;
   Pillow renders these onto a branded PNG with measured text layout (font
   size shrinks to fit; content that still can't fit raises an error
   instead of silently overlapping or clipping).

All transcript content is treated as untrusted data throughout the
pipeline — prompts explicitly tell Gemini never to follow instructions that
might appear inside a transcript.

A persistent, DB-backed job queue (not an in-memory queue) runs each of the
above as a background job claimed by a separate worker process, with atomic
claiming, lease expiry, and bounded retries so a crashed worker cannot lose
or duplicate work.

## Project layout

```
learn-to-post-ai/
  backend/    FastAPI app, LangGraph pipeline, SQLAlchemy models, worker
  frontend/   React + TypeScript + Vite + Tailwind dashboard
  docs/       this file
```

## Requirements

- Python 3.12+ (a virtual environment is already set up at
  `backend/.venv`)
- Node.js 20+
- Windows + PowerShell (target environment; Playwright's Chromium build is
  already installed in the backend venv)
- No Docker, no n8n — everything runs as plain local processes

## Running it (PowerShell)

Three processes run independently: the API server, the background worker,
and the frontend dev server.

**1. Backend API**

```powershell
cd D:\claude-project\calude-july\learn-to-post-ai\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**2. Worker** (processes transcript/Gemini/image/publish jobs)

```powershell
cd D:\claude-project\calude-july\learn-to-post-ai\backend
.\.venv\Scripts\Activate.ps1
python -m app.worker.runner
```

**3. Frontend**

```powershell
cd D:\claude-project\calude-july\learn-to-post-ai\frontend
npm install
npm run dev
```

Then open the URL Vite prints (typically `http://localhost:5173`). The
first time you open it you'll be asked to create the owner account
(username + password) — this bootstrap endpoint only works while there is
no owner yet, and the app binds to `127.0.0.1` by default, not `0.0.0.0`,
so it is not exposed on the network unless you explicitly change
`LTP_HOST`.

## Configuring credentials

All secrets are entered through the running app's **Settings** page —
never through `.env`, never through a config file checked into the repo.

- **Settings → Gemini**: paste a Gemini API key (from Google AI Studio),
  pick a model (`gemini-2.5-flash`, `gemini-2.5-pro`, or
  `gemini-2.5-flash-lite`), click **Test Connection** to verify it before
  relying on it. The key is encrypted at rest (Fernet, with the encryption
  key itself sourced from an env var, then the Windows Credential Locker
  via `keyring`, then a git-ignored local file — never plaintext). The key
  is never sent back to the browser once saved; the UI only ever shows a
  masked value.
- **Settings → LinkedIn**: enter your LinkedIn developer app's Client ID
  and Client Secret, then click **Connect LinkedIn** to run the OAuth
  authorization-code flow. A personal-profile connection does not imply
  permission to post to a company page — those are separate LinkedIn API
  scopes/permissions and would need to be requested and tested separately.

## Using it

1. On the Dashboard, enter a YouTube channel name or URL and confirm the
   match.
2. Each date has a card. Click **Generate Post** on today's (or an earlier
   unprocessed) card to start the pipeline for that channel's latest
   unprocessed video. A future-dated card is just a placeholder — it never
   auto-triggers generation or publishing on its own.
3. Watch the card's status update live as the pipeline runs (extracting →
   translating → summarizing → drafting → verifying → image).
4. Once done, review and edit the post text, hashtags, and image headline/
   takeaways directly in the card. Edits are kept as revision history and
   can be restored.
5. If you change the headline/takeaways after the image was generated, the
   image is flagged outdated with a **Regenerate Image** option — it is
   never silently overwritten.
6. Click **Publish to LinkedIn** only when you're ready to actually post.
   This requires a connected LinkedIn account and is the only action in the
   whole app that posts anything externally. Repeat clicks are blocked
   once a publish record exists for that draft (unless it genuinely
   failed), so there is no duplicate-post risk from double-clicking.

## What was verified live in this environment

- **YouTube integration — live-verified.** Channel resolution, latest-
  video discovery via the channel's RSS feed, and full transcript
  extraction were run against the real, public example video from the
  spec (`https://www.youtube.com/watch?v=FAHgiiomd98`) and correctly
  extracted all 86 real transcript segments in Tamil.
- **End-to-end pipeline wiring — live-verified.** From the dashboard,
  resolving a real channel, clicking Generate Post, and watching the job
  reach the worker, attempt transcript extraction, and correctly stop with
  an honest `Gemini is not configured` error (because no Gemini key exists
  in this environment) — with the *other* date's card correctly untouched.
  This confirms discovery → dedup → draft creation → job enqueue → worker
  claim → pipeline execution → status streaming to the UI all work
  correctly together.
- **Gemini generation (translate/summarize/draft/verify/image copy) — NOT
  live-verified.** No Gemini API key was available in this environment.
  The client code is implemented against the official `google-genai` SDK
  with structured-output parsing, retries on invalid JSON, and typed error
  handling, but the actual model calls have not been exercised against a
  real key. Add a key via Settings → Gemini and use **Test Connection**,
  then Generate Post on a card, to complete this verification.
- **LinkedIn OAuth and publishing — NOT live-verified.** No LinkedIn
  developer app credentials were available in this environment. The OAuth
  authorization-code flow and Posts API calls are implemented per
  LinkedIn's official documentation (including the `LinkedIn-Version`
  header and OIDC `/v2/userinfo` for identity), and unknown-outcome
  timeouts are deliberately mapped to a "publication uncertain" status
  rather than blind retries — but none of this has been exercised against
  a real LinkedIn app. Add credentials via Settings → LinkedIn and connect
  an account to complete this verification.
- **Automated tests — all passing, run in this environment just now.**
  - Backend: `pytest` — 35/35 passed (these are mocked-dependency tests:
    Gemini and LinkedIn calls are stubbed, not live network calls; the
    YouTube/Playwright tests specifically exercise real selectors against
    fixture HTML, not a live browser session).
  - Backend: `ruff check` — clean. `mypy app` — clean (0 errors, 33 files).
  - Frontend: `tsc -b` — clean. `eslint .` — clean. `vite build` — succeeds
    (295 KB JS / 18.5 KB CSS bundle).

## Known limitations

- Transcript extraction depends on YouTube's actual (undocumented) DOM and
  will need selector updates if YouTube changes its transcript UI. Not
  every video will have a transcript available (auto-captions disabled,
  bot-check triggered, etc.) — the app surfaces this honestly with a Retry
  and a manual-paste fallback rather than pretending to succeed.
- Gemini and LinkedIn integrations are implemented and unit-tested against
  mocks but have not been exercised against live credentials in this
  environment, as noted above.
- The worker is a single long-running Python process; running the browser
  automation (Playwright) requires the target machine to have Chromium
  installed (already provisioned in `backend/.venv` here), and cannot run
  in a container-less headless-only environment without a display server
  dependency unless launched headless (it already is, by default).
- No CAPTCHA or login bypass is attempted anywhere — if YouTube presents a
  "sign in to confirm you're not a robot" style challenge, extraction
  fails cleanly rather than attempting to work around it.
