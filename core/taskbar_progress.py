# coding=utf-8
"""
Windows 任务栏进度条（ITaskbarList3）

PySide6 已移除 Qt5 的 QtWinExtras（QWinTaskbarButton），因此这里用 ctypes
直接调用 Windows 的 ITaskbarList3 COM 接口，零第三方依赖。

仅支持 Windows；在其他平台下所有方法自动退化为空操作，不会产生副作用。
"""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

# 任务栏进度条状态（TBPFLAG）
NO_PROGRESS = 0x0    # 隐藏进度条
INDETERMINATE = 0x1  # 循环滚动（进度未知）
NORMAL = 0x2         # 正常（绿色）
ERROR = 0x4          # 出错（红色）
PAUSED = 0x8         # 暂停（黄色）

_IS_WINDOWS = sys.platform == "win32"
_CLSCTX_INPROC_SERVER = 0x1
_CLSID_TASKBAR_LIST = "{56FDF344-FD6D-11D0-958A-006097C9A090}"
_IID_ITASKBAR_LIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"


class _GUID(ctypes.Structure):
    """COM GUID，可由形如 {xxxxxxxx-xxxx-...} 的字符串构造"""
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, text: str) -> "_GUID":
        guid = cls()
        _ole32.IIDFromString(text, ctypes.byref(guid))
        return guid


class _ITaskbarList3Vtbl(ctypes.Structure):
    """ITaskbarList3 的虚函数表（IUnknown + ITaskbarList + ITaskbarList2 + ITaskbarList3）"""
    _fields_ = [
        ("QueryInterface", ctypes.c_void_p),
        ("AddRef", ctypes.c_void_p),
        ("Release", ctypes.c_void_p),
        ("HrInit", ctypes.c_void_p),
        ("AddTab", ctypes.c_void_p),
        ("DeleteTab", ctypes.c_void_p),
        ("ActivateTab", ctypes.c_void_p),
        ("SetActiveAlt", ctypes.c_void_p),
        ("MarkFullscreenWindow", ctypes.c_void_p),   # ITaskbarList2
        ("SetProgressValue", ctypes.c_void_p),       # ITaskbarList3
        ("SetProgressState", ctypes.c_void_p),
        ("RegisterTab", ctypes.c_void_p),
        ("UnregisterTab", ctypes.c_void_p),
        ("SetTabOrder", ctypes.c_void_p),
        ("SetTabActive", ctypes.c_void_p),
        ("ThumbBarAddButtons", ctypes.c_void_p),
        ("ThumbBarUpdateButtons", ctypes.c_void_p),
        ("ThumbBarSetImageList", ctypes.c_void_p),
        ("SetOverlayIcon", ctypes.c_void_p),
        ("SetThumbnailTooltip", ctypes.c_void_p),
        ("SetThumbnailClip", ctypes.c_void_p),
    ]


_ReleaseProto = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
_HrInitProto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)
_SetProgressValueProto = ctypes.WINFUNCTYPE(
    ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND, ctypes.c_ulonglong, ctypes.c_ulonglong)
_SetProgressStateProto = ctypes.WINFUNCTYPE(
    ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND, ctypes.c_int)


if _IS_WINDOWS:
    _ole32 = ctypes.oledll.ole32
    _ole32.IIDFromString.argtypes = (ctypes.c_wchar_p, ctypes.POINTER(_GUID))
    _ole32.CoInitialize.argtypes = (ctypes.c_void_p,)
    _ole32.CoCreateInstance.argtypes = (
        ctypes.POINTER(_GUID), ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p),
    )
else:  # 非 Windows：保留占位，避免导入时报错
    _ole32 = None


class TaskbarProgress:
    """单个窗口的任务栏进度条"""

    def __init__(self):
        self._hwnd = 0            # 目标窗口句柄
        self._ptr = None          # ITaskbarList3 指针
        self._vtbl = None         # 虚函数表
        self._available = None    # None=尚未尝试初始化，True/False=结果
        self._state = NO_PROGRESS

    # ==================== 初始化 ====================
    def _ensure(self) -> bool:
        """惰性创建 ITaskbarList3 实例（只创建一次）"""
        if self._available is not None:
            return self._available
        self._available = False
        if not _IS_WINDOWS:
            return False
        try:
            try:
                _ole32.CoInitialize(None)  # 已初始化时返回 S_FALSE，属正常
            except OSError as error:
                logging.debug(f"CoInitialize 已由 Qt 完成或模式不同：{error}")
            ptr = ctypes.c_void_p()
            _ole32.CoCreateInstance(
                ctypes.byref(_GUID.from_string(_CLSID_TASKBAR_LIST)),
                None, _CLSCTX_INPROC_SERVER,
                ctypes.byref(_GUID.from_string(_IID_ITASKBAR_LIST3)),
                ctypes.byref(ptr),
            )
            if not ptr:
                logging.warning("创建 ITaskbarList3 失败，任务栏进度条不可用")
                return False
            self._ptr = ptr
            self._vtbl = ctypes.cast(
                ptr, ctypes.POINTER(ctypes.POINTER(_ITaskbarList3Vtbl))).contents.contents
            _HrInitProto(self._vtbl.HrInit)(ptr)
            self._available = True
            logging.debug("任务栏进度条已就绪")
        except Exception as error:
            logging.warning(f"初始化任务栏进度条失败：{error}")
        return self._available

    @staticmethod
    def _resolve_hwnd(window) -> int:
        """从 QWidget / 顶层窗口 / 句柄中取得 HWND"""
        if isinstance(window, int):
            return window
        try:
            top = window.window() if hasattr(window, "window") else window
            return int(top.winId())
        except Exception:
            return 0

    def bind(self, window) -> bool:
        """绑定要显示进度条的窗口（传主窗口或任意子控件均可）"""
        hwnd = self._resolve_hwnd(window)
        if hwnd:
            self._hwnd = hwnd
        return self._ensure() and self._hwnd != 0

    # ==================== 进度控制 ====================
    def set_state(self, state: int) -> bool:
        """设置进度条状态：NO_PROGRESS / INDETERMINATE / NORMAL / ERROR / PAUSED"""
        if not self._hwnd or not self._ensure():
            return False
        try:
            self._state = state
            _SetProgressStateProto(self._vtbl.SetProgressState)(self._ptr, self._hwnd, state)
            return True
        except Exception as error:
            logging.debug(f"设置任务栏进度条状态失败：{error}")
            return False

    def set_value(self, completed: int, total: int = 100, state: int = NORMAL) -> bool:
        """设置进度百分比（自动切换到 NORMAL 状态）"""
        if not self._hwnd or not self._ensure():
            return False
        try:
            completed = max(0, min(int(completed), int(total)))
            if self._state != state:
                self.set_state(state)
            _SetProgressValueProto(self._vtbl.SetProgressValue)(
                self._ptr, self._hwnd, ctypes.c_ulonglong(completed), ctypes.c_ulonglong(total))
            return True
        except Exception as error:
            logging.debug(f"更新任务栏进度失败：{error}")
            return False

    def set_indeterminate(self) -> bool:
        """进度未知时的循环滚动动画"""
        return self.set_state(INDETERMINATE)

    def clear(self) -> bool:
        """隐藏任务栏进度条"""
        return self.set_state(NO_PROGRESS)

    # ==================== 清理 ====================
    def release(self):
        if self._ptr is not None:
            try:
                _ReleaseProto(self._vtbl.Release)(self._ptr)
            except Exception:
                pass
            self._ptr = None
            self._vtbl = None
            self._available = None

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass
