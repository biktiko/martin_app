import streamlit as st
import pandas as pd

@st.cache_data(show_spinner=False)
def load_data(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    return df

def process_data(df: pd.DataFrame) -> pd.DataFrame:
    # Identify date columns
    DATE_COLS = [
        "activation_date","prize_receive_date","prize_delivery_date",
        "win_date","created_date","modify_date"
    ]
    for c in DATE_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)

    # --- Derived semantic columns ---
    # Normalize prize_id
    if "prize_id" in df.columns:
        if not pd.api.types.is_numeric_dtype(df["prize_id"]):
            df["prize_id"] = df["prize_id"].astype(str).str.strip()
            df.loc[df["prize_id"].str.lower().isin(["", "null", "none", "nan"]), "prize_id"] = pd.NA

    df["has_win"] = df["win_date"].notna() if "win_date" in df.columns else False

    if {"win_date","prize_id"} <= set(df.columns):
        df["is_real_prize"] = df["win_date"].notna() & df["prize_id"].notna()
        df["is_point_win"] = df["win_date"].notna() & df["prize_id"].isna()
    else:
        df["is_real_prize"] = False
        df["is_point_win"] = False

    def _win_type(row):
        if row["is_real_prize"]:
            return "real_prize"
        if row["is_point_win"]:
            return "points"
        return "no_win"

    df["win_type"] = df.apply(_win_type, axis=1)

    if "is_win_received" not in df.columns:
        df["is_win_received"] = False
    else:
        df["is_win_received"] = df["is_win_received"].astype(str).str.lower().isin(["1","true","yes","y","t"])

    # Points instantly received
    df.loc[df["is_point_win"], "is_win_received"] = True

    df["is_real_prize_received"] = df["is_real_prize"] & df["is_win_received"]
    df["is_real_prize_pending"] = df["is_real_prize"] & ~df["is_win_received"]

    REGION_MAP = {1: "Georgia", 2: "Armenia"}
    if "region_id" in df.columns:
        df["region_name"] = df["region_id"].map(REGION_MAP).fillna(df["region_id"].astype(str))
    else:
        df["region_name"] = "Unknown"
        
    return df

def get_user_col(df: pd.DataFrame):
    # user id column (customer_id приоритетно; fallback на user_id)
    return next((c for c in ["customer_id", "user_id"] if c in df.columns), None)
