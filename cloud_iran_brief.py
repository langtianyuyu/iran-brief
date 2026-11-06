#!/usr/bin/env python3
import argparse
from pathlib import Path
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def curl_get(url: str) -> str:
    return subprocess.check_output(
        ["curl", "-fsSL", "-A", "Mozilla/5.0", "--max-time", "30", url],
        text=True,
    )


def translate_text(text: str, target_lang: str) -> str:
    q = urllib.parse.quote_plus(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl={target_lang}&dt=t&q={q}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return "".join(part[0] for part in data[0] if part and part[0]).strip() or text


def fetch_rss(query: str, bucket: str):
    encoded = urllib.parse.quote_plus(query)
    url = (
        "https://news.google.com/rss/search"
        f"?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    )
    root = ET.fromstring(curl_get(url))
    items = []
    for item in root.findall("./channel/item")[:10]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if title and link:
            items.append(
                {
                    "bucket": bucket,
                    "title": title,
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                }
            )
    return items


def extract_numeric_detail(description_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", description_html or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    hits = [p for p in parts if re.search(r"\d", p)]
    return hits[0][:240] if hits else ""


def pick_news():
    plans = [
        ("Top-tier", 'Iran Reuters OR AP OR Bloomberg when:1d'),
        ("US", 'Iran White House OR State Department when:1d'),
        ("China", '伊朗 外交部 when:1d'),
        ("Iran", 'Iran IRNA OR Iranian foreign ministry when:1d'),
    ]
    out = []
    seen = set()
    for bucket, q in plans:
        try:
            fetched = fetch_rss(q, bucket)
        except Exception:
            continue
        for it in fetched:
            key = it["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            detail = extract_numeric_detail(it["description"])
            if not detail and not re.search(r"\d", it["title"]):
                continue
            out.append({**it, "detail": detail})
            if len(out) >= 5:
                return out
    return out[:5]


def fetch_markets():
    spx_line = "S&P 500: N/A"
    btc_line = "BTC: N/A"
    try:
        csv_text = curl_get("https://stooq.com/q/d/l/?s=%5Espx&i=d")
        lines = [x.strip() for x in csv_text.splitlines() if x.strip()]
        if len(lines) >= 3:
            last = lines[-1].split(",")
            prev = lines[-2].split(",")
            c1 = float(last[4])
            c0 = float(prev[4])
            p = (c1 - c0) / c0 * 100.0
            spx_line = f"S&P 500: {c1:,.2f} ({p:+.2f}% d/d)"
    except Exception:
        pass

    try:
        raw = curl_get(
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        )
        d = json.loads(raw)["bitcoin"]
        btc_line = f"BTC: ${float(d['usd']):,.0f} ({float(d['usd_24h_change']):+.2f}% 24h)"
    except Exception:
        pass

    en = f"{spx_line} | {btc_line}"
    zh = translate_text(en, "zh-CN")
    return {"en": en, "zh": zh}


def send(subject: str, html_body: str):
    api_key = os.environ["RESEND_API_KEY"].strip()
    mail_to = os.getenv("MAIL_TO", "langtianyuyu@gmail.com").strip()
    mail_from = os.getenv("MAIL_FROM", "onboarding@resend.dev").strip()
    payload = json.dumps(
        {"from": mail_from, "to": [mail_to], "subject": subject, "html": html_body},
        ensure_ascii=False,
    )
    return subprocess.check_output(
        [
            "curl",
            "-fsS",
            "https://api.resend.com/emails",
            "-H",
            f"Authorization: Bearer {api_key}",
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
        ],
        text=True,
    )


def render_email(date_str, paired):
    """Escape external text and allow only HTTP(S) source links."""
    bullets = "".join(
        f"<li><b>EN:</b> {html.escape(b['en'])}<br/><b>中文:</b> {html.escape(b['zh'])}</li>"
        for b in paired
    )
    links = "".join(
        f'<li><a href="{html.escape(b["link"], quote=True)}">{html.escape(b["link"])}</a></li>'
        for b in paired if urllib.parse.urlparse(b.get('link', '')).scheme in ('http', 'https')
    )
    return (f"<h3>Iran News &amp; Markets Brief / 伊朗资讯与市场简报 ({html.escape(date_str)})</h3>"
            f"<ul>{bullets}</ul><p>Sources / 来源:</p><ul>{links}</ul>"
            "<p>Automatically collected headlines and translations; sources are not independently verified."
            " / 自动采集与翻译，内容未经独立核实。</p>")


def main():
    parser = argparse.ArgumentParser(description='Bilingual news digest')
    parser.add_argument('--preview', metavar='HTML_PATH', help='Save HTML without sending email')
    parser.add_argument('--fixture', metavar='JSON_PATH', help='Offline paired items; requires --preview')
    args = parser.parse_args()
    if args.fixture and not args.preview:
        parser.error('--fixture requires --preview')
    if args.fixture:
        paired = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
        Path(args.preview).write_text(render_email('DEMO — synthetic fixture', paired), encoding='utf-8')
        return

    tz = os.getenv("TZ", "America/Los_Angeles")
    os.environ["TZ"] = tz
    try:
        import time

        time.tzset()
    except Exception:
        pass

    date_str = dt.datetime.now().strftime("%Y-%m-%d")
    news = pick_news()
    paired = []
    for it in news:
        en = f"[{it['bucket']}] {it['title']}"
        if it["detail"]:
            en = f"{en}. Detail: {it['detail']}"
        try:
            zh = translate_text(en, "zh-CN")
        except Exception:
            zh = en
        paired.append({"en": en, "zh": zh, "link": it["link"]})

    if not paired:
        paired = [
            {
                "en": "No matching numeric news items retrieved. Sources may be unavailable or filtered out.",
                "zh": "未获取到符合数字筛选条件的新闻；可能是来源不可用或条目被过滤。",
                "link": "",
            }
        ]

    paired.append({**fetch_markets(), "link": ""})

    body = render_email(date_str, paired)
    subject = f"[Iran News Brief | 伊朗资讯] {date_str}"
    if args.preview:
        Path(args.preview).write_text(body, encoding='utf-8')
        print(f"Preview saved to {args.preview}")
        return
    print(send(subject, body))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
