1. Create a GitHub repo and push this folder.
2. In GitHub repo settings, add Actions secrets:
   - RESEND_API_KEY = your Resend key
   - MAIL_TO = langtianyuyu@gmail.com
   - MAIL_FROM = onboarding@resend.dev
3. Enable GitHub Actions for the repo.
4. Run workflow once manually: Actions -> "Daily Iran Brief" -> Run workflow.
5. After that, it runs daily at 06:00 (Los Angeles time target via UTC cron).

Notes:
- This runs in GitHub cloud, so your Mac can stay off.
- Internet is required in GitHub runner (already provided by Actions).
- If you want a different timezone, update TZ and cron in .github/workflows/iran-brief.yml.
