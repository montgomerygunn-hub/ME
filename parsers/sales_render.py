"""
Massage Envy — Gunn Group FDA/Manager Sales Dashboard: HTML rendering.
This is the build_html() function from the original sales_dashboard.py
script, unchanged in output.
"""

from collections import defaultdict
from datetime import datetime

from .sales_parser import CLINIC_ORDER, POOR_THRESHOLD, LTV


def build_html(employees, month_label, date_range, prev_month, prev_run_date, prev_clinic_ltv):
    generated = datetime.now().strftime("%B %d, %Y %I:%M %p")
    same_month = employees[0]["same_month"] if employees else False

    def delta(cur, prev, is_pct=False, higher_good=True):
        if prev is None:
            return '<span class="d-none">—</span>'
        diff = cur - prev
        if diff == 0:
            return '<span class="d-flat">→ 0</span>'
        label = f"{'+' if diff>0 else ''}{diff*100:.1f}pp" if is_pct else f"{'+' if diff>0 else ''}{diff}"
        good  = (diff > 0) == higher_good
        cls   = "d-up" if good else "d-dn"
        arrow = "↑" if diff > 0 else "↓"
        return f'<span class="{cls}">{arrow} {label}</span>'

    def close_cls(v):
        if v == 0.0:  return 'bg-zero'
        if v >= 0.20: return 'bg-g'
        if v >= 0.15: return 'bg-y'
        return 'bg-r'

    clinic_data = defaultdict(lambda: {'total_guests': 0, 'poor_guests': 0, 'poor_memb': 0})
    for e in employees:
        c = e['clinic']
        clinic_data[c]['total_guests'] += e['guests']
        if e['close'] < POOR_THRESHOLD:
            clinic_data[c]['poor_guests'] += e['guests']
            clinic_data[c]['poor_memb']   += e['memb']

    exposure_rows = ""
    for clinic in CLINIC_ORDER:
        d = clinic_data[clinic]
        if d['total_guests'] == 0: continue
        poor_pct = d['poor_guests'] / d['total_guests'] * 100
        missed   = max(0, round(d['poor_guests'] * 0.20) - d['poor_memb'])
        ltv_loss = missed * LTV
        exp_cls  = 'exp-hi' if poor_pct >= 70 else ('exp-md' if poor_pct >= 40 else 'exp-lo')

        prev_ltv = prev_clinic_ltv.get(clinic)
        if prev_ltv is not None:
            ltv_diff = ltv_loss - prev_ltv
            if ltv_diff < 0:
                ltv_delta = f'<span class="d-up">↓ ${abs(ltv_diff):,.0f}</span>'
            elif ltv_diff > 0:
                ltv_delta = f'<span class="d-dn">↑ +${ltv_diff:,.0f}</span>'
            else:
                ltv_delta = '<span class="d-flat">→ no change</span>'
        else:
            ltv_delta = '<span class="d-none">—</span>'

        exposure_rows += f"""
        <tr>
          <td class="td-loc">{clinic}</td>
          <td class="td-num">{d['total_guests']}</td>
          <td class="td-num">{d['poor_guests']}</td>
          <td class="td-num {exp_cls}">{poor_pct:.0f}%</td>
          <td class="td-num miss">{missed}</td>
          <td class="td-num ltv">${ltv_loss:,.0f}</td>
        </tr>"""

    main_rows = ""
    for e in employees:
        parts = e['name'].split(', ')
        display_name = f"{parts[1]} {parts[0]}" if len(parts) == 2 else e['name']
        flag      = e['guests'] >= 20 and e['close'] < POOR_THRESHOLD
        row_cls   = ' class="flag-row"' if flag else ''
        flag_icon = ' <span class="flag-icon">▲ COACHING OPP</span>' if flag else ''
        new_badge = ' <span class="new-badge">NEW</span>' if e['is_new'] else ''

        main_rows += f"""
        <tr{row_cls}>
          <td class="td-loc">{e['clinic']}</td>
          <td class="td-emp">{display_name}{flag_icon}{new_badge}</td>
          <td class="td-num">{e['guests']}</td>
          <td class="td-num">{delta(e['guests'], e['prev_guests'])}</td>
          <td class="td-num">{e['memb']}</td>
          <td class="td-num">{delta(e['memb'], e['prev_memb'])}</td>
          <td class="td-num {close_cls(e['close'])}">{e['close']*100:.2f}%</td>
          <td class="td-num">{delta(e['close'], e['prev_close'], is_pct=True)}</td>
        </tr>"""

    tot_guests      = sum(e['guests'] for e in employees)
    tot_memb        = sum(e['memb']   for e in employees)
    tot_close       = tot_memb / tot_guests if tot_guests else 0
    tot_poor_guests = sum(d['poor_guests'] for d in clinic_data.values())
    tot_poor_pct    = tot_poor_guests / tot_guests * 100 if tot_guests else 0
    tot_missed      = sum(max(0, round(d['poor_guests']*0.20)-d['poor_memb']) for d in clinic_data.values())
    tot_ltv         = tot_missed * LTV

    if not prev_month:
        prior_note = "First run — no prior data. Changes will appear next run."
    elif same_month:
        prior_note = f"Changes shown vs. run on {prev_run_date} ({prev_month}) — week over week"
    else:
        prior_note = f"Changes shown vs. {prev_month} (month over month)"

    css = """
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;background:#f5f5f3;padding:1.2rem;-webkit-print-color-adjust:exact;print-color-adjust:exact}
    h1{font-size:16px;font-weight:700;color:#1a3a5c;background:#b8d4f0;padding:8px 12px;border-radius:4px 4px 0 0;margin-bottom:0}
    h2{font-size:13px;font-weight:700;color:#fff;background:#b85c00;padding:7px 12px;margin:1.2rem 0 0}
    .sub{font-size:12px;color:#888;margin:6px 0 0}
    .prior-note{font-size:11px;color:#aaa;font-style:italic;margin:4px 0 1rem}
    .wrap{max-width:1150px}
    table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #aaa;margin-bottom:1.4rem}
    thead tr{background:#1a3a5c;color:#fff}
    th{font-size:11px;font-weight:600;padding:7px 10px;text-align:center;border:1px solid #888;white-space:nowrap}
    th.th-loc{text-align:left;width:18%}
    th.th-emp{text-align:left;width:16%}
    th.th-delta{color:#aaa;font-weight:400}
    td{font-size:12px;padding:5px 10px;border:1px solid #ccc}
    td.td-loc{text-align:left;color:#1a3a5c;font-weight:500}
    td.td-emp{text-align:left}
    td.td-num{text-align:right}
    tbody tr:nth-child(even){background:#f2f6fc}
    .bg-g{background:#4caf50;color:#fff;font-weight:600}
    .bg-y{background:#ffd600;color:#333;font-weight:600}
    .bg-r{background:#f44336;color:#fff;font-weight:600}
    .bg-zero{background:#000;color:#fff;font-weight:800;letter-spacing:1px}
    tfoot tr{background:#1a3a5c;color:#fff;font-weight:700}
    tfoot td{border:1px solid #888;text-align:right;font-size:12px}
    tfoot td.td-loc{text-align:left}
    .exp-hi{background:#f44336;color:#fff;font-weight:700}
    .exp-md{background:#ffd600;color:#333;font-weight:700}
    .exp-lo{background:#4caf50;color:#fff;font-weight:700}
    .miss{color:#c0392b;font-weight:700}
    .ltv{color:#7b0000;font-weight:800;font-size:13px}
    .flag-row{background:#fff3e0 !important;border-left:4px solid #e65100}
    .flag-row td{border-bottom:1px solid #f5c07a}
    .flag-icon{font-size:9px;font-weight:700;color:#e65100;margin-left:6px;vertical-align:middle;white-space:nowrap}
    .new-badge{font-size:9px;font-weight:700;color:#fff;background:#1a6eb5;padding:1px 5px;border-radius:3px;margin-left:5px;vertical-align:middle}
    .d-up{color:#2a7d2e;font-weight:700;font-size:11px}
    .d-dn{color:#c0392b;font-weight:700;font-size:11px}
    .d-flat{color:#aaa;font-size:11px}
    .d-none{color:#ccc;font-size:11px}
    .legend{font-size:11px;color:#666;margin-bottom:.5rem;font-style:italic}
    .generated{font-size:11px;color:#aaa;text-align:right;margin-top:1rem}
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ME Sales Dashboard — {month_label}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">

<h1>Employee Hours Sales Summary — {month_label}</h1>
<div class="sub">{date_range} &nbsp;·&nbsp; Close rate goal: ≥20% &nbsp;·&nbsp; Coaching flag threshold: &lt;15%</div>
<div class="prior-note">{prior_note}</div>

<h2>⚠ Clinic Exposure — Guest Visits at Risk of No Sale</h2>
<table>
  <thead>
    <tr>
      <th class="th-loc">Clinic</th>
      <th>Total Guests Seen</th>
      <th>Guests w/ &lt;15% Closers</th>
      <th>% of Guest Visits at Risk</th>
      <th>Memberships Left on Table*</th>
      <th>Lifetime Revenue at Risk**</th>
    </tr>
  </thead>
  <tbody>{exposure_rows}</tbody>
  <tfoot>
    <tr>
      <td class="td-loc">PORTFOLIO TOTAL</td>
      <td>{tot_guests}</td>
      <td>{tot_poor_guests}</td>
      <td>{tot_poor_pct:.0f}%</td>
      <td>{tot_missed}</td>
      <td>${tot_ltv:,.0f}</td>
    </tr>
  </tfoot>
</table>
<p class="legend">* Memberships left on table = guests seen by sub-15% closers × 20% target − memberships they actually sold</p>
<p class="legend">** Lifetime revenue at risk = memberships left on table × $80/month × 18 months average member lifetime</p>

<h2>📋 Individual Performance — Sorted by Closing Rate</h2>
<p class="legend" style="margin-top:8px">▲ COACHING OPP = 20+ guests seen with close rate below 15% &nbsp;·&nbsp; <span style="background:#1a6eb5;color:#fff;padding:1px 5px;border-radius:3px;font-style:normal">NEW</span> = not in prior run this month</p>
<table>
  <thead>
    <tr>
      <th class="th-loc">Location</th>
      <th class="th-emp">Employee</th>
      <th>Guests Seen</th>
      <th class="th-delta">Δ Guests</th>
      <th>Memberships Sold</th>
      <th class="th-delta">Δ Memb</th>
      <th>Close Rate</th>
      <th class="th-delta">Δ Close Rate</th>
    </tr>
  </thead>
  <tbody>{main_rows}</tbody>
  <tfoot>
    <tr>
      <td class="td-loc" colspan="2">PORTFOLIO TOTAL</td>
      <td>{tot_guests}</td>
      <td></td>
      <td>{tot_memb}</td>
      <td></td>
      <td>{tot_close*100:.2f}%</td>
      <td></td>
    </tr>
  </tfoot>
</table>

<p class="generated">Generated {generated}</p>
</div>
</body>
</html>"""
