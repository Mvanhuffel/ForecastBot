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
from typing import Dict, Set, Tuple, Optional

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
seen_ids_path = os.path.join(data_dir, "seen_ids_v2.json")
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

def load_seen_ids() -> Dict[str, str]:
    """Load seen IDs with their last seen date"""
    try:
        with open(seen_ids_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_seen_ids(seen: Dict[str, str]):
    """Save seen IDs with their last seen date"""
    with open(seen_ids_path, "w") as f:
        json.dump(seen, f, indent=2)

def format_opportunity_block(row: pd.Series) -> str:
    """Format a single opportunity into an HTML block for Teams"""
    dr = row["DOLLAR_RANGE"]
    dr_name = dr.get("display_name") if isinstance(dr, dict) else dr
    return (
        f"**Organization:** {row['ORGANIZATION']}<br/>"
        f"**NAICS:** {row['NAICS']}<br/>"
        f"**Est. Start:** {row['ESTIMATED_PERIOD_OF_PERFORMANCE_START']}<br/>"
        f"**Dollar Range:** {dr_name}<br/>"
        f"**Competitive:** {row['COMPETITIVE']}<br/>"
        f"**Requirement:** {row['REQUIREMENT']}<br/>"
    )

def format_disappeared_block(row: pd.Series, last_seen: str) -> str:
    """Format a disappeared opportunity into an HTML block for Teams"""
    block = format_opportunity_block(row)
    return f"{block}**Last Seen:** {last_seen}<br/>"

def get_header(count: int, type_str: str) -> str:
    """Generate header for Teams message"""
    now = datetime.now(ZoneInfo("America/New_York"))
    pulled = now.strftime("%B %d, %Y at %I:%M %p ET")
    emoji = "✅" if type_str == "new" else "❌"
    return (
        f"{emoji} **Forecast Bot {type_str.title()} Opportunities** ({count} {type_str})<br/>"
        f"{pulled}<br/>"
    )

def get_links_html(today: str) -> str:
    """Generate links section for Teams message"""
    dated_tag = f"forecast-{today}"
    csv_url = f"https://github.com/Mvanhuffel/ForecastBot/releases/download/{dated_tag}/filtered_forecast_{today}.csv"
    site_url = "https://apfs-cloud.dhs.gov/forecast/"
    return (
        f"[Download the latest filtered CSV]({csv_url}) | "
        f"[Visit the APFS Forecast site]({site_url})<br/><br/>"
    )

def process_opportunities(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, str]]:
    """Process opportunities and return new, disappeared, and updated seen IDs"""
    # Load current state
    seen_ids = load_seen_ids()
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    
    # Get current IDs
    current_ids = set(df["ID"].tolist())
    
    # Find new opportunities
    new_mask = [row_id not in seen_ids for row_id in df["ID"]]
    new_df = df.loc[new_mask]
    
    # Find disappeared opportunities
    disappeared_ids = set(seen_ids.keys()) - current_ids
    disappeared_df = pd.DataFrame()
    if disappeared_ids:
        # Load the last known state of disappeared opportunities
        try:
            last_csv = os.path.join(data_dir, "filtered_forecast.csv")
            historical_df = pd.read_csv(last_csv)
            disappeared_df = historical_df[historical_df["APFS Number"].isin(disappeared_ids)]
            # Rename column to match current df
            disappeared_df = disappeared_df.rename(columns={"APFS Number": "ID"})
        except (FileNotFoundError, pd.errors.EmptyDataError):
            logger.warning("Could not load historical data for disappeared opportunities")
    
    # Update seen IDs
    for row_id in current_ids:
        seen_ids[str(row_id)] = today
    
    return new_df, disappeared_df, seen_ids

