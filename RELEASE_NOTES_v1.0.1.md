# 遊戲即時翻譯工具 v1.0.1

小幅更新：新增**單檔版**散布選項 + 句子卡 bug 修復。

## 下載

| 檔案 | 大小 | 說明 |
|---|---|---|
| [`翻譯工具.exe`](https://github.com/brokenblack/manga-TCNtranslator/releases/download/v1.0.1/翻譯工具.exe) | 402 MB | **新版** — 單一 exe，下載即用，分享方便 |
| [`使用說明.txt`](https://github.com/brokenblack/manga-TCNtranslator/releases/download/v1.0.1/使用說明.txt) | 10 KB | 給使用者的操作說明 |


## 修復

- **句子卡選取詞元後讀音欄位沒更新** — `SentenceDialog._select_token()` 原本只更新內部變數，沒同步 UI 上的讀音 Entry。現在點 token 會即時把讀音切換為該詞的讀音（對齊挖空卡行為）。
  Commit: [c7084cd](https://github.com/brokenblack/manga-TCNtranslator/commit/c7084cd)

## 新增

- **單一 exe 散布**（PyInstaller `--onefile` 模式）
  優點：只有一個檔，方便分享、傳輸
  缺點：每次啟動會多 10-15 秒（解壓內建 bundle 到 `%TEMP%`）
  記憶體用量約 930 MB（vs 資料夾版約 390 MB）

## 該下載哪個版本？

| 場景 | 建議 |
|---|---|
| 想分享給朋友、不在乎啟動慢 | 本版 `翻譯工具.exe` |
| 想自行打包 | 看 [README 開發者區塊](https://github.com/brokenblack/manga-TCNtranslator#從原始碼執行開發者) |

## 安全性

VirusTotal 檢測尚未上傳（單檔模式 PyInstaller 誤報率較高，預期 5-15 個中小廠誤報，主流大廠應仍 clean）。

⚠️ Windows Defender 可能誤報 — 處理方式請見 `使用說明.txt` 之常見問題。

## 檔案完整性 (SHA256)

```
翻譯工具.exe : 064205b2bc3744cd79063e42f092dba38cbb3a01acf7b1814ff06e2a55f01d7d
```

下載後可用 `Get-FileHash 翻譯工具.exe` 驗證。

## 使用步驟（首次）

1. 下載 `翻譯工具.exe` 與 `使用說明.txt`，放在同一資料夾（建議桌面或 `C:\Tools`）
2. 雙擊 `翻譯工具.exe` —— **首次啟動需 10-15 秒**，請耐心等候
3. 視窗開啟後，右上角 **⚙️ 翻譯設定** → **翻譯 API** → 填入 [Groq API Key](https://console.groq.com)（免費）→ 儲存
4. 按 **Ctrl + Alt + Q** 框選遊戲文字 → 自動翻譯！

詳細功能請見 `使用說明.txt`。

---

**v1.0 → v1.0.1 完整 commit log**：[compare view](https://github.com/brokenblack/manga-TCNtranslator/compare/v1.0...main)
