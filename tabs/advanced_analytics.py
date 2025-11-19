import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
from utils.helpers import safe_rate, span_stats

def render_advanced_analytics(df, work, metrics_df, USER_COL, local_tz):
    st.header("Advanced Analytics")

    if not USER_COL:
        st.error("Не выбран идентификатор пользователя. Аналитика невозможна.")
        return

    # --- 1. Cohort Analysis (Retention) ---
    st.subheader("1. Когортный анализ (Retention)")
    
    cohort_data = df.dropna(subset=["win_date"]).copy()
    if local_tz != "UTC":
        cohort_data["win_date"] = cohort_data["win_date"].dt.tz_convert(local_tz)
    
    user_first_scan = cohort_data.groupby(USER_COL)["win_date"].min().reset_index()
    user_first_scan.columns = [USER_COL, "first_scan"]
    
    cohort_data = cohort_data.merge(user_first_scan, on=USER_COL)
    
    cohort_data["cohort_week"] = cohort_data["first_scan"].dt.to_period("W").dt.start_time
    cohort_data["activity_week"] = cohort_data["win_date"].dt.to_period("W").dt.start_time
    
    cohort_data["weeks_since_first"] = (
        (cohort_data["activity_week"] - cohort_data["cohort_week"]).dt.days // 7
    ).astype(int)
    
    cohort_counts = cohort_data.groupby(["cohort_week", "weeks_since_first"])[USER_COL].nunique().reset_index()
    cohort_pivot = cohort_counts.pivot(index="cohort_week", columns="weeks_since_first", values=USER_COL)
    
    cohort_size = cohort_pivot.iloc[:, 0]
    retention = cohort_pivot.divide(cohort_size, axis=0)
    
    retention_display = retention.copy()
    retention_display.index = retention_display.index.strftime("%Y-%m-%d")
    st.dataframe(retention_display.style.format("{:.1%}", na_rep=""), use_container_width=True)
    
    # --- 2. Time-to-Claim Analysis ---
    st.subheader("2. Скорость получения призов (Time-to-Claim)")
    
    claim_data = df[
        df["is_real_prize"] & 
        df["is_win_received"] & 
        df["prize_receive_date"].notna() & 
        df["win_date"].notna()
    ].copy()
    
    if not claim_data.empty:
        claim_data["hours_to_claim"] = (claim_data["prize_receive_date"] - claim_data["win_date"]).dt.total_seconds() / 3600.0
        claim_data = claim_data[claim_data["hours_to_claim"] >= 0]
        
        c_claim1, c_claim2 = st.columns(2)
        c_claim1.metric("Среднее время (часы)", f"{claim_data['hours_to_claim'].mean():.1f}")
        c_claim2.metric("Медианное время (часы)", f"{claim_data['hours_to_claim'].median():.1f}")
        
        chart_claim = alt.Chart(claim_data).mark_bar().encode(
            x=alt.X("hours_to_claim:Q", bin=alt.Bin(maxbins=30), title="Часов до получения"),
            y=alt.Y("count()", title="Количество призов")
        ).properties(title="Распределение времени получения приза")
        st.altair_chart(chart_claim, use_container_width=True)
        
        now = pd.Timestamp.now(tz="UTC")
        pending_long = df[
            df["is_real_prize_pending"] & 
            (df["win_date"] < (now - pd.Timedelta(days=7)))
        ]
        st.metric("Забытые призы (> 7 дней)", len(pending_long))
    else:
        st.info("Нет данных о полученных реальных призах для анализа времени получения.")

    # --- 3. RFM Analysis (Simplified) ---
    st.subheader("3. Сегментация пользователей (RFM-style)")
    
    rfm_data = df.dropna(subset=["win_date"]).copy()
    last_scan_date = rfm_data["win_date"].max()
    
    rfm = rfm_data.groupby(USER_COL).agg(
        last_scan=("win_date", "max"),
        frequency=("win_date", "count"),
        real_prizes=("is_real_prize", "sum")
    ).reset_index()
    
    rfm["recency_days"] = (last_scan_date - rfm["last_scan"]).dt.days
    
    def segment_user(row):
        if row["frequency"] == 1:
            return "Novice (1 scan)"
        elif row["frequency"] <= 5:
            return "Active (2-5 scans)"
        else:
            return "Power User (6+ scans)"
            
    rfm["segment"] = rfm.apply(segment_user, axis=1)
    
    c_rfm1, c_rfm2 = st.columns([1, 2])
    with c_rfm1:
        st.write("Распределение по сегментам")
        segment_counts = rfm["segment"].value_counts().reset_index()
        segment_counts.columns = ["segment", "count"]
        st.dataframe(segment_counts, hide_index=True)
        
    with c_rfm2:
        chart_rfm = alt.Chart(rfm).mark_circle(size=60).encode(
            x=alt.X("frequency:Q", title="Количество сканирований"),
            y=alt.Y("real_prizes:Q", title="Выиграно реальных призов"),
            color="segment:N",
            tooltip=[USER_COL, "frequency", "real_prizes", "recency_days", "segment"]
        ).properties(title="Активность vs Выигрыши", height=300)
        st.altair_chart(chart_rfm, use_container_width=True)

    # --- 4. Prize Efficiency ---
    st.subheader("4. Эффективность призов")
    
    if "prize_id" in df.columns:
        prize_stats = df[df["is_real_prize"]].groupby("prize_id").agg(
            total_won=("prize_id", "count"),
            total_received=("is_win_received", "sum")
        ).reset_index()
        
        prize_stats["unclaimed_rate"] = 1 - (prize_stats["total_received"] / prize_stats["total_won"])
        
        st.dataframe(
            prize_stats.sort_values("total_won", ascending=False).style.format({
                "unclaimed_rate": "{:.1%}"
            }),
            use_container_width=True
        )
    else:
        st.info("Нет информации о prize_id.")

    # --- 5. General Statistics (Normalized) ---
    st.subheader("5. Общая статистика (Нормированные показатели)")
    
    if not metrics_df.empty:
        base = metrics_df.dropna(subset=["win_date"]).copy()
        
        # A. Total scans per user
        total_scans_per_user = base.groupby(USER_COL).size().rename("total_scans")
        if len(total_scans_per_user):
            overall_stats = span_stats(total_scans_per_user)
        else:
            overall_stats = {"mean": 0, "q25": 0, "median": 0, "q75": 0, "count": 0}

        st.markdown(f"**A. Суммарные сканы на пользователя ({USER_COL}) (за всё время присутствия)**")
        c_tot1, c_tot2, c_tot3, c_tot4, c_tot5 = st.columns(5)
        c_tot1.metric(f"Всего пользователей", int(overall_stats["count"]), help=f"Уникальные {USER_COL}")
        c_tot2.metric("Сканов/пользователь (среднее)", f"{overall_stats['mean']:.2f}")
        c_tot3.metric("Q1", f"{overall_stats['q25']:.2f}")
        c_tot4.metric("Медиана", f"{overall_stats['median']:.2f}")
        c_tot5.metric("Q3", f"{overall_stats['q75']:.2f}")

        with st.expander("Распределение: суммарные сканы на пользователя"):
            st.dataframe(
                total_scans_per_user.describe(percentiles=[0.25, 0.5, 0.75]).to_frame(),
                use_container_width=True
            )

        # B. Normalized indicators
        rate_basis = st.radio(
            "База нормализации интервала",
            ["До последнего собственного скана", "До глобального конца периода"],
            index=1,
            horizontal=True
        )

        global_last_day = base["win_date"].dt.floor("D").max()
        global_last_week_start = base["win_date"].dt.to_period("W").max().start_time
        
        per_user_first = base.groupby(USER_COL)["win_date"].min().to_frame(name="first_win")
        per_user_first["first_day"] = per_user_first["first_win"].dt.floor("D")
        per_user_first["first_week_start"] = per_user_first["first_win"].dt.to_period("W").dt.start_time

        if rate_basis == "До последнего собственного скана":
            per_user_last = base.groupby(USER_COL)["win_date"].max().to_frame(name="last_win")
            per_user_span = per_user_first.join(per_user_last)
            per_user_span["last_day"] = per_user_span["last_win"].dt.floor("D")
            per_user_span["last_week_start"] = per_user_span["last_win"].dt.to_period("W").dt.start_time
        else:
            per_user_span = per_user_first.copy()
            per_user_span["last_win"] = global_last_day
            per_user_span["last_day"] = global_last_day
            per_user_span["last_week_start"] = global_last_week_start

        per_user_span["span_days"] = (per_user_span["last_day"] - per_user_span["first_day"]).dt.days + 1
        per_user_span["span_weeks"] = ((per_user_span["last_week_start"] - per_user_span["first_week_start"]).dt.days // 7) + 1

        per_user_span = per_user_span.join(total_scans_per_user)

        per_user_span["span_days"] = per_user_span["span_days"].where(per_user_span["span_days"] > 0, 1)
        per_user_span["span_weeks"] = per_user_span["span_weeks"].where(per_user_span["span_weeks"] > 0, 1)

        per_user_span["daily_rate_span"] = per_user_span["total_scans"] / per_user_span["span_days"]
        per_user_span["weekly_rate_span"] = per_user_span["total_scans"] / per_user_span["span_weeks"]

        # Full weeks logic
        def _count_full_weeks(row):
            first_day = row["first_day"]
            last_day = row["last_day"]
            if pd.isna(first_day) or pd.isna(last_day):
                return 0
            week_starts = pd.date_range(first_day, last_day, freq="W-MON")
            if len(week_starts) == 0:
                if first_day.weekday() == 0 and (first_day + pd.Timedelta(days=6)) <= last_day:
                    return 1
                return 0
            full = ((week_starts + pd.Timedelta(days=6)) <= last_day).sum()
            if full == 0 and first_day.weekday() == 0 and (first_day + pd.Timedelta(days=6)) <= last_day:
                return 1
            return int(full)

        per_user_span["full_weeks"] = per_user_span.apply(_count_full_weeks, axis=1)

        per_user_span["weekly_rate_full_weeks"] = per_user_span.apply(
            lambda r: (r["total_scans"] / r["full_weeks"]) if r["full_weeks"] > 0 else pd.NA, axis=1
        )

        daily_span_stats = span_stats(per_user_span["daily_rate_span"])
        weekly_span_stats = span_stats(per_user_span["weekly_rate_span"])
        
        with st.expander("Старый недельный подсчёт (включая неполные недели)"):
            st.write("Старые недельные метрики учитывали первую/последнюю неполную неделю как целую.")
            old_week_stats = weekly_span_stats
            c_ow1, c_ow2, c_ow3, c_ow4, c_ow5 = st.columns(5)
            c_ow1.metric("Сканы/неделю (старый mean)", f"{old_week_stats['mean']:.2f}")
            c_ow2.metric("Q1", f"{old_week_stats['q25']:.2f}")
            c_ow3.metric("Медиана", f"{old_week_stats['median']:.2f}")
            c_ow4.metric("Q3", f"{old_week_stats['q75']:.2f}")
