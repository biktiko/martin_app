import streamlit as st
import pandas as pd
import datetime as dt

# Imports from our new modules
from utils.auth import require_auth
from utils.db import check_db_connection
from utils.data import load_data, process_data, get_user_col
from tabs.basic_analytics import render_basic_analytics
from tabs.advanced_analytics import render_advanced_analytics

# ----------------------------- Config & Auth ----------------------------------
st.set_page_config(page_title="QR Code Analytics", layout="wide")

# Enforce authentication
require_auth()

# ----------------------------- Sidebar & Data Loading -------------------------
st.sidebar.header("Загрузка данных")
uploaded_file = st.sidebar.file_uploader("Выберите CSV файл", type="csv")

# Button to clear cache
if st.sidebar.button("Обновить/очистить кэш данных"):
    load_data.clear()
    st.rerun()

# Load raw data
if uploaded_file is not None:
    raw_df = load_data(uploaded_file)
else:
    raw_df = load_data("qr_code.csv")

# Process data (add derived columns)
df = process_data(raw_df.copy())

# ----------------------------- Global Settings & Filters ----------------------
st.sidebar.header("Фильтры")

# User ID Column Selection
USER_COL = get_user_col(df)
candidate_ids = [c for c in df.columns if (
    c in ["customer_id","user_id","msisdn","phone","user_uuid","uuid"]
    or c.lower().endswith("_id")
)]
if not candidate_ids and USER_COL:
    candidate_ids = [USER_COL]
if candidate_ids:
    default_idx = candidate_ids.index(USER_COL) if USER_COL in candidate_ids else 0
    USER_COL = st.sidebar.selectbox("Поле идентификатора пользователя", options=candidate_ids, index=default_idx)
USER_LABEL = USER_COL

local_tz = st.sidebar.selectbox("Часовой пояс отображения", ["UTC","Asia/Yerevan"], index=1)

# --- 1. Global Segmentation (Pre-Filter) ---
if USER_COL:
    # Calculate global frequency for segmentation based on FULL data
    user_freq = df.groupby(USER_COL).size()
    def _get_segment(c):
        if c == 1: return "Novice (1 scan)"
        elif c <= 5: return "Active (2-5 scans)"
        else: return "Power User (6+ scans)"
    
    # Map to dataframe
    # Use map for speed, fillna for safety
    df["user_segment"] = df[USER_COL].map(user_freq).fillna(0).apply(_get_segment)
else:
    df["user_segment"] = "Unknown"

# --- 2. Global Filters (Create filtered_df) ---
filtered_df = df.copy()

# A. Region Filter
if "region_name" in filtered_df.columns:
    region_values = sorted([x for x in filtered_df["region_name"].unique() if pd.notna(x)])
    selected_regions = st.sidebar.multiselect("Регионы", region_values, default=region_values)
    if selected_regions:
        filtered_df = filtered_df[filtered_df["region_name"].isin(selected_regions)]

# B. Prize ID Filter (NEW)
if "prize_id" in filtered_df.columns:
    all_prizes = filtered_df["prize_id"].dropna().unique()
    # Convert to string for sorting/display consistency
    all_prizes_list = sorted([str(p) for p in all_prizes])
    if all_prizes_list:
        selected_prizes = st.sidebar.multiselect("Фильтр по prize_id", all_prizes_list, default=[])
        if selected_prizes:
            # Filter converting column to string to match selection
            filtered_df = filtered_df[filtered_df["prize_id"].astype(str).isin(selected_prizes)]

# C. User Segment Filter (NEW)
if USER_COL:
    all_segments = sorted(filtered_df["user_segment"].unique())
    selected_segments = st.sidebar.multiselect("Сегмент пользователей", all_segments, default=[])
    if selected_segments:
        filtered_df = filtered_df[filtered_df["user_segment"].isin(selected_segments)]

# D. Win Type Filter
win_type_values = ["real_prize","points","no_win"]
selected_win_types = st.sidebar.multiselect("Тип выигрыша", win_type_values, default=win_type_values)
filtered_df = filtered_df[filtered_df["win_type"].isin(selected_win_types)]

