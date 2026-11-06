# Deploy the briefing workflow

1. Push the reviewed project to your repository.
2. Add Actions secrets: `RESEND_API_KEY`, `MAIL_TO`, `MAIL_FROM`.
3. Enable Actions and open **Daily Iran Brief**.
4. Manually dispatch once if you intend to send a real email; inspect the job and mailbox for success.
5. The workflow is scheduled for **14:00 UTC daily**. `TZ=America/Edmonton` changes script date formatting, not cron scheduling.

14:00 UTC is 07:00 Edmonton standard time / 08:00 daylight time. Scheduled jobs may start late. No delivery or continuous-operation guarantee has been established.

For a no-send preview, use the README's `--preview` command locally. The legacy macOS launcher contains absolute paths for another checkout and needs configuration before use.
