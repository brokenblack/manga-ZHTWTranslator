# 日韓文即時翻譯工具

Windows 桌面工具，**OCR 截圖 + AI 翻譯 + Anki 單字卡匯出**。專為玩日文／韓文遊戲與視覺小說（VN）的玩家設計。

[![Latest Release](https://img.shields.io/github/v/release/brokenblack/manga-TCNtranslator?label=最新版本)](https://github.com/brokenblack/manga-TCNtranslator/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 下載使用（推薦）

> 🎯 打包好的 Windows 程式，下載即可使用，無需安裝 Python。

➡️ **[到 Releases 頁面下載最新版](https://github.com/brokenblack/manga-TCNtranslator/releases/latest)**

| 檔案 | 大小 | 啟動 | 說明 |
|---|---|---|---|
| [`翻譯工具_v1.1.0.zip`](https://github.com/brokenblack/manga-TCNtranslator/releases/download/v1.1.0/翻譯工具_v1.1.0.zip) ⭐ | 約 400 MB | < 2 秒 | **最新版**，資料夾版啟動快，新增 `Ctrl+Alt+W` 喚回視窗熱鍵 |
| [`翻譯工具_v1.1.0.7z`](https://github.com/brokenblack/manga-TCNtranslator/releases/download/v1.1.0/翻譯工具_v1.1.0.7z) | 約 280 MB | < 2 秒 | 同上但較小，需 [7-Zip](https://www.7-zip.org/) |
| [`翻譯工具.exe`](https://github.com/brokenblack/manga-TCNtranslator/releases/download/v1.0.1/翻譯工具.exe) (v1.0.1) | 402 MB | 10-15 秒 | 舊版單檔，分享方便但無 `Ctrl+Alt+W` |

### 快速開始

1. 下載 `翻譯工具_v1.1.0.zip` 並解壓到固定資料夾（建議桌面或 `C:\Tools`）
2. 進入解壓後的 `翻譯工具/` 資料夾，雙擊 `翻譯工具.exe`
3. 點右上角 **⚙️ 翻譯設定** → **翻譯 API** 分頁
4. 申請並填入 [API Key] → 儲存
5. 按 **Ctrl + Alt + Q** 框選遊戲文字 → 自動翻譯！

詳細說明請見資料夾內的 **使用說明.txt**。

---

## 功能

### 翻譯
- **OCR 截圖** — Ctrl + Alt + Q 框選任何視窗（含全螢幕遊戲），自動辨識日／韓文
- **Textractor 整合** — 監聽剪貼簿，與 [Textractor](https://github.com/Artikash/Textractor) 搭配擷取 VN 文字
- **多 API 自動 fallback** — 支援 **Groq / Gemini / Claude / OpenRouter / Ollama**
  可設定優先順序（如 `[Gemini, Ollama]`），前者失敗自動切換到下一個

### 學習
- **句子卡** — 整句加入 Anki，含 AI 教師解說
- **挖空卡 (Cloze)** — 點選詞元做 `{{c1::單字::意思}}` 格式卡片
- **單字卡** — 查詢單字後以 AI 解說製卡
- **真人音訊** — 整合 Forvo API，自動加入發音
- **批量匯出** — 翻譯歷史側欄多選後一次匯出

### 體驗
- **快速喚回視窗** — `Ctrl + Alt + W` 從系統匣一鍵叫出主視窗（v1.1.0 新增）
- **可自訂熱鍵** — 截圖 / Textractor 監聽快捷鍵都可改
- **自訂 AI Prompt** — 改翻譯風格、語氣、格式
- **開機自動啟動** —（選用）登入後自動跑到系統匣
- **完全離線可用** — 配 Ollama 跑本地模型，無需網路

---

## 全域快捷鍵

| 快捷鍵 | 功能 | 可自訂 |
|--------|------|:------:|
| `Ctrl + Alt + Q` | 截圖選取翻譯（全螢幕遊戲也能用） | ✅ |
| `Ctrl + Alt + T` | 切換 Textractor 剪貼簿監聽 | ✅ |
| `Ctrl + Alt + W` | 從系統匣叫出主視窗 | 固定 |
| `ESC` | 取消截圖選取 / 取消監聽 | — |

截圖與監聽熱鍵可在 **⚙️ 翻譯設定 → 一般** 自訂。

---

## 翻譯 API 比較

| API | 費用 | 速度 | 品質 | 適合場景 |
|-----|-----|-----|-----|---------|
| **Groq** | 免費額度大 | ⚡ 最快 | 良好 | **入門推薦** |
| Gemini | 免費額度大 | 快 | 佳 | 日常使用 |
| Claude | 付費 | 中 | ⭐ 最佳 | 解說品質優先 |
| OpenRouter | 部分免費 | 視模型而定 | 視模型而定 | 想試多種模型 |
| Ollama | 免費（本地） | 視硬體而定 | 視模型而定 | 完全離線 |

**推薦組合**：`[Gemini, Ollama]` — 平常用 Gemini，沒網路自動切 Ollama。

---

## OCR 引擎

| 引擎 | 語言 | 特性 |
|------|------|------|
| **manga-ocr** | 日文 | 漫畫對話框優化，乾淨背景效果最佳 |
| **EasyOCR** | 日文、韓文 | 複雜背景下表現較穩定，支援多語言 |

兩個引擎都已內建在程式包中，可在主視窗下拉選單即時切換。
模型約 400 MB / 引擎，**首次使用時自動下載**到使用者目錄。

---

## 系統需求

- Windows 10 / 11（64 位元）
- 記憶體：建議 4 GB 以上
- 硬碟：解壓後約 1.5 GB（含 OCR 模型約 2.5 GB）
- 網路：使用線上 AI 翻譯時需要
- 選用：[Anki](https://apps.ankiweb.net/) + [AnkiConnect](https://ankiweb.net/shared/info/2055492159) 外掛（匯出功能）

---

## 安全性

每次發布都會通過 VirusTotal 掃描，主流大廠（Microsoft / BitDefender / Kaspersky / Avira / CrowdStrike 等）皆 clean。各版本的掃描報告連結附在對應的 Release 頁面。

⚠️ 由於是個人開發工具未經商業簽章，Windows Defender 可能有誤報。處理方式請見壓縮包內的 **使用說明.txt** 之常見問題。

---

## 從原始碼執行（開發者）

如果你想自行修改或從原始碼跑：

```bash
# 1. Clone repo
git clone https://github.com/brokenblack/manga-TCNtranslator.git
cd manga-TCNtranslator

# 2. 建立虛擬環境
uv venv

# 3. 安裝相依
uv pip install pillow numpy pykakasi keyboard pystray opencc-python-reimplemented \
              anthropic google-generativeai groq \
              manga-ocr easyocr transformers
uv pip install torch --index-url https://download.pytorch.org/whl/cpu

# 4. 執行
.venv/Scripts/python.exe translator/translator.py
```

### 自行打包 exe

```bash
# 資料夾版（啟動快，產出 dist/翻譯工具/，約 1.3 GB）
.venv/Scripts/python.exe translator/build_exe.py

# 單檔版（單一 exe，分享方便，啟動較慢）
.venv/Scripts/python.exe translator/build_exe_onefile.py
```

打包時間約 25–60 分鐘。詳細設定見 [`translator/build_exe.py`](translator/build_exe.py)。

---

## 專案結構

```
manga_translator/
├── translator/
│   ├── translator.py            # 主程式（UI + OCR + 翻譯流程，~1900 行）
│   ├── anki_helper.py           # AnkiConnect 整合、句子卡、挖空卡
│   ├── anki_settings.py         # Anki 設定視窗
│   ├── history_manager.py       # 翻譯歷史管理
│   ├── build_exe.py             # PyInstaller 打包腳本（資料夾版）
│   ├── build_exe_onefile.py     # PyInstaller 打包腳本（單檔版）
│   └── 使用說明.txt              # 給終端使用者的說明（會打包進程式）
├── modelfile for local LLM/
│   └── Modelfile                # Ollama 本地模型設定
├── README.md
└── pyproject.toml
```

---

## 問題回報 / 功能建議

[GitHub Issues](https://github.com/brokenblack/manga-TCNtranslator/issues)

歡迎 PR。

---

## 授權

MIT License — 個人使用、修改、散布皆可，無任何擔保。
