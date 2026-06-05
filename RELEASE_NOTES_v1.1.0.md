# 日韓文即時翻譯工具 v1.1.0

新增 **一鍵喚回視窗** 全域熱鍵。把程式縮到系統匣（背景）後，隨時用 `Ctrl + Alt + W` 把主視窗叫回來，不必再去工作列或系統匣點圖示。

## 新功能

- **`Ctrl + Alt + W` 喚回主視窗** — 在任何畫面（含全螢幕遊戲）按下即可把縮到背景的視窗叫出來並置頂。此為固定快捷鍵。

## 下載

| 檔案 | 大小 | 啟動 | 說明 |
|---|---|---|---|
| [`翻譯工具_v1.1.0.zip`](https://github.com/brokenblack/manga-TCNtranslator/releases/download/v1.1.0/翻譯工具_v1.1.0.zip) ⭐ | 約 400 MB | < 2 秒 | Windows 內建解壓即可使用 |
| [`翻譯工具_v1.1.0.7z`](https://github.com/brokenblack/manga-TCNtranslator/releases/download/v1.1.0/翻譯工具_v1.1.0.7z) | 約 280 MB | < 2 秒 | 需安裝 [7-Zip](https://www.7-zip.org/) |

> 兩個檔案內容完全相同，依你習慣的解壓工具擇一下載。

## 快速開始

1. 下載 ZIP 並解壓到固定資料夾（建議桌面或 `C:\Tools`）
2. 進入解壓後的 `翻譯工具/` 資料夾
3. 雙擊 `翻譯工具.exe`
4. 點右上角「⚙️ 翻譯設定」→「翻譯 API」分頁
5. 填入 API Key → 儲存

詳細使用方式請見資料夾內的 `使用說明.txt`。

## 全域快捷鍵

| 快捷鍵 | 功能 |
|--------|------|
| `Ctrl + Alt + Q` | 截圖選取翻譯（全螢幕遊戲也能用） |
| `Ctrl + Alt + T` | 切換 Textractor 剪貼簿監聽 |
| `Ctrl + Alt + W` | 從系統匣叫出主視窗 ⭐ 本版新增 |
| `ESC` | 取消截圖選取 / 取消監聽 |

## 功能總覽

- **OCR 截圖翻譯** — Ctrl + Alt + Q 框選遊戲畫面，自動辨識日／韓文並翻譯
- **Textractor 整合** — 監聽剪貼簿，與 VN 工具搭配
- **多 API + 自動 fallback** — 支援 Groq / Gemini / Claude / OpenRouter / Ollama，按優先級自動切換（網路斷線可 fallback 到本地 Ollama）
- **Anki 匯出** — 句子卡 + 挖空卡（Cloze），可選 Forvo 真人音訊
- **翻譯歷史** — 側欄記錄全部翻譯，支援批量加入 Anki
- **可自訂熱鍵** — 截圖快捷鍵 / Textractor 監聽快捷鍵都可改

## 安全性

⚠️ **Windows Defender 可能誤報**：這是 PyInstaller 未簽章 exe 的常態，非惡意程式。處理方式：

1. 開啟「Windows 安全性」
2. 「病毒與威脅防護」→「保護歷程記錄」
3. 找到本程式 →「動作」→「允許」

或將整個資料夾加入「排除項目」。

## 完整變更

- 新增 `Ctrl + Alt + W` 全域熱鍵，從系統匣喚回主視窗（複用既有 `_tray_show` 顯示邏輯，熱鍵 callback 透過 `after(0, ...)` marshal 回 Tk 主執行緒）
- 更新 README、使用說明.txt，補上新熱鍵說明
- 新增 `build_exe_onefile.py` 單檔打包腳本

**完整 diff**：https://github.com/brokenblack/manga-TCNtranslator/compare/v1.0.1...v1.1.0
