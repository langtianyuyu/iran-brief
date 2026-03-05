#!/usr/bin/env python3
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
from typing import Optional, Tuple


def curl_get(url: str) -> str:
    out = subprocess.check_output(
        ["curl", "-fsSL", "-A", "Mozilla/5.0", "--max-time", "30", url],
        text=True,
    )
    return out


def safe_float(v: str) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def fetch_spx_snapshot() -> Optional[Tuple[float, float]]:
    # Use last 2 daily closes from Stooq to compute day-over-day change.
    csv_text = curl_get("https://stooq.com/q/d/l/?s=%5Espx&i=d")
    lines = [ln.strip() for ln in csv_text.splitlines() if ln.strip()]
    if len(lines) < 3:
        return None
    last = lines[-1].split(",")
    prev = lines[-2].split(",")
    if len(last) < 5 or len(prev) < 5:
        return None
    last_close = safe_float(last[4])
    prev_close = safe_float(prev[4])
    if last_close is None or prev_close is None or prev_close == 0:
        return None
    pct = (last_close - prev_close) / prev_close * 100.0
    return last_close, pct


def fetch_btc_snapshot() -> Optional[Tuple[float, float]]:
    raw = curl_get(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
    )
    data = json.loads(raw)
    btc = data.get("bitcoin", {})
    price = btc.get("usd")
    pct = btc.get("usd_24h_change")
    if price is None or pct is None:
        return None
    return float(price), float(pct)


def market_pair_line() -> dict:
    spx = fetch_spx_snapshot()
    btc = fetch_btc_snapshot()

    if not spx and not btc:
        return {
            "en": "Market add-on unavailable today: failed to fetch both S&P 500 and BTC data.",
            "zh": "今日市场补充不可用：S&P 500 和 BTC 数据都获取失败。",
        }

    en_parts = []
    zh_parts = []
    if spx:
        spx_px, spx_pct = spx
        en_parts.append(f"S&P 500: {spx_px:,.2f} ({spx_pct:+.2f}% d/d)")
        zh_parts.append(f"S&P 500：{spx_px:,.2f}（日变动 {spx_pct:+.2f}%）")
    if btc:
        btc_px, btc_pct = btc
        en_parts.append(f"BTC: ${btc_px:,.0f} ({btc_pct:+.2f}% 24h)")
        zh_parts.append(f"BTC：${btc_px:,.0f}（24小时 {btc_pct:+.2f}%）")

    return {"en": " | ".join(en_parts), "zh": "；".join(zh_parts)}


def fetch_rss(query: str, bucket: str, lang: str = "en-US", country: str = "US"):
    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl={lang}&gl={country}&ceid={country}:en"
    xml = curl_get(url)
    root = ET.fromstring(xml)

    out = []
    for item in root.findall("./channel/item")[:6]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        if title and link:
            out.append(
                {
                    "bucket": bucket,
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "description": description,
                }
            )
    return out


def extract_numeric_detail(description_html: str) -> str:
    if not description_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", description_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?。！？])\s+", text)
    candidates = [p.strip() for p in parts if re.search(r"\d", p)]
    return candidates[0][:220] if candidates else ""


def translate_text(text: str, target_lang: str) -> str:
    q = urllib.parse.quote_plus(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl={target_lang}&dt=t&q={q}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        translated = "".join(part[0] for part in data[0] if part and part[0])
        return translated.strip() or text
    except Exception:
        return text


def pick_items():
    plans = [
        ("Top-tier", 'Iran (Reuters OR AP OR Bloomberg) when:1d'),
        ("US", 'Iran (White House OR State Department) when:1d'),
        ("China", '伊朗 外交部 when:1d'),
        ("Iran", 'Iran official IRNA when:1d'),
    ]

    items = []
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
            items.append(it)
            if len(items) >= 5:
                return items

    return items[:5]


def summarize(items):
    if not items:
        return [
            {
                "en": "No major verifiable update was detected in the past 24 hours from automated sources.",
                "zh": "过去24小时未抓到可核验重大新增（自动源），建议人工复核。",
            }
        ]

    paired = []
    for it in items[:5]:
        t = it["title"]
        if " - " in t:
            headline = t.rsplit(" - ", 1)[0]
            source = t.rsplit(" - ", 1)[1]
            en_line = f"[{it['bucket']}/{source}] {headline}"
        else:
            en_line = f"[{it['bucket']}] {t}"
        detail = extract_numeric_detail(it.get("description", ""))
        if not detail and not re.search(r"\d", en_line):
            continue
        en_full = f"{en_line}. Detail: {detail}" if detail else en_line
        zh_line = translate_text(en_full, "zh-CN")
        paired.append({"en": en_full, "zh": zh_line})

    if not paired:
        return [
            {
                "en": "No item with concrete numeric detail was found from reachable sources today.",
                "zh": "今天可访问来源中未抓到带具体数字细节的条目。",
            }
        ]
    return paired


def send(subject: str, html: str):
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    mail_to = os.getenv("MAIL_TO", "langtianyuyu@gmail.com").strip()
    mail_from = os.getenv("MAIL_FROM", "onboarding@resend.dev").strip()

    if not api_key:
        raise RuntimeError("RESEND_API_KEY missing")

    payload = json.dumps(
        {
            "from": mail_from,
            "to": [mail_to],
            "subject": subject,
            "html": html,
        },
        ensure_ascii=False,
    )

    out = subprocess.check_output(
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
    return out


def main():
    date_str = dt.datetime.now().strftime("%Y-%m-%d")
    items = pick_items()
    paired_bullets = summarize(items)
    paired_bullets.append(market_pair_line())

    paired_html = "".join(
        f"<li><b>EN:</b> {b['en']}<br/><b>中文:</b> {b['zh']}</li>" for b in paired_bullets
    )
    links_html = "".join(
        f'<li><a href="{it["link"]}">{it["title"]}</a></li>' for it in items[:5]
    )

    subject = f"[伊朗局势简报 | Iran Brief] {date_str}（晚间）"
    html = (
        f"<h3>伊朗局势简报 / Iran Conflict Brief（{date_str}）</h3>"
        f"<ul>{paired_html}</ul>"
        f"<p><b>观察 / Watchlist:</b> 是否出现新一轮跨境打击；能源与航运风险是否继续上行。"
        f" / Whether a new cross-border strike wave appears; whether energy/shipping risk keeps rising.</p>"
        f"<p>来源链接 | Sources:</p><ul>{links_html}</ul>"
    )

    print(send(subject, html))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
