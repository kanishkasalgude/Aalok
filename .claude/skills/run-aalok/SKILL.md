---
name: run-aalok
description: Run the Aalok AI Commerce Platform — FastAPI backend + browser-driven frontend with chromium-cli
---

# Run Aalok

Aalok is a multi-merchant AI-native commerce orchestration platform built for Razorpay's AI Buildathon. The backend is FastAPI + SQLite; the frontend is a static single-page app served from the same server.

**The UI is one screen.** There is no router and there are no hash routes — `http://localhost:8000` is the whole app. It opens on the "Just ask Aalok" landing, becomes a conversation once you ask something, and surfaces the cart + authorization receipt in a right-side drawer. The Overview/Discover/Merchants/Orders/Payments/Analytics/Audit/Settings dashboards were removed from the interface; their APIs still run and are still tested. See README.md.

## Prerequisites

```bash
pip install -r requirements.txt
```

On Windows with Python restrictions, add `--break-system-packages` if needed:
```bash
pip install -r requirements.txt --break-system-packages
```

## Build

No build step — the project runs from source. The frontend is served as static files by the FastAPI backend.

## Run (agent path)

Use `chromium-cli` to launch and drive the app:

```bash
chromium-cli --script=<(cat <<'EOF'
{
  "targets": [
    {
      "host": "127.0.0.1",
      "port": 8000,
      "type": "page"
    }
  ],
  "onConnect": [
    "send_command",
    "open_url http://localhost:8000",
    "sleep 2",
    "take_screenshot /tmp/aalok-home.png"
  ]
}
EOF
) &

# Start the server in the background
cd "C:\MY\MYPROJECTS\Aalok"
python -m uvicorn backend.main:app --reload --port 8000

# Wait for server to be ready, then let chromium-cli drive it
sleep 3
# chromium-cli will connect and execute the script above
```

**Key commands for chromium-cli:**

- `take_screenshot <path>` — save a PNG screenshot
- `open_url <url>` — navigate to a URL
- `evaluate <js>` — run JavaScript and capture output
- `click_selector <selector>` — click an element
- `type_text <text>` — type into focused input
- `wait <ms>` — pause execution

**Screenshots land in the path you specify** — use a consistent location like `/tmp/aalok-*.png` for test artifacts.

### Testing the full flow

1. Launch the server in one terminal:
   ```bash
   cd "C:\MY\MYPROJECTS\Aalok"
   python -m uvicorn backend.main:app --reload --port 8000
   ```

2. Open `http://localhost:8000` in your browser (or script it with chromium-cli as shown above).

3. Interact with the one screen:
   - **Landing** — type or speak a request into "Just ask Aalok", or click a suggestion chip
   - **Conversation** — the agent's reply plus product cards from every merchant, inline. Requires `GEMINI_API_KEY` for the real LLM path; falls back to deterministic heuristics otherwise
   - **Cart drawer** — opens on add-to-cart, or via the Cart button in the header
   - **Checkout** — the drawer shows the payment result and the full authorization/policy receipt
   - **Demos** — "see the policy engine reject a cart" (under the composer), "Simulate a failed payment" (in the cart drawer, next to Checkout), and the **Demo Control Panel** ("Demo" button in the header) — one-click Successful Purchase / Budget Rejection / Cart Tampering / Payment Failure / Payment Retry / External AI Buyer / Upsell Accepted / Upsell Declined scenarios, each a real backend call
   - **Sessions** — every browser tab gets a signed, expiring session token minted automatically on first request (`POST /api/session`, `backend/services/session/auth.py`); no login step

## Run (human path)

1. Copy `.env.example` to `.env` (already done in this repo):
   ```bash
   cp .env.example .env
   ```

