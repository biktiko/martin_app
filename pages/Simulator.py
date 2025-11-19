import math
import pandas as pd
import streamlit as st
import altair as alt
from dataclasses import dataclass, asdict

st.set_page_config(page_title="Goose Balance Simulator", layout="wide")

# ------------------------------- Model ----------------------------------------
@dataclass
class StageSpec:
    name: str
    hunger_cap: int
    size_cap: int
    daily_hunger_loss: int
    stageup_bonus_pts: int = 0  # optional: add to wallet on stage-up

DEFAULT_STAGES = {
    "small":  StageSpec("small",  hunger_cap=5,  size_cap=5,  daily_hunger_loss=1, stageup_bonus_pts=5),
    "medium": StageSpec("medium", hunger_cap=10, size_cap=15, daily_hunger_loss=1, stageup_bonus_pts=10),
    "adult":  StageSpec("adult",  hunger_cap=20, size_cap=15, daily_hunger_loss=2, stageup_bonus_pts=0),
}

def next_stage_name(cur: str) -> str | None:
    order = ["small", "medium", "adult"]
    i = order.index(cur)
    return order[i+1] if i+1 < len(order) else None

# Cost rule: 1st feed free, then 1,2,3,...
def feed_cost_for(feed_index_1_based: int) -> int:
    return max(0, feed_index_1_based - 1)

# ------------------------------ Simulator -------------------------------------
def simulate_goose(
    weekly_pts: float,
    stages: dict[str, StageSpec],
    accrual_mode: str = "daily",  # "daily" or "weekly"
    weekly_value_mode: str = "points",  # "points" or "feeds"
    start_stage: str = "small",
    start_hunger: int = 3,
    start_size: int = 1,
    visit_daily: bool = True,
    max_paid_feeds_per_day: int = 10,
    add_stageup_bonus_to_wallet: bool = True,
    max_days: int = 365
) -> tuple[pd.DataFrame, dict]:
    cur_stage = start_stage
    hunger = start_hunger
    size = start_size
    wallet = 0.0

    log = []
    day_reached_medium = None
    day_reached_adult = None
    died_on_day = None

    def spec() -> StageSpec:
        return stages[cur_stage]

    daily_income = weekly_pts / 7.0

    # Weekly feeding plan (only used when weekly_value_mode == "feeds")
    weekly_feed_plan: list[int] | None = None
    if weekly_value_mode == "feeds":
        total_feeds = max(0, int(round(weekly_pts)))
        baseline = 1 if visit_daily else 0
        # start with baseline per day
        plan = [baseline for _ in range(7)]
        extras = max(0, total_feeds - baseline * 7)
        # fill extras from Monday forward, respecting daily cap = 1 + max_paid_feeds_per_day
        i = 0
        while extras > 0 and i < 7:
            cap_today = baseline + max(0, int(max_paid_feeds_per_day)) + 0  # total feeds allowed today
            can_add = max(0, cap_today - plan[i])
            add_now = min(extras, can_add)
            plan[i] += add_now
            extras -= add_now
            i += 1
        weekly_feed_plan = plan

    for day in range(1, max_days + 1):
        # Начисление очков (только для режима валюты)
        if weekly_value_mode == "points":
            if accrual_mode == "daily":
                wallet += daily_income
            else:
                if day == 1 or ((day - 1) % 7 == 0):
                    wallet += weekly_pts

        # Суточное снижение голода до визита
        hunger -= spec().daily_hunger_loss
        if hunger <= 0:
            hunger = 0
            died_on_day = day
            log.append({
                "day": day, "stage": cur_stage, "hunger": hunger, "size": size,
                "feeds_today": 0, "paid_spent": 0.0, "wallet_end": wallet,
                "size_gains": 0, "stage_up": ""
            })
            break

        feeds_today = 0
        paid_spent = 0.0
        size_gains = 0
        stage_up_label = ""

        if visit_daily:
            if weekly_value_mode == "feeds" and weekly_feed_plan is not None:
                target_feeds_today = weekly_feed_plan[(day - 1) % 7]
                max_feeds_today = target_feeds_today
            else:
                max_feeds_today = 1 + max(0, int(max_paid_feeds_per_day))

            # Жадная стратегия: кормим пока можем платить за следующую и пока есть смысл
            while feeds_today < max_feeds_today:
                next_cost = max(0, feeds_today)  # 1-я кормёжка = 0, далее 1,2,3...
                if weekly_value_mode == "points":
                    if next_cost > 0 and wallet + 1e-9 < next_cost:
                        break
                    if next_cost > 0:
                        wallet -= next_cost
                        paid_spent += next_cost
                else:
                    # В режиме "feeds" кошелёк не ограничивает, но считаем гипотетические затраты
                    if next_cost > 0:
                        paid_spent += next_cost

                # Рост размера: происходит, если ПЕРЕД кормлением желудок полный
                if hunger >= spec().hunger_cap and size < spec().size_cap:
                    size += 1
                    size_gains += 1

                    # Проверка stage-up на текущем этапе
                    if size >= spec().size_cap:
                        prev_stage = cur_stage
                        nxt = next_stage_name(cur_stage)
                        if nxt is not None:
                            # Переход на следующий этап
                            cur_stage = nxt
                            stage_up_label = f"{prev_stage}->{cur_stage}"

                            # Начисляем бонус за переход (берём у прошлого этапа)
                            if add_stageup_bonus_to_wallet:
                                wallet += stages[prev_stage].stageup_bonus_pts

                            # Отметка дней достижения этапов
                            if prev_stage == "small" and day_reached_medium is None:
                                day_reached_medium = day
                            if prev_stage == "medium" and day_reached_adult is None:
                                day_reached_adult = day

                # Применяем кормление: +1 hunger до cap
                hunger = min(hunger + 1, spec().hunger_cap)
                feeds_today += 1

                # Если уже взрослый — продолжаем день ради трат, но можно выйти из цикла кормлений
                if cur_stage == "adult":
                    # оставим цикл завершиться по ограничителям; хотим видеть реальную трату
                    pass

        log.append({
            "day": day, "stage": cur_stage, "hunger": hunger, "size": size,
            "feeds_today": feeds_today, "paid_spent": paid_spent,
            "wallet_end": wallet, "size_gains": size_gains,
            "stage_up": stage_up_label
        })

        # Можно завершать симуляцию, как только достигли adult (метрика времени до adult)
        if cur_stage == "adult":
            if day_reached_adult is None:
                day_reached_adult = day
            break

    df = pd.DataFrame(log)
    summary = {
        "days_run": int(df["day"].max()) if not df.empty else 0,
        "reached_medium_on_day": int(day_reached_medium) if day_reached_medium is not None else None,
        "reached_adult_on_day": int(day_reached_adult) if day_reached_adult is not None else None,
        "died_on_day": int(died_on_day) if died_on_day is not None else None,
        "final_stage": df.iloc[-1]["stage"] if not df.empty else start_stage,
        "final_hunger": int(df.iloc[-1]["hunger"]) if not df.empty else start_hunger,
        "final_size": int(df.iloc[-1]["size"]) if not df.empty else start_size,
        "wallet_end": float(df.iloc[-1]["wallet_end"]) if not df.empty else 0.0,
        "total_paid_spent": float(df["paid_spent"].sum()) if not df.empty else 0.0
    }
    return df, summary

