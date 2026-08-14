# Submission screenshot capture

Run this only after the release gate passes:

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\capture_submission.ps1" -BrowserChannel "chrome"
```

The command drives the real canonical browser journey and writes:

- `01-found-nearby-and-03-agent-proof.png`
- `02-stock-card-evidence.png`
- `04-offline-facility-proof.png`
- `05-delivery-defense-audit.png`

Review each image for sensitive information before publishing. The fifth required proof—Cloud Run revision/URL plus correlated logs—must be captured manually from the owner’s credentialed Google Cloud project and must not contain tokens, billing details, or secret environment values.
