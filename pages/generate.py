import os.path

from PySide6 import QtGui
from PySide6.QtCore import QByteArray,QRectF
from PySide6.QtGui import QKeySequence,QShortcut

from core.generate_core import *
from core.save_core import SaveThread
from core.system_notification import send_system_notification
from core.timetable_core import *
from pages.dialogs import *

# 读取配置文件
cfg=load_settings()
colors={"Light":{"yes":QColor(150,255,150),"no":QColor(255,150,150),"curr":QColor(255,255,200),"same":QColor(170,170,255)},
        "Dark":{"yes":QColor(100,200,100),"no":QColor(200,100,100),"curr":QColor(170,170,100),"same":QColor(170,170,255)}}[darkdetect.theme() if darkdetect.theme() else "Light"]

class HistoryIcon(FluentIconBase,Enum):
    """撤销/重做图标（FluentIcon 未内置，直接使用组件自带的 svg 资源）"""

    UNDO="ArrowUndo"
    REDO="ArrowRedo"

    def path(self,theme=Theme.AUTO):
        return f":/qfluentwidgets/images/icons/{self.value}_{getIconColor(theme)}.svg"

class ColorSwatch(QWidget):
    """抗锯齿圆角色块（解决 QSS 圆角在高分屏上的锯齿问题）"""

    def __init__(self, color: QColor, size: int = 16, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QtGui.QPen(QColor(127, 127, 127, 102), 1))
        painter.setBrush(self._color)
        painter.drawRoundedRect(rect, 4, 4)

def make_legend(parent=None) -> QWidget:
    """构建课表高亮配色图例（色块+说明文字），颜色与课表高亮保持一致"""
    legend = QWidget(parent)
    layout = QHBoxLayout(legend)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)
    for key, text in (
        ("yes", "可以调课"),
        ("no", "不可调课"),
        ("curr", "当前选中"),
        ("same", "相同学科"),
    ):
        item = QWidget(legend)
        item_layout = QHBoxLayout(item)
        item_layout.setContentsMargins(0, 0, 0, 0)
        item_layout.setSpacing(6)
        swatch = ColorSwatch(colors[key], parent=item)
        text_label = BodyLabel(text, item)
        text_label.setFont(fonts.button)
        item_layout.addWidget(swatch)
        item_layout.addWidget(text_label)
        layout.addWidget(item)
    return legend

