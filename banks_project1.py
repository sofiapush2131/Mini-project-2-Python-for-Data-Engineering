import requests
from bs4 import BeautifulSoup
import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime

URL = "https://web.archive.org/web/2024/https://en.wikipedia.org/wiki/List_of_largest_banks"
EXCHANGE_RATE_CSV = "exchange_rate.csv"
OUTPUT_CSV  = "Largest_banks_data.csv"
DB_FILE     = "Banks.db"
TABLE_NAME  = "Largest_banks"
LOG_FILE    = "code_log.txt"


def log_progress(message: str):
    """Log message with timestamp to log file and console."""
    ts = datetime.now().strftime("%Y-%h-%d-%H:%M:%S")
    entry = f"{ts} : {message}"
    print(entry)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


def extract(url: str, table_attribs: list) -> pd.DataFrame:
    """
    Extract top-10 largest banks table from Wikipedia archive
    under the heading 'By market capitalization'.
    """
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    df = pd.DataFrame(columns=table_attribs)
    rows = []

    tables = soup.find_all("table", {"class": "wikitable"})
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if any("Market" in h or "Capitalization" in h or "market" in h for h in headers):
            for tr in table.find_all("tr")[1:]:
                cols = tr.find_all("td")
                if len(cols) < 3:
                    continue
                name    = cols[1].get_text(strip=True)
                mc_raw  = cols[2].get_text(strip=True).replace(",", "").replace("\n", "")
                try:
                    mc_usd = float(mc_raw)
                    rows.append({"Name": name, "MC_USD_Billion": round(mc_usd, 2)})
                except ValueError:
                    continue
            break

    df = pd.DataFrame(rows[:10], columns=table_attribs)
    return df


def transform(df: pd.DataFrame, csv_path: str) -> pd.DataFrame:
    """
    Add MC_GBP_Billion, MC_EUR_Billion, MC_INR_Billion columns
    using exchange rates from CSV file.
    """
    exchange_df = pd.read_csv(csv_path, header=0, index_col=0)
    exchange_rate = exchange_df["Rate"].to_dict()

    df["MC_GBP_Billion"] = [round(x * exchange_rate["GBP"], 2) for x in df["MC_USD_Billion"]]
    df["MC_EUR_Billion"] = [round(x * exchange_rate["EUR"], 2) for x in df["MC_USD_Billion"]]
    df["MC_INR_Billion"] = [round(x * exchange_rate["INR"], 2) for x in df["MC_USD_Billion"]]

    return df


def load_to_csv(df: pd.DataFrame, output_path: str):
    """Save transformed DataFrame to CSV file."""
    df.to_csv(output_path, index=False)


def load_to_db(df: pd.DataFrame, sql_connection, table_name: str):
    """Save transformed DataFrame to SQLite table."""
    df.to_sql(table_name, sql_connection, if_exists="replace", index=False)


def run_query(query_statement: str, sql_connection):
    """Execute SQL query and print results."""
    print(f"SQL: {query_statement}")
    result = pd.read_sql_query(query_statement, sql_connection)
    print(result.to_string(index=False))
    return result


if __name__ == "__main__":

    table_attribs = ["Name", "MC_USD_Billion"]

    import os
    if not os.path.exists(EXCHANGE_RATE_CSV):
        ex_data = pd.DataFrame({
            "Currency": ["EUR", "GBP", "INR"],
            "Rate":     [0.93,  0.80,  82.95]
        })
        ex_data.to_csv(EXCHANGE_RATE_CSV, index=False)
        log_progress(f"Created default {EXCHANGE_RATE_CSV}")

    ex_check = pd.read_csv(EXCHANGE_RATE_CSV)
    if "Currency" in ex_check.columns:
        ex_check = ex_check.set_index("Currency")
        ex_check.to_csv(EXCHANGE_RATE_CSV)

    log_progress("Preliminaries complete. Initiating ETL process")

    log_progress("Data extraction started")
    df = extract(URL, table_attribs)
    log_progress("Data extraction complete")

    print(df)

    log_progress("Data transformation started")
    df = transform(df, EXCHANGE_RATE_CSV)
    log_progress("Data transformation complete")

    print(df)

    print(f"\nMC_EUR_Billion of 5th bank: {df['MC_EUR_Billion'].iloc[4]}")

    log_progress("Data loading to CSV started")
    load_to_csv(df, OUTPUT_CSV)
    log_progress(f"Data saved to CSV: {OUTPUT_CSV}")

    log_progress("Data loading to Database started")
    conn = sqlite3.connect(DB_FILE)
    load_to_db(df, conn, TABLE_NAME)
    log_progress(f"Data saved to DB: {DB_FILE} / table '{TABLE_NAME}'")

    log_progress("Running queries")

    run_query(f"SELECT * FROM {TABLE_NAME}", conn)

    run_query(
        f"SELECT Name, MC_GBP_Billion FROM {TABLE_NAME} LIMIT 5",
        conn
    )

    run_query(
        f"SELECT Name, MC_EUR_Billion FROM {TABLE_NAME} LIMIT 5",
        conn
    )

    run_query(
        f"SELECT Name, MC_INR_Billion FROM {TABLE_NAME} LIMIT 5",
        conn
    )

    run_query(
        f"SELECT AVG(MC_GBP_Billion) FROM {TABLE_NAME}",
        conn
    )

    conn.close()
    log_progress("Query execution complete")
    log_progress("ETL process complete")
