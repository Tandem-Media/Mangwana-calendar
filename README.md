# WhatsApp Invitation Bot

A WhatsApp-native bot built on Flask and the Wasender gateway. Runs locally with a `config.json` file and deploys to **Railway** via environment variables — no code changes required between environments.

---

## Configuration Priority

The app resolves every value in this order:

| Priority | Source | When used |
|----------|--------|-----------|
| 1 | **Environment variable** | Railway (production) |
| 2 | **`config.json`** | Local development |
| 3 | Hard-coded default | `PORT` only (→ 5000) |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WASENDER_API_KEY` | ✅ **Fatal if missing** | Wasender gateway API key |
| `PHONE_NUMBER_ID` | ✅ **Fatal if missing** | WhatsApp phone number ID |
| `OPENAI_API_KEY` | Optional | OpenAI key for AI-generated replies |
| `GOOGLE_CALENDAR_ID` | Optional | Google Calendar ID for event lookup |
| `PORT` | Optional | HTTP port (Railway injects this automatically) |

---

## Local Development

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd whatsapp-bot

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your local config
cp config.json.example config.json
# Edit config.json and fill in real keys (never commit this file)

# 5. Run
python app.py
```

The startup log will confirm where each value came from:

```
──────────────────────────────────────────────────────────────
  WhatsApp Bot — Configuration Summary
──────────────────────────────────────────────────────────────
  OPENAI_API_KEY         ✔  config.json           sk-loc**************
  WASENDER_API_KEY       ✔  config.json           ws-loc**************
  PHONE_NUMBER_ID        ✔  config.json           1234567890
  GOOGLE_CALENDAR_ID     ✔  config.json           primary
  PORT                   ✔  config.json           5000
──────────────────────────────────────────────────────────────
  Binding on  0.0.0.0:5000
──────────────────────────────────────────────────────────────
```

---

## Railway Deployment

### 1. Push your code

```bash
git add .
git commit -m "feat: Railway-compatible config"
git push origin main
```

### 2. Create a Railway project

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
2. Select your repository.
3. Railway detects the `Procfile` and uses `gunicorn` automatically.

### 3. Set environment variables

In the Railway dashboard, open your service → **Variables** tab, then add:

```
WASENDER_API_KEY   =  <your key>
PHONE_NUMBER_ID    =  <your number id>
OPENAI_API_KEY     =  <your key>          # optional
GOOGLE_CALENDAR_ID =  <your calendar id> # optional
```

> **Do not set `PORT`** — Railway injects it automatically. The app reads it via `os.environ.get("PORT", 5000)`.

### 4. Verify the deployment

Railway exposes a public URL once the deploy succeeds. Hit the health endpoint to confirm everything loaded:

```bash
curl https://<your-service>.up.railway.app/health
```

Expected response:

```json
{
  "status": "ok",
  "config": {
    "host": "0.0.0.0",
    "port": 8080,
    "phone_number_id": "...",
    "google_calendar_id": "...",
    "openai_api_key": true,
    "wasender_api_key": true
  }
}
```

### 5. Webhook URL

Point your Wasender webhook to:

```
https://<your-service>.up.railway.app/webhook
```

---

## Fatal Errors at Startup

If a required variable is missing the app **exits immediately** with a clear message rather than crashing mid-request:

```
  ✖  Required config value is missing: 'WASENDER_API_KEY'
     Set it as an environment variable (Railway → Variables tab)
     or add it to config.json for local development.
```

---

## Project Structure

```
whatsapp-bot/
├── app.py              # Flask app & entry point
├── config.py           # Config loader (env → file → default)
├── config.json.example # Template for local development
├── config.json         # Your local secrets (git-ignored)
├── Procfile            # gunicorn start command for Railway
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Security Notes

- `config.json` is in `.gitignore` — never commit real keys.
- The `/health` endpoint redacts secret values (returns `true`/`false`, not the actual keys).
- Rotate keys immediately if accidentally exposed.
