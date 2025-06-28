import time
import sys
import os
import json
import requests
import pandas as pd
import logging
from logging.handlers import RotatingFileHandler
import yaml
from datetime import datetime
from zoneinfo import ZoneInfo

# ─── Setup paths and logging ───────────────────────────────────────────────────
script_dir   = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# Load configuration
with open(os.path.join(project_root, "config", "settings.yaml")) as f:
    cfg = yaml.safe_load(f)
teams_webhook = os.getenv("TEAMS_WEBHOOK_URL") or cfg["teams"]["webhook_url"]

# Configure logger
log_dir  = os.path.join(project_root, "logs")
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, "forecast_bot.log")
logger   = logging.getLogger("forecast_bot")
logger.setLevel(logging.INFO)
handler  = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

# Path to seen-IDs file
data_dir       = os.path.join(project_root, "data", "processed")
seen_ids_path  = os.path.join(data_dir, "seen_ids.json")
os.makedirs(data_dir, exist_ok=True)

def fetch_forecast() -> pd.DataFrame:
    ts  = int(time.time() * 1000)
    url = f"https://apfs-cloud.dhs.gov/api/forecast/?_={ts}"
    r   = requests.get(url)
    r.raise_for_status()
    return pd.DataFrame(r.json())

def post_to_teams(webhook_url: str, message: str):
    payload = {"text": message}
    resp = requests.post(webhook_url, json=payload)
    resp.raise_for_status()
    logger.info("Posted notification to Teams")

def load_seen_ids() -> set:
    try:
        with open(seen_ids_path, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen_ids(seen: set):
    with open(seen_ids_path, "w") as f:
        json.dump(sorted(seen), f)

def main():
    logger.info("Run started")
    try:
        # 1) Fetch and normalize
        df = fetch_forecast()
        df.columns = df.columns.str.upper()

        # 2) Filter on NAICS
        target      = "541612 - Human Resources Consulting Services"
        df_filtered = df[df["NAICS"] == target]
        logger.info(f"Rows after filter: {len(df_filtered)}")

        # 3) Load previously seen IDs and compute new rows
        seen_ids = load_seen_ids()
        new_df = df_filtered[~df_filtered["ID"].isin(seen_ids)]
        if new_df.empty:
            logger.info("No new opportunities—nothing to post.")
            return

        # 4) Write full CSV (as before)
        output_path = os.path.join(data_dir, "filtered_forecast.csv")
        df_filtered.to_csv(output_path, index=False)
        logger.info(f"Wrote filtered data to {output_path}")

        # 5) Build and send summary for just the NEW rows
        cols = [
            "ORGANIZATION",
            "NAICS",
            "ESTIMATED_PERIOD_OF_PERFORMANCE_START",
            "DOLLAR_RANGE",
            "COMPETITIVE",
            "REQUIREMENT",
        ]
        blocks = []
        for _, row in new_df[cols].iterrows():
            dr = row["DOLLAR_RANGE"]
            dr_name = dr.get("display_name") if isinstance(dr, dict) else dr
            block = (
                f"**Organization:** {row['ORGANIZATION']}<br/>"
                f"**NAICS:** {row['NAICS']}<br/>"
                f"**Est. Start:** {row['ESTIMATED_PERIOD_OF_PERFORMANCE_START']}<br/>"
                f"**Dollar Range:** {dr_name}<br/>"
                f"**Competitive:** {row['COMPETITIVE']}<br/>"
                f"**Requirement:** {row['REQUIREMENT']}<br/>"
            )
            blocks.append(block)

        # build header with timestamp
        now    = datetime.now(ZoneInfo("America/New_York"))
        pulled = now.strftime("%B %d, %Y at %I:%M %p ET")
        header = (
            f"✅ **Forecast Bot Summary** ({len(blocks)} new opportunities)<br/>"
            f"{pulled}<br/><br/>"
        )
        message = header + "<br/><br/>".join(blocks)
        post_to_teams(teams_webhook, message)

        # 6) Update seen IDs and save
        seen_ids |= set(new_df["ID"])
        save_seen_ids(seen_ids)

        logger.info("Run completed successfully")
    except Exception:
        logger.exception("Run failed with an error")
        sys.exit(1)

if __name__ == "__main__":
    main()
