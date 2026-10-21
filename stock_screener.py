#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
選股大師 - 自動篩選程式（台股）
六大技術面選股法：RSI / KD / MA / MTM / MACD / 寶塔線(三線反轉)

安裝：  pip install yfinance pandas numpy
用法：
  # 篩選（今天的訊號）
  python stock_screener.py --tickers 2330 2317 2454 --min-score 3
  python stock_screener.py --file my_list.txt --min-score 2

  # 回測（檢驗這些條件過去到底有沒有用）
  python stock_screener.py --file my_list.txt --backtest --horizon 10

my_list.txt：每行一個股票代號，例如 2330；上櫃股可寫 6488.TWO
注意：僅供研究參考，不構成投資建議。
"""
import argparse
import datetime as dt
import sys

import numpy as np
import pandas as pd

# 預設股票池（僅為示範，請用 --tickers / --file 換成你自己的清單）
DEFAULT_UNIVERSE = [
    "2330", "2317", "2454", "2308", "2382", "2412", "2881", "2882", "2891",
    "1301", "1303", "2002", "2603", "2609", "3711", "2357", "2395", "3034",
    "2884", "2886", "1216", "2301", "3008", "2327", "6505",
]


# ------------------------------------------------------------------ 指標 ---
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI"""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def kd(df: pd.DataFrame, n: int = 9):
    """台灣慣用 KD：K=2/3*K前+1/3*RSV，D=2/3*D前+1/3*K，起始值 50"""
    low_n = df["Low"].rolling(n).min()
    high_n = df["High"].rolling(n).max()
    rsv = ((df["Close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100).values
    k = np.full(len(df), np.nan)
    d = np.full(len(df), np.nan)
    pk, pd_ = 50.0, 50.0
    for i, r in enumerate(rsv):
        if np.isnan(r):
            continue
        pk = 2 / 3 * pk + 1 / 3 * r
        pd_ = 2 / 3 * pd_ + 1 / 3 * pk
        k[i], d[i] = pk, pd_
    return pd.Series(k, df.index), pd.Series(d, df.index)


def macd(close: pd.Series, fast=12, slow=26, sig=9):
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=sig, adjust=False).mean()
    return dif, dea, dif - dea


def three_line_break(close: pd.Series) -> pd.Series:
    """
    寶塔線（三線反轉圖）。回傳每日方向：+1 紅(上升) / -1 綠(下降) / 0 尚未形成。
    規則：續創新高(低)就加一條同向線；反向收盤要突破前三條線的最高(低)點才算翻轉。
    """
    c = close.values
    n = len(c)
    state = np.zeros(n)
    lines = []  # (open, close)
    for i in range(1, n):
        if not lines:
            if c[i] != c[0]:
                lines.append((c[0], c[i]))
        else:
            o, lc = lines[-1]
            last3 = lines[-3:]
            hi = max(max(a, b) for a, b in last3)
            lo = min(min(a, b) for a, b in last3)
            if lc > o:  # 目前紅線
                if c[i] > lc:
                    lines.append((lc, c[i]))
                elif c[i] < lo:
                    lines.append((o, c[i]))
            else:  # 目前綠線
                if c[i] < lc:
                    lines.append((lc, c[i]))
                elif c[i] > hi:
                    lines.append((o, c[i]))
        if lines:
            state[i] = 1 if lines[-1][1] > lines[-1][0] else -1
    return pd.Series(state, close.index)


# ------------------------------------------------------------------ 訊號 ---
def cross_up(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def within(event: pd.Series, n: int) -> pd.Series:
    """最近 n 天內曾發生"""
    return event.astype(float).rolling(n, min_periods=1).max().fillna(0).astype(bool)


def build_signals(df: pd.DataFrame, lookback: int = 3) -> pd.DataFrame:
    """每個指標一個『偏多訊號』布林欄位，並計算總分。"""
    c = df["Close"]
    out = pd.DataFrame(index=df.index)

    # 1) RSI：由超賣區(30)向上突破，且尚未過熱
    r = rsi(c, 14)
    out["RSI"] = within(cross_up(r, pd.Series(30.0, index=r.index)), lookback) & (r < 70)

    # 2) KD：K 上穿 D（黃金交叉），且 K 值在 80 以下（避免高檔鈍化）
    k, d = kd(df, 9)
    out["KD"] = within(cross_up(k, d), lookback) & (k < 80)

    # 3) MA：5MA 上穿 20MA，股價站上 20MA，且 20MA 向上
    ma5, ma20 = c.rolling(5).mean(), c.rolling(20).mean()
    out["MA"] = within(cross_up(ma5, ma20), lookback) & (c > ma20) & (ma20 > ma20.shift(3))

    # 4) MTM(10)：動能由負轉正，或上穿其 10 日均線且為正
    mtm = c - c.shift(10)
    mtm_ma = mtm.rolling(10).mean()
    out["MTM"] = within(cross_up(mtm, pd.Series(0.0, index=mtm.index)), lookback) | (
        within(cross_up(mtm, mtm_ma), lookback) & (mtm > 0)
    )

    # 5) MACD：DIF 上穿 DEA（黃金交叉），或柱狀體由負翻正
    dif, dea, hist = macd(c)
    out["MACD"] = within(cross_up(dif, dea), lookback) | within(
        (hist > 0) & (hist.shift(1) <= 0), lookback
    )

    # 6) 寶塔線：由綠翻紅
    tlb = three_line_break(c)
    out["TLB"] = within((tlb == 1) & (tlb.shift(1) == -1), lookback)

    out = out.fillna(False)
    out["score"] = out[["RSI", "KD", "MA", "MTM", "MACD", "TLB"]].sum(axis=1)
    return out


# ------------------------------------------------------------------ 資料 ---
def normalize(code: str) -> str:
    code = code.strip().upper()
    return code if "." in code else code + ".TW"


def load_data(tickers, years: int):
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("請先安裝： pip install yfinance")
    end = dt.date.today() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=int(365 * years) + 30)
    data = {}
    for t in tickers:
        try:
            df = yf.download(t, start=start, end=end, auto_adjust=True,
                             progress=False, multi_level_index=False)
        except TypeError:  # 舊版 yfinance
            df = yf.download(t, start=start, end=end, auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close"])
        # 上市查無資料時，自動改試上櫃
        if df.empty and t.endswith(".TW"):
            alt = t[:-3] + ".TWO"
            df = yf.download(alt, start=start, end=end, auto_adjust=True,
                             progress=False, multi_level_index=False).dropna(subset=["Close"])
            t = alt
        if len(df) >= 80:
            data[t] = df
        else:
            print(f"[略過] {t}：資料不足", file=sys.stderr)
    return data


# ------------------------------------------------------------------ 篩選 ---
def screen(data, min_score, min_vol_lots, lookback):
    rows = []
    for t, df in data.items():
        avg_lots = df["Volume"].tail(20).mean() / 1000  # 股 -> 張
        if avg_lots < min_vol_lots:
            continue
        s = build_signals(df, lookback).iloc[-1]
        if s["score"] >= min_score:
            rows.append({
                "代號": t.split(".")[0],
                "收盤": round(float(df["Close"].iloc[-1]), 2),
                "分數": int(s["score"]),
                "20日均量(張)": int(avg_lots),
                **{k: ("V" if s[k] else "") for k in ["RSI", "KD", "MA", "MTM", "MACD", "TLB"]},
            })
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(["分數", "20日均量(張)"], ascending=False).reset_index(drop=True)
    return res


# ------------------------------------------------------------------ 回測 ---
def backtest_table(data, horizon, min_vol_lots, lookback):
    """
    檢驗：訊號出現後 N 個交易日的報酬，對比「任意一天買進」的基準。
    注意：訊號當天收盤才確定，這裡假設隔天進場，
    所以報酬由「訊號日隔天收盤」起算，以避免偷看未來。
    回傳 DataFrame；沒有資料時回傳空表。
    """
    cols = ["RSI", "KD", "MA", "MTM", "MACD", "TLB"]
    frames = []
    for t, df in data.items():
        if df["Volume"].tail(20).mean() / 1000 < min_vol_lots:
            continue
        sig = build_signals(df, lookback)
        sig["fwd"] = df["Close"].shift(-1 - horizon) / df["Close"].shift(-1) - 1
        frames.append(sig.dropna(subset=["fwd"]))
    if not frames:
        return pd.DataFrame()
    allr = pd.concat(frames)
    base = allr["fwd"]

    def stat(name, mask):
        x = allr.loc[mask, "fwd"]
        if len(x) == 0:
            return {"條件": name, "次數": 0}
        return {"條件": name, "次數": len(x),
                f"平均{horizon}日報酬%": round(x.mean() * 100, 2),
                "中位數%": round(x.median() * 100, 2),
                "勝率%": round((x > 0).mean() * 100, 1),
                "較基準超額%": round((x.mean() - base.mean()) * 100, 2)}

    rows = [stat("基準(任一天買進)", pd.Series(True, index=allr.index))]
    rows += [stat(c, allr[c]) for c in cols]
    rows += [stat(f"分數>={k}", allr["score"] >= k) for k in (2, 3, 4, 5)]
    return pd.DataFrame(rows)


BACKTEST_NOTE = ("提醒：樣本重疊、未計手續費與證交稅(約0.585%來回)，"
                 "且有存活者偏差，結果僅供參考。")


def backtest(data, horizon, min_vol_lots, lookback):
    out = backtest_table(data, horizon, min_vol_lots, lookback)
    if out.empty:
        print("沒有可回測的資料")
        return
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    print("\n" + BACKTEST_NOTE)


# ------------------------------------------------------------------ 主程式 ---
def main():
    ap = argparse.ArgumentParser(description="台股技術面自動選股")
    ap.add_argument("--tickers", nargs="*", help="股票代號，如 2330 2317")
    ap.add_argument("--file", help="股票清單檔（每行一檔）")
    ap.add_argument("--min-score", type=int, default=3, help="最低符合指標數(1~6)")
    ap.add_argument("--lookback", type=int, default=3, help="訊號有效天數")
    ap.add_argument("--min-vol", type=int, default=500, help="20日均量下限(張)")
    ap.add_argument("--years", type=float, default=2, help="抓取年數（回測建議>=3）")
    ap.add_argument("--backtest", action="store_true", help="執行回測")
    ap.add_argument("--horizon", type=int, default=10, help="回測持有天數")
    a = ap.parse_args()

    codes = a.tickers or []
    if a.file:
        with open(a.file, encoding="utf-8-sig") as f:
            codes += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    codes = codes or DEFAULT_UNIVERSE
    tickers = [normalize(c) for c in dict.fromkeys(codes)]

    print(f"下載 {len(tickers)} 檔資料中…")
    data = load_data(tickers, a.years if not a.backtest else max(a.years, 3))

    if a.backtest:
        backtest(data, a.horizon, a.min_vol, a.lookback)
        return

    res = screen(data, a.min_score, a.min_vol, a.lookback)
    if res.empty:
        print(f"沒有股票達到分數 >= {a.min_score}")
        return
    print(res.to_string(index=False))
    fn = f"screener_{dt.date.today():%Y%m%d}.csv"
    res.to_csv(fn, index=False, encoding="utf-8-sig")
    print(f"\n已輸出：{fn}")


if __name__ == "__main__":
    main()
