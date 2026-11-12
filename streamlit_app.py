import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="美股持倉訊號儀表板", layout="wide")

DEFAULT_HOLDINGS = {
    "VOO": 7.82789, "EPD": 95.39788, "TSLA": 8.86216, "VZ": 76.69738,
    "O": 48.44974, "JNJ": 9.32249, "ARCC": 118.91823, "PG": 9.85584,
    "SCHP": 51.38192, "GOOGL": 3.87485, "SOXX": 2.05541, "TSM": 1.34955,
    "COHR": 1.40927,
}

st.title("美股持倉訊號儀表板（v3 策略改版）")
st.caption("參考 asinkk/txo-dashboard 的 v3 邏輯：突破 + 拉回進場、ATR 停損、Chandelier 移動停利。僅供參考。")

st.subheader("監測標的")
col_a, col_b = st.columns([3, 1])
with col_a:
    extra_input = st.text_input("額外監測股票（逗號分隔）", value="", placeholder="NVDA, META, AAPL")
with col_b:
    if st.button("重新整理", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

tickers_to_show = dict(DEFAULT_HOLDINGS)
if extra_input.strip():
    for t in extra_input.upper().replace(" ", "").split(","):
        if t and t not in tickers_to_show:
            tickers_to_show[t] = 0

@st.cache_data(ttl=300)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close", "High", "Low", "Open", "Volume"])
        if len(df) < 80:
            return None

        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA60"] = df["Close"].ewm(span=60, adjust=False).mean()
        df["BB_mid"] = df["Close"].rolling(20).mean()
        df["BB_std"] = df["Close"].rolling(20).std()
        df["BB_upper"] = df["BB_mid"] + 2 * df["BB_std"]
        df["BB_lower"] = df["BB_mid"] - 2 * df["BB_std"]
        df["ATR"] = (df["High"] - df["Low"]).rolling(14).mean()
        ema12 = df["Close"].ewm(span=12, adjust=False).mean()
        ema26 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df["MACD_hist"] = macd - signal
        return df
    except Exception:
        return None

def to_float(val):
    if isinstance(val, (pd.Series, np.ndarray)):
        return float(val.iloc[0] if hasattr(val, "iloc") else val[0])
    try:
        return float(val)
    except:
        return np.nan

def check_v3(df):
    if df is None or len(df) < 65:
        return "資料不足", "—", "—", "—"

    i = -1
    row = df.iloc[i]
    prev = df.iloc[i-1]

    close = to_float(row["Close"])
    open_ = to_float(row["Open"])
    high = to_float(row["High"])
    low = to_float(row["Low"])
    ema20 = to_float(row["EMA20"])
    ema60 = to_float(row["EMA60"])
    atr = to_float(row["ATR"])
    atr_prev = to_float(prev["ATR"])
    bb_upper = to_float(row["BB_upper"])
    macd_hist = to_float(row["MACD_hist"])
    prev_high = to_float(prev["High"])

    if any(np.isnan(x) for x in [close, ema20, ema60, atr]):
        return "資料不足", "—", "—", "—"

    trend = "多頭" if ema20 > ema60 else "空頭"
    body = abs(close - open_)
    rng = high - low if high > low else 0.01
    body_ratio = body / rng

    status = "空手"
    stop_txt = "—"
    detail = ""

    if trend == "多頭":
        breakout = (
            body_ratio >= 0.5 and
            body >= 0.8 * atr_prev and
            close > bb_upper and
            macd_hist > 0
        )
        pullback = (
            body_ratio >= 0.5 and
            low <= ema20 and
            close > ema20 and
            close > prev_high and
            ema60 > to_float(df.iloc[i-5]["EMA60"])
        )

        if breakout:
            status = "可考慮做多（突破）"
            detail = "突破布林 + 實體夠強 + MACD正"
        elif pullback:
            status = "可考慮做多（拉回）"
            detail = "回測 EMA20 後站回 + 破前高"

        if status != "空手":
            raw_stop_dist = close - (low - 0.1 * atr)
            stop_dist = max(min(raw_stop_dist, 1.5 * atr), 0.5 * atr)
            stop_price = close - stop_dist
            stop_txt = f"停損 ~{stop_price:.1f}（約 {stop_dist:.1f} 點）"

    return status, trend, stop_txt, detail

st.subheader("即時訊號（v3 邏輯）")

rows = []
for ticker, shares in tickers_to_show.items():
    df = get_data(ticker)
    status, trend, stop, detail = check_v3(df)

    price = None
    value = None
    if df is not None and not df.empty:
        price = to_float(df["Close"].iloc[-1])
        value = price * shares if shares > 0 else None

    rows.append({
        "標的": ticker,
        "股數": round(shares, 2) if shares > 0 else "—",
        "現價": f"${price:.2f}" if price and not np.isnan(price) else "—",
        "市值": f"${value:,.0f}" if value else "—",
        "趨勢": trend,
        "訊號": status,
        "停損": stop,
        "說明": detail,
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()
st.markdown("""
**v3 改版條件（參考 asinkk）**
- 趨勢：EMA20 > EMA60 才考慮做多
- **突破**：實體 ≥ 高低差 50%、實體 ≥ 0.8 ATR、收盤破布林上軌、MACD 柱狀圖 > 0
- **拉回**：實體 ≥ 50%、低點觸及 EMA20、收盤站回 EMA20、收盤破前高、EMA60 近 5 根上升
- 停損：以當根極值為基準，0.5～1.5 ATR
- 出場建議：Chandelier 移動停利（最高點 - 5 ATR），或獲利 1R 後保本

**注意**：這是日線版本，僅供觀察，不是下單指令。
""")

st.caption(f"最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
