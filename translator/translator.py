"""
遊戲即時翻譯工具 (PC 版)
- OCR 截圖 / Textractor 剪貼簿
- 翻譯：Claude / Gemini / Groq / Ollama
- Anki：句子卡 / 挖空卡（Cloze）+ Forvo 真人音訊
- 翻譯歷史側欄
"""

import sys
import os
from pathlib import Path

# ── GUI subsystem stdout/stderr 防護 ─────────────────────────
# PyInstaller --windowed 模式下 sys.stdout/stderr 會是 None，
# 任何 print() 都會拋 AttributeError 讓 GUI 執行緒炸掉。
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# ── GPU 自動偵測 ──────────────────────────────────────────────
# NVIDIA 用戶能用 CUDA；AMD 用戶沒 CUDA 支援，改用 CPU
try:
    import torch
    if not torch.cuda.is_available():
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
except ImportError:
    pass

# ── PyInstaller 打包路徑修正 ─────────────────────────────────
# 打包後 __file__ 在臨時解壓目錄；config / history 要存在 exe 同層
if getattr(sys, "frozen", False):
    # 執行中的 exe 所在目錄（使用者可見的目錄）
    APP_DIR = Path(sys.executable).parent
    # PyInstaller 解壓的臨時目錄（含打包進去的 .py）
    _bundle = Path(sys._MEIPASS)
    sys.path.insert(0, str(_bundle))
else:
    APP_DIR = Path(__file__).parent

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import time
import re
import urllib.request
from PIL import ImageGrab, Image, ImageDraw, ImageFont
import numpy as np
import pystray
import keyboard as kb

from anki_helper   import (
    extract_reading, get_forvo_tag,
    add_sentence_note, add_cloze_note, build_cloze_text,
)
from anki_settings  import AnkiSettingsWindow
from history_manager import add_entry, get_entries, search_entries, clear_history

# ── 設定 ────────────────────────────────────────────────────
CONFIG_PATH  = APP_DIR / "config.json"

DEFAULT_CONFIG = {
    "api_provider": "groq",
    "api_priority": ["groq"],
    "claude_api_key": "", "gemini_api_key": "",
    "groq_api_key": "", "groq_model": "llama-3.3-70b-versatile",
    "openrouter_api_key": "",
    "openrouter_model": "meta-llama/llama-3.3-70b-instruct:free",
    "ollama_url": "http://localhost:11434", "ollama_model": "gemma3:12b",
    "ocr_engine": "manga-ocr", "ocr_language": "ja", "text_direction": "ltr",
    "capture_region": None, "auto_mode": False, "auto_interval": 3.0,
    "textractor_filter_english": True, "textractor_min_length": 1,
    "anki_url": "http://localhost:8765",
    "anki_deck": "遊戲翻譯", "anki_model": "Basic",
    "anki_tags": "遊戲翻譯",
    "anki_fields": {
        "original": "Front", "reading": "Reading",
        "translation": "Back", "audio": "Audio",
    },
    "anki_cloze_deck": "遊戲翻譯（挖空）", "anki_cloze_model": "Cloze",
    "anki_cloze_fields": {
        "text": "Text", "extra": "Extra", "reading": "Reading",
        "audio": "Audio", "sentence": "",
    },
    "forvo_api_key": "", "audio_enabled": True,
    "font_size": 14,
    "global_hotkey": "ctrl+alt+q",
    "clip_hotkey": "ctrl+alt+t",
    "background_mode": True,
    "close_ask": True,
    "anki_open_editor": True,
    "autostart": False,
    "translation_prompt": "",
}

def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    # 敏感金鑰優先從環境變數讀取（檔案值作 fallback）
    for cfg_key, env_key in (
        ("claude_api_key", "CLAUDE_API_KEY"),
        ("gemini_api_key", "GEMINI_API_KEY"),
        ("groq_api_key",   "GROQ_API_KEY"),
        ("forvo_api_key",  "FORVO_API_KEY"),
    ):
        if os.environ.get(env_key):
            cfg[cfg_key] = os.environ[env_key]
    return cfg

def save_config(cfg):
    # 若金鑰由環境變數提供，則不回寫到磁碟（避免洩漏）
    to_save = cfg.copy()
    for cfg_key, env_key in (
        ("claude_api_key", "CLAUDE_API_KEY"),
        ("gemini_api_key", "GEMINI_API_KEY"),
        ("groq_api_key",   "GROQ_API_KEY"),
        ("forvo_api_key",  "FORVO_API_KEY"),
    ):
        if os.environ.get(env_key):
            to_save[cfg_key] = ""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(to_save, f, ensure_ascii=False, indent=2)


# ── 語言偵測 ────────────────────────────────────────────────
JP_PAT = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]')
KO_PAT = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF]')
def has_cjk(t): return bool(JP_PAT.search(t)) or bool(KO_PAT.search(t))


# ── OCR ─────────────────────────────────────────────────────
_manga_ocr = None; _easy_ocr = {}

