# tw-stock-screener 台股技術面自動選股

以六種經典技術指標（RSI、KD、MA、MTM、MACD、寶塔線）自動篩選台股，
每個指標出現偏多訊號得 1 分，依總分排序；並內建回測功能，檢驗各條件的歷史表現。

> ⚠️ **免責聲明**：本專案僅供程式設計與研究學習，不構成任何投資建議。
> 技術指標有落後性與假訊號，回測結果不代表未來績效，投資風險請自行承擔。

## 安裝
```bash
pip install -r requirements.txt
```

## 使用
```bash
# 篩選今天符合 3 個以上訊號的股票
python stock_screener.py --file my_list.txt --min-score 3

# 回測：訊號出現後持有 10 天的表現
python stock_screener.py --file my_list.txt --backtest --horizon 10
```
`my_list.txt` 每行一個代號（如 `2330`；上櫃股寫 `6488.TWO`）。

## 訊號定義（預設最近 3 天內發生）
| 指標 | 偏多條件 |
|---|---|
| RSI(14) | 由 30 向上突破，且低於 70 |
| KD(9,3,3) | K 上穿 D，且 K < 80 |
| MA | 5MA 上穿 20MA，股價在 20MA 之上且 20MA 向上 |
| MTM(10) | 由負轉正，或上穿自身均線且為正 |
| MACD | DIF 上穿 DEA，或柱狀體翻正 |
| 寶塔線 | 由綠翻紅（三線反轉） |

## 限制
- 資料來自 Yahoo Finance，可能缺漏或延遲。
- 回測未計手續費與證交稅，且有存活者偏差。

## 授權
MIT License
