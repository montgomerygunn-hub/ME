import os
import ssl
import smtplib
import tempfile
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file

import db
from parsers import me_parser
from parsers.me_render import build_html as build_me_html

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-key-change-me")

APP_USERNAME = os.environ.get("APP_USERNAME", "brett")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

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
        if (request.form.get("username") == APP_USERNAME
                and APP_PASSWORD
                and request.form.get("password") == APP_PASSWORD):
            session["logged_in"] = True
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


def send_dashboard_email(html_body, month_label, pdf_path=None):
    smtp_server = os.environ.get("SMTP_SERVER", "secure.emailsrvr.com")
    smtp_port   = int(os.environ.get("SMTP_PORT", 465))
    username    = os.environ.get("SMTP_USERNAME")
    password    = os.environ.get("SMTP_PASSWORD")
    email_from  = os.environ.get("EMAIL_FROM", username)

    if not username or not password:
        raise RuntimeError("SMTP_USERNAME / SMTP_PASSWORD not configured")

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"Monthly Progress — {month_label}"
    msg["From"]    = email_from
    msg["To"]      = ", ".join(ME_EMAIL_TO)

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
        server.sendmail(email_from, ME_EMAIL_TO, msg.as_string())


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

    clinics = report["data"]["clinics"]
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
    prev_snapshot = {k: v for k, v in (prior["data"].get("prev_snapshot", {}) if prior else {}).items()}
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
        send_dashboard_email(html, month_label, pdf_path)
        flash(f"Dashboard generated and emailed to the team for {month_label}.")
    except Exception as e:
        flash(f"Dashboard generated, but email failed: {e}")

    if pdf_path and os.path.exists(pdf_path):
        os.unlink(pdf_path)

    return redirect(url_for("me_dashboard", month=month_label))


@app.route("/sales")
@login_required
def sales_dashboard():
    # TODO: FDA/Manager sales dashboard — pending sales_dashboard.py parsing logic
    return render_template("coming_soon.html", name="Sales Dashboard")


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True, port=5000)