# ------------------------------- UI -------------------------------------------
st.title("Goose Growth Balance Simulator")

st.caption("Проверь, за сколько дней гусь вырастет до Medium/Adult при разных недельных доходах очков и правилах кормления. Логика: 1‑я кормёжка в день бесплатна, далее: 1,2,3... очков. Рост (+1 size) происходит только если кормёжка сделана при полном желудке (hunger == cap) перед кормёжкой.")

with st.sidebar:
    st.header("Параметры стадий")
    colA, colB, colC = st.columns(3)
    small_hcap = colA.number_input("Small hunger cap", 1, 100, value=DEFAULT_STAGES["small"].hunger_cap)
    small_scap = colB.number_input("Small size cap", 1, 200, value=DEFAULT_STAGES["small"].size_cap)
    small_loss = colC.number_input("Small daily loss", 0, 10, value=DEFAULT_STAGES["small"].daily_hunger_loss)

    colA, colB, colC = st.columns(3)
    med_hcap = colA.number_input("Medium hunger cap", 1, 100, value=DEFAULT_STAGES["medium"].hunger_cap)
    med_scap = colB.number_input("Medium size cap", 1, 200, value=DEFAULT_STAGES["medium"].size_cap)
    med_loss = colC.number_input("Medium daily loss", 0, 10, value=DEFAULT_STAGES["medium"].daily_hunger_loss)

    colA, colB, colC = st.columns(3)
    ad_hcap  = colA.number_input("Adult hunger cap", 1, 200, value=DEFAULT_STAGES["adult"].hunger_cap)
    ad_scap  = colB.number_input("Adult size cap", 1, 300, value=DEFAULT_STAGES["adult"].size_cap)
    ad_loss  = colC.number_input("Adult daily loss", 0, 10, value=DEFAULT_STAGES["adult"].daily_hunger_loss)

    stage_bonus = st.checkbox("Начислять бонус очков за Stage-Up", value=True)
    colB1, colB2 = st.columns(2)
    bonus_s_to_m = colB1.number_input("Бонус small→medium", 0, 100, value=5)
    bonus_m_to_a = colB2.number_input("Бонус medium→adult", 0, 100, value=10)

    st.header("Стартовые значения")
    start_hunger = st.number_input("Начальный hunger", 0, 100, value=3)
    start_size   = st.number_input("Начальный size", 0, 300, value=1)

    st.header("Доход очков")
    weekly_pts = st.number_input("Недельное значение", 0.0, 1000.0, value=2.0, step=0.5, help="В зависимости от режима ниже: очки (валюта) или количество кормлений в неделю")
    value_mode = st.radio("Тип недельного значения", ["Очки (валюта)", "Кормления (шт.)"], index=0)
    value_mode_key = "points" if value_mode.startswith("Очки") else "feeds"
    accrual_mode = st.radio("Распределение по времени (для очков)", ["Ежедневно равными долями", "Раз в неделю (понедельник)"], index=0, help="Применяется только если выбран режим Очки (валюта)")
    accrual_mode_key = "daily" if accrual_mode.startswith("Еже") else "weekly"

    st.header("Кормление")
    visit_daily = st.checkbox("Пользователь заходит каждый день", value=True)
    max_paid_feeds_per_day = st.slider("Макс платных кормлений в день", 0, 50, value=10)
    max_days = st.slider("Горизонт симуляции (дней)", 7, 365, value=180)

