import requests
from bs4 import BeautifulSoup
import pandas as pd
import sqlite3
import json
from datetime import datetime

URL = "https://web.archive.org/web/2024/https://en.wikipedia.org/wiki/List_of_countries_by_GDP_(nominal)"
JSON_FILE   = "Countries_by_GDP.json"
DB_FILE     = "World_Economies.db"
TABLE_NAME  = "Countries_by_GDP"
LOG_FILE    = "etl_project_log.txt"


def log(message: str):
    ts = datetime.now().strftime("%Y-%b-%d-%H:%M:%S")
    entry = f"{ts}, {message}"
    print(entry)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


def extract(url: str) -> pd.DataFrame:
    """Scrape IMF GDP data from Wikipedia archive."""
    log("Extract phase Started")

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    tables = soup.find_all("table", {"class": "wikitable"})

    rows = []
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        caption = table.find("caption")
        caption_text = caption.get_text(strip=True) if caption else ""
        if "IMF" not in caption_text and not any("IMF" in h for h in headers):
            pass

        for tr in table.find_all("tr")[1:]:
            cols = tr.find_all(["td", "th"])
            if len(cols) < 2:
                continue
            country = cols[0].get_text(strip=True)
            gdp_raw = cols[1].get_text(strip=True).replace(",", "").replace("—", "").replace("–", "")

            if not country or not gdp_raw:
                continue
            try:
                gdp_billion = round(float(gdp_raw) / 1_000, 2)
                rows.append({"Country": country, "GDP_USD_billion": gdp_billion})
            except ValueError:
                continue

        if rows:
            break

    df = pd.DataFrame(rows).drop_duplicates(subset="Country")
    log(f"Extract phase Ended — {len(df)} records extracted")
    return df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Round GDP to 2 decimal places and drop invalid rows."""
    log("Transform phase Started")

    df = df.dropna(subset=["Country", "GDP_USD_billion"])
    df = df[df["GDP_USD_billion"] > 0]
    df["GDP_USD_billion"] = df["GDP_USD_billion"].round(2)
    df = df.sort_values("GDP_USD_billion", ascending=False).reset_index(drop=True)

    log(f"Transform phase Ended — {len(df)} records after transform")
    return df


def load(df: pd.DataFrame):
    """Save to JSON and SQLite."""
    log("Load phase Started")

    df.to_json(JSON_FILE, orient="records", indent=2)
    log(f"Saved JSON → {JSON_FILE}")

    conn = sqlite3.connect(DB_FILE)
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()
    log(f"Saved DB  → {DB_FILE} / table '{TABLE_NAME}'")

    log("Load phase Ended")


def query_top_economies(threshold: float = 100.0):
    """Print countries with GDP > threshold billion USD."""
    log(f"Query: GDP > {threshold} billion USD")

    conn = sqlite3.connect(DB_FILE)
    query = f"""
        SELECT Country, GDP_USD_billion
        FROM {TABLE_NAME}
        WHERE GDP_USD_billion > {threshold}
        ORDER BY GDP_USD_billion DESC
    """
    result = pd.read_sql_query(query, conn)
    conn.close()

    print("\n── Economies with GDP > 100 billion USD ──")
    print(result.to_string(index=False))
    print(f"\nTotal: {len(result)} countries\n")
    log(f"Query returned {len(result)} records")


if __name__ == "__main__":
    log("ETL Job Started")

    df_raw        = extract(URL)
    df_transformed = transform(df_raw)
    load(df_transformed)
    query_top_economies(100)

    log("ETL Job Ended")
