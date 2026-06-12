# The Boss 2026 — Morning Agent

A small Python agent you run on your own machine (via Claude Code in VS Code).
Every morning it fetches last night's World Cup results, checks them against your
bets (hit/miss on sign and exact result — no points), briefs today's games, and
posts it all to Slack.

## Files
- `bets.json` — your 72 group predictions + 8 special bets (already filled in from your Excel).
- `agent.py` — the agent.
- `.env.example` — template for your secrets.
- `requirements.txt` — Python dependencies.

## What you need (≈10 minutes)

### 1. Python deps
```
pip install -r requirements.txt
```

### 2. football-data.org token (free)
Register at https://www.football-data.org/client/register — you'll get a token by email.
Free tier covers the World Cup; if scorer/lineup detail is thin, that's the tier's limit.

### 3. Slack incoming webhook
- In Slack: create (or pick) a channel for the feed, e.g. `#vm-2026`.
- Go to https://api.slack.com/apps → **Create New App** → *From scratch*.
- Add feature **Incoming Webhooks** → toggle **On** → **Add New Webhook to Workspace**
  → pick your channel → copy the webhook URL.

### 4. Configure secrets
```
cp .env.example .env
```
Fill in `FOOTBALL_DATA_TOKEN` and `SLACK_WEBHOOK_URL`. Leave `ANTHROPIC_API_KEY`
blank unless you want the one-line AI context per game (then paste a key from
https://console.anthropic.com).

The agent reads real environment variables. Easiest: load the .env before running, e.g.
```
export $(grep -v '^#' .env | xargs)
python agent.py
```

### 5. Run it
```
python agent.py
```
Check Slack — the brief should appear.

## Automate the morning run

**macOS / Linux (cron)** — run 07:30 daily:
```
30 7 * * * cd /path/to/world-cup-agent && export $(grep -v '^#' .env | xargs) && /usr/bin/python3 agent.py >> agent.log 2>&1
```

**Windows** — Task Scheduler → daily 07:30 → action: run `python agent.py` in this folder
(set the env vars in the task, or wrap it in a small `.bat`).

## Things to ask Claude Code to help with
- Verify the football-data competition code is `WC` once the tournament feed is live
  (run a quick test fetch; adjust `COMPETITION` in `agent.py` if needed).
- If any team name fails to match, add it to `SV_TO_EN` in `agent.py`
  (the brief will print `(no matching bet found)` when that happens).
- Later: add a second output that posts into the WhatsApp biktbås group.
- Before each knockout round, paste the new fixtures so we extend `bets.json`.

## Deliberately out of scope
- **Points/odds**: not calculated. ATG/Bet365 odds are frozen at kickoff and not in any
  free API, so the agent shows hits/misses only; your real standings come from
  Fredrik's leaderboard email.
