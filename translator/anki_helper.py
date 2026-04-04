"""
anki_helper.py
AnkiConnect / 讀音抽取 / Forvo 音檔 / 一般卡 / 挖空卡（Cloze）
"""

import json
import urllib.request
import urllib.error
import urllib.parse
import base64
import hashlib


# ── AnkiConnect 基礎 ─────────────────────────────────────────
def anki_req(action: str, params: dict, url: str) -> dict:
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def anki_get_decks(url: str) -> list:
    return anki_req("deckNames", {}, url).get("result", [])

def anki_get_models(url: str) -> list:
    return anki_req("modelNames", {}, url).get("result", [])

def anki_get_fields(model: str, url: str) -> list:
    return anki_req("modelFieldNames", {"modelName": model}, url).get("result", [])

def anki_version(url: str) -> int:
    return anki_req("version", {}, url).get("result", 0)

def anki_ensure_deck(deck: str, url: str):
    if deck not in anki_req("deckNames", {}, url).get("result", []):
        anki_req("createDeck", {"deck": deck}, url)


# ── 讀音抽取（漢字 → 平假名）────────────────────────────────
def extract_reading(text: str) -> str:
    """漢字 → 平假名。優先 pykakasi，fallback fugashi，最後回傳原文。"""
    text = text.strip()
    if not text:
        return ""
    try:
        import pykakasi
        kks    = pykakasi.kakasi()
        result = kks.convert(text)
        return "".join(item["hira"] or item["orig"] for item in result).strip()
    except ImportError:
        pass
    try:
        import fugashi
        tagger = fugashi.Tagger()
        parts  = []
        for word in tagger(text):
            feat = word.feature
            try:
                kana = feat[7] if len(feat) > 7 and feat[7] != "*" else word.surface
            except Exception:
                kana = word.surface
            parts.append(kana)
        return _k2h("".join(parts)).strip()
    except ImportError:
        pass
    return text

def _k2h(text: str) -> str:
    return "".join(
        chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c
        for c in text
    )


# ── Forvo API ────────────────────────────────────────────────
LANG_CODE = {"ja": "ja", "ko": "ko", "ja+ko": "ja"}

