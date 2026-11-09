import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="美股持倉訊號儀表板", layout="wide")

# 你的持倉（來自 2026-10-31 對帳單）
HOLDINGS = {
    "VOO": 7.82789,
    "EPD": 95.39788,
    "TSLA": 8.86216,
    "VZ": 76.69738,
    "O": 48.44974,
    "JNJ": 9.32249,
    "ARCC": 118.91823,
    "PG": 9.85584,
    "SCHP": 51.38192,
    "GOOGL": 3.87485,
    "SOXX": 2.05541,
    "TSM": 1.34955,
    "COHR": 1.40927,
}

st.title("美股持倉訊號儀表板")
st.caption("邏輯參考台指 v3 / D2：EMA20 vs EMA60 + 布林 + ATR。僅供參考，非下單建議。")

@st.cache_data(ttl=300)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None

        # 處理 yfinance 可能回傳 MultiIndex 的情況
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.dropna(subset=["Close"])
        if len(df) < 60:
            return None

        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA60"] = df["Close"].ewm(span=60, adjust=False).mean()
        df["BB_mid"] = df["Close"].rolling(20).mean()
        df["BB_std"] = df["Close"].rolling(20).std()
        df["BB_upper"] = df["BB_mid"] + 2 * df["BB_std"]
        df["BB_lower"] = df["BB_mid"] - 2 * df["BB_std"]
        df["ATR"] = (df["High"] - df["Low"]).rolling(14).mean()
        return df
    except Exception:
        return None

def check_signal(df):
    if df is None or len(df) < 60:
        return "資料不足", "—", "—"

    last = df.iloc[-1]

    # 強制轉成純數字，避免 Series 比較錯誤
    def to_float(val):
        if isinstance(val, (pd.Series, np.ndarray)):
            return float(val.iloc[0] if hasattr(val, "iloc") else val[0])
        return float(val)

    ema20 = to_float(last["EMA20"])
    ema60 = to_float(last["EMA60"])
    close = to_float(last["Close"])
    open_ = to_float(last["Open"])
    atr = to_float(last["ATR"])
    bb_upper = to_float(last["BB_upper"])
    bb_lower = to_float(last["BB_lower"])

    trend = "多頭" if ema20 > ema60 else "空頭"

    long_ok = (ema20 > ema60) and (close > bb_upper * 0.98) and ((close - open_) > atr * 0.5)
    short_ok = (ema20 < ema60) and (close < bb_lower * 1.02) and ((open_ - close) > atr * 0.5)

    if long_ok:
        status = "可考慮做多"
    elif short_ok:
        status = "可考慮做空"
    else:
        status = "空手 / 條件未觸發"

    stop_long = close - atr * 1.2
    stop_short = close + atr * 1.2

    return status, trend, f"多停損 ~{stop_long:.1f} / 空停損 ~{stop_short:.1f}"

# 主畫面
col1, col2 = st.columns([3, 1])
with col1:
    st.subheader("即時訊號")
with col2:
    if st.button("重新整理"):
        st.cache_data.clear()
        st.rerun()

rows = []
for ticker, shares in HOLDINGS.items():
    df = get_data(ticker)
    status, trend, stop = check_signal(df)

    price = None
    value = None
    if df is not None and not df.empty:
        price = float(df["Close"].iloc[-1])
        value = price * shares

    rows.append({
        "標的": ticker,
        "股數": round(shares, 2),
        "現價": f"${price:.2f}" if price else "—",
        "市值": f"${value:,.0f}" if value else "—",
        "趨勢": trend,
        "訊號": status,
        "停損估計": stop,
    })

df_view = pd.DataFrame(rows)
st.dataframe(df_view, use_container_width=True, hide_index=True)

st.divider()
st.markdown("""
**說明**
- 趨勢：EMA20 > EMA60 = 多頭，反之空頭
- 訊號為簡化版條件（接近原台指儀表板的突破邏輯），僅供觀察
- 資料來源：Yahoo Finance，約 5 分鐘快取
- 這不是投資建議，下單前請自行確認
""")

st.caption(f"最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
