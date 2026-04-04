# 截圖即時翻譯工具

PC 漫畫日文／韓文即時翻譯工具，支援 OCR 截圖辨識、多種 AI 翻譯引擎，並可直接匯出 Anki 單字卡。

---

## 功能

- **OCR 截圖翻譯** — 拖曳選取遊戲畫面區域，自動辨識並翻譯日文／韓文
- **Textractor 整合** — 監聽剪貼簿，與 Textractor 搭配擷取遊戲文字
- **多引擎翻譯** — 支援 Groq、Gemini、Claude、Ollama（本地）
- **Anki 匯出** — 一鍵製作句子卡、挖空卡（Cloze），支援 Forvo API 真人發音
- **翻譯歷史** — 側欄記錄所有翻譯，可批量加入 Anki
- **單字查詢** — 點選詞元查詢讀音、詞性、例句解說，並以解說製卡

---

## 系統需求

- Windows 10 / 11
- Python 3.9+
- [Anki](https://apps.ankiweb.net/) + [AnkiConnect](https://ankiweb.net/shared/info/2055492159) 外掛（匯出功能）

---

## 安裝

### 1. 安裝 Python 相依套件

```bash
uv pip install pillow numpy pykakasi
```

### 2. 安裝 OCR 套件（可擇一）

**manga-ocr**（日文漫畫優化，首次執行自動下載模型 ~400MB）：
```bash
uv pip install manga-ocr
```

**EasyOCR**（支援日文 + 韓文，首次下載 ~300MB/語言）：
```bash
uv pip install easyocr
```

### 3. 安裝翻譯 API 相依

```bash
uv pip install anthropic google-generativeai groq
```

---

## 使用方式

```bash
python translator/translator.py
```

### OCR 截圖翻譯

1. 點擊 **✂️ 選取區域並翻譯 (F9)** 或按 `F9`
2. 在遊戲畫面上拖曳選取文字區域
3. 放開滑鼠後自動截圖、辨識、翻譯

### Textractor 整合

1. 在 Textractor 啟用 **Copy to Clipboard** 外掛
2. 切換至 **🔗 Textractor** 分頁，點擊 **▶ 開始監聽**
3. 遊戲文字自動擷取翻譯

### 匯出至 Anki

確認 Anki 開啟且 AnkiConnect 外掛已安裝後：

| 功能 | 說明 |
|------|------|
| 句子卡 | 以 AI 提取的例句為正面，老師解說為背面 |
| 挖空卡 (Cloze) | 點選詞元，以 `{{c1::單字::意思}}` 格式製卡 |
| 單字卡 | 查詢單字後，以 AI 解說製成單字卡 |
| 批量加入 | 在翻譯歷史側欄多選後批量匯出 |

---

## 設定

點擊主視窗右上角 **⚙️ 翻譯設定** 或 **🃏 Anki 設定**。

### 翻譯 API

| API | 說明 |
|-----|------|
| Groq | 免費額度大，速度快，推薦入門 |
| Gemini | Google AI，免費額度充足 |
| Claude | Anthropic，解說品質佳 |
| Ollama | 完全本地執行，需預先下載模型 |

### OCR 引擎（主視窗快速切換）

| 引擎 | 語言 | 說明 |
|------|------|------|
| manga-ocr | 日文 | 漫畫優化，對話框文字效果佳 |
| EasyOCR | 日文、韓文 | 支援複雜背景，遊戲 UI 較穩定 |

---

## 專案結構

```
manga_translator/
├── translator/
│   ├── translator.py       # 主程式（UI + OCR + 翻譯流程）
│   ├── anki_helper.py      # AnkiConnect 整合、句子卡、挖空卡
│   ├── anki_settings.py    # Anki 設定視窗
│   ├── history_manager.py  # 翻譯歷史管理
│   └── install_ocr.bat     # OCR 套件一鍵安裝
└── pyproject.toml
```

---

## 打包為 EXE

```bash
python translator/build_exe.py
```

輸出在 `dist/遊戲翻譯工具.exe`。

---

## 授權

MIT License
