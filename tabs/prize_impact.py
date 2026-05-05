import streamlit as st
import pandas as pd
import altair as alt
import numpy as np

def render_prize_impact(df, USER_COL, local_tz):
    st.header("Влияние реальных призов на активность")
    st.markdown("Этот раздел позволяет изучить, как выигрыш реального приза влияет на дальнейшую активность пользователя. Анализируется количество сканирований ДО и ПОСЛЕ выигрыша. Добавлена **Контрольная группа** для сравнения с пользователями, которые ничего не выиграли.")

    if not USER_COL:
        st.error("Не выбран идентификатор пользователя.")
        return

    required_cols = ["win_date", USER_COL, "is_real_prize", "prize_name"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"Отсутствуют необходимые колонки для анализа: {', '.join(missing)}")
        return

    # Base filtering and localization
    base = df.dropna(subset=["win_date"]).copy()
    if local_tz != "UTC":
        base["win_date"] = base["win_date"].dt.tz_convert(local_tz)

    # Настройки внутри вкладки (а не в сайдбаре), чтобы не путать с глобальными фильтрами
    with st.expander("⚙️ Настройки анализа влияния", expanded=True):
        c1, c2, c3 = st.columns(3)
        window_days = c1.slider("Окно анализа (дней до/после)", min_value=7, max_value=90, value=30, step=1)
        cg_scan_threshold = c2.number_input("Скан для Контрольной группы (X)", min_value=1, max_value=50, value=3, help="На каком по счету сканировании мы фиксируем 'Дату X' для контрольной группы.")
        min_users = c3.number_input("Мин. победителей для показа приза", min_value=1, value=20)
        
        c4, c5, c6 = st.columns(3)
        delivery_status = c4.selectbox(
            "Статус доставки ПЕРВОГО приза", 
            ["Все", "Получен", "Не получен"],
            help="Позволяет оценить, как сам факт выдачи приза влияет на лояльность."
        )
        delivery_speed = c5.slider(
            "Скорость доставки первого приза (в днях)",
            min_value=0, max_value=90, value=(0, 90), step=1,
            help="Учитываются только победители, получившие приз в этом диапазоне дней после выигрыша.",
            disabled=(delivery_status == "Не получен")
        )
        max_scans = c6.number_input(
            "Исключить китов (макс. сканов)", 
            min_value=1, value=20, 
            help="Исключает аномальных пользователей, которые сделали больше X сканирований за всё время."
        )

        strict_matching = st.checkbox(
            f"⚖️ Учитывать только победителей, выигравших свой первый приз не позднее {cg_scan_threshold}-го скана", 
            value=True, 
            help="По умолчанию победители могли выиграть и на 100-й скан (из-за чего у них было бы 100 сканов 'ДО'). Эта галочка оставляет только тех, кто выиграл приз быстро, чтобы их показатели 'ДО' были сопоставимы с Контрольной группой (у которой мы берем отсечку на X скане)."
        )

    with st.spinner("Анализ данных и расчет когорт..."):
        # ОПТИМИЗАЦИЯ: Оставляем только нужные колонки для скорости
        cols_to_keep = [USER_COL, "win_date", "is_real_prize", "prize_name"]
        if "is_win_received" in base.columns: cols_to_keep.append("is_win_received")
        if "prize_receive_date" in base.columns: cols_to_keep.append("prize_receive_date")
            
        slim_base = base[cols_to_keep].copy()
        
        # Исключение китов
        total_scans_per_user = slim_base.groupby(USER_COL).size()
        normal_users = total_scans_per_user[total_scans_per_user <= max_scans].index
        slim_base = slim_base[slim_base[USER_COL].isin(normal_users)]
        
        # Сортировка ОДИН раз
        slim_base = slim_base.sort_values(by=[USER_COL, "win_date"])
        
        # Считаем порядковый номер скана для каждого юзера
        slim_base["scan_num"] = slim_base.groupby(USER_COL).cumcount() + 1
        
        # 1. Победители
        real_wins = slim_base[slim_base["is_real_prize"] == True]
        first_wins = real_wins.drop_duplicates(subset=[USER_COL], keep="first").copy()
        winners_set = set(first_wins[USER_COL]) # Все победители (чтобы они не попали в контрольную группу)
        
        if strict_matching:
            first_wins = first_wins[first_wins["scan_num"] <= cg_scan_threshold]
            
        # Фильтры по доставке
        if "is_win_received" in first_wins.columns:
            if delivery_status == "Получен":
                first_wins = first_wins[first_wins["is_win_received"] == True]
            elif delivery_status == "Не получен":
                first_wins = first_wins[first_wins["is_win_received"] != True]
                
        if "prize_receive_date" in first_wins.columns and delivery_status != "Не получен":
            diff = first_wins["prize_receive_date"] - first_wins["win_date"]
            first_wins["delivery_days"] = diff.dt.total_seconds() / 86400.0
            
            # Оставляем только тех, кто попадает в окно доставки (или не получил приз, если выбран статус "Все")
            if delivery_speed != (0, 90):
                out_of_range = (first_wins["is_win_received"] == True) & ((first_wins["delivery_days"] < delivery_speed[0]) | (first_wins["delivery_days"] > delivery_speed[1]))
                first_wins = first_wins[~out_of_range]
            
        first_wins = first_wins[[USER_COL, "win_date", "prize_name"]].rename(columns={"win_date": "event_date", "prize_name": "first_prize_name"})
        
        # 2. Контрольная группа (те, кто НЕ в winners_set)
        cg_data = slim_base[~slim_base[USER_COL].isin(winners_set)]
        cg_events = cg_data[cg_data["scan_num"] == cg_scan_threshold]
        cg_events = cg_events.drop_duplicates(subset=[USER_COL], keep="first") # Защита от дублей в один момент
        cg_events = cg_events[[USER_COL, "win_date"]].rename(columns={"win_date": "event_date"})
        cg_events["first_prize_name"] = f"Контрольная группа (Скан №{cg_scan_threshold})"
        
        # Объединяем Победителей и Контрольную группу
        all_events = pd.concat([first_wins, cg_events])
        
        if all_events.empty:
            st.warning("Нет данных для анализа (ни победителей, ни контрольной группы).")
            return
            
        # Мэппинг даты события обратно к slim_base
        event_map = all_events.set_index(USER_COL)
        merged = slim_base.merge(event_map, on=USER_COL, how="inner")
        
        # Считаем разницу во времени (оптимизировано)
        merged["days_since_event"] = (merged["win_date"] - merged["event_date"]).dt.total_seconds() / 86400.0
        
        # Маски для окон ДО и ПОСЛЕ
        before_mask = (merged["days_since_event"] >= -window_days) & (merged["days_since_event"] < 0)
        after_mask = (merged["days_since_event"] > 0) & (merged["days_since_event"] <= window_days)
        
        # 1. СКАНИРОВАНИЯ (группировка по маске)
        before_scans = merged[before_mask].groupby(USER_COL).size()
        after_scans = merged[after_mask].groupby(USER_COL).size()
        
        # 2. АКТИВНЫЕ ДНИ (ОПТИМИЗАЦИЯ: Убираем дубликаты по дням вместо медленного nunique)
        merged["activity_day"] = merged["win_date"].dt.floor("D")
        unique_days = merged.drop_duplicates(subset=[USER_COL, "activity_day"])
        
        bd_mask = (unique_days["days_since_event"] >= -window_days) & (unique_days["days_since_event"] < 0)
        ad_mask = (unique_days["days_since_event"] > 0) & (unique_days["days_since_event"] <= window_days)
        
        before_days = unique_days[bd_mask].groupby(USER_COL).size()
        after_days = unique_days[ad_mask].groupby(USER_COL).size()
        
        # Сборка финального DataFrame пользователей
        user_impact = all_events.copy().set_index(USER_COL)
        user_impact["scans_before"] = before_scans
        user_impact["scans_after"] = after_scans
        user_impact["days_active_before"] = before_days
        user_impact["days_active_after"] = after_days
        user_impact = user_impact.fillna(0).reset_index()
        
        # Расчет разницы
        user_impact["scans_diff"] = user_impact["scans_after"] - user_impact["scans_before"]
        user_impact["days_diff"] = user_impact["days_active_after"] - user_impact["days_active_before"]
        
        # Группировка по типу приза / контрольной группе
        prize_stats = user_impact.groupby("first_prize_name").agg(
            users_count=(USER_COL, "nunique"),
            avg_scans_before=("scans_before", "mean"),
            avg_scans_after=("scans_after", "mean"),
            avg_days_before=("days_active_before", "mean"),
            avg_days_after=("days_active_after", "mean")
        ).reset_index()

    # Фильтруем редкие призы, но всегда оставляем контрольную группу
    is_cg = prize_stats["first_prize_name"].str.contains("Контрольная группа")
    prize_stats = prize_stats[(prize_stats["users_count"] >= min_users) | is_cg]

    if prize_stats.empty:
        st.warning("Недостаточно данных для анализа по призам с текущими фильтрами.")
        return

    # Расчет метрик и дельт
    prize_stats["avg_scans_diff"] = prize_stats["avg_scans_after"] - prize_stats["avg_scans_before"]
    prize_stats["avg_days_diff"] = prize_stats["avg_days_after"] - prize_stats["avg_days_before"]
    
    prize_stats["scans_growth_percent"] = np.where(
        prize_stats["avg_scans_before"] > 0,
        (prize_stats["avg_scans_after"] - prize_stats["avg_scans_before"]) / prize_stats["avg_scans_before"] * 100,
        np.nan 
    )
    prize_stats["days_growth_percent"] = np.where(
        prize_stats["avg_days_before"] > 0,
        (prize_stats["avg_days_after"] - prize_stats["avg_days_before"]) / prize_stats["avg_days_before"] * 100,
        np.nan
    )

    st.subheader(f"Сводка активности: {window_days} дней ДО и ПОСЛЕ события (выигрыша или X-го скана)")
    
    display_df = prize_stats.copy()
    display_df = display_df.rename(columns={
        "first_prize_name": "Группа / Приз",
        "users_count": "Пользователей",
        "avg_scans_before": "Сканы ДО",
        "avg_scans_after": "Сканы ПОСЛЕ",
        "avg_scans_diff": "Δ Сканов",
        "scans_growth_percent": "Рост сканов (%)",
        "avg_days_before": "Активные дни ДО",
        "avg_days_after": "Активные дни ПОСЛЕ",
        "avg_days_diff": "Δ Дней",
        "days_growth_percent": "Рост дней (%)"
    })
    
    # Sort so Control Group is at the top
    display_df["is_cg"] = display_df["Группа / Приз"].str.contains("Контрольная")
    display_df = display_df.sort_values(by=["is_cg", "Пользователей"], ascending=[False, False]).drop(columns=["is_cg"])
    
    st.dataframe(
        display_df.style.format({
            "Сканы ДО": "{:.2f}",
            "Сканы ПОСЛЕ": "{:.2f}",
            "Δ Сканов": "{:.2f}",
            "Рост сканов (%)": "{:.1f}%",
            "Активные дни ДО": "{:.2f}",
            "Активные дни ПОСЛЕ": "{:.2f}",
            "Δ Дней": "{:.2f}",
            "Рост дней (%)": "{:.1f}%"
        }),
        use_container_width=True
    )

    st.subheader("Визуализация изменения активности (Топ-10 групп)")
    
    # Ограничиваем количество групп для графика, чтобы браузер не зависал (Altair Facet Chart очень тяжелый)
    top_prizes_for_chart = display_df.head(10)["Группа / Приз"].tolist()
    
    melted_scans = prize_stats[prize_stats["first_prize_name"].isin(top_prizes_for_chart)].melt(
        id_vars=["first_prize_name"],
        value_vars=["avg_scans_before", "avg_scans_after"],
        var_name="period",
        value_name="value"
    )
    melted_scans["period"] = melted_scans["period"].map({"avg_scans_before": "ДО", "avg_scans_after": "ПОСЛЕ"})
    melted_scans["metric"] = "Средние сканирования"

    melted_days = prize_stats[prize_stats["first_prize_name"].isin(top_prizes_for_chart)].melt(
        id_vars=["first_prize_name"],
        value_vars=["avg_days_before", "avg_days_after"],
        var_name="period",
        value_name="value"
    )
    melted_days["period"] = melted_days["period"].map({"avg_days_before": "ДО", "avg_days_after": "ПОСЛЕ"})
    melted_days["metric"] = "Активные дни"
    
    melted = pd.concat([melted_scans, melted_days])

    chart = alt.Chart(melted).mark_bar().encode(
        x=alt.X("period:N", title="", sort=["ДО", "ПОСЛЕ"]),
        y=alt.Y("value:Q", title="Значение"),
        color=alt.Color("period:N", legend=alt.Legend(title="Период")),
        column=alt.Column("first_prize_name:N", title="", header=alt.Header(labelAngle=-45, labelAlign='right')),
        row=alt.Row("metric:N", title="")
    ).properties(
        width=120,
        height=200
    )
    
    st.altair_chart(chart)

    # Динамика
    st.subheader("Ежедневная динамика вокруг дня X (Дня выигрыша / Дня X-го скана)")
    merged["day_offset"] = np.floor(merged["days_since_event"]).astype(int)
    daily_data = merged[(merged["day_offset"] >= -window_days) & (merged["day_offset"] <= window_days)]
    
    top_prizes = display_df["Группа / Приз"].head(4).tolist()
    selected_prizes = st.multiselect("Выберите группы для показа динамики:", options=display_df["Группа / Приз"].tolist(), default=top_prizes)
    
    if selected_prizes:
        daily_filtered = daily_data[daily_data["first_prize_name"].isin(selected_prizes)]
        
        # Aggregation optimized
        total_scans_per_day = daily_filtered.groupby(["first_prize_name", "day_offset"]).size().reset_index(name="total_scans")
        users_per_prize = prize_stats[["first_prize_name", "users_count"]]
        daily_avg = total_scans_per_day.merge(users_per_prize, on="first_prize_name")
        daily_avg["avg_scans"] = daily_avg["total_scans"] / daily_avg["users_count"]
        
        line_chart = alt.Chart(daily_avg).mark_line(point=True).encode(
            x=alt.X("day_offset:Q", title="Дни от события (0 = день события)"),
            y=alt.Y("avg_scans:Q", title="Ср. сканов на 1 пользователя"),
            color=alt.Color("first_prize_name:N", title="Группа", sort=selected_prizes),
            tooltip=["first_prize_name", "day_offset", "avg_scans"]
        ).properties(
            height=400
        ).interactive()
        
        rule = alt.Chart(pd.DataFrame({'x': [0]})).mark_rule(color='red', strokeDash=[3, 3]).encode(x='x:Q')
        st.altair_chart(line_chart + rule, use_container_width=True)

