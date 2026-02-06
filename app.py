import streamlit as st
import pandas as pd
import datetime as dt

# Imports from our new modules
from utils.auth import require_auth
# from utils.db import check_db_connection
from utils.data import load_data, process_data, get_user_col
from tabs.basic_analytics import render_basic_analytics
from tabs.advanced_analytics import render_advanced_analytics

# ----------------------------- Config & Auth ----------------------------------
st.set_page_config(page_title="QR Code Analytics", layout="wide")

# Enforce authentication
require_auth()

# ----------------------------- Sidebar & Data Loading -------------------------
# Placeholder for data freshness (top of sidebar)
sidebar_top = st.sidebar.empty()

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

# Enrich with prize names
from utils.prizes import enrich_with_prize_name
df = enrich_with_prize_name(df)

# Show data freshness
if "win_date" in df.columns and not df.empty:
    last_date = df["win_date"].max()
    if pd.notna(last_date):
        sidebar_top.info(f"Актуальность данных: {last_date.strftime('%d.%m.%Y %H:%M')}")

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

# --- Quick Filters Buttons ---
q_cols = st.sidebar.columns(2)

# A. Chips Button
if q_cols[0].button("🏆 Чипсы", help="Розыгрыш чипсов с 11.12.2025 (created) / 15.01.2026 (win)"):
    if "region_name" in df.columns:
        st.session_state["region_filter"] = ["Armenia"]
    
    if "created_date" in df.columns:
        q_start = pd.Timestamp("2025-12-11").tz_localize(local_tz) if local_tz != "UTC" else pd.Timestamp("2025-12-11").tz_localize("UTC")
        temp_df = df[df["region_name"] == "Armenia"] if "region_name" in df.columns else df
        q_max = temp_df["created_date"].max()
        if pd.notna(q_max):
            q_max = q_max.tz_convert(local_tz) if local_tz != "UTC" else q_max.tz_convert("UTC")
        else:
            q_max = q_start
        if q_max < q_start: q_max = q_start
        st.session_state["created_date_filter"] = (q_start.to_pydatetime(), q_max.to_pydatetime())

    if "win_date" in df.columns:
        w_start = pd.Timestamp("2026-01-15").tz_localize(local_tz) if local_tz != "UTC" else pd.Timestamp("2026-01-15").tz_localize("UTC")
        temp_df = df[df["region_name"] == "Armenia"] if "region_name" in df.columns else df
        w_max = temp_df["win_date"].max()
        if pd.notna(w_max):
            w_max = w_max.tz_convert(local_tz) if local_tz != "UTC" else w_max.tz_convert("UTC")
        else:
            w_max = w_start
        if w_max < w_start: w_max = w_start
        st.session_state["win_date_filter"] = (w_start.to_pydatetime(), w_max.to_pydatetime())
    st.rerun()

# B. Seeds Button
if q_cols[1].button("🌻 Семечки", help="Розыгрыш семечек: до 09.12.2025 (created) / с 16.12.2025 (win)"):
    if "region_name" in df.columns:
        st.session_state["region_filter"] = ["Armenia"]
    
    if "created_date" in df.columns:
        q_end = pd.Timestamp("2025-12-09 23:59:59").tz_localize(local_tz) if local_tz != "UTC" else pd.Timestamp("2025-12-09 23:59:59").tz_localize("UTC")
        temp_df = df[df["region_name"] == "Armenia"] if "region_name" in df.columns else df
        q_min = temp_df["created_date"].min()
        if pd.notna(q_min):
            q_min = q_min.tz_convert(local_tz) if local_tz != "UTC" else q_min.tz_convert("UTC")
        else:
            q_min = q_end - pd.Timedelta(days=30) # fallback
        if q_min > q_end: q_min = q_end - pd.Timedelta(hours=1)
        st.session_state["created_date_filter"] = (q_min.to_pydatetime(), q_end.to_pydatetime())

    if "win_date" in df.columns:
        w_start = pd.Timestamp("2025-12-16 00:00:00").tz_localize(local_tz) if local_tz != "UTC" else pd.Timestamp("2025-12-16 00:00:00").tz_localize("UTC")
        temp_df = df[df["region_name"] == "Armenia"] if "region_name" in df.columns else df
        w_max = temp_df["win_date"].max()
        if pd.notna(w_max):
            w_max = w_max.tz_convert(local_tz) if local_tz != "UTC" else w_max.tz_convert("UTC")
        else:
            w_max = w_start
        if w_max < w_start: w_max = w_start
        st.session_state["win_date_filter"] = (w_start.to_pydatetime(), w_max.to_pydatetime())
    st.rerun()

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
    # Ensure session state is initialized to avoid "default value" warning if key exists
    if "region_filter" not in st.session_state:
        st.session_state["region_filter"] = region_values
    selected_regions = st.sidebar.multiselect("Регионы", region_values, key="region_filter")
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

