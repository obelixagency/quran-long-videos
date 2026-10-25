# Credential-safe automation output

Scheduled publishing, channel selection, upload payloads, permissions and secret names are unchanged.

Authenticated YouTube and GitHub requests now suppress transport exception details (which may contain bearer upload URLs). OAuth errors, playlist failures and upload failures report operation/status only, never API bodies or arbitrary error descriptions. Failed playlist additions still do not block a successful video upload, but their stored history result is now a fixed message rather than an exception string.

The five workflows were reviewed for logs, job summaries, artifacts and issue output. Playlist backfill no longer prints raw API response bodies. Watchdog summaries/issues retain counts, slot identifiers and run links only. Uploaded artifacts remain thumbnail/frame images and title/description text; no credential files were added.

Run offline checks with `python -m unittest discover -s tests -v` and `python -m compileall -q long tests`. Canary tests exercise refresh success/failure, invalid JSON, transport failures, playlist errors, upload initialization failures and retry/success. They never access live accounts or publish content. In a minimal environment they use a requests stub; in normal environments they mock the installed requests package.

This patch does not erase past logs/artifacts/history, rotate credentials, change repository visibility, or change account access. Existing disclosures would require a separately approved cleanup and rotation.
