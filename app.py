import os
import ssl
import smtplib
import json
import tempfile
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file

import db
from parsers import me_parser, sales_parser
from parsers.me_render import build_html as build_me_html
from parsers.sales_render import build_html as build_sales_html

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-change-me")

def load_app_users():
    """
    APP_USERS format: "user1:pass1,user2:pass2,..."
    Falls back to the old single APP_USERNAME/APP_PASSWORD pair if APP_USERS
    isn't set, so existing deployments keep working.
    """
    raw = os.environ.get("APP_USERS")
    if raw:
        users = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            user, _, pw = pair.partition(":")
            users[user.strip()] = pw.strip()
        return users

    legacy_user = os.environ.get("APP_USERNAME")
    legacy_pass = os.environ.get("APP_PASSWORD")
    if legacy_user and legacy_pass:
        return {legacy_user: legacy_pass}
    return {}


APP_USERS = load_app_users()

ME_EMAIL_TO = [
    "brett.gunn@massageenvy.com",
    "steven.nacol@massageenvy.com",
    "tommie.bennight@massageenvy.com",
    "steven.smith@massageenvy.com",
    "krystle.green@massageenvy.com",
    "gabby.queener@massageenvy.com",
    "callie.morris@massageenvy.com",
    "beth.webster@massageenvy.com",
    "becky.ober@massageenvy.com",
]
SALES_EMAIL_TO = ME_EMAIL_TO
SALES_EMAIL_SUBJECT = "FDA/Manager Sales Report"

db.init_db()


# ── AUTH ────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username in APP_USERS and APP_USERS[username] == password:
            session["logged_in"] = True
            session["username"] = username
            return redirect(request.args.get("next") or url_for("index"))
        flash("Invalid username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── HELPERS ──────────────────────────────────────────────────────────────────

def month_sort_key(month_label):
    return datetime.strptime(month_label, "%B %Y").strftime("%Y-%m")


def send_dashboard_email(html_body, subject, to_list, pdf_path=None):
    smtp_server = os.environ.get("SMTP_SERVER", "secure.emailsrvr.com")
    smtp_port   = int(os.environ.get("SMTP_PORT", 465))
    username    = os.environ.get("SMTP_USERNAME")
    password    = os.environ.get("SMTP_PASSWORD")
    email_from  = os.environ.get("EMAIL_FROM", username)

    if not username or not password:
        raise RuntimeError("SMTP_USERNAME / SMTP_PASSWORD not configured")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = email_from
    msg["To"]      = ", ".join(to_list)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html_body, "html"))
    msg.attach(alt)

    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
        pdf_attachment.add_header("Content-Disposition", "attachment", filename=Path(pdf_path).name)
        msg.attach(pdf_attachment)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(username, password)
        server.sendmail(email_from, to_list, msg.as_string())


def generate_pdf(html_str, pdf_path):
    from playwright.sync_api import sync_playwright
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html_str)
        tmp_html = f.name
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file:///{tmp_html.replace(chr(92), '/')}")
            page.wait_for_load_state("networkidle")
            page.pdf(
                path=pdf_path,
                format="Letter",
                print_background=True,
                margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"},
            )
            browser.close()
    finally:
        os.unlink(tmp_html)


# ── ROUTES ───────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return redirect(url_for("me_dashboard"))


@app.route("/me")
@login_required
def me_dashboard():
    month = request.args.get("month")
    report = db.get_report("me", month) if month else db.get_latest_report("me")
    months = db.list_months("me")

    if not report:
        return render_template("me_dashboard.html", html=None, months=months, selected_month=None)

    clinics = report["data"].get("clinics") or []
    if not clinics:
        # Seed-only row (e.g. imported prior-month history/goals with no full
        # report generated) -- nothing to render, but still selectable in history.
        return render_template("me_dashboard.html", html=None, months=months,
                                selected_month=report["month_label"], seed_only=True)

    html = build_me_html(
        clinics, report["pace"], report["days_into"], report["days_in_month"],
        report["month_label"], datetime.fromisoformat(report["end_date"]),
        report.get("synopses"),
    )
    return render_template("me_dashboard.html", html=html, months=months, selected_month=report["month_label"])


