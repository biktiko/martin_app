import streamlit as st
import pandas as pd
import json
import os
import re
import glob
import shutil

CSV_FOLDER = "csv_data"

def get_folder_signature(folder_path=CSV_FOLDER) -> str:
    """
    Generates a unique string signature based on the names, sizes, and last modified times
    of all .csv files in the folder to handle automatic Streamlit cache invalidation.
    """
    if not os.path.exists(folder_path):
        return ""
    files = sorted(glob.glob(os.path.join(folder_path, "*.csv")))
    sig_parts = []
    for f in files:
        try:
            stat = os.stat(f)
            sig_parts.append(f"{os.path.basename(f)}:{stat.st_size}:{stat.st_mtime}")
        except Exception:
            pass
    return ",".join(sig_parts)

@st.cache_data(show_spinner=False)
def load_data(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    return df

@st.cache_data(show_spinner=False)
def load_data_from_folder(folder_path=CSV_FOLDER, folder_signature: str = "") -> pd.DataFrame:
    """
    Loads all .csv files from the specified folder and combines their rows.
    If the folder is empty but 'qr_code.csv' exists in the root, it copies it over first.
    """
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)

    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    
    # Auto-migration/fallback logic for the first run
    if not csv_files:
        root_default = "qr_code.csv"
        if os.path.exists(root_default):
            try:
                shutil.copy(root_default, os.path.join(folder_path, root_default))
                csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
            except Exception as e:
                st.sidebar.error(f"Не удалось скопировать {root_default} в {folder_path}: {e}")

    if not csv_files:
        st.error(f"В папке '{folder_path}' не найдено ни одного .csv файла. Пожалуйста, добавьте CSV-файлы в эту папку.")
        return pd.DataFrame()

    dfs = []
    for file in csv_files:
        try:
            df = pd.read_csv(file)
            if not df.empty:
                dfs.append(df)
        except Exception as e:
            st.error(f"Ошибка при чтении файла {os.path.basename(file)}: {e}")

    if not dfs:
        st.error("Не удалось прочитать данные ни из одного CSV файла в папке.")
        return pd.DataFrame()

    # Combine all dataframes
    combined_df = pd.concat(dfs, ignore_index=True)
    
    if not combined_df.empty:
        # Deduplicate by primary key "id" if available
        if "id" in combined_df.columns:
            combined_df = combined_df.drop_duplicates(subset=["id"], keep="first")
            
    return combined_df


def process_data(df: pd.DataFrame) -> pd.DataFrame:
    # Exclude scans from user 21541 (the user themselves) from the entire dataset
    user_col = next((c for c in ["customer_id", "user_id"] if c in df.columns), None)
    if user_col and user_col in df.columns:
        df = df[df[user_col].astype(str).str.split('.').str[0].str.strip() != "21541"]

    # Identify date columns
    DATE_COLS = [
        "activation_date","prize_receive_date","prize_delivery_date",
        "win_date","created_date","modify_date"
    ]
    for c in DATE_COLS:
        if c in df.columns:
            # Optimization: cache unique values to speed up datetime conversion
            unique_dates = df[c].dropna().unique()
            date_dict = {d: pd.to_datetime(d, errors="coerce", utc=True) for d in unique_dates}
            df[c] = df[c].map(date_dict)

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

    # Fill missing win_date with created_date for no_win scans so they are not dropped
    if "win_date" in df.columns and "created_date" in df.columns:
        df["win_date"] = df["win_date"].fillna(df["created_date"])
        
    # Deduplicate by win_date + customer_id now that dates are normalized
    if user_col and "win_date" in df.columns:
        df = df.drop_duplicates(subset=["win_date", user_col], keep="first")

    return df

def get_user_col(df: pd.DataFrame):
    # user id column (customer_id приоритетно; fallback на user_id)
    return next((c for c in ["customer_id", "user_id"] if c in df.columns), None)

def enrich_with_product_info(df):
    mapping_path = os.path.join("utils", "product_mapping.json")
    
    # Identify the product ID column (prioritize new name 'product_id')
    pid_col = next((c for c in ["product_id", "product_campaign_id"] if c in df.columns), None)
    
    if os.path.exists(mapping_path) and pid_col:
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        
        # Normalize to string and clean it
        def _normalize_id(val):
            if pd.isna(val) or val == "": return "None"
            s = str(val)
            s = re.sub(r'\.0$', '', s)
            return s.strip()

        df["product_id_str"] = df[pid_col].apply(_normalize_id)
        
        df["product_name"] = df["product_id_str"].apply(lambda x: mapping.get(x, {}).get("name", f"ID {x}"))
        df["product_category"] = df["product_id_str"].apply(lambda x: mapping.get(x, {}).get("category", "Unknown"))
    else:
        if "product_name" not in df.columns:
            df["product_name"] = "Unknown"
        if "product_category" not in df.columns:
            df["product_category"] = "Unknown"
        if "product_id_str" not in df.columns:
            df["product_id_str"] = "None"
    return df
