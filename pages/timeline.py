# coding=utf-8
"""时间段活动编辑窗口。

以独立窗口的形式，把“课程起止时间”与“活动信息”统一放到一条时间轴上编辑：

- 蓝色块 = 课程（对应 cfg.lessons_time）
- 橙色块 = 活动（对应 cfg.activity_info）

支持：点击/左侧列表选中、拖拽整块移动、拖拽上下边缘调整时长、双击或右键
（列表、时间轴均可）打开编辑菜单、滑杆缩放时间轴，并在存在交叉/非法时间时
给出提示。
"""

import logging

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTime, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QPen, QShortcut
)
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget
)
from qfluentwidgets_pro import Action, FluentWidget, MenuAnimationType, RoundMenu

from pages.ui_widgets import *

# 时间块类型
KIND_LESSON = "lesson"
KIND_ACTIVITY = "activity"

# 类型 -> (类型名, 底色, 内部浅色)
BLOCK_STYLES = {
    KIND_LESSON: ("课程", QColor(206, 224, 242), QColor(233, 241, 250)),
    KIND_ACTIVITY: ("活动", QColor(228, 213, 184), QColor(244, 236, 222)),
}

# 拖动时吸附的最小时间粒度（分钟）
SNAP_MINUTES = 5
# 时间块最短时长（分钟）
MIN_DURATION = 5

# 本窗口统一使用的字号（主窗口整体字号偏大，这里单独调小以保持协调）
UI_FONT = QFont("Microsoft YaHei", 12)        # 正文 / 控件
SUBTITLE_FONT = QFont("Microsoft YaHei", 15)  # 小标题
TITLE_FONT = QFont("Microsoft YaHei", 22)     # 页面大标题
# 时间轴内部文字（块里空间有限，用更小的字号）
TIMELINE_AXIS_FONT = QFont("Microsoft YaHei", 10)          # 左侧刻度
TIMELINE_NAME_FONT = QFont("Microsoft YaHei", 10, QFont.Bold)  # 块内名称
TIMELINE_TIME_FONT = QFont("Microsoft YaHei", 9)           # 块内时间


