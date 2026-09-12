"""
课程表拖拽相关的自定义组件。

- TimeTableWidget        课程表预览的表格（支持表格内拖拽 + 接收从暂存区拖来的课程）
- LessonStoragePane      暂存区容器（接收从表格拖来的课程）
- DraggableLessonCard    暂存区的可拖拽卡片（支持点击/拖拽激活课表高亮）
"""
from typing import Optional,Iterable

from PySide6.QtCore import QMimeData,QPoint
from PySide6.QtGui import (
    QDropEvent,QDragMoveEvent,QDragEnterEvent,QPixmap,QPainter,QBrush,
    QDrag
)
from qfluentwidgets_pro.components.date_time.picker_base import SeparatorWidget
from locals import *
from style import *


# =====================================================================
# 课程表预览表格
# =====================================================================
class TimeTableWidget(TableWidget):
    """课表预览表格：支持两种拖拽来源
       1. 表格内（选中项拖到另一格） -> 执行交换或移动
       2. 暂存区卡片（application/x-stored-lesson-card）-> 放入课程
    """

    # 表格内拖到有课程的位置（emit target_item）
    dropdown = Signal(QTableWidgetItem)
    # 表格内拖拽移动时（用于课表详情显示，历史兼容）
    dragmove = Signal(QTableWidgetItem)
    # 拖到暂存区（历史兼容）
    lesson_storage = Signal(QTableWidgetItem)
    # 暂存区卡片拖放到课表某个位置（emit (row, col)）
    stored_lesson_dropped = Signal(tuple)
    # 暂存区卡片在课表上移动时（emit subject_name）
    stored_lesson_dragmove = Signal(Subject)
    # 表格内拖到空位（emit (row, col)）
    table_dropped_on_empty = Signal(tuple)

    # 最近一次被拖动的暂存区卡片（DraggableLessonCard，由 DraggableLessonCard 设置）
    _dragged_card = None
    # 最近一次表格内拖拽的源 item（QTableWidgetItem，由 startDrag 设置）
    _drag_source_item = None

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self._dragged_item = None

    # ---------------------------------------------------------------
    # 表格内拖拽：记录源位置
    # ---------------------------------------------------------------
    def startDrag(self, supportedActions):
        self._dragged_item = self.currentItem()
        TimeTableWidget._drag_source_item = self.currentItem()

        # 普通文本单元格：交给默认逻辑（默认会按 item 文本渲染预览图）
        row, col = self.currentRow(), self.currentColumn()
        if row < 0 or col < 0 or self.cellWidget(row, col) is None:
            super().startDrag(supportedActions)
            return

        # 使用 setCellWidget 的单元格：QTableWidget 默认不把 cell widget
        # 画进拖拽预览图（它只画 item 的文本/图标），这里手动渲染控件作为预览图
        indexes = self.selectedIndexes()
        if not indexes:
            return
        mime_data = self.model().mimeData(indexes)

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        widget = self.cellWidget(row, col)
        pixmap = self._render_cell_pixmap(widget)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(widget.width() // 2, widget.height() // 2))

        drag.exec(supportedActions)

    @staticmethod
    def _render_cell_pixmap(widget: QWidget) -> QPixmap:
        """把 cell widget 渲染成高 DPI 的拖拽预览图"""
        dpr = widget.devicePixelRatioF() if hasattr(widget, "devicePixelRatioF") else 1.0
        if dpr < 1.0:
            dpr = 1.0
        logical_w = widget.width()
        logical_h = widget.height()

        pixmap = QPixmap(int(logical_w * dpr), int(logical_h * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.transparent)

        # 白色圆角卡片背景（与暂存区卡片视觉一致）
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
        painter.drawRoundedRect(0, 0, logical_w, logical_h, 8, 8)
        painter.end()

        # 把控件（含子控件、badge、分隔线）整体渲染进预览图
        widget.render(pixmap)
        return pixmap

    def get_dragged_item(self):
        return self._dragged_item

    # ---------------------------------------------------------------
    # 接收从暂存区拖来的卡片
    # ---------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat("application/x-stored-lesson-card"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.mimeData().hasFormat("application/x-stored-lesson-card"):
            # 在课表上移动时，告知 Generate 当前拖拽的学科名（用于实时高亮检查）
            try:
                data = bytes(event.mimeData().data("application/x-stored-lesson-card")).decode("utf-8")
                subject_name = data.split("\n")[0]
                self.stored_lesson_dragmove.emit(str2subject(subject_name))
            except Exception:
                pass
            event.acceptProposedAction()
        else:
            self.dragmove.emit(self.currentItem())
            super().dragMoveEvent(event)

    # ---------------------------------------------------------------
    # 拖放落点处理
    # ---------------------------------------------------------------
    def dropEvent(self, event: QDropEvent):
        # 1) 来自暂存区
        if event.mimeData().hasFormat("application/x-stored-lesson-card"):
            row, col = self._cell_at(event.pos())
            if row < 0 or col < 0:
                return
            event.setDropAction(Qt.CopyAction)
            event.accept()
            self.stored_lesson_dropped.emit((row, col))
            return

        # 2) 表格内拖拽
        row, col = self._cell_at(event.pos())
        if row < 0 or col < 0:
            return
        event.accept()
        if self.item(row, col) is not None and self.item(row, col).data(Qt.UserRole):
            # 拖到有内容的格子
            self.dropdown.emit(self.item(row, col))
        else:
            # 拖到空格子
            self.table_dropped_on_empty.emit((row, col))

    # ---------------------------------------------------------------
    # 辅助：把鼠标坐标换算为 (row, col)，越界返回 (-1, -1)
    # ---------------------------------------------------------------
    def _cell_at(self, pos):
        row = self.rowAt(pos.y())
        col = self.columnAt(pos.x())
        if row < 0 or col < 0 or row >= self.rowCount() or col >= self.columnCount():
            return -1, -1
        return row, col


# =====================================================================
# 暂存区容器
# =====================================================================
class LessonStoragePane(QFrame):
    """接收从课表拖入课程的容器（只发射信号，具体新增卡片由 Generate 处理）"""

    lesson_dropped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame{background: transparent;}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent):
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        event.acceptProposedAction()
        self.lesson_dropped.emit()


# =====================================================================
# 可拖拽的暂存课程卡片
# =====================================================================
class DraggableLessonCard(CardWidget):
    """暂存区的课程卡片。
       - 点击（未发生拖动）：发射 card_activated，让课表立刻高亮能否放入
       - 开始拖拽：同样发射 card_activated，然后创建 QDrag 对象并绘制预览图
       - 拖到课表：由 TimeTableWidget / Generate 接收并放入
       - 拖到暂存区内部的其他位置：由 LessonStoragePane 接收并重排卡片顺序
    """

    card_activated = Signal(str,Subject)

    def __init__(self, subject: Subject, teacher: Teacher, remain_num: int = 1, parent=None):
        super().__init__(parent=parent)
        self.subject = subject
        self.teacher = teacher
        self.remain_num = remain_num
        self._drag_start_pos = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        label = BodyLabel()
        label.setText(f"{subject}\n{teacher}")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.setCursor(Qt.PointingHandCursor)

        # 卡片右上角用 badge 标注剩余数量
        # 不使用 InfoBadgeManager：它按 target 父容器坐标系计算位置，
        # 而本场景 parent==target，会导致坐标偏移 & badge 被父容器裁掉。
        # 改为直接把 badge 放在卡片内部，右上角内侧。
        self.badge = InfoBadge.attension(remain_num, self)
        self.badge.adjustSize()
        self._update_badge_pos()
        if remain_num==1:
            self.badge.hide()

    def _update_badge_pos(self):
        """把 badge 放到卡片右上角内侧，避免溢出被截断"""
        margin = 4
        self.badge.move(
            self.width() - self.badge.width() - margin,
            margin,
        )
        self.badge.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_badge_pos()

    # ---------------------------------------------------------------
    # 鼠标事件：区分"点击"和"拖拽"
    # ---------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = self._event_pos(event)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # 点击（移动距离 < 4 像素）→ 视为激活，让课表立刻高亮能否放入
        if event.button() == Qt.LeftButton and self._drag_start_pos is not None:
            current_pos = self._event_pos(event)
            if (current_pos - self._drag_start_pos).manhattanLength() < 4:
                self.card_activated.emit("click",self.subject)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        current_pos = self._event_pos(event)
        if self._drag_start_pos is None or (current_pos - self._drag_start_pos).manhattanLength() < 4:
            return

        # 先激活高亮
        self.card_activated.emit("drag",self.subject)

        # 构造拖拽数据
        mime_data = QMimeData()
        payload = f"{self.subject}\n{self.teacher}".encode("utf-8")
        mime_data.setData("application/x-stored-lesson-card", payload)
        mime_data.setText(self.subject.name)

        # 绘制拖拽预览图
        pixmap = self._render_drag_pixmap()

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(self.width() // 2, self.height() // 2))

        TimeTableWidget._dragged_card = self
        drag.exec(Qt.CopyAction | Qt.MoveAction)
        TimeTableWidget._dragged_card = None

    # ---------------------------------------------------------------
    # 内部辅助
    # ---------------------------------------------------------------
    @staticmethod
    def _event_pos(event):
        """兼容旧版 PySide6：某些版本的 event 没有 position() 方法"""
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def _render_drag_pixmap(self) -> QPixmap:
        """绘制高 DPI 的拖拽预览图，避免在高分屏上出现模糊"""
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        if dpr < 1.0:
            dpr = 1.0
        logical_w = self.width()
        logical_h = self.height()

        pixmap = QPixmap(int(logical_w * dpr), int(logical_h * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 圆角卡片背景
        painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, logical_w, logical_h, 8, 8)

        # 文字（继承控件自身的字体，保证字号与视觉一致）
        painter.setPen(QColor(50, 50, 50))
        font = self.font()
        if font.pointSize() > 0:
            font.setPointSize(max(9, font.pointSize()))
        else:
            font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            0, 0, logical_w, logical_h,
            Qt.AlignCenter,
            f"{self.subject}\n{self.teacher}"
        )

        painter.end()
        return pixmap

def widget_with_badge(label_text:str,badge_text,font:QFont,badge_font:QFont|None=None,badge_type=InfoBadge.error,badge_pos:str="right")->QWidget:
    item_widget=QWidget()
    item_layout=QHBoxLayout(item_widget)
    item_layout.setContentsMargins(0,0,0,0)
    if badge_font is None:
        badge_font=font
    if badge_text and badge_pos=="left":
        badge=badge_type(badge_text)
        badge.setFont(badge_font)
        item_layout.addWidget(badge)
    name_label=BodyLabel()
    name_label.setFont(font)
    name_label.setText(label_text)
    name_label.setWordWrap(True)
    name_label.setAlignment(Qt.AlignCenter)
    item_layout.addWidget(name_label)
    if badge_text and badge_pos=="right":
        badge=badge_type(badge_text)
        badge.setFont(badge_font)
        item_layout.addWidget(badge)
    item_layout.addStretch(1)
    return item_widget

def sindou_widget(sin_text:str,dou_text:str,font:QFont,show_separator=True)->QWidget:
    lesson_widget=QWidget()
    split_layout=QVBoxLayout(lesson_widget)
    split_layout.setContentsMargins(0,0,0,0)
    font.setPointSize(font.pointSize()-2)
    if sin_text:
        single_widget=widget_with_badge(sin_text,"单",font,font,InfoBadge.attension,"left")
        single_layout=QHBoxLayout()
        single_layout.setContentsMargins(0,0,0,0)
        single_layout.addStretch(1)
        add_widget(single_widget,single_layout,0)
        single_layout.addStretch(1)
        split_layout.addLayout(single_layout)
    if show_separator and sin_text and dou_text:
        add_widget(SeparatorWidget(Qt.Horizontal),split_layout,0)
    if dou_text:
        double_widget=widget_with_badge(dou_text,"双",font,font,InfoBadge.warning,"left")
        double_layout=QHBoxLayout()
        double_layout.setContentsMargins(0,0,0,0)
        double_layout.addStretch(1)
        add_widget(double_widget,double_layout,0)
        double_layout.addStretch(1)
        split_layout.addLayout(double_layout)
    return lesson_widget

def display_teachers_timetable(teacher:Teacher,tablewidget:QTableWidget,show_separator=True):
    display_df_in_table(tablewidget,teacher.timetable_dataframe)
    for day in range(1,6):
        for lesson in range(1,cfg.day_class_num+1):
            curr_time=Time(day,lesson)
            curr_item=tablewidget.item(lesson-1,day-1)
            if not curr_item:
                continue
            curr_item.setData(Qt.UserRole,curr_item.text())
            if teacher.timetable[curr_time]:
                continue
            sin_text=dou_text=""
            if teacher.is_busy(curr_time.sin_week):
                sin_text=["",""]
                for sin_clas,sin_subject in teacher.get_lessons(curr_time.sin_week):
                    sin_text[0]+=f"/{sin_clas}"
                    sin_text[1]+=f"/{sin_subject}"
                sin_text[0]=sin_text[0][1:]
                sin_text[1]=sin_text[1][1:]
                sin_text="\n".join(sin_text)
            if teacher.is_busy(curr_time.dou_week):
                dou_text=["",""]
                for dou_clas,dou_subject in teacher.get_lessons(curr_time.dou_week):
                    dou_text[0]+=f"/{dou_clas}"
                    dou_text[1]+=f"/{dou_subject}"
                dou_text[0]=dou_text[0][1:]
                dou_text[1]=dou_text[1][1:]
                dou_text="\n".join(dou_text)
            tablewidget.setCellWidget(lesson-1,day-1,sindou_widget(sin_text,dou_text,tablewidget.font(),show_separator))
            curr_item.setText("")

class ClassMultiSelectionCombobox(MultiSelectionTreeComboBox):
    def __init__(
        self,
        items: Optional[Iterable] = None,
        placeholderText: Optional[str] = None,
        parent: Optional[QWidget] = None,
        check_all:bool=False
    ):
        super().__init__(items, placeholderText, parent)
        self.addItems(cfg.grades_info.value)
        self.setAllItemsChecked(check_all)

    def checkedClasses(self)->list[Class]:
        return [lesson_info.classes[class_name] for class_name in self.checkedTexts()]

class TimeMultiSelectionCombobox(MultiSelectionTreeComboBox):
    """时间多选框：弹出“空课表”网格（列 = 星期，行 = 上午/下午第 x 节）。

    每个空格内是一个多选框，文本为完整的 ``str(Time)``（如“星期一上午第1节”）。
    勾选完成后用 :meth:`checkedTimes` 取回全部 :class:`Time`。
    """

    def __init__(
        self,
        placeholderText: Optional[str] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(None, placeholderText, parent)
        self.setSearchEnabled(False)   # 课表网格无需搜索框

    # ------------------------------------------------------------------ 弹层
    def _hasPopupContent(self) -> bool:
        # 网格数据不来自 _rootItems，始终允许弹出
        return True

    def _createPopup(self):
        colLabels = [days[day] for day in range(1, 6)]
        rowLabels: list[str] = []
        cellTexts: dict[tuple[int, int], str] = {}
        for row, lesson in enumerate(range(1, cfg.day_class_num + 1)):
            rowLabels.append(lesson2str(lesson))
            for col, day in enumerate(range(1, 6)):
                cellTexts[(row, col)] = str(Time(day, lesson))
        return GridMultiSelectPopup(
            self, rowLabels, colLabels, cellTexts, set(self.checkedTexts())
        )

    # ------------------------------------------------------------------ 选择
    def setCheckedTexts(self, texts):
        """按文本设置勾选（时间控件的数据不在树里，覆写以支持回填）。"""
        if isinstance(texts, str):
            texts = [texts]
        self._checked = [TreeComboItem(text=t) for t in texts]
        self._updateText()
        self.checkedItemsChanged.emit(list(self._checked))
        self.checkedTextsChanged.emit(self.checkedTexts())

    def setCheckedTimes(self, times: Iterable[Time]):
        """按 :class:`Time` 列表设置勾选（``setCheckedTexts`` 的语义封装）。"""
        self.setCheckedTexts([str(t) for t in times])

    def setAllItemsChecked(self, checked: bool = True):
        """全选 / 清空所有时间格。"""
        if checked:
            texts = [
                str(Time(day, lesson))
                for lesson in range(1, cfg.day_class_num + 1)
                for day in range(1, 6)
            ]
        else:
            texts = []
        self.setCheckedTexts(texts)

    def checkedTimes(self) -> list[Time]:
        return [Time(string=time_str) for time_str in self.checkedTexts()]