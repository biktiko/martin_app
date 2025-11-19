import streamlit as st
import pandas as pd
import altair as alt
from utils.helpers import aggregate_time, safe_rate

def render_basic_analytics(df, work, metrics_df, USER_COL, USER_LABEL, local_tz, gran, mode_unique, metrics_scope, start_dt_local):
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

    # ----------------------------- Time Series (по win_date) ----------------------
    st.subheader("Динамика")

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
    real_by_prize = (
        metrics_df[metrics_df["is_real_prize"]]
        .groupby("prize_id")
        .size()
        .reset_index(name="real_prize_count")
        .sort_values("real_prize_count", ascending=False)
    )
    if not real_by_prize.empty:
        total_real = int(real_by_prize["real_prize_count"].sum())
        received_by_prize = (
            metrics_df[metrics_df["is_real_prize_received"]]
            .groupby("prize_id")
            .size()
            .reindex(real_by_prize["prize_id"])
            .fillna(0)
            .astype(int)
            .reset_index(name="received_count")
        )
        prob_df = real_by_prize.merge(received_by_prize, on="prize_id", how="left")
        prob_df["p_per_scan"] = prob_df["real_prize_count"] / max(den_scans, 1)
        prob_df["share_among_real"] = prob_df["real_prize_count"] / max(total_real, 1)
        prob_df["received_share_in_prize"] = prob_df["received_count"] / prob_df["real_prize_count"]
        show_cols = prob_df.copy()
        for c in ["p_per_scan","share_among_real","received_share_in_prize"]:
            show_cols[c] = (show_cols[c] * 100).round(3)
        st.dataframe(show_cols, use_container_width=True)
        st.download_button(
            "Скачать вероятности по prize_id (CSV)",
            prob_df.to_csv(index=False).encode("utf-8"),
            file_name="prize_probabilities.csv",
            mime="text/csv"
        )
    else:
        st.info("Нет real prizes в текущей области метрик.")

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
        user_list = sorted(work[USER_COL].dropna().unique())
        col_uh1, col_uh2 = st.columns([2,1])
        selected_user = col_uh1.selectbox("Выбери пользователя", user_list if len(user_list) <= 5000 else [],
                                          index=0 if len(user_list) else None,
                                          help="Если список слишком большой, используй поле справа.")
        manual_user = col_uh2.text_input(f"Или введи {USER_LABEL} вручную")
        if manual_user:
            if work[USER_COL].dtype.kind in ("i","u"):
                try:
                    manual_id_cast = int(manual_user)
                except:
                    manual_id_cast = manual_user
            else:
                manual_id_cast = manual_user
            user_id_value = manual_id_cast
        else:
            user_id_value = selected_user

        if user_id_value is not None:
            user_df = work[work[USER_COL] == user_id_value].copy()
            if user_df.empty:
                st.warning("Нет событий для этого пользователя (с учётом фильтров).")
            else:
                user_df = user_df.sort_values(by="win_date")
                base_user = alt.Chart(user_df).encode(
                    x=alt.X("win_date:T", title="Дата (win_date)"),
                    color=alt.Color("win_type:N", title="Тип"),
                    shape=alt.Shape("win_type:N", title="Тип"),
                    tooltip=[
                        alt.Tooltip("win_date:T", title="Дата"),
                        alt.Tooltip("win_type:N", title="Тип"),
                        alt.Tooltip("is_real_prize:N", title="Real prize"),
                        alt.Tooltip("is_point_win:N", title="Points"),
                        alt.Tooltip("is_win_received:N", title="Получен"),
                        alt.Tooltip("prize_id:N", title="prize_id")
                    ]
                )
                timeline = base_user.mark_point(size=140, filled=True).properties(
                    height=160, width="container", title=f"События пользователя {user_id_value}"
                )
                st.altair_chart(timeline, use_container_width=True)

                with st.expander("Сырые строки пользователя"):
                    base_cols = [
                        USER_COL, "region_name", "win_type", "is_win_received",
                        "is_real_prize", "is_point_win", "win_date",
                        "prize_receive_date", "prize_delivery_date", "prize_id"
                    ]
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