# E. Received Filter
received_filter = st.sidebar.selectbox("Получение приза (is_win_received)", ["Все","Только получен","Не получен"])
if received_filter == "Только получен":
    filtered_df = filtered_df[filtered_df["is_win_received"]]
elif received_filter == "Не получен":
    filtered_df = filtered_df[~filtered_df["is_win_received"]]

# --- 3. Date Filtering (Create work) ---
# Hardcoded start date
START_FROM_STR = "2025-09-15"
START_FROM = pd.Timestamp(START_FROM_STR, tz="UTC")

if "win_date" not in df.columns:
    st.error("Колонка win_date отсутствует — временные графики недоступны.")
    st.stop()

# Prepare working dataset from filtered_df
work = filtered_df.copy()
work = work.dropna(subset=["win_date"])

if local_tz != "UTC":
    work["win_date"] = work["win_date"].dt.tz_convert(local_tz)
    start_dt_local = START_FROM.tz_convert(local_tz)
else:
    start_dt_local = START_FROM

# Filter by hardcoded start date
work = work[work["win_date"] >= start_dt_local]

# Slider for date range
if not work.empty:
    actual_min = work["win_date"].min()
    actual_max = work["win_date"].max()

    slider_min = max(start_dt_local, actual_min)
    slider_max = actual_max

    # Check if min > max (can happen if data is weird or empty after filter)
    if slider_min > slider_max:
        slider_min = slider_max

    win_range = st.sidebar.slider(
        "Диапазон по win_date (≥ 15.09.2025)",
        min_value=slider_min.to_pydatetime(),
        max_value=slider_max.to_pydatetime(),
        value=(slider_min.to_pydatetime(), slider_max.to_pydatetime()),
        format="DD.MM.YYYY"
    )

    # Apply slider filter
    def _ensure_tz_runtime(dt_obj, tzinfo):
        ts = pd.Timestamp(dt_obj)
        if ts.tzinfo is None:
            return ts.tz_localize(tzinfo)
        else:
            return ts.tz_convert(tzinfo)

    tzinfo_w = slider_min.tz
    w_start = _ensure_tz_runtime(win_range[0], tzinfo_w)
    w_end   = _ensure_tz_runtime(win_range[1], tzinfo_w)
    work = work[(work["win_date"] >= w_start) & (work["win_date"] <= w_end)]
else:
    st.warning("Нет данных после 15.09.2025 в текущих фильтрах.")

# Aggregation Settings (for Basic Analytics)
mode_unique = st.sidebar.toggle("Считать уникальных пользователей (вместо событий)", value=False)
gran = st.sidebar.radio("Гранулярность", ["Day","Week","Month"], horizontal=True)

# Metrics Scope
metrics_scope = st.sidebar.radio("Область метрик", ["Текущий срез", "Вся база (с учетом фильтров)"], index=0)
if metrics_scope == "Текущий срез":
    metrics_df = work
else:
    # Use filtered_df instead of raw df to respect Region/Prize/Segment filters
    metrics_df = filtered_df.copy()
    metrics_df = metrics_df.dropna(subset=["win_date"])
    if local_tz != "UTC":
        metrics_df["win_date"] = metrics_df["win_date"].dt.tz_convert(local_tz)
    metrics_df = metrics_df[metrics_df["win_date"] >= start_dt_local]

# ----------------------------- Main UI ----------------------------------------
st.title("QR Code Analytics")

# Tabs
tab_basic, tab_advanced = st.tabs(["Базовая аналитика", "Advanced Analytics"])

with tab_basic:
    render_basic_analytics(
        df=df,
        work=work,
        metrics_df=metrics_df,
        USER_COL=USER_COL,
        USER_LABEL=USER_LABEL,
        local_tz=local_tz,
        gran=gran,
        mode_unique=mode_unique,
        metrics_scope=metrics_scope,
        start_dt_local=start_dt_local
    )

with tab_advanced:
    render_advanced_analytics(
        df=filtered_df,
        work=work,
        metrics_df=metrics_df,
        USER_COL=USER_COL,
        local_tz=local_tz
    )

# ----------------------------- Footer / DB Check ------------------------------
st.divider()
check_db_connection()