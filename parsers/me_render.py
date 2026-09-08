"""
Massage Envy — Gunn Group Clinic Dashboard: HTML rendering.
This is the build_html() function from the original me_dashboard.py script,
unchanged in output — same CSS, same layout, same color thresholds.
"""

from datetime import datetime


def build_html(clinics, pace, days_into, days_in_month, month_label, end_dt, clinic_synopses=None):
    def sum_c(field): return sum(c[field] for c in clinics)
    def sum_g(field): return sum(c["goals"].get(field, 0) for c in clinics)

    gg_active_mb = sum(c["active_mb"] for c in clinics)
    gg_prev_mb   = sum(c["prev_active_mb"] for c in clinics)
    gg_suspended = sum(c["suspended"] for c in clinics)
    gg_inactive  = sum(c["inactive"] for c in clinics)
    gg_guests    = sum(c["guest_count"] for c in clinics)
    gg_memb_sold = sum(c["memberships_sold"] for c in clinics)

    prev_susp_vals = [c["prev_suspend"] for c in clinics if c["prev_suspend"] is not None]
    prev_inact_vals = [c["prev_inactive"] for c in clinics if c["prev_inactive"] is not None]
    gg_prev_susp = sum(prev_susp_vals) / len(prev_susp_vals) if prev_susp_vals else None
    gg_prev_inact = sum(prev_inact_vals) / len(prev_inact_vals) if prev_inact_vals else None

    gg = {
        "name": "Gunn Group (All Clinics)",
        "total_mb":         sum_c("total_mb"),
        "active_mb":        gg_active_mb,
        "prev_active_mb":   gg_prev_mb,
        "suspended":        gg_suspended,
        "inactive":         gg_inactive,
        "gift_card":        sum_c("gift_card"),
        "retail":           sum_c("retail"),
        "service_hours":    sum_c("service_hours"),
        "guest_count":      gg_guests,
        "memberships_sold": gg_memb_sold,
        "close_rate":       gg_memb_sold / gg_guests if gg_guests else 0,
        "goals": {
            "gift_card":     sum_g("gift_card"),
            "retail":        sum_g("retail"),
            "service_hours": sum_g("service_hours"),
            "memberships":   sum_g("memberships"),
        },
        "prev_suspend":  gg_prev_susp,
        "prev_inactive": gg_prev_inact,
        "is_group": True,
    }

    pace_pct = round(pace * 100)

    css = """
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f3;color:#1a1a18;padding:1.5rem;-webkit-print-color-adjust:exact;print-color-adjust:exact}
    h1{font-size:18px;font-weight:500;margin-bottom:2px}
    .sub{font-size:12px;color:#888;margin-bottom:1rem}
    .pace-wrap{background:#efefed;border-radius:8px;padding:8px 14px;margin-bottom:1rem;display:flex;align-items:center;gap:12px;max-width:900px}
    .pace-label{font-size:12px;color:#666;white-space:nowrap}
    .pace-track{flex:1;height:6px;background:#d0d0cc;border-radius:3px;overflow:hidden}
    .pace-fill{height:100%;background:#1a6eb5;border-radius:3px}
    .pace-pct{font-size:12px;font-weight:500;color:#1a6eb5;white-space:nowrap}
    .card{background:#fff;border:1px solid #ddd;border-radius:8px;margin-bottom:14px;overflow:hidden;max-width:900px}
    .card.group{border:2px solid #1a6eb5}
    .card-hdr{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;border-bottom:1px solid #e5e5e5;background:#f9f9f7}
    .card.group .card-hdr{background:#e6f1fb}
    .card-name{font-size:14px;font-weight:600}
    .card.group .card-name{color:#1a6eb5;font-size:15px}
    .card-meta{font-size:12px;color:#888}
    .arr-up-good{color:#2a7d2e;font-weight:700}
    .arr-dn-bad{color:#c0392b;font-weight:700}
    .arr-up-bad{color:#c0392b;font-weight:700}
    .arr-dn-good{color:#2a7d2e;font-weight:700}
    .delta-pos{font-size:11px;font-weight:600;color:#2a7d2e}
    .delta-neg{font-size:11px;font-weight:600;color:#c0392b}
    .legend{display:flex;gap:14px;flex-wrap:wrap;padding:6px 14px;border-bottom:1px solid #e5e5e5;background:#f9f9f7}
    .leg{display:flex;align-items:center;gap:5px;font-size:11px;color:#888}
    .leg-box{width:11px;height:11px;border-radius:2px;display:inline-block}
    table{width:100%;border-collapse:collapse;table-layout:fixed}
    th{font-size:11px;color:#888;font-weight:400;text-align:right;padding:6px 12px 4px;border-bottom:1px solid #e5e5e5;background:#fafaf8}
    th:first-child{text-align:left}
    td{font-size:12px;padding:6px 12px;border-bottom:1px solid #eee;text-align:right;vertical-align:middle}
    td:first-child{text-align:left;color:#666}
    tr:last-child td{border-bottom:none}
    .g{background:#c8edc0}.y{background:#ffe599}.r{background:#f4a89a}
    .t-g{color:#2a7d2e;font-weight:600}.t-y{color:#854f0b;font-weight:600}.t-r{color:#c0392b;font-weight:600}
    .badge{font-size:10px;padding:2px 7px;border-radius:4px;font-weight:600;display:inline-block}
    .b-g{background:#d5f5e3;color:#1e8449}.b-y{background:#fef9e7;color:#9a7d0a}.b-r{background:#fadbd8;color:#c0392b}
    .dir{display:flex;align-items:center;justify-content:flex-end;gap:4px}
    .divider{border:none;border-top:2px solid #ddd;margin:1.5rem 0 1rem;max-width:900px}
    .generated{font-size:11px;color:#aaa;margin-top:1rem;max-width:900px;text-align:right}
    .clinic-synopsis{font-size:12px;color:#444;line-height:1.65;padding:10px 14px;border-top:1px solid #eee;background:#fafaf8}
    .history-nav{max-width:900px;margin-bottom:1rem;font-size:12px}
    .history-nav select{font-size:12px;padding:4px 8px;border-radius:6px;border:1px solid #ccc}
    """

    legend_html = """
    <div class="legend">
      <span class="leg"><span class="leg-box" style="background:#c8edc0;border:1px solid #5aab47"></span>Ahead of pace / at benchmark</span>
      <span class="leg"><span class="leg-box" style="background:#ffe599;border:1px solid #d4a800"></span>Within 10% of pace (recoverable)</span>
      <span class="leg"><span class="leg-box" style="background:#f4a89a;border:1px solid #d94f3d"></span>More than 10% behind pace</span>
    </div>"""

    def fmt_d(v): return f"${round(v):,}"
    def fmt_n(v): return f"{round(v):,}"
    def fmt_pct(v): return f"{v:.2f}%"

    def cell_cls(actual, goal):
        t = goal * pace
        if actual >= t: return "g"
        if actual >= t * 0.90: return "y"
        return "r"

    def gap_d(actual, goal):
        t = goal * pace
        diff = actual - t
        cls = "t-g" if diff >= 0 else ("t-y" if actual >= t * 0.90 else "t-r")
        return f'<span class="{cls}">{"+" if diff>=0 else ""}{fmt_d(diff)}</span>'

    def gap_n(actual, goal):
        t = goal * pace
        diff = actual - t
        cls = "t-g" if diff >= 0 else ("t-y" if actual >= t * 0.90 else "t-r")
        return f'<span class="{cls}">{"+" if diff>=0 else ""}{round(diff)}</span>'

    def dir_arrow_bad_up(cur, prev):
        if prev is None: return '<span style="color:#aaa">—</span>'
        if cur > prev:   return '<span class="arr-up-bad">&#8593;</span>'
        if cur < prev:   return '<span class="arr-dn-good">&#8595;</span>'
        return '<span style="color:#aaa">&#8594;</span>'

    def member_arrow(cur, prev):
        delta = cur - prev
        if delta > 0: return f'<span class="arr-up-good">&#8593;</span> <span class="delta-pos">+{delta}</span>'
        if delta < 0: return f'<span class="arr-dn-bad">&#8595;</span> <span class="delta-neg">{delta}</span>'
        return '<span style="color:#aaa;font-size:11px">no change</span>'

    def close_badge(r):
        pct = f"{r*100:.1f}%"
        if r >= 0.20: return f'<span class="badge b-g">{pct}</span>'
        if r >= 0.16: return f'<span class="badge b-y">{pct}</span>'
        return f'<span class="badge b-r">{pct}</span>'

    def render_card(c):
        g = c["goals"]
        susp_pct  = c["suspended"] / c["total_mb"] * 100 if c["total_mb"] else 0
        inact_pct = c["inactive"]  / c["total_mb"] * 100 if c["total_mb"] else 0
        susp_cls  = "g" if susp_pct <= 2.0 else "r"
        card_cls  = "card group" if c.get("is_group") else "card"
        mb_delta  = member_arrow(int(c["active_mb"]), int(c["prev_active_mb"]))

        rows = f"""
        <tr>
          <td>Gift card sales</td><td>{fmt_d(g.get("gift_card",0))}</td>
          <td class="{cell_cls(c['gift_card'],g.get('gift_card',1))}">{fmt_d(c['gift_card'])}</td>
          <td class="{cell_cls(c['gift_card'],g.get('gift_card',1))}">{gap_d(c['gift_card'],g.get('gift_card',1))}</td>
        </tr>
        <tr>
          <td>Retail sales</td><td>{fmt_d(g.get("retail",0))}</td>
          <td class="{cell_cls(c['retail'],g.get('retail',1))}">{fmt_d(c['retail'])}</td>
          <td class="{cell_cls(c['retail'],g.get('retail',1))}">{gap_d(c['retail'],g.get('retail',1))}</td>
        </tr>
        <tr>
          <td>Service hours</td><td>{fmt_n(g.get("service_hours",0))}</td>
          <td class="{cell_cls(c['service_hours'],g.get('service_hours',1))}">{fmt_n(c['service_hours'])}</td>
          <td class="{cell_cls(c['service_hours'],g.get('service_hours',1))}">{gap_n(c['service_hours'],g.get('service_hours',1))}</td>
        </tr>
        <tr>
          <td>Memberships sold</td><td>{fmt_n(g.get("memberships",0))}</td>
          <td class="{cell_cls(c['memberships_sold'],g.get('memberships',1))}">{fmt_n(c['memberships_sold'])}</td>
          <td class="{cell_cls(c['memberships_sold'],g.get('memberships',1))}">{gap_n(c['memberships_sold'],g.get('memberships',1))}</td>
        </tr>
        <tr>
          <td>Suspend %</td>
          <td style="text-align:left;color:#aaa;font-size:11px">goal &le;2.0%</td>
          <td class="{susp_cls}">{fmt_pct(susp_pct)} ({int(c['suspended'])})</td>
          <td class="{susp_cls}"><div class="dir">{f"{c['prev_suspend']:.2f}% prev" if c['prev_suspend'] else ""} {dir_arrow_bad_up(susp_pct,c['prev_suspend'])}</div></td>
        </tr>
        <tr>
          <td>Inactive %</td>
          <td style="text-align:left;color:#aaa;font-size:11px">goal &le;4.0%</td>
          <td>{fmt_pct(inact_pct)} ({int(c['inactive'])})</td>
          <td><div class="dir">{f"{c['prev_inactive']:.2f}% prev" if c['prev_inactive'] else ""} {dir_arrow_bad_up(inact_pct,c['prev_inactive'])}</div></td>
        </tr>
        <tr>
          <td>Close rate</td>
          <td style="text-align:left;color:#aaa;font-size:11px">goal &ge;20%</td>
          <td colspan="2" style="text-align:right">{close_badge(c['close_rate'])} &nbsp; {int(c['memberships_sold'])} sold / {int(c['guest_count'])} guests</td>
        </tr>
        <tr>
          <td>Guest count</td>
          <td style="text-align:left;color:#aaa;font-size:11px">—</td>
          <td colspan="2" style="text-align:right;font-weight:600">{fmt_n(c['guest_count'])}</td>
        </tr>"""

        synopsis_html = ""
        if clinic_synopses and not c.get("is_group"):
            synopsis_text = clinic_synopses.get(c['name'], "")
            if synopsis_text:
                synopsis_html = f'<div class="clinic-synopsis">{synopsis_text}</div>'

        return f"""
        <div class="{card_cls}">
          <div class="card-hdr">
            <span class="card-name">{c['name']}</span>
            <span class="card-meta">
              Active members: <strong>{fmt_n(c['active_mb'])}</strong> {mb_delta}
              &nbsp;·&nbsp; Total base: {fmt_n(c['total_mb'])}
            </span>
          </div>
          {legend_html}
          <table>
            <thead>
              <tr>
                <th style="width:35%">KPI</th>
                <th style="width:20%">Monthly goal</th>
                <th style="width:20%">Actual</th>
                <th style="width:25%">Gap to pace</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
          {synopsis_html}
        </div>"""

    clinic_cards = "\n".join(render_card(c) for c in clinics)
    group_card   = render_card(gg)
    generated    = datetime.now().strftime("%B %d, %Y %I:%M %p")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ME Dashboard — {month_label}</title>
  <style>{css}</style>
</head>
<body>
  <h1>Massage Envy — {month_label} Scorecard</h1>
  <div class="sub">Data through {end_dt.month}/{end_dt.day} &nbsp;·&nbsp; {days_into} of {days_in_month} days reported ({pace_pct}%) &nbsp;·&nbsp; Portal data: {month_label}</div>
  <div class="pace-wrap">
    <span class="pace-label">Days reported this month</span>
    <div class="pace-track"><div class="pace-fill" style="width:{pace_pct}%"></div></div>
    <span class="pace-pct">{pace_pct}%</span>
  </div>
  {clinic_cards}
  <hr class="divider">
  {group_card}
  <p class="generated">Generated {generated}</p>
</body>
</html>"""
