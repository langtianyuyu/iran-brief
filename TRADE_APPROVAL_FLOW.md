# Trade Approval Flow

1. `Questrade Plan Email` runs daily and sends plan email with buy reasons and estimated price/notional.
2. If you approve, open GitHub Actions workflow `Questrade Execute Approved Trades`.
3. Click `Run workflow` and set `confirm=YES`.
4. Orders execute only when:
   - `confirm=YES`
   - `TRADE_ENABLED=true` in GitHub Secrets.

## Required GitHub Secrets
- QUESTRADE_REFRESH_TOKEN
- QUESTRADE_ACCOUNT_ID
- QUESTRADE_IS_DEMO
- TRADE_ENABLED
- MAX_TRADES_PER_DAY
- MAX_NOTIONAL_PER_TRADE
- DAILY_LOSS_LIMIT
- TRADE_UNIVERSE
- RESEND_API_KEY
- MAIL_TO
- MAIL_FROM