@app.route("/me/upload", methods=["GET", "POST"])
@login_required
def me_upload():
    if request.method == "GET":
        return render_template("me_upload.html")

    file = request.files.get("report_file")
    if not file or not file.filename:
        flash("Please choose the Scorecard Datamart .xlsx file.")
        return redirect(url_for("me_upload"))

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        report_month = me_parser.peek_report_month(tmp_path)
        if not report_month:
            flash("Could not detect the report month from this file.")
            return redirect(url_for("me_upload"))

        # Do we already have goals saved for this month? If not, send to goals form first.
        existing_goals = db.get_report("me", report_month)
        if not existing_goals or not existing_goals.get("goals"):
            # stash the uploaded file path + month in session so /me/goals can pick it up
            session["pending_upload"] = tmp_path
            session["pending_month"] = report_month
            prior = db.get_previous_report("me", month_sort_key(report_month))
            prior_goals = prior["goals"] if prior else None
            return redirect(url_for("me_goals", prefill="1"))

        return _finish_me_processing(tmp_path, report_month, existing_goals["goals"])
    except Exception as e:
        flash(f"Failed to process file: {e}")
        return redirect(url_for("me_upload"))


@app.route("/me/goals", methods=["GET", "POST"])
@login_required
def me_goals():
    month = session.get("pending_month")
    tmp_path = session.get("pending_upload")
    if not month or not tmp_path:
        flash("No report pending — please upload a file first.")
        return redirect(url_for("me_upload"))

    prior = db.get_previous_report("me", month_sort_key(month))
    prior_goals = prior["goals"] if prior else None
    default_goals = me_parser.default_goals_for_all_clinics(prior_goals)

    if request.method == "GET":
        return render_template("me_goals.html", month=month, clinics=me_parser.CLINIC_NAMES,
                                defaults=default_goals)

    goals = {}
    for clinic in me_parser.CLINIC_NAMES:
        goals[clinic] = {
            "gift_card":     float(request.form.get(f"{clinic}__gift_card", 0)),
            "retail":        float(request.form.get(f"{clinic}__retail", 0)),
            "service_hours": float(request.form.get(f"{clinic}__service_hours", 0)),
            "memberships":   float(request.form.get(f"{clinic}__memberships", 0)),
        }

    session.pop("pending_upload", None)
    session.pop("pending_month", None)
    return _finish_me_processing(tmp_path, month, goals)


def _finish_me_processing(tmp_path, report_month, goals):
    prior = db.get_previous_report("me", month_sort_key(report_month))
    # prev snapshot for parse_report is keyed by clinic name -> {active_mb, suspend_pct, inactive_pct}
    prev_for_parse = prior["data"]["snapshot"] if prior and "snapshot" in prior["data"] else {}

    clinics, pace, days_into, days_in_month, month_label, end_dt = me_parser.parse_report(
        tmp_path, prev_for_parse, goals
    )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    synopses = me_parser.generate_clinic_synopses(clinics, pace, days_into, days_in_month, month_label, api_key)

    snapshot = me_parser.snapshot_for_history(clinics, goals, month_label)

    db.save_report(
        "me", month_label, month_sort_key(month_label),
        data={"clinics": clinics, "snapshot": snapshot},
        goals=goals, synopses=synopses, pace=pace,
        days_into=days_into, days_in_month=days_in_month,
        end_date=end_dt.isoformat(),
    )

    os.unlink(tmp_path)

    # Render + email
    html = build_me_html(clinics, pace, days_into, days_in_month, month_label, end_dt, synopses)

    pdf_path = None
    try:
        pdf_path = os.path.join(tempfile.gettempdir(), f"ME_Dashboard_{month_label.replace(' ', '_')}.pdf")
        generate_pdf(html, pdf_path)
    except Exception as e:
        flash(f"PDF generation failed (email will still send without it): {e}")

    try:
        send_dashboard_email(html, f"Monthly Progress — {month_label}", ME_EMAIL_TO, pdf_path)
        flash(f"Dashboard generated and emailed to the team for {month_label}.")
    except Exception as e:
        flash(f"Dashboard generated, but email failed: {e}")

    if pdf_path and os.path.exists(pdf_path):
        os.unlink(pdf_path)

    return redirect(url_for("me_dashboard", month=month_label))


