# -*- coding: utf-8 -*-
"""台股技術面自動選股 - Streamlit 網頁介面"""
import streamlit as st

import stock_screener as ss

st.set_page_config(page_title="台股自動選股", page_icon="📈", layout="wide")
st.title("📈 台股技術面自動選股")
st.caption("RSI / KD / MA / MTM / MACD / 寶塔線　｜　僅供研究參考，不構成投資建議")


@st.cache_data(ttl=3600, show_spinner=False)
def get_data(tickers: tuple, years: float):
    return ss.load_data(list(tickers), years)


with st.sidebar:
    st.header("設定")
    text = st.text_area(
        "股票代號（每行一檔，上櫃請加 .TWO）",
        value="\n".join(ss.DEFAULT_UNIVERSE),
        height=220,
    )
    min_score = st.slider("最低符合指標數", 1, 6, 3)
    lookback = st.slider("訊號有效天數", 1, 10, 3)
    min_vol = st.number_input("20日均量下限（張）", 0, 100000, 500, step=100)
    horizon = st.slider("回測持有天數", 3, 60, 10)

codes = [c.strip() for c in text.splitlines() if c.strip()]
tickers = tuple(ss.normalize(c) for c in dict.fromkeys(codes))
if len(tickers) > 150:
    st.warning("股票數量太多會很慢，已只取前 150 檔。")
    tickers = tickers[:150]

tab1, tab2 = st.tabs(["🔍 今日篩選", "🧪 回測"])

with tab1:
    if st.button("開始篩選", type="primary"):
        with st.spinner(f"下載 {len(tickers)} 檔資料中…"):
            data = get_data(tickers, 2)
        res = ss.screen(data, min_score, min_vol, lookback)
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
    if st.button("執行回測"):
        with st.spinner("下載 3 年資料並回測中，請稍候…"):
            data = get_data(tickers, 3)
            table = ss.backtest_table(data, horizon, min_vol, lookback)
        if table.empty:
            st.info("沒有可回測的資料。")
        else:
            st.dataframe(table, use_container_width=True, hide_index=True)
            st.caption(ss.BACKTEST_NOTE)
