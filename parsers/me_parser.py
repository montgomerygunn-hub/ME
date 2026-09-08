"""
Massage Envy — Gunn Group Clinic Dashboard: parsing + rendering.
Extracted from the original me_dashboard.py CLI script, with the CLI-only
bits (input() prompts, sys.exit) removed. Web app calls these functions
directly and manages goals/history via the database instead of a local
.json file and stdin prompts.
"""

import re
import requests
import pandas as pd
from datetime import datetime

# ── CLINIC ORDER ──────────────────────────────────────────────────────────────

CLINIC_NAMES = [
    "Katy", "The Woodlands", "Copperfield", "Market Street",
    "Gleannloch Farms", "Cypress", "West Katy"
]

CLINIC_MAP = {
    "Cypress (0157)":              "Cypress",
    "Katy (0040)":                 "Katy",
    "Market Street (0124)":        "Market Street",
    "The Woodlands (0059)":        "The Woodlands",
    "Gleannloch Farms (0131)":     "Gleannloch Farms",
    "Copperfield (0106)":          "Copperfield",
    "West Katy-Firethorne (1223)": "West Katy",
}

EXCLUDE = {"FM 1960 Eldridge (1368)"}

DEFAULT_GOALS = {
    "gift_card": 1500,
    "retail": 3000,
    "service_hours": 1000,
    "memberships": 25,
}


def default_goals_for_all_clinics(prior_goals=None):
    """Build a goals dict for every clinic, using prior month's values as
    defaults where available, falling back to DEFAULT_GOALS otherwise."""
    prior_goals = prior_goals or {}
    goals = {}
    for clinic in CLINIC_NAMES:
        d = prior_goals.get(clinic, {})
        goals[clinic] = {
            "gift_card":     d.get("gift_card", DEFAULT_GOALS["gift_card"]),
            "retail":        d.get("retail", DEFAULT_GOALS["retail"]),
            "service_hours": d.get("service_hours", DEFAULT_GOALS["service_hours"]),
            "memberships":   d.get("memberships", DEFAULT_GOALS["memberships"]),
        }
    return goals


# ── MEMBER BASE FALLBACK (Sheet1 daily grain) ─────────────────────────────────

def get_latest_member_base(path):
    """
    Sheet2's 'Totals for Date Range' rollup reports Total/Active/Frozen/Suspended
    Member Base as 0 for every clinic when the report covers a partial/in-progress
    month -- those fields are point-in-time snapshots and can't be summed across
    days, so ME's export leaves them blank until the month closes.
    Sheet1's daily grain rows are unaffected. This pulls Total/Active/Frozen/
    Suspended Member Base from the most recent date present in Sheet1's daily
    rows, per clinic, as a reliable substitute.
    Returns: dict of {clinic_full_name: (total, active, frozen, suspended)}
    """
    raw = pd.read_excel(path, sheet_name="Sheet1", header=None)

    header_row_idx = None
    for i in range(len(raw)):
        row_vals = [str(v) for v in raw.iloc[i].tolist() if pd.notna(v)]
        if any("LocationName/Total" in v for v in row_vals):
            header_row_idx = i
            break
    if header_row_idx is None:
        return {}

    header = raw.iloc[header_row_idx]
    col_map = {}
    for col_idx, val in enumerate(header):
        if pd.isna(val):
            continue
        label = str(val).replace("\n", " ").strip()
        if label == "Date":
            col_map["date"] = col_idx
        elif "LocationName/Total" in label:
            col_map["location"] = col_idx
        elif "Consolidated Total" in label and "Member Base" in label:
            col_map["total_mb"] = col_idx
        elif "Consolidated Active" in label and "Member Base" in label:
            col_map["active_mb"] = col_idx
        elif "Consolidated Frozen" in label and "Member Base" in label:
            col_map["frozen_mb"] = col_idx
        elif "Consolidated Suspended" in label and "Member Base" in label:
            col_map["suspended_mb"] = col_idx

    required = ("date", "location", "total_mb", "active_mb", "frozen_mb", "suspended_mb")
    if not all(k in col_map for k in required):
        return {}

    daily = raw.iloc[header_row_idx + 1:].copy()
    daily[col_map["date"]] = pd.to_datetime(daily[col_map["date"]], errors="coerce").ffill()
    daily = daily.rename(columns={col_map["date"]: "_date"})
    daily = daily.dropna(subset=["_date"])
    if daily.empty:
        return {}

    dates_desc = sorted(daily["_date"].unique(), reverse=True)
    result = {}
    for candidate_date in dates_desc:
        candidate_rows = daily[daily["_date"] == candidate_date]
        candidate_result = {}
        for _, row in candidate_rows.iterrows():
            loc = str(row[col_map["location"]]).strip()
            if loc in ("Total", "nan", "None"):
                continue
            try:
                candidate_result[loc] = (
                    float(row[col_map["total_mb"]]),
                    float(row[col_map["active_mb"]]),
                    float(row[col_map["frozen_mb"]]),
                    float(row[col_map["suspended_mb"]]),
                )
            except (ValueError, TypeError):
                continue
        if any(v[0] != 0 for v in candidate_result.values()):
            result = candidate_result
            break

    return result