def fetch_forvo_audio(word: str, lang: str, api_key: str) -> bytes:
    """
    Forvo API 取得真人發音 mp3。
    - 優先用讀音（平假名）搜尋，更精確。
    - 找不到則 raise RuntimeError。
    """
    lang_code = LANG_CODE.get(lang, "ja")
    word_enc  = urllib.parse.quote(word.strip())
    url = (
        f"https://apifree.forvo.com"
        f"/action/word-pronunciations/format/json"
        f"/word/{word_enc}/language/{lang_code}"
        f"/order/rate-desc/limit/1/key/{api_key}/"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "AnkiGameTranslator/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())

    items = data.get("items", [])
    if not items:
        raise RuntimeError(f"Forvo 找不到「{word}」的發音")

    audio_url = items[0].get("pathmp3") or items[0].get("pathogg")
    if not audio_url:
        raise RuntimeError("Forvo 回傳資料中沒有音訊 URL")

    req2 = urllib.request.Request(audio_url, headers={"User-Agent": "AnkiGameTranslator/1.0"})
    with urllib.request.urlopen(req2, timeout=20) as r:
        return r.read()

def test_forvo_api(api_key: str) -> str:
    try:
        fetch_forvo_audio("日本語", "ja", api_key)
        return "✅ Forvo API 連線成功！"
    except RuntimeError as e:
        return f"⚠️ API 可連線但：{e}"
    except urllib.error.HTTPError as e:
        return f"❌ HTTP {e.code}（API Key 可能無效）" if e.code == 401 else f"❌ HTTP {e.code}"
    except Exception as e:
        return f"❌ 連線失敗：{e}"

def get_forvo_tag(search_word: str, lang: str, api_key: str, anki_url: str) -> str:
    """取得 Forvo 音訊並存入 Anki，回傳 [sound:xxx.mp3]"""
    audio = fetch_forvo_audio(search_word, lang, api_key)
    h     = hashlib.md5(search_word.encode()).hexdigest()[:8]
    fname = f"forvo_{h}.mp3"
    anki_req("storeMediaFile", {
        "filename": fname,
        "data":     base64.b64encode(audio).decode(),
    }, anki_url)
    return f"[sound:{fname}]"


# ── 一般筆記（句子卡）────────────────────────────────────────
def add_sentence_note(orig: str, example: str, trans: str, reading: str,
                      audio_tag: str, cfg: dict) -> tuple:
    """
    新增句子卡。
    欄位對應（cfg["anki_fields"]）：
      original     → OCR 原始文字（備存）
      example      → AI 例句（卡片正面）
      reading      → 平假名讀音
      translation  → 老師完整解說（卡片背面）
      audio        → [sound:xxx.mp3]
      pitch_accent → 留空（AJT 自動填）
    回傳 (ok: bool, msg: str)
    """
    return _add_note(
        deck  = cfg["anki_deck"],
        model = cfg["anki_model"],
        fm    = cfg.get("anki_fields", {}),
        tags  = cfg.get("anki_tags", "遊戲翻譯").split(),
        url   = cfg["anki_url"],
        data  = {
            "original":    orig,
            "example":     example,
            "reading":     reading,
            "translation": trans,
            "audio":       audio_tag,
        },
    )


# ── 挖空筆記（Cloze 卡）─────────────────────────────────────
def build_cloze_text(sentence: str, word: str, hint: str) -> str:
    """
    將 sentence 中的 word 替換為 Anki Cloze 格式。
    例：
      sentence = "今日は天気がいい"
      word     = "天気"
      hint     = "好天氣"  （可為翻譯或讀音）
      → "今日は{{c1::天気::好天氣}}がいい"

    若 hint 為空，格式為 {{c1::天気}}。
    若句中找不到 word，則把 word 單獨做成 cloze（例句放 Extra）。
    """
    cloze = f"{{{{c1::{word}::{hint}}}}}" if hint else f"{{{{c1::{word}}}}}"

    if word in sentence:
        # 只替換第一個出現位置
        return sentence.replace(word, cloze, 1)
    else:
        # 找不到時，回傳「word 單獨 cloze」，例句整句放 Extra
        return cloze

def add_cloze_note(sentence: str, translation: str,
                   word: str, word_reading: str,
                   audio_tag: str, cfg: dict,
                   word_hint: str = "") -> tuple:
    """
    新增挖空卡。
    使用 cfg["anki_cloze_*"] 的欄位設定（與一般卡獨立）。

    Cloze 筆記類型欄位（預設）：
      Text   → 含 {{c1::word::hint}} 的日文句子（hint 優先用簡要翻譯）
      Extra  → 繁體中文翻譯（背面提示）
      Audio  → [sound:xxx.mp3]
    """
    hint = word_hint if word_hint else word_reading
    cloze_text = build_cloze_text(sentence, word, hint)
    fm   = cfg.get("anki_cloze_fields", {})
    deck = cfg.get("anki_cloze_deck", cfg.get("anki_deck", "遊戲翻譯（挖空）"))
    model= cfg.get("anki_cloze_model", "Cloze")
    tags = cfg.get("anki_tags", "遊戲翻譯").split() + ["cloze"]
    url  = cfg["anki_url"]

    return _add_note(
        deck  = deck,
        model = model,
        fm    = fm,
        tags  = tags,
        url   = url,
        data  = {
            "text":        cloze_text,
            "extra":       translation,
            "audio":       audio_tag,
            "sentence":    sentence,          # 原句（Extra 也可放）
        },
    )


# ── 共用新增邏輯 ─────────────────────────────────────────────
def _add_note(deck: str, model: str, fm: dict,
              tags: list, url: str, data: dict) -> tuple:
    anki_ensure_deck(deck, url)

    fields: dict = {}
    for role, value in data.items():
        fname = fm.get(role, "").strip()
        if fname and value:
            fields[fname] = value

    # pitch_accent 留空讓 AJT 填
    pa = fm.get("pitch_accent", "").strip()
    if pa:
        fields[pa] = ""

    note = {
        "deckName":  deck,
        "modelName": model,
        "fields":    fields,
        "options":   {"allowDuplicate": False, "duplicateScope": "deck"},
        "tags":      [t for t in tags if t],
    }
    resp = anki_req("addNote", {"note": note}, url)
    if resp.get("error"):
        return False, f"Anki 錯誤：{resp['error']}"
    return True, f"✅ 已加入「{deck}」（ID: {resp['result']}）"
