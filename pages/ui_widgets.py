"""
课程表拖拽相关的自定义组件。

- TimeTableWidget        课程表预览的表格（支持表格内拖拽 + 接收从暂存区拖来的课程）
- LessonStoragePane      暂存区容器（接收从表格拖来的课程）
- DraggableLessonCard    暂存区的可拖拽卡片（支持点击/拖拽激活课表高亮）
- WarningBanner          常驻在页面中的多行警告横幅
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
# WarningBanner 警告横幅
# =====================================================================
class WarningBanner(InfoBar):
    """
    常驻在页面布局中的警告横幅。

    与 InfoBar 默认的弹出式用法不同，这里把它当作普通控件插入布局：
    - duration=-1 表示不自动消失，position=NONE 表示不交给 InfoBarManager 管理
    - isClosable 默认 False（横幅常驻，由校验结果控制显隐）；
      需要关闭按钮时传入 isClosable=True，此时与标准 InfoBar 外观一致，
      点击关闭会发出 closedSignal
    - 标题与内容均自动换行，可完整显示多行提示信息
    """

    def __init__(self,parent=None,isClosable=False):
        super().__init__(
            InfoBarIcon.WARNING,"","",
            orient=Qt.Vertical,isClosable=isClosable,
            duration=-1,position=InfoBarPosition.NONE,parent=parent
        )
        self.titleLabel.setWordWrap(True)
        self.contentLabel.setWordWrap(True)
        self._polish_layout()
        self.setVisible(False)

    def _polish_layout(self):
        """按标准 InfoBar 外观微调排版。

        父类默认布局：图标 ↔ textLayout(标题/正文) ↔ 12px 间隔 ↔ 关闭按钮，
        textLayout 在水平方向 stretch=0，标题与正文间距 5px。
        这里做两处调整：
        1. 标题与正文之间留 12px 空行（父类默认 5 显得紧凑）
        2. textLayout 设为 stretch=1，横幅被外层拉宽时文字占据剩余宽度
        若不可关闭，还会把关闭按钮及其间隔移出布局，避免右侧白白占位。
        """
        # 标题与正文之间留 12px 间距（父类默认 5 显得紧凑）
        self.textLayout.setSpacing(12)

        # 不可关闭时移除关闭按钮与其前面的间隔，避免右侧白白占位
        if not self.isClosable and self.closeButton is not None:
            self.closeButton.hide()
            self.closeButton.setFixedSize(0,0)
            self.hBoxLayout.removeWidget(self.closeButton)
            for index in reversed(range(self.hBoxLayout.count())):
                if self.hBoxLayout.itemAt(index).spacerItem() is not None:
                    self.hBoxLayout.takeAt(index)

        # 当外部布局把横幅拉宽时，文字能占据剩余宽度（不撑满也无所谓，靠左对齐）
        expanding=QSizePolicy.Expanding
        self.titleLabel.setSizePolicy(expanding,expanding)
        self.contentLabel.setSizePolicy(expanding,expanding)
        text_index=self.hBoxLayout.indexOf(self.textLayout)
        if text_index>=0:
            self.hBoxLayout.setStretch(text_index,1)

    def _adjustText(self):
        # 覆盖父类实现：父类会按固定宽度截断文本，这里保留完整内容并自动换行
        self.titleLabel.setText(self.title)
        self.contentLabel.setText(self.content)
        self.titleLabel.setVisible(bool(self.title))
        self.contentLabel.setVisible(bool(self.content))
        self.updateGeometry()

    def show_warning(self,title:str,messages:list[str]|str):
        """显示警告横幅，messages 为多行文本时逐行显示"""
        self.title=title
        self.content="\n".join(messages) if isinstance(messages,(list,tuple)) else messages
        self._adjustText()
        self.setVisible(True)

    def hide_warning(self):
        """隐藏警告横幅"""
        self.setVisible(False)


# =====================================================================
# 支持字体调整的表格
# =====================================================================
class FontTableWidget(TableWidget):
    """可通过 setFont() 调整单元格字体的表格控件。

    库自带的 TableItemDelegate 在 initStyleOption 里把单元格字体写死为 13px
    的应用字体（只有 item 设置了 Qt.FontRole 时才使用 item 自己的字体），
    所以直接调用 table.setFont() 对单元格内容无效。
    这里把字体写入每个 item 的 Qt.FontRole，setItem 时自动带上；
    表头字号被 QSS 固定成 13px，额外追加一段样式覆盖它。
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._item_font: QFont | None = None
        self._extra_qss = ""
        # 主题热切换会重设整个样式表，追加的自定义规则需要在之后重新应用
        qconfig.themeChangedFinished.connect(self._apply_extra_qss)

    def setFont(self, font: QFont):
        super().setFont(font)
        self._item_font = QFont(font)
        self._apply_item_font()
        self._apply_extra_qss()

    def setItem(self, row: int, column: int, item: QTableWidgetItem):
        # 新放入的 item 也要用同一字体，否则填表后字体又会回到默认的 13px
        if self._item_font is not None:
            item.setData(Qt.FontRole, self._item_font)
        super().setItem(row, column, item)

    def _apply_item_font(self):
        """把字体写入所有已有 item 的 Qt.FontRole"""
        if self._item_font is None:
            return
        for row in range(self.rowCount()):
            for column in range(self.columnCount()):
                item = self.item(row, column)
                if item is not None:
                    item.setData(Qt.FontRole, self._item_font)

    def _apply_extra_qss(self):
        """覆盖库 QSS：表头字号、单元格左右内边距"""
        if self._item_font is None:
            return
        try:
            # 先移除上一次追加的规则，避免反复 setFont 时样式表无限增长
            if self._extra_qss:
                self.setStyleSheet(self.styleSheet().replace(self._extra_qss, ""))
            size = self._item_font.pointSize()
            size = f"{size}pt" if size > 0 else f"{max(1, self._item_font.pixelSize())}px"
            font_qss = f'QHeaderView::section{{font: {size} "{self._item_font.family()}";}}'
            # 库默认 QTableView::item 左右 padding 为 16px，教师课表列宽较窄，改成 4px 让文字更宽敞
            padding_qss = 'QTableView::item{padding-left:4px;padding-right:4px;}'
            self._extra_qss = font_qss + padding_qss
            self.setStyleSheet(self.styleSheet() + self._extra_qss)
        except RuntimeError:
            pass  # 控件已被销毁（主题切换回调晚于析构）


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
    # 再次按下当前已选中的单元格（emit item，用于"再次点击取消选中"）
    reclicked = Signal(QTableWidgetItem)

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
        self._press_item = None           # 鼠标按下时所在的单元格
        self._press_current_item = None   # 鼠标按下时的当前项（选中项尚未改变）
        self._press_pos = QPoint()        # 鼠标按下位置，用于区分点击与拖拽

    # ---------------------------------------------------------------
    # 鼠标按下/松开：识别"再次点击当前已选中的单元格"
    # ---------------------------------------------------------------
    def mousePressEvent(self, event):
        # 此时选中项尚未变化，先记录状态，真正的判定放到 mouseReleaseEvent
        if event.button() == Qt.LeftButton:
            self._press_item = self.itemAt(event.position().toPoint())
            self._press_current_item = self.currentItem()
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # currentItemChanged 在同一格上再次点击时不会触发，这里额外发信号供"再次点击取消选中"使用。
        # 必须等松开且鼠标几乎没移动（是点击而非拖拽）才判定，
        # 否则从已选中的格子开始拖拽时会先把高亮取消掉
        if (event.button() == Qt.LeftButton and self._press_item is not None
                and self._press_item is self._press_current_item
                and self._press_item is self.currentItem()
                and (event.position().toPoint() - self._press_pos).manhattanLength() < QApplication.startDragDistance()):
            # 双击的第二次按下不会进入 mousePressEvent（走 mouseDoubleClickEvent），
            # 因此这里天然只会切换一次，无需额外判断
            self.reclicked.emit(self._press_item)
        self._press_item = None
        self._press_current_item = None
        super().mouseReleaseEvent(event)

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

