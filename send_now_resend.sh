#!/usr/bin/env bash
set -euo pipefail

: "${RESEND_API_KEY:?RESEND_API_KEY is required}"
: "${MAIL_TO:=langtianyuyu@gmail.com}"
: "${MAIL_FROM:=onboarding@resend.dev}"

SUBJECT='[伊朗局势简报] 2026-03-05（晚间）'
HTML='<h3>伊朗局势简报（2026-03-05）</h3><ul><li>安理会紧急会议上，多方要求立即降级并重回谈判，联合国警告冲突外溢风险上升。</li><li>美国白宫（3月1日、3月3日）继续确认对伊行动（Operation Epic Fury）并强调军事压制目标。</li><li>中国外交部（3月3日）重申“停火止战、重回对话、反对单边行动”，并通报已组织大规模在伊人员撤离。</li><li>伊朗方面继续以“自卫回应”为主线谴责美以打击，三方叙事分歧仍大。</li><li>市场端（Bloomberg）显示油价与避险资产受冲突推动上行，需重点关注霍尔木兹海峡与后续通胀风险。</li></ul><p>来源：AP、白宫、中国外交部、Bloomberg</p>'

curl -sS https://api.resend.com/emails \
  -H "Authorization: Bearer ${RESEND_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d "$(cat <<JSON
{
  "from": "${MAIL_FROM}",
  "to": ["${MAIL_TO}"],
  "subject": "${SUBJECT}",
  "html": "${HTML}"
}
JSON
)"
