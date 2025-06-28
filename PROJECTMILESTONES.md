2025-06-27: Initialized project directory structure.
2025-06-27: Implemented fetch_forecast.py to pull and filter DHS APFS data.
2025-06-27: Added logging and CSV export to data/processed.
2025-06-27: Integrated Teams webhook notification with HTML-formatted summaries.
2025-06-27: Enhanced summary formatting using `<br/>` for clear line breaks.
2025-06-27: Created comprehensive README.md with setup and usage instructions.
2025-06-27: Defined Cursor best-practice rules in .cursorrules.
2025-06-27: Outlined persistence plan for “seen” IDs to enable delta-only posting.
2025-06-28: Initialized GitHub repository and pushed initial commit.
2025-06-28: Added GitHub Actions workflow for scheduled weekday and manual runs.
2025-06-28: CI step added to generate config/settings.yaml from the TEAMS_WEBHOOK_URL secret.
2025-06-28: Implemented seen_ids.json persistence to enable delta-only posting of new opportunities.
2025-06-28: Updated Teams notification header to include human-friendly timestamp.
2025-06-28: Reordered summary fields in the Teams message for improved readability.
