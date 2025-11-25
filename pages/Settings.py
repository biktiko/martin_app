import streamlit as st
import pandas as pd
from utils.prizes import load_prize_map, save_prize_map
from utils.auth import require_auth

st.set_page_config(page_title="Settings", layout="wide")

# Enforce authentication
require_auth()

st.title("Настройки")

st.header("Таблица призов (Prize Mapping)")

current_map = load_prize_map()

# Convert to DataFrame for editing
data = [{"prize_id": k, "prize_name": v} for k, v in current_map.items()]
df = pd.DataFrame(data)

# Sort by prize_id (try to convert to int for sorting)
try:
    df["prize_id_int"] = df["prize_id"].astype(int)
    df = df.sort_values("prize_id_int").drop(columns=["prize_id_int"])
except:
    df = df.sort_values("prize_id")

edited_df = st.data_editor(
    df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "prize_id": st.column_config.TextColumn("ID Приза", required=True),
        "prize_name": st.column_config.TextColumn("Название", required=True)
    },
    hide_index=True
)

if st.button("Сохранить изменения"):
    new_map = {}
    for _, row in edited_df.iterrows():
        pid = str(row["prize_id"]).strip()
        pname = str(row["prize_name"]).strip()
        if pid:
            new_map[pid] = pname
    
    save_prize_map(new_map)
    st.success("Таблица призов обновлена! Перезагрузите основную страницу, чтобы увидеть изменения.")