def peek_report_month(path):
    """Quickly detect the report's month label without full parsing."""
    df_peek = pd.read_excel(path, sheet_name="Sheet2", header=None)
    date_str = str(df_peek.iloc[3, 1])
    match = re.search(r"(\d+/\d+/\d+)", date_str)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%m/%d/%Y").strftime("%B %Y")


def parse_report(path, prev, goals):
    """
    prev: dict keyed by clinic name -> {active_mb, suspend_pct, inactive_pct}
          (i.e. last month's saved snapshot, same shape as the old
          me_dashboard_prev.json)
    goals: dict keyed by clinic name -> {gift_card, retail, service_hours, memberships}
    """
    df = pd.read_excel(path, sheet_name="Sheet2", header=None)
    latest_mb = get_latest_member_base(path)

    date_str = str(df.iloc[3, 1])
    match = re.search(r"(\d+/\d+/\d+) through (\d+/\d+/\d+)", date_str)
    if not match:
        raise ValueError(f"Could not parse date range from: {date_str}")
    start_dt = datetime.strptime(match.group(1), "%m/%d/%Y")
    end_dt   = datetime.strptime(match.group(2), "%m/%d/%Y")

    if start_dt.month == 12:
        next_month = datetime(start_dt.year + 1, 1, 1)
    else:
        next_month = datetime(start_dt.year, start_dt.month + 1, 1)
    days_in_month = (next_month - datetime(start_dt.year, start_dt.month, 1)).days
    days_into     = (end_dt - start_dt).days + 1
    pace          = days_into / days_in_month
    month_label   = start_dt.strftime("%B %Y")

    clinics = []
    for row_idx in range(8, 16):
        if row_idx >= len(df):
            break
        row = df.iloc[row_idx]
        loc = str(row[3]).strip()
        if loc in EXCLUDE or loc not in CLINIC_MAP:
            continue
        name  = CLINIC_MAP[loc]
        g     = goals.get(name, {})
        total_mb  = float(row[5])
        active_mb = float(row[6])
        suspended = float(row[8])

        if total_mb == 0 and active_mb == 0 and loc in latest_mb:
            total_mb, active_mb, frozen_mb, suspended = latest_mb[loc]

        inactive  = total_mb - active_mb
        memberships_sold = int(row[20]) if pd.notna(row[20]) else 0
        guest_count      = int(row[19]) if pd.notna(row[19]) else 0
        close_rate = memberships_sold / guest_count if guest_count else 0

        p = prev.get(name, {})
        clinics.append({
            "name":             name,
            "total_mb":         total_mb,
            "active_mb":        active_mb,
            "prev_active_mb":   p.get("active_mb", active_mb),
            "suspended":        suspended,
            "inactive":         inactive,
            "gift_card":        float(row[12]) if pd.notna(row[12]) else 0,
            "retail":           float(row[13]) if pd.notna(row[13]) else 0,
            "service_hours":    float(row[18]) if pd.notna(row[18]) else 0,
            "guest_count":      guest_count,
            "memberships_sold": memberships_sold,
            "close_rate":       close_rate,
            "goals":            g,
            "prev_suspend":     p.get("suspend_pct"),
            "prev_inactive":    p.get("inactive_pct"),
        })

    return clinics, pace, days_into, days_in_month, month_label, end_dt


