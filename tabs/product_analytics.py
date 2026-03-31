import streamlit as st
import pandas as pd
import altair as alt
import json
import os

def load_product_mapping():
    mapping_path = os.path.join("utils", "product_mapping.json")
    if os.path.exists(mapping_path):
        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def render_product_analytics(df, USER_COL, local_tz):
    st.header("Анализ продуктов и категорий")

    if "product_campaign_id" not in df.columns:
        st.error("Колонка product_campaign_id отсутствует в данных.")
        return

    if not USER_COL:
        st.error("Не выбран идентификатор пользователя.")
        return

    # Оставляем только строки с известным product_campaign_id
    pdf = df.dropna(subset=["product_campaign_id"]).copy()
    
    if pdf.empty:
        st.warning("Нет данных о сканированиях продуктов с учетом текущих фильтров.")
        return

    # --- 1. Category Summary ---
    st.subheader("1. Сводная информация по категориям")
    cat_summary = pdf.groupby("product_category").agg(
        scans=("product_category", "count"),
        unique_users=(USER_COL, "nunique"),
        product_count=("product_name", "nunique")
    ).reset_index().sort_values("scans", ascending=False)
    
    cat_summary.columns = ["Категория", "Всего сканирований", "УНИК. пользователей", "Видов продуктов"]
    st.dataframe(cat_summary, use_container_width=True, hide_index=True)
    st.divider()

    # --- 2. Product Summary ---
    st.subheader("2. Сводная информация по продуктам")
    summary_df = pdf.groupby(["product_category", "product_campaign_id_str", "product_name"]).agg(
        scans=("product_name", "count"),
        unique_users=(USER_COL, "nunique")
    ).reset_index().sort_values("scans", ascending=False)
    
    summary_df.columns = ["Категория", "ID", "Продукт", "Всего сканирований", "Уникальных пользователей"]
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    st.divider()

    # --- 3. Joint Scans ---
    st.subheader("3. Совместные сканирования (Кросс-продажи)")
    st.caption("Частота совместного сканирования разных продуктов одним пользователем.")
    
    user_products = pdf.groupby(USER_COL)["product_name"].unique()
    user_products = user_products[user_products.apply(len) > 1]
    
    if len(user_products) > 0:
        co_occurrence = {}
        for products in user_products:
            prods = sorted(list(products))
            for i in range(len(prods)):
                for j in range(i + 1, len(prods)):
                    pair = (prods[i], prods[j])
                    co_occurrence[pair] = co_occurrence.get(pair, 0) + 1
        
        if co_occurrence:
            co_df = pd.DataFrame([
                {"Продукт А": p1, "Продукт Б": p2, "Совместных пользователей": count}
                for (p1, p2), count in co_occurrence.items()
            ])
            co_df = co_df.sort_values("Совместных пользователей", ascending=False).reset_index(drop=True)
            st.dataframe(co_df, use_container_width=True)
        else:
            st.info("Нет совместных сканирований.")
    else:
        st.info("Нет пользователей с совместными сканированиями.")

    st.divider()

    # --- 4. Interactive Graphs ---
    st.subheader("4. Графики динамики")
    
    mode = st.radio("Режим графика", ["По продукту", "По категории"], horizontal=True)
    
    if mode == "По категории":
        all_cats = sorted(pdf["product_category"].unique())
        selected = st.selectbox("Выберите категорию", all_cats)
        plot_df = pdf[pdf["product_category"] == selected].copy()
        title = f"Динамика категории: {selected}"
    else:
        all_prods = sorted(pdf["product_name"].unique())
        selected = st.selectbox("Выберите продукт", all_prods)
        plot_df = pdf[pdf["product_name"] == selected].copy()
        title = f"Динамика продукта: {selected}"

    if not plot_df.empty:
        date_col = "win_date" if "win_date" in plot_df.columns else "created_date"
        if local_tz != "UTC":
            plot_df[date_col] = plot_df[date_col].dt.tz_convert(local_tz)
        
        plot_df["day"] = plot_df[date_col].dt.floor("D")
        daily_counts = plot_df.groupby("day").size().reset_index(name="scans")
        
        chart = alt.Chart(daily_counts).mark_line(point=True).encode(
            x=alt.X("day:T", title="День"),
            y=alt.Y("scans:Q", title="Количество сканирований"),
            tooltip=[alt.Tooltip("day:T", format="%Y-%m-%d"), "scans"]
        ).properties(height=400, title=title).interactive()
        
        st.altair_chart(chart, use_container_width=True)
        
        c1, c2 = st.columns(2)
        c1.metric("Всего сканирований (срез)", len(plot_df))
        c2.metric("Уникальных пользователей (срез)", plot_df[USER_COL].nunique())
    else:
        st.info("Нет данных для графика.")