class ClassTreeComboBox(TreeComboBox):
    """班级树形下拉单选框：年级（分组）→ 班级（叶子），一次只能选一个班级。

    与 :class:`ClassMultiSelectionCombobox` 共用数据源 ``cfg.grades_info``
    （``{年级名: [班级名, ...]}``），区别只在单/多选：

    * 年级只是分组，点击它只展开 / 收起，不会被当成选项选中；确实需要把年级
      也作为选项时传 ``allowGrade=True``；
    * 读取：:meth:`currentClass` 直接返回 :class:`Class` 对象；
    * 回填：:meth:`setCurrentClass`（传 :class:`Class` 或班级名均可）；
    * 年级 / 班级在设置页被改动后调用 :meth:`reload` 重建树，默认会尝试
      恢复原先选中的班级。
    """

    def __init__(
        self,
        placeholderText: Optional[str] = None,
        parent: Optional[QWidget] = None,
        allowGrade: bool = False
    ):
        super().__init__(None, placeholderText, parent)
        self.allowGrade=allowGrade
        self.reload(keepCurrent=False)

    # ------------------------------------------------------------------ 数据
    def reload(self,keepCurrent:bool=True)->None:
        """按当前 ``cfg.grades_info`` 重建树。

        :param keepCurrent: 重建后是否恢复原先选中的项（默认 ``True``）
        """
        last=self.currentText()
        self.clearItems()
        self.addItems(cfg.grades_info.value)
        if keepCurrent and last:
            self.setCurrentText(last)
        self._updateText()

    # ------------------------------------------------------------------ 选择
    def _onPopupItemClicked(self,node,clickedAllChildren:bool)->None:
        # 年级不是班级：点它只展开 / 收起，不改变当前选择
        if not self.allowGrade and node is not None and not node.isLeaf():
            return
        super()._onPopupItemClicked(node,clickedAllChildren)

    def currentClass(self)->Optional[Class]:
        """当前选中的班级；未选择或当前项是年级时返回 ``None``。"""
        node=self.currentItem()
        if node is None or not node.isLeaf():
            return None
        return lesson_info.classes.get(node.text())

    def currentGrade(self)->Optional[Grade]:
        """当前选中项所属的年级；未选择时返回 ``None``。"""
        node=self.currentItem()
        if node is None:
            return None
        # 选中班级时取其父节点（年级）；选中年级时它本身即年级
        grade_node=node if not node.isLeaf() else node.parent()
        if grade_node is None:
            return None
        return lesson_info.grades.get(grade_node.text())

    def setCurrentClass(self,clas)->bool:
        """按 :class:`Class` 对象或班级名设置当前项。

        :return: 是否设置成功（班级不存在 / 不允许选年级却传入年级时为 ``False``）
        """
        name=clas.name if isinstance(clas,Class) else clas
        if not name:
            return False
        node=self.findItem(name)
        if node is None or (not self.allowGrade and not node.isLeaf()):
            return False
        return self.setCurrentItem(node)

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