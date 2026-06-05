"""
build_exe_onefile.py
打包遊戲翻譯工具為 Windows 單一 EXE（--onefile 模式）

策略 vs build_exe.py:
  - --onefile：單一 .exe，分享方便，但每次啟動會解壓到 %TEMP%（5-15 秒延遲）
  - --onedir：資料夾結構，啟動快但要連同 _internal/ 一起發給別人

預估 EXE 約 400-500 MB，打包時間 25-50 分鐘。
首次啟動會比 --onedir 慢 10-30 秒（PyInstaller bootloader 解壓）。
之後啟動稍快（OS 檔案快取），仍比 --onedir 慢一些。

依賴前置條件（必須先在 .venv 安裝）：
  uv pip install pyinstaller pillow numpy keyboard pystray opencc-python-reimplemented \
                 anthropic google-generativeai groq \
                 manga-ocr easyocr pykakasi transformers
  uv pip install torch --index-url https://download.pytorch.org/whl/cpu
"""

import subprocess
import sys
import shutil
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).parent


def run(cmd: list, **kw):
    print("▶", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, **kw)
    if result.returncode != 0:
        print(f"\n❌ 指令失敗（code {result.returncode}）")
        sys.exit(1)
    return result


def ensure_pyinstaller():
    try:
        import PyInstaller
        print(f"✅ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("安裝 PyInstaller...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build():
    ensure_pyinstaller()

    for d in ["build", "dist"]:
        p = HERE / d
        if p.exists():
            shutil.rmtree(p)
            print(f"🗑  清除 {d}/")

    icon_args = []
    if (HERE / "icon.ico").exists():
        icon_args = ["--icon", str(HERE / "icon.ico")]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "翻譯工具",

        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageGrab",
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "numpy",

        "--hidden-import", "anthropic",
        "--hidden-import", "google.generativeai",
        "--hidden-import", "groq",

        "--hidden-import", "keyboard",
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "opencc",

        "--hidden-import", "torch",
        "--hidden-import", "torch.nn",
        "--hidden-import", "torch.utils",
        "--hidden-import", "torch.utils.data",

        "--collect-all", "manga_ocr",
        "--collect-all", "easyocr",
        "--collect-all", "transformers",
        "--collect-all", "tokenizers",
        "--collect-all", "opencc",
        "--collect-data", "pykakasi",
        "--collect-data", "unidic_lite",

        "--exclude-module", "paddleocr",
        "--exclude-module", "paddlepaddle",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--exclude-module", "notebook",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "tensorflow",
        "--exclude-module", "tensorboard",

        *icon_args,
        str(HERE / "translator.py"),
    ]

    print("\n⏳ 開始打包（單檔模式約 25-50 分鐘，請勿中斷）...\n")
    run(cmd, cwd=str(HERE))

    exe = HERE / "dist" / "翻譯工具.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / 1024 / 1024
        print(f"\n✅ 打包完成！")
        print(f"   位置：{exe}")
        print(f"   大小：{size_mb:.1f} MB")
        print(f"\n📌 注意（單檔模式特性）：")
        print(f"   - 首次啟動會比較慢（PyInstaller 解壓到 %TEMP%）")
        print(f"   - config.json / history.json 會儲存在 EXE 同層目錄")
        print(f"   - 把 EXE 移到固定位置再使用，避免設定檔散落")
    else:
        print("\n❌ 找不到輸出 EXE，請查看上方錯誤訊息")


if __name__ == "__main__":
    build()