# Build stage specs from sidebar
stages = {
    "small":  StageSpec("small",  small_hcap, small_scap, small_loss, stageup_bonus_pts=(bonus_s_to_m if stage_bonus else 0)),
    "medium": StageSpec("medium", med_hcap,   med_scap,   med_loss,   stageup_bonus_pts=(bonus_m_to_a if stage_bonus else 0)),
    "adult":  StageSpec("adult",  ad_hcap,    ad_scap,    ad_loss,    stageup_bonus_pts=0),
}

# Main run
df, summary = simulate_goose(
    weekly_pts=weekly_pts,
    stages=stages,
    accrual_mode=accrual_mode_key,
    weekly_value_mode=value_mode_key,
    start_stage="small",
    start_hunger=start_hunger,
    start_size=start_size,
    visit_daily=visit_daily,
    max_paid_feeds_per_day=max_paid_feeds_per_day,
    add_stageup_bonus_to_wallet=stage_bonus,
    max_days=max_days
)

# ----------------------------- Output -----------------------------------------
st.subheader("Результаты сценария")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Дней до Medium", summary["reached_medium_on_day"] if summary["reached_medium_on_day"] else "—")
c2.metric("Дней до Adult", summary["reached_adult_on_day"] if summary["reached_adult_on_day"] else "—")
c3.metric("Смерть на дне", summary["died_on_day"] if summary["died_on_day"] else "—")
c4.metric("Остаток очков", f"{summary['wallet_end']:.1f}")

tab1, tab2, tab3 = st.tabs(["Размер/Дни", "Дневной лог", "Быстрые сценарии"])
with tab1:
    if not df.empty:
        df_plot = df.copy()
        df_plot["size_cum"] = df_plot["size"]
        chart = (
            alt.Chart(df_plot)
            .mark_line(point=True)
            .encode(
                x=alt.X("day:Q", title="День"),
                y=alt.Y("size_cum:Q", title="Размер (size)"),
                color=alt.value("#2a74ea"),
                tooltip=["day","stage","hunger","size","feeds_today","paid_spent","wallet_end","size_gains"]
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Нет данных симуляции (гусь умер в первый же день или горизонт = 0).")

with tab2:
    st.dataframe(df, use_container_width=True, height=360)
    st.download_button(
        "Скачать дневной лог (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name="goose_simulation_log.csv",
        mime="text/csv"
    )

with tab3:
    st.caption("Сравнение типичных недельных доходов очков при текущих параметрах и политике кормлений.")
    rates = [1, 2, 5, 10]
    rows = []
    for r in rates:
        dfx, sx = simulate_goose(
            weekly_pts=float(r),
            stages=stages,
            accrual_mode=accrual_mode_key,
            weekly_value_mode=value_mode_key,
            start_stage="small",
            start_hunger=start_hunger,
            start_size=start_size,
            visit_daily=visit_daily,
            max_paid_feeds_per_day=max_paid_feeds_per_day,
            add_stageup_bonus_to_wallet=stage_bonus,
            max_days=max_days
        )
        rows.append({
            "pts_per_week": r,
            "to_medium_days": sx["reached_medium_on_day"],
            "to_adult_days": sx["reached_adult_on_day"],
            "died_on_day": sx["died_on_day"],
            "spent_total": round(sx["total_paid_spent"], 1),
        })
    comp = pd.DataFrame(rows)
    st.dataframe(comp, use_container_width=True)