class Generate(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent=parent)
        self.setObjectName("Generate")
        main_layout = QVBoxLayout(self)
        self.check_result:dict[Time,bool]={}
        self.failed_reasons:dict[Time,set]={}
        self.conflict_lessons:dict[Time,set[tuple[Class,Time]]]={}
        self.teacher_pane_teachers:dict[QTableWidget,Teacher]={}  # 右侧教师课程表预览对应的老师
        self.history=TimetableHistory()  # 课表修改历史（撤销/重做）

        # === 创建内容容器 ===
        view=QWidget()
        view.setStyleSheet("QWidget{background: transparent}")
        self.layout = QVBoxLayout(view)

        self.title = title("生成",self,self.layout,10)
        self.title.setFixedHeight(60)

        self.operation_layout=QHBoxLayout()
        self.layout.addLayout(self.operation_layout)
        # 生成课程表按钮
        self.generate_button=PrimaryDropDownPushButton()
        self.generate_button.setText("生成课程表")
        self.generate_button.setIcon(FluentIcon.BRUSH)
        self.generate_button.setFixedSize(160,40)
        self.generate_menu=RoundMenu()
        self.generate_left_action=Action("生成剩余课表",triggered=lambda :self.generate_timetables("left"))
        self.generate_school_action=Action("生成全校课表",triggered=lambda :self.generate_timetables("school"))
        self.generate_grade_action=Action("生成本年段课表",triggered=lambda :self.generate_timetables("grade"))
        self.generate_class_action=Action("生成本班课表",triggered=lambda :self.generate_timetables("class"))
        self.generate_custom_action=Action("生成自定义部分课表",triggered=lambda :self.generate_timetables("custom"))
        self.generate_grade_action.setEnabled(False)
        self.generate_class_action.setEnabled(False)
        self.generate_menu.addActions([self.generate_left_action,self.generate_school_action,self.generate_grade_action,self.generate_class_action,self.generate_custom_action])
        self.generate_button.setMenu(self.generate_menu)
        add_widget(self.generate_button,self.operation_layout,0)

        self.clear_button=PrimaryDropDownPushButton()
        self.clear_button.setText("清空课程表")
        self.clear_button.setIcon(FluentIcon.DELETE)
        self.clear_button.setFixedSize(160,40)
        self.clear_menu=RoundMenu()
        self.clear_school_action=Action("清空全校课表",triggered=lambda:self.clear_timetables("school"))
        self.clear_grade_action=Action("清空本年段课表",triggered=lambda:self.clear_timetables("grade"))
        self.clear_class_action=Action("清空本班课表",triggered=lambda:self.clear_timetables("class"))
        self.clear_custom_action=Action("清空自定义部分课表",triggered=lambda:self.clear_timetables("custom"))
        self.clear_grade_action.setEnabled(False)
        self.clear_class_action.setEnabled(False)
        self.clear_menu.addActions([self.clear_school_action,self.clear_grade_action,self.clear_class_action,self.clear_custom_action])
        self.clear_button.setMenu(self.clear_menu)
        add_widget(self.clear_button,self.operation_layout,0)

        self.save_button=PrimaryDropDownPushButton()
        self.save_button.setText("导出课程表")
        self.save_button.setToolTip("直接导出最终的Excel课程表表格")
        self.save_button.setIcon(FluentIcon.SAVE)
        self.save_button.setFixedSize(160,40)
        self.save_menu=RoundMenu()
        self.save_menu.addAction(Action("全部导出",triggered=lambda :self.save_timetable("all")))
        self.save_menu.addAction(Action("导出班级课表",triggered=lambda :self.save_timetable("classes")))
        self.save_menu.addAction(Action("导出教师课表",triggered=lambda :self.save_timetable("teachers")))
        self.save_menu.addAction(Action("导出班级总表",triggered=lambda :self.save_timetable("total_classes")))
        self.save_menu.addAction(Action("导出教师总表",triggered=lambda :self.save_timetable("total_teachers")))
        self.save_menu.addSeparator()
        self.save_menu.addAction(Action(QtGui.QIcon("images/cses.png"),"导出CSES课表v1",triggered=lambda :self.save_timetable("cses_v1"),toolTip="可直接导入Class Island、Class Widgets等班级大屏课表软件"))
        self.save_menu.addAction(Action(QtGui.QIcon("images/cses.png"),"导出CSES课表v2",triggered=lambda :self.save_timetable("cses"),toolTip="当前部分软件尚未支持，如课表软件提示导入失败请尝试v1版本导入"))
        self.save_button.setMenu(self.save_menu)
        add_widget(self.save_button,self.operation_layout)

        # 撤销 / 重做
        self.undo_button=TransparentToolButton()
        self.undo_button.setIcon(FluentIcon.CANCEL)
        self.undo_button.setToolTip("撤销")
        self.undo_button.clicked.connect(self.undo)
        add_widget(self.undo_button,self.operation_layout)

        self.redo_button=TransparentToolButton()
        self.redo_button.setIcon(HistoryIcon.REDO)
        self.redo_button.setToolTip("重做")
        self.redo_button.clicked.connect(self.redo)
        add_widget(self.redo_button,self.operation_layout)

        # 快捷键：Ctrl+Z 撤销，Ctrl+Y / Ctrl+Shift+Z 重做
        for shortcut in (QShortcut(QKeySequence(QKeySequence.Undo),self),):
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self.undo)
        for shortcut in (QShortcut(QKeySequence(QKeySequence.Redo),self),QShortcut(QKeySequence("Ctrl+Shift+Z"),self)):
            shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self.redo)
        self.refresh_history_actions()

        add_widget(SeparatorWidget(orient=Qt.Vertical),self.operation_layout)
        self.manage_plan_button=DropDownPushButton()
        self.manage_plan_button.setText("管理课程表方案")
        self.manage_plan_button.setToolTip("管理已保存的课程表方案")
        self.manage_plan_button.setIcon(FluentIcon.DICTIONARY)
        self.manage_plan_button.setFixedHeight(40)
        self.manage_plan_menu=RoundMenu()
        self.save_plan_action=Action(FluentIcon.SAVE,"保存当前方案",triggered=self.save_plan,toolTip="保存当前的课程表方案，用于保存当前正在编排的课程表，以便下次加载在当前方案下继续排课")
        self.load_plan_action=Action(FluentIcon.HISTORY,"加载方案",triggered=self.load_plan,toolTip="加载曾经保存的课程表方案，用于在曾经未排好的课程表基础上继续排课")
        self.del_plan_action=Action(FluentIcon.DELETE,"删除方案",triggered=self.del_plan,toolTip="删除已保存的课程表方案")
        self.manage_plan_menu.addActions([self.save_plan_action,self.load_plan_action,self.del_plan_action])
        self.manage_plan_button.setMenu(self.manage_plan_menu)
        add_widget(self.manage_plan_button,self.operation_layout)
        self.refresh_plan_actions()

        self.curr_plan=write("当前方案：无",self,self.operation_layout,0)
        self.curr_plan.setFixedHeight(40)
        self.operation_layout.addStretch(1)

        # 课程表预览
        self.object_splitter=Splitter(Qt.Horizontal)
        self.object_splitter.splitterMoved.connect(self.on_splitter_moved)
        add_widget(self.object_splitter,self.layout,0)

        self.object_pane=QWidget()
        self.object_layout=QVBoxLayout(self.object_pane)
        self.object_search=SearchLineEdit()
        self.object_search.textChanged.connect(self.filter_object_tree)
        add_widget(self.object_search,self.object_layout)

        self.object_tree=TreeWidget(self)
        self.object_tree.setHeaderHidden(True)
        self.object_tree.currentItemChanged.connect(self.change_timetable)
        add_widget(self.object_tree,self.object_layout,0)
        self.object_splitter.addWidget(self.object_pane)
        self.show_object_tree()

        self.preview_splitter=Splitter(Qt.Horizontal)
        self.preview_splitter.splitterMoved.connect(self.on_splitter_moved)
        add_widget(self.preview_splitter,self.layout,0)

        self.timetable_pane=QWidget()
        self.timetable_layout=QVBoxLayout(self.timetable_pane)
        self.timetable_header_layout=QHBoxLayout()
        self.timetable_layout.addLayout(self.timetable_header_layout)
        self.timetable_subheader=subheader("班级课程表",self,self.timetable_header_layout,10)
        self.timetable_header_layout.addStretch(1)
        self.timetable_legend=make_legend(self.timetable_pane)
        self.timetable_legend.hide()
        self.preview_class_scope=ClassMultiSelectionCombobox(check_all=True)
        self.preview_class_scope.checkedTextsChanged.connect(self.refresh_timetable)
        self.preview_class_scope.setMaximumWidth(300)
        self.preview_class_scope.hide()
        self.timetable_header_layout.addWidget(self.preview_class_scope)
        self.timetable_header_layout.addWidget(self.timetable_legend)
        self.timetable_preview=TimeTableWidget(self)
        self.timetable_preview.setContextMenuPolicy(Qt.CustomContextMenu)
        self.timetable_preview.currentItemChanged.connect(self.on_timetable_preview_clicked)
        self.timetable_preview.reclicked.connect(self.on_timetable_preview_reclicked)
        self.timetable_preview.dropdown.connect(self.exchange_lessons)
        self.timetable_preview.dragmove.connect(self.on_drag_move)
        self.timetable_preview.stored_lesson_dropped.connect(self.add_stored_lesson_to_timetable)
        self.timetable_preview.stored_lesson_dragmove.connect(self.on_stored_lesson_dragmove)
        self.timetable_preview.table_dropped_on_empty.connect(self.move_lesson_to_empty)
        self.timetable_preview.lesson_storage.connect(self.store_lesson)
        self.timetable_preview.itemDoubleClicked.connect(self.jump_to_class_from_cell)
        add_widget(self.timetable_preview,self.timetable_layout,0)
        self.store_lesson_subheader=subheader("课程暂存区",self,self.timetable_layout,10)
        self.stored_lesson_cards:list[DraggableLessonCard]=[]
        self._active_stored_subject=None  # 当前选中高亮的暂存课程名
        self.lesson_storage_pane=LessonStoragePane(self)
        self.timetable_layout.addWidget(self.lesson_storage_pane)
        self.lesson_storage_layout=WaterfallLayout(self.lesson_storage_pane)
        self.lesson_storage_layout.setColumnWidth(110)
        self.lesson_storage_pane.lesson_dropped.connect(self.on_storage_dropped)
        self.preview_splitter.addWidget(self.timetable_pane)

        self.teacher_timetable_pane=QWidget()
        self.teacher_timetable_pane.hide()
        self.teacher_timetable_layout=QVBoxLayout(self.teacher_timetable_pane)
        self.teacher_timetable_subheader=subheader("教师课程表",self,self.teacher_timetable_layout,0)
        self.teacher_timetable_preview=QTableWidget()
        self.teacher_timetable_preview.setFont(QFont("Microsoft YaHei", 7))
        self.teacher_timetable_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.teacher_timetable_preview.verticalHeader().setVisible(False)
        self.teacher_timetable_preview.setStyleSheet("QTableWidget { border: none; }")
        self.teacher_timetable_preview.itemDoubleClicked.connect(self.jump_to_class_from_cell)
        add_widget(self.teacher_timetable_preview,self.teacher_timetable_layout,10)

        self.teacher2_timetable_subheader=subheader("教师2课程表",self,self.teacher_timetable_layout,0)
        self.teacher2_timetable_preview=QTableWidget()
        self.teacher2_timetable_preview.setFont(QFont("Microsoft YaHei", 7))
        self.teacher2_timetable_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.teacher2_timetable_preview.verticalHeader().setVisible(False)
        self.teacher2_timetable_preview.setStyleSheet("QTableWidget { border: none; }")
        self.teacher2_timetable_preview.itemDoubleClicked.connect(self.jump_to_class_from_cell)
        add_widget(self.teacher2_timetable_preview,self.teacher_timetable_layout,0)

        self.preview_splitter.addWidget(self.teacher_timetable_pane)
        self.object_splitter.addWidget(self.preview_splitter)
        if cfg.object_splitter_state.value:
            byte_array=QByteArray.fromBase64(cfg.object_splitter_state.value.encode())
            self.object_splitter.restoreState(byte_array)
        if cfg.preview_splitter_state.value:
            byte_array=QByteArray.fromBase64(cfg.preview_splitter_state.value.encode())
            self.preview_splitter.restoreState(byte_array)

        # === 设置滚动区域内容 ===
        main_layout.addWidget(view)
        # 检查是否已配置课程信息
        if not cfg.lessons_info.value:
            Toast.error("请先在设置页面配置课程信息","",duration=-1,parent=self)
            self.setEnabled(False)

        self.progress_toast=Toast.info("正在生成课程表","",duration=-1,parent=self,position=ToastPosition.BOTTOM,isClosable=False)
        self.progress_bar=ProgressBar()
        self.progress_bar.setFixedWidth(400)
        self.progress_bar.setMaximum(100)
        self.progress_toast.addWidget(self.progress_bar,alignment=Qt.AlignCenter)

        self.log_label:BodyLabel=BodyLabel()
        self.progress_toast.addWidget(self.log_label,alignment=Qt.AlignCenter)
        self.stop_generate=PushButton()
        self.stop_generate.setText("停止生成")
        self.progress_toast.addWidget(self.stop_generate,alignment=Qt.AlignCenter)
        self.stop_generate.clicked.connect(lambda :setattr(self.generate_thread,"finish",True))
        self.progress_toast.hide()

    def resizeEvent(self, event: QtGui.QResizeEvent, /) -> None:
        self.set_timetables_size()
        super().resizeEvent(event)

    def show_object_tree(self):
        self.object_tree.clear()
        self.classes_top_item=QTreeWidgetItem()
        self.classes_top_item.setData(0,Qt.UserRole,"班级课表")
        self.total_left_subjects=0
        self.class_items:dict[QTreeWidgetItem,list[QTreeWidgetItem]]={}
        for grade,classes in cfg.grades_info.value.items():
            grade_item=QTreeWidgetItem()
            grade_item.setData(0,Qt.UserRole,grade)
            self.class_items[grade_item]=[]
            grade_left_subjects=0
            for class_name in classes:
                class_item=QTreeWidgetItem()
                class_item.setData(0,Qt.UserRole,class_name)
                grade_item.addChild(class_item)
                self.class_items[grade_item].append(class_item)
                clas=lesson_info.classes[class_name]
                self.object_tree.setItemWidget(class_item,0,widget_with_badge(class_name,len(clas.left_subjects),self.object_tree.font()))

                grade_left_subjects+=len(clas.left_subjects)
                self.total_left_subjects+=len(clas.left_subjects)
            self.classes_top_item.addChild(grade_item)
            self.object_tree.setItemWidget(grade_item,0,widget_with_badge(grade,grade_left_subjects,self.object_tree.font()))
        self.object_tree.addTopLevelItem(self.classes_top_item)
        self.object_tree.setItemWidget(self.classes_top_item,0,widget_with_badge("班级课表",self.total_left_subjects,self.object_tree.font()))

        self.teachers_top_item=QTreeWidgetItem(["教师课表"])
        for teacher in lesson_info.teacher_names:
            self.teachers_top_item.addChild(QTreeWidgetItem([teacher]))
        self.object_tree.addTopLevelItem(self.teachers_top_item)

        self.subjects_top_item=QTreeWidgetItem(["学科课表"])
        for subject in lesson_info.subject_names:
            self.subjects_top_item.addChild(QTreeWidgetItem([subject]))
        self.object_tree.addTopLevelItem(self.subjects_top_item)

        self.class_total_item=QTreeWidgetItem(["班级总表"])
        self.teacher_total_item=QTreeWidgetItem(["教师总表"])
        self.object_tree.addTopLevelItems([self.class_total_item,self.teacher_total_item])
        self.refresh_object_tree()

    def refresh_object_tree(self,class_names=None):
        """刷新对象树上的剩余课程数徽标；class_names 不为 None 时只重建这些班级的徽标"""
        badge_font=InfoBadge.info(1).font()
        class_names=None if class_names is None else set(class_names)
        self.total_left_subjects=sum(len(clas.left_subjects) for clas in lesson_info.class_lst)
        for grade_item,class_items in self.class_items.items():
            grade_name=grade_item.data(0,Qt.UserRole)
            if class_names is not None and not any(class_item.data(0,Qt.UserRole) in class_names for class_item in class_items):
                continue  # 该年段没有变化的班级，整段都不用重建
            grade_left_subjects=0
            for class_item in class_items:
                class_name=class_item.data(0,Qt.UserRole)
                clas=lesson_info.classes[class_name]
                grade_left_subjects+=len(clas.left_subjects)
                if class_names is not None and class_name not in class_names:
                    continue
                self.object_tree.setItemWidget(class_item,0,widget_with_badge(class_name,len(clas.left_subjects),self.object_tree.font(),badge_font))
            self.object_tree.setItemWidget(grade_item,0,widget_with_badge(grade_name,grade_left_subjects,self.object_tree.font(),badge_font))
        self.object_tree.setItemWidget(self.classes_top_item,0,widget_with_badge("班级课表",self.total_left_subjects,self.object_tree.font(),badge_font))

    def filter_object_tree(self,keyword:str):
        keyword=str(keyword).strip().lower()
        # 班级课表：匹配班级或年级名称
        grade_matches_any=False
        for g in range(self.classes_top_item.childCount()):
            grade_item=self.classes_top_item.child(g)
            grade_match=keyword in grade_item.data(0,Qt.UserRole).lower()
            class_any_match=False
            for c in range(grade_item.childCount()):
                class_item=grade_item.child(c)
                class_match=keyword in class_item.data(0,Qt.UserRole).lower() or grade_match
                class_item.setHidden(not class_match)
                if class_match:
                    class_any_match=True
            grade_item.setHidden(not class_any_match and not grade_match)
            if not grade_item.isHidden():
                grade_matches_any=True
        self.classes_top_item.setHidden(False)

        # 教师课表：匹配教师姓名
        teacher_matches_any=False
        for t in range(self.teachers_top_item.childCount()):
            teacher_item=self.teachers_top_item.child(t)
            match=keyword in teacher_item.text(0).lower()
            teacher_item.setHidden(not match)
            if match:
                teacher_matches_any=True

        # 学科课表：匹配学科名称
        subject_matches_any=False
        for s in range(self.subjects_top_item.childCount()):
            subject_item=self.subjects_top_item.child(s)
            match=keyword in subject_item.text(0).lower()
            subject_item.setHidden(not match)
            if match:
                subject_matches_any=True

        # 总表项目：在搜索时总是显示，便于快速查看
        self.class_total_item.setHidden(False)
        self.teacher_total_item.setHidden(False)

        # 如果有关键字，自动展开匹配项，否则保持默认
        if keyword:
            self.classes_top_item.setExpanded(grade_matches_any)
            for g in range(self.classes_top_item.childCount()):
                grade_item=self.classes_top_item.child(g)
                if not grade_item.isHidden():
                    grade_item.setExpanded(True)
            self.teachers_top_item.setExpanded(teacher_matches_any)
            self.subjects_top_item.setExpanded(subject_matches_any)
        else:
            self.classes_top_item.setExpanded(False)
            for g in range(self.classes_top_item.childCount()):
                self.classes_top_item.child(g).setExpanded(False)
            self.teachers_top_item.setExpanded(False)
            self.subjects_top_item.setExpanded(False)

    def set_timetables_size(self):
        if not hasattr(self,"preview_mode"):
            return
        QApplication.processEvents()
        if self.preview_mode in ["class","teacher","subject"]:
            for row in range(self.timetable_preview.rowCount()):
                self.timetable_preview.setRowHeight(row,(self.timetable_preview.height()-40)//self.timetable_preview.rowCount())
            for col in range(self.timetable_preview.columnCount()):
                self.timetable_preview.setColumnWidth(col,(self.timetable_preview.width()-90)//self.timetable_preview.columnCount())

            for row in range(self.teacher_timetable_preview.rowCount()):
                self.teacher_timetable_preview.setRowHeight(row,40)
            for col in range(self.teacher_timetable_preview.columnCount()):
                self.teacher_timetable_preview.setColumnWidth(col,self.teacher_timetable_preview.width()//self.teacher_timetable_preview.columnCount())

            for row in range(self.teacher2_timetable_preview.rowCount()):
                self.teacher2_timetable_preview.setRowHeight(row,40)
            for col in range(self.teacher2_timetable_preview.columnCount()):
                self.teacher2_timetable_preview.setColumnWidth(col,self.teacher2_timetable_preview.width()//self.teacher2_timetable_preview.columnCount())
        else:
            for row in range(self.timetable_preview.rowCount()):
                self.timetable_preview.setRowHeight(row,60)
            for col in range(self.timetable_preview.columnCount()):
                self.timetable_preview.setColumnWidth(col,110)

    def on_splitter_moved(self):
        cfg.preview_splitter_state.value=bytes(self.preview_splitter.saveState().toBase64()).decode()
        cfg.object_splitter_state.value=bytes(self.object_splitter.saveState().toBase64()).decode()
        save_settings()
        self.set_timetables_size()

    # ==================== 撤销 / 重做 ====================
    def history_extra(self)->dict:
        """随历史快照一起保存的界面状态"""
        return {"saved":lesson_info.saved,"plan_text":self.curr_plan.text()}

    def push_history(self,snapshot:tuple|None=None):
        """记录一步可撤销的操作，应在修改课表之前调用"""
        if snapshot is None:
            snapshot=self.history.snapshot(self.history_extra())
        self.history.push(snapshot)
        self.refresh_history_actions()

    def apply_history_extra(self,snapshot:tuple):
        """恢复随快照保存的界面状态（课表数据由 TimetableHistory 恢复）"""
        if "plan_text" in snapshot[1]:
            self.curr_plan.setText(snapshot[1]["plan_text"])

    def refresh_history_actions(self):
        """根据撤销/重做栈刷新按钮状态"""
        self.undo_button.setEnabled(self.history.can_undo)
        self.redo_button.setEnabled(self.history.can_redo)

    def update_timetable_cells(self,clas:Class,times):
        """只更新课表中发生变化的格子，不重绘整张表"""
        for curr_time in times:
            row,column=curr_time.lesson-1,curr_time.day-1
            subjects=clas.get_lessons(curr_time)
            if not subjects:  # 变成空位：与整体重绘保持一致，不保留单元格
                if self.timetable_preview.cellWidget(row,column) is not None:
                    self.timetable_preview.removeCellWidget(row,column)
                if self.timetable_preview.item(row,column) is not None:
                    self.timetable_preview.takeItem(row,column)
                continue
            item=self.timetable_preview.item(row,column)
            if item is None:  # 该位置原本是空位，没有 item
                item=QTableWidgetItem("")
                item.setTextAlignment(Qt.AlignCenter)
                self.timetable_preview.setItem(row,column,item)
            if len(subjects)>=2:  # 单双周两节课：用上下分隔的控件显示
                sin_text=subjects[0].name+("\n"+str(clas.get_teacher(subjects[0])) if cfg.show_teachers.value else "")
                dou_text=subjects[1].name+("\n"+str(clas.get_teacher(subjects[1])) if cfg.show_teachers.value else "")
                self.timetable_preview.setCellWidget(row,column,sindou_widget(sin_text,dou_text,self.timetable_preview.font()))
                item.setText("")
            else:
                if self.timetable_preview.cellWidget(row,column) is not None:
                    self.timetable_preview.removeCellWidget(row,column)
                item.setText(str(subjects[0])+("\n"+str(clas.get_teacher(subjects[0])) if cfg.show_teachers.value else ""))
            item.setData(Qt.UserRole,item.text())

    def on_history_restored(self,changed:dict[str,set[Time]]|None=None):
        """撤销/重做后刷新界面：只更新发生变化的部分"""
        self.hide_lesson_details()
        self.refresh_history_actions()
        if not changed:  # 不知道变化范围时才整体刷新
            self.refresh_object_tree()
            self.refresh_timetable()
            return
        changed={class_name:times for class_name,times in changed.items() if times}
        if not changed:
            return
        self.refresh_object_tree(changed.keys())  # 只重建受影响班级的徽标
        if getattr(self,"preview_mode",None)=="class":
            times=changed.get(self.preview_object.name)
            if times:
                self.update_timetable_cells(self.preview_object,times)  # 只改变化的格子
                self.show_stored_lesson_cards()  # 暂存区剩余数量可能变化
        else:
            self.refresh_timetable()  # 教师/学科/总表预览无法按格更新

    def undo(self):
        """撤销上一步对课表的修改"""
        if not self.history.can_undo or not self.generate_button.isEnabled():
            return  # 没有可撤销的操作或正在生成课程表
        result=self.history.undo(self.history.snapshot(self.history_extra()))
        if result is None:
            return
        self.apply_history_extra(result[0])
        self.on_history_restored(result[1])
        logging.info(f"已撤销上一步操作，还可撤销 {len(self.history.undo_stack)} 步")

    def redo(self):
        """重做被撤销的修改"""
        if not self.history.can_redo or not self.generate_button.isEnabled():
            return  # 没有可重做的操作或正在生成课程表
        result=self.history.redo(self.history.snapshot(self.history_extra()))
        if result is None:
            return
        self.apply_history_extra(result[0])
        self.on_history_restored(result[1])
        logging.info(f"已重做一步操作，还可重做 {len(self.history.redo_stack)} 步")

    def clear_timetables(self,clear_object):
        if not lesson_info.saved:
            msgbox=MessageBox("确定清空课程表？","这会使所选范围内班级课表的所有修改丢失，建议先保存当前课程表方案，是否继续清空？",self)
            if not msgbox.exec():
                return

        if clear_object=="school":
            logging.info("清空全校课表")
            class_lst=lesson_info.class_lst
        elif clear_object=="grade":
            logging.info("清空年段课表")
            if self.preview_mode=="grade":
                class_lst=[lesson_info.classes[class_name] for class_name in cfg.grades_info.value[self.preview_object]]
            else:
                for grade,class_names in cfg.grades_info.value.items():
                    if self.preview_object.name in class_names:
                        class_lst=[lesson_info.classes[class_name] for class_name in class_names]
                        break
        elif clear_object=="class":
            logging.info("清空班级课表")
            class_lst=[self.preview_object]
        elif clear_object=="custom":
            logging.info("自定义清空课表")
            custom_msgbox=SelectCustomClassesMsgbox("clear",self)
            if not custom_msgbox.exec():
                return
            class_lst=[]
            for item in custom_msgbox.class_combo.selectedItems():
                class_lst.append(lesson_info.classes[item.text])

        self.push_history()
        for clas in class_lst:
            clas.reset()
        self.refresh_timetable()
        self.refresh_object_tree()

    def generate_timetables(self,generate_object):
        try:
            logging.debug(f"当前配置：{len(lesson_info.class_names)}个班级，{len(lesson_info.subjects)}个科目，{len(lesson_info.teachers)}个老师")

            if not lesson_info.saved:
                msgbox=MessageBox("确定重新生成课程表？","重新生成会使所选范围内班级课表的所有修改丢失，建议先保存当前课程表方案，是否继续重新生成？",self)
                if not msgbox.exec():
                    return

            if generate_object=="left":
                logging.info("生成剩余课表")
                class_lst="left"
            elif generate_object=="school":
                logging.info("生成全校课表")
                class_lst=lesson_info.class_lst
            elif generate_object=="grade":
                logging.info("生成年段课表")
                class_lst=self.preview_grade.classes
            elif generate_object=="class":
                logging.info("生成班级课表")
                class_lst=[self.preview_object]
            elif generate_object=="custom":
                logging.info("自定义生成课表")
                custom_msgbox=SelectCustomClassesMsgbox("generate",self)
                if not custom_msgbox.exec():
                    return
                class_lst=custom_msgbox.class_combo.checkedClasses()

            self.push_history()
            # 禁用生成按钮防止重复点击
            self.generate_button.setEnabled(False)
            self.load_plan_action.setEnabled(False)
            self.progress_toast.show()
            self.progress_bar.setValue(0)

            # 创建并启动线程
            self.generate_start_time=time.time()
            self.generate_thread=GenerateThread(class_lst)
            self.generate_thread.finished_signal.connect(self.on_generation_finished)
            self.generate_thread.progress_signal.connect(self.on_progress_update)
            QTimer.singleShot(500,self.generate_thread.start)
            logging.info("课程表生成线程已启动")
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"生成课程表出错：\n{e}")
            show_error(self,error)

    def on_generation_finished(self,skipped_lessons:set[tuple[Class,Time]]):
        logging.info("排课已完成")
        if skipped_lessons:
            skipped_text="、".join(f"{clas} {time}" for clas,time in list(skipped_lessons)[:3])
            notify_message=f"课表生成完成，有 {len(skipped_lessons)} 节课未自动安排"
            notify_message+=f"：{skipped_text}" if len(skipped_lessons)<=3 else f"，如 {skipped_text}"
            notify_message+="，请手动调整"
        else:
            notify_message="所有课程均已安排完成"
        send_system_notification("排课完成",notify_message)

        Toast.success("自动排课完成","跳过了以下课程：\n"+"\n".join([f"{clas} {time}" for clas,time in skipped_lessons]) if skipped_lessons else "没有跳过课程",duration=-1 if skipped_lessons else 4000,parent=self)
        lesson_info.saved=False
        self.generate_button.setEnabled(True)
        self.refresh_plan_actions()
        self.curr_plan.setText("当前方案：未保存")
        self.progress_toast.hide()
        self.refresh_object_tree()
        self.refresh_timetable()

    def show_check_result(self,source_subjects:list[Subject],source_time:Time|None,exchange:bool=True):
        clas=self.preview_object
        rows=self.timetable_preview.rowCount()
        cols=self.timetable_preview.columnCount()
        # 由后端计算每个位置能否放置，这里只负责染色
        self.check_result,self.failed_reasons,self.conflict_lessons=check_placement(clas,source_subjects,source_time,exchange)
        for j in range(cols):
            for i in range(rows):
                target_time=Time(j+1,i+1)
                target_subjects=clas.get_lessons(target_time)
                can_place=self.check_result[target_time]
                # 获取或创建 item，然后设置背景色
                item=self.timetable_preview.item(i,j)
                if not item:
                    item=QTableWidgetItem("")
                    item.setTextAlignment(Qt.AlignCenter)
                    self.timetable_preview.setItem(i,j,item)
                if target_subjects==source_subjects:
                    item.setBackground(colors["same"])
                    self.check_result[target_time]=False
                    item.setToolTip("相同学科")
                elif can_place:
                    item.setBackground(colors["yes"])
                    item.setToolTip("可以调课")
                else:
                    item.setBackground(colors["no"])
                    item.setToolTip("不可调课，原因：\n"+"\n".join(self.failed_reasons[target_time]))
        if exchange and source_time:
            source_item=self.timetable_preview.item(source_time.lesson-1,source_time.day-1)
            if source_item:
                source_item.setBackground(colors["curr"])
                source_item.setToolTip("当前选中（再次点击可取消）")
        self.timetable_legend.show()

    def on_drag_move(self,curr_item:QTableWidgetItem):
        if not curr_item:
            return
        curr_time=Time(curr_item.column()+1,curr_item.row()+1)
        self.show_lesson_details(self.preview_object.get_lessons(curr_time),curr_time)

    def on_stored_lesson_dragmove(self,target_subject:Subject):
        """暂存区卡片在课表上移动时，检查每个位置能否放入"""
        try:
            if self.preview_mode!="class":
                return
            self.show_check_result([target_subject],None,exchange=False)
        except Exception as error:
            logging.debug(f"暂存课程拖拽预览出错：{error}")

    def show_lesson_details(self,source_subjects:list[Subject],curr_time:Time|None,exchange:bool=True):
        try:
            if self.preview_mode!="class" or not source_subjects:
                return
            clas=self.preview_object
            self.show_check_result(source_subjects,curr_time,exchange)

            teacher=clas.get_teacher(source_subjects[0])
            display_teachers_timetable(teacher,self.teacher_timetable_preview,False)
            self.teacher_pane_teachers[self.teacher_timetable_preview]=teacher
            self.teacher_timetable_subheader.setText(f"任课教师 {teacher.name} 课程表")
            if curr_time:
                teacher_item=self.teacher_timetable_preview.item(curr_time.lesson-1,curr_time.day-1)
                if teacher_item:
                    teacher_item.setBackground(colors["curr"])
            if len(source_subjects)==2:
                teacher2=clas.get_teacher(source_subjects[1])
                display_teachers_timetable(teacher2,self.teacher2_timetable_preview,False)
                self.teacher_pane_teachers[self.teacher2_timetable_preview]=teacher2
                self.teacher_timetable_subheader.setText(f"单周任课教师 {teacher.name} 课程表")
                self.teacher2_timetable_subheader.setText(f"双周任课教师 {teacher2.name} 课程表")
                if curr_time:
                    teacher_item=self.teacher2_timetable_preview.item(curr_time.lesson-1,curr_time.day-1)
                    if teacher_item:
                        teacher_item.setBackground(colors["curr"])
                self.teacher2_timetable_subheader.show()
                self.teacher2_timetable_preview.show()
            else:
                self.teacher2_timetable_subheader.hide()
                self.teacher2_timetable_preview.hide()
            self.teacher_timetable_pane.show()
            self.set_timetables_size()
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"点击课程表出错：\n{e}")
            show_error(self,error)

    def hide_lesson_details(self):
        """清除课表所有高亮颜色"""
        try:
            for j in range(self.timetable_preview.columnCount()):
                for i in range(self.timetable_preview.rowCount()):
                    item=self.timetable_preview.item(i,j)
                    if item:
                        item.setBackground(QtGui.QBrush(Qt.NoBrush))
                        item.setToolTip("")
            self._active_stored_subject=None
            self.timetable_legend.hide()
            self.teacher_timetable_pane.hide()
        except Exception as error:
            logging.debug(f"清除课表高亮出错：{error}")

    def on_timetable_preview_clicked(self):
        """选中项变化时显示课程详情（同一格上再次点击不会触发该信号）"""
        if self.preview_mode!="class":
            return
        curr_item=self.timetable_preview.currentItem()
        if not curr_item:
            return
        if curr_item.background()==colors["curr"]:
            self.hide_lesson_details()
            return
        curr_time=Time(curr_item.column()+1,curr_item.row()+1)
        self.show_lesson_details(self.preview_object.get_lessons(curr_time),curr_time)

    def on_timetable_preview_reclicked(self,item:QTableWidgetItem):
        """再次单击当前单元格：在"选中"与"取消选中"之间切换"""
        try:
            if self.preview_mode!="class" or item is None:
                return
            curr_item=self.timetable_preview.currentItem()
            if curr_item is not item:
                return
            curr_time=Time(item.column()+1,item.row()+1)
            if curr_item.background()==colors["curr"]:  # 已选中 -> 取消选中
                self.hide_lesson_details()
                logging.debug(f"取消选中 {curr_time}")
                return
            self.show_lesson_details(self.preview_object.get_lessons(curr_time),curr_time)  # 未选中 -> 重新选中
        except Exception as error:
            logging.debug(f"取消选中课程出错：{error}")

    def collect_double_clicked_lessons(self,item:QTableWidgetItem)->tuple[str,list[tuple[Class,Subject,Time]]]:
        """收集双击位置上可跳转的课程，返回(弹窗标题,课程列表)"""
        try:
            table=self.sender()
            if table is self.timetable_preview:  # 主预览区
                if self.preview_mode=="teacher" and isinstance(self.preview_object,Teacher):
                    lessons=get_teacher_lessons_at_cell(self.preview_object,item.row(),item.column())
                    return f"{self.preview_object.name}老师在该位置共有{len(lessons)}节课",lessons
                if self.preview_mode=="subject" and isinstance(self.preview_object,Subject):
                    lessons=get_subject_lessons_at_cell(self.preview_object,item.row(),item.column(),self.preview_class_scope.checkedClasses())
                    return f"{self.preview_object.name}在该位置共有{len(lessons)}节课",lessons
                return "",[]
            teacher=self.teacher_pane_teachers.get(table) if isinstance(table,QTableWidget) else None  # 右侧任课教师课程表
            if teacher is None:
                return "",[]
            lessons=get_teacher_lessons_at_cell(teacher,item.row(),item.column())
            return f"{teacher.name}老师在该位置共有{len(lessons)}节课",lessons
        except Exception as error:
            logging.debug(f"收集双击位置的课程出错：{error}")
        return "",[]

    def jump_to_class_from_cell(self,item:QTableWidgetItem):
        """双击课程表上的课程时，跳转到对应班级的对应课程"""
        try:
            if item is None:
                return
            title,lessons=self.collect_double_clicked_lessons(item)
            if not lessons:
                if self.sender() is not self.timetable_preview or self.preview_mode not in ("teacher","subject"):
                    return  # 班级课表/未知来源：不需要跳转，也不提示
                logging.info("双击的位置没有课程，无需跳转")
                return
            if len(lessons)>1:  # 该位置有多节课，让用户选择跳转到哪一节
                dialog=ChooseLessonMsgbox(title,lessons,self)
                if not dialog.exec() or dialog.selected_lesson is None:
                    logging.info("用户取消了跳转到班级课程")
                    return
                clas,subject,curr_time=dialog.selected_lesson
            else:
                clas,subject,curr_time=lessons[0]
            logging.info(f"跳转到 {clas} 在 {curr_time} 的 {subject} 课")
            self.goto_class_lesson(clas,curr_time)
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"跳转到班级课程出错：\n{e}")
            show_error(self,error)

    def find_class_item(self,class_name:str)->tuple[QTreeWidgetItem|None,QTreeWidgetItem|None]:
        """在对象树中查找班级所在项，返回(年级项,班级项)"""
        for grade_item,class_items in self.class_items.items():
            for class_item in class_items:
                if class_item.data(0,Qt.UserRole)==class_name:
                    return grade_item,class_item
        return None,None

    def goto_class_lesson(self,clas:Class,curr_time:Time):
        """切换到指定班级的课程表并选中指定位置"""
        try:
            grade_item,class_item=self.find_class_item(clas.name)
            if class_item is None:
                logging.warning(f"对象树中未找到班级 {clas.name}，无法跳转")
                return
            if class_item.isHidden():  # 被搜索关键字隐藏时清空搜索
                self.object_search.clear()
            if grade_item is not None:
                grade_item.setExpanded(True)
            self.classes_top_item.setExpanded(True)
            if self.object_tree.currentItem() is class_item:
                self.change_timetable()
            else:
                self.object_tree.setCurrentItem(class_item)
            self.object_tree.scrollToItem(class_item)
            target_time=curr_time.all_week
            self.timetable_preview.setCurrentCell(target_time.lesson-1,target_time.day-1)
            self.timetable_preview.setFocus()
        except Exception as error:
            logging.debug(f"跳转到班级 {clas.name} 出错：{error}")
            raise

    def on_storage_dropped(self):
        if self.preview_mode!="class":
            return
        dragged_item=self.timetable_preview.get_dragged_item()
        if dragged_item:
            self.store_lesson(dragged_item)

    def show_stored_lesson_cards(self):
        self.store_lesson_subheader.show()
        self.lesson_storage_pane.show()
        for card in self.stored_lesson_cards:
            self.lesson_storage_layout.removeWidget(card)
            card.deleteLater()
        self.stored_lesson_cards.clear()
        # 相同科目整合为一张卡片（按名称去重，保持原顺序），badge 标注剩余数量
        unique_subjects=list(dict.fromkeys(self.preview_object.left_subjects))
        for subject in unique_subjects:
            remain_num=self.preview_object.get_subject_left_num(subject)
            card=DraggableLessonCard(subject,self.preview_object.get_teacher(subject),remain_num=remain_num)
            # 点击或开始拖拽卡片时在课表立刻高亮能否放入
            card.card_activated.connect(self.on_stored_card_activated)
            self.lesson_storage_layout.addWidget(card)
            self.stored_lesson_cards.append(card)

    def on_stored_card_activated(self,mode:str,target_subject:Subject):
        """用户点击或开始拖拽暂存卡片时：立刻在课表上染色显示能否放入"""
        try:
            if self.preview_mode!="class":
                return
            if mode=="click" and self._active_stored_subject==target_subject:
                self.hide_lesson_details()
                return
            # 记录当前激活的课程
            self._active_stored_subject=target_subject
            # 用 exchange=False 遍历高亮（只看每个目标位置能否放入）
            self.show_lesson_details([target_subject],None,exchange=False)
            logging.debug(f"激活暂存卡片：{target_subject}，已更新课表高亮")
        except Exception as error:
            logging.debug(f"激活暂存卡片高亮出错：{error}")

    def add_stored_lesson_to_timetable(self,target_pos:tuple):
        """将暂存区的一张课程卡片添加到课程表目标位置 (row,col)"""
        try:
            if self.preview_mode!="class":
                return
            dragged_card=TimeTableWidget._dragged_card
            if not dragged_card:
                return
            row,col=target_pos
            clas=self.preview_object
            target_time=Time(col+1,row+1)
            source_subject=dragged_card.subject
            logging.info(f"将暂存课程拖入课表位置：{target_time}")
            
            # 先检查新课程能否放入（不管目标位置是否已有课程）
            force=False
            before=self.history.snapshot(self.history_extra())
            if not self.check_result[target_time]:
                if not self.ask_force(target_time):
                    return
                else:
                    force=True
            self.push_history(before)
            # 目标位置已有课程：先把原课程移入暂存区
            target_subjects=clas.get_lessons(target_time)
            if len(target_subjects)==1 and target_subjects[0] in self.preview_object.half_subjects and not force and check(clas,target_time.dou_week,source_subject):
                clas.add_lesson(target_time.dou_week,source_subject)
            elif not target_subjects and source_subject in self.preview_object.half_subjects:
                clas.add_lesson(target_time.sin_week,source_subject)
            else:
                logging.debug(f"目标位置已有课程，先将其移入暂存区")
                clas.remove_lesson(target_time)
                self.show_stored_lesson_cards()
                # 添加新课程
                clas.add_lesson(target_time,source_subject)
            self.refresh_object_tree()
            self.refresh_timetable(False)
            self.show_lesson_details(clas.get_lessons(target_time),target_time)
            self.set_timetables_size()
            lesson_info.saved=False
            logging.info(f"暂存课程成功放入课表")
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"添加暂存课程出错：\n{e}")
            show_error(self,error)

    def move_lesson_to_empty(self,target_pos:tuple):
        """表格内：将被拖的课程移动到空位 (row,col)"""
        try:
            if self.preview_mode!="class":
                return
            source_item=TimeTableWidget._drag_source_item
            if not source_item:
                return
            row,col=target_pos
            clas=self.preview_object
            target_time=Time(col+1,row+1)
            source_time=Time(source_item.column()+1,source_item.row()+1)
            logging.info(f"移动课程：{source_time} 到 {target_time}")
            
            # 目标位置已有课程：不应走此分支（已有课程走 exchange_lesson）
            if clas.get_lessons(target_time):
                return
            source_subjects=clas.get_lessons(source_time)
            if not source_subjects:
                return
            before=self.history.snapshot(self.history_extra())
            # 检查能否放下
            if not self.check_result[target_time]:
                logging.info(f"课程不能移动到目标位置")
                if not self.ask_force(target_time):
                    return
            self.push_history(before)
            # 先移除源位置，再添加到目标位置
            clas.remove_lesson(source_time)
            for s in source_subjects:
                clas.add_lesson(target_time,s)
            self.refresh_timetable()
            self.show_lesson_details(source_subjects,target_time)
            lesson_info.saved=False
            logging.info(f"课程移动成功")
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"移动课程出错：\n{e}")
            show_error(self,error)

    def store_lesson(self,lesson_item:QTableWidgetItem):
        try:
            curr_time=Time(lesson_item.column()+1,lesson_item.row()+1)
            subjects=self.preview_object.get_lessons(curr_time)
            if not subjects or (curr_time,subjects[0]) in self.preview_object.set_lessons.items():
                return
            self.push_history()
            self.preview_object.remove_lesson(curr_time)
            self.refresh_timetable()
            lesson_info.saved=False
            self.refresh_object_tree()
        except RuntimeError:
            pass

    def exchange_lessons(self,target_item:QTableWidgetItem):
        try:
            if self.preview_mode!="class":
                return
            curr_item=self.timetable_preview.currentItem()
            if not curr_item:
                return
            clas=self.preview_object
            curr_time=Time(curr_item.column()+1,curr_item.row()+1)
            curr_subjects=clas.get_lessons(curr_time)
            target_time=Time(target_item.column()+1,target_item.row()+1)
            target_subjects=clas.get_lessons(target_time)
            
            logging.info(f"交换课程：{curr_time} 与 {target_time}")
            
            before=self.history.snapshot(self.history_extra())
            if not self.check_result[target_time]:
                if curr_subjects==target_subjects or not self.ask_force(target_time):
                    return
            self.push_history(before)
            clas.exchange_lessons(curr_time,target_time)

            self.refresh_timetable(False)
            self.refresh_object_tree()
            self.timetable_preview.setCurrentCell(target_time.lesson-1,target_time.day-1)
            self.show_lesson_details(curr_subjects,target_time)
            self.set_timetables_size()
            lesson_info.saved=False
            logging.info(f"课程交换成功")
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"交换课程出错：\n{e}")
            show_error(self,error)

    def refresh_timetable(self,set_size=True):
        if not hasattr(self,"preview_mode"):
            return
        if self.preview_mode=="total_classes":
            display_df_in_table(self.timetable_preview,class_total_dataframe())
            self.store_lesson_subheader.hide()
            self.lesson_storage_pane.hide()
            self.timetable_legend.hide()
            if set_size:
                self.set_timetables_size()
        elif self.preview_mode=="total_teachers":
            display_df_in_table(self.timetable_preview,teacher_total_dataframe())
            self.store_lesson_subheader.hide()
            self.lesson_storage_pane.hide()
            self.timetable_legend.hide()
            if set_size:
                self.set_timetables_size()
        elif self.preview_mode=="teacher":
            self.store_lesson_subheader.hide()
            self.lesson_storage_pane.hide()
            display_teachers_timetable(self.preview_object,self.timetable_preview)
            self.timetable_legend.hide()
            if set_size:
                self.set_timetables_size()
        elif self.preview_mode=="class":
            display_df_in_table(self.timetable_preview,self.preview_object.timetable_dataframe)
            for day in range(1,6):
                for lesson in range(1,cfg.day_class_num+1):
                    curr_time=Time(day,lesson)
                    curr_item=self.timetable_preview.item(lesson-1,day-1)
                    if not curr_item:
                        continue
                    curr_subjects=self.preview_object.get_lessons(curr_time)
                    curr_item.setData(Qt.UserRole,curr_item.text())
                    if len(curr_subjects)<2:
                        continue
                    sin_text=curr_subjects[0].name+("\n"+self.preview_object.get_teacher(curr_subjects[0]).name if cfg.show_teachers.value else "")
                    dou_text=curr_subjects[1].name+("\n"+self.preview_object.get_teacher(curr_subjects[1]).name if cfg.show_teachers.value else "")
                    self.timetable_preview.setCellWidget(lesson-1,day-1,sindou_widget(sin_text,dou_text,self.timetable_preview.font()))
                    self.timetable_preview.setCellWidget(lesson-1,day-1,sindou_widget(sin_text,dou_text,self.timetable_preview.font()))
                    curr_item.setText("")
            self.timetable_legend.hide()
            self.show_stored_lesson_cards()
            if set_size:
                self.set_timetables_size()
        elif self.preview_mode=="subject":
            display_df_in_table(self.timetable_preview,self.preview_object.timetable_dataframe(self.preview_class_scope.checkedClasses()))
            self.store_lesson_subheader.hide()
            self.lesson_storage_pane.hide()
            self.timetable_legend.hide()
            if set_size:
                self.set_timetables_size()

    def change_timetable(self,set_size=True):
        object_item=self.object_tree.currentItem()
        if not object_item:
            return
        try:
            self.generate_grade_action.setEnabled(False)
            self.generate_class_action.setEnabled(False)
            self.clear_grade_action.setEnabled(False)
            self.clear_class_action.setEnabled(False)
            if object_item.text(0)=="班级总表":
                self.preview_mode="total_classes"
                self.timetable_preview.setDragEnabled(False)
                self.timetable_subheader.setText("班级总表")
                display_df_in_table(self.timetable_preview,class_total_dataframe())
                self.store_lesson_subheader.hide()
                self.lesson_storage_pane.hide()
                self.timetable_legend.hide()
                if set_size:
                    self.set_timetables_size()
            elif object_item.text(0)=="教师总表":
                self.preview_mode="total_teachers"
                self.timetable_preview.setDragEnabled(False)
                self.timetable_subheader.setText("教师总表")
                display_df_in_table(self.timetable_preview,teacher_total_dataframe())
                self.store_lesson_subheader.hide()
                self.lesson_storage_pane.hide()
                self.timetable_legend.hide()
                self.preview_class_scope.hide()
                if set_size:
                    self.set_timetables_size()
            elif object_item.parent() is not None and object_item.parent().text(0) =="教师课表":
                self.preview_mode="teacher"
                self.timetable_preview.setDragEnabled(False)
                self.store_lesson_subheader.hide()
                self.lesson_storage_pane.hide()
                self.preview_object=lesson_info.teachers[object_item.text(0)]
                self.timetable_subheader.setText(f"{self.preview_object.name}老师 课程表")
                display_teachers_timetable(self.preview_object,self.timetable_preview)
                self.timetable_legend.hide()
                self.preview_class_scope.hide()
                if set_size:
                    self.set_timetables_size()
            elif object_item.parent() is not None and object_item.parent().data(0,Qt.UserRole) =="班级课表":
                self.preview_grade=lesson_info.grades[object_item.data(0,Qt.UserRole)]
                self.generate_grade_action.setEnabled(True)
                self.clear_grade_action.setEnabled(True)
            elif object_item.parent().parent() is not None and object_item.parent().parent().data(0,Qt.UserRole) =="班级课表":
                self.preview_mode="class"
                self.generate_grade_action.setEnabled(True)
                self.generate_class_action.setEnabled(True)
                self.clear_grade_action.setEnabled(True)
                self.clear_class_action.setEnabled(True)
                self.timetable_preview.setDragEnabled(True)
                self.preview_object=lesson_info.classes[object_item.data(0,Qt.UserRole)]
                self.preview_grade=self.preview_object.grade
                self.timetable_subheader.setText(f"{self.preview_object} 课程表")
                display_df_in_table(self.timetable_preview,self.preview_object.timetable_dataframe)
                for day in range(1,6):
                    for lesson in range(1,cfg.day_class_num+1):
                        curr_time=Time(day,lesson)
                        curr_item=self.timetable_preview.item(lesson-1,day-1)
                        if not curr_item:
                            continue
                        curr_subjects=self.preview_object.get_lessons(curr_time)
                        curr_item.setData(Qt.UserRole,curr_item.text())
                        if len(curr_subjects)<2:
                            continue
                        sin_text=curr_subjects[0].name+("\n"+self.preview_object.get_teacher(curr_subjects[0]).name if cfg.show_teachers.value else "")
                        dou_text=curr_subjects[1].name+("\n"+self.preview_object.get_teacher(curr_subjects[1]).name if cfg.show_teachers.value else "")
                        self.timetable_preview.setCellWidget(lesson-1,day-1,sindou_widget(sin_text,dou_text,self.timetable_preview.font()))
                        self.timetable_preview.setCellWidget(lesson-1,day-1,sindou_widget(sin_text,dou_text,self.timetable_preview.font()))
                        curr_item.setText("")
                self.timetable_legend.hide()
                self.preview_class_scope.hide()
                self.show_stored_lesson_cards()
                if set_size:
                    self.set_timetables_size()
            elif object_item.parent() is not None and object_item.parent().text(0) =="学科课表":
                self.preview_mode="subject"
                self.timetable_preview.setDragEnabled(False)
                self.store_lesson_subheader.hide()
                self.lesson_storage_pane.hide()
                self.preview_object=lesson_info.subjects[object_item.text(0)]
                self.timetable_subheader.setText(f"{self.preview_object.name} 课程表")
                display_df_in_table(self.timetable_preview,self.preview_object.timetable_dataframe(self.preview_class_scope.checkedClasses()))
                self.preview_class_scope.show()
                self.timetable_legend.hide()
                if set_size:
                    self.set_timetables_size()
            else:
                raise ValueError("未知的课程表类型")
            self.teacher_timetable_pane.hide()
        except:
            return

    def on_progress_update(self,progress:tuple[Class,Time,int]):
        try:
            used_time=round(time.time()-self.generate_start_time)
            self.log_label.setText(f"当前进度：{progress[2]}%%，班级：{progress[0].name}，课时：{progress[1]}，已用时间：%02d:%02d"%(used_time//60,used_time%60))
            self.progress_bar.setValue(progress[2])
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"生成课程表出错：\n{e}")
            show_error(self,error)

    def save_timetable(self,file):
        logging.info("导出按钮被点击")
        if self.total_left_subjects:
            logging.warning(f"暂存区还有{self.total_left_subjects}门课程")
            dialog=MessageBox("确认导出课程表吗？",f"班级课表中还有{self.total_left_subjects}门课程位于暂存区中，是否确认导出？",self)
            if not dialog.exec():
                logging.info("用户取消导出（暂存区有课程）")
                return
        if file in ("cses","cses_v1"):
            # CSES 导出为每个班级一个 YAML 文件，需选择保存目录
            filename=QFileDialog.getExistingDirectory(self,"导出CSES课表（每个班级一个YAML文件）","")
            if not filename:
                logging.info("用户取消导出")
                return
            logging.info(f"导出CSES课表目录：{filename}")
        else:
            filename,_=QFileDialog.getSaveFileName(self,"导出课程表","","Microsoft Excel 工作表(*.xlsx);;Microsoft Excel 97-2003 工作表(*.xls)")
            if not filename:
                logging.info("用户取消导出")
                return
            logging.info(f"导出课程表文件名：{filename}")

        self.save_Toast=Toast.info("正在导出课程表，请稍候...","",parent=self,duration=-1)
        self.save_progress=IndeterminateProgressBar()
        self.save_Toast.addWidget(self.save_progress, alignment=Qt.AlignmentFlag.AlignCenter)

        name,ext=os.path.splitext(filename)
        if file in ("cses","cses_v1"):
            name,ext=filename,""
        save_thread=SaveThread(name,ext,file,self)
        save_thread.success.connect(self.on_save_success)
        save_thread.error.connect(self.on_save_error)
        save_thread.start()
        logging.info("导出线程已启动")

    def on_save_success(self):
        self.save_Toast.close()
        Toast.success("课程表导出成功！","",parent=self,duration=-1)

    def on_save_error(self,error):
        self.save_Toast.close()
        Toast.error("课程表导出失败！",error,parent=self,duration=-1)

    def refresh_plan_actions(self):
        self.load_plan_action.setEnabled(len(cfg.timetable_plans.value)>0)
        self.del_plan_action.setEnabled(len(cfg.timetable_plans.value)>0)

    def save_plan(self):
        try:
            logging.info("保存课程表方案")
            plan_time=time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())
            save_plan_msg=SaveTimetablePlan(plan_time,self)
            if not save_plan_msg.exec():
                logging.info("用户取消保存")
                return
            plan_name=save_plan_msg.name_input.text()
            plan_desc=save_plan_msg.desc_input.text()
            save_current_plan(plan_name,plan_desc,plan_time)
            self.curr_plan.setText("当前方案："+plan_name)
            lesson_info.saved=True
            self.refresh_plan_actions()
            logging.info("课程表方案保存成功")
            Toast.success("课程表方案保存成功！","",parent=self,duration=3000)
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"保存课程表方案出错：\n{e}")
            show_error(self,error)

    def load_plan(self):
        try:
            logging.info("加载课程表方案")
            load_plan_msg=LoadTimetablePlan(self)
            if not load_plan_msg.exec():
                logging.info("用户取消加载")
                return
            if not lesson_info.saved:
                msgbox=MessageBox("确定加载课程表方案？","加载方案会使当前的所有修改丢失，建议先保存当前课程表方案，是否继续加载方案？",self)
                if not msgbox.exec():
                    return
            plan_name=load_plan_msg.plan_list.selectedItems()[0].text().split("\n")[0]
            plan=read_plan_file(cfg.timetable_plans.value[plan_name]["filename"])
            if not check_plan_compatible(plan):
                Toast.error("课程表方案与当前设置不匹配",f"加载的课程表方案不是在当前设置下生成的",duration=-1,parent=self)
                logging.error("课程表方案加载失败")
                return

            self.push_history()
            apply_plan(plan)
            self.curr_plan.setText("当前方案："+plan_name)
            logging.info("课程表方案加载成功")
            Toast.success("课程表方案加载成功",f"成功加载方案：{plan_name}",parent=self,duration=3000)

            self.show_object_tree()
            self.refresh_timetable()
            self.hide_lesson_details()
            lesson_info.saved=True
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"加载课程表方案出错：\n{e}")
            show_error(self,error)

    def del_plan(self):
        try:
            logging.info("删除课程表方案")
            del_plan_msg=DelTimetablePlan(self)
            if not del_plan_msg.exec():
                logging.info("用户取消删除")
                return
            plans=del_plan_msg.plan_list.selectedItems()
            plan_names=[plan.text().split("\n")[0] for plan in plans]
            if self.curr_plan.text()[5:] in plan_names:
                self.curr_plan.setText("当前方案：未保存")
                lesson_info.saved=False
            delete_plans(plan_names)
            self.refresh_plan_actions()
            logging.info("课程表方案删除成功")
            Toast.success("课程表方案删除成功！","",parent=self,duration=3000)
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"删除课程表方案出错：\n{e}")
            show_error(self,error)

    def ask_force(self,target_time:Time)->bool:
        logging.info("询问是否强制调课")
        if not ForceExchangeMsgbox(self.failed_reasons[target_time],self.conflict_lessons[target_time],self).exec():
            logging.info("用户取消强制调课")
            return False
        else:
            logging.info("用户确认强制调课")
            for lesson in self.conflict_lessons[target_time]:
                lesson[0].remove_lesson(lesson[1])
            return True