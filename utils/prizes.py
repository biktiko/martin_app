import json
import os
import pandas as pd

PRIZE_MAPPING_FILE = "prize_mapping.json"

DEFAULT_PRIZES = {
    "21": "Անլար լիցքավորիչ (Armenia)",
    "22": "Էլեկտրական թեյնիկ (Armenia)",
    "23": "Արդուկ (Armenia)",
    "24": "Ֆեն (Armenia)",
    "25": "Բարձրախոս (Armenia)",
    "26": "Հեծանիվ (Armenia)",
    "27": "Ինքնագլոր (Armenia)",
    "28": "Գնդակ (Armenia)",
    "29": "Բաժակ (Armenia)",
    "30": "Автомобиль BYD E2 (Armenia)",
    "31": "Ուղեգիր 2 հոգու Եգիպտոս (Armenia)",
    "32": "Apple iPhone 17 (Armenia)",
    "33": "PSP 5 (Armenia)",
    "34": "Dyson Airstrait (Armenia)",
    "35": "iPad 11 (Armenia)",
    "36": "Apple Watch SE 2 40mm (Armenia)",
    "37": "Asus Vivobook F1504GA-WS36 (Armenia)",
    "38": "JBL Flip 6 (Armenia)",
    "39": "AirPods 4 (Armenia)",
    "40": "Բլենդեր (Armenia)"
}

def load_prize_map():
    if not os.path.exists(PRIZE_MAPPING_FILE):
        save_prize_map(DEFAULT_PRIZES)
        return DEFAULT_PRIZES
    
    try:
        with open(PRIZE_MAPPING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_PRIZES

def save_prize_map(mapping):
    with open(PRIZE_MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=4)

def enrich_with_prize_name(df, prize_col="prize_id"):
    """
    Adds a 'prize_name' column to the dataframe based on the prize_col.
    """
    if prize_col not in df.columns:
        df["prize_name"] = None
        return df

    mapping = load_prize_map()
    
    # Prepare lookup series
    # We want "Name" format only (as requested).
    # Convert mapping to string keys and pre-format values
    lookup_dict = {}
    for k, v in mapping.items():
        s_k = str(k)
        lookup_dict[s_k] = v
        
    # Convert column to string once
    s_col = df[prize_col].astype(str)
    
    # Fix for float-like strings (e.g. "29.0" -> "29")
    # This happens if prize_id was read as float
    s_col = s_col.str.replace(r"\.0$", "", regex=True)
    
    # Map values
    # map is much faster than apply
    mapped = s_col.map(lookup_dict)
    
    # For missing values in map (but present in data), we want "ID (Unknown)"
    # We can identify them by isna() in mapped but not isna() in original (if we handled original NaNs)
    # But simpler: fillna with a fallback
    
    # Optimization: Only do the fallback formatting for rows that didn't match
    # But vectorized string operations are fast enough usually.
    
    # Let's try a pure vectorized approach
    # 1. Create a Series for the column
    # 2. Map knowns
    # 3. Fill unknowns
    
    df["prize_name"] = mapped
    
    # Fill NaNs where the original ID was not NaN but mapping failed
    # (If original ID was NaN/None, s_col might be 'nan' or 'None' depending on pandas version/data, 
    #  but usually we want prize_name to be None if prize_id is None)
    
    # Let's handle the "Unknown" case efficiently
    mask_missing_map = df["prize_name"].isna() & df[prize_col].notna()
    
    if mask_missing_map.any():
        # Only format the missing ones
        # This is still somewhat slow if MANY are missing, but usually most are found.
        missing_ids = df.loc[mask_missing_map, prize_col].astype(str)
        df.loc[mask_missing_map, "prize_name"] = missing_ids + " (Unknown)"
        
    return df
