import os
import json
import re
import datetime as dt
import pandas as pd

CALLED_NUMBERS_FILE = "called_numbers.json"

def normalize_phone(phone_val) -> str:
    """
    Standardizes Armenian and Georgian mobile phone numbers to their canonical formats:
    - Armenia: 374XXXXXXXX (11 digits)
    - Georgia: 995XXXXXXXXX (12 digits)
    """
    if phone_val is None or (isinstance(phone_val, float) and pd.isna(phone_val)):
        return ""
        
    # Convert to string and clean float representation (.0)
    phone_str = str(phone_val).strip()
    phone_str = re.sub(r'\.0$', '', phone_str)
    
    # Extract only digits
    digits = "".join(c for c in phone_str if c.isdigit())
    if not digits:
        return ""
    
    # 1. Georgian Mobile Numbers
    # Canonical: starts with 995 and has 12 digits
    if digits.startswith("995") and len(digits) == 12:
        return digits
    # 9 digits (no country code), e.g., 557767743 -> 995557767743
    if len(digits) == 9 and digits.startswith(("5", "7", "9")):
        return "995" + digits
    # 10 digits starting with 0, e.g., 0557767743 -> 995557767743
    if len(digits) == 10 and digits.startswith("0"):
        return "995" + digits[1:]
        
    # 2. Armenian Mobile Numbers
    # Canonical: starts with 374 and has 11 digits
    if digits.startswith("374") and len(digits) == 11:
        return digits
    # 8 digits (no country code), e.g., 98199628 -> 37498199628
    if len(digits) == 8:
        return "374" + digits
    # 9 digits starting with 0, e.g., 098199628 -> 37498199628
    if len(digits) == 9 and digits.startswith("0"):
        return "374" + digits[1:]
        
    # Fallback for other formats/lengths
    if len(digits) >= 8:
        return digits
    return ""


def load_called_numbers() -> dict:
    """Loads called numbers from the JSON file. Returns a dict mapping normalized phone to metadata."""
    if not os.path.exists(CALLED_NUMBERS_FILE):
        return {}
    try:
        with open(CALLED_NUMBERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # Backwards/fallback compatibility: convert list to dict
                return {normalize_phone(num): {"added_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} for num in data if normalize_phone(num)}
            return data
    except Exception:
        return {}


def save_called_numbers(called_dict: dict):
    """Saves called numbers dict to the JSON file."""
    try:
        with open(CALLED_NUMBERS_FILE, "w", encoding="utf-8") as f:
            json.dump(called_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving called numbers: {e}")


def extract_and_normalize_phones(text: str) -> list:
    """
    Parses any text block to extract all valid phone numbers.
    Supports lists separated by newlines, commas, semicolons, spaces, and even comments.
    """
    if not text:
        return []
        
    lines = text.splitlines()
    normalized_list = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for inline list delimiters (comma or semicolon)
        tokens = []
        if "," in line:
            tokens = line.split(",")
        elif ";" in line:
            tokens = line.split(";")
        else:
            tokens = [line]
            
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue
                
            # Direct normalization first
            norm = normalize_phone(tok)
            if norm:
                normalized_list.append(norm)
            else:
                # If direct normalization failed, search for patterns within the text
                # We look for a sequence of 8-12 digits in the cleaned string
                digits_only = "".join(c for c in tok if c.isdigit())
                match = re.search(r'\b(374\d{8}|995\d{9}|0\d{8,9}|\d{8,9})\b', digits_only)
                if match:
                    norm = normalize_phone(match.group(1))
                    if norm:
                        normalized_list.append(norm)
                        continue
                
                # Search with regex allowing spaces/dashes between digits (e.g. +374 98 19-96-28)
                match_raw = re.search(r'(\+?\d[\d\s\-\(\)]{6,}\d)', tok)
                if match_raw:
                    norm = normalize_phone(match_raw.group(1))
                    if norm:
                        normalized_list.append(norm)
                        
    # Deduplicate while preserving order
    return list(dict.fromkeys(normalized_list))


def add_called_numbers(raw_text: str, comment: str = "Manually added") -> list:
    """
    Extracts phone numbers from raw_text, normalizes them, 
    adds them to the JSON store, and returns the list of successfully added numbers.
    """
    phones_to_add = extract_and_normalize_phones(raw_text)
    if not phones_to_add:
        return []
        
    called_dict = load_called_numbers()
    now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    added = []
    for ph in phones_to_add:
        if ph not in called_dict:
            called_dict[ph] = {
                "added_at": now_str,
                "comment": comment
            }
            added.append(ph)
            
    if added:
        save_called_numbers(called_dict)
        
    return added


def remove_called_number(phone: str) -> bool:
    """Removes a phone number from the JSON store. Returns True if removed."""
    norm = normalize_phone(phone)
    if not norm:
        return False
        
    called_dict = load_called_numbers()
    if norm in called_dict:
        del called_dict[norm]
        save_called_numbers(called_dict)
        return True
    return False