def get_manga_ocr():
    global _manga_ocr
    if _manga_ocr is None:
        try:
            from manga_ocr import MangaOcr
            _manga_ocr = MangaOcr()
        except Exception as e:
            print(f"❌ manga_ocr 初始化失敗：{type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    return _manga_ocr

def get_easy_ocr(langs):
    if langs not in _easy_ocr:
        import easyocr; _easy_ocr[langs] = easyocr.Reader(list(langs), gpu=False)
    return _easy_ocr[langs]

def _lang_tuple(cfg):
    return {"ja":("ja",),"ko":("ko",),"ja+ko":("ja","ko")}.get(
        cfg.get("ocr_language","ja"), ("ja",))

def _preprocess_ocr_img(img):
    """確保 RGB 模式，並放大過小的圖（OCR 需要最低解析度）。"""
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w < 300 or h < 80:
        scale = max(300 / w, 80 / h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    return img

def run_ocr(img, cfg):
    img = _preprocess_ocr_img(img)
    engine = cfg.get("ocr_engine","manga-ocr"); dirn = cfg.get("text_direction","ltr")
    if engine == "manga-ocr":
        from PIL import ImageOps
        ocr = get_manga_ocr()
        t = ocr(img).strip()
        if not t:
            # manga-ocr 訓練在白底黑字；深色背景白字時自動反轉再試一次
            t = ocr(ImageOps.invert(img)).strip()
        if dirn == "rtl" and t:
            t = "\n".join(" ".join(l.split()[::-1]) for l in t.splitlines())
        return t
    from PIL import ImageOps
    reader = get_easy_ocr(_lang_tuple(cfg))
    results = reader.readtext(np.array(img), detail=1, paragraph=False)
    if not results:
        results = reader.readtext(np.array(ImageOps.invert(img)), detail=1, paragraph=False)
    if not results: return ""
    items = [(sum(p[1] for p in b)/4, sum(p[0] for p in b)/4, t) for b,t,_ in results]
    items.sort(key=lambda x: x[0])
    lines, cur = [], [items[0]]
    for item in items[1:]:
        if abs(item[0]-cur[-1][0]) < 20: cur.append(item)
        else: lines.append(cur); cur = [item]
    lines.append(cur)
    merged = []
    for line in lines:
        line.sort(key=lambda x: (-x[1] if dirn=="rtl" else x[1]))
        merged.append("".join(i[2] for i in line))
    return "\n".join(merged)


# ── 簡轉繁（OpenCC）─────────────────────────────────────────
try:
    from opencc import OpenCC
    _s2t = OpenCC('s2t')
except ImportError:
    _s2t = None


# ── 翻譯 ─────────────────────────────────────────────────────
# 預設翻譯 prompt 模板。{src} 會被替換為「日文」/「韓文」/「日文或韓文」。
DEFAULT_TRANSLATION_PROMPT_TEMPLATE = """你是一位親切、專業的{src}老師，正在幫助學生理解遊戲中的{src}文字。

收到{src}輸入後，請用繁體中文依以下格式回應：

【譯文】
（流暢自然的繁體中文翻譯，保留遊戲語感）

【例句】
（從輸入文字中取出或改寫出一個最具代表性、最適合記憶的{src}例句，加上繁體中文對譯）
{src}：（例句原文）
中文：（對應翻譯）

【重點單字】
（列出 1–3 個值得學習的單字或詞組）
・單字（讀音）— 詞性｜核心意思
  → 補充：用法說明、常見搭配、或與近義詞的差異

【用詞備注】（若有值得補充的語感、慣用表現或文體特色才列出，否則省略）
（例如：這裡用〜てしまう 表示遺憾語氣；或：〜のだ 是強調原因的說明語氣）

規則：
- 所有中文必須使用繁體中文，嚴禁簡體字（例：✓資訊 ✗信息 ✓遊戲 ✗游戏 ✓軟體 ✗软件）
- 【例句】請直接使用輸入文字，除非輸入過長（超過 30 字）才截短或改寫
- 若輸入是短詞或單字（5 字以內），【例句】必須造一個包含該詞的完整自然例句（至少 8 字），不可只重覆單字本身
- 重點單字以學習者角度挑選，避免列明顯簡單的詞（如 私、です）
- 若整句皆為平假名或非常簡單，重點單字可省略
- 人名、地名若無通用譯法請保留原文
- 格式要精簡，不要過度展開"""

def _prompt(cfg):
    src = {"ja":"日文","ko":"韓文","ja+ko":"日文或韓文"}.get(cfg.get("ocr_language","ja"),"日文")
    template = cfg.get("translation_prompt", "").strip() or DEFAULT_TRANSLATION_PROMPT_TEMPLATE
    return template.replace("{src}", src)

def _word_prompt(cfg):
    src = {"ja":"日文","ko":"韓文","ja+ko":"日文"}.get(cfg.get("ocr_language","ja"),"日文")
    return f"""你是{src}老師。收到單字後，請用繁體中文簡潔說明（嚴禁使用簡體字）：

【讀音】（平假名）
【詞性】（名詞／動詞／形容詞等）
【意思】（核心意思，1–2 行）
【例句】
{src}：（包含該單字的完整自然例句，至少 8 字）
中文：（翻譯）
【補充】（選填：語感、常見搭配、近義詞差異）

格式精簡，不要過度展開。"""

def _extract_brief_meaning(explain: str, fallback: str = "") -> str:
    """從 AI 單字解說中抽出【意思】行，作為挖空卡的提示（hint）。"""
    for line in explain.splitlines():
        line = line.strip()
        if line.startswith("【意思】"):
            meaning = line[4:].strip()   # remove 【意思】
            if meaning:
                return meaning[:40]
    # fallback：第一個非標題行
    for line in explain.splitlines():
        line = line.strip()
        if line and not line.startswith("【") and not line.startswith("（"):
            return line[:40]
    return fallback


def _ensure_traditional(text: str) -> str:
    """簡轉繁後處理（OpenCC s2t）。已是繁體的文字不受影響。"""
    if _s2t:
        return _s2t.convert(text)
    return text


def _translate_one(p, text, pr, cfg, max_tok=800):
    """單一 provider 呼叫；失敗會 raise。"""
    if p == "claude":
        import anthropic
        return anthropic.Anthropic(api_key=cfg["claude_api_key"]).messages.create(
            model="claude-opus-4-5", max_tokens=max_tok, system=pr,
            messages=[{"role":"user","content":text}]).content[0].text.strip()
    elif p == "gemini":
        import google.generativeai as genai; genai.configure(api_key=cfg["gemini_api_key"])
        return genai.GenerativeModel("gemini-2.0-flash",system_instruction=pr).generate_content(text).text.strip()
    elif p == "groq":
        from groq import Groq
        return Groq(api_key=cfg["groq_api_key"]).chat.completions.create(
            model=cfg["groq_model"],
            messages=[{"role":"system","content":pr},{"role":"user","content":text}],
            max_tokens=max_tok).choices[0].message.content.strip()
    elif p == "ollama":
        url = cfg.get("ollama_url","http://localhost:11434").rstrip("/")
        payload = json.dumps({"model":cfg.get("ollama_model","gemma3:12b"),
            "messages":[{"role":"system","content":pr},{"role":"user","content":text}],
            "stream":False}).encode()
        req = urllib.request.Request(f"{url}/api/chat", data=payload,
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["message"]["content"].strip()
    elif p == "openrouter":
        # OpenAI-compatible endpoint；用 stdlib urllib 不需新依賴
        payload = json.dumps({
            "model": cfg.get("openrouter_model","meta-llama/llama-3.3-70b-instruct:free"),
            "messages":[{"role":"system","content":pr},{"role":"user","content":text}],
            "max_tokens": max_tok,
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type":"application/json",
                "Authorization": f"Bearer {cfg.get('openrouter_api_key','')}",
                "HTTP-Referer": "https://github.com/local/game-translator",
                "X-Title": "Game Translator",
            })
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    raise ValueError(f"未知 API：{p}")


def translate(text, cfg, system_prompt=None):
    """依優先順序嘗試各 provider，回傳 (result, used_provider)。全失敗則 raise。"""
    pr = system_prompt if system_prompt is not None else _prompt(cfg)
    priority = cfg.get("api_priority") or [cfg.get("api_provider", "groq")]
    last_err = None
    for p in priority:
        try:
            result = _translate_one(p, text, pr, cfg)
            return _ensure_traditional(result), p
        except Exception as e:
            last_err = f"{p}: {e}"
            continue
    raise RuntimeError(f"所有翻譯模型皆失敗｜{last_err}")

def extract_clean_translation(teacher_response: str) -> str:
    """從老師回應抽出【譯文】區塊。格式不符時回傳整個原始回應。"""
    m = re.search(r'【譯文】\s*\n(.*?)(?:\n【|$)', teacher_response, re.DOTALL)
    if m:
        return m.group(1).strip()
    return teacher_response.strip()

def extract_example_sentence(teacher_response: str) -> tuple:
    """
    從老師回應抽出【例句】區塊，回傳 (ja_sentence, zh_translation)。
    格式：
        日文：xxx
        中文：xxx
    若找不到，回傳 ("", "")。
    """
    block = re.search(r'【例句】\s*\n(.*?)(?:\n【|$)', teacher_response, re.DOTALL)
    if not block:
        return "", ""
    text = block.group(1).strip()
    # 嘗試配對「日文：」「中文：」（也接受語言名稱變體）
    ja_m  = re.search(r'(?:日文|原文|韓文|[Jj][Aa]|[Kk][Oo])：\s*(.+)', text)
    zh_m  = re.search(r'(?:中文|繁中|翻譯|[Zz][Hh])：\s*(.+)', text)
    ja  = ja_m.group(1).strip()  if ja_m  else ""
    zh  = zh_m.group(1).strip()  if zh_m  else ""
    # Fallback：如果 regex 不匹配，取 block 中第一行含日/韓文字元的文字
    if not ja:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith(("中文", "翻譯", "（")):
                if JP_PAT.search(line) or KO_PAT.search(line):
                    ja = line
                    break
    return ja, zh


# ── 區域選擇器 ───────────────────────────────────────────────
class RegionSelector(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback; self.sx = self.sy = 0; self.rect = None
        self.attributes("-fullscreen",True); self.attributes("-alpha",0.35)
        self.attributes("-topmost", True)
        self.configure(bg="black", cursor="crosshair"); self.overrideredirect(True)
        # 搶到最上層 + 鍵盤焦點（遊戲常自稱 topmost，需主動 lift）
        self.after(10, self._force_top)
        c = tk.Canvas(self, bg="black", highlightthickness=0); c.pack(fill="both", expand=True)
        c.bind("<ButtonPress-1>",  self._p)
        c.bind("<B1-Motion>",       self._d)
        c.bind("<ButtonRelease-1>", self._r)
        self.bind("<Escape>", lambda e: self.destroy()); self.c = c
        tk.Label(c, text="拖曳選取翻譯區域  |  ESC 取消",
                 fg="white", bg="black", font=("Microsoft JhengHei",16)
                 ).place(relx=0.5, rely=0.05, anchor="center")
    def _force_top(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception: pass
    def _p(self, e):
        # x_root/y_root = absolute screen coords; cx/cy = canvas-relative for drawing
        self.sx, self.sy = e.x_root, e.y_root
        self.cx, self.cy = e.x, e.y
        self.rect and self.c.delete(self.rect)
    def _d(self, e):
        self.rect and self.c.delete(self.rect)
        self.rect = self.c.create_rectangle(self.cx, self.cy, e.x, e.y,
            outline="#FF4444",width=2,fill="gray",stipple="gray25")
    def _r(self, e):
        x1,y1=min(self.sx,e.x_root),min(self.sy,e.y_root)
        x2,y2=max(self.sx,e.x_root),max(self.sy,e.y_root)
        self.destroy()
        if x2-x1>10 and y2-y1>10: self.callback([x1,y1,x2,y2])


# ── 句子分詞工具 ─────────────────────────────────────────────
def tokenize_sentence(sentence: str) -> list:
    """
    用 pykakasi 將句子切分為 (surface, reading) 配對清單。
    surface = 原文詞素；reading = 平假名（無法轉換則等於 surface）。
    """
    try:
        import pykakasi
        kks    = pykakasi.kakasi()
        result = kks.convert(sentence)
        tokens = []
        for item in result:
            surf = item["orig"]
            hira = item["hira"] or surf
            if surf.strip():
                tokens.append((surf, hira))
        return tokens
    except ImportError:
        # fallback：整句當一個 token
        return [(sentence, "")]


# ── 挖空卡對話框 ─────────────────────────────────────────────
class ClozeDialog(tk.Toplevel):
    """
    點擊詞元自動選取挖空單字 + 讀音，不需手動輸入。
    詞元由 pykakasi 切分（本地，不需 AI）。
    """
    def __init__(self, parent, sentence: str, orig: str, translation: str, cfg: dict, on_done):
        super().__init__(parent)
        self.sentence    = sentence
        self.orig        = orig
        self.translation = translation
        self.cfg         = cfg
        self.on_done     = on_done
        self._tokens: list = []          # [(surface, reading), ...]
        self._sel_btns: list = []        # 詞元按鈕清單
        self._selected_idx: int = -1

        self.title("挖空卡（Cloze）—— 點擊詞元選取")
        self.geometry("560x620")
        self.resizable(True, False)
        self.attributes("-topmost", True)
        self.grab_set()
        self._build()
        # 背景切詞
        threading.Thread(target=self._load_tokens, daemon=True).start()

    def _build(self):
        f = ttk.Frame(self, padding=12); f.pack(fill="both", expand=True)

        # 挖空句（AI 例句 or 原文）
        lbl_sent = "例句（AI 生成）：" if self.sentence != self.orig else "原文（無 AI 例句）："
        ttk.Label(f, text=lbl_sent, font=("",9,"bold")).pack(anchor="w")
        sb = tk.Text(f, height=2, wrap="word", font=("Yu Gothic UI",11),
                     relief="flat", bg="#fff8e1", state="normal")
        sb.insert("1.0", self.sentence); sb.configure(state="disabled")
        sb.pack(fill="x", pady=(2,4))

        # 翻譯（背景色提示）
        ttk.Label(f, text="翻譯（背面提示）：", font=("",9,"bold")).pack(anchor="w")
        tb = tk.Text(f, height=2, wrap="word", font=("Microsoft JhengHei",11),
                     relief="flat", bg="#f0f8ff", state="normal")
        tb.insert("1.0", extract_clean_translation(self.translation)); tb.configure(state="disabled")
        tb.pack(fill="x", pady=(2, 8))

        ttk.Separator(f).pack(fill="x", pady=4)

        # 詞元點擊區
        ttk.Label(f, text="👆 點擊要挖空的詞：", font=("",9,"bold")).pack(anchor="w")
        ttk.Label(f, text="（pykakasi 自動切詞，讀音同步填入）",
                  foreground="gray").pack(anchor="w")

        # 捲動容器
        token_outer = ttk.Frame(f); token_outer.pack(fill="x", pady=4)
        canvas = tk.Canvas(token_outer, height=72, bg="#fafafa",
                           highlightthickness=1, highlightbackground="#ddd")
        hbar   = ttk.Scrollbar(token_outer, orient="horizontal",
                               command=canvas.xview)
        canvas.configure(xscrollcommand=hbar.set)
        hbar.pack(side="bottom", fill="x")
        canvas.pack(fill="x")
        self.token_frame = ttk.Frame(canvas)
        self.token_frame_id = canvas.create_window(
            (0, 0), window=self.token_frame, anchor="nw")
        self.token_frame.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        self._canvas = canvas

        self.loading_lbl = ttk.Label(self.token_frame,
            text="⏳ 切詞中...", foreground="gray")
        self.loading_lbl.pack(side="left", padx=6)

        ttk.Separator(f).pack(fill="x", pady=6)

        # 已選取的詞
        sel_row = ttk.Frame(f); sel_row.pack(fill="x")
        ttk.Label(sel_row, text="選取的單字：").pack(side="left")
        self.word_var = tk.StringVar(value="（未選取）")
        ttk.Label(sel_row, textvariable=self.word_var,
                  font=("Yu Gothic UI", 12, "bold"),
                  foreground="#1a6fb5").pack(side="left", padx=6)

        ttk.Label(sel_row, text="讀音：").pack(side="left", padx=(10, 0))
        self.reading_var = tk.StringVar(value="")
        self.reading_entry = ttk.Entry(sel_row, textvariable=self.reading_var,
                                       width=12, font=("Yu Gothic UI", 11))
        self.reading_entry.pack(side="left", padx=4)
        self.reading_entry.bind("<KeyRelease>", lambda e: self._update_preview())
        ttk.Label(sel_row, text="（可手動修改）",
                  foreground="gray").pack(side="left")

        ttk.Separator(f).pack(fill="x", pady=6)

        # Cloze 預覽
        ttk.Label(f, text="Cloze 預覽：", font=("",9,"bold")).pack(anchor="w")
        self.preview_var = tk.StringVar(value="（點擊詞元後預覽）")
        ttk.Label(f, textvariable=self.preview_var,
                  foreground="#1a6fb5", wraplength=520,
                  font=("Yu Gothic UI", 11)).pack(anchor="w", padx=4, pady=2)

        ttk.Separator(f).pack(fill="x", pady=4)

        # 單字查詢
        lkp_row = ttk.Frame(f); lkp_row.pack(fill="x")
        self.lookup_btn = ttk.Button(lkp_row, text="🔍 查詢此單字",
                                     command=self._lookup_word, state="disabled")
        self.lookup_btn.pack(side="left")
        ttk.Label(lkp_row, text="← 選取詞元後可查詢", foreground="gray").pack(side="left", padx=6)

        exp_frame = ttk.Frame(f); exp_frame.pack(fill="both", expand=True, pady=(4,0))
        self.explain_text = tk.Text(exp_frame, height=6, wrap="word",
                                    font=("Microsoft JhengHei",10),
                                    state="disabled", relief="flat", bg="#f9f9f9")
        exp_sb = ttk.Scrollbar(exp_frame, orient="vertical", command=self.explain_text.yview)
        self.explain_text.configure(yscrollcommand=exp_sb.set)
        exp_sb.pack(side="right", fill="y")
        self.explain_text.pack(side="left", fill="both", expand=True)

        self.make_cloze_btn = ttk.Button(f, text="📝 以解說製成挖空卡",
                                         command=self._make_cloze_from_explain, state="disabled")
        self.make_cloze_btn.pack(anchor="w", pady=(4,0))

        ttk.Separator(f).pack(fill="x", pady=6)

        # 送出
        btn_row = ttk.Frame(f); btn_row.pack()
        ttk.Button(btn_row, text="🃏 加入 Anki（挖空卡）",
                   command=self._submit).pack(side="left", padx=6)
        ttk.Button(btn_row, text="取消",
                   command=self.destroy).pack(side="left", padx=6)
        self.status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.status, foreground="green").pack(pady=2)

    def _load_tokens(self):
        tokens = tokenize_sentence(self.sentence)
        self._tokens = tokens
        self.after(0, self._render_tokens)

    def _render_tokens(self):
        # 清除 loading 標籤
        self.loading_lbl.destroy()

        for i, (surf, hira) in enumerate(self._tokens):
            cell = ttk.Frame(self.token_frame,
                             relief="ridge", padding=2)
            cell.pack(side="left", padx=2, pady=4)

            # 讀音（小字）
            r_lbl = tk.Label(cell, text=hira if hira != surf else "",
                             font=("Yu Gothic UI", 7), fg="#888", bg="#fafafa")
            r_lbl.pack()

            # 詞素（主字）
            btn = tk.Button(
                cell, text=surf,
                font=("Yu Gothic UI", 12),
                relief="flat", bg="#fafafa", activebackground="#d0e8ff",
                cursor="hand2", padx=4,
                command=lambda idx=i: self._select_token(idx),
            )
            btn.pack()
            self._sel_btns.append((btn, cell))

    def _select_token(self, idx: int):
        # 還原舊選取顏色
        if 0 <= self._selected_idx < len(self._sel_btns):
            old_btn, old_cell = self._sel_btns[self._selected_idx]
            old_btn.configure(bg="#fafafa")
            old_cell.configure(relief="ridge")

        # 設定新選取
        self._selected_idx = idx
        btn, cell = self._sel_btns[idx]
        btn.configure(bg="#b3d4ff")
        cell.configure(relief="solid")

        surf, hira = self._tokens[idx]
        self.word_var.set(surf)
        self.reading_var.set(hira if hira != surf else "")
        self._update_preview()
        self.lookup_btn.configure(state="normal")

    def _lookup_word(self):
        word = self.word_var.get().strip()
        if not word or word == "（未選取）": return
        self._set_explain("⏳ 查詢中...")
        self.lookup_btn.configure(state="disabled")
        def _w():
            try:
                result, _ = translate(word, self.cfg, system_prompt=_word_prompt(self.cfg))
                self.after(0, lambda: self._set_explain(result))
            except Exception as e:
                self.after(0, lambda: self._set_explain(f"❌ {e}"))
            self.after(0, lambda: self.lookup_btn.configure(state="normal"))
        threading.Thread(target=_w, daemon=True).start()

    def _set_explain(self, text: str):
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        self.explain_text.configure(state="normal")
        self.explain_text.delete("1.0", "end")
        self.explain_text.insert("1.0", text)
        self.explain_text.configure(state="disabled")
        if not text.startswith("⏳"):
            self.make_cloze_btn.configure(state="normal")

    def _make_cloze_from_explain(self):
        word = self.word_var.get().strip()
        if not word or word == "（未選取）": return
        explain = self.explain_text.get("1.0", "end").strip()
        if not explain: return
        reading = self.reading_var.get().strip() or extract_reading(word)
        word_hint = _extract_brief_meaning(explain, fallback=reading)
        self.status.set("⏳ 製作挖空卡...")
        explain_html = explain.replace("\n", "<br>")
        def _w():
            try:
                from anki_helper import get_forvo_tag, add_cloze_note
                audio_tag = ""
                key  = self.cfg.get("forvo_api_key","").strip()
                lang = self.cfg.get("ocr_language","ja")
                if key:
                    try:
                        search = reading if reading else word
                        audio_tag = get_forvo_tag(search, lang, key, self.cfg["anki_url"])
                    except Exception as e:
                        self.after(0, lambda: self.status.set(f"⚠️ Forvo：{e}，繼續加入"))
                ok, msg = add_cloze_note(
                    sentence=self.sentence,
                    translation=explain_html,
                    word=word,
                    word_reading=reading,
                    audio_tag=audio_tag,
                    cfg=self.cfg,
                    word_hint=word_hint)
                final = f"{'✅' if ok else '❌'} {msg}"
                self.after(0, lambda: self.status.set(final))
                if ok:
                    self.after(1500, self.destroy)
                    self.after(0, lambda: self.on_done(final))
            except Exception as e:
                self.after(0, lambda: self.status.set(f"❌ {e}"))
        threading.Thread(target=_w, daemon=True).start()

    def _update_preview(self):
        word    = self.word_var.get()
        reading = self.reading_var.get().strip()
        if not word or word == "（未選取）":
            self.preview_var.set("（點擊詞元後預覽）")
            return
        from anki_helper import build_cloze_text
        preview = build_cloze_text(self.sentence, word, reading)
        self.preview_var.set(preview)

    def _submit(self):
        word    = self.word_var.get().strip()
        reading = self.reading_var.get().strip()
        if not word or word == "（未選取）":
            self.status.set("⚠️ 請先點擊要挖空的詞")
            return
        explain_raw = self.explain_text.get("1.0", "end").strip()
        if explain_raw and not explain_raw.startswith(("⏳", "❌", "（")):
            word_hint = _extract_brief_meaning(explain_raw, fallback=reading)
        else:
            word_hint = reading
        self.status.set("⏳ 取得 Forvo 音訊...")

        def _w():
            try:
                from anki_helper import get_forvo_tag, add_cloze_note
                audio_tag = ""
                key  = self.cfg.get("forvo_api_key","").strip()
                lang = self.cfg.get("ocr_language","ja")
                if key:
                    try:
                        search    = reading if reading else word
                        audio_tag = get_forvo_tag(search, lang, key, self.cfg["anki_url"])
                        self.after(0, lambda: self.status.set("✅ 音訊取得"))
                    except Exception as e:
                        self.after(0, lambda: self.status.set(f"⚠️ Forvo：{e}，繼續加入"))
                else:
                    self.after(0, lambda: self.status.set("（未設定 Forvo Key，無音訊）"))

                # Cloze Extra 欄位只放純譯文，不放老師解說
                clean_trans = extract_clean_translation(self.translation)

                ok, msg = add_cloze_note(
                    sentence     = self.sentence,
                    translation  = clean_trans,
                    word         = word,
                    word_reading = reading,
                    audio_tag    = audio_tag,
                    cfg          = self.cfg,
                    word_hint    = word_hint,
                )
                final = f"{'✅' if ok else '❌'} {msg}"
                self.after(0, lambda: self.status.set(final))
                if ok:
                    self.after(1500, self.destroy)
                    self.after(0, lambda: self.on_done(final))
            except Exception as e:
                self.after(0, lambda: self.status.set(f"❌ {e}"))

        threading.Thread(target=_w, daemon=True).start()


# ── 句子卡選詞視窗 ────────────────────────────────────────────
class SentenceDialog(tk.Toplevel):
    """
    與 ClozeDialog 相似的 UI：點擊詞元選取要查發音的單字。
    選取的詞元只用於 Forvo 音訊；卡片內容為完整例句 + 老師解說。
    """
    def __init__(self, parent, orig: str, translation: str, cfg: dict, on_done):
        super().__init__(parent)
        self.orig        = orig
        self.translation = translation
        self.cfg         = cfg
        self.on_done     = on_done
        self._tokens: list   = []
        self._sel_btns: list = []
        self._selected_idx   = -1
        self._sel_reading    = ""
        ex_ja, _ = extract_example_sentence(translation)
        self.sentence = ex_ja if ex_ja else orig

        self.title("句子卡 —— 點擊詞元選取發音")
        self.geometry("560x580")
        self.resizable(True, True)
        self.attributes("-topmost", True)
        self.grab_set()
        self._build()
        threading.Thread(target=self._load_tokens, daemon=True).start()

    def _build(self):
        f = ttk.Frame(self, padding=12); f.pack(fill="both", expand=True)

        ttk.Label(f, text="例句（正面）：", font=("",9,"bold")).pack(anchor="w")
        sb = tk.Text(f, height=2, wrap="word", font=("Yu Gothic UI",11),
                     relief="flat", bg="#fff8e1", state="normal")
        sb.insert("1.0", self.sentence); sb.configure(state="disabled")
        sb.pack(fill="x", pady=(2,4))

        ttk.Label(f, text="翻譯（背面）：", font=("",9,"bold")).pack(anchor="w")
        tb = tk.Text(f, height=2, wrap="word", font=("Microsoft JhengHei",11),
                     relief="flat", bg="#f0f8ff", state="normal")
        tb.insert("1.0", extract_clean_translation(self.translation))
        tb.configure(state="disabled")
        tb.pack(fill="x", pady=(2,8))

        ttk.Separator(f).pack(fill="x", pady=4)
        ttk.Label(f, text="👆 點擊要查發音的詞（可略過）：", font=("",9,"bold")).pack(anchor="w")
        ttk.Label(f, text="（選取詞元用於 Forvo 音訊；不選則不附音訊）",
                  foreground="gray").pack(anchor="w")

        token_outer = ttk.Frame(f); token_outer.pack(fill="x", pady=4)
        canvas = tk.Canvas(token_outer, height=72, bg="#fafafa",
                           highlightthickness=1, highlightbackground="#ddd")
        hbar = ttk.Scrollbar(token_outer, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=hbar.set)
        hbar.pack(side="bottom", fill="x"); canvas.pack(fill="x")
        self.token_frame = ttk.Frame(canvas)
        canvas.create_window((0,0), window=self.token_frame, anchor="nw")
        self.token_frame.bind("<Configure>",
                              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self.loading_lbl = ttk.Label(self.token_frame, text="⏳ 切詞中...", foreground="gray")
        self.loading_lbl.pack(side="left", padx=6)

        ttk.Separator(f).pack(fill="x", pady=6)

        sel_row = ttk.Frame(f); sel_row.pack(fill="x")
        ttk.Label(sel_row, text="發音單字：").pack(side="left")
        self.word_var = tk.StringVar(value="（未選取，不附音訊）")
        ttk.Label(sel_row, textvariable=self.word_var,
                  font=("Yu Gothic UI",12,"bold"), foreground="#1a6fb5").pack(side="left", padx=6)

        reading_row = ttk.Frame(f); reading_row.pack(fill="x", pady=(2,0))
        ttk.Label(reading_row, text="讀音：").pack(side="left")
        self.reading_var = tk.StringVar(value="")
        self.reading_entry = ttk.Entry(reading_row, textvariable=self.reading_var,
                                        width=30, font=("Yu Gothic UI", 11))
        self.reading_entry.pack(side="left", padx=4)
        ttk.Label(reading_row, text="（可手動修改，會存入 Anki）",
                  foreground="gray").pack(side="left")

        ttk.Separator(f).pack(fill="x", pady=4)

        # 單字查詢
        lkp_row = ttk.Frame(f); lkp_row.pack(fill="x")
        self.lookup_btn = ttk.Button(lkp_row, text="🔍 查詢此單字",
                                     command=self._lookup_word, state="disabled")
        self.lookup_btn.pack(side="left")
        ttk.Label(lkp_row, text="← 選取詞元後可查詢", foreground="gray").pack(side="left", padx=6)

        exp_frame = ttk.Frame(f); exp_frame.pack(fill="both", expand=True, pady=(4,0))
        self.explain_text = tk.Text(exp_frame, height=6, wrap="word",
                                    font=("Microsoft JhengHei",10),
                                    state="disabled", relief="flat", bg="#f9f9f9")
        exp_sb = ttk.Scrollbar(exp_frame, orient="vertical", command=self.explain_text.yview)
        self.explain_text.configure(yscrollcommand=exp_sb.set)
        exp_sb.pack(side="right", fill="y")
        self.explain_text.pack(side="left", fill="both", expand=True)

        self.make_card_btn = ttk.Button(f, text="📝 以解說製成單字卡",
                                        command=self._make_word_card, state="disabled")
        self.make_card_btn.pack(anchor="w", pady=(4,0))

        ttk.Separator(f).pack(fill="x", pady=6)
        btn_row = ttk.Frame(f); btn_row.pack()
        ttk.Button(btn_row, text="🃏 加入 Anki（句子卡）",
                   command=self._submit).pack(side="left", padx=6)
        ttk.Button(btn_row, text="取消", command=self.destroy).pack(side="left", padx=6)
        self.status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.status, foreground="green").pack(pady=2)

    def _load_tokens(self):
        self._tokens = tokenize_sentence(self.sentence)
        lang = self.cfg.get("ocr_language", "ja")
        sent_reading = extract_reading(self.sentence) if lang == "ja" else ""
        self.after(0, lambda: self.reading_var.set(sent_reading))
        self.after(0, self._render_tokens)

    def _render_tokens(self):
        self.loading_lbl.destroy()
        for i, (surf, hira) in enumerate(self._tokens):
            cell = ttk.Frame(self.token_frame, relief="ridge", padding=2)
            cell.pack(side="left", padx=2, pady=4)
            tk.Label(cell, text=hira if hira != surf else "",
                     font=("Yu Gothic UI",7), fg="#888", bg="#fafafa").pack()
            btn = tk.Button(cell, text=surf, font=("Yu Gothic UI",12),
                            relief="flat", bg="#fafafa", activebackground="#d0e8ff",
                            cursor="hand2", padx=4,
                            command=lambda idx=i: self._select_token(idx))
            btn.pack()
            self._sel_btns.append((btn, cell))

    def _select_token(self, idx: int):
        if 0 <= self._selected_idx < len(self._sel_btns):
            ob, oc = self._sel_btns[self._selected_idx]
            ob.configure(bg="#fafafa"); oc.configure(relief="ridge")
        self._selected_idx = idx
        btn, cell = self._sel_btns[idx]
        btn.configure(bg="#b3d4ff"); cell.configure(relief="solid")
        surf, hira = self._tokens[idx]
        self.word_var.set(surf)
        self._sel_reading = hira if hira != surf else ""
        self.lookup_btn.configure(state="normal")

    def _lookup_word(self):
        word = self.word_var.get().strip()
        if not word or word == "（未選取，不附音訊）": return
        self._set_explain("⏳ 查詢中...")
        self.lookup_btn.configure(state="disabled")
        def _w():
            try:
                result, _ = translate(word, self.cfg, system_prompt=_word_prompt(self.cfg))
                self.after(0, lambda: self._set_explain(result))
            except Exception as e:
                self.after(0, lambda: self._set_explain(f"❌ {e}"))
            self.after(0, lambda: self.lookup_btn.configure(state="normal"))
        threading.Thread(target=_w, daemon=True).start()

    def _set_explain(self, text: str):
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        self.explain_text.configure(state="normal")
        self.explain_text.delete("1.0", "end")
        self.explain_text.insert("1.0", text)
        self.explain_text.configure(state="disabled")
        # 查詢完成後才啟用製卡按鈕
        if not text.startswith("⏳"):
            self.make_card_btn.configure(state="normal")

    def _make_word_card(self):
        word = self.word_var.get().strip()
        if not word or word == "（未選取，不附音訊）": return
        explain = self.explain_text.get("1.0", "end").strip()
        if not explain: return
        self.status.set("⏳ 製作單字卡...")
        # Use token reading if available; fall back to pykakasi for the whole word
        reading = self._sel_reading or extract_reading(word)
        # Anki fields are HTML; convert newlines so they render as line breaks
        explain_html = explain.replace("\n", "<br>")
        def _w():
            try:
                ok, msg = add_sentence_note(
                    orig=word, example=word,
                    trans=explain_html, reading=reading,
                    audio_tag="", cfg=self.cfg)
                final = f"{'✅' if ok else '❌'} {msg}"
                self.after(0, lambda: self.status.set(final))
                if ok:
                    self.after(1500, self.destroy)
                    self.after(0, lambda: self.on_done(final))
            except Exception as e:
                self.after(0, lambda: self.status.set(f"❌ {e}"))
        threading.Thread(target=_w, daemon=True).start()

    def _submit(self):
        self.status.set("⏳ 加入中...")
        word = self.word_var.get().strip()
        reading = self._sel_reading
        has_word = word and word != "（未選取，不附音訊）"

        def _w():
            try:
                audio_tag = ""
                key = self.cfg.get("forvo_api_key","").strip()
                lang = self.cfg.get("ocr_language","ja")
                if key and has_word:
                    try:
                        audio_tag = get_forvo_tag(reading if reading else word,
                                                  lang, key, self.cfg["anki_url"])
                        self.after(0, lambda: self.status.set("✅ 音訊取得"))
                    except Exception as e:
                        self.after(0, lambda: self.status.set(f"⚠️ Forvo：{e}，繼續加入"))

                sent_reading = self.reading_var.get().strip()
                ok, msg = add_sentence_note(
                    orig=self.orig, example=self.sentence,
                    trans=extract_clean_translation(self.translation),
                    reading=sent_reading, audio_tag=audio_tag, cfg=self.cfg)
                final = f"{'✅' if ok else '❌'} {msg}"
                self.after(0, lambda: self.status.set(final))
                if ok:
                    self.after(1500, self.destroy)
                    self.after(0, lambda: self.on_done(final))
            except Exception as e:
                self.after(0, lambda: self.status.set(f"❌ {e}"))

        threading.Thread(target=_w, daemon=True).start()


# ── 一般設定視窗 ──────────────────────────────────────────────
class GeneralSettingsWindow(tk.Toplevel):
    def __init__(self, parent, cfg, on_save):
        super().__init__(parent)
        self.cfg=cfg.copy(); self.on_save=on_save
        self.title("翻譯設定"); self.resizable(False,False)
        self.attributes("-topmost", True); self.grab_set()
        nb = ttk.Notebook(self); nb.pack(fill="both",expand=True,padx=8,pady=8)
        self._api(nb); self._tx(nb); self._prompt_tab(nb); self._gen(nb)
        btn=ttk.Frame(self); btn.pack(pady=6)
        ttk.Button(btn,text="儲存",command=self._save).pack(side="left",padx=4)
        ttk.Button(btn,text="取消",command=self.destroy).pack(side="left",padx=4)

    def _R(self,f,lbl,row): ttk.Label(f,text=lbl).grid(row=row,column=0,sticky="w",padx=8,pady=4)
    def _E(self,f,var,row,col=1,w=30,show=""):
        e=ttk.Entry(f,textvariable=var,width=w,show=show)
        e.grid(row=row,column=col,sticky="w",padx=8,pady=4); return e

    def _ocr(self,nb):
        f=ttk.Frame(nb,padding=12); nb.add(f,text="OCR")
        P={"padx":8,"pady":4}
        self._R(f,"OCR 引擎",0)
        self.eng=tk.StringVar(value=self.cfg.get("ocr_engine","manga-ocr"))
        ecb=ttk.Combobox(f,textvariable=self.eng,values=["manga-ocr","easyocr"],state="readonly",width=14)
        ecb.grid(row=0,column=1,sticky="w",**P); ecb.bind("<<ComboboxSelected>>",self._echange)
        self.enote=ttk.Label(f,foreground="gray",wraplength=300)
        self.enote.grid(row=1,column=0,columnspan=3,sticky="w",padx=8)
        ttk.Separator(f).grid(row=2,column=0,columnspan=3,sticky="ew",pady=6)
        self._R(f,"辨識語言",3)
        self.lang=tk.StringVar(value=self.cfg.get("ocr_language","ja"))
        self.lcb=ttk.Combobox(f,textvariable=self.lang,values=["ja","ko","ja+ko"],state="readonly",width=10)
        self.lcb.grid(row=3,column=1,sticky="w",**P)
        ttk.Label(f,text="ja＝日文　ko＝韓文　ja+ko＝混合",foreground="gray").grid(row=4,column=0,columnspan=3,sticky="w",padx=8)
        ttk.Separator(f).grid(row=5,column=0,columnspan=3,sticky="ew",pady=6)
        self._R(f,"文字方向",6)
        self.dirn=tk.StringVar(value=self.cfg.get("text_direction","ltr"))
        ttk.Radiobutton(f,text="左→右",variable=self.dirn,value="ltr").grid(row=6,column=1,sticky="w",**P)
        ttk.Radiobutton(f,text="右→左",variable=self.dirn,value="rtl").grid(row=7,column=1,sticky="w",**P)
        self._echange()

    def _echange(self,_=None):
        e=self.eng.get()
        if e=="manga-ocr":
            self.enote.configure(text="manga-ocr：日文優化，僅支援日文。")
            self.lang.set("ja"); self.lcb.configure(state="disabled")
        else:
            self.enote.configure(text="EasyOCR：支援日韓，首次下載 ~300MB/語言。")
            self.lcb.configure(state="readonly")

    def _api(self,nb):
        f=ttk.Frame(nb,padding=12); nb.add(f,text="翻譯 API")
        P={"padx":8,"pady":4}
        self._R(f,"翻譯使用模型",0)
        ttk.Label(f,text="（由上至下＝優先順序，前者失敗自動 fallback）",
                  foreground="gray").grid(row=0,column=2,sticky="w",padx=4)

        list_f=ttk.Frame(f); list_f.grid(row=1,column=0,columnspan=3,sticky="w",padx=8,pady=4)
        self.prov_lb=tk.Listbox(list_f,height=4,width=14,exportselection=False)
        self.prov_lb.pack(side="left")
        priority=self.cfg.get("api_priority") or [self.cfg.get("api_provider","groq")]
        for p in priority:
            self.prov_lb.insert("end", p)

        btn_f=ttk.Frame(list_f); btn_f.pack(side="left",padx=6)
        ttk.Button(btn_f,text="↑",width=3,command=self._prov_up).pack()
        ttk.Button(btn_f,text="↓",width=3,command=self._prov_down).pack(pady=2)
        ttk.Button(btn_f,text="⊖",width=3,command=self._prov_remove).pack()

        add_f=ttk.Frame(list_f); add_f.pack(side="left",padx=6)
        self.prov_add=tk.StringVar(value="claude")
        ttk.Combobox(add_f,textvariable=self.prov_add,
                     values=["groq","gemini","claude","openrouter","ollama"],
                     state="readonly",width=12).pack()
        ttk.Button(add_f,text="⊕ 加入",command=self._prov_add).pack(pady=2)

        self.kvars={}
        for i,(k,lbl) in enumerate([
            ("groq_api_key","Groq"),
            ("gemini_api_key","Gemini"),
            ("claude_api_key","Claude"),
            ("openrouter_api_key","OpenRouter"),
        ],2):
            self._R(f,f"{lbl} API Key",i)
            v=tk.StringVar(value=self.cfg.get(k,""))
            ttk.Entry(f,textvariable=v,width=44,show="*").grid(row=i,column=1,columnspan=2,sticky="ew",**P)
            self.kvars[k]=v
        self._R(f,"Groq 模型",6)
        self.gm=tk.StringVar(value=self.cfg.get("groq_model","llama-3.3-70b-versatile"))
        ttk.Combobox(f,textvariable=self.gm,width=30,
                     values=["llama-3.3-70b-versatile","llama-3.1-8b-instant","gemma2-9b-it"]
                     ).grid(row=6,column=1,sticky="w",**P)
        self._R(f,"OpenRouter 模型",7)
        self.orm=tk.StringVar(value=self.cfg.get("openrouter_model","meta-llama/llama-3.3-70b-instruct:free"))
        ttk.Combobox(f,textvariable=self.orm,width=44,
                     values=[
                         "meta-llama/llama-3.3-70b-instruct:free",
                         "google/gemini-2.0-flash-exp:free",
                         "deepseek/deepseek-chat-v3-0324:free",
                         "qwen/qwen-2.5-72b-instruct:free",
                         "anthropic/claude-3.5-sonnet",
                         "openai/gpt-4o-mini",
                     ]).grid(row=7,column=1,columnspan=2,sticky="ew",**P)
        ttk.Label(f,text="可自由輸入任何 OpenRouter model slug；:free 後綴為免費額度",
                  foreground="gray").grid(row=8,column=0,columnspan=3,sticky="w",padx=8)
        ttk.Separator(f).grid(row=9,column=0,columnspan=3,sticky="ew",pady=8)
        self._R(f,"Ollama URL",10); self.ou=tk.StringVar(value=self.cfg.get("ollama_url","http://localhost:11434"))
        self._E(f,self.ou,10)
        self._R(f,"Ollama 模型",11); self.om=tk.StringVar(value=self.cfg.get("ollama_model","gemma3:12b"))
        self._E(f,self.om,11,w=24)

    def _prov_up(self):
        sel=self.prov_lb.curselection()
        if not sel or sel[0]==0: return
        i=sel[0]; v=self.prov_lb.get(i)
        self.prov_lb.delete(i); self.prov_lb.insert(i-1,v)
        self.prov_lb.selection_set(i-1)

    def _prov_down(self):
        sel=self.prov_lb.curselection()
        if not sel or sel[0]==self.prov_lb.size()-1: return
        i=sel[0]; v=self.prov_lb.get(i)
        self.prov_lb.delete(i); self.prov_lb.insert(i+1,v)
        self.prov_lb.selection_set(i+1)

    def _prov_remove(self):
        sel=self.prov_lb.curselection()
        if not sel or self.prov_lb.size()<=1: return
        self.prov_lb.delete(sel[0])

    def _prov_add(self):
        p=self.prov_add.get()
        existing=list(self.prov_lb.get(0,"end"))
        if p in existing: return
        self.prov_lb.insert("end",p)

    def _tx(self,nb):
        f=ttk.Frame(nb,padding=12); nb.add(f,text="Textractor")
        P={"padx":8,"pady":5}
        ttk.Label(f,text="Textractor → Extensions → Copy to Clipboard",foreground="gray30"
                  ).grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,8))
        self.txf=tk.BooleanVar(value=self.cfg.get("textractor_filter_english",True))
        ttk.Checkbutton(f,text="過濾純英文",variable=self.txf).grid(row=1,column=0,columnspan=2,sticky="w",**P)
        self._R(f,"最少字元數",2)
        self.txm=tk.IntVar(value=self.cfg.get("textractor_min_length",3))
        ttk.Spinbox(f,from_=1,to=20,textvariable=self.txm,width=6).grid(row=2,column=1,sticky="w",**P)

    def _prompt_tab(self,nb):
        f=ttk.Frame(nb,padding=12); nb.add(f,text="AI Prompt")
        ttk.Label(f,text="自訂翻譯 prompt（留空則使用預設）。{src} 會自動替換為「日文」/「韓文」",
                  foreground="gray",wraplength=520).pack(anchor="w",pady=(0,6))
        txt_f=ttk.Frame(f); txt_f.pack(fill="both",expand=True)
        sb=ttk.Scrollbar(txt_f,orient="vertical")
        self.prompt_txt=tk.Text(txt_f,wrap="word",height=18,width=64,
                                yscrollcommand=sb.set,font=("Consolas",10))
        sb.configure(command=self.prompt_txt.yview)
        self.prompt_txt.pack(side="left",fill="both",expand=True)
        sb.pack(side="right",fill="y")
        # 載入既有設定，若空則填入預設供使用者編輯
        existing=self.cfg.get("translation_prompt","").strip()
        self.prompt_txt.insert("1.0", existing or DEFAULT_TRANSLATION_PROMPT_TEMPLATE)
        btn=ttk.Frame(f); btn.pack(fill="x",pady=(6,0))
        def _restore():
            self.prompt_txt.delete("1.0","end")
            self.prompt_txt.insert("1.0", DEFAULT_TRANSLATION_PROMPT_TEMPLATE)
        ttk.Button(btn,text="↺ 還原預設",command=_restore).pack(side="left")
        ttk.Label(btn,text="儲存空白＝改回預設",foreground="gray").pack(side="left",padx=10)

    def _gen(self,nb):
        f=ttk.Frame(nb,padding=12); nb.add(f,text="一般")
        P={"padx":8,"pady":4}
        self._R(f,"自動截圖間隔 (秒)",0)
        self.intv=tk.DoubleVar(value=self.cfg.get("auto_interval",3.0))
        ttk.Spinbox(f,from_=1,to=60,textvariable=self.intv,width=6,increment=0.5).grid(row=0,column=1,sticky="w",**P)
        self._R(f,"字體大小",1)
        self.fs=tk.IntVar(value=self.cfg.get("font_size",14))
        ttk.Spinbox(f,from_=10,to=28,textvariable=self.fs,width=6).grid(row=1,column=1,sticky="w",**P)
        ttk.Separator(f).grid(row=2,column=0,columnspan=3,sticky="ew",pady=8)
        self._R(f,"截圖快捷鍵",3)
        self.hk=tk.StringVar(value=self.cfg.get("global_hotkey","ctrl+alt+q"))
        ttk.Entry(f,textvariable=self.hk,width=22).grid(row=3,column=1,sticky="w",**P)
        ttk.Label(f,text="例：ctrl+alt+q、ctrl+shift+space",foreground="gray").grid(
            row=4,column=0,columnspan=3,sticky="w",padx=8)
        self._R(f,"監聽快捷鍵",5)
        self.chk=tk.StringVar(value=self.cfg.get("clip_hotkey","ctrl+alt+t"))
        ttk.Entry(f,textvariable=self.chk,width=22).grid(row=5,column=1,sticky="w",**P)
        ttk.Label(f,text="切換 Textractor 剪貼簿監聽（監聽中按 ESC 也可取消）",foreground="gray").grid(
            row=6,column=0,columnspan=3,sticky="w",padx=8)
        ttk.Separator(f).grid(row=7,column=0,columnspan=3,sticky="ew",pady=8)
        self.ask=tk.BooleanVar(value=self.cfg.get("close_ask",True))
        ttk.Checkbutton(f,text="關閉視窗時詢問（隱藏到背景 / 完全退出）",
                        variable=self.ask).grid(row=8,column=0,columnspan=3,sticky="w",padx=8,pady=2)
        self.bg=tk.BooleanVar(value=self.cfg.get("background_mode",True))
        ttk.Checkbutton(f,text="不詢問時，關閉 X 預設隱藏到背景",
                        variable=self.bg).grid(row=9,column=0,columnspan=3,sticky="w",padx=8,pady=2)
        ttk.Separator(f).grid(row=10,column=0,columnspan=3,sticky="ew",pady=8)
        self.autostart=tk.BooleanVar(value=self.cfg.get("autostart",False))
        ttk.Checkbutton(f,text="開機後自動啟動（背景運作，縮到系統匣）",
                        variable=self.autostart).grid(row=11,column=0,columnspan=3,sticky="w",padx=8,pady=2)
        ttk.Label(f,text="啟用後寫入 HKCU\\...\\Run 登錄檔，不需管理員權限",
                  foreground="gray").grid(row=12,column=0,columnspan=3,sticky="w",padx=8)

    def _save(self):
        prompt_val = self.prompt_txt.get("1.0","end-1c").strip()
        # 若內容等同預設，存空字串以利未來預設更新時自動套用
        if prompt_val == DEFAULT_TRANSLATION_PROMPT_TEMPLATE.strip():
            prompt_val = ""
        priority = list(self.prov_lb.get(0,"end"))
        if not priority:
            priority = ["groq"]
        self.cfg.update({
            "api_priority": priority,
            "api_provider": priority[0],
            "groq_model":self.gm.get(),
            "openrouter_model":self.orm.get().strip(),
            "ollama_url":self.ou.get().strip(),
            "ollama_model":self.om.get().strip(),
            "textractor_filter_english":self.txf.get(),
            "textractor_min_length":self.txm.get(),
            "auto_interval":self.intv.get(),"font_size":self.fs.get(),
            "global_hotkey":self.hk.get().strip().lower(),
            "clip_hotkey":self.chk.get().strip().lower(),
            "close_ask":self.ask.get(),
            "background_mode":self.bg.get(),
            "autostart":self.autostart.get(),
            "translation_prompt":prompt_val,
        })
        for k,v in self.kvars.items(): self.cfg[k]=v.get().strip()
        ok, msg = apply_autostart(self.autostart.get())
        if not ok:
            messagebox.showwarning("開機自動啟動", msg, parent=self)
        self.on_save(self.cfg); self.destroy()


# ── Windows 開機自動啟動 ────────────────────────────────────
AUTOSTART_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "GameTranslator"

def _autostart_target_cmd() -> str:
    if getattr(sys, "frozen", False):
        exe = str(Path(sys.executable).resolve())
        return f'"{exe}" --minimized'
    pyw = str(Path(sys.executable).with_name("pythonw.exe"))
    script = str(Path(__file__).resolve())
    return f'"{pyw}" "{script}" --minimized'

def apply_autostart(enabled: bool) -> tuple:
    try:
        import winreg
    except ImportError:
        return False, "此功能僅支援 Windows"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                            0, winreg.KEY_ALL_ACCESS) as k:
            if enabled:
                winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ,
                                  _autostart_target_cmd())
                return True, "已啟用開機自動啟動"
            try:
                winreg.DeleteValue(k, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
            return True, "已關閉開機自動啟動"
    except OSError as e:
        return False, f"寫入登錄檔失敗：{e}"


# ── 系統匣圖示產生 ───────────────────────────────────────────
def _make_tray_image(size=64):
    """動態產生 tray 圖示：藍底 + 白色 T 字"""
    img = Image.new("RGB", (size, size), (40, 110, 200))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, size-5, size-5], radius=8,
                           outline=(255, 255, 255), width=3)
    try:
        font = ImageFont.truetype("arial.ttf", int(size*0.55))
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "T", font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text(((size-tw)/2 - bbox[0], (size-th)/2 - bbox[1] - 2),
              "T", fill=(255, 255, 255), font=font)
    return img


