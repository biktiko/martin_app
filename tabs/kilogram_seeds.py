import streamlit as st
import pandas as pd
import datetime as dt
import io
from utils.called_numbers_manager import (
    normalize_phone,
    load_called_numbers,
    add_called_numbers,
    remove_called_number,
    save_called_numbers
)

def get_amd_val(prize_id):
    try:
        # Normalize and map prize_id to its AMD value
        pid = int(float(prize_id))
        if pid == 54:
            return 3000
        elif pid == 55:
            return 5000
        elif pid == 56:
            return 10000
        elif pid == 57:
            return 20000
    except Exception:
        pass
    return 0

def render_kilogram_seeds(df, USER_COL, USER_LABEL, local_tz):
    st.header("Аналитика по килограммовым семечкам (Դրամային շահումներ)")

    tab_analytics, tab_calling, tab_database = st.tabs([
        "📊 Аналитика & Реестр",
        "📞 Обзвон (Первый выигрыш)",
        "⚙️ База обзвоненных номеров"
    ])

    with tab_analytics:
        # 1. Filter dataset for Kilogram Seeds prizes
        kg_prizes = [54, 55, 56, 57]
        
        if "prize_id" not in df.columns:
            st.error("Колонка prize_id отсутствует в данных.")
        else:
            # Get subset of winning rows
            df_wins = df[pd.to_numeric(df["prize_id"].astype(str).str.split('.').str[0].str.strip(), errors='coerce').isin(kg_prizes)].copy()
            if "region_id" in df_wins.columns:
                df_wins = df_wins[pd.to_numeric(df_wins["region_id"], errors="coerce") == 2].copy()
            
            # Map each win to its AMD value
            df_wins["amd_value"] = df_wins["prize_id"].apply(get_amd_val)
            
            # Fill won_prize_status if not exist
            if "won_prize_status" not in df_wins.columns:
                df_wins["won_prize_status"] = pd.NA

            # Map status value to readable string
            def _status_name(status_val):
                if pd.isna(status_val):
                    return "Неизвестный статус"
                try:
                    val = int(float(status_val))
                    if val == 1:
                        return "1 - Won (Не отправили данные)"
                    elif val == 2:
                        return "2 - Pending (Отправили данные)"
                    elif val == 4:
                        return "4 - Payed / Обработано"
                    else:
                        return f"{val} - Другой статус"
                except Exception:
                    return str(status_val)

            df_wins["status_label"] = df_wins["won_prize_status"].apply(_status_name)

            # 2. Key Metrics Calculation
            total_won_amd = int(df_wins["amd_value"].sum())
            total_wins_count = len(df_wins)
            
            # Sent data: status 2 (pending) or other non-1 statuses (like status 4)
            df_sent = df_wins[pd.to_numeric(df_wins["won_prize_status"], errors='coerce').isin([2, 4])]
            df_waiting = df_wins[pd.to_numeric(df_wins["won_prize_status"], errors='coerce') == 1]
            df_unknown = df_wins[~pd.to_numeric(df_wins["won_prize_status"], errors='coerce').isin([1, 2, 4])]
            
            sent_amd = int(df_sent["amd_value"].sum())
            sent_count = len(df_sent)
            
            waiting_amd = int(df_waiting["amd_value"].sum())
            waiting_count = len(df_waiting)
            
            unknown_amd = int(df_unknown["amd_value"].sum())
            unknown_count = len(df_unknown)

            # --- Metrics Layout ---
            st.markdown("### Ключевые показатели")
            col_m1, col_m2, col_m3 = st.columns(3)
            
            col_m1.metric("Всего выиграно (AMD)", f"{total_won_amd:,} ֏", f"Всего выигрышей: {total_wins_count}")
            col_m2.metric("Отправили данные (AMD)", f"{sent_amd:,} ֏", f"Победителей: {sent_count}")
            col_m3.metric("Не отправили данные (AMD)", f"{waiting_amd:,} ֏", f"Победителей: {waiting_count}")
            
            if unknown_count > 0:
                st.info(f"Выигрышей без статуса / с неизвестным статусом: **{unknown_count}** на сумму **{unknown_amd:,} ֏**.")

            st.divider()

            # --- Breakdown Tables ---
            st.markdown("### Сводная информация по статусам и номиналам")
            
            col_t1, col_t2 = st.columns(2)
            
            with col_t1:
                st.markdown("#### 📊 Разбивка по статусам")
                if not df_wins.empty:
                    status_summary = df_wins.groupby("status_label").agg(
                        count=("amd_value", "count"),
                        sum_amd=("amd_value", "sum")
                    ).reset_index()
                    status_summary["share_count"] = (status_summary["count"] / total_wins_count * 100).round(1)
                    status_summary["share_count"] = status_summary["share_count"].astype(str) + " %"
                    
                    status_summary.columns = ["Статус выигрыша", "Количество", "Сумма (AMD)", "Доля по кол-ву"]
                    st.dataframe(status_summary, use_container_width=True, hide_index=True)
                else:
                    st.info("Нет данных")

            with col_t2:
                st.markdown("#### 💰 Разбивка по номиналам призов")
                if not df_wins.empty:
                    def _prize_desc(prize_id):
                        pid = int(float(prize_id))
                        if pid == 54: return "3,000 AMD"
                        if pid == 55: return "5,000 AMD"
                        if pid == 56: return "10,000 AMD"
                        if pid == 57: return "20,000 AMD"
                        return f"ID {pid}"

                    df_wins["prize_desc"] = df_wins["prize_id"].apply(_prize_desc)
                    prize_summary = df_wins.groupby("prize_desc").agg(
                        count=("amd_value", "count"),
                        sum_amd=("amd_value", "sum")
                    ).reset_index()
                    
                    prize_summary.columns = ["Номинал приза", "Количество", "Сумма (AMD)"]
                    st.dataframe(prize_summary, use_container_width=True, hide_index=True)
                else:
                    st.info("Нет данных")

            st.divider()

            # --- Winner Register ---
            st.markdown("### 📋 Реестр победителей")
            
            # Controls
            c_ctrl1, c_ctrl2 = st.columns([2, 1])
            
            search_q = c_ctrl1.text_input("🔍 Поиск победителя (по ID или Телефону)", placeholder="Введите ID пользователя или номер телефона...")
            
            status_filter = c_ctrl2.selectbox(
                "Фильтр по статусу отправки данных",
                ["Все статусы", "Отправили данные (Pending)", "Не отправили данные (Won)", "Прочие / Неизвестно"]
            )
            
            # Apply status filter
            df_display = df_wins.copy()
            if status_filter == "Отправили данные (Pending)":
                df_display = df_display[pd.to_numeric(df_display["won_prize_status"], errors='coerce').isin([2, 4])]
            elif status_filter == "Не отправили данные (Won)":
                df_display = df_display[pd.to_numeric(df_display["won_prize_status"], errors='coerce') == 1]
            elif status_filter == "Прочие / Неизвестно":
                df_display = df_display[~pd.to_numeric(df_display["won_prize_status"], errors='coerce').isin([1, 2, 4])]
                
            # Apply text search
            if search_q.strip():
                q = search_q.strip().lower()
                search_mask = pd.Series(False, index=df_display.index)
                
                if USER_COL and USER_COL in df_display.columns:
                    search_mask |= df_display[USER_COL].astype(str).str.lower().str.contains(q)
                    
                if "phone_number" in df_display.columns:
                    search_mask |= df_display["phone_number"].astype(str).str.lower().str.contains(q)
                    
                if "first_name" in df_display.columns:
                    search_mask |= df_display["first_name"].astype(str).str.lower().str.contains(q)
                    
                if "last_name" in df_display.columns:
                    search_mask |= df_display["last_name"].astype(str).str.lower().str.contains(q)
                    
                df_display = df_display[search_mask]

            # Date formatting for display
            if not df_display.empty:
                df_display = df_display.sort_values("win_date", ascending=False)
                
                display_cols = []
                if USER_COL:
                    display_cols.append(USER_COL)
                
                possible_cols = ["first_name", "last_name", "phone_number", "win_date", "prize_name", "amd_value", "status_label", "is_win_received"]
                for col in possible_cols:
                    if col in df_display.columns:
                        display_cols.append(col)
                        
                # Format dates for presentation
                df_table = df_display[display_cols].copy()
                if "win_date" in df_table.columns:
                    # Localize to selected tz
                    if local_tz != "UTC" and df_table["win_date"].dt.tz is not None:
                        df_table["win_date"] = df_table["win_date"].dt.tz_convert(local_tz)
                    df_table["win_date"] = df_table["win_date"].dt.strftime("%d.%m.%Y %H:%M")
                    
                df_table.rename(columns={
                    USER_COL: USER_LABEL,
                    "first_name": "Имя",
                    "last_name": "Фамилия",
                    "phone_number": "Телефон",
                    "win_date": "Дата выигрыша",
                    "prize_name": "Название приза",
                    "amd_value": "Сумма (AMD)",
                    "status_label": "Статус",
                    "is_win_received": "Получен?"
                }, inplace=True)
                
                st.dataframe(df_table, use_container_width=True, hide_index=True)
                
                # Download register
                st.download_button(
                    "📥 Скачать реестр победителей килограммовых семечек (CSV)",
                    df_table.to_csv(index=False).encode("utf-8"),
                    file_name="kilogram_seeds_winners.csv",
                    mime="text/csv"
                )
            else:
                st.warning("Нет записей победителей, соответствующих критериям фильтрации.")

    with tab_calling:
        st.subheader("📞 Список на обзвон (Первый выигрыш)")
        st.markdown(
            "В этот список попадают пользователи, которые выиграли денежный приз (3,000, 5,000, 10,000 или 20,000 AMD) "
            "**в первый раз** (у них статус `1 - Won` и нет ни одной другой записи со статусами `2 - Pending`, `3 - Rejected`, `4 - Payed` по денежным призам), "
            "и которые еще **не были обзвонены**."
        )
        
        # 1. Load called numbers
        called_nums = load_called_numbers()
        
        # 2. Extract monetary wins
        kg_prizes = [54, 55, 56, 57]
        if "prize_id" not in df.columns:
            st.error("Колонка prize_id отсутствует в данных.")
        else:
            # Filter all scans for monetary prizes
            df_all_kg = df[pd.to_numeric(df["prize_id"].astype(str).str.split('.').str[0].str.strip(), errors='coerce').isin(kg_prizes)].copy()
            
            if df_all_kg.empty:
                st.info("Нет записей денежных выигрышей в базе данных для Армении.")
            else:
                if "phone_number" in df_all_kg.columns:
                    df_all_kg["normalized_phone"] = df_all_kg["phone_number"].apply(normalize_phone)
                    group_col = "normalized_phone"
                else:
                    group_col = USER_COL

                # Group by phone/user to find statuses across all their scans
                user_status_sets = df_all_kg.groupby(group_col)["won_prize_status"].apply(
                    lambda x: set(pd.to_numeric(x, errors="coerce").dropna().astype(int))
                ).to_dict()
                
                # Find users whose only statuses in won_prize_status are 1 (and no 2, 3, 4)
                target_user_ids = []
                for uid, statuses in user_status_sets.items():
                    if 1 in statuses and not statuses.intersection({2, 3, 4}):
                        target_user_ids.append(uid)
                        
                # Filter all_kg rows for these target users with status 1
                df_targets = df_all_kg[
                    (df_all_kg[group_col].isin(target_user_ids)) &
                    (pd.to_numeric(df_all_kg["won_prize_status"], errors="coerce") == 1)
                ].copy()
                
                # Apply region filter for the current call list
                if "region_id" in df_targets.columns:
                    df_targets = df_targets[pd.to_numeric(df_targets["region_id"], errors="coerce") == 2].copy()
                
                # Add total scans count for each user (for caller context)
                if USER_COL in df.columns:
                    user_scan_counts = df.groupby(USER_COL).size().to_dict()
                    df_targets["total_scans"] = df_targets[USER_COL].map(user_scan_counts).fillna(0).astype(int)
                else:
                    df_targets["total_scans"] = 1
                    
                # Exclude already called numbers
                if not df_targets.empty and "phone_number" in df_targets.columns:
                    df_targets["normalized_phone"] = df_targets["phone_number"].apply(normalize_phone)
                    df_targets = df_targets[~df_targets["normalized_phone"].isin(called_nums)]
                    # Sort by win_date descending first to keep the latest win
                    if "win_date" in df_targets.columns:
                        df_targets = df_targets.sort_values("win_date", ascending=False)
                    # Deduplicate by phone number to make sure each number is listed only once
                    df_targets = df_targets.drop_duplicates(subset=["normalized_phone"], keep="first")
                else:
                    df_targets["normalized_phone"] = ""
                    
                if df_targets.empty:
                    st.success("🎉 Все пользователи обзвонены! Список пуст.")
                else:
                    st.info(f"Найдено пользователей для обзвона: **{len(df_targets)}**")
                    
                    # Dynamic search/filter within the call list
                    call_search = st.text_input("🔍 Быстрый поиск по списку обзвона", placeholder="Введите телефон или имя для фильтрации...")
                    df_call_display = df_targets.copy()
                    if call_search.strip():
                        qs = call_search.strip().lower()
                        mask = pd.Series(False, index=df_call_display.index)
                        if "phone_number" in df_call_display.columns:
                            mask |= df_call_display["phone_number"].astype(str).str.lower().str.contains(qs)
                        if "first_name" in df_call_display.columns:
                            mask |= df_call_display["first_name"].astype(str).str.lower().str.contains(qs)
                        if "last_name" in df_call_display.columns:
                            mask |= df_call_display["last_name"].astype(str).str.lower().str.contains(qs)
                        df_call_display = df_call_display[mask]
                    
                    # Generate Excel file
                    df_excel = df_call_display.copy()
                    df_excel["prize_desc"] = df_excel["prize_id"].apply(lambda pid: f"{get_amd_val(pid):,} AMD" if get_amd_val(pid) > 0 else f"ID {pid}")
                    
                    if "win_date" in df_excel.columns:
                        if local_tz != "UTC" and df_excel["win_date"].dt.tz is not None:
                            df_excel["win_date_loc"] = df_excel["win_date"].dt.tz_convert(local_tz).dt.strftime("%d.%m.%Y %H:%M")
                        else:
                            df_excel["win_date_loc"] = df_excel["win_date"].dt.strftime("%d.%m.%Y %H:%M")
                    else:
                        df_excel["win_date_loc"] = ""
                        
                    df_excel_export = pd.DataFrame({
                        "Phone": df_excel["phone_number"].fillna(""),
                        "First Name": df_excel["first_name"].fillna(""),
                        "Last Name": df_excel["last_name"].fillna(""),
                        "Win Date": df_excel["win_date_loc"],
                        "Prize": df_excel["prize_desc"],
                        "Total Scans": df_excel["total_scans"],
                        "Export Date": dt.datetime.now().strftime("%d.%m.%Y %H:%M")
                    })
                    
                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                        df_excel_export.to_excel(writer, index=False, sheet_name="Call List")
                        worksheet = writer.sheets["Call List"]
                        for col in worksheet.columns:
                            max_len = max(len(str(cell.value or '')) for cell in col)
                            col_letter = col[0].column_letter
                            worksheet.column_dimensions[col_letter].width = max(max_len + 3, 10)
                            
                    excel_data = buffer.getvalue()
                    
                    col_act1, col_act2 = st.columns([1, 1])
                    
                    with col_act1:
                        st.download_button(
                            label="📥 Download Excel file for operators (.xlsx)",
                            data=excel_data,
                            file_name=f"call_list_{dt.date.today().strftime('%d_%m_%Y')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
                    with col_act2:
                        if st.button("✅ Отметить все номера в этой таблице как обзвоненные"):
                            phones_list = df_call_display["normalized_phone"].dropna().tolist()
                            if phones_list:
                                added_count = 0
                                called_dict = load_called_numbers()
                                now_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                for ph in phones_list:
                                    if ph not in called_dict:
                                        called_dict[ph] = {
                                            "added_at": now_str,
                                            "comment": "Bulk marked from calling list export"
                                        }
                                        added_count += 1
                                if added_count > 0:
                                    save_called_numbers(called_dict)
                                    st.success(f"Успешно добавлено {added_count} номеров в базу обзвоненных!")
                                    st.rerun()
                                    
                    st.divider()
                    
                    df_table_show = df_excel_export.drop(columns=["Export Date"])
                    st.dataframe(df_table_show, use_container_width=True, hide_index=True)
                    
                    # Manual results upload section
                    st.markdown("### 📥 Импорт результатов от операторов")
                    st.markdown(
                        "Когда операторы вернут вам список номеров, которым они позвонили, скопируйте его и вставьте сюда. "
                        "Они будут добавлены в базу обзвоненных, и эти пользователи **исчезнут** из следующей выгрузки."
                    )
                    
                    import_text = st.text_area(
                        "Вставьте список номеров (из Excel, WhatsApp, или разделенные запятой/новой строкой)", 
                        height=150, 
                        placeholder="Например:\n+37498199628\n099 12 34 56\n+995 557 76 77 43",
                        key="call_tab_import_text"
                    )
                    
                    if st.button("➕ Добавить номера в обзвоненные", key="btn_add_calling_tab_import"):
                        if import_text.strip():
                            added = add_called_numbers(import_text, comment="Imported from operator feedback")
                            if added:
                                st.success(f"Успешно импортировано и добавлено номеров: **{len(added)}**")
                                st.rerun()
                            else:
                                st.warning("Не найдено новых номеров для добавления (возможно, они уже есть в базе или формат не распознан).")
                        else:
                            st.error("Пожалуйста, вставьте список номеров.")

    with tab_database:
        st.subheader("⚙️ База обзвоненных номеров")
        st.markdown(
            "Здесь находится полная база номеров телефонов клиентов, которым уже звонили. "
            "Номера отсюда никогда повторно не попадут в список обзвона."
        )
        
        called_dict = load_called_numbers()
        
        col_db1, col_db2 = st.columns([1, 2])
        
        with col_db1:
            st.markdown("#### Добавить номера вручную")
            manual_input = st.text_area("Номера для ручного добавления", height=150, placeholder="Введите номера...", key="db_manual_input")
            db_comment = st.text_input("Комментарий / Источник", value="Ручное добавление", key="db_manual_comment")
            
            if st.button("➕ Добавить в базу", key="btn_add_db_tab"):
                if manual_input.strip():
                    added = add_called_numbers(manual_input, comment=db_comment)
                    if added:
                        st.success(f"Добавлено номеров: **{len(added)}**")
                        st.rerun()
                    else:
                        st.warning("Новые номера не добавлены (возможно, они уже в базе).")
                else:
                    st.error("Введите номера.")
                    
        with col_db2:
            st.markdown(f"#### Текущая база ({len(called_dict)} номеров)")
            
            if not called_dict:
                st.info("База обзвоненных номеров пока пуста.")
            else:
                db_rows = []
                for phone, meta in called_dict.items():
                    db_rows.append({
                        "Телефон": phone,
                        "Дата добавления": meta.get("added_at", "Неизвестно"),
                        "Комментарий": meta.get("comment", "")
                    })
                df_db = pd.DataFrame(db_rows)
                
                db_search = st.text_input("🔍 Поиск по базе", placeholder="Введите телефон или комментарий для поиска...")
                if db_search.strip():
                    q_db = db_search.strip().lower()
                    df_db = df_db[
                        df_db["Телефон"].astype(str).str.lower().str.contains(q_db) |
                        df_db["Комментарий"].astype(str).str.lower().str.contains(q_db)
                    ]
                
                st.dataframe(df_db, use_container_width=True, hide_index=True)
                
                st.markdown("##### 🗑️ Удалить номер из базы (вернуть в список обзвона)")
                phone_to_delete = st.selectbox(
                    "Выберите номер для удаления",
                    options=[""] + sorted(df_db["Телефон"].tolist()),
                    format_func=lambda x: f"{x} ({called_dict.get(x, {}).get('comment', '')})" if x else "Выберите номер..."
                )
                
                if st.button("🗑️ Удалить выбранный номер"):
                    if phone_to_delete:
                        if remove_called_number(phone_to_delete):
                            st.success(f"Номер {phone_to_delete} успешно удален из базы обзвоненных.")
                            st.rerun()
                        else:
                            st.error("Не удалось удалить номер.")
                    else:
                        st.error("Выберите номер для удаления.")