def format_clock(minutes: int) -> str:
    """把“从0点开始的分钟数”格式化成 HH:MM"""
    minutes = max(0, int(minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def snap_minutes(minutes: float) -> int:
    """把分钟数吸附到最近的 SNAP_MINUTES 粒度"""
    return int(round(minutes / SNAP_MINUTES)) * SNAP_MINUTES


class TimeBlock:
    """时间轴上的一个时间块"""

    def __init__(self, kind: str, key: str, name: str, start: int, end: int):
        self.kind = kind
        self.key = key          # 课程为节次字符串，活动为活动名称
        self.name = name        # 显示名称
        self.start = int(start)  # 开始时间（分钟）
        self.end = int(end)      # 结束时间（分钟）

    @property
    def duration(self) -> int:
        return max(0, self.end - self.start)

    def __repr__(self):
        return f"<TimeBlock {self.kind} {self.name} {format_clock(self.start)}-{format_clock(self.end)}>"


# =====================================================================
# 编辑对话框
# =====================================================================
class BlockEditMsgbox(MessageBoxBase):
    """编辑一个时间块的名称与起止时间"""

    def __init__(self, block: TimeBlock, parent=None):
        super().__init__(parent=parent)
        self.block = block
        self.result = None
        self.setFont(UI_FONT)
        is_lesson = block.kind == KIND_LESSON
        label("编辑课程时间" if is_lesson else "编辑活动", SubtitleLabel, SUBTITLE_FONT,
              self, self.viewLayout)

        add_widget(BodyLabel("名称："), self.viewLayout, 0)
        self.name_input = LineEdit()
        self.name_input.setText(block.name)
        if is_lesson:
            self.name_input.setEnabled(False)
            self.name_input.setToolTip("课程名称由节次决定，不能修改")
        add_widget(self.name_input, self.viewLayout)

        add_widget(BodyLabel("开始时间："), self.viewLayout, 0)
        self.start_picker = TimePicker()
        self.start_picker.setTime(QTime(block.start // 60, block.start % 60))
        add_widget(self.start_picker, self.viewLayout)

        add_widget(BodyLabel("结束时间："), self.viewLayout, 0)
        self.end_picker = TimePicker()
        self.end_picker.setTime(QTime(min(block.end, 23 * 60 + 59) // 60, block.end % 60))
        add_widget(self.end_picker, self.viewLayout)

        self.yesButton.setText("保存")
        self.yesButton.setIcon(FluentIcon.SAVE)
        self.cancelButton.setText("取消")

    def validate(self) -> bool:
        name = self.name_input.text().strip()
        if not name:
            Toast.error("请输入名称", "", parent=self, duration=-1)
            return False
        start = self.start_picker.time.hour() * 60 + self.start_picker.time.minute()
        end = self.end_picker.time.hour() * 60 + self.end_picker.time.minute()
        if end <= start:
            Toast.error("结束时间必须晚于开始时间", "", parent=self, duration=-1)
            return False
        if self.block.kind == KIND_ACTIVITY and name != self.block.key and name in cfg.activity_info.value:
            Toast.error("活动名称重复", f"名称“{name}”已存在", parent=self, duration=-1)
            return False
        self.result = (name, start, end)
        return True


class DefaultDurationMsgbox(MessageBoxBase):
    """设置新建课程/活动时的默认时长"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFont(UI_FONT)
        label("设置默认时长", SubtitleLabel, SUBTITLE_FONT, self, self.viewLayout)
        add_widget(BodyLabel("为新建的课程、活动设置默认持续时间（分钟）："), self.viewLayout, 0)
        self.spin = SpinBox()
        self.spin.setRange(5, 180)
        self.spin.setValue(int(cfg.default_duration.value))
        add_widget(self.spin, self.viewLayout)
        self.yesButton.setText("保存")
        self.yesButton.setIcon(FluentIcon.SAVE)

    def validate(self) -> bool:
        cfg.default_duration.value = self.spin.value()
        save_settings()
        return True


class TimelineRangeMsgbox(MessageBoxBase):
    """设置时间轴显示的时间范围"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFont(UI_FONT)
        label("设置时间轴范围", SubtitleLabel, SUBTITLE_FONT, self, self.viewLayout)
        add_widget(BodyLabel("时间轴会自动包含所有课程与活动，此处设置的是一天内时间轴至少展示的范围："),
                   self.viewLayout, 0)
        start_hour, end_hour = list(cfg.timeline_range.value or [7, 18])[:2]
        row = QHBoxLayout()
        row.setSpacing(8)
        self.viewLayout.addLayout(row)
        self.start_picker = TimePicker()
        self.start_picker.setTime(QTime(int(start_hour), 0))
        self.end_picker = TimePicker()
        self.end_picker.setTime(QTime(int(end_hour), 0))
        row.addWidget(BodyLabel("开始："))
        row.addWidget(self.start_picker)
        row.addWidget(BodyLabel("结束："))
        row.addWidget(self.end_picker)
        self.yesButton.setText("保存")
        self.yesButton.setIcon(FluentIcon.SAVE)

    def validate(self) -> bool:
        start = self.start_picker.time.hour() * 60 + self.start_picker.time.minute()
        end = self.end_picker.time.hour() * 60 + self.end_picker.time.minute()
        if end <= start:
            Toast.error("结束时间必须晚于开始时间", "", parent=self, duration=-1)
            return False
        cfg.timeline_range.value = [start // 60, (end + 59) // 60]
        save_settings()
        return True


# =====================================================================
# 时间轴画布
# =====================================================================
class TimelineCanvas(QWidget):
    """自绘的时间轴：绘制刻度与时间块，并处理拖动/缩放交互"""

    RULER_WIDTH = 74     # 左侧刻度宽度
    SIDE_MARGIN = 14     # 右侧留白
    BASE_HOUR_HEIGHT = 80  # 100% 时每小时的高度

    blockClicked = Signal(object)          # 选中变化（TimeBlock 或 None）
    blockDoubleClicked = Signal(object)    # 双击某个时间块
    blockCommitted = Signal(object)        # 拖动结束后需要写回配置

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(TIMELINE_AXIS_FONT)
        self.blocks: list[TimeBlock] = []
        self.range_start = 7 * 60
        self.range_end = 18 * 60
        self.hour_height = self.BASE_HOUR_HEIGHT
        self.selected: TimeBlock | None = None
        self.scroll_area = None
        self._hover: TimeBlock | None = None
        self._drag = None
        self.setMouseTracking(True)
        self.setMinimumWidth(320)
        self._update_height()

    # ---------------------------------------------------------------
    # 坐标换算
    # ---------------------------------------------------------------
    def y_for(self, minutes: float) -> int:
        return int((minutes - self.range_start) / 60 * self.hour_height)

    def minutes_for(self, y: float) -> float:
        return self.range_start + y / self.hour_height * 60

    def block_rect(self, block: TimeBlock) -> QRect:
        left = self.RULER_WIDTH
        right = max(left + 20, self.width() - self.SIDE_MARGIN)
        top = self.y_for(block.start)
        bottom = self.y_for(block.end)
        if bottom - top < 20:
            bottom = top + 20
        return QRect(left, top, right - left, bottom - top)

    def block_at(self, pos) -> TimeBlock | None:
        """命中测试：后绘制的块显示在上层，因此从后往前找"""
        for block in reversed(self.blocks):
            if self.block_rect(block).contains(pos):
                return block
        return None

    # ---------------------------------------------------------------
    # 数据与尺寸
    # ---------------------------------------------------------------
    def set_data(self, blocks, range_start, range_end):
        self.blocks = blocks
        self.selected = None
        self._hover = None
        self._drag = None
        self.refresh_range(range_start, range_end)

    def refresh_range(self, range_start, range_end):
        self.range_start = range_start
        self.range_end = range_end
        self._update_height()
        self.update()

    def set_hour_height(self, height: int):
        self.hour_height = max(28, int(height))
        self._update_height()
        self.update()

    def _update_height(self):
        total = int((self.range_end - self.range_start) / 60 * self.hour_height) + 40
        self.setFixedHeight(max(total, 120))

    def select(self, block):
        self.selected = block
        self.update()

    def scroll_to(self, block: TimeBlock):
        if self.scroll_area is None:
            return
        bar = self.scroll_area.verticalScrollBar()
        center = self.block_rect(block).center().y()
        bar.setValue(max(0, center - bar.height() // 2))

    # ---------------------------------------------------------------
    # 绘制
    # ---------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        self._paint_ruler(painter)
        for block in self.blocks:
            self._paint_block(painter, block)
        painter.end()

    def _paint_ruler(self, painter: QPainter):
        painter.setFont(self.font())
        hour = self.range_start // 60
        end_hour = self.range_end // 60
        while hour <= end_hour:
            y = self.y_for(hour * 60)
            painter.setPen(QColor(120, 120, 120))
            text = f"{hour:02d}:00"
            painter.drawText(QRect(0, y - 10, self.RULER_WIDTH - 12, 20),
                             Qt.AlignRight | Qt.AlignVCenter, text)
            painter.setPen(QPen(QColor(0, 0, 0, 22), 1))
            painter.drawLine(self.RULER_WIDTH, y, max(self.width() - self.SIDE_MARGIN, self.RULER_WIDTH), y)
            hour += 1

    def _paint_block(self, painter: QPainter, block: TimeBlock):
        rect = self.block_rect(block)
        _, base, light = BLOCK_STYLES[block.kind]
        painter.setPen(Qt.NoPen)
        painter.setBrush(base)
        painter.drawRoundedRect(QRectF(rect), 8, 8)
        inner = rect.adjusted(3, 3, -3, -3)
        if inner.height() > 8:
            painter.setBrush(light)
            painter.drawRoundedRect(QRectF(inner), 6, 6)
        if block is self.selected:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(0, 120, 215), 2))
            painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 8, 8)
        elif block is self._hover:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(0, 0, 0, 45), 2))
            painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 8, 8)

        name_font = QFont(TIMELINE_NAME_FONT)
        time_font = QFont(TIMELINE_TIME_FONT)
        time_text = f"{format_clock(block.start)} - {format_clock(block.end)}（{block.duration}分钟）"
        text_rect = rect.adjusted(14, 2, -10, -2)

        if rect.height() < 24:
            # 块太矮，只画名称
            painter.setFont(name_font)
            painter.setPen(QColor(55, 55, 55))
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, block.name)
            return

        if rect.height() >= 52:
            # 两行：名称在上，时间在下，整体垂直居中
            name_h = QFontMetrics(name_font).height() + 2
            time_h = QFontMetrics(time_font).height() + 2
            top = text_rect.y() + max(0, (text_rect.height() - name_h - time_h) // 2)
            painter.setFont(name_font)
            painter.setPen(QColor(45, 45, 45))
            painter.drawText(QRect(text_rect.x(), top, text_rect.width(), name_h),
                             Qt.AlignLeft | Qt.AlignVCenter, block.name)
            painter.setFont(time_font)
            painter.setPen(QColor(85, 85, 85))
            painter.drawText(QRect(text_rect.x(), top + name_h, text_rect.width(), time_h),
                             Qt.AlignLeft | Qt.AlignVCenter, time_text)
        else:
            # 单行：名称 + 时间
            painter.setFont(name_font)
            painter.setPen(QColor(45, 45, 45))
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, block.name)
            name_width = QFontMetrics(name_font).horizontalAdvance(block.name)
            painter.setFont(time_font)
            painter.setPen(QColor(85, 85, 85))
            painter.drawText(text_rect.adjusted(name_width + 10, 0, 0, 0),
                             Qt.AlignLeft | Qt.AlignVCenter, time_text)

    # ---------------------------------------------------------------
    # 交互：拖拽移动 / 调整时长
    # ---------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        pos = event.position().toPoint()
        block = self.block_at(pos)
        if block is None:
            self.select(None)
            self.blockClicked.emit(None)
            return
        rect = self.block_rect(block)
        if pos.y() - rect.top() <= 6:
            mode = "top"
        elif rect.bottom() - pos.y() <= 6:
            mode = "bottom"
        else:
            mode = "move"
        self._drag = {
            "block": block,
            "mode": mode,
            "grab": self.minutes_for(pos.y()),
            "start": block.start,
            "end": block.end,
            "moved": False,
        }
        self.select(block)
        self.blockClicked.emit(block)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        if self._drag is not None:
            self._apply_drag(pos)
            return
        block = self.block_at(pos)
        if block is not self._hover:
            self._hover = block
            self.update()
        if block is not None:
            rect = self.block_rect(block)
            if pos.y() - rect.top() <= 6 or rect.bottom() - pos.y() <= 6:
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self._drag is not None and self._drag["moved"]:
            block = self._drag["block"]
            self._drag = None
            self.blockCommitted.emit(block)
            return
        self._drag = None

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mouseDoubleClickEvent(event)
        block = self.block_at(event.position().toPoint())
        if block is not None:
            self.blockDoubleClicked.emit(block)

    def _apply_drag(self, pos):
        drag = self._drag
        block = drag["block"]
        delta = snap_minutes(self.minutes_for(pos.y()) - drag["grab"])
        if drag["mode"] == "move":
            duration = drag["end"] - drag["start"]
            start = max(0, min(drag["start"] + delta, 24 * 60 - duration))
            block.start, block.end = start, start + duration
        elif drag["mode"] == "top":
            block.start = max(0, min(drag["start"] + delta, drag["end"] - MIN_DURATION))
        else:
            block.end = max(drag["start"] + MIN_DURATION, min(drag["end"] + delta, 24 * 60 - 1))
        drag["moved"] = True
        self.update()


# =====================================================================
# 独立窗口
# =====================================================================
class TimelineEditor(FluentWidget):
    """时间段活动编辑窗口（独立窗口，非子页面）"""

    dataChanged = Signal()  # 时间配置被修改

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # 即使指定了父窗口也要作为独立窗口显示
        if parent is not None:
            self.setWindowFlag(Qt.Window, True)
        self.setObjectName("TimelineEditor")
        self.setWindowTitle("活动时间设置")
        self.setWindowIcon(QIcon("logo.ico"))
        self.setFont(UI_FONT)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1000, 760)
        self._center(parent)

        self.blocks: list[TimeBlock] = []
        self._list_lock = False

        # 内容区域（放在标题栏下方）
        content = QWidget(self)
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(0)

        self.title = label("活动时间设置", LargeTitleLabel, TITLE_FONT, content, main_layout, 10)
        self.title.setFixedHeight(46)

        # 顶部设置卡片
        header = QHBoxLayout()
        header.setSpacing(16)
        main_layout.addLayout(header)
        main_layout.addSpacing(10)

        self.duration_card = PushSettingCard("设置", FluentIcon.STOP_WATCH, "设置默认时长",
                                             "为新建的课程、活动设置默认持续时间")
        self.duration_card.clicked.connect(self.set_default_duration)
        header.addWidget(self.duration_card)

        self.range_card = PushSettingCard("设置", FluentIcon.DATE_TIME, "设置时间轴范围",
                                          "设置时间轴显示的开始与结束时间")
        self.range_card.clicked.connect(self.set_timeline_range)
        header.addWidget(self.range_card)

        # 冲突提示横幅
        self.banner = WarningBanner(content)
        main_layout.addWidget(self.banner)
        main_layout.addSpacing(10)

        # 主体：左侧列表 + 右侧时间轴
        body = QHBoxLayout()
        body.setSpacing(16)
        main_layout.addLayout(body, 1)

        self.side = QWidget()
        self.side.setFixedWidth(230)
        side_layout = QVBoxLayout(self.side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(8)
        side_label = BodyLabel("课程及活动列表")
        side_label.setFont(SUBTITLE_FONT)
        side_layout.addWidget(side_label)

        self.block_list = RoundListWidget()
        self.block_list.setFont(UI_FONT)
        self.list_delegate = RoundListItemDelegate(self.block_list)
        self.list_delegate.sizeHint = lambda option, index: QSize(option.rect.width(), 58)
        self.block_list.setItemDelegate(self.list_delegate)
        self.block_list.currentItemChanged.connect(self.on_list_selection)
        self.block_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.block_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.block_list.customContextMenuRequested.connect(self.on_list_context_menu)
        side_layout.addWidget(self.block_list, 1)

        side_buttons = QHBoxLayout()
        side_buttons.setSpacing(8)
        side_layout.addLayout(side_buttons)
        self.add_activity_button = PushButton("新建活动")
        self.add_activity_button.setIcon(FluentIcon.ADD)
        self.add_activity_button.setFixedHeight(34)
        self.add_activity_button.clicked.connect(self.add_activity)
        side_buttons.addWidget(self.add_activity_button)
        self.del_block_button = PushButton("删除")
        self.del_block_button.setIcon(FluentIcon.DELETE)
        self.del_block_button.setFixedHeight(34)
        self.del_block_button.setEnabled(False)
        self.del_block_button.setToolTip("删除选中的活动（也可直接按 Delete 键）")
        self.del_block_button.clicked.connect(self.delete_selected)
        side_buttons.addWidget(self.del_block_button)
        body.addWidget(self.side)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        body.addWidget(right, 1)

        self.scroll = SingleDirectionScrollArea(orient=Qt.Vertical)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea{background: transparent; border: none;}")
        self.canvas = TimelineCanvas(right)
        self.canvas.scroll_area = self.scroll
        self.canvas.blockClicked.connect(self.on_canvas_selection)
        self.canvas.blockDoubleClicked.connect(self.edit_block)
        self.canvas.blockCommitted.connect(self.on_block_committed)
        self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self.canvas.customContextMenuRequested.connect(self.on_canvas_context_menu)
        self.scroll.setWidget(self.canvas)

        # Delete 键删除选中的活动
        self.delete_shortcut = QShortcut(QKeySequence(QKeySequence.Delete), self)
        self.delete_shortcut.activated.connect(self.on_delete_shortcut)
        right_layout.addWidget(self.scroll, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        right_layout.addLayout(bottom)
        for kind in (KIND_LESSON, KIND_ACTIVITY):
            bottom.addWidget(self._make_legend_item(kind))
        bottom.addStretch(1)
        self.zoom_label = BodyLabel("100%")
        bottom.addWidget(self.zoom_label)
        self.zoom_slider = Slider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(160)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        bottom.addWidget(self.zoom_slider)

        window_layout = QVBoxLayout(self)
        window_layout.setContentsMargins(0, self.titleBar.height(), 0, 0)
        window_layout.setSpacing(0)
        window_layout.addWidget(content)
        self.titleBar.raise_()

        self.reload()

    def _center(self, parent=None):
        """把窗口居中显示（默认相对父窗口，没有父窗口则相对屏幕）"""
        try:
            if isinstance(parent, QWidget):
                geometry = parent.frameGeometry()
            else:
                screen = self.screen() or QApplication.primaryScreen()
                if screen is None:
                    return
                geometry = screen.availableGeometry()
            self.move(geometry.center() - self.rect().center())
        except Exception:
            pass

    # ---------------------------------------------------------------
    # 构建与刷新
    # ---------------------------------------------------------------
    def _make_legend_item(self, kind: str) -> QWidget:
        name, base, _ = BLOCK_STYLES[kind]
        item = QWidget()
        layout = QHBoxLayout(item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        dot = QLabel()
        dot.setFixedSize(12, 12)
        dot.setStyleSheet(
            f"QLabel{{background:{base.name()};border:1px solid rgba(127,127,127,0.35);border-radius:3px;}}"
        )
        name_label = BodyLabel(name)
        layout.addWidget(dot)
        layout.addWidget(name_label)
        return item

    def build_blocks(self) -> list[TimeBlock]:
        """根据当前配置生成时间块"""
        blocks: list[TimeBlock] = []
        default_duration = int(cfg.default_duration.value)
        for lesson in range(1, cfg.day_class_num + 1):
            key = str(lesson)
            start, end = cfg.lessons_time.value.get(key, [[0, 0], [0, 0]])
            start_minutes = start[0] * 60 + start[1]
            end_minutes = end[0] * 60 + end[1]
            if end_minutes <= start_minutes:
                end_minutes = start_minutes + default_duration
            blocks.append(TimeBlock(KIND_LESSON, key, Time(1, lesson).to_str(False, True),
                                    start_minutes, end_minutes))
        for name, (start, end) in cfg.activity_info.value.items():
            start_minutes = start[0] * 60 + start[1]
            end_minutes = end[0] * 60 + end[1]
            if end_minutes <= start_minutes:
                end_minutes = start_minutes + default_duration
            blocks.append(TimeBlock(KIND_ACTIVITY, name, name, start_minutes, end_minutes))
        blocks.sort(key=lambda block: (block.start, block.end))
        return blocks

    def compute_range(self) -> tuple[int, int]:
        """时间轴显示范围 = 用户设置的范围与所有时间块的并集"""
        config_range = list(cfg.timeline_range.value or [7, 18])
        low = min(int(hour) for hour in config_range) * 60
        high = max(int(hour) for hour in config_range) * 60
        for block in self.blocks:
            low = min(low, block.start)
            high = max(high, block.end)
        low = max(0, (low // 60) * 60)
        high = min(24 * 60, ((high + 59) // 60) * 60)
        return low, high

    def reload(self):
        try:
            self.blocks = self.build_blocks()
            self.canvas.set_data(self.blocks, *self.compute_range())
            self.refresh_list()
            self.refresh_warnings()
            self.del_block_button.setEnabled(False)
        except Exception as error:
            logging.critical(f"加载活动时间设置页面出错：\n{traceback.format_exc()}")
            show_error(self, error)

    def sort_blocks(self):
        """按时间顺序排列时间块（开始时间，相同则按结束时间），并同步给画布"""
        self.blocks.sort(key=lambda block: (block.start, block.end))
        self.canvas.blocks = self.blocks
        self.canvas.update()

    def refresh_list(self):
        self.sort_blocks()
        # 先记下滚动位置，刷新后恢复，避免每次改动都跳回列表顶部
        scroll_bar = self.block_list.verticalScrollBar()
        scroll_value = scroll_bar.value()
        self._list_lock = True
        try:
            if self.block_list.count() == len(self.blocks):
                # 数量没变时就地更新文本，不做整体重建（重建会清空滚动位置）
                for row, block in enumerate(self.blocks):
                    item = self.block_list.item(row)
                    item.setText(f"{block.name}\n{format_clock(block.start)} - {format_clock(block.end)}")
                    item.setData(Qt.UserRole, block)
            else:
                self.block_list.clear()
                for block in self.blocks:
                    item = QListWidgetItem(f"{block.name}\n{format_clock(block.start)} - {format_clock(block.end)}")
                    item.setData(Qt.UserRole, block)
                    QListWidget.addItem(self.block_list, item)
            # 排序后选中项的行号可能变化，重新对齐
            if self.canvas.selected in self.blocks:
                for row in range(self.block_list.count()):
                    if self.block_list.item(row).data(Qt.UserRole) is self.canvas.selected:
                        self.block_list.setCurrentRow(row)
                        break
        finally:
            self._list_lock = False
            scroll_bar.setValue(scroll_value)

    # ---------------------------------------------------------------
    # 事件
    # ---------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        self.reload()

    def on_list_selection(self, current, previous=None):
        if self._list_lock or current is None:
            return
        block = current.data(Qt.UserRole)
        if isinstance(block, TimeBlock):
            self.canvas.select(block)
            self.canvas.scroll_to(block)
            self.del_block_button.setEnabled(block.kind == KIND_ACTIVITY)

    def on_canvas_selection(self, block):
        self._list_lock = True
        try:
            if block is None:
                self.block_list.setCurrentRow(-1)
                self.block_list.clearSelection()
            else:
                for row in range(self.block_list.count()):
                    if self.block_list.item(row).data(Qt.UserRole) is block:
                        self.block_list.setCurrentRow(row)
                        break
        finally:
            self._list_lock = False
        self.del_block_button.setEnabled(block is not None and block.kind == KIND_ACTIVITY)

    def on_item_double_clicked(self, item):
        """双击左侧列表项直接编辑"""
        block = item.data(Qt.UserRole) if item is not None else None
        if isinstance(block, TimeBlock):
            self.edit_block(block)

    def on_list_context_menu(self, pos):
        """在左侧列表上右键"""
        item = self.block_list.itemAt(pos)
        if item is not None:
            self.block_list.setCurrentItem(item)
        block = item.data(Qt.UserRole) if item is not None else None
        self.show_block_menu(block, self.block_list.mapToGlobal(pos))

    def on_canvas_context_menu(self, pos):
        """在时间轴上右键"""
        block = self.canvas.block_at(pos)
        if block is not None:
            self.canvas.select(block)
            self.on_canvas_selection(block)
        self.show_block_menu(block, self.canvas.mapToGlobal(pos))

    def show_block_menu(self, block, global_pos):
        """弹出时间块的右键菜单（列表与时间轴共用）"""
        menu = RoundMenu(parent=self)
        if block is not None:
            edit_action = Action(FluentIcon.EDIT, "编辑时间")
            edit_action.triggered.connect(lambda: self.edit_block(block))
            menu.addAction(edit_action)

            delete_action = Action(FluentIcon.DELETE, "删除")
            delete_action.setShortcut(QKeySequence(QKeySequence.Delete))
            delete_action.triggered.connect(self.delete_selected)
            delete_action.setEnabled(block.kind == KIND_ACTIVITY)
            menu.addAction(delete_action)

            copy_action = Action(FluentIcon.COPY, "以此为模板新建活动")
            copy_action.triggered.connect(lambda: self.duplicate_block(block))
            menu.addAction(copy_action)
            menu.addSeparator()

        add_action = Action(FluentIcon.ADD, "新建活动")
        add_action.triggered.connect(self.add_activity)
        menu.addAction(add_action)
        menu.exec(global_pos, aniType=MenuAnimationType.DROP_DOWN)

    def on_zoom_changed(self, value: int):
        self.zoom_label.setText(f"{value}%")
        self.canvas.set_hour_height(int(TimelineCanvas.BASE_HOUR_HEIGHT * value / 100))

    def on_block_committed(self, block: TimeBlock):
        try:
            self.apply_block_to_cfg(block)
            save_settings()
            self.refresh_list()
            self.canvas.refresh_range(*self.compute_range())
            self.refresh_warnings()
            self.dataChanged.emit()
        except Exception as error:
            logging.critical(f"保存时间块出错：\n{traceback.format_exc()}")
            show_error(self, error)

    # ---------------------------------------------------------------
    # 编辑操作
    # ---------------------------------------------------------------
    def apply_block_to_cfg(self, block: TimeBlock):
        value = [[block.start // 60, block.start % 60], [block.end // 60, block.end % 60]]
        if block.kind == KIND_LESSON:
            cfg.lessons_time.value[block.key] = value
        else:
            cfg.activity_info.value[block.key] = value

    def edit_block(self, block: TimeBlock):
        try:
            msgbox = BlockEditMsgbox(block, self)
            if not msgbox.exec():
                return
            name, start, end = msgbox.result
            if block.kind == KIND_ACTIVITY and name != block.key:
                # 改名：保持原有顺序重建活动字典
                new_info = {}
                for key, value in cfg.activity_info.value.items():
                    new_info[name if key == block.key else key] = value
                cfg.activity_info.value = new_info
                block.key = name
            block.name = name
            block.start, block.end = start, end
            self.apply_block_to_cfg(block)
            save_settings()
            self.refresh_list()
            self.canvas.refresh_range(*self.compute_range())
            self.canvas.select(block)
            self.canvas.update()
            self.refresh_warnings()
            self.dataChanged.emit()
        except Exception as error:
            logging.critical(f"编辑时间块出错：\n{traceback.format_exc()}")
            show_error(self, error)

    def find_free_slot(self, duration: int) -> int:
        """在时间轴范围内找到一段空闲时间，找不到就放在最后一个时间块之后"""
        low, _ = self.compute_range()
        occupied = [(block.start, block.end) for block in self.blocks if block.end > block.start]
        position = low
        while position + duration <= 24 * 60:
            if all(position + duration <= start or position >= end for start, end in occupied):
                return position
            position += SNAP_MINUTES
        last_end = max([block.end for block in self.blocks], default=low)
        return min(last_end, 24 * 60 - duration)

    def add_activity(self):
        try:
            index = 1
            name = "新活动1"
            while name in cfg.activity_info.value:
                index += 1
                name = f"新活动{index}"
            duration = int(cfg.default_duration.value)
            start = self.find_free_slot(duration)
            cfg.activity_info.value[name] = [[start // 60, start % 60],
                                             [(start + duration) // 60, (start + duration) % 60]]
            save_settings()
            self.reload()
            for block in self.blocks:
                if block.kind == KIND_ACTIVITY and block.key == name:
                    self.canvas.select(block)
                    self.canvas.scroll_to(block)
                    self.on_canvas_selection(block)
                    break
            self.dataChanged.emit()
            logging.info(f"新增活动 {name} {format_clock(start)}-{format_clock(start + duration)}")
            return name
        except Exception as error:
            logging.critical(f"新增活动出错：\n{traceback.format_exc()}")
            show_error(self, error)
            return None

    def duplicate_block(self, block: TimeBlock):
        """以某个时间块的时长为模板新建一个活动"""
        try:
            base = f"{block.name}副本"
            name = base
            index = 1
            while name in cfg.activity_info.value:
                index += 1
                name = f"{base}{index}"
            duration = max(MIN_DURATION, block.duration)
            start = self.find_free_slot(duration)
            cfg.activity_info.value[name] = [[start // 60, start % 60],
                                             [(start + duration) // 60, (start + duration) % 60]]
            save_settings()
            self.reload()
            for new_block in self.blocks:
                if new_block.kind == KIND_ACTIVITY and new_block.key == name:
                    self.canvas.select(new_block)
                    self.canvas.scroll_to(new_block)
                    self.on_canvas_selection(new_block)
                    break
            self.dataChanged.emit()
        except Exception as error:
            logging.critical(f"复制时间块出错：\n{traceback.format_exc()}")
            show_error(self, error)

    def on_delete_shortcut(self):
        """Delete 键：删除选中的活动（输入框内不拦截删除键）"""
        widget = QApplication.focusWidget()
        if isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox)):
            return
        self.delete_selected()

    def delete_selected(self):
        block = self.canvas.selected
        if block is None:
            return
        if block.kind != KIND_ACTIVITY:
            Toast.error("只能删除活动", "课程节次的数量请在设置页面的“课程数量”中调整", parent=self, duration=3000)
            return
        cfg.activity_info.value.pop(block.key, None)
        save_settings()
        self.reload()
        self.dataChanged.emit()
        logging.info(f"删除活动 {block.name}")

    # ---------------------------------------------------------------
    # 顶部卡片
    # ---------------------------------------------------------------
    def set_default_duration(self):
        DefaultDurationMsgbox(self).exec()

    def set_timeline_range(self):
        if TimelineRangeMsgbox(self).exec():
            self.canvas.refresh_range(*self.compute_range())

    # ---------------------------------------------------------------
    # 冲突检查
    # ---------------------------------------------------------------
    def check_conflicts(self) -> list[str]:
        messages: list[str] = []
        valid = [block for block in self.blocks if block.end > block.start]
        for block in self.blocks:
            if block.end <= block.start:
                messages.append(
                    f"{block.name}（{format_clock(block.start)} ~ {format_clock(block.end)}）的结束时间必须晚于开始时间"
                )
        for index, block in enumerate(valid):
            for other in valid[index + 1:]:
                if block.start < other.end and other.start < block.end:
                    messages.append(
                        f"{block.name}（{format_clock(block.start)} ~ {format_clock(block.end)}）"
                        f"与{other.name}（{format_clock(other.start)} ~ {format_clock(other.end)}）时间交叉"
                    )
        if len(messages) > 10:
            messages = messages[:10] + [f"……等共 {len(messages)} 处时间冲突"]
        return messages

    def refresh_warnings(self):
        messages = self.check_conflicts()
        if messages:
            self.banner.show_warning("时间设置有冲突", messages)
        else:
            self.banner.hide_warning()
