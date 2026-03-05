#!/usr/bin/env python3
import json
import os
import subprocess
import sys


def send_email(subject: str, html: str) -> str:
    key = os.environ["RESEND_API_KEY"].strip()
    mail_to = os.getenv("MAIL_TO", "langtianyuyu@gmail.com").strip()
    mail_from = os.getenv("MAIL_FROM", "onboarding@resend.dev").strip()

    payload = json.dumps(
        {
            "from": mail_from,
            "to": [mail_to],
            "subject": subject,
            "html": html,
        },
        ensure_ascii=False,
    )

    return subprocess.check_output(
        [
            "curl",
            "-fsS",
            "https://api.resend.com/emails",
            "-H",
            f"Authorization: Bearer {key}",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
        ],
        text=True,
    )


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        raise RuntimeError("No plan JSON provided on stdin")
    plan = json.loads(raw)

    orders = plan.get("orders", [])
    date = plan.get("date", "")

    if not orders:
        html = (
            f"<h3>Questrade Trade Plan ({date})</h3>"
            f"<p>No trade today.</p>"
            f"<p>Reason: {plan.get('summary','No candidates')}</p>"
        )
    else:
        rows = ""
        for i, o in enumerate(orders, 1):
            rows += (
                f"<li><b>{i}. {o['side']} {o['symbol']}</b> | Qty: {o['qty']} | "
                f"Est Price: ${o['ask']} | Est Notional: ${o['est_notional']}<br/>"
                f"Reason: {o['reason']}</li>"
            )

        html = (
            f"<h3>Questrade Trade Plan ({date})</h3>"
            f"<p>Cash: ${plan.get('cash_usd', 0)}</p>"
            f"<ul>{rows}</ul>"
            f"<p>Sell plan: {plan.get('sell_plan','N/A')}</p>"
            f"<p><b>How to approve:</b> Go to GitHub Actions -> 'Questrade Execute Approved Trades' -> Run workflow -> set confirm=YES.</p>"
            f"<p><b>中文：</b>如同意下单，请到 GitHub Actions 运行 “Questrade Execute Approved Trades”，把 confirm 填 YES。</p>"
        )

    subject = f"[Trade Approval Needed] {date} Questrade Plan"
    print(send_email(subject, html))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