2. Optionally set `GEMINI_API_KEY` (from https://aistudio.google.com/apikey) for real LLM-driven agent; leave blank to use deterministic fallbacks.

3. Optionally set `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (Test Mode keys from Razorpay Dashboard) for real payment integration; runs in mock mode otherwise.

4. Start the server:
   ```bash
   python -m uvicorn backend.main:app --reload --port 8000
   ```

5. Open `http://localhost:8000` — that root URL is the entire frontend. There are no other pages and no hash routes.

## Test

Run the full test suite:
```bash
python -m pytest tests/ -v
```

Expected: **145 tests passing**. Covers:
- Commerce Policy Engine (mandate validation, spend/time/diet bounds)
- Authorization layer
- Cart service lifecycle
- Federated catalog search
- Payment idempotency (retry reuses same Razorpay order)
- Razorpay signature verification
- Refund idempotency
- AI tool boundary (LLM cannot reach payment/DB symbols)
- Security boundaries
- External AI buyer reference client
- Growth experiment benchmark
- Read-only order/refund/analytics aggregates (no longer rendered by any screen, still routed and tested)

Run a single test file to isolate failures:
```bash
python -m pytest tests/test_mandates.py -v
```

## Gotchas

1. **No GEMINI_API_KEY → deterministic fallback.** The agent works without it. Set the env var to enable the real Gemini LLM path; everything falls back to regex/keyword heuristics + rule-based recommendation if it's unset or the API call times out. This is intentional — the project was tested both ways.

2. **Mock payment mode by default.** Without `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`, all payment flows run offline with synthetic responses. The header chip shows `Mock payments` in that case. Set `PAYMENT_PROVIDER=razorpay_test` with real keys to enable Checkout.js + real Test Mode Orders API.

3. **SQLite database file.** By default, `backend/aalok.db` (or per `DATABASE_URL` in `.env`). Gets created on first run. If you reset state, delete the `.db` file and restart the server.

4. **Port 8000 must be free.** The quick start assumes `--port 8000` is available. If 8000 is in use, pass a different port and navigate to `http://localhost:<port>`.

5. **Reload mode watches file changes.** The `--reload` flag in the quick start makes uvicorn restart on source changes. Useful for dev; for a stable deployment, omit `--reload`.

6. **AI Agent requires latency tolerance.** When `GEMINI_API_KEY` is set, the agent makes real API calls which may take 2–5 seconds. The UI handles timeouts gracefully — a failed request shows an error message and falls back to heuristics. The agent is not real-time chat; expect brief delays between message and response.

## Troubleshooting

### `ModuleNotFoundError: No module named 'fastapi'`
Missing dependencies. Run:
```bash
pip install -r requirements.txt
```

### `Address already in use` on port 8000
Another process is using port 8000. Either:
- Kill the existing process: `lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9` (Linux/Mac)
- Use a different port: `python -m uvicorn backend.main:app --reload --port 8001`

### Agent returns `"I couldn't reach the commerce agent just then"`
No `GEMINI_API_KEY` set, or the API call timed out. Check `.env`:
```bash
grep GEMINI_API_KEY .env
```
If it's empty or unset, that's expected — the system falls back to deterministic heuristics. To enable the LLM:
1. Get a free key from https://aistudio.google.com/apikey
2. Add `GEMINI_API_KEY=<your-key>` to `.env`
3. Restart the server

### Payment flow shows `Razorpay API call failed`
`PAYMENT_PROVIDER=razorpay_test` is set but keys are missing. Either:
- **Use mock mode (offline):** remove `PAYMENT_PROVIDER` or set `PAYMENT_PROVIDER=mock`, restart
- **Use real Test Mode:** add test keys (`rzp_test_*`) to `.env` from Razorpay Dashboard → Settings → API Keys, restart

The app fails loudly, never silently drops to mock mode mid-demo.

### `/api/audit` or other API endpoints return empty/404
Check that the server is running:
```bash
curl -s http://localhost:8000/api/audit | head
```
If no response, restart the server.

### Database locked / "database is locked" error
SQLite doesn't support concurrent writes well. If running multiple processes:
- Close all but one uvicorn instance
- Or switch to Postgres (not in scope for this project)

### Browser page is blank after navigation
`http://localhost:8000` is the only page. If it renders blank:
1. Verify the server is running: `curl -s http://localhost:8000 | head -5`
2. Check browser console for JS errors (F12 → Console tab)
3. Hard-refresh: `Ctrl+Shift+R` (or Cmd+Shift+R on Mac)

### Tests fail with database errors
The test suite uses a separate in-memory SQLite database (see `tests/conftest.py`). If tests fail with "cannot lock database":
- Stop any running dev server: `pkill -f "uvicorn backend.main"`
- Run tests in isolation: `python -m pytest tests/test_mandates.py -v`

---

**All paths relative to the project root** (C:\MY\MYPROJECTS\Aalok on this machine).