@app.route("/sales")
@login_required
def sales_dashboard():
    month = request.args.get("month")
    report = db.get_report("sales", month) if month else db.get_latest_report("sales")
    months = db.list_months("sales")

    if not report:
        return render_template("sales_dashboard.html", html=None, months=months, selected_month=None)

    d = report["data"]
    if not d.get("employees"):
        return render_template("sales_dashboard.html", html=None, months=months,
                                selected_month=report["month_label"], seed_only=True)

    html = build_sales_html(
        d["employees"], report["month_label"], d["date_range"],
        d["prev_month"], d["prev_run_date"], d["prev_clinic_ltv"],
    )
    return render_template("sales_dashboard.html", html=html, months=months, selected_month=report["month_label"])


@app.route("/sales/upload", methods=["GET", "POST"])
@login_required
def sales_upload():
    if request.method == "GET":
        return render_template("sales_upload.html")

    file = request.files.get("report_file")
    if not file or not file.filename:
        flash("Please choose the Employee Performance Summary .xlsx file.")
        return redirect(url_for("sales_upload"))

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        last_run = db.get_last_run("sales")
        prev = last_run["data"]["snapshot"] if last_run else {}

        employees, month_label, date_range, prev_month, prev_run_date, prev_clinic_ltv = \
            sales_parser.parse_report(tmp_path, prev)

        if not employees:
            flash("No Front Desk/Manager rows found in this file — check it's the right report.")
            return redirect(url_for("sales_upload"))

        clinic_ltv_now = sales_parser.compute_clinic_ltv(employees)
        snapshot = sales_parser.snapshot_for_history(employees, month_label, clinic_ltv_now)

        db.save_report(
            "sales", month_label, month_sort_key(month_label),
            data={
                "employees": employees,
                "date_range": date_range,
                "prev_month": prev_month,
                "prev_run_date": prev_run_date,
                "prev_clinic_ltv": prev_clinic_ltv,
                "snapshot": snapshot,
            },
        )

        html = build_sales_html(employees, month_label, date_range, prev_month, prev_run_date, prev_clinic_ltv)

        pdf_path = None
        try:
            pdf_path = os.path.join(tempfile.gettempdir(), f"ME_Sales_Dashboard_{month_label.replace(' ', '_')}.pdf")
            generate_pdf(html, pdf_path)
        except Exception as e:
            flash(f"PDF generation failed (email will still send without it): {e}")

        try:
            send_dashboard_email(html, f"{SALES_EMAIL_SUBJECT} — {month_label}", SALES_EMAIL_TO, pdf_path)
            flash(f"Sales dashboard generated and emailed to the team for {month_label}.")
        except Exception as e:
            flash(f"Sales dashboard generated, but email failed: {e}")

        if pdf_path and os.path.exists(pdf_path):
            os.unlink(pdf_path)

        return redirect(url_for("sales_dashboard", month=month_label))
    except Exception as e:
        flash(f"Failed to process file: {e}")
        return redirect(url_for("sales_upload"))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.route("/admin/seed", methods=["GET", "POST"])
@login_required
def admin_seed():
    if request.method == "GET":
        return render_template("admin_seed.html")

    results = []

    me_file = request.files.get("me_prev_file")
    if me_file and me_file.filename:
        try:
            payload = json.load(me_file.stream)
            month_label = payload.get("_goals_month")
            goals = payload.get("_goals")
            if not month_label:
                results.append("ME file: no _goals_month found — skipped.")
            else:
                snapshot = {k: v for k, v in payload.items()}  # already shaped like snapshot_for_history()
                db.save_report(
                    "me", month_label, month_sort_key(month_label),
                    data={"clinics": [], "snapshot": snapshot},
                    goals=goals,
                )
                results.append(f"ME: seeded history/goals for {month_label}.")
        except Exception as e:
            results.append(f"ME file failed: {e}")

    sales_file = request.files.get("sales_prev_file")
    if sales_file and sales_file.filename:
        try:
            payload = json.load(sales_file.stream)
            month_label = payload.get("month_label")
            if not month_label:
                results.append("Sales file: no month_label found — skipped.")
            else:
                db.save_report(
                    "sales", month_label, month_sort_key(month_label),
                    data={
                        "employees": [],
                        "date_range": "",
                        "prev_month": "",
                        "prev_run_date": "",
                        "prev_clinic_ltv": {},
                        "snapshot": payload,
                    },
                )
                results.append(f"Sales: seeded history for {month_label}.")
        except Exception as e:
            results.append(f"Sales file failed: {e}")

    if not results:
        results.append("No files were uploaded.")

    for r in results:
        flash(r)
    return redirect(url_for("admin_seed"))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True, port=5000)
