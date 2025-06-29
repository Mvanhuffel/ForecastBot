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

# Paths for data & seen-IDs
data_dir      = os.path.join(project_root, "data", "processed")
seen_ids_path = os.path.join(data_dir, "seen_ids.json")
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
        with open(seen_ids_path) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_seen_ids(seen: set):
    with open(seen_ids_path, "w") as f:
        json.dump(sorted(seen), f)

def main():
    logger.info("Run started")
    try:
        # Fetch & normalize
        df = fetch_forecast()
        logger.info(f"Available columns from API: {sorted(df.columns.tolist())}")
        df.columns = df.columns.str.upper()

        # Filter on NAICS
        target      = "541612 - Human Resources Consulting Services"
        df_filtered = df[df["NAICS"] == target]
        logger.info(f"Rows after filter: {len(df_filtered)}")

        # Determine newly unseen rows
        seen_ids = load_seen_ids()
        ids_list = df_filtered["ID"].tolist()
        mask     = [row_id not in seen_ids for row_id in ids_list]
        new_df   = df_filtered.loc[mask]

        if new_df.shape[0] == 0:
            logger.info("No new opportunities—nothing to post.")
            return

        # Write full filtered CSV with date-based filename
        today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        dated_output_path = os.path.join(data_dir, f"filtered_forecast_{today}.csv")
        latest_output_path = os.path.join(data_dir, "filtered_forecast.csv")
        
        # Define target schema matching APFS site CSV
        desired_columns = [
            "APFS Number",
            "NAICS",
            "Component",
            "Title",
            "Contract Type",
            "Contract Vehicle",
            "Dollar Range",
            "Small Business Set-Aside",
            "Small Business Program",
            "Contract Status",
            "Contract Number",
            "Contractor",
            "Place of Performance City",
            "Place of Performance State",
            "Primary Contact First Name",
            "Primary Contact Last Name",
            "Primary Contact Phone",
            "Primary Contact Email",
            "Description",
            "Award Quarter",
            "Estimated Solicitation Release",
            "Forecast Published",
            "Forecast Previously Published"
        ]

        # Map API JSON keys to APFS CSV headers
        rename_map = {
            # 1. APFS Number
            "ID": "APFS Number",

            # 2. NAICS
            "NAICS": "NAICS",

            # 3. Component
            "ORGANIZATION": "Component",

            # 4. Title
            "REQUIREMENTS_TITLE": "Title",

            # 5. Contract Type
            "CONTRACT_TYPE": "Contract Type",

            # 6. Contract Vehicle
            "CONTRACT_VEHICLE": "Contract Vehicle",

            # 7. Dollar Range
            "DOLLAR_RANGE": "Dollar Range",

            # 8. Small Business Set-Aside
            "SMALL_BUSINESS_SET_ASIDE": "Small Business Set-Aside",

            # 9. Small Business Program
            "SMALL_BUSINESS_PROGRAM": "Small Business Program",

            # 10. Contract Status
            "CONTRACT_STATUS": "Contract Status",

            # 11. Contract Number
            "CONTRACT_NUMBER": "Contract Number",

            # 12. Contractor
            "CONTRACTOR": "Contractor",

            # 13. Place of Performance City
            "PLACE_OF_PERFORMANCE_CITY": "Place of Performance City",

            # 14. Place of Performance State
            "PLACE_OF_PERFORMANCE_STATE": "Place of Performance State",

            # 15-18. Primary Contact First/Last/Phone/Email
            "REQUIREMENTS_CONTACT_FIRST_NAME": "Primary Contact First Name",
            "REQUIREMENTS_CONTACT_LAST_NAME": "Primary Contact Last Name",
            "REQUIREMENTS_CONTACT_PHONE": "Primary Contact Phone",
            "REQUIREMENTS_CONTACT_EMAIL": "Primary Contact Email",

            # 19. Description (the full text of the requirement)
            "REQUIREMENT": "Description",

            # 20. Award Quarter
            "AWARD_QUARTER": "Award Quarter",

            # 21. Estimated Solicitation Release
            "ESTIMATED_SOLICITATION_RELEASE_DATE": "Estimated Solicitation Release",

            # 22. Forecast Published
            "PUBLISH_DATE": "Forecast Published",

            # 23. Forecast Previously Published
            "PREVIOUS_PUBLISH_DATE": "Forecast Previously Published"
        }

        # Transform DataFrame to match APFS CSV structure
        df_export = df_filtered.rename(mapper=rename_map, axis=1)  # type: ignore
        df_export = df_export[desired_columns]
        
        # Write to dated file
        df_export.to_csv(dated_output_path, index=False)
        logger.info(f"Wrote filtered data to {dated_output_path}")
        
        # Copy to latest
        df_export.to_csv(latest_output_path, index=False)
        logger.info(f"Updated latest filtered data at {latest_output_path}")

        # Build HTML summary blocks for new_df
        cols   = [
            "ORGANIZATION",
            "NAICS",
            "ESTIMATED_PERIOD_OF_PERFORMANCE_START",
            "DOLLAR_RANGE",
            "COMPETITIVE",
            "REQUIREMENT",
        ]
        blocks = []
        for _, row in new_df[cols].iterrows():
            dr      = row["DOLLAR_RANGE"]
            dr_name = dr.get("display_name") if isinstance(dr, dict) else dr
            blocks.append(
                f"**Organization:** {row['ORGANIZATION']}<br/>"
                f"**NAICS:** {row['NAICS']}<br/>"
                f"**Est. Start:** {row['ESTIMATED_PERIOD_OF_PERFORMANCE_START']}<br/>"
                f"**Dollar Range:** {dr_name}<br/>"
                f"**Competitive:** {row['COMPETITIVE']}<br/>"
                f"**Requirement:** {row['REQUIREMENT']}<br/>"
            )

        # Header with timestamp
        now    = datetime.now(ZoneInfo("America/New_York"))
        pulled = now.strftime("%B %d, %Y at %I:%M %p ET")
        header = (
            f"✅ **Forecast Bot Summary** ({len(blocks)} new opportunities)<br/>"
            f"{pulled}<br/>"
        )

        # Links immediately after header on the same level, with pipe separator
        dated_tag = f"forecast-{today}"
        csv_url = f"https://github.com/Mvanhuffel/ForecastBot/releases/download/{dated_tag}/filtered_forecast_{today}.csv"
        site_url = "https://apfs-cloud.dhs.gov/forecast/"
        links_html = (
            f"[Download the latest filtered CSV]({csv_url}) | "
            f"[Visit the APFS Forecast site]({site_url})<br/><br/>"
        )

        # Combine and post: header → links → details
        message = header + links_html + "<br/><br/>".join(blocks)
        post_to_teams(teams_webhook, message)

        # Persist seen IDs
        seen_ids |= set(new_df["ID"])
        save_seen_ids(seen_ids)

        logger.info("Run completed successfully")

    except Exception:
        logger.exception("Run failed with an error")
        sys.exit(1)

if __name__ == "__main__":
    main()