def snapshot_for_history(clinics, goals, month_label):
    """Build the {clinic_name: {...}} snapshot saved after each month's run,
    consumed as `prev` on the following month's parse_report() call."""
    snap = {"_goals_month": month_label, "_goals": goals}
    for c in clinics:
        snap[c["name"]] = {
            "active_mb":    int(c["active_mb"]),
            "suspend_pct":  round(c["suspended"] / c["total_mb"] * 100, 4) if c["total_mb"] else 0,
            "inactive_pct": round(c["inactive"]  / c["total_mb"] * 100, 4) if c["total_mb"] else 0,
        }
    return snap


# ── AI SYNOPSES ────────────────────────────────────────────────────────────────

def generate_clinic_synopses(clinics, pace, days_into, days_in_month, month_label, api_key):
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — no AI synopsis was generated.")

    days_remaining = days_in_month - days_into

    clinic_summaries = []
    for c in clinics:
        g = c["goals"]
        susp_pct  = c["suspended"] / c["total_mb"] * 100 if c["total_mb"] else 0
        inact_pct = c["inactive"]  / c["total_mb"] * 100 if c["total_mb"] else 0
        member_delta = int(c["active_mb"]) - int(c["prev_active_mb"])

        def pacing_status(actual, goal):
            t = goal * pace
            if actual >= t: return "AHEAD"
            if actual >= t * 0.90: return "CLOSE (within 10%)"
            return "BEHIND"

        clinic_summaries.append(f"""
{c['name']}:
  Active members: {int(c['active_mb'])} ({'+' if member_delta >= 0 else ''}{member_delta} vs prior)
  Gift card sales: ${c['gift_card']:,.0f} vs ${g.get('gift_card',0):,} goal — {pacing_status(c['gift_card'], g.get('gift_card',1))}
  Retail sales: ${c['retail']:,.0f} vs ${g.get('retail',0):,} goal — {pacing_status(c['retail'], g.get('retail',1))}
  Service hours: {c['service_hours']:,.0f} vs {g.get('service_hours',0):,} goal — {pacing_status(c['service_hours'], g.get('service_hours',1))}
  Memberships sold: {c['memberships_sold']} vs {g.get('memberships',0)} goal — {pacing_status(c['memberships_sold'], g.get('memberships',1))}
  Close rate: {c['close_rate']*100:.1f}% (goal ≥20%)
  Suspend %: {susp_pct:.2f}% (goal ≤2%)
  Inactive %: {inact_pct:.2f}% (goal ≤4%)
  Guest count: {c['guest_count']}""")

    prompt = f"""You are analyzing the monthly performance dashboard for Brett Gunn, owner of 7 Massage Envy franchise clinics in the Houston area (Gunn Group).

Report: {month_label} | Data through day {days_into} of {days_in_month} ({round(pace*100)}% of month reported, {days_remaining} days remaining)

CLINIC DATA:
{''.join(clinic_summaries)}

For EACH clinic, write a concise 2-3 sentence synopsis that appears directly below that clinic's KPI table. Focus on:
- What's working or not working at THIS clinic specifically
- The 1-2 most important things to know or act on
- Any standout metrics (good or bad)

Keep each synopsis tight and clinic-specific. Do NOT summarize across clinics or make portfolio-level observations — those belong in a separate portfolio summary. Be direct and numbers-grounded. No fluff. Only cite figures that appear explicitly in the data provided above — do not infer, estimate, or fabricate benchmarks or averages not directly present in the data.

Respond ONLY with a JSON object where each key is the exact clinic name and the value is the synopsis string. Example format:
{{"Katy": "Synopsis here.", "The Woodlands": "Synopsis here."}}

Clinic names to use exactly: {[c['name'] for c in clinics]}"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"AI synopsis request failed to reach Anthropic: {e}") from e

    if resp.status_code != 200:
        # Surface the API's own error body -- e.g. "invalid x-api-key" -- rather
        # than swallowing it, so a bad/missing ANTHROPIC_API_KEY is diagnosable
        # from the app instead of only showing up in server logs.
        raise RuntimeError(f"AI synopsis request failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError(f"AI synopsis response wasn't valid JSON: {text[:300]}")

    import json as _json
    return _json.loads(match.group(0))
