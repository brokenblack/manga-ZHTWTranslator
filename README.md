# 日韓文漫畫/遊戲即時翻譯工具

Windows 桌面工具，**OCR 截圖 + AI 翻譯 + Anki 單字卡匯出**。專為玩日文／韓文遊戲與視覺小說（VN）的玩家設計。

[![Latest Release](https://github.com/brokenblack/manga-TCNtranslator/releases/tag/v1.0)](https://github.com/brokenblack/manga-TCNtranslator/releases/tag/v1.0)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 下載使用（推薦）

> 🎯 打包好的 Windows exe，下載解壓即可使用。

➡️ **[到 Releases 頁面下載最新版](https://github.com/brokenblack/manga-TCNtranslator/releases/latest)**

| 檔案 | 大小 | 說明 |
|---|---|---|
| `翻譯工具_v1.0.zip` | 398 MB | Windows 內建解壓即可使用 |
| `翻譯工具_v1.0.7z` | 279 MB | 較小，需安裝 [7-Zip](https://www.7-zip.org/) |

### 快速開始

1. 下載 ZIP 並解壓到任意資料夾（建議桌面或 `C:\Tools`）
2. 進入解壓後的 `翻譯工具/` 資料夾，雙擊 **`翻譯工具.exe`**
3. 點右上角 **⚙️ 翻譯設定** → **翻譯 API** 分頁
4. 申請並填入 [API Key] → 儲存
5. 按 **Ctrl + Alt + Q** 框選遊戲文字 → 自動翻譯！

詳細說明請見壓縮包內的 **使用說明.txt**。

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
- **可自訂熱鍵** — 截圖 / Textractor 監聽快捷鍵都可改
- **自訂 AI Prompt** — 改翻譯風格、語氣、格式
- **開機自動啟動** —（選用）登入後自動跑到系統匣
- **完全離線可用** — 配 Ollama 跑本地模型，無需網路

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

兩個引擎都已內建在 exe 包中，可在主視窗下拉選單即時切換。
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

每次發布都會通過 VirusTotal 掃描，主流大廠（Microsoft / BitDefender / Kaspersky / Avira / CrowdStrike 等）皆 clean。

最新版檢測：[VirusTotal Report](https://www.virustotal.com/gui/file/a102d76e8c8f02fb15756a8f36d8b8cc6c0cdffb9ecb650fdf43a80bf3ca1ae3)

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
.venv/Scripts/python.exe translator/build_exe.py
```

完成後檔案位於 `translator/dist/翻譯工具/`。打包時間 20-40 分鐘，產出約 1.3 GB。

詳細打包設定見 [`translator/build_exe.py`](translator/build_exe.py)。

---

## 專案結構

```
manga_translator/
├── translator/
│   ├── translator.py       # 主程式（UI + OCR + 翻譯流程，~1900 行）
│   ├── anki_helper.py      # AnkiConnect 整合、句子卡、挖空卡
│   ├── anki_settings.py    # Anki 設定視窗
│   ├── history_manager.py  # 翻譯歷史管理
│   ├── build_exe.py        # PyInstaller 打包腳本
│   └── 使用說明.txt         # 給終端使用者的說明（會打包進 exe）
├── modelfile for local LLM/
│   └── Modelfile           # Ollama 本地模型設定
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
