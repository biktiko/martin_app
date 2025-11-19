import pandas as pd
import datetime as dt

def build_time_index(series, granularity: str):
    if granularity == "Day":
        key = series.dt.floor("D"); freq = "D"
    elif granularity == "Week":
        key = series.dt.to_period("W").dt.start_time; freq = "W-MON"
    else:
        key = series.dt.to_period("M").dt.to_timestamp(); freq = "MS"
    return key, freq

def _to_naive_utc_series(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s, errors="coerce")
    try:
        if s.dt.tz is not None:
            return s.dt.tz_convert("UTC").dt.tz_localize(None)
        else:
            return s
    except Exception:
        return s

def _to_naive_utc_ts(ts) -> dt.datetime:
    t = pd.Timestamp(ts)
    if t.tz is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t.to_pydatetime()

def aggregate_time(df_in: pd.DataFrame, date_field: str, granularity: str, unique_mode: bool, local_tz: str, user_col: str):
    """
    Агрегация по win_date без смещения дней.
    """
    if df_in.empty:
        return pd.DataFrame(columns=["date","count"])
    
    s = pd.to_datetime(df_in[date_field], errors="coerce", utc=True)
    if local_tz != "UTC":
        s = s.dt.tz_convert(local_tz)

    if granularity == "Day":
        key = s.dt.floor("D")
        freq = "D"
    elif granularity == "Week":
        key = s.dt.to_period("W").dt.start_time
        freq = "W-MON"
    else:
        key = s.dt.to_period("M").dt.to_timestamp()
        freq = "MS"

    if unique_mode and user_col:
        grouped = df_in.assign(_g=key).groupby("_g")[user_col].nunique()
    else:
        grouped = pd.Series(1, index=key).groupby(level=0).size()

    out = grouped.sort_index().reset_index()
    out.columns = ["date", "count"]

    if hasattr(out["date"].dt, "tz"):
        out["date"] = out["date"].dt.tz_localize(None)

    full_range = pd.date_range(out["date"].min(), out["date"].max(), freq=freq)
    full = pd.DataFrame({"date": full_range})
    out = full.merge(out, on="date", how="left").fillna({"count": 0})

    first_nonzero_idx = out.index[out["count"] > 0]
    if len(first_nonzero_idx):
        first_i = first_nonzero_idx[0]
        if first_i > 0:
            out = out.loc[first_i:].reset_index(drop=True)

    if len(out) and out.iloc[-1]["count"] == 0:
        out = out.iloc[:-1].reset_index(drop=True)

    return out

def safe_rate(num, den):
    return (num / den) if den else 0

def span_stats(series: pd.Series):
    s = pd.to_numeric(series.dropna(), errors="coerce")
    s = s[~pd.isna(s)]
    if len(s) == 0:
        return {"mean": 0.0, "q25": 0.0, "median": 0.0, "q75": 0.0, "count": 0}
    return {
        "mean": float(s.mean()),
        "q25": float(s.quantile(0.25)),
        "median": float(s.quantile(0.5)),
        "q75": float(s.quantile(0.75)),
        "count": int(len(s))
    }
