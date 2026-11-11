"""
Daily proactive alert — runs every morning at 8am.
Checks stockout risks + reorder alerts, sends Email + WhatsApp.

Run once:  python daily_alert.py
Run on schedule: python daily_alert.py --schedule
"""

import argparse
import os
import smtplib
import textwrap
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import schedule
import time

from dotenv import load_dotenv
from drift_check import run_drift_check, format_drift_report

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

ALERT_TO_EMAIL    = os.getenv("ALERT_TO_EMAIL")       # recipient email
ALERT_FROM_EMAIL  = os.getenv("ALERT_FROM_EMAIL")     # sender Gmail address
ALERT_EMAIL_PASS  = os.getenv("ALERT_EMAIL_PASS")     # Gmail app password

TWILIO_SID        = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH       = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM       = os.getenv("TWILIO_WHATSAPP_FROM") # e.g. whatsapp:+<your_twilio_number>
TWILIO_TO         = os.getenv("TWILIO_WHATSAPP_TO")   # e.g. whatsapp:+<your_phone_number>

ALERT_TIME        = os.getenv("ALERT_TIME", "08:00")  # 24hr format


# ── Data pull ─────────────────────────────────────────────────────────────────

def _get_stockout_risks():
    from erp_tools import inventory_tool
    df, _ = inventory_tool()
    at_risk = df[df["stock_status"] == "STOCKOUT RISK"][
        ["Product", "months_of_stock_left", "latest_balance", "abc_class"]
    ].copy()
    at_risk["months_of_stock_left"] = at_risk["months_of_stock_left"].round(1)
    return at_risk.to_dict("records")


def _get_reorder_needed():
    from erp_tools import safety_stock_tool
    df, _ = safety_stock_tool()
    reorder = df[df["Status"] == "REORDER"][
        ["Product", "Balance", "Reorder Point (units)", "Safety Stock (units)", "Avg Monthly Demand"]
    ].copy()
    return reorder.to_dict("records")


# ── Message builder ───────────────────────────────────────────────────────────

def build_alert_data():
    stockouts = _get_stockout_risks()
    reorders  = _get_reorder_needed()
    drift     = run_drift_check()
    today     = date.today().strftime("%B %d, %Y")
    return today, stockouts, reorders, drift


def build_whatsapp_message(today, stockouts, reorders, drift=None):
    lines = [
        f"*Reman ERP — Daily Alert*",
        f"_{today}_",
        "",
    ]

    if stockouts:
        lines.append(f"*STOCKOUT RISKS ({len(stockouts)} products)*")
        for p in stockouts:
            months = p.get("months_of_stock_left", "?")
            abc    = p.get("abc_class", "")
            lines.append(f"• {p['Product']} [{abc}] — {months} months left")
    else:
        lines.append("*STOCKOUT RISKS* — None today")

    lines.append("")

    if reorders:
        lines.append(f"*REORDER NOW ({len(reorders)} products)*")
        for p in reorders:
            bal = int(p.get("Balance", 0))
            rop = int(p.get("Reorder Point (units)", 0))
            lines.append(f"• {p['Product']} — Balance: {bal} units (ROP: {rop})")
    else:
        lines.append("*REORDER NOW* — All products OK")

    if drift:
        lines.append("")
        lines.append(format_drift_report(drift))

    lines += ["", "_Reman ERP Agent_"]
    return "\n".join(lines)


def _build_drift_html(drift):
    if not drift or drift.get("status") == "OK" and not drift.get("alerts"):
        m = drift["metrics"] if drift else {}
        return f"""
      <div style="padding:16px 20px;background:#f9f9f9;border-top:1px solid #eee">
        <h3 style="color:#323130;margin:0 0 8px 0">Agent Health (LLMOps)</h3>
        <p style="margin:2px 0;font-size:13px;color:#444">Status: <span style="color:green;font-weight:600">OK</span></p>
        <p style="margin:2px 0;font-size:13px;color:#444">Critic fail rate: {m.get('critic_fail_rate',0)*100:.0f}% &nbsp;|&nbsp;
          Avg cost/query: ${m.get('avg_cost_usd',0):.4f} &nbsp;|&nbsp;
          Avg response: {m.get('avg_response_s',0):.1f}s &nbsp;|&nbsp;
          Tool miss rate: {m.get('tool_miss_rate',0)*100:.0f}%</p>
        <p style="margin:2px 0;font-size:12px;color:#888">Total queries logged: {drift.get('total_queries',0)} &nbsp;|&nbsp; Total cost: ${m.get('total_cost_usd',0):.4f}</p>
      </div>"""

    m = drift.get("metrics", {})
    alert_html = "".join(
        f"<li style='color:#c00;font-size:13px'>{a}</li>" for a in drift.get("alerts", [])
    )
    return f"""
      <div style="padding:16px 20px;background:#fff8f0;border-top:2px solid #e65c00">
        <h3 style="color:#c00;margin:0 0 8px 0">&#9888; Agent Health — DRIFT DETECTED</h3>
        <ul style="margin:4px 0;padding-left:18px">{alert_html}</ul>
        <p style="margin:8px 0 2px 0;font-size:13px;color:#444">Critic fail rate: {m.get('critic_fail_rate',0)*100:.0f}% &nbsp;|&nbsp;
          Avg cost/query: ${m.get('avg_cost_usd',0):.4f} &nbsp;|&nbsp;
          Avg response: {m.get('avg_response_s',0):.1f}s &nbsp;|&nbsp;
          Tool miss rate: {m.get('tool_miss_rate',0)*100:.0f}%</p>
        <p style="margin:2px 0;font-size:12px;color:#888">Total queries logged: {drift.get('total_queries',0)} &nbsp;|&nbsp; Total cost: ${m.get('total_cost_usd',0):.4f}</p>
      </div>"""


def build_email_html(today, stockouts, reorders, drift=None):
    def row(cells, header=False):
        tag = "th" if header else "td"
        style = "background:#0078D4;color:white;padding:8px 12px;" if header else "padding:8px 12px;border-bottom:1px solid #eee;"
        return "<tr>" + "".join(f"<{tag} style='{style}'>{c}</{tag}>" for c in cells) + "</tr>"

    stockout_rows = ""
    if stockouts:
        stockout_rows += row(["Product", "ABC Class", "Months Left"], header=True)
        for p in stockouts:
            months = p.get("months_of_stock_left", "?")
            abc    = p.get("abc_class", "")
            color  = "#c00" if float(months or 0) < 1 else "#e65c00"
            stockout_rows += row([
                p["Product"], abc,
                f"<span style='color:{color};font-weight:600'>{months}</span>"
            ])
    else:
        stockout_rows = "<tr><td style='padding:8px 12px;color:green'>No stockout risks today</td></tr>"

    reorder_rows = ""
    if reorders:
        reorder_rows += row(["Product", "Balance", "Reorder Point"], header=True)
        for p in reorders:
            bal = int(p.get("Balance", 0))
            rop = int(p.get("Reorder Point (units)", 0))
            reorder_rows += row([p["Product"], f"{bal:,} units", f"{rop:,} units"])
    else:
        reorder_rows = "<tr><td style='padding:8px 12px;color:green'>All products above reorder point</td></tr>"

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto">
      <div style="background:#0078D4;padding:16px 24px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">Reman ERP — Daily Alert</h2>
        <p style="color:#cce4f7;margin:4px 0 0 0">{today}</p>
      </div>
      <div style="padding:20px;background:#fff;border:1px solid #eee">
        <h3 style="color:#323130">Stockout Risks</h3>
        <table style="width:100%;border-collapse:collapse">{stockout_rows}</table>
        <h3 style="color:#323130;margin-top:24px">Reorder Now</h3>
        <table style="width:100%;border-collapse:collapse">{reorder_rows}</table>
      </div>
      {_build_drift_html(drift)}
      <div style="padding:12px 24px;background:#f4f4f4;border-radius:0 0 8px 8px;font-size:12px;color:#666">
        Reman ERP Agent — automated daily alert
      </div>
    </body></html>
    """


# ── Senders ───────────────────────────────────────────────────────────────────

def send_email(today, stockouts, reorders, drift=None):
    if not all([ALERT_FROM_EMAIL, ALERT_EMAIL_PASS, ALERT_TO_EMAIL]):
        print("[Email] Skipped — credentials not set in .env")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Reman ERP Alert — {len(stockouts)} Stockout Risk(s) | {today}"
    msg["From"]    = ALERT_FROM_EMAIL
    msg["To"]      = ALERT_TO_EMAIL

    html = build_email_html(today, stockouts, reorders, drift)
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(ALERT_FROM_EMAIL, ALERT_EMAIL_PASS)
            server.sendmail(ALERT_FROM_EMAIL, ALERT_TO_EMAIL, msg.as_string())
        print(f"[Email] Sent to {ALERT_TO_EMAIL}")
    except Exception as e:
        print(f"[Email] Failed: {e}")


def send_whatsapp(today, stockouts, reorders, drift=None):
    if not all([TWILIO_SID, TWILIO_AUTH, TWILIO_FROM, TWILIO_TO]):
        print("[WhatsApp] Skipped — Twilio credentials not set in .env")
        return

    try:
        from twilio.rest import Client
        client  = Client(TWILIO_SID, TWILIO_AUTH)
        message = build_whatsapp_message(today, stockouts, reorders, drift)
        client.messages.create(body=message, from_=TWILIO_FROM, to=TWILIO_TO)
        print(f"[WhatsApp] Sent to {TWILIO_TO}")
    except ImportError:
        print("[WhatsApp] twilio package not installed — run: pip install twilio")
    except Exception as e:
        print(f"[WhatsApp] Failed: {e}")


# ── Runner ────────────────────────────────────────────────────────────────────

def run_alert():
    print(f"\n[Alert] Running daily alert...")
    today, stockouts, reorders, drift = build_alert_data()

    print(f"[Alert] {len(stockouts)} stockout risk(s), {len(reorders)} reorder(s), drift: {drift['status']}")

    send_email(today, stockouts, reorders, drift)
    send_whatsapp(today, stockouts, reorders, drift)

    print(f"[Alert] Done.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reman ERP daily alert")
    parser.add_argument("--schedule", action="store_true", help=f"Run on schedule at {ALERT_TIME} daily")
    args = parser.parse_args()

    if args.schedule:
        print(f"[Alert] Scheduler started — will run every day at {ALERT_TIME}")
        schedule.every().day.at(ALERT_TIME).do(run_alert)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_alert()
