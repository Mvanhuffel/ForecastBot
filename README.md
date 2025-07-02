# Forecast Bot

## What it Does

Forecast Bot automates the end-to-end process of  
1. Gathering government forecast data  
2. Filtering it for your target NAICS codes  
3. Summarizing key insights with an LLM  
4. Posting a human-friendly summary into a Microsoft Teams channel

It also archives the raw filtered CSV in `data/processed/` and writes detailed logs to `logs/forecast_bot.log`.

## Key Features

- **Data Fetching**  
  Pull live forecast tables from DHS, BEA, USDA, etc.

- **Filtering**  
  Apply NAICS-based (or other) filters to reduce the dataset.

- **Summarization**  
  Format and post a concise, bullet-free summary directly into Teams.

- **Delivery**  
  Use a Teams Incoming Webhook to push HTML-formatted notifications.

- **Logging**  
  Rotating file logs under `logs/forecast_bot.log` capture run details and errors.

## Project Layout

    ForecastBot/
    ├── config/
    │   └── settings.yaml        ← Teams webhook URL, NAICS targets, etc.
    ├── data/
    │   └── processed/           ← filtered_forecast.csv outputs
    ├── logs/
    │   └── forecast_bot.log     ← rotating run log
    ├── src/
    │   └── fetch_forecast.py    ← main bot logic
    ├── tests/                   ← unit tests as you add them
    ├── .cursorrules             ← Cursor best-practice rules
    ├── requirements.txt         ← pinned dependencies
    ├── README.md
    └── .env.example             ← template for env-based secrets

## Getting Started

### Prerequisites

- Python 3.8+  
- A Teams Incoming Webhook URL  
- Your LLM API credentials (OpenAI, Anthropic, etc.)

### Installation & First Run

```bash
git clone https://github.com/your-org/ForecastBot.git
cd ForecastBot

# 1. Create & activate a virtual environment
python -m venv .venv
# Windows PowerShell:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Paste your TEAMS_WEBHOOK_URL and any LLM API keys into .env
# Edit config/settings.yaml if you need to override via file

# 4. Run
python src/fetch_forecast.py

## Configuration

All runtime settings live in `config/settings.yaml` (overridable via environment variables). Example:

    teams:
      webhook_url: "${TEAMS_WEBHOOK_URL}"
    # Add additional API endpoints, NAICS targets, LLM prompt parameters, etc.

## Logs & Outputs

- **Logs**: `logs/forecast_bot.log` (rotates at 5 MB, keeps 3 backups)  
- **Filtered CSV**: `data/processed/filtered_forecast.csv`

## Data Persistence

The bot uses GitHub Actions artifacts and releases to maintain state and archive data:

- **Seen Opportunities**: The bot tracks which opportunities it has already posted using `seen_ids.json`, which is maintained as a GitHub Actions artifact with a 90-day retention period. This ensures reliable state persistence between workflow runs and prevents reposting of opportunities. The file appears empty in the repository because it's managed entirely through GitHub Actions artifacts.

- **Forecast Archives**: Daily forecast CSV files (e.g., `filtered_forecast_2025-07-02.csv`) are published as GitHub Releases rather than being committed to the repository. These are accessible via the "Download the latest filtered CSV" link in Teams messages, keeping historical data available without bloating the repository.

This design ensures efficient data persistence while keeping the repository clean and focused on source code.

## Next Steps

- Add unit tests under `tests/` (e.g. for `fetch_forecast()` and filter logic)  
- Expand `post_to_teams()` to include Adaptive Cards or file-upload via Microsoft Graph  
- Improve error handling and retry logic for transient failures  
