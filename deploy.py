import fnmatch
import os
import shutil
import subprocess
import sys

# ============================================================
# 打包后自动清理配置（缩小产物体积）
# ============================================================
# 打包产物目录（Nuitka standalone 默认生成在入口脚本同名目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "main.dist")

# 是否删除 Qt WebEngine 相关文件（约 300MB）
# qfluentwidgets_pro 的图表控件(ChartWidget)已改为延迟加载 WebEngine，
# 主程序未使用图表，删除后不影响程序启动。
# 若日后需要使用图表，将此设为 False 重新打包即可恢复。
REMOVE_WEBENGINE = True

# WebEngine 相关文件（dist 根目录下按名称/通配符匹配）
WEBENGINE_PATTERNS = (
    "qt6webenginecore.dll",
    "QtWebEngineProcess.exe",
    "qtwebengine*.pak",
    "qt6pdf.dll",
    "qt6quick.dll",
    "qt6qml.dll",
    "qt6qmlmodels.dll",
)

# WebEngine 相关路径（相对 dist 目录，文件或目录均可）
WEBENGINE_PATHS = (
    "PySide6/QtWebEngineCore.pyd",
    "PySide6/QtWebEngineWidgets.pyd",
    "PySide6/QtWebEngineChannel.pyd",
    "PySide6/translations/qtwebengine_locales",
)

# 是否删除 scipy（约 70MB）
# scipy 仅被 qfluentwidgets_pro 的 AcrylicLabel(亚克力标签) 在函数内部延迟引用，
# 主程序未使用该控件，删除安全。若打包后运行报 gaussianBlur/scipy 相关错误，
# 说明某处用到了亚克力效果，将此常量改为 False 后重新打包即可恢复。
REMOVE_SCIPY = True

# 翻译文件保留的语言（仅保留中文，其余约 14MB 会被清理）
KEEP_TRANSLATIONS = ("zh_CN", "zh_TW")


def clean_dist(dist_dir):
    """打包成功后清理冗余文件，缩小产物体积"""
    if not os.path.isdir(dist_dir):
        print(f"[clean] 未找到产物目录 {dist_dir}，跳过清理")
        return

    removed = 0

    def _rm_file(path):
        nonlocal removed
        removed += os.path.getsize(path)
        os.remove(path)
        print(f"[clean] 删除文件: {os.path.relpath(path, dist_dir)}")

    def _rm_tree(path, label):
        nonlocal removed
        size = sum(
            os.path.getsize(os.path.join(root, f))
            for root, _, files in os.walk(path)
            for f in files
        )
        removed += size
        shutil.rmtree(path)
        print(f"[clean] 删除目录: {label} ({size / 1024 / 1024:.1f} MB)")

    # 1. Qt WebEngine 调试资源（发布版完全不需要，约 75MB）
    for name in os.listdir(dist_dir):
        if name.endswith(".debug.pak"):
            _rm_file(os.path.join(dist_dir, name))

    # 2. 裁剪 PySide6 翻译，仅保留中文（约 14MB）
    trans_dir = os.path.join(dist_dir, "PySide6", "translations")
    if os.path.isdir(trans_dir):
        for name in os.listdir(trans_dir):
            if name.endswith(".qm") and not any(
                lang in name for lang in KEEP_TRANSLATIONS
            ):
                _rm_file(os.path.join(trans_dir, name))

    # 3. 删除 scipy（约 70MB，见 REMOVE_SCIPY 说明）
    if REMOVE_SCIPY:
        for name in ("scipy", "scipy.libs"):
            path = os.path.join(dist_dir, name)
            if os.path.isdir(path):
                _rm_tree(path, name)

    # 4. 删除 Qt WebEngine（约 300MB，见 REMOVE_WEBENGINE 说明）
    if REMOVE_WEBENGINE:
        for name in os.listdir(dist_dir):
            if any(fnmatch.fnmatch(name, p) for p in WEBENGINE_PATTERNS):
                _rm_file(os.path.join(dist_dir, name))

        for rel in WEBENGINE_PATHS:
            path = os.path.join(dist_dir, *rel.split("/"))
            if os.path.isdir(path):
                _rm_tree(path, rel)
            elif os.path.isfile(path):
                _rm_file(path)

    if removed:
        print(f"[clean] 共释放 {removed / 1024 / 1024:.1f} MB")
    else:
        print("[clean] 无需清理")


if sys.platform == "win32":
    args = [
        sys.executable,  # 使用当前Python解释器
        "-m",
        "nuitka",
        "--standalone",
        "--remove-output",  # 打包前清空旧产物(main.dist/main.build)，避免上次中断的残留混入
        # "--windows-uac-admin",
        "--windows-disable-console",
        "--plugin-enable=pyside6",
        "--include-qt-plugins=sensible,sqldrivers",
        "--assume-yes-for-downloads",
        "--mingw64",
        "--show-memory",
        "--show-progress",
        "--windows-icon-from-ico=logo.ico",  # 设置应用程序图标
        "--output-filename=School-Timetable-Generator.exe",  # 指定输出主程序文件名
        # ── 项目数据文件 ──
        "--include-data-file=images/gitcode.png=images/gitcode.png",
        "--include-data-file=images/issue_help.png=images/issue_help.png",
        "--include-data-file=images/issue_help2.png=images/issue_help2.png",
        "--include-data-file=images/issue_help3.png=images/issue_help3.png",
        "--include-data-file=images/cses.png=images/cses.png",
        "--include-data-file=LICENSE=LICENSE",
        "--include-data-file=logo.ico=logo.ico",
        "--include-data-file=template.xlsx=template.xlsx",
        "--include-data-file=app_version.txt=app_version.txt",
        # 排除不必要的大型包以减小体积
        # 注意：WebEngine 部分需与 REMOVE_WEBENGINE 保持一致（图表控件已改为延迟加载）
        "--nofollow-import-to=pytest,unittest,test,"
        "PySide6.QtWebEngineWidgets,PySide6.QtWebEngineCore,PySide6.QtWebEngineChannel,"
        "qfluentwidgets_pro.qframelesswindow.webengine",
        "main.py",
    ]

elif sys.platform == "darwin":
    args = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--plugin-enable=pyside6",
        "--show-memory",
        "--show-progress",
        "--macos-create-app-bundle",
        "--assume-yes-for-download",
        "--macos-disable-console",
        "main.py",
    ]
else:
    args = [
        sys.executable,
        "-m",
        "pyinstaller",
        "-w",
        "main.py",
    ]


result = subprocess.run(" ".join(args))
if result.returncode == 0:
    if sys.platform == "win32":
        clean_dist(DIST_DIR)
else:
    print("打包失败，跳过清理")
    sys.exit(result.returncode)