# F. Created Date Filter
if "created_date" in filtered_df.columns:
    cd_series = filtered_df["created_date"].dropna()
    if not cd_series.empty:
        cd_min = cd_series.min()
        cd_max = cd_series.max()

        if local_tz != "UTC":
            cd_min = cd_min.tz_convert(local_tz)
            cd_max = cd_max.tz_convert(local_tz)
            
        # Ensure min < max
        if cd_min > cd_max:
             cd_min = cd_max

        st.sidebar.markdown("---")
        # Clamp session state if it exists to avoid StreamlitValueAboveMaxError
        if "created_date_filter" in st.session_state:
            curr_vals = st.session_state["created_date_filter"]
            c_min_dt = cd_min.to_pydatetime()
            c_max_dt = cd_max.to_pydatetime()
            # Ensure tuple, handle potential None or mismatch
            try:
                v0 = max(c_min_dt, min(curr_vals[0], c_max_dt))
                v1 = max(c_min_dt, min(curr_vals[1], c_max_dt))
                st.session_state["created_date_filter"] = (v0, v1)
            except Exception:
                pass # Fallback to default behavior if types mismatch

        created_range = st.sidebar.slider(
            "Дата создания QR (created_date)",
            min_value=cd_min.to_pydatetime(),
            max_value=cd_max.to_pydatetime(),
            value=(cd_min.to_pydatetime(), cd_max.to_pydatetime()),
            format="DD.MM.YYYY HH:mm",
            key="created_date_filter"
        )
        
        # Apply filter
        # 1. Convert tuple back to Timestamp with TZ
        c_start = pd.Timestamp(created_range[0])
        c_end = pd.Timestamp(created_range[1])
        
        # 2. Localize if needed to match what the slider provided (which is local_tz)
        if c_start.tzinfo is None:
            c_start = c_start.tz_localize(local_tz)
        elif str(c_start.tzinfo) != str(local_tz): # crude check, or just tz_convert
            c_start = c_start.tz_convert(local_tz)
            
        if c_end.tzinfo is None:
            c_end = c_end.tz_localize(local_tz)
        elif str(c_end.tzinfo) != str(local_tz):
            c_end = c_end.tz_convert(local_tz)

        # 3. Convert to UTC to filter the dataframe
        c_start_utc = c_start.tz_convert("UTC")
        c_end_utc = c_end.tz_convert("UTC")
        
        filtered_df = filtered_df[
            (filtered_df["created_date"] >= c_start_utc) & 
            (filtered_df["created_date"] <= c_end_utc)
        ]

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

    # Clamp session state for win_date to avoid StreamlitValueAboveMaxError
    if "win_date_filter" in st.session_state:
        w_vals = st.session_state["win_date_filter"]
        w_min_dt = slider_min.to_pydatetime()
        w_max_dt = slider_max.to_pydatetime()
        try:
            # We must respect the types. slider_min/max are usually Timestamps converted to pydatetime above
            # session state has datetimes.
            wv0 = pd.Timestamp(w_vals[0]).to_pydatetime()
            wv1 = pd.Timestamp(w_vals[1]).to_pydatetime()
            
            # Clamp
            wv0 = max(w_min_dt, min(wv0, w_max_dt))
            wv1 = max(w_min_dt, min(wv1, w_max_dt))
            
            st.session_state["win_date_filter"] = (wv0, wv1)
        except Exception:
            pass

    win_range = st.sidebar.slider(
        "Диапазон по win_date (≥ 15.09.2025)",
        min_value=slider_min.to_pydatetime(),
        max_value=slider_max.to_pydatetime(),
        value=(slider_min.to_pydatetime(), slider_max.to_pydatetime()),
        format="DD.MM.YYYY",
        key="win_date_filter"
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
        mode_unique=mode_unique,
        metrics_scope=metrics_scope,
        start_dt_local=start_dt_local,
        filtered_df=filtered_df
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
# check_db_connection()