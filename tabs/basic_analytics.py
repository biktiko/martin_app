import streamlit as st
import pandas as pd
import datetime as dt
import altair as alt
from utils.helpers import aggregate_time, safe_rate

def render_basic_analytics(df, work, metrics_df, USER_COL, USER_LABEL, local_tz, mode_unique, metrics_scope, start_dt_local, filtered_df):
    # ----------------------------- Metrics Summary (всё по win_date) --------------
    st.subheader("Ключевые метрики")

    total_events = len(metrics_df)
    unique_users = metrics_df[USER_COL].nunique() if USER_COL else None

    wins_total = metrics_df["has_win"].sum()
    real_prizes_total = metrics_df["is_real_prize"].sum()
    real_prizes_received = (metrics_df["is_real_prize"] & metrics_df["is_win_received"]).sum()
    real_prizes_pending = metrics_df["is_real_prize_pending"].sum()  # считаем напрямую

    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    col_m1.metric("Событий", int(total_events))
    if unique_users is not None:
        col_m2.metric("Уникальных пользователей", int(unique_users))
    col_m3.metric("Всего выигрышей", int(wins_total))
    col_m4.metric("Real prizes (всего)", int(real_prizes_total))
    col_m5.metric("Real prizes выдано", int(real_prizes_received))
    col_m6.metric("Real prizes не выдано", int(real_prizes_pending))

    c2a, c2b, c2c, c2d = st.columns(4)
    c2a.metric("Конверсия в выигрыш", f"{safe_rate(wins_total, total_events):.2%}")
    c2b.metric("Доля real prizes среди выигрышей", f"{safe_rate(real_prizes_total, wins_total):.2%}")
    c2c.metric("Выдано real prizes", f"{safe_rate(real_prizes_received, real_prizes_total):.2%}")
    c2d.metric("Ожидают выдачи", f"{safe_rate(real_prizes_pending, real_prizes_total):.2%}")

    # --- Daily Averages ---
    avg_scans_per_day = 0
    avg_unique_users_per_day = 0
    avg_new_users_per_day = 0
    avg_wins_per_day = 0
    avg_real_prizes_per_day = 0

    if not metrics_df.empty and "win_date" in metrics_df.columns:
        metrics_df_daily = metrics_df.copy()
        if metrics_df_daily["win_date"].dt.tz is None:
            metrics_df_daily["win_date"] = metrics_df_daily["win_date"].dt.tz_localize("UTC")
        if local_tz != "UTC":
            metrics_df_daily["win_date"] = metrics_df_daily["win_date"].dt.tz_convert(local_tz)
            
        metrics_df_daily["day"] = metrics_df_daily["win_date"].dt.date
        min_day = metrics_df_daily["day"].min()
        max_day = metrics_df_daily["day"].max()
        
        if pd.notna(min_day) and pd.notna(max_day):
            num_days = (max_day - min_day).days + 1
            if num_days > 0:
                avg_scans_per_day = total_events / num_days
                avg_wins_per_day = wins_total / num_days
                avg_real_prizes_per_day = real_prizes_total / num_days
                
                if USER_COL:
                    all_days = [min_day + dt.timedelta(days=i) for i in range(num_days)]
                    daily_unique = metrics_df_daily.groupby("day")[USER_COL].nunique().reindex(all_days, fill_value=0)
                    avg_unique_users_per_day = daily_unique.mean()
                    
                    current_scope_users = metrics_df[USER_COL].dropna().unique()
                    global_history = df[df[USER_COL].isin(current_scope_users)]
                    first_scans = global_history.groupby(USER_COL)["win_date"].min()
                    
                    if first_scans.dt.tz is None:
                        first_scans = first_scans.dt.tz_localize("UTC")
                    if local_tz != "UTC":
                        first_scans = first_scans.dt.tz_convert(local_tz)
                        
                    first_scans_day = first_scans.dt.date
                    first_scans_in_range = first_scans_day[(first_scans_day >= min_day) & (first_scans_day <= max_day)]
                    avg_new_users_per_day = len(first_scans_in_range) / num_days

    st.markdown("##### Средние показатели в день")
    c3a, c3b, c3c, c3d, c3e = st.columns(5)
    c3a.metric("Сканирований", f"{avg_scans_per_day:.1f}")
    c3b.metric("Уник. пользователей", f"{avg_unique_users_per_day:.1f}")
    c3c.metric("Новых пользователей", f"{avg_new_users_per_day:.1f}")
    c3d.metric("Любых выигрышей", f"{avg_wins_per_day:.1f}")
    c3e.metric("Real prizes", f"{avg_real_prizes_per_day:.1f}")

    # ----------------------------- Time Series (по win_date) ----------------------
    st.subheader("Динамика")

    gran = st.radio("Гранулярность", ["Day", "Week", "Month"], horizontal=True, key="dynamic_gran")

    ts_events = aggregate_time(work, "win_date", gran, mode_unique, local_tz, USER_COL)
    metric_label = "Уникальные пользователи (win_date)" if mode_unique else "События (win_date)"
    chart_events = alt.Chart(ts_events).mark_line(point=True).encode(
        x=alt.X("date:T", title="Дата", axis=alt.Axis(format="%d.%m", labelAngle=-35)),
        y=alt.Y("count:Q", title=metric_label),
        tooltip=[alt.Tooltip("date:T", title="Дата"),
                 alt.Tooltip("count:Q", title=metric_label)]
    ).properties(height=280, title="События по времени (win_date)")
    st.altair_chart(chart_events, use_container_width=True)

    work_real = work[work["is_real_prize"]]
    ts_real = aggregate_time(work_real, "win_date", gran, mode_unique, local_tz, USER_COL)
    real_label = "Уникальные пользователи с real prize" if mode_unique else "Real prizes (события)"
    chart_real = alt.Chart(ts_real).mark_line(point=True, color="#ff7f0e").encode(
        x=alt.X("date:T", title="Дата", axis=alt.Axis(format="%d.%m", labelAngle=-35)),
        y=alt.Y("count:Q", title=real_label),
        tooltip=[alt.Tooltip("date:T", title="Дата"),
                 alt.Tooltip("count:Q", title=real_label)]
    ).properties(height=280, title="Реальные призы по времени (win_date)")
    st.altair_chart(chart_real, use_container_width=True)

    # NEW: Growth of New Unique Users
    if USER_COL and not filtered_df.empty:
        # 1. Identify users currently in the filtered scope
        current_scope_users = filtered_df[USER_COL].unique()

        # 2. Calculate TRUE first appearance context globally (using df) for these users
        #    This prevents "old" users from appearing as "new" just because their old history was filtered out.
        #    We only consider users who are present in the current filter (e.g. Region=Armenia),
        #    but we look at their entire history to find the real start date.
        global_history = df[df[USER_COL].isin(current_scope_users)]
        first_scans = global_history.groupby(USER_COL)["win_date"].min().reset_index()
        first_scans.columns = [USER_COL, "first_seen_date"]
        
        # Filter to current view range (work)
        if not work.empty:
            min_dt = work["win_date"].min()
            max_dt = work["win_date"].max()
            
            # Ensure timezone awareness/conversion for comparison
            if first_scans["first_seen_date"].dt.tz is None:
                 first_scans["first_seen_date"] = first_scans["first_seen_date"].dt.tz_localize("UTC")
            
            if local_tz != "UTC":
                first_scans["first_seen_date"] = first_scans["first_seen_date"].dt.tz_convert(local_tz)
            
            first_scans_in_range = first_scans[
                (first_scans["first_seen_date"] >= min_dt) & 
                (first_scans["first_seen_date"] <= max_dt)
            ]
        else:
            first_scans_in_range = first_scans

        ts_new_users = aggregate_time(first_scans_in_range, "first_seen_date", gran, False, local_tz, USER_COL)
        
        chart_new_users = alt.Chart(ts_new_users).mark_bar(color="#2ca02c").encode(
            x=alt.X("date:T", title="Дата", axis=alt.Axis(format="%d.%m", labelAngle=-35)),
            y=alt.Y("count:Q", title="Новые пользователи"),
            tooltip=[alt.Tooltip("date:T", title="Дата"),
                     alt.Tooltip("count:Q", title="Новые пользователи")]
        ).properties(height=280, title="Прирост новых пользователей (по дате первого сканирования)")
        
        st.altair_chart(chart_new_users, use_container_width=True)

    with st.expander("DEBUG Time Series"):
        st.write("Events head:", ts_events.head(10))
        st.write("Events tail:", ts_events.tail(5))
        st.write("Real prizes head:", ts_real.head(10))
        st.write("Real prizes tail:", ts_real.tail(5))

    # ----------------------------- Users: winners / received / pending ------------
    st.subheader("Пользователи: выигрыши и получение")

    if USER_COL:
        users_won_any = metrics_df.loc[metrics_df["has_win"], USER_COL].dropna().nunique()
        users_received_any = metrics_df.loc[metrics_df["is_win_received"], USER_COL].dropna().nunique()

        pending_df = metrics_df[metrics_df["is_real_prize_pending"]].copy()
        received_real_df = metrics_df[metrics_df["is_real_prize_received"]].copy()

        # считаем уникальных ожидающих строго по pending_df
        pending_unique_users = int(pending_df[USER_COL].dropna().nunique())
        pending_events = int(pending_df.shape[0])

        # детальная таблица по ожидающим
        pending_counts = pending_df.groupby(USER_COL).size().rename("pending_real_prizes")
        received_before_counts = received_real_df.groupby(USER_COL).size().rename("received_real_before_count")
        pending_users_table = pd.concat([pending_counts, received_before_counts], axis=1).fillna(0)
        pending_users_table["received_real_before_count"] = pending_users_table["received_real_before_count"].astype(int)
        pending_users_table["has_received_real_before"] = pending_users_table["received_real_before_count"] > 0
        pending_users_table = pending_users_table.reset_index()

        users_pending_real_count = pending_unique_users
        users_pending_but_ever_received_real = int(pending_users_table["has_received_real_before"].sum())

        c3a, c3b, c3c, c3d = st.columns(4)
        c3a.metric("Уникальных победителей (любой выигрыш)", int(users_won_any))
        c3b.metric("Уникальных получивших (любой приз)", int(users_received_any))
        c3c.metric("Ожидают real prize (уник.)", users_pending_real_count)
        c3d.metric("Из ожидающих уже получали real", users_pending_but_ever_received_real)

        with st.expander("Проверка согласованности данных"):
            st.write({
                "Не выдано (события)": pending_events,
                "Ожидают (уникальные пользователи)": users_pending_real_count,
                "Поле идентификатора": USER_COL,
                "Область метрик": metrics_scope
            })
            st.dataframe(pending_users_table.sort_values("pending_real_prizes", ascending=False).head(20), use_container_width=True)

            # выгрузки для сверки 1:1
            st.download_button(
                "Скачать все pending-события (CSV)",
                pending_df.to_csv(index=False).encode("utf-8"),
                file_name="pending_events.csv",
                mime="text/csv"
            )
            st.download_button(
                "Скачать список пользователей с ожиданием (CSV)",
                pending_users_table.to_csv(index=False).encode("utf-8"),
                file_name="pending_users.csv",
                mime="text/csv"
            )

            if users_pending_real_count > pending_events:
                st.error(
                    "Аномалия: уникальных ожидающих больше, чем событий «не выдано». "
                    "Попробуйте сменить поле идентификатора в сайдбаре (например, на user_id) "
                    "и нажмите «Обновить/очистить кэш данных»."
                )
    else:
        st.info(f"Колонка идентификатора пользователя ({USER_LABEL}) отсутствует — пользовательские метрики недоступны.")

    # ----------------------------- Time-of-day analysis (win_date) ----------------
    st.subheader("Аналитика по времени суток (win_date)")

    if not work.empty:
        work["hour"] = work["win_date"].dt.hour
        work["dow"] = work["win_date"].dt.dayofweek  # 0=Mon ... 6=Sun
        # 1) Бар по часам
        hour_counts = work["hour"].value_counts().sort_index()
        hour_df = hour_counts.reset_index()
        hour_df.columns = ["hour","count"]
        chart_hour = alt.Chart(hour_df).mark_bar().encode(
            x=alt.X("hour:O", title="Час суток", sort=list(range(24))),
            y=alt.Y("count:Q", title="События"),
            tooltip=["hour","count"]
        ).properties(height=260, title="Распределение по часам суток (win_date)")
        st.altair_chart(chart_hour, use_container_width=True)

        # 2) Теплокарта День недели × Час
        heat_df = work.groupby(["dow","hour"]).size().reset_index(name="count")
        chart_heat = alt.Chart(heat_df).mark_rect().encode(
            x=alt.X("hour:O", title="Час", sort=list(range(24))),
            y=alt.Y("dow:O", title="День недели",
                    sort=list(range(7)),
                    axis=alt.Axis(values=list(range(7)), labelExpr="['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][datum.value]")),
            color=alt.Color("count:Q", title="События", scale=alt.Scale(scheme="blues")),
            tooltip=[alt.Tooltip("dow:O", title="День", format=".0f"),
                     alt.Tooltip("hour:O", title="Час"),
                     alt.Tooltip("count:Q", title="События")]
        ).properties(height=220, title="Heatmap: день недели × час (win_date)")
        st.altair_chart(chart_heat, use_container_width=True)
    else:
        st.info("Нет данных для анализа времени суток после фильтров.")

    # ----------------------------- Prize probabilities per prize_id ---------------
    st.subheader("Вероятности по каждому prize_id")

    den_scans = len(metrics_df)
    group_cols = ["prize_id"]
    if "prize_name" in metrics_df.columns:
        group_cols.append("prize_name")

    real_by_prize = (
        metrics_df[metrics_df["is_real_prize"]]
        .groupby(group_cols)
        .size()
        .reset_index(name="real_prize_count")
        .sort_values("real_prize_count", ascending=False)
    )
    if not real_by_prize.empty:
        total_real = int(real_by_prize["real_prize_count"].sum())
        
        # For received count, we also need to group by same cols or just merge on prize_id
        # Merging on prize_id is safer/easier if we just want counts
        received_counts = (
            metrics_df[metrics_df["is_real_prize_received"]]
            .groupby("prize_id")
            .size()
            .reset_index(name="received_count")
        )
        
        prob_df = real_by_prize.merge(received_counts, on="prize_id", how="left").fillna({"received_count": 0})
        prob_df["received_count"] = prob_df["received_count"].astype(int)
        
        prob_df["p_per_scan"] = prob_df["real_prize_count"] / max(den_scans, 1)
        prob_df["share_among_real"] = prob_df["real_prize_count"] / max(total_real, 1)
        prob_df["received_share_in_prize"] = prob_df["received_count"] / prob_df["real_prize_count"]
        
        show_cols = prob_df.copy()
        for c in ["p_per_scan","share_among_real","received_share_in_prize"]:
            show_cols[c] = (show_cols[c] * 100).round(3)
            
        # Reorder columns to put prize_name next to prize_id
        cols_order = ["prize_id"]
        if "prize_name" in show_cols.columns:
            cols_order.append("prize_name")
        cols_order.extend(["real_prize_count", "received_count", "p_per_scan", "share_among_real", "received_share_in_prize"])
        
        st.dataframe(show_cols[cols_order], use_container_width=True)
        st.download_button(
            "Скачать вероятности по prize_id (CSV)",
            prob_df.to_csv(index=False).encode("utf-8"),
            file_name="prize_probabilities.csv",
            mime="text/csv"
        )
    else:
        st.info("Нет real prizes в текущей области метрик.")

    # ----------------------------- Winner vs Others Comparison --------------------
    st.subheader("Сравнение: Победители (Real Prize) vs Остальные")

    if USER_COL:
        # 1. Identify Winners (Global Scope)
        # Winners are users who have EVER won a real prize in the filtered context
        all_winners_ids = set(filtered_df[filtered_df["is_real_prize"]][USER_COL].unique())
        
        # Received Winners: Users who have EVER won AND received at least one real prize
        received_winners_ids = set(filtered_df[
            filtered_df["is_real_prize"] & filtered_df["is_win_received"]
        ][USER_COL].unique())
        
        # Pending Winners: Users who have won but NEVER received any real prize
        # (Strict definition: if they received at least one, they are in "Received Winners")
        pending_winners_ids = all_winners_ids - received_winners_ids
        
        # 2. UI Controls
        view_mode = st.radio(
            "Режим отображения", 
            [
                "Все пользователи", 
                "Только победители (Все)", 
                "Только получившие (Received)", 
                "Только ожидающие (Pending Only)", 
                "Только без выигрышей (Others)",
                "Сравнение (3 группы)"
            ], 
            horizontal=True,
            key="winner_comparison_mode"
        )
        
        # 3. Prepare Data
        # We work with 'metrics_df' (current scope) but tag users based on global lists
        # Create a copy to avoid SettingWithCopyWarning and side effects
        metrics_df = metrics_df.copy()
        
        # Assign segments
        def _get_winner_segment(uid):
            if uid in received_winners_ids:
                return "Received"
            elif uid in pending_winners_ids:
                return "Pending"
            else:
                return "Others"
                
        metrics_df["winner_segment"] = metrics_df[USER_COL].apply(_get_winner_segment)
        
        if view_mode == "Все пользователи":
            st.caption("Показана статистика по всем пользователям в текущем срезе.")
            target_df = metrics_df
            
        elif view_mode == "Только победители (Все)":
            target_df = metrics_df[metrics_df["winner_segment"].isin(["Received", "Pending"])]
            if target_df.empty:
                st.warning("В текущем срезе нет событий от победителей.")
            else:
                st.metric("Количество победителей (всех) в текущем срезе", target_df[USER_COL].nunique())
                _render_simple_activity_chart(target_df, gran, local_tz, USER_COL, "Активность победителей (всех)", "green")

        elif view_mode == "Только получившие (Received)":
            target_df = metrics_df[metrics_df["winner_segment"] == "Received"]
            if target_df.empty:
                st.warning("В текущем срезе нет событий от получивших приз.")
            else:
                st.metric("Количество получивших в текущем срезе", target_df[USER_COL].nunique())
                _render_simple_activity_chart(target_df, gran, local_tz, USER_COL, "Активность получивших", "green")

        elif view_mode == "Только ожидающие (Pending Only)":
            target_df = metrics_df[metrics_df["winner_segment"] == "Pending"]
            if target_df.empty:
                st.warning("В текущем срезе нет событий от ожидающих (pending only).")
            else:
                st.metric("Количество ожидающих (pending only) в текущем срезе", target_df[USER_COL].nunique())
                _render_simple_activity_chart(target_df, gran, local_tz, USER_COL, "Активность ожидающих", "orange")

        elif view_mode == "Только без выигрышей (Others)":
            target_df = metrics_df[metrics_df["winner_segment"] == "Others"]
            if target_df.empty:
                st.warning("В текущем срезе нет событий от пользователей без выигрышей.")
            else:
                st.metric("Количество без выигрышей (Others) в текущем срезе", target_df[USER_COL].nunique())
                _render_simple_activity_chart(target_df, gran, local_tz, USER_COL, "Активность без выигрышей", "gray")

        else: # Comparison (3 groups)
            # A. Key Metrics Comparison
            c_cmp1, c_cmp2, c_cmp3 = st.columns(3)
            
            # Helper to get avg scans
            def _get_avg_scans(seg):
                sub = metrics_df[metrics_df["winner_segment"] == seg]
                if sub.empty: return 0.0
                return sub.groupby(USER_COL).size().mean()

            avg_rec = _get_avg_scans("Received")
            avg_pen = _get_avg_scans("Pending")
            avg_oth = _get_avg_scans("Others")
            
            c_cmp1.metric("Avg Scans (Received)", f"{avg_rec:.2f}")
            c_cmp2.metric("Avg Scans (Pending)", f"{avg_pen:.2f}")
            c_cmp3.metric("Avg Scans (Others)", f"{avg_oth:.2f}")
            
            # B. Activity Comparison Chart
            # Aggregate for each group
            ts_list = []
            for seg in ["Received", "Pending", "Others"]:
                sub = metrics_df[metrics_df["winner_segment"] == seg]
                ts = aggregate_time(sub, "win_date", gran, True, local_tz, USER_COL)
                ts["Group"] = seg
                ts_list.append(ts)
            
            ts_cmp = pd.concat(ts_list)
            
            chart_cmp = alt.Chart(ts_cmp).mark_line(point=True).encode(
                x=alt.X("date:T", title="Дата"),
                y=alt.Y("count:Q", title="Уникальные пользователи"),
                color=alt.Color("Group:N", scale=alt.Scale(
                    domain=["Received", "Pending", "Others"], 
                    range=["green", "orange", "gray"]
                )),
                tooltip=["date", "count", "Group"]
            ).properties(height=300, title="Сравнение активности: Received vs Pending vs Others")
            st.altair_chart(chart_cmp, use_container_width=True)
            
            # C. Scans Distribution (Histogram)
            st.markdown("##### Распределение количества сканов")
            
            counts_list = []
            for seg in ["Received", "Pending", "Others"]:
                sub = metrics_df[metrics_df["winner_segment"] == seg]
                if not sub.empty:
                    c = sub.groupby(USER_COL).size().reset_index(name="scans")
                    c["Group"] = seg
                    counts_list.append(c)
            
            if counts_list:
                counts_all = pd.concat(counts_list)
                counts_all["scans_capped"] = counts_all["scans"].clip(upper=50)
                
                hist_chart = alt.Chart(counts_all).mark_bar(opacity=0.6, binSpacing=0).encode(
                    x=alt.X("scans_capped:Q", bin=alt.Bin(maxbins=25), title="Количество сканов (capped at 50)"),
                    y=alt.Y("count()", stack=None, title="Количество пользователей"),
                    color=alt.Color("Group:N", scale=alt.Scale(
                        domain=["Received", "Pending", "Others"], 
                        range=["green", "orange", "gray"]
                    )),
                    tooltip=["count()", "Group"]
                ).properties(height=250, title="Гистограмма активности")
                st.altair_chart(hist_chart, use_container_width=True)

    else:
        st.info("Для сравнения групп необходимо выбрать поле идентификатора пользователя.")

    # ----------------------------- User activity (на win_date) --------------------
    st.subheader("Активность пользователей")

    if USER_COL and "win_date" in metrics_df.columns:
        tmp = metrics_df.dropna(subset=["win_date"]).copy()
        if local_tz != "UTC":
            tmp["win_date"] = tmp["win_date"].dt.tz_convert(local_tz)

        scans_per_user = tmp.groupby(USER_COL).size().rename("scans")
        wins_any_per_user = metrics_df.groupby(USER_COL)["has_win"].sum().rename("wins_any")
        real_prizes_per_user = metrics_df.groupby(USER_COL)["is_real_prize"].sum().rename("real_prizes")

        tmp = tmp.sort_values([USER_COL, "win_date"])
        tmp["prev"] = tmp.groupby(USER_COL)["win_date"].shift(1)
        tmp["delta_hours"] = (tmp["win_date"] - tmp["prev"]).dt.total_seconds() / 3600.0
        delta_stats = tmp.groupby(USER_COL)["delta_hours"].agg(
            avg_hours_between_scans="mean",
            median_hours_between_scans="median"
        )
        activity = pd.concat([scans_per_user, wins_any_per_user, real_prizes_per_user, delta_stats], axis=1).fillna(0)
        activity["avg_days_between_scans"] = (activity["avg_hours_between_scans"] / 24).round(2)
        activity["avg_hours_between_scans"] = activity["avg_hours_between_scans"].round(2)
        activity["median_hours_between_scans"] = activity["median_hours_between_scans"].round(2)
        if len(tmp) > 0:
            period_max = tmp["win_date"].max()
            period_min = tmp["win_date"].min()
            
            # 1. Real global first scans for these users to determine true age
            curr_users = tmp[USER_COL].unique()
            global_first_scans = df[df[USER_COL].isin(curr_users)].groupby(USER_COL)["win_date"].min()
            if global_first_scans.dt.tz is None:
                 global_first_scans = global_first_scans.dt.tz_localize("UTC")
            if local_tz != "UTC":
                 global_first_scans = global_first_scans.dt.tz_convert(local_tz)
                 
            # 2. Effective start is the later of their true first scan or the period min
            eff_starts = global_first_scans.clip(lower=period_min)
            eff_days = (period_max - eff_starts).dt.total_seconds() / 86400.0
            
            # Clip at 0.01 to prevent division by zero for identical min/max
            eff_days = eff_days.clip(lower=0.01)

            # 3. Weekly rates (only for users with >= 7 days lifetime)
            valid_7 = eff_days[eff_days >= 7].index
            if len(valid_7) > 0:
                weekly_rates = scans_per_user.reindex(valid_7) / (eff_days.reindex(valid_7) / 7.0)
                avg_weekly_rate = weekly_rates.mean()
                q_w = weekly_rates.quantile([0.25, 0.5, 0.75, 1.0])
                valid_7_count = len(valid_7)
            else:
                avg_weekly_rate = 0.0
                q_w = pd.Series({0.25: 0, 0.5: 0, 0.75: 0, 1.0: 0})
                valid_7_count = 0

            # 4. Monthly rates (only for users with >= 30 days lifetime)
            valid_30 = eff_days[eff_days >= 30].index
            if len(valid_30) > 0:
                monthly_rates = scans_per_user.reindex(valid_30) / (eff_days.reindex(valid_30) / 30.0)
                avg_monthly_rate = monthly_rates.mean()
                q_m = monthly_rates.quantile([0.25, 0.5, 0.75, 1.0])
                valid_30_count = len(valid_30)
            else:
                avg_monthly_rate = 0.0
                q_m = pd.Series({0.25: 0, 0.5: 0, 0.75: 0, 1.0: 0})
                valid_30_count = 0
                
            st.markdown("##### Индивидуальные средние показатели")
            c4a, c4b = st.columns(2)
            with c4a:
                st.metric("Скан/нед (в среднем на юзера)", f"{avg_weekly_rate:.2f}", f"≥7 дней (база: {valid_7_count} чел)", delta_color="off")
                if valid_7_count > 0:
                    st.caption(f"**Квартили:** Q1: {q_w[0.25]:.1f} | Q2 (Медиана): {q_w[0.5]:.1f} | Q3: {q_w[0.75]:.1f} | Q4 (Max): {q_w[1.0]:.1f}")
            with c4b:
                st.metric("Скан/мес (в среднем на юзера)", f"{avg_monthly_rate:.2f}", f"≥30 дней (база: {valid_30_count} чел)", delta_color="off")
                if valid_30_count > 0:
                    st.caption(f"**Квартили:** Q1: {q_m[0.25]:.1f} | Q2 (Медиана): {q_m[0.5]:.1f} | Q3: {q_m[0.75]:.1f} | Q4 (Max): {q_m[1.0]:.1f}")
            
            # Enrich table
            activity["lifetime_days_in_period"] = eff_days.reindex(activity.index).round(1)
            activity["scans_per_week"] = (activity["scans"] / (eff_days.reindex(activity.index) / 7.0)).round(2)
            activity["scans_per_month"] = (activity["scans"] / (eff_days.reindex(activity.index) / 30.0)).round(2)
            activity.loc[activity["lifetime_days_in_period"] < 1, ["scans_per_week", "scans_per_month"]] = None

        activity = activity.reset_index().sort_values(["scans","wins_any","real_prizes"], ascending=False)

        st.dataframe(activity, use_container_width=True, height=420)
        st.download_button(
            "Скачать активность пользователей (CSV)",
            activity.to_csv(index=False).encode("utf-8"),
            file_name="user_activity.csv",
            mime="text/csv"
        )
    else:
        st.info(f"Нужны {USER_LABEL} и win_date для расчёта активности.")

    # ----------------------------- User History (ось = win_date) ------------------
    st.subheader("История пользователя")

    if USER_COL and not work.empty:
        # Define search columns
        search_cols = [USER_COL]
        possible_extras = ["phone_number", "first_name", "last_name"]
        extra_cols = [c for c in possible_extras if c in work.columns]
        all_search_cols = search_cols + extra_cols

        # Create a lookup for the dropdown
        # We take unique users by USER_COL, but keep the extra info
        # Optimization: Only build the expensive labels if we are going to show the dropdown
        unique_users_count = work[USER_COL].nunique()
        
        user_labels = []
        label_to_id = {}
        
        if unique_users_count <= 5000:
            unique_users_df = work.drop_duplicates(subset=[USER_COL])[all_search_cols].copy()
            
            # Vectorized label building is hard with variable columns, but we can try to be faster than row-apply
            # Or just accept apply for < 5000 rows (it's fast enough).
            # But let's optimize slightly by pre-converting to string
            
            for c in all_search_cols:
                unique_users_df[c] = unique_users_df[c].astype(str).replace(["nan", "None"], "")
            
            def _build_label_fast(row):
                # row is now all strings
                parts = [row[USER_COL]]
                extras = [row[c] for c in extra_cols if row[c].strip()]
                if extras:
                    parts.append(", ".join(extras))
                return " | ".join(parts)

            unique_users_df["_display_label"] = unique_users_df.apply(_build_label_fast, axis=1)
            unique_users_df = unique_users_df.sort_values("_display_label")
            
            label_to_id = dict(zip(unique_users_df["_display_label"], unique_users_df[USER_COL]))
            user_labels = unique_users_df["_display_label"].tolist()

        # --- Search / Selection UI ---
        
        # 1. Dropdown (Selection from list)
        # Only show if list is manageable
        options = user_labels if len(user_labels) <= 5000 else []
        
        st.markdown("##### Выбор пользователя")
        col_sel, col_mode = st.columns([3, 1])
        selected_label = col_sel.selectbox(
            "Выбрать из списка", 
            options,
            index=0 if options else None,
            help="Если список пуст (>5000), используйте поиск ниже.",
            key="user_select_dropdown"
        )
        
        # 2. Search Inputs
        st.markdown("##### Поиск (фильтры)")
        match_mode = col_mode.radio("Режим поиска", ["Точное (быстро)", "Частичное"], index=0, help="Точное совпадение работает быстрее.")
        is_exact = (match_mode == "Точное (быстро)")
        
        c_s1, c_s2, c_s3 = st.columns(3)
        s_id = c_s1.text_input("Поиск по ID", key="search_id")
        s_phone = c_s2.text_input("Поиск по телефону", key="search_phone") if "phone_number" in work.columns else None
        s_name = c_s3.text_input("Поиск по имени", key="search_name") if ("first_name" in work.columns or "last_name" in work.columns) else None
        
        user_id_value = None
        
        # Search Logic
        search_active = any([s_id, s_phone, s_name])
        
        if search_active:
            # Start with all True
            mask = pd.Series(True, index=work.index)
            
            # 1. ID Search
            if s_id:
                s_id = s_id.strip()
                if is_exact:
                    # Try to match types for speed
                    if pd.api.types.is_numeric_dtype(work[USER_COL]):
                        try:
                            # Try int first if it looks like int
                            if s_id.isdigit():
                                val = int(s_id)
                            else:
                                val = float(s_id)
                            mask &= (work[USER_COL] == val)
                        except:
                            # Input not numeric, col is numeric -> no match
                            mask &= False
                    else:
                        # String exact match
                        mask &= (work[USER_COL].astype(str) == s_id)
                else:
                    # Partial match
                    mask &= work[USER_COL].astype(str).str.contains(s_id, case=False, na=False)
            
            # 2. Phone Search
            if s_phone and "phone_number" in work.columns:
                s_phone = s_phone.strip()
                if is_exact:
                    mask &= (work["phone_number"].astype(str) == s_phone)
                else:
                    mask &= work["phone_number"].astype(str).str.contains(s_phone, case=False, na=False)
            
            # 3. Name Search
            if s_name:
                s_name = s_name.strip()
                name_cols = [c for c in ["first_name", "last_name"] if c in work.columns]
                if name_cols:
                    name_mask = pd.Series(False, index=work.index)
                    for c in name_cols:
                        if is_exact:
                            name_mask |= (work[c].astype(str).str.lower() == s_name.lower())
                        else:
                            name_mask |= work[c].astype(str).str.contains(s_name, case=False, na=False)
                    mask &= name_mask
            
            found_ids = work.loc[mask, USER_COL].unique()
            
            if len(found_ids) == 0:
                st.warning("🔍 Пользователь не найден по заданным критериям.")
            elif len(found_ids) == 1:
                user_id_value = found_ids[0]
                st.success(f"✅ Найден пользователь: {user_id_value}")
            else:
                st.warning(f"⚠️ Найдено пользователей: {len(found_ids)}. Уточните поиск (например, используйте точный ID).")
                # Preview
                preview_cols = [USER_COL] + extra_cols
                preview = work[work[USER_COL].isin(found_ids)][preview_cols].drop_duplicates(subset=[USER_COL]).head(10)
                st.dataframe(preview, hide_index=True)
                
        elif selected_label:
            # Fallback to dropdown selection if no search input
            user_id_value = label_to_id.get(selected_label)

        if user_id_value is not None:
            user_df = work[work[USER_COL] == user_id_value].copy()
            if user_df.empty:
                st.warning("Нет событий для этого пользователя (с учётом фильтров).")
            else:
                user_df = user_df.sort_values(by="win_date")
                user_df["event_seq"] = range(1, len(user_df) + 1)

                base = alt.Chart(user_df).encode(
                    x=alt.X("win_date:T", title="Дата (win_date)")
                )

                # Line: Cumulative sequence
                line = base.mark_line(color="#a0cbe8").encode(
                    y=alt.Y("event_seq:Q", title="Событие №")
                )

                # Tooltip columns
                tooltip_cols = [
                    alt.Tooltip("win_date:T", title="Дата"),
                    alt.Tooltip("win_type:N", title="Тип"),
                    alt.Tooltip("is_real_prize:N", title="Real prize"),
                    alt.Tooltip("is_point_win:N", title="Points"),
                    alt.Tooltip("is_win_received:N", title="Получен"),
                    alt.Tooltip("prize_id:N", title="prize_id")
                ]
                
                if "prize_name" in user_df.columns:
                    tooltip_cols.append(alt.Tooltip("prize_name:N", title="Приз"))

                # Points: Individual events with details
                points = base.mark_point(size=120, filled=True).encode(
                    y=alt.Y("event_seq:Q"),
                    color=alt.Color("win_type:N", title="Тип"),
                    shape=alt.Shape("win_type:N", title="Тип"),
                    tooltip=tooltip_cols
                )

                timeline = (line + points).properties(
                    height=300, width="container", title=f"История событий пользователя {user_id_value}"
                )
                st.altair_chart(timeline, use_container_width=True)

                with st.expander("Сырые строки пользователя"):
                    base_cols = [
                        USER_COL, "region_name", "win_type", "is_win_received",
                        "is_real_prize", "is_point_win", "win_date",
                        "prize_receive_date", "prize_delivery_date", "prize_id", "prize_name"
                    ]
                    # Add extra cols to view
                    base_cols.extend(extra_cols)
                    
                    seen = set()
                    show_cols = [c for c in base_cols if c in user_df.columns and not (c in seen or seen.add(c))]
                    st.dataframe(user_df[show_cols])
    else:
        st.info("Колонка идентификатора пользователя не найдена — история пользователя недоступна.")

    # ----------------------------- Export -----------------------------------------
    with st.expander("Экспорт агрегированных данных (Time Series)"):
        ts_export = ts_events.copy()
        ts_export["date"] = ts_export["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(ts_export)
        st.download_button(
            "Скачать Time Series (events, win_date) CSV",
            data=ts_export.to_csv(index=False).encode("utf-8"),
            file_name="timeseries_events_win_date.csv",
            mime="text/csv"
        )
        ts_real_export = ts_real.copy()
        ts_real_export["date"] = ts_real_export["date"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.download_button(
            "Скачать Time Series (real prizes, win_date) CSV",
            data=ts_real_export.to_csv(index=False).encode("utf-8"),
            file_name="timeseries_real_prizes_win_date.csv",
            mime="text/csv"
        )



def _render_simple_activity_chart(df, gran, local_tz, USER_COL, title, color):
    ts = aggregate_time(df, 'win_date', gran, True, local_tz, USER_COL)
    chart = alt.Chart(ts).mark_line(point=True, color=color).encode(
        x=alt.X('date:T', title='Дата'),
        y=alt.Y('count:Q', title='Активные пользователи'),
        tooltip=['date', 'count']
    ).properties(height=250, title=title)
    st.altair_chart(chart, use_container_width=True)

