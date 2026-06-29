#!/usr/bin/env python3
"""
The Boss 2026 — World Cup morning agent.

Each morning it:
  1. Loads your bets (bets.json).
  2. Fetches yesterday's finished World Cup matches from football-data.org.
  3. Scores them against your predictions (HIT/MISS on sign and exact result).
  4. Builds a brief for today's matches (facts + one AI context line each).
  5. Posts the whole thing to your Slack webhook.

Points are intentionally NOT calculated (odds aren't reliably available).
Run it daily — manually or via cron / Task Scheduler.

Required environment variables (see .env.example):
  FOOTBALL_DATA_TOKEN   football-data.org API token (free tier)
  SLACK_WEBHOOK_URL     Slack incoming webhook URL
  ANTHROPIC_API_KEY     (optional) for the one-line game context; omit to skip
"""

import os
import sys
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import datetime as dt
from pathlib import Path

import requests

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Stockholm")
except Exception:
    TZ = None

BASE = Path(__file__).resolve().parent
FD_BASE = "https://api.football-data.org/v4"
# football-data competition code for the men's World Cup is "WC".
COMPETITION = "WC"
# Last morning brief date: covers through the final Round of 16 match (4 Jul 03:30).
LAST_BRIEF_DATE = dt.date(2026, 7, 4)


# ---------------------------------------------------------------------------
# Team-name mapping: your Excel is in Swedish, the API returns English names.
# Only teams in your bets need to map. Extend if the API uses other spellings.
# ---------------------------------------------------------------------------
SV_TO_EN = {
    "Mexiko": "Mexico", "Sydafrika": "South Africa", "Sydkorea": "South Korea",
    "Tjeckien": "Czechia", "Kanada": "Canada", "Bosnien-Herzegovina": "Bosnia-Herzegovina",
    "Bosnien Hercegovina": "Bosnia-Herzegovina",
    "USA": "United States", "Paraguay": "Paraguay", "Qatar": "Qatar", "Schweiz": "Switzerland",
    "Brasilien": "Brazil", "Marocko": "Morocco", "Haiti": "Haiti", "Skottland": "Scotland",
    "Australien": "Australia", "Turkiet": "Turkey", "Tyskland": "Germany", "Curacao": "Curaçao",
    "Nederländerna": "Netherlands", "Japan": "Japan", "Elfenbenskusten": "Ivory Coast",
    "Ecuador": "Ecuador", "Sverige": "Sweden", "Tunisien": "Tunisia", "Spanien": "Spain",
    "Kap Verde": "Cape Verde Islands", "Belgien": "Belgium", "Egypten": "Egypt",
    "Saudiarabien": "Saudi Arabia", "Uruguay": "Uruguay", "Iran": "Iran",
    "Nya Zeeland": "New Zealand", "Frankrike": "France", "Senegal": "Senegal",
    "Irak": "Iraq", "Norge": "Norway", "Argentina": "Argentina", "Algeriet": "Algeria",
    "Österrike": "Austria", "Jordanien": "Jordan", "Portugal": "Portugal",
    "DR Kongo": "Congo DR", "England": "England", "Kroatien": "Croatia", "Ghana": "Ghana",
    "Panama": "Panama", "Uzbekistan": "Uzbekistan", "Colombia": "Colombia",
}
EN_TO_SV = {v: k for k, v in SV_TO_EN.items()}


def load_bets():
    return json.loads((BASE / "bets.json").read_text(encoding="utf-8"))


def sign_from_score(h, a):
    if h > a:
        return "1"
    if h < a:
        return "2"
    return "X"


def fetch_finished(token, day):
    """Matches that finished on the given date (UTC date string YYYY-MM-DD)."""
    headers = {"X-Auth-Token": token}
    url = f"{FD_BASE}/competitions/{COMPETITION}/matches"
    params = {"dateFrom": day, "dateTo": day, "status": "FINISHED"}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("matches", [])


def fetch_scheduled(token, date_from, date_to):
    headers = {"X-Auth-Token": token}
    url = f"{FD_BASE}/competitions/{COMPETITION}/matches"
    params = {"dateFrom": date_from, "dateTo": date_to}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return [m for m in r.json().get("matches", [])
            if m.get("status") in ("SCHEDULED", "TIMED")]


def find_bet(bets, home_en, away_en):
    """Match an API fixture to one of your bets via the name map."""
    hs = EN_TO_SV.get(home_en, home_en)
    as_ = EN_TO_SV.get(away_en, away_en)
    for m in bets["matches"]:
        if m["home"] == hs and m["away"] == as_:
            return m
    return None


def ai_context_line(home_en, away_en):
    """One short context sentence. Returns '' if no API key configured."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return ""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 80,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"In ONE short sentence (max 20 words), give context for the "
                        f"2026 World Cup group-stage match {home_en} vs {away_en}. "
                        f"No preamble, just the sentence."
                    ),
                }],
            },
            timeout=30,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
    except Exception:
        return ""


def build_results_section(bets, finished):
    lines = []
    if not finished:
        return ["_No finished matches reported for last night._"]
    for m in finished:
        home_en = m["homeTeam"]["name"]
        away_en = m["awayTeam"]["name"]
        ft = m["score"]["fullTime"]
        h, a = ft.get("home"), ft.get("away")
        if h is None or a is None:
            continue
        bet = find_bet(bets, home_en, away_en)
        hs = EN_TO_SV.get(home_en, home_en)
        as_ = EN_TO_SV.get(away_en, away_en)
        line = f"*{hs} {h}–{a} {as_}*"
        if bet:
            actual_sign = sign_from_score(h, a)
            sign_hit = (bet["sign"] == actual_sign)
            result_hit = (bet["pred_home"] == h and bet["pred_away"] == a)
            sign_mark = "✅" if sign_hit else "❌"
            res_mark = "✅" if result_hit else "❌"
            line += (f"\n    your pick: {bet['pred_home']}–{bet['pred_away']} "
                     f"({bet['sign']})  ·  sign {sign_mark}  ·  exact result {res_mark}")
            s_sign = bet.get("stake_sign")
            s_res = bet.get("stake_result")
            if s_sign is not None or s_res is not None:
                stake_parts = []
                if s_sign is not None:
                    stake_parts.append(f"{s_sign} on sign")
                if s_res is not None:
                    stake_parts.append(f"{s_res} on result")
                line += f"\n    stake: {', '.join(stake_parts)}"
        else:
            line += "\n    _(no matching bet found)_"
        lines.append(line)
    return lines


def build_today_section(bets, scheduled, local_today):
    lines = []
    if not scheduled:
        return ["_No matches scheduled for today._"]
    for m in scheduled:
        home_en = m["homeTeam"]["name"]
        away_en = m["awayTeam"]["name"]
        ko = m.get("utcDate", "")
        ko_label = ko
        try:
            d = dt.datetime.fromisoformat(ko.replace("Z", "+00:00"))
            if TZ:
                d = d.astimezone(TZ)
            ko_label = d.strftime("%H:%M")
            # Mark early-hours kickoffs that fall on the next calendar day locally
            if d.date() > local_today:
                ko_label += " _(natt)_"
        except Exception:
            pass
        hs = EN_TO_SV.get(home_en, home_en)
        as_ = EN_TO_SV.get(away_en, away_en)
        bet = find_bet(bets, home_en, away_en)
        line = f"*{ko_label}*  {hs} – {as_}"
        if bet:
            line += f"\n    your pick: {bet['pred_home']}–{bet['pred_away']} ({bet['sign']})"
            s_sign = bet.get("stake_sign")
            s_res = bet.get("stake_result")
            if s_sign is not None or s_res is not None:
                stake_parts = []
                if s_sign is not None:
                    stake_parts.append(f"{s_sign} on sign")
                if s_res is not None:
                    stake_parts.append(f"{s_res} on result")
                line += f"\n    stake: {', '.join(stake_parts)}"
        ctx = ai_context_line(home_en, away_en)
        if ctx:
            line += f"\n    _{ctx}_"
        lines.append(line)
    return lines


def post_to_slack(webhook, text):
    r = requests.post(webhook, json={"text": text}, timeout=30)
    r.raise_for_status()


def main():
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not token or not webhook:
        sys.exit("Set FOOTBALL_DATA_TOKEN and SLACK_WEBHOOK_URL (see .env.example).")

    bets = load_bets()
    # Use Stockholm time for "today" so the cutoff is consistent with display times.
    today = dt.datetime.now(TZ).date() if TZ else dt.date.today()
    if today > LAST_BRIEF_DATE:
        print("Group stage complete — no bets loaded for this date, skipping.")
        sys.exit(0)
    yesterday = today - dt.timedelta(days=1)

    # Late kickoffs (e.g. 04:00 CET) finish on the calendar day after their
    # listed date, so check both yesterday and today (UTC) for finished games.
    finished = []
    for d in (yesterday, today):
        try:
            finished += fetch_finished(token, d.isoformat())
        except Exception as e:
            print(f"warn: finished fetch {d}: {e}", file=sys.stderr)
    # de-dup
    seen, uniq = set(), []
    for m in finished:
        if m["id"] not in seen:
            seen.add(m["id"]); uniq.append(m)
    finished = uniq

    # Fetch scheduled matches from today through tomorrow, then cut off at
    # tomorrow 06:00 Stockholm time — this captures tonight's late/post-midnight
    # kickoffs (e.g. 04:00 CET) that sit on tomorrow's UTC calendar date.
    tomorrow = today + dt.timedelta(days=1)
    if TZ:
        cutoff_utc = dt.datetime(tomorrow.year, tomorrow.month, tomorrow.day,
                                 6, 0, tzinfo=TZ).astimezone(dt.timezone.utc)
    else:
        cutoff_utc = dt.datetime(tomorrow.year, tomorrow.month, tomorrow.day,
                                 5, 0, tzinfo=dt.timezone.utc)
    try:
        scheduled = fetch_scheduled(token, today.isoformat(), tomorrow.isoformat())
        scheduled = [m for m in scheduled
                     if dt.datetime.fromisoformat(
                         m["utcDate"].replace("Z", "+00:00")) <= cutoff_utc]
        scheduled.sort(key=lambda m: m["utcDate"])
    except Exception as e:
        print(f"warn: scheduled fetch: {e}", file=sys.stderr)
        scheduled = []

    parts = []
    parts.append(f":soccer: *The Boss 2026 — {today.strftime('%A %d %B')}*")
    parts.append("")
    parts.append("*— Last night's results —*")
    parts += build_results_section(bets, finished)
    parts.append("")
    parts.append("*— Today's games —*")
    parts += build_today_section(bets, scheduled, today)
    parts.append("")
    parts.append("_Hits/misses only. Points come from Fredrik's leaderboard email._")

    message = "\n".join(parts)
    post_to_slack(webhook, message)
    print("Posted to Slack.")


if __name__ == "__main__":
    main()
