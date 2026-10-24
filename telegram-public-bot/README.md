# Telegram Public Bot on Vercel (Python)

A public Telegram bot that replies automatically to anyone who messages it. It runs as a serverless function on Vercel's free Hobby plan and receives messages through a Telegram **webhook** (no polling process).

## What it does

- Replies to `/start`, `/help`, `/about`
- Greets users by first name
- Answers greetings, thanks, goodbyes, "who are you", "what can you do"
- Replies gracefully to unknown or non-text messages
- Validates every webhook request with a secret token
- Reads credentials only from environment variables

> **No AI is connected.** The bot uses prepared replies and cannot answer arbitrary questions. See [Optional AI integration](#optional-ai-integration).

> **Telegram limitation.** A bot can only respond to people who message **the bot itself** (via its `t.me/<bot_username>` link or search). It cannot detect someone opening your *personal* Telegram profile or private chat. This project never touches personal accounts or their credentials.

## Project structure

```
telegram-public-bot/
├── api/
│   └── webhook.py        # serverless function (POST = Telegram updates, GET = health check)
├── requirements.txt      # requests
├── vercel.json           # function max duration
├── .gitignore
├── .env.example          # variable names only, no real values
└── README.md
```

How the pieces fit: Vercel exposes `api/webhook.py` at **`/api/webhook`**. The file defines a class named `handler`, which is what Vercel's Python runtime looks for. `requirements.txt` installs `requests`, the only import that is not in the standard library. `vercel.json` caps the function at 10 seconds.

---

## 1. Create the bot (BotFather)

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a display name and a username ending in `bot` (e.g. `my_helper_bot`).
3. Copy the **token** (`123456789:AA...`). Treat it like a password.
4. Optional: `/setdescription`, `/setabouttext`, `/setuserpic`, and `/setcommands` with:

   ```
   start - Show the welcome message
   help - Show help
   about - About this bot
   ```

If a token ever leaks, send `/revoke` to BotFather and use the new token.

## 2. Generate a webhook secret

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Allowed characters are `A-Z a-z 0-9 _ -`, length 1–256. Keep this value; you need it in steps 4 and 5.

## 3. Push the code to GitHub

Install [Git](https://git-scm.com/downloads) and create an empty repository on github.com (e.g. `telegram-public-bot`, no README/.gitignore added by GitHub). Then, inside the project folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/telegram-public-bot.git
git push -u origin main
```

Before pushing, confirm no secrets are tracked: `git status` must **not** list `.env`.

## 4. Deploy on Vercel

1. Sign in at [vercel.com](https://vercel.com) with GitHub (free Hobby plan).
2. **Add New → Project**, import `telegram-public-bot`.
3. Framework Preset: **Other**. Leave Build Command and Output Directory empty.
4. Expand **Environment Variables** and add (for Production, Preview and Development):

   | Name | Value |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | token from BotFather |
   | `TELEGRAM_WEBHOOK_SECRET` | secret from step 2 |

5. Click **Deploy**.
6. Open the production URL (e.g. `https://telegram-public-bot.vercel.app`). Your webhook URL is that URL plus `/api/webhook`.
7. Check it: opening `https://<your-project>.vercel.app/api/webhook` in a browser must show `{"status": "ok"}`.

> **Environment variables only apply to new deployments.** If you add or change one later, go to **Deployments → ⋯ → Redeploy**.

If Vercel Deployment Protection is on for production in your project, make sure the production domain is publicly reachable. Telegram cannot send requests through a login wall.

## 5. Register the webhook

Do this once after the first successful deploy, and again if the URL or secret changes. Replace the three values.

**macOS / Linux / Git Bash**

```bash
TOKEN="123456789:AA..."
SECRET="your-webhook-secret"
URL="https://<your-project>.vercel.app/api/webhook"

curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  --data-urlencode "url=${URL}" \
  --data-urlencode "secret_token=${SECRET}" \
  --data-urlencode "allowed_updates=[\"message\"]" \
  --data-urlencode "drop_pending_updates=true"
```

**Windows PowerShell**

```powershell
$TOKEN  = "123456789:AA..."
$SECRET = "your-webhook-secret"
$URL    = "https://<your-project>.vercel.app/api/webhook"

Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$TOKEN/setWebhook" -Body @{
  url = $URL
  secret_token = $SECRET
  allowed_updates = '["message"]'
  drop_pending_updates = "true"
}
```

Expected response: `{"ok":true,"result":true,"description":"Webhook was set"}`

Verify:

```bash
curl -s "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"
```

Look for the right `url`, `pending_update_count` near 0, and no `last_error_message`.

Remove the webhook (e.g. to move hosts): `https://api.telegram.org/bot<TOKEN>/deleteWebhook`

## 6. Get and share the public link

Your bot's public link is:

```
https://t.me/<your_bot_username>
```

Share it anywhere. Anyone who opens it and taps **Start** gets the welcome message. The user does not need to be in your contacts.

## 7. Test

| Send | Expected reply |
|---|---|
| `/start` | Welcome message with your first name and usage hints |
| `/help` | List of commands |
| `/about` | Description; states it is not an AI |
| `hello` | Greeting using your first name |
| `thanks` | "You're welcome!" |
| `asdf qwerty` | "Sorry, I didn't understand that…" |
| a photo or sticker | "I can only read text messages for now…" |

Test the security directly (should return **403**):

```bash
curl -i -X POST "https://<your-project>.vercel.app/api/webhook" \
  -H "Content-Type: application/json" -d '{}'
```

View logs in Vercel: **Project → Logs** (or **Deployments → Functions**).

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Bot never replies; `getWebhookInfo` shows `last_error_message: Wrong response from the webhook: 403` | Secret mismatch. Make `TELEGRAM_WEBHOOK_SECRET` on Vercel equal to the `secret_token` you passed to `setWebhook`, redeploy, then run `setWebhook` again. |
| `500 Internal Server Error` / `server not configured` | `TELEGRAM_BOT_TOKEN` or `TELEGRAM_WEBHOOK_SECRET` is missing. Add it in Vercel and **redeploy**. |
| `404` on `/api/webhook` | `api/webhook.py` is not at the repository root's `api/` folder, or the project's Root Directory setting points elsewhere. |
| `401`/login page from the URL | Vercel Deployment Protection is active for that URL. Use the public production domain or disable protection for production. |
| `setWebhook` returns `Bad Request: bad webhook: HTTPS url must be provided` | URL must start with `https://`. |
| `setWebhook` returns `secret token contains unallowed characters` | Use only `A-Z a-z 0-9 _ -`. |
| `401 Unauthorized` from Telegram in Vercel logs | Wrong bot token. Re-copy it from BotFather (or `/revoke` and use the new one), update Vercel, redeploy. |
| Logs show `Telegram sendMessage returned error 403: bot was blocked by the user` | Normal: that user blocked the bot. Nothing to fix. |
| Build fails: `ModuleNotFoundError: requests` at runtime | `requirements.txt` missing or not at the repo root. |
| Replies are delayed after idle periods | Cold start on a serverless platform. Usually a second or two. |
| Bot silent in groups | Telegram privacy mode: bots in groups only see commands and replies to them unless privacy mode is disabled in BotFather (`/setprivacy`). |
| Changes don't take effect | Push to GitHub and wait for the deployment to finish; env var changes need a redeploy. |

## Free hosting limitations

- **Hobby plan is for personal, non-commercial use.** Commercial use requires a paid plan.
- Usage quotas (function invocations, execution time, bandwidth) are capped. Limits change, so check Vercel's current Hobby limits. A reply bot uses very little, but a very popular bot could exceed them.
- Serverless: **no persistent process and no local file storage.** The bot is stateless; it keeps no conversation history. Storing data would need an external database (many have free tiers).
- Cold starts add occasional latency.
- Telegram retries a webhook delivery if your endpoint returns an error or times out. This bot returns `200` once a valid request is processed, even if sending the reply failed, so a failure won't cause a retry loop.

## Optional AI integration

AI is **not** implemented. The hook is `ai_reply()` in `api/webhook.py`:

- It is called only for messages that match no built-in rule.
- It currently returns `None`, so unknown messages get the "didn't understand" reply.
- To add AI, implement only that function (call your provider with `requests` and return text). Webhook validation and Telegram handling stay untouched.
- Store the provider's API key as a Vercel environment variable (e.g. `AI_API_KEY`), never in code.
- **Cost:** hosted AI APIs are generally paid per use (per token or request); some providers offer limited free tiers that can change. Because the bot is public, anyone can trigger paid calls, so add rate limiting or a spending cap with your provider before enabling it. Keep the call under about 8 seconds.

## Security notes

- Credentials come from environment variables only; `.env` is git-ignored.
- Every POST must carry the `X-Telegram-Bot-Api-Secret-Token` header; it is compared in constant time. Wrong or missing → `403`.
- Malformed requests return `400` (bad JSON/empty body) or `413` (oversized body).
- The token is never logged or returned; logs record only error types and Telegram error codes.
- User-supplied text (first names, AI output) is HTML-escaped before sending.
- The bot ignores messages from other bots.
