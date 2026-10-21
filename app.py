# -*- coding: utf-8 -*-
"""台股技術面自動選股 - Streamlit 網頁介面"""
import streamlit as st

import stock_screener as ss

st.set_page_config(page_title="台股自動選股", page_icon="📈", layout="wide")
st.title("📈 台股技術面自動選股")
st.caption("RSI / KD / MA / MTM / MACD / 寶塔線　｜　僅供研究參考，不構成投資建議")


@st.cache_data(ttl=3600, show_spinner=False)
def get_universe(top_n: int, include_otc: bool):
    return ss.fetch_universe(top_n, include_otc)


@st.cache_data(ttl=3600, show_spinner=False)
def get_data(tickers: tuple, years: float):
    return ss.load_data_batch(tickers, years)


with st.sidebar:
    st.header("股票池")
    mode = st.radio("來源", ["自動：成交金額前 N 大", "自訂清單"])
    names = {}
    if mode.startswith("自動"):
        top_n = st.slider("取前 N 檔", 30, 300, 100, step=10)
        otc = st.checkbox("包含上櫃", value=True)
        uni = get_universe(top_n, otc)
        if uni.empty:
            st.error("抓不到股票清單（證交所或網路暫時異常），請稍後再試或改用自訂清單。")
            st.stop()
        tickers = tuple(uni["ticker"])
        names = dict(zip(uni["ticker"], uni["name"]))
        st.caption(f"已載入 {len(tickers)} 檔（依最近交易日成交金額排序）")
    else:
        text = st.text_area("股票代號（每行一檔，上櫃請加 .TWO）",
                            value="\n".join(ss.DEFAULT_UNIVERSE), height=200)
        codes = [c.strip() for c in text.splitlines() if c.strip()]
        tickers = tuple(ss.normalize(c) for c in dict.fromkeys(codes))[:300]

    st.header("條件")
    min_score = st.slider("最低符合指標數", 1, 6, 3)
    lookback = st.slider("訊號有效天數", 1, 10, 3)
    min_vol = st.number_input("20日均量下限（張）", 0, 100000, 500, step=100)
    horizon = st.slider("回測持有天數", 3, 60, 10)

tab1, tab2 = st.tabs(["🔍 今日篩選", "🧪 回測"])

with tab1:
    if st.button("開始篩選", type="primary"):
        with st.spinner(f"下載 {len(tickers)} 檔資料中，可能需要 1～2 分鐘…"):
            data = get_data(tickers, 2)
        st.caption(f"成功取得 {len(data)} / {len(tickers)} 檔資料")
        res = ss.screen(data, min_score, min_vol, lookback, names)
        if res.empty:
            st.info(f"沒有股票達到分數 ≥ {min_score}，可以調低門檻再試。")
        else:
            st.success(f"共 {len(res)} 檔符合條件")
            st.dataframe(res, use_container_width=True, hide_index=True)
            st.download_button(
                "下載 CSV",
                res.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                file_name="screener_result.csv",
                mime="text/csv",
            )

with tab2:
    st.write("檢驗這些條件在過去的實際表現，並與「任意一天買進」比較。")
    if mode.startswith("自動"):
        st.warning("自動股票池是依「最近」成交金額挑選的，用它回測會偏樂觀"
                   "（挑的是現在熱門的股票）。結果請保守看待。")
    if st.button("執行回測"):
        with st.spinner("下載 3 年資料並回測中，請稍候…"):
            data = get_data(tickers, 3)
            table = ss.backtest_table(data, horizon, min_vol, lookback)
        if table.empty:
            st.info("沒有可回測的資料。")
        else:
            st.dataframe(table, use_container_width=True, hide_index=True)
            st.caption(ss.BACKTEST_NOTE)
