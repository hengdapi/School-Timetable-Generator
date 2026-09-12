# coding=utf-8
"""
系统通知模块（Windows 原生实现）

基于 Shell_NotifyIcon 发送系统级气泡通知，无需任何第三方库，
也不依赖 Qt 系统托盘图标，即使应用窗口在后台/最小化也能收到提醒。

仅支持 Windows；其他平台调用 send_system_notification 时自动跳过并写日志。
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from ctypes import wintypes

# =====================================================================
# Win32 API 常量
# =====================================================================
_NIM_ADD = 0x0000        # Shell_NotifyIcon：添加图标
_NIM_MODIFY = 0x0001     # Shell_NotifyIcon：修改图标
_NIM_DELETE = 0x0002     # Shell_NotifyIcon：删除图标

_NIF_MESSAGE = 0x0001
_NIF_ICON = 0x0002
_NIF_TIP = 0x0004
_NIF_INFO = 0x0010

_NIIF_INFO = 0x0001      # 气泡信息样式：普通信息
_IMAGE_ICON = 1
_IDI_APPLICATION = 32512
_LR_LOADFROMFILE = 0x0010
_LR_DEFAULTSIZE = 0x0040
_WS_POPUP = 0x80000000
_HWND_MESSAGE = -3       # 创建仅用于消息的隐藏窗口
_WM_USER = 0x0400


class _NOTIFYICONDATAW(ctypes.Structure):
    """NOTIFYICONDATA 结构的 Unicode 版本（Windows 2000+ 布局）"""
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uTimeout", wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


if sys.platform == "win32":
    try:
        _user32 = ctypes.windll.user32
        _shell32 = ctypes.windll.shell32
        _kernel32 = ctypes.windll.kernel32

        # 声明 Win32 API 签名，避免 64 位下指针被截断
        _shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        _shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.c_void_p)

        _user32.CreateWindowExW.restype = wintypes.HWND
        _user32.CreateWindowExW.argtypes = (
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        )
        _user32.DestroyWindow.argtypes = (wintypes.HWND,)
        _user32.DestroyIcon.argtypes = (wintypes.HICON,)

        _user32.LoadImageW.restype = wintypes.HANDLE
        _user32.LoadImageW.argtypes = (
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        )
        _user32.LoadIconW.restype = wintypes.HICON
        _user32.LoadIconW.argtypes = (wintypes.HINSTANCE, ctypes.c_void_p)

        _kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        _kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    except Exception:  # pragma: no cover - 极端环境（无桌面会话等）
        _user32 = _shell32 = _kernel32 = None
else:
    _user32 = _shell32 = _kernel32 = None


def _get_default_icon_path() -> str | None:
    """定位应用图标文件 logo.ico，兼容源码运行与打包后的 exe"""
    candidates: list[str] = []
    if getattr(sys, "frozen", False):  # PyInstaller 打包
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
        candidates.append(os.path.join(base, "logo.ico"))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(os.path.dirname(here), "logo.ico"))  # 项目根目录
    candidates.append(os.path.join(here, "logo.ico"))
    candidates.append("logo.ico")
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _show_balloon(title: str, message: str, icon_path: str | None, display_time: float):
    """在后台线程中完成：创建图标 -> 弹出气泡 -> 延时清理（避免线程内创建窗口后被回收）"""
    hwnd = None
    hicon = None
    try:
        user32, shell32, kernel32 = _user32, _shell32, _kernel32

        # 1. 加载通知图标
        if icon_path and os.path.isfile(icon_path):
            try:
                hicon = user32.LoadImageW(
                    None, os.path.abspath(icon_path), _IMAGE_ICON, 0, 0,
                    _LR_LOADFROMFILE | _LR_DEFAULTSIZE,
                )
            except Exception:
                hicon = None
        if not hicon:
            # 找不到图标文件时使用系统默认“应用程序”图标
            hicon = user32.LoadIconW(None, ctypes.c_void_p(_IDI_APPLICATION))

        # 2. 创建隐藏的消息窗口，用于承载托盘图标（不出现在任务栏/Alt-Tab）
        hwnd = user32.CreateWindowExW(
            0, "STATIC", None, _WS_POPUP,
            0, 0, 0, 0,
            wintypes.HWND(_HWND_MESSAGE), None, kernel32.GetModuleHandleW(None), None,
        )
        if not hwnd:
            logging.warning("创建通知窗口失败，无法发送系统通知")
            return

        # 3. 先添加托盘图标
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 0
        nid.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        nid.uCallbackMessage = _WM_USER + 20
        nid.hIcon = hicon or 0
        nid.szTip = title[:127]
        if not shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid)):
            logging.warning("添加系统通知图标失败")
            return

        # 4. 再发送一次以弹出气泡（部分 Windows 版本首次添加时不显示气泡）
        nid.uFlags = _NIF_ICON | _NIF_INFO
        nid.szInfo = message[:255]
        nid.szInfoTitle = title[:63]
        nid.dwInfoFlags = _NIIF_INFO
        shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(nid))
        logging.debug(f"系统通知已发送：{title} - {message}")

        # 5. 等待通知展示结束后再清理图标，避免气泡提前消失
        time.sleep(display_time)
        shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(nid))
    except Exception as error:
        logging.warning(f"发送系统通知失败：{error}")
    finally:
        try:
            if hwnd:
                _user32.DestroyWindow(hwnd)
        except Exception:
            pass
        try:
            if hicon:
                _user32.DestroyIcon(hicon)
        except Exception:
            pass


def send_system_notification(
    title: str, message: str,
    icon_path: str | None = None, display_time: float = 8.0,
) -> bool:
    """发送系统通知。

    :param title: 通知标题
    :param message: 通知正文（过长时会被系统截断）
    :param icon_path: 图标文件路径；为 None 时自动查找 logo.ico
    :param display_time: 托盘图标保留时长（秒），应大于通知实际展示时间
    :return: 是否成功启动通知线程（通知仍在异步展示中）
    """
    if sys.platform != "win32" or _user32 is None:
        logging.warning("无法发送系统通知：当前系统不支持或系统 API 不可用")
        return False
    title = title or "课程表生成器"
    if icon_path is None:
        icon_path = _get_default_icon_path()
    try:
        threading.Thread(
            target=_show_balloon,
            args=(title, message, icon_path, display_time),
            daemon=True,
        ).start()
        return True
    except Exception as error:
        logging.warning(f"发送系统通知失败：{error}")
        return False
