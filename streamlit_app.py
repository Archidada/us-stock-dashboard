import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="美股持倉訊號儀表板", layout="wide")

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

st.title("美股持倉訊號儀表板（波段強化版）")
st.caption("趨勢過濾 + 回檔進場 + 量能確認 + ATR 停損 + 簡易回測。僅供參考，非下單建議。")

@st.cache_data(ttl=300)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close", "Volume"])
        if len(df) < 80:
            return None

        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["EMA60"] = df["Close"].ewm(span=60, adjust=False).mean()
        df["ATR"] = (df["High"] - df["Low"]).rolling(14).mean()
        df["Vol_MA20"] = df["Volume"].rolling(20).mean()
        delta = df["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["RSI"] = 100 - (100 / (1 + rs))
        return df
    except Exception:
        return None

def to_float(val):
    if isinstance(val, (pd.Series, np.ndarray)):
        return float(val.iloc[0] if hasattr(val, "iloc") else val[0])
    return float(val)

def check_signal(df):
    if df is None or len(df) < 60:
        return "資料不足", "—", "—", "—", "—"

    last = df.iloc[-1]
    ema20 = to_float(last["EMA20"])
    ema60 = to_float(last["EMA60"])
    close = to_float(last["Close"])
    atr = to_float(last["ATR"])
    vol = to_float(last["Volume"])
    vol_ma = to_float(last["Vol_MA20"])
    rsi = to_float(last["RSI"]) if not pd.isna(last["RSI"]) else 50

    trend = "多頭" if ema20 > ema60 else "空頭"
    dist = abs(close - ema20)
    volume_ok = vol > vol_ma * 1.2
    not_extended = dist < atr * 2

    status = "空手 / 條件未觸發"
    stop = "—"
    rr = "—"

    if trend == "多頭" and not_extended and volume_ok and rsi > 40:
        if abs(close - ema20) <= atr * 0.5:
            status = "可考慮做多（回檔）"
            stop_price = close - atr * 1.2
            stop = f"停損 ~{stop_price:.1f}"
            rr = "RR ≈ 1.67"

    if trend == "空頭" and not_extended and volume_ok and rsi < 60:
        if abs(close - ema20) <= atr * 0.5:
            status = "可考慮做空（反彈）"
            stop_price = close + atr * 1.2
            stop = f"停損 ~{stop_price:.1f}"
            rr = "RR ≈ 1.67"

    return status, trend, stop, rr, f"RSI {rsi:.0f}"

def simple_backtest(df, ticker):
    if df is None or len(df) < 100:
        return None
    trades = []
    position = None

    for i in range(60, len(df) - 1):
        row = df.iloc[i]
        close = to_float(row["Close"])
        ema20 = to_float(row["EMA20"])
        ema60 = to_float(row["EMA60"])
        atr = to_float(row["ATR"])
        vol = to_float(row["Volume"])
        vol_ma = to_float(row["Vol_MA20"])
        rsi = to_float(row["RSI"]) if not pd.isna(row["RSI"]) else 50

        trend = "long" if ema20 > ema60 else "short"
        volume_ok = vol > vol_ma * 1.2
        near_ema = abs(close - ema20) <= atr * 0.5
        not_extended = abs(close - ema20) < atr * 2

        if position is None:
            if trend == "long" and near_ema and volume_ok and not_extended and rsi > 40:
                position = {"side": "long", "entry": close, "stop": close - atr*1.2, "target": close + atr*2.0, "entry_idx": i}
            elif trend == "short" and near_ema and volume_ok and not_extended and rsi < 60:
                position = {"side": "short", "entry": close, "stop": close + atr*1.2, "target": close - atr*2.0, "entry_idx": i}

        if position is not None:
            next_high = to_float(df.iloc[i+1]["High"])
            next_low = to_float(df.iloc[i+1]["Low"])
            next_close = to_float(df.iloc[i+1]["Close"])

            hit = None
            if position["side"] == "long":
                if next_low <= position["stop"]:
                    hit = position["stop"]
                elif next_high >= position["target"]:
                    hit = position["target"]
            else:
                if next_high >= position["stop"]:
                    hit = position["stop"]
                elif next_low <= position["target"]:
                    hit = position["target"]

            if hit is not None or (i - position["entry_idx"] > 15):
                exit_price = hit if hit is not None else next_close
                pnl = (exit_price - position["entry"]) if position["side"] == "long" else (position["entry"] - exit_price)
                trades.append(pnl / position["entry"])
                position = None

    if not trades:
        return {"trades": 0, "win_rate": 0, "avg_return": 0, "total_return": 0}

    wins = [t for t in trades if t > 0]
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100,
        "avg_return": np.mean(trades) * 100,
        "total_return": sum(trades) * 100,
    }

col1, col2 = st.columns([3, 1])
with col1:
    st.subheader("即時訊號")
with col2:
    if st.button("重新整理"):
        st.cache_data.clear()
        st.rerun()

rows = []
backtest_rows = []

for ticker, shares in HOLDINGS.items():
    df = get_data(ticker)
    status, trend, stop, rr, rsi_txt = check_signal(df)

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
        "停損 / RR": f"{stop} | {rr}" if stop != "—" else "—",
        "RSI": rsi_txt,
    })

    bt = simple_backtest(df, ticker)
    if bt:
        backtest_rows.append({
            "標的": ticker,
            "交易次數": bt["trades"],
            "勝率": f"{bt['win_rate']:.0f}%",
            "平均報酬": f"{bt['avg_return']:.1f}%",
            "累計報酬": f"{bt['total_return']:.1f}%",
        })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.subheader("簡易回測（過去約 1 年）")
st.caption("規則：趨勢方向 + 回檔到 EMA20 ± 0.5ATR + 量能放大 + RSI 過濾。停損 1.2ATR、停利 2ATR，最多持有 15 天。")
if backtest_rows:
    st.dataframe(pd.DataFrame(backtest_rows), use_container_width=True, hide_index=True)
else:
    st.info("回測資料不足")

st.divider()
st.markdown("""
**波段強化條件**
- 只做趨勢方向（EMA20 vs EMA60）
- 回檔到 EMA20 ± 0.5 ATR 才進場
- 成交量 > 20 日均量 1.2 倍
- 價格離 EMA20 不超過 2 ATR
- RSI 過濾（多頭 >40、空頭 <60）
- 停損 1.2 ATR、停利 2 ATR

**注意**：回測為簡化模擬，未計入手續費、滑價與隔夜跳空，僅供參考規則品質。
""")

st.caption(f"最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