def main():
    logger.info("Run started")
    try:
        # Fetch & normalize
        df = fetch_forecast()
        logger.info(f"Available columns from API: {sorted(df.columns.tolist())}")
        df.columns = df.columns.str.upper()

        # Filter on NAICS
        target = "541612 - Human Resources Consulting Services"
        df_filtered = df[df["NAICS"] == target]
        logger.info(f"Rows after filter: {len(df_filtered)}")

        # Process opportunities
        new_df, disappeared_df, seen_ids = process_opportunities(df_filtered)
        
        # Save state
        save_seen_ids(seen_ids)

        # Get today's date for filenames
        today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

        # Write filtered CSV
        dated_output_path = os.path.join(data_dir, f"filtered_forecast_{today}.csv")
        latest_output_path = os.path.join(data_dir, "filtered_forecast.csv")
        
        # Define target schema and rename columns as in original script
        desired_columns = [
            "APFS Number", "NAICS", "Component", "Title", "Contract Type",
            "Contract Vehicle", "Dollar Range", "Small Business Set-Aside",
            "Small Business Program", "Contract Status", "Contract Number",
            "Contractor", "Place of Performance City", "Place of Performance State",
            "Primary Contact First Name", "Primary Contact Last Name",
            "Primary Contact Phone", "Primary Contact Email", "Description",
            "Award Quarter", "Estimated Solicitation Release",
            "Forecast Published", "Forecast Previously Published"
        ]

        rename_map = {
            "ID": "APFS Number",
            "NAICS": "NAICS",
            "ORGANIZATION": "Component",
            "REQUIREMENTS_TITLE": "Title",
            "CONTRACT_TYPE": "Contract Type",
            "CONTRACT_VEHICLE": "Contract Vehicle",
            "DOLLAR_RANGE": "Dollar Range",
            "SMALL_BUSINESS_SET_ASIDE": "Small Business Set-Aside",
            "SMALL_BUSINESS_PROGRAM": "Small Business Program",
            "CONTRACT_STATUS": "Contract Status",
            "CONTRACT_NUMBER": "Contract Number",
            "CONTRACTOR": "Contractor",
            "PLACE_OF_PERFORMANCE_CITY": "Place of Performance City",
            "PLACE_OF_PERFORMANCE_STATE": "Place of Performance State",
            "REQUIREMENTS_CONTACT_FIRST_NAME": "Primary Contact First Name",
            "REQUIREMENTS_CONTACT_LAST_NAME": "Primary Contact Last Name",
            "REQUIREMENTS_CONTACT_PHONE": "Primary Contact Phone",
            "REQUIREMENTS_CONTACT_EMAIL": "Primary Contact Email",
            "REQUIREMENT": "Description",
            "AWARD_QUARTER": "Award Quarter",
            "ESTIMATED_SOLICITATION_RELEASE_DATE": "Estimated Solicitation Release",
            "PUBLISH_DATE": "Forecast Published",
            "PREVIOUS_PUBLISH_DATE": "Forecast Previously Published"
        }

        # Transform and save DataFrame
        df_export = df_filtered.rename(mapper=rename_map, axis=1)
        df_export = df_export[desired_columns]
        df_export.to_csv(dated_output_path, index=False)
        df_export.to_csv(latest_output_path, index=False)
        logger.info(f"Wrote filtered data to {dated_output_path} and {latest_output_path}")

        # Post new opportunities
        if len(new_df) > 0:
            new_blocks = [format_opportunity_block(row) for _, row in new_df.iterrows()]
            new_message = (
                get_header(len(new_blocks), "new") +
                get_links_html(today) +
                "<br/><br/>".join(new_blocks)
            )
            post_to_teams(teams_webhook, new_message)
            logger.info(f"Posted {len(new_blocks)} new opportunities")

        # Post disappeared opportunities
        if len(disappeared_df) > 0:
            disappeared_blocks = [
                format_disappeared_block(row, seen_ids[str(row["ID"])])
                for _, row in disappeared_df.iterrows()
            ]
            disappeared_message = (
                get_header(len(disappeared_blocks), "disappeared") +
                get_links_html(today) +
                "<br/><br/>".join(disappeared_blocks)
            )
            post_to_teams(teams_webhook, disappeared_message)
            logger.info(f"Posted {len(disappeared_blocks)} disappeared opportunities")

        logger.info("Run completed successfully")

    except Exception:
        logger.exception("Run failed with an error")
        sys.exit(1)

if __name__ == "__main__":
    main() 