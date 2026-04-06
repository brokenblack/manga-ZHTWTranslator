"""
anki_settings.py
Anki 設定視窗：連線 / 句子卡欄位 / 挖空卡欄位 / Forvo 音訊
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from anki_helper import (
    anki_version, anki_get_decks, anki_get_models,
    anki_get_fields, test_forvo_api, fetch_forvo_audio,
)

# ── 欄位角色定義 ──────────────────────────────────────────────
SENTENCE_ROLES = [
    ("original",     "原句（OCR）",        "遊戲截圖的原始文字（備存用）"),
    ("example",      "例句（正面）",        "AI 從原句抽出的代表性例句，作為卡片正面"),
    ("reading",      "讀音（平假名）",      "自動抽取讀音，供 Forvo addon 消歧"),
    ("translation",  "老師解說（背面）",    "含譯文、重點單字、用詞備注的完整解說"),
    ("audio",        "音訊",               "[sound:xxx.mp3]（Forvo 音檔）"),
    ("pitch_accent", "Pitch Accent",      "AJT addon 自動填入，留空即可"),
]

CLOZE_ROLES = [
    ("text",         "挖空文字（Text）",   "{{c1::單字::讀音}} 格式，例：今日は{{c1::天気::てんき}}がいい"),
    ("extra",        "提示（Extra）",      "繁體中文翻譯（卡片背面提示）"),
    ("audio",        "音訊",              "[sound:xxx.mp3]（單字 Forvo 音檔）"),
    ("sentence",     "原句（選用）",       "完整日文例句（可放在 Extra 或獨立欄位）"),
    ("pitch_accent", "Pitch Accent",      "AJT addon 自動填入，留空即可"),
]


class AnkiSettingsWindow(tk.Toplevel):
    def __init__(self, parent, cfg: dict, on_save):
        super().__init__(parent)
        self.cfg     = cfg.copy()
        self.on_save = on_save
        self.title("Anki 設定")
        self.geometry("580x560")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()

        self._decks:  list = []
        self._models: list = []
        self._fields: list = []

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_conn_tab(nb)
        self._build_sentence_tab(nb)
        self._build_cloze_tab(nb)
        self._build_forvo_tab(nb)

        bar = ttk.Frame(self); bar.pack(pady=8)
        ttk.Button(bar, text="儲存", command=self._save).pack(side="left", padx=6)
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="left", padx=6)

        self.after(300, self._auto_connect)

    # ── Tab 1：連線 ─────────────────────────────────────────
    def _build_conn_tab(self, nb):
        f = ttk.Frame(nb, padding=14); nb.add(f, text="🔌 連線")
        P = {"padx": 8, "pady": 5}

        ttk.Label(f, text=(
            "需要安裝的 Anki addon：\n"
            "  • AnkiConnect        代碼：2055492159\n"
            "  • AJT Pitch Accent   代碼：148002038\n"
            "  • Forvo Downloader   代碼：1784714388（選用，可手動補音）"
        ), foreground="gray30", justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(f, text="AnkiConnect URL").grid(row=1, column=0, sticky="w", **P)
        self.url_var = tk.StringVar(value=self.cfg.get("anki_url", "http://localhost:8765"))
        ttk.Entry(f, textvariable=self.url_var, width=30).grid(row=1, column=1, sticky="w", **P)
        self.conn_btn = ttk.Button(f, text="測試連線", command=self._test_conn)
        self.conn_btn.grid(row=1, column=2, **P)

        self.conn_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.conn_status, foreground="gray40").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=8)

        ttk.Separator(f).grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(f, text="Tags（空格分隔）").grid(row=4, column=0, sticky="w", **P)
        self.tags_var = tk.StringVar(value=self.cfg.get("anki_tags", "遊戲翻譯"))
        ttk.Entry(f, textvariable=self.tags_var, width=30).grid(row=4, column=1, sticky="w", **P)

    def _test_conn(self):
        url = self.url_var.get().strip()
        self.conn_status.set("⏳ 連線中...")
        self.conn_btn.configure(state="disabled")
        def _w():
            try:
                ver    = anki_version(url)
                decks  = anki_get_decks(url)
                models = anki_get_models(url)
                self._decks  = sorted(decks)
                self._models = sorted(models)
                self.after(0, lambda: self._on_connected(ver))
            except Exception as e:
                self.after(0, lambda: self._on_fail(str(e)))
        threading.Thread(target=_w, daemon=True).start()

    def _on_connected(self, ver):
        self.conn_status.set(f"✅ v{ver}｜{len(self._decks)} 個牌組")
        self.conn_btn.configure(state="normal")
        for cb in [self.sent_deck_cb, self.sent_model_cb,
                   self.cloze_deck_cb, self.cloze_model_cb]:
            cb.configure(values=self._decks if "deck" in str(cb) else self._models)
        self.sent_deck_cb.configure(values=self._decks)
        self.sent_model_cb.configure(values=self._models)
        self.cloze_deck_cb.configure(values=self._decks)
        self.cloze_model_cb.configure(values=self._models)

    def _on_fail(self, msg):
        self.conn_status.set(f"❌ {msg[:60]}")
        self.conn_btn.configure(state="normal")

    def _auto_connect(self):
        self._test_conn()

    # ── Tab 2：句子卡 ────────────────────────────────────────
    def _build_sentence_tab(self, nb):
        f = ttk.Frame(nb, padding=14); nb.add(f, text="📝 句子卡")
        P = {"padx": 8, "pady": 5}

        ttk.Label(f, text="牌組").grid(row=0, column=0, sticky="w", **P)
        self.sent_deck_var = tk.StringVar(value=self.cfg.get("anki_deck", "遊戲翻譯"))
        self.sent_deck_cb  = ttk.Combobox(f, textvariable=self.sent_deck_var,
                                           values=self._decks, width=22)
        self.sent_deck_cb.grid(row=0, column=1, sticky="w", **P)
        ttk.Button(f, text="↻", width=3,
                   command=self._auto_connect).grid(row=0, column=2, **P)

        ttk.Label(f, text="筆記類型").grid(row=1, column=0, sticky="w", **P)
        self.sent_model_var = tk.StringVar(value=self.cfg.get("anki_model", "Basic"))
        self.sent_model_cb  = ttk.Combobox(f, textvariable=self.sent_model_var,
                                            values=self._models, state="readonly", width=22)
        self.sent_model_cb.grid(row=1, column=1, sticky="w", **P)
        self.sent_model_cb.bind("<<ComboboxSelected>>", self._load_sent_fields)

        ttk.Separator(f).grid(row=2, column=0, columnspan=3, sticky="ew", pady=8)

        # 欄位對應表頭
        for col, txt in enumerate(["內容", "Anki 欄位名稱", "說明"]):
            ttk.Label(f, text=txt, font=("", 9, "bold")).grid(
                row=3, column=col, sticky="w", padx=8)
        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=3)

        fm = self.cfg.get("anki_fields", {})
        self.sent_field_vars: dict[str, tk.StringVar] = {}
        self.sent_field_cbs:  dict[str, ttk.Combobox] = {}
        _sent_defaults = {
            "original":    "OriginalText",
            "example":     "Front",
            "reading":     "Reading",
            "translation": "Back",
            "audio":       "Audio",
            "pitch_accent":"VocabPitchPattern",
        }
        for i, (role, label, desc) in enumerate(SENTENCE_ROLES, start=5):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar(value=fm.get(role, _sent_defaults.get(role, "")))
            cb  = ttk.Combobox(f, textvariable=var, values=self._fields, width=18)
            cb.grid(row=i, column=1, sticky="w", padx=8, pady=3)
            ttk.Label(f, text=desc, foreground="gray", wraplength=150).grid(
                row=i, column=2, sticky="w", padx=4)
            self.sent_field_vars[role] = var
            self.sent_field_cbs[role]  = cb

        ttk.Label(f, text="💡 欄位名稱可手動輸入，留空表示不使用",
                  foreground="gray40").grid(
            row=len(SENTENCE_ROLES)+5, column=0, columnspan=3,
            sticky="w", padx=8, pady=6)

        ttk.Separator(f).grid(row=len(SENTENCE_ROLES)+6, column=0,
                              columnspan=3, sticky="ew", pady=4)
        self.trigger_pitch_var = tk.BooleanVar(
            value=self.cfg.get("anki_trigger_pitch", True))
        ttk.Checkbutton(
            f, text="建立卡片後自動觸發 AJT Pitch Accent（會短暫開啟編輯視窗）",
            variable=self.trigger_pitch_var).grid(
            row=len(SENTENCE_ROLES)+7, column=0, columnspan=3,
            sticky="w", padx=8, pady=4)
        ttk.Label(f, text="AJT 只在編輯器載入時才填 pitch，需藉由開啟編輯視窗觸發",
                  foreground="gray50", wraplength=480).grid(
            row=len(SENTENCE_ROLES)+8, column=0, columnspan=3,
            sticky="w", padx=26, pady=(0, 4))

    def _load_sent_fields(self, _=None):
        model = self.sent_model_var.get()
        url   = self.url_var.get()
        def _w():
            try:
                fields = anki_get_fields(model, url)
                opts   = ["（不使用）"] + fields
                self.after(0, lambda: [
                    cb.configure(values=opts)
                    for cb in self.sent_field_cbs.values()
                ])
            except Exception:
                pass
        threading.Thread(target=_w, daemon=True).start()

    # ── Tab 3：挖空卡 ────────────────────────────────────────
    def _build_cloze_tab(self, nb):
        f = ttk.Frame(nb, padding=14); nb.add(f, text="✂️ 挖空卡（Cloze）")
        P = {"padx": 8, "pady": 5}

        ttk.Label(f, text=(
            "挖空卡格式：{{c1::單字::讀音}} 嵌入例句\n"
            "筆記類型請選 Anki 內建的「Cloze」或相容類型。"
        ), foreground="gray40", justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(f, text="牌組").grid(row=1, column=0, sticky="w", **P)
        self.cloze_deck_var = tk.StringVar(
            value=self.cfg.get("anki_cloze_deck", "遊戲翻譯（挖空）"))
        self.cloze_deck_cb  = ttk.Combobox(f, textvariable=self.cloze_deck_var,
                                            values=self._decks, width=22)
        self.cloze_deck_cb.grid(row=1, column=1, sticky="w", **P)

        ttk.Label(f, text="筆記類型").grid(row=2, column=0, sticky="w", **P)
        self.cloze_model_var = tk.StringVar(
            value=self.cfg.get("anki_cloze_model", "Cloze"))
        self.cloze_model_cb  = ttk.Combobox(f, textvariable=self.cloze_model_var,
                                             values=self._models, state="readonly", width=22)
        self.cloze_model_cb.grid(row=2, column=1, sticky="w", **P)
        self.cloze_model_cb.bind("<<ComboboxSelected>>", self._load_cloze_fields)

        ttk.Separator(f).grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)

        for col, txt in enumerate(["內容", "Anki 欄位名稱", "說明"]):
            ttk.Label(f, text=txt, font=("", 9, "bold")).grid(
                row=4, column=col, sticky="w", padx=8)
        ttk.Separator(f).grid(row=5, column=0, columnspan=3, sticky="ew", pady=3)

        cfm = self.cfg.get("anki_cloze_fields", {})
        self.cloze_field_vars: dict[str, tk.StringVar] = {}
        self.cloze_field_cbs:  dict[str, ttk.Combobox] = {}
        _cloze_defaults = {
            "text": "Text", "extra": "Extra",
            "audio": "Audio", "sentence": "",
            "pitch_accent": "VocabPitchPattern",
        }
        for i, (role, label, desc) in enumerate(CLOZE_ROLES, start=6):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=3)
            var = tk.StringVar(value=cfm.get(role, _cloze_defaults.get(role, "")))
            cb  = ttk.Combobox(f, textvariable=var, values=self._fields, width=18)
            cb.grid(row=i, column=1, sticky="w", padx=8, pady=3)
            ttk.Label(f, text=desc, foreground="gray", wraplength=160).grid(
                row=i, column=2, sticky="w", padx=4)
            self.cloze_field_vars[role] = var
            self.cloze_field_cbs[role]  = cb

    def _load_cloze_fields(self, _=None):
        model = self.cloze_model_var.get()
        url   = self.url_var.get()
        def _w():
            try:
                fields = anki_get_fields(model, url)
                opts   = ["（不使用）"] + fields
                self.after(0, lambda: [
                    cb.configure(values=opts)
                    for cb in self.cloze_field_cbs.values()
                ])
            except Exception:
                pass
        threading.Thread(target=_w, daemon=True).start()

    # ── Tab 4：Forvo ─────────────────────────────────────────
    def _build_forvo_tab(self, nb):
        f = ttk.Frame(nb, padding=14); nb.add(f, text="🎙 Forvo")
        P = {"padx": 8, "pady": 5}

        ttk.Label(f, text=(
            "使用 Forvo API 自動下載真人發音。\n"
            "• 申請：https://api.forvo.com/（約 $2/月，有 30 天試用）\n"
            "• 搜尋時優先使用「讀音（平假名）」，同音字更精確。\n"
            "• 若 API 找不到，卡片不含音訊（不使用 TTS fallback）。"
        ), foreground="gray30", justify="left").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(f, text="Forvo API Key").grid(row=1, column=0, sticky="w", **P)
        self.forvo_key = tk.StringVar(value=self.cfg.get("forvo_api_key", ""))
        ttk.Entry(f, textvariable=self.forvo_key, width=34, show="*").grid(
            row=1, column=1, sticky="w", **P)
        ttk.Button(f, text="測試", command=self._test_forvo).grid(
            row=1, column=2, **P)

        ttk.Separator(f).grid(row=2, column=0, columnspan=3, sticky="ew", pady=8)

        ttk.Label(f, text="讀音抽取套件").grid(row=3, column=0, sticky="w", **P)
        ttk.Label(f, text="uv pip install pykakasi",
                  foreground="gray").grid(row=3, column=1, sticky="w", **P)

        ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)

        # 試聽
        ttk.Label(f, text="試聽單字").grid(row=5, column=0, sticky="w", **P)
        self.test_word = tk.StringVar(value="天気")
        ttk.Entry(f, textvariable=self.test_word, width=14).grid(row=5, column=1, sticky="w", **P)
        ttk.Button(f, text="▶ 試聽", command=self._preview).grid(row=5, column=2, **P)
        self.forvo_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.forvo_status, foreground="gray40").grid(
            row=6, column=0, columnspan=3, sticky="w", padx=8, pady=4)

    def _test_forvo(self):
        key = self.forvo_key.get().strip()
        if not key:
            messagebox.showwarning("Forvo", "請先填入 API Key", parent=self)
            return
        self.forvo_status.set("⏳ 測試中...")
        def _w():
            msg = test_forvo_api(key)
            self.after(0, lambda: self.forvo_status.set(msg))
        threading.Thread(target=_w, daemon=True).start()

    def _preview(self):
        word = self.test_word.get().strip()
        key  = self.forvo_key.get().strip()
        if not word or not key:
            self.forvo_status.set("⚠️ 請填入單字和 API Key")
            return
        self.forvo_status.set("⏳ 下載中...")
        def _w():
            try:
                import tempfile, os
                data = fetch_forvo_audio(word, "ja", key)
                tmp  = tempfile.mktemp(suffix=".mp3")
                with open(tmp, "wb") as fp: fp.write(data)
                os.startfile(tmp)
                self.after(0, lambda: self.forvo_status.set(f"✅「{word}」播放中"))
            except Exception as e:
                self.after(0, lambda: self.forvo_status.set(f"❌ {e}"))
        threading.Thread(target=_w, daemon=True).start()

    # ── 儲存 ────────────────────────────────────────────────
    def _save(self):
        def _fm(vars_dict):
            fm = {}
            for role, var in vars_dict.items():
                v = var.get().strip()
                fm[role] = "" if v in ("", "（不使用）") else v
            return fm

        self.cfg.update({
            "anki_url":          self.url_var.get().strip(),
            "anki_tags":         self.tags_var.get().strip(),
            # 句子卡
            "anki_deck":         self.sent_deck_var.get().strip(),
            "anki_model":        self.sent_model_var.get().strip(),
            "anki_fields":       _fm(self.sent_field_vars),
            # 挖空卡
            "anki_cloze_deck":   self.cloze_deck_var.get().strip(),
            "anki_cloze_model":  self.cloze_model_var.get().strip(),
            "anki_cloze_fields": _fm(self.cloze_field_vars),
            # Forvo
            "forvo_api_key":     self.forvo_key.get().strip(),
            # AJT Pitch 觸發
            "anki_trigger_pitch": self.trigger_pitch_var.get(),
        })
        self.on_save(self.cfg)
        self.destroy()