# ── 主視窗 ───────────────────────────────────────────────────
class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.ocr_ready=False
        self._working=False; self._last_clip=""; self._clip_polling=False
        self._last_orig=""; self._last_trans=""
        self._tx_debounce_id=None; self._tx_pending=""

        self.title("🎮 遊戲即時翻譯"); self.geometry("900x580")
        self.resizable(True,True); self.attributes("-topmost",True)

        self._current_hotkey = None
        self._current_clip_hotkey = None
        self._esc_hotkey = None
        self._tray_icon = None
        self._quitting = False

        self._build_ui()
        self.bind("<F9>", lambda e: self.select_region())
        # 延後註冊：等 mainloop 開始、keyboard hook thread 啟動後，
        # 首次按鍵才不會落在 hook 尚未就緒的空窗
        self.after(300, self._register_global_hotkey)
        self._start_tray()
        self.protocol("WM_DELETE_WINDOW", self._on_close_window)
        threading.Thread(target=self._preload_ocr, daemon=True).start()
        self._refresh_history()

    # ── UI ──────────────────────────────────────────────────
    def _build_ui(self):
        P={"padx":5,"pady":3}
        # 左右分割
        pane = tk.PanedWindow(self, orient="horizontal", sashwidth=6, bg="#ccc")
        pane.pack(fill="both", expand=True)

        # ── 左：主翻譯區 ─────────────────────────────────────
        left = ttk.Frame(pane); pane.add(left, minsize=400, stretch="always")

        # 模式分頁
        self.nb = ttk.Notebook(left); self.nb.pack(fill="x", padx=6, pady=(6,0))
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab)
        ocr_f=ttk.Frame(self.nb); tx_f=ttk.Frame(self.nb)
        self.nb.add(ocr_f, text="📸 OCR 截圖"); self.nb.add(tx_f, text="🔗 Textractor")

        _hk = self.cfg.get("global_hotkey","ctrl+alt+q").upper()
        self._region_btn = ttk.Button(ocr_f,text=f"✂️ 選取區域並翻譯 ({_hk})",command=self.select_region)
        self._region_btn.pack(side="left",**P)
        ttk.Button(ocr_f,text="清除",command=self.clear_region).pack(side="right",**P)
        ttk.Button(ocr_f,text="🔍 OCR 診斷",command=self._diag_ocr).pack(side="right",**P)

        # OCR 快速設定列
        info=ttk.Frame(left); info.pack(fill="x",padx=8,pady=(2,0))
        ttk.Label(info,text="引擎：").pack(side="left")
        self.eng_var=tk.StringVar(value=self.cfg.get("ocr_engine","manga-ocr"))
        eng_cb=ttk.Combobox(info,textvariable=self.eng_var,values=["manga-ocr","easyocr"],state="readonly",width=11)
        eng_cb.pack(side="left",padx=2); eng_cb.bind("<<ComboboxSelected>>",self._engine_chg)
        ttk.Separator(info,orient="vertical").pack(side="left",fill="y",padx=6,pady=2)
        ttk.Label(info,text="語言：").pack(side="left")
        self.lang_var=tk.StringVar(value=self.cfg.get("ocr_language","ja"))
        self.lang_cb=ttk.Combobox(info,textvariable=self.lang_var,values=["ja","ko","ja+ko"],state="readonly",width=7)
        self.lang_cb.pack(side="left",padx=2); self.lang_cb.bind("<<ComboboxSelected>>",self._lang_chg)
        ttk.Separator(info,orient="vertical").pack(side="left",fill="y",padx=6,pady=2)
        ttk.Label(info,text="方向：").pack(side="left")
        self.dir_var=tk.StringVar(value=self.cfg.get("text_direction","ltr"))
        ttk.Radiobutton(info,text="左→右",variable=self.dir_var,value="ltr",command=self._dir_chg).pack(side="left")
        ttk.Radiobutton(info,text="右→左",variable=self.dir_var,value="rtl",command=self._dir_chg).pack(side="left",padx=(0,4))
        # manga-ocr 僅支援日文，禁用語言選單
        if self.cfg.get("ocr_engine","manga-ocr") == "manga-ocr":
            self.lang_cb.configure(state="disabled")

        # Textractor tab
        self.tx_st=tk.StringVar(value="⏸ 未啟動")
        ttk.Label(tx_f,textvariable=self.tx_st,foreground="gray30").pack(side="left",**P)
        self.tx_btn=tk.StringVar()
        self._set_tx_btn_text(active=False)
        ttk.Button(tx_f,textvariable=self.tx_btn,command=self.toggle_tx).pack(side="left",**P)
        self._tx_hint=tk.StringVar()
        self._set_tx_hint_text(active=False)
        ttk.Label(tx_f,textvariable=self._tx_hint,foreground="#999").pack(side="left")

        # 設定按鈕
        top=ttk.Frame(left); top.pack(fill="x",padx=8,pady=(2,0))
        ttk.Button(top,text="⚙️ 翻譯設定",command=self.open_settings).pack(side="right",padx=2)
        ttk.Button(top,text="🃏 Anki 設定",command=self.open_anki_settings).pack(side="right",padx=2)

        # 狀態
        self.status=tk.StringVar(value="就緒｜載入 OCR 中...")
        ttk.Label(left,textvariable=self.status,relief="sunken",anchor="w",padding=(6,2)).pack(fill="x",side="bottom")

        # 原文框
        of=ttk.LabelFrame(left,text="原文",padding=4)
        of.pack(fill="both",expand=True,padx=8,pady=4)
        self.orig_text=tk.Text(of,height=4,wrap="word",
            font=("Yu Gothic UI",self.cfg["font_size"]),state="disabled",relief="flat",bg="#f8f8f8")
        self.orig_text.pack(fill="both",expand=True)

        # 翻譯框
        tf=ttk.LabelFrame(left,text="繁體中文翻譯",padding=4)
        tf.pack(fill="both",expand=True,padx=8,pady=(0,2))
        self.trans_text=tk.Text(tf,height=4,wrap="word",
            font=("Microsoft JhengHei",self.cfg["font_size"]),state="disabled",relief="flat",bg="#f0f8ff")
        self.trans_text.pack(fill="both",expand=True)

        # Anki 匯出列
        anki_bar=ttk.Frame(left); anki_bar.pack(fill="x",padx=8,pady=(0,6))
        ttk.Button(anki_bar,text="🃏 句子卡",command=self.add_sentence).pack(side="left")
        ttk.Button(anki_bar,text="✂️ 挖空卡",command=self.add_cloze).pack(side="left",padx=6)
        self.anki_status=tk.StringVar(value="")
        ttk.Label(anki_bar,textvariable=self.anki_status,foreground="green").pack(side="left")

        # ── 右：歷史側欄 ─────────────────────────────────────
        right=ttk.Frame(pane); pane.add(right, minsize=220, stretch="never")

        hist_top=ttk.Frame(right); hist_top.pack(fill="x",padx=6,pady=(6,0))
        ttk.Label(hist_top,text="📜 翻譯歷史",font=("",10,"bold")).pack(side="left")
        ttk.Button(hist_top,text="清除",command=self._clear_hist,width=4).pack(side="right")

        # 搜尋
        srch=ttk.Frame(right); srch.pack(fill="x",padx=6,pady=3)
        self.srch_var=tk.StringVar()
        srch_e=ttk.Entry(srch,textvariable=self.srch_var,width=18)
        srch_e.pack(side="left",fill="x",expand=True)
        srch_e.bind("<KeyRelease>", lambda e: self._refresh_history())

        # 歷史列表
        hist_frame=ttk.Frame(right); hist_frame.pack(fill="both",expand=True,padx=6,pady=3)
        self.hist_list=tk.Listbox(hist_frame,font=("Microsoft JhengHei",9),
                                   activestyle="dotbox",selectmode="extended")
        sb=ttk.Scrollbar(hist_frame,orient="vertical",command=self.hist_list.yview)
        self.hist_list.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y")
        self.hist_list.pack(side="left",fill="both",expand=True)
        self.hist_list.bind("<<ListboxSelect>>", self._on_hist_select)
        self._hist_entries: list = []

        # 批量加入 Anki
        bulk_bar=ttk.Frame(right); bulk_bar.pack(fill="x",padx=6,pady=(0,4))
        ttk.Button(bulk_bar,text="🃏 批量句子卡",command=self._bulk_add_sentence).pack(side="left",padx=4)
        self.hist_anki_status=tk.StringVar(value="")
        ttk.Label(bulk_bar,textvariable=self.hist_anki_status,foreground="green",wraplength=160).pack(side="left")

    # ── 快速列回呼 ─────────────────────────────────────────
    def _engine_chg(self,_=None):
        e=self.eng_var.get(); self.cfg["ocr_engine"]=e
        if e=="manga-ocr":
            self.lang_var.set("ja"); self.cfg["ocr_language"]="ja"
            self.lang_cb.configure(state="disabled")
        else:
            self.lang_cb.configure(state="readonly")
        self.ocr_ready=False
        threading.Thread(target=self._preload_ocr, daemon=True).start()
        save_config(self.cfg)

    def _lang_chg(self,_=None):
        l=self.lang_var.get(); self.cfg["ocr_language"]=l
        if l in ("ko","ja+ko") and self.cfg.get("ocr_engine")=="manga-ocr":
            self.cfg["ocr_engine"]="easyocr"
            self.eng_var.set("easyocr")
            self.lang_cb.configure(state="readonly")
            self.status.set("⚠️ 韓文需要 EasyOCR，已自動切換")
        save_config(self.cfg)

    def _dir_chg(self): self.cfg["text_direction"]=self.dir_var.get(); save_config(self.cfg)
    def _on_tab(self,_=None):
        if self.nb.index("current")==0 and self._clip_polling: self._stop_tx()

    # ── OCR 預載 ────────────────────────────────────────────
    def _preload_ocr(self):
        # 診斷 OCR 套件安裝狀況，更新至狀態列
        diag = []
        try:
            import manga_ocr as _mocr
            ver = getattr(_mocr, "__version__", "?")
            diag.append(f"manga_ocr✅{ver}")
        except ImportError as e:
            diag.append(f"manga_ocr❌({e})")
        except Exception as e:
            diag.append(f"manga_ocr⚠️({e})")
        try:
            import easyocr as _eocr
            ver = getattr(_eocr, "__version__", "?")
            diag.append(f"easyocr✅{ver}")
        except ImportError as e:
            diag.append(f"easyocr❌({e})")
        except Exception as e:
            diag.append(f"easyocr⚠️({e})")
        diag_str = " | ".join(diag)
        self.after(0, lambda: self.status.set(f"🔍 OCR 診斷：{diag_str}"))

        try:
            eng=self.cfg.get("ocr_engine","manga-ocr")
            (get_manga_ocr if eng=="manga-ocr" else lambda: get_easy_ocr(_lang_tuple(self.cfg)))()
            self.ocr_ready=True
            _hk = self.cfg.get("global_hotkey","ctrl+alt+q").upper()
            self.after(0,lambda: self.status.set(f"✅ 就緒｜{eng}｜{_hk} 截圖翻譯"))
        except Exception as e:
            self.after(0,lambda e=e: self.status.set(f"❌ OCR 載入失敗：{e}"))

    def _diag_ocr(self):
        """彈出 OCR 套件診斷視窗"""
        lines = ["=== OCR 套件診斷 ===\n"]
        missing_pkg = False

        # manga_ocr
        try:
            import manga_ocr as _mocr
            ver = getattr(_mocr, "__version__", "版本未知")
            lines.append(f"manga_ocr : ✅ 已安裝  版本 {ver}")
        except ImportError as e:
            lines.append(f"manga_ocr : ❌ 未安裝\n  ModuleNotFoundError: {e}")
            missing_pkg = True
        except Exception as e:
            lines.append(f"manga_ocr : ⚠️ 載入異常\n  {type(e).__name__}: {e}")

        # easyocr
        try:
            import easyocr as _eocr
            ver = getattr(_eocr, "__version__", "版本未知")
            lines.append(f"easyocr   : ✅ 已安裝  版本 {ver}")
        except ImportError as e:
            lines.append(f"easyocr   : ❌ 未安裝\n  ModuleNotFoundError: {e}")
            missing_pkg = True
        except Exception as e:
            lines.append(f"easyocr   : ⚠️ 載入異常\n  {type(e).__name__}: {e}")

        if missing_pkg:
            lines.append("\n⚠️ 有套件未安裝，請執行 install_ocr.bat 安裝 OCR 套件。")

        lines.append(f"\nPython 執行路徑:\n  {sys.executable}")
        frozen = "是（PyInstaller 打包）" if getattr(sys, "frozen", False) else "否（源碼模式）"
        lines.append(f"\nFrozen 模式: {frozen}")
        lines.append("\nsys.path:")
        for p in sys.path:
            lines.append(f"  {p}")

        win = tk.Toplevel(self)
        win.title("🔍 OCR 套件診斷")
        win.geometry("640x420")
        win.grab_set()

        txt = tk.Text(win, wrap="word", font=("Consolas", 10), padx=8, pady=8)
        sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")
        ttk.Button(win, text="關閉", command=win.destroy).pack(pady=6)

    # ── 截圖翻譯 ─────────────────────────────────────────────
    # ── 區域選取 ─────────────────────────────────────────────
    def select_region(self):
        self.withdraw()
        def _on_select(region):
            self.cfg["capture_region"] = region
            save_config(self.cfg)
            # 主視窗保持隱藏，直接進入截圖流程；
            # do_capture 會再次 withdraw（無害）再由 _capture_worker deiconify
            self.do_capture()
        def _on_cancel():
            self.deiconify()
        sel = RegionSelector(self, _on_select)
        def _cancel_and_restore(*_):
            try: sel.destroy()
            except Exception: pass
            _on_cancel()
        sel.protocol("WM_DELETE_WINDOW", _cancel_and_restore)
        sel.bind("<Escape>", _cancel_and_restore)

    def clear_region(self):
        self.cfg["capture_region"] = None
        save_config(self.cfg)
        self.status.set("🗑 截圖區域已清除")

    def _show_ocr_debug(self, img, sz):
        """OCR 讀不到文字時，彈出視窗顯示實際傳入 OCR 的圖，方便確認內容。"""
        from PIL import ImageTk, ImageOps
        self.status.set(f"⚠️ 未偵測到文字（截圖 {sz[0]}×{sz[1]}px）— 顯示 OCR 輸入圖供確認")
        win = tk.Toplevel(self)
        win.title(f"OCR 輸入圖（{sz[0]}×{sz[1]}px）— 若文字清楚可見，請換 easyocr 引擎")
        win.attributes("-topmost", True)
        # 顯示原圖和反轉圖並排
        proc = _preprocess_ocr_img(img)
        inv  = ImageOps.invert(proc.convert("RGB"))
        max_w = 500
        for label, pil_img in [("原圖（送入OCR）", proc), ("反轉圖（fallback）", inv)]:
            w, h = pil_img.size
            scale = min(max_w / w, 200 / h, 1.0)
            disp = pil_img.resize((int(w*scale), int(h*scale)), Image.LANCZOS) if scale < 1 else pil_img
            tk_img = ImageTk.PhotoImage(disp)
            f = ttk.Frame(win); f.pack(fill="x", padx=6, pady=2)
            ttk.Label(f, text=label, font=("",9,"bold")).pack(anchor="w")
            lbl = tk.Label(f, image=tk_img); lbl.image = tk_img; lbl.pack()
        ttk.Button(win, text="關閉", command=win.destroy).pack(pady=6)

    def _preview_screenshot(self):
        r = self.cfg.get("capture_region")
        if not r:
            self.status.set(f"⚠️ 尚未設定截圖區域，請先按 {self.cfg.get('global_hotkey','ctrl+alt+q').upper()} 選取")
            return
        # 先隱藏視窗再截圖，350ms 後執行
        self.withdraw()
        self.after(350, lambda: self._preview_screenshot_do(r))

    def _preview_screenshot_do(self, r):
        try:
            from PIL import ImageTk
            full = ImageGrab.grab(all_screens=True)
            scr_w = self.winfo_screenwidth()
            scr_h = self.winfo_screenheight()
            iw, ih = full.size
            sx = iw / scr_w if scr_w > 0 else 1.0
            sy = ih / scr_h if scr_h > 0 else 1.0
            bbox = (int(r[0]*sx), int(r[1]*sy), int(r[2]*sx), int(r[3]*sy))
            img = full.crop(bbox)
            self.deiconify()
            w, h = img.size
            # 縮放：最大 600px
            scale = min(600/w, 400/h, 1.0)
            if scale < 1.0:
                img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            win = tk.Toplevel(self)
            win.title(f"截圖預覽  {r[0]},{r[1]} – {r[2]},{r[3]}  ({w}×{h}px)")
            win.attributes("-topmost", True)
            lbl = tk.Label(win, image=tk_img)
            lbl.image = tk_img   # 防止 GC 回收
            lbl.pack(padx=4, pady=4)
            ttk.Button(win, text="關閉", command=win.destroy).pack(pady=4)
            self.status.set(f"🖼 預覽截圖 {w}×{h}px")
        except Exception as e:
            self.deiconify()
            self.status.set(f"❌ 預覽失敗：{e}")

    def _region_text(self):
        r = self.cfg.get("capture_region")
        if r:
            return f"區域：{r[0]},{r[1]}–{r[2]},{r[3]}"
        return "區域：全螢幕"

    def _get_dpi_scale(self) -> float:
        """回傳 Windows DPI 縮放倍率（125% → 1.25）"""
        try:
            import ctypes
            hwnd = int(self.winfo_id())
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
            if dpi > 0:
                return dpi / 96.0
        except Exception:
            pass
        try:
            return self.winfo_fpixels('1i') / 96.0
        except Exception:
            return 1.0

    def do_capture(self):
        if self._working:
            self.deiconify(); return
        if not self.ocr_ready:
            self.deiconify()
            self.status.set("⚠️ OCR 尚未載入完成（或載入失敗），請稍候"); return
        # Read screen size on main thread; window may already be hidden by select_region
        scr_w = self.winfo_screenwidth()
        scr_h = self.winfo_screenheight()
        self.withdraw()
        self.after(350, lambda: threading.Thread(
            target=self._capture_worker, args=(scr_w, scr_h), daemon=True).start())

    def _capture_worker(self, scr_w: int = 0, scr_h: int = 0):
        self._working=True
        try:
            r=self.cfg.get("capture_region")
            # all_screens=True 支援多螢幕；比較 PIL 圖尺寸與 tkinter 螢幕尺寸自動校正縮放
            full = ImageGrab.grab(all_screens=True)
            iw, ih = full.size
            if scr_w > 0 and scr_h > 0:
                sx, sy = iw / scr_w, ih / scr_h
            else:
                sx, sy = 1.0, 1.0
            bbox = (int(r[0]*sx), int(r[1]*sy), int(r[2]*sx), int(r[3]*sy))
            img = full.crop(bbox)
            self.after(0, self.deiconify)
            if img.size[0] < 4 or img.size[1] < 4:
                self.after(0, lambda: self.status.set(
                    f"⚠️ 截圖區域太小或超出螢幕範圍（bbox={bbox}）"))
                return
            self.after(0,lambda: self.status.set("🔍 OCR 辨識中..."))
            jp=run_ocr(img,self.cfg)
            if not jp:
                sz=img.size
                _img_ref = img   # 閉包保留
                self.after(0, lambda: self._show_ocr_debug(_img_ref, sz))
                return
            self._do_translate(jp)
        except Exception as e:
            self.after(0, self.deiconify)
            self._err(str(e))
        finally: self._working=False

    # ── Textractor ───────────────────────────────────────────
    def _set_tx_btn_text(self, active: bool):
        hk = self.cfg.get("clip_hotkey", "ctrl+alt+t").upper()
        self.tx_btn.set(f"⏹ 停止監聽 ({hk})" if active else f"▶ 開始監聽 ({hk})")

    def _set_tx_hint_text(self, active: bool):
        if active:
            self._tx_hint.set("← 監聽中｜ESC 取消")
        else:
            self._tx_hint.set("← Extensions > Copy to Clipboard")

    def toggle_tx(self): (self._stop_tx if self._clip_polling else self._start_tx)()
    def _start_tx(self):
        self._clip_polling=True; self._last_clip=self._clip()
        self.tx_st.set("🟢 監聽中...")
        self._set_tx_btn_text(active=True)
        self._set_tx_hint_text(active=True)
        # 註冊全域 ESC 熱鍵：監聽進行中才生效，停止時解除
        try:
            self._esc_hotkey = kb.add_hotkey(
                "esc", lambda: self.after(0, self._stop_tx))
        except Exception:
            self._esc_hotkey = None
        self.status.set("🔗 Textractor 模式｜等待剪貼簿...（ESC 或 Ctrl+Alt+T 停止）")
        self._poll()
    def _stop_tx(self):
        self._clip_polling=False
        if self._tx_debounce_id:
            self.after_cancel(self._tx_debounce_id); self._tx_debounce_id=None
        self._tx_pending=""
        if getattr(self, "_esc_hotkey", None) is not None:
            try: kb.remove_hotkey(self._esc_hotkey)
            except Exception: pass
            self._esc_hotkey = None
        self.tx_st.set("⏸ 已停止")
        self._set_tx_btn_text(active=False)
        self._set_tx_hint_text(active=False)
        self.status.set("✅ Textractor 模式已停止")
    def _poll(self):
        if not self._clip_polling: return
        try:
            t=self._clip()
            if t and t!=self._last_clip:
                self._last_clip=t
                if self._should_tx(t):
                    # 去抖動：Textractor 會逐步寫入剪貼簿，等穩定後再翻譯
                    self._tx_pending=t
                    if self._tx_debounce_id:
                        self.after_cancel(self._tx_debounce_id)
                    self._tx_debounce_id=self.after(800, self._tx_fire)
        except Exception: pass
        self.after(200,self._poll)
    def _tx_fire(self):
        self._tx_debounce_id=None
        t=self._tx_pending
        if t and self._clip_polling:
            # 再讀一次剪貼簿，確認已穩定
            cur=self._clip()
            if cur and cur!=t:
                # 還在變動，再等一輪
                self._tx_pending=cur; self._last_clip=cur
                self._tx_debounce_id=self.after(600, self._tx_fire)
                return
            threading.Thread(target=self._do_translate,args=(t,),daemon=True).start()
    def _clip(self):
        try: return self.clipboard_get()
        except: return ""
    def _should_tx(self,t):
        t=t.strip()
        if len(t)<self.cfg.get("textractor_min_length",3): return False
        if self.cfg.get("textractor_filter_english",True) and not has_cjk(t): return False
        return True

    # ── 翻譯核心 ─────────────────────────────────────────────
    def _do_translate(self,src:str):
        self._set(self.orig_text,src); self._set(self.trans_text,"翻譯中...")
        self.after(0,lambda: self.anki_status.set(""))
        chain = "→".join(p.upper() for p in (self.cfg.get("api_priority") or [self.cfg.get("api_provider","groq")]))
        self.after(0,lambda: self.status.set(f"🌐 {chain} 翻譯中..."))
        try:
            result, used_p = translate(src,self.cfg)
            self._last_orig=src; self._last_trans=result
            self._set(self.trans_text,result)
            ts=time.strftime("%H:%M:%S")
            up = used_p.upper()
            self.after(0,lambda: self.status.set(f"✅ {ts}｜{up}"))
            if self._clip_polling:
                self.after(0,lambda: self.tx_st.set(f"🟢 監聽中｜{ts}"))
            # 存入歷史
            reading = extract_reading(src) if self.cfg.get("ocr_language","ja")=="ja" else ""
            add_entry(src, result, reading)
            self.after(0, self._refresh_history)
        except Exception as e: self._err(str(e))

    # ── Anki 匯出 ────────────────────────────────────────────
    def add_sentence(self):
        orig=self._last_orig.strip(); trans=self._last_trans.strip()
        if not orig or not trans or trans.startswith("❌"):
            self.anki_status.set("⚠️ 請先翻譯"); return
        SentenceDialog(self, orig, trans, self.cfg,
                       on_done=lambda msg: self.anki_status.set(msg))

    def add_cloze(self):
        orig=self._last_orig.strip(); trans=self._last_trans.strip()
        if not orig or not trans or trans.startswith("❌"):
            self.anki_status.set("⚠️ 請先翻譯"); return
        ex_ja, _ = extract_example_sentence(trans)
        # 優先用 AI 例句；若 AI 例句與原文相同或為空則 fallback 用原文
        sentence = ex_ja if (ex_ja and ex_ja.strip() != orig.strip()) else orig
        # 單字 fallback：若例句跟原文相同且原文很短，
        # 嘗試從完整 AI 回覆中找一個含原文的較長日文句子
        if sentence == orig and len(orig) <= 5:
            for line in trans.splitlines():
                line = line.strip()
                if orig in line and len(line) > len(orig) + 3 and (JP_PAT.search(line) or KO_PAT.search(line)):
                    cleaned = re.sub(r'^(?:日文|原文|韓文|[Jj][Aa]|[Kk][Oo])：\s*', '', line)
                    if len(cleaned) > len(orig) + 2:
                        sentence = cleaned
                        break
        ClozeDialog(self, sentence, orig, trans, self.cfg,
                    on_done=lambda msg: self.anki_status.set(msg))

    # ── 歷史側欄 ─────────────────────────────────────────────
    def _refresh_history(self):
        kw=self.srch_var.get().strip()
        entries=search_entries(kw,50) if kw else get_entries(50)
        self._hist_entries=entries
        self.hist_list.delete(0,"end")
        for e in entries:
            # 顯示格式：時間戳 + 原文摘要
            ts   = e.get("ts","")[-8:]   # 只顯示時間部分
            orig = e.get("original","")
            preview = orig[:18]+"…" if len(orig)>18 else orig
            self.hist_list.insert("end", f"{ts}  {preview}")

    def _on_hist_select(self,_=None):
        sel=self.hist_list.curselection()
        if not sel: return
        # 只在單選時載入文字框
        if len(sel)==1:
            e=self._hist_entries[sel[0]]
            self._last_orig  = e.get("original","")
            self._last_trans = e.get("translation","")
            self._set(self.orig_text,  self._last_orig)
            self._set(self.trans_text, self._last_trans)
            self.anki_status.set("（從歷史載入）")
        else:
            self.anki_status.set(f"已選取 {len(sel)} 筆")

    def _clear_hist(self):
        clear_history()
        self._refresh_history()

    def _bulk_add_sentence(self):
        sel=self.hist_list.curselection()
        if not sel: self.hist_anki_status.set("⚠️ 請先選取項目"); return
        entries=[self._hist_entries[i] for i in sel]
        self.hist_anki_status.set(f"⏳ 加入 {len(entries)} 筆...")
        def _w():
            ok_cnt=fail_cnt=0
            for e in entries:
                orig=e.get("original","").strip(); trans=e.get("translation","").strip()
                if not orig or not trans: fail_cnt+=1; continue
                try:
                    ex_ja,_=extract_example_sentence(trans)
                    front=ex_ja if ex_ja else orig
                    reading=extract_reading(front) if self.cfg.get("ocr_language","ja")=="ja" else ""
                    # 卡背使用完整 AI 回覆（老師解說：含譯文、例句、重點單字、用詞備注）
                    # Anki 欄位是 HTML，換行需轉成 <br> 才會正常顯示
                    trans_html = trans.replace("\n", "<br>")
                    ok,_=add_sentence_note(orig,front,trans_html,reading,"",self.cfg)
                    if ok: ok_cnt+=1
                    else: fail_cnt+=1
                except: fail_cnt+=1
            self.after(0,lambda: self.hist_anki_status.set(
                f"✅ {ok_cnt} 筆"+(f"，{fail_cnt} 失敗" if fail_cnt else "")))
        threading.Thread(target=_w,daemon=True).start()

    # ── 工具方法 ─────────────────────────────────────────────
    def _set(self, widget: tk.Text, text: str):
        """安全地更新 tk.Text 內容（在主執行緒呼叫）"""
        def _do():
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
            widget.configure(state="disabled")
        self.after(0, _do)

    def _err(self, msg: str):
        self.after(0, lambda: self.status.set(f"❌ {msg}"))

    # ── 設定視窗 ─────────────────────────────────────────────
    def open_settings(self):
        def _on_save(new_cfg):
            self.cfg.update(new_cfg)
            save_config(self.cfg)
            self._lang_chg()
            self._register_global_hotkey()
            self._refresh_hotkey_labels()
        GeneralSettingsWindow(self, self.cfg, _on_save)

    def open_anki_settings(self):
        def _on_save(new_cfg):
            self.cfg.update(new_cfg)
            save_config(self.cfg)
        AnkiSettingsWindow(self, self.cfg, _on_save)

    # ── 全域熱鍵 ─────────────────────────────────────────────
    def _register_global_hotkey(self):
        """註冊/重新註冊全域熱鍵。熱鍵 callback 在 keyboard thread，需 marshal 回 Tk"""
        if self._current_hotkey is not None:
            try: kb.remove_hotkey(self._current_hotkey)
            except Exception: pass
            self._current_hotkey = None
        if self._current_clip_hotkey is not None:
            try: kb.remove_hotkey(self._current_clip_hotkey)
            except Exception: pass
            self._current_clip_hotkey = None
        hk = self.cfg.get("global_hotkey", "ctrl+alt+q").strip().lower()
        if hk:
            try:
                self._current_hotkey = kb.add_hotkey(
                    hk, lambda: self.after(0, self.select_region))
            except Exception as e:
                self.after(0, lambda: self.status.set(f"⚠️ 熱鍵註冊失敗 {hk}: {e}"))
        chk = self.cfg.get("clip_hotkey", "ctrl+alt+t").strip().lower()
        if chk:
            try:
                self._current_clip_hotkey = kb.add_hotkey(
                    chk, lambda: self.after(0, self.toggle_tx))
            except Exception as e:
                self.after(0, lambda: self.status.set(f"⚠️ 剪貼簿熱鍵註冊失敗 {chk}: {e}"))

    def _refresh_hotkey_labels(self):
        """熱鍵變更後同步更新 UI 文字"""
        hk = self.cfg.get("global_hotkey", "ctrl+alt+q").upper()
        if hasattr(self, "_region_btn"):
            self._region_btn.configure(text=f"✂️ 選取區域並翻譯 ({hk})")
        # 監聽按鈕文字也含熱鍵，需同步刷新
        if hasattr(self, "tx_btn"):
            self._set_tx_btn_text(active=self._clip_polling)
        if self.ocr_ready:
            eng = self.cfg.get("ocr_engine", "manga-ocr")
            self.status.set(f"✅ 就緒｜{eng}｜{hk} 截圖翻譯")

    # ── 系統匣 ───────────────────────────────────────────────
    def _start_tray(self):
        img = _make_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem("顯示視窗", self._tray_show, default=True),
            pystray.MenuItem("隱藏視窗", self._tray_hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("截圖翻譯", lambda: self.after(0, self.select_region)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._tray_quit),
        )
        self._tray_icon = pystray.Icon("game_translator", img, "遊戲即時翻譯", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _tray_show(self, *_):
        def _do():
            self.deiconify(); self.lift()
            self.attributes("-topmost", True)
        self.after(0, _do)

    def _tray_hide(self, *_):
        self.after(0, self.withdraw)

    def _tray_quit(self, *_):
        self._quitting = True
        if self._tray_icon is not None:
            try: self._tray_icon.stop()
            except Exception: pass
        if self._current_hotkey is not None:
            try: kb.remove_hotkey(self._current_hotkey)
            except Exception: pass
        if self._current_clip_hotkey is not None:
            try: kb.remove_hotkey(self._current_clip_hotkey)
            except Exception: pass
        if self._esc_hotkey is not None:
            try: kb.remove_hotkey(self._esc_hotkey)
            except Exception: pass
        self.after(0, self.destroy)

    # ── 關閉按鈕 ─────────────────────────────────────────────
    def _on_close_window(self):
        """右上 X 被按下：詢問或直接隱藏"""
        if self._quitting:
            return
        if self.cfg.get("close_ask", True):
            ans = messagebox.askyesnocancel(
                "關閉視窗",
                "要把程式隱藏到系統匣持續運作嗎？\n\n"
                "【是】隱藏到背景（推薦）\n"
                "【否】完全退出\n"
                "【取消】不關閉",
                parent=self)
            if ans is None:
                return
            if ans:
                self.withdraw()
            else:
                self._tray_quit()
        else:
            if self.cfg.get("background_mode", True):
                self.withdraw()
            else:
                self._tray_quit()


if __name__ == "__main__":
    start_minimized = "--minimized" in sys.argv
    app = MainApp()
    if start_minimized:
        app.after(100, app.withdraw)
    app.mainloop()