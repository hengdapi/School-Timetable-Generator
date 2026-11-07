# coding=utf-8
"""课程信息页面：创建、调整年级 / 班级 / 任课教师，并支持从 Excel 文件导入。

数据说明：
- 本页读写的是配置项（cfg.lessons_info / subjects_info / teachers_info / grades_info），
  它们才是“当前编辑中的”课程信息；
- lesson_info 是程序启动时解析出来的快照（生成课表、检查冲突都用它），
  所以本页修改配置后不会就地重建，而是提示“重启后生效”，并在顶部提供“立即重启”；
- 文件导入、年级设置的实现与设置页保持一致。
"""
import shutil

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor

from locals import *
from pages.ui_widgets import PagedPage,WarningBanner,log_page_error,show_item_menu

# 没有归入任何年级的班级在界面上的显示名
UNGRADED="（未归入年级）"
# 班级对话框里各列的固定宽度（表头与内容行共用）
SUBJECT_COLUMN_WIDTH=180
HOURS_COLUMN_WIDTH=175


class FillWidthImageLabel(ImageLabel):
    """宽度跟随父容器、高度按原图比例自动变化的图片标签"""

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.image.isNull():
            return
        height=round(self.width()*self.image.height()/self.image.width())
        if self.height()!=height:
            self.setFixedHeight(height)


# =====================================================================
# 配置读写
# =====================================================================
def config_lessons()->list[dict]:
    """当前编辑中的课程信息（兼容旧版本把 lessons_info 存成 JSON 字符串的情况）"""
    info=cfg.lessons_info.value
    if isinstance(info,str):
        if not info.strip():
            return []
        try:
            info=json.loads(info)
        except Exception:
            logging.warning("课程信息无法解析为 JSON，按空课程信息处理")
            return []
    if not isinstance(info,list):
        return []
    return [dict(row) for row in info if isinstance(row,dict)]


def apply_lessons(lessons:list[dict]):
    """写入课程信息并立即保存"""
    cfg.lessons_info.value=lessons
    save_settings()


def config_subjects()->list[str]:
    """学科顺序：以 subjects_info 为准，并补上只出现在课程信息里的学科"""
    subjects=[]
    for subject in (cfg.subjects_info.value or []):
        subject=str(subject)
        if subject and subject not in subjects:
            subjects.append(subject)
    for row in config_lessons():
        for key in row:
            if key.endswith(" - 课时"):
                subject=key[:-len(" - 课时")]
                if subject and subject not in subjects:
                    subjects.append(subject)
    return subjects


def row_teachers(row:dict,subject:str)->list[str]:
    """某班某学科的任课老师（联合授课时返回多位）"""
    return split_teacher_names(row.get(f"{subject} - 任课老师"))


def row_hours(row:dict,subject:str)->int:
    """某班某学科的每周课时"""
    value=row.get(f"{subject} - 课时")
    try:
        if value is None or pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError,ValueError):
        return 0


def config_teachers()->list[str]:
    """教师名单：以 teachers_info 为准，并补上只出现在课程信息里的老师"""
    teachers=[]
    for name in (cfg.teachers_info.value or []):
        for teacher in split_teacher_names(name):
            if teacher not in teachers:
                teachers.append(teacher)
    for row in config_lessons():
        for subject in config_subjects():
            for teacher in row_teachers(row,subject):
                if teacher not in teachers:
                    teachers.append(teacher)
    return teachers


def config_class_names()->list[str]:
    """当前编辑中的班级名单（顺序与课程信息表一致）"""
    return [str(row.get("班级")) for row in config_lessons() if row.get("班级")]


def class_grade(class_name:str)->str:
    """班级所属年级，没有归入年级时返回 UNGRADED"""
    for grade,classes in (cfg.grades_info.value or {}).items():
        if class_name in classes:
            return grade
    return UNGRADED


def set_class_grade(class_name:str,grade_name:str):
    """把班级从其它年级里移出，再放进指定年级"""
    if grade_name==UNGRADED:
        grade_name=None
    grades=dict(cfg.grades_info.value or {})
    for name,classes in grades.items():
        if name!=grade_name and class_name in classes:
            grades[name]=[clas for clas in classes if clas!=class_name]
    if grade_name:
        grades.setdefault(grade_name,[])
        if class_name not in grades[grade_name]:
            grades[grade_name].append(class_name)
    cfg.grades_info.value=grades


def build_lesson_row(class_name:str,teachers:dict[str,list[str]],hours:dict[str,int])->dict:
    """按当前学科顺序生成一行课程信息"""
    row={"班级":class_name}
    for subject in config_subjects():
        row[f"{subject} - 任课老师"]=" ".join(teachers.get(subject,[]))
        row[f"{subject} - 课时"]=int(hours.get(subject,0))
    return row


def cleanup_references(diff_classes:set,diff_teachers:set,diff_subjects:set):
    """删除班级 / 教师 / 学科后，把年级、规则、并课设置里的引用一并清掉

    与 locals.del_cfg_diff 逻辑一致，只是年级里的班级排序按配置中的顺序，
    避免课程信息刚改过、lesson_info 还没重建时出现“班级不存在”的报错。
    """
    diff_all=set(diff_classes)|set(diff_teachers)|set(diff_subjects)
    class_order=config_class_names()

    grades=cfg.grades_info.value or {}
    for grade,classes in list(grades.items()):
        left=[clas for clas in classes if clas not in diff_classes]
        left.sort(key=lambda clas:class_order.index(clas) if clas in class_order else len(class_order))
        grades[grade]=left
    cfg.grades_info.value=grades

    new_rules=[]
    for rule in (cfg.rules.value or []):
        rule=dict(rule)
        keep=True
        for arg,value in list(rule.items()):
            if isinstance(value,list):
                rule[arg]=[item for item in value if item not in diff_all]
            elif isinstance(value,str) and value in diff_all:
                keep=False
                break
        if keep:
            new_rules.append(rule)
    cfg.rules.value=new_rules

    new_merged=[]
    for merged_lesson in (cfg.merged_lessons.value or []):
        subject,classes=merged_lesson[0],list(merged_lesson[1])
        if subject in diff_subjects:
            continue
        left=[clas for clas in classes if clas not in diff_classes]
        if len(left)>=2:
            new_merged.append((subject,left))
    cfg.merged_lessons.value=new_merged


def rename_reference(old_name:str,new_name:str):
    """班级 / 教师改名后，同步修改年级、规则、并课设置里的引用"""
    grades=cfg.grades_info.value or {}
    for grade,classes in list(grades.items()):
        grades[grade]=[new_name if clas==old_name else clas for clas in classes]
    cfg.grades_info.value=grades

    new_rules=[]
    for rule in (cfg.rules.value or []):
        rule=dict(rule)
        for arg,value in list(rule.items()):
            if isinstance(value,list):
                rule[arg]=[new_name if item==old_name else item for item in value]
            elif isinstance(value,str) and value==old_name:
                rule[arg]=new_name
        new_rules.append(rule)
    cfg.rules.value=new_rules

    cfg.merged_lessons.value=[
        (merged_lesson[0],[new_name if clas==old_name else clas for clas in merged_lesson[1]])
        for merged_lesson in (cfg.merged_lessons.value or [])
    ]


# =====================================================================
# 学科统计 / 增删改
# =====================================================================
def subject_statistics(subject:str)->tuple[list[str],list[str],int]:
    """统计某学科的任教班级、任课老师和每周总课时"""
    classes=[]
    teachers=[]
    hours=0
    for row in config_lessons():
        teacher_names=row_teachers(row,subject)
        if not teacher_names:
            continue
        class_name=str(row.get("班级",""))
        if class_name and class_name not in classes:
            classes.append(class_name)
        for teacher in teacher_names:
            if teacher not in teachers:
                teachers.append(teacher)
        hours+=row_hours(row,subject)
    return classes,teachers,hours


def rename_subject(old_name:str,new_name:str):
    """重命名学科：课程信息里的两列、学科列表、规则与并课设置一并改名"""
    lessons=[]
    for row in config_lessons():
        new_row={}
        for key,value in row.items():
            if key==f"{old_name} - 任课老师":
                key=f"{new_name} - 任课老师"
            elif key==f"{old_name} - 课时":
                key=f"{new_name} - 课时"
            new_row[key]=value
        lessons.append(new_row)
    apply_lessons(lessons)
    cfg.subjects_info.value=[new_name if subject==old_name else subject for subject in config_subjects()]

    new_rules=[]
    for rule in (cfg.rules.value or []):
        rule=dict(rule)
        for arg,value in list(rule.items()):
            if isinstance(value,list):
                rule[arg]=[new_name if item==old_name else item for item in value]
            elif isinstance(value,str) and value==old_name:
                rule[arg]=new_name
        new_rules.append(rule)
    cfg.rules.value=new_rules

    cfg.merged_lessons.value=[
        (new_name if merged_lesson[0]==old_name else merged_lesson[0],list(merged_lesson[1]))
        for merged_lesson in (cfg.merged_lessons.value or [])
    ]
    save_settings()


def remove_subject(subject:str):
    """删除学科：课程信息里对应的两列一并去掉"""
    lessons=[]
    for row in config_lessons():
        lessons.append({
            key:value for key,value in row.items()
            if key not in (f"{subject} - 任课老师",f"{subject} - 课时")
        })
    apply_lessons(lessons)
    cfg.subjects_info.value=[name for name in config_subjects() if name!=subject]
    save_settings()


# =====================================================================
# 年级对话框（与设置页实现一致）
# =====================================================================
class GradeMsgbox(MessageBoxBase):
    def __init__(self,parent=None,edit=False,grade_name:str=""):
        super().__init__(parent)
        self.edit=edit
        self.grade_name=grade_name
        if self.edit:
            self.classes=list((cfg.grades_info.value or {}).get(grade_name,[]))
        subheader("添加年级" if not edit else "编辑年级",self,self.viewLayout)
        write("年级名称：",self,self.viewLayout,0)
        self.grade_name_input=LineEdit()
        self.grade_name_input.setPlaceholderText("X年级")
        if self.edit:
            self.grade_name_input.setText(grade_name)
        add_widget(self.grade_name_input,self.viewLayout)
        write("所含班级：",self,self.viewLayout,0)
        self.classes_combo=MultiSelectComboBox()
        # 只列出还没被其它年级占用的班级，编辑时把自己原有的班级也放回候选
        taken=set()
        for classes in (cfg.grades_info.value or {}).values():
            taken|=set(classes)
        if self.edit:
            taken-=set(self.classes)
        left_classes=[clas for clas in config_class_names() if clas not in taken]
        self.classes_combo.addItems(left_classes)
        if self.edit:
            self.classes_combo.setSelectedIndices({left_classes.index(clas) for clas in self.classes if clas in left_classes})
        add_widget(self.classes_combo,self.viewLayout)
        self.yesButton.setText("添加年级" if not edit else "保存修改")
        self.cancelButton.setText("取消")

    def validate(self) -> bool:
        curr_grade_name=self.grade_name_input.text().strip()
        if not curr_grade_name:
            Toast.error("请输入年级名称","",parent=self,duration=2000)
            return False
        if not self.classes_combo.selectedItems():
            Toast.error("请选择所含班级","",parent=self,duration=2000)
            return False
        grade_names=list((cfg.grades_info.value or {}).keys())
        if curr_grade_name!=self.grade_name and curr_grade_name in grade_names:
            Toast.error("请勿设置名称重复的年级",f"名称“{curr_grade_name}”重复",parent=self,duration=2000)
            return False
        return True


# =====================================================================
# 班级对话框
# =====================================================================
class SubjectRow(QWidget):
    """班级对话框里的一行：学科（只读） + 任课老师 + 每周课时"""

    def __init__(self,subject:str,teachers:list[str],teacher_names=None,hours:int=0,parent=None):
        super().__init__(parent)
        self.subject_name=subject
        # 候选项列表，注意不要和 teachers() 方法重名
        self.teacher_options=list(teachers)
        teacher_names=list(teacher_names or [])

        layout=QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(8)

        # 学科只作为文字显示，不提供编辑（用 BodyLabel 默认的正文字体）
        self.subject_label=BodyLabel()
        self.subject_label.setText(subject)
        self.subject_label.setToolTip(subject)
        self.subject_label.setIndent(10)
        self.subject_label.setFixedWidth(SUBJECT_COLUMN_WIDTH)
        layout.addWidget(self.subject_label,0,Qt.AlignVCenter)

        self.teacher_combo=MultiSelectComboBox()
        self.teacher_combo.setFixedHeight(33)
        self.teacher_combo.addItems(self.teacher_options)
        self.teacher_combo.setPlaceholderText("任课老师（可多选，多位老师即联合授课）")
        self.set_teachers(teacher_names)
        layout.addWidget(self.teacher_combo,1)

        self.hours_spin=SpinBox()
        self.hours_spin.setRange(0,50)
        self.hours_spin.setSuffix(" 课时")
        # 右侧还有上下两个微调按钮，宽度太窄时“课时”两个字会被截掉
        self.hours_spin.setFixedWidth(HOURS_COLUMN_WIDTH)
        self.hours_spin.setValue(int(hours))
        layout.addWidget(self.hours_spin)

    def subject(self)->str:
        return self.subject_name

    def teachers(self)->list[str]:
        return [item.text for item in self.teacher_combo.selectedItems()]

    def hours(self)->int:
        return self.hours_spin.value()

    def set_teachers(self,names:list[str]):
        texts=[item.text for item in self.teacher_combo.items]
        self.teacher_combo.setSelectedIndices({index for index,text in enumerate(texts) if text in names})

    def add_teacher_option(self,names:list[str]):
        """把新老师追加到候选项（菜单每次点击都会重建，无需手动刷新）

        只加入候选项、不自动勾选：各学科的课时不同，交由使用者自己勾选。
        """
        self.teacher_options=list(dict.fromkeys(self.teacher_options+list(names)))
        existing=[item.text for item in self.teacher_combo.items]
        for name in names:
            if name not in existing:
                self.teacher_combo.addItem(name)


class SubjectNameMsgbox(MessageBoxBase):
    """新增 / 重命名学科时输入学科名称（学科行本身是只读文字）"""

    def __init__(self,parent=None,subjects:list[str]|None=None,used:list[str]|None=None,edit=False,subject_name:str=""):
        super().__init__(parent)
        self.subjects=list(subjects or [])
        self.used=set(used or [])
        self.edit=edit
        subheader("重命名学科" if edit else "添加学科",self,self.viewLayout)
        write("学科名称：",self,self.viewLayout,0)
        self.subject_input=LineEdit()
        self.subject_input.setPlaceholderText("输入学科名称，也可下拉选择已有学科")
        self.subject_input.setCompleter(QCompleter(self.subjects,self.subject_input))
        if edit:
            self.subject_input.setText(subject_name)
            self.subject_input.selectAll()
        add_widget(self.subject_input,self.viewLayout)
        self.yesButton.setText("保存修改" if edit else "添加学科")
        self.cancelButton.setText("取消")

    def validate(self) -> bool:
        subject=self.subject_input.text().strip()
        if not subject:
            Toast.error("请输入学科名称","",parent=self,duration=2000)
            return False
        if subject in self.used:
            Toast.error("学科重复",f"“{subject}”已经在列表里了",parent=self,duration=3000)
            return False
        return True


class ClassMsgbox(MessageBoxBase):
    """添加 / 编辑班级：班级名称、所属年级，以及各学科的任课老师与每周课时"""

    def __init__(self,parent=None,edit=False,class_name:str=""):
        super().__init__(parent)
        self.edit=edit
        self.origin_name=class_name
        self.subjects=config_subjects()
        self.teachers=config_teachers()
        self.rows=[]

        subheader("添加班级" if not edit else "编辑班级",self,self.viewLayout)

        # 班级名称：标签在左、输入框在右
        name_layout=QHBoxLayout()
        name_layout.setSpacing(8)
        self.name_label=BodyLabel()
        self.name_label.setFont(fonts.write)
        self.name_label.setText("班级名称：")
        name_layout.addWidget(self.name_label,0,Qt.AlignVCenter)
        self.name_input=LineEdit()
        self.name_input.setPlaceholderText("X年级X班")
        if edit:
            self.name_input.setText(class_name)
        name_layout.addWidget(self.name_input,1)
        self.viewLayout.addLayout(name_layout)

        # 所属年级：同样标签在左、下拉框在右
        grade_layout=QHBoxLayout()
        grade_layout.setSpacing(8)
        self.grade_label=BodyLabel()
        self.grade_label.setFont(fonts.write)
        self.grade_label.setText("所属年级：")
        grade_layout.addWidget(self.grade_label,0,Qt.AlignVCenter)
        self.grade_combo=ComboBox()
        self.grade_combo.addItems(list((cfg.grades_info.value or {}).keys())+[UNGRADED])
        self.grade_combo.setCurrentText(class_grade(class_name) if edit else UNGRADED)
        grade_layout.addWidget(self.grade_combo,1)
        self.viewLayout.addLayout(grade_layout)

        # 两个标签等宽，输入框和下拉框的起始位置才对得齐
        label_width=max(self.name_label.sizeHint().width(),self.grade_label.sizeHint().width())
        self.name_label.setFixedWidth(label_width)
        self.grade_label.setFixedWidth(label_width)

        # 学科列表的表头
        header_layout=QHBoxLayout()
        header_layout.setSpacing(8)
        for name,width in (("学科",SUBJECT_COLUMN_WIDTH),("任课老师",0),("每周课时",HOURS_COLUMN_WIDTH)):
            label=BodyLabel()
            label.setFont(fonts.write)
            label.setText(name)
            if width:
                # 与内容行的文字内缩保持一致，表头文字才对得齐
                label.setIndent(10)
                label.setFixedWidth(width)
                header_layout.addWidget(label)
            else:
                header_layout.addWidget(label,1)
        self.viewLayout.addLayout(header_layout)

        # 学科行（可滚动）
        self.rows_area=SingleDirectionScrollArea(orient=Qt.Vertical)
        self.rows_area.setStyleSheet("QScrollArea{background: transparent; border: none}")
        self.rows_area.setWidgetResizable(True)
        self.rows_area.setMinimumWidth(820)
        self.rows_area.setFixedHeight(280)
        rows_view=QWidget()
        rows_view.setStyleSheet("QWidget{background: transparent}")
        self.rows_layout=QVBoxLayout(rows_view)
        self.rows_layout.setContentsMargins(0,0,0,0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)
        self.rows_area.setWidget(rows_view)
        add_widget(self.rows_area,self.viewLayout,0)

        # 对话框整体带 QGraphicsDropShadowEffect（高斯模糊阴影），内容里任何一处重绘
        # 都会让 Qt 把整个对话框重新渲染到离屏图像再模糊一次，滚动学科列表时每帧都
        # 要付这笔开销（实测单帧 CPU 50ms 以上，帧率 20 出头）。这里在滚动期间先摘掉
        # 阴影、停下 200ms 后再装回去：阴影叠在暗色遮罩上本来就不明显，摘掉后单帧
        # CPU 降到 15ms 左右，帧率可以到 60 以上。
        self.shadow_restore_timer=QTimer(self)
        self.shadow_restore_timer.setSingleShot(True)
        self.shadow_restore_timer.setInterval(200)
        self.shadow_restore_timer.timeout.connect(self.restore_shadow)
        self.rows_area.verticalScrollBar().valueChanged.connect(self.drop_shadow)

        # 添加学科：输入框 + 按钮
        add_subject_layout=QHBoxLayout()
        self.new_subject_input=LineEdit()
        self.new_subject_input.setPlaceholderText("输入学科名称，回车或点击右侧按钮添加一行")
        self.new_subject_input.returnPressed.connect(self.add_subject)
        add_widget(self.new_subject_input,add_subject_layout,0)
        self.add_subject_button=PushButton()
        self.add_subject_button.setText("添加学科")
        self.add_subject_button.setIcon(FluentIcon.ADD)
        self.add_subject_button.clicked.connect(self.add_subject)
        add_widget(self.add_subject_button,add_subject_layout,0)
        self.viewLayout.addLayout(add_subject_layout)

        # 新增教师：输入框 + 按钮
        add_teacher_layout=QHBoxLayout()
        self.new_teacher_input=LineEdit()
        self.new_teacher_input.setPlaceholderText("输入教师姓名，回车或点击右侧按钮加入候选项")
        self.new_teacher_input.returnPressed.connect(self.add_teacher)
        add_widget(self.new_teacher_input,add_teacher_layout,0)
        self.add_teacher_button=PushButton()
        self.add_teacher_button.setText("新增教师")
        self.add_teacher_button.setIcon(FluentIcon.PEOPLE)
        self.add_teacher_button.clicked.connect(self.add_teacher)
        add_widget(self.add_teacher_button,add_teacher_layout,0)
        self.viewLayout.addLayout(add_teacher_layout)

        self.yesButton.setText("添加班级" if not edit else "保存修改")
        self.cancelButton.setText("取消")

        row_data=None
        if edit:
            row_data=next((row for row in config_lessons() if str(row.get("班级",""))==class_name),None)
        for subject in self.subjects:
            teacher_names=row_teachers(row_data,subject) if row_data else []
            hours=row_hours(row_data,subject) if row_data else 0
            self.add_row(subject,teacher_names,hours)

    # ------------------------------------------------------------------
    # 学科行
    # ------------------------------------------------------------------
    def add_row(self,subject:str,teacher_names:list[str]|None=None,hours:int=0)->SubjectRow:
        row=SubjectRow(subject,self.teachers,teacher_names,hours)
        self.rows.append(row)
        # 保持在末尾的伸缩项之前
        self.rows_layout.insertWidget(self.rows_layout.count()-1,row)
        return row

    def add_subject(self):
        """新增学科：把输入框里的学科名加到最后一行"""
        name=self.new_subject_input.text().strip()
        if not name:
            Toast.error("请输入学科名称","",parent=self,duration=2000)
            return
        if name in [row.subject() for row in self.rows]:
            Toast.error("学科重复",f"“{name}”已经在列表里了",parent=self,duration=3000)
            return
        self.add_row(name)
        self.new_subject_input.clear()

    def add_teacher(self):
        """新增教师：把输入框里的姓名加入所有学科行的候选项"""
        name=self.new_teacher_input.text().strip()
        if not name:
            Toast.error("请输入教师姓名","",parent=self,duration=2000)
            return
        if name in self.teachers:
            Toast.error("教师重复",f"名单里已经有“{name}”了",parent=self,duration=3000)
            return
        self.teachers.append(name)
        for row in self.rows:
            row.add_teacher_option([name])
        self.new_teacher_input.clear()
        Toast.success("已添加老师",f"“{name}”已加入候选项，请在对应学科里勾选",parent=self,duration=2000)

    # ------------------------------------------------------------------
    # 滚动时卸掉对话框阴影，减少每帧的离屏重绘
    # ------------------------------------------------------------------
    def drop_shadow(self):
        if self.widget.graphicsEffect() is not None:
            self.widget.setGraphicsEffect(None)
        self.shadow_restore_timer.start()

    def restore_shadow(self):
        # 对话框已经关掉了就不用再装回去，避免改到关闭动画用的透明度效果
        if not self.isVisible() or self.widget.graphicsEffect() is not None:
            return
        self.setShadowEffect(60,(0,10),QColor(0,0,0,50))

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def validate(self) -> bool:
        name=self.name_input.text().strip()
        if not name:
            Toast.error("请输入班级名称","",parent=self,duration=2000)
            return False
        other_names=[clas for clas in config_class_names() if not (self.edit and clas==self.origin_name)]
        if name in other_names:
            Toast.error("班级名称重复",f"已存在名为“{name}”的班级",parent=self,duration=3000)
            return False

        teachers={}
        hours={}
        new_subjects=[]
        for row in self.rows:
            subject=row.subject()
            teacher_names=row.teachers()
            lesson_hours=row.hours()
            if not subject:
                continue
            if subject in teachers:
                Toast.error("学科填写重复",f"学科“{subject}”填写了多行",parent=self,duration=3000)
                return False
            if teacher_names and lesson_hours<=0:
                Toast.error("课时必须大于 0",f"请填写“{subject}”的每周课时",parent=self,duration=3000)
                return False
            if lesson_hours>0 and not teacher_names:
                Toast.error("缺少任课老师",f"请为“{subject}”选择任课老师",parent=self,duration=3000)
                return False
            if not teacher_names:
                continue
            teachers[subject]=teacher_names
            hours[subject]=lesson_hours
            if subject not in self.subjects:
                new_subjects.append(subject)

        if not teachers:
            Toast.error("请至少填写一个学科","填写学科、任课老师和每周课时后即可保存",parent=self,duration=3000)
            return False

        self.class_name=name
        self.grade=self.grade_combo.currentText() or UNGRADED
        self.teacher_map=teachers
        self.hours_map=hours
        self.new_subjects=new_subjects
        return True


class TeacherMsgbox(MessageBoxBase):
    """添加教师 / 重命名教师"""

    def __init__(self,parent=None,edit=False,teacher_name:str=""):
        super().__init__(parent)
        self.edit=edit
        self.origin_name=teacher_name
        subheader("添加教师" if not edit else "重命名教师",self,self.viewLayout)
        write("教师姓名：",self,self.viewLayout,0)
        self.name_input=LineEdit()
        self.name_input.setPlaceholderText("请输入教师姓名")
        if edit:
            self.name_input.setText(teacher_name)
        add_widget(self.name_input,self.viewLayout)
        if edit:
            write("重命名后，各班课程信息里的任课老师会一并更新。",self,self.viewLayout,0)
        self.yesButton.setText("添加教师" if not edit else "保存修改")
        self.cancelButton.setText("取消")

    def validate(self) -> bool:
        name=self.name_input.text().strip()
        if not name:
            Toast.error("请输入教师姓名","",parent=self,duration=2000)
            return False
        other_names=[teacher for teacher in config_teachers() if not (self.edit and teacher==self.origin_name)]
        if name in other_names:
            Toast.error("教师姓名重复",f"名单里已经有“{name}”了",parent=self,duration=3000)
            return False
        return True


# =====================================================================
# 课程信息页面
# =====================================================================
class Classes(PagedPage):
    def __init__(self,parent=None):
        try:
            # 顶部导航、堆叠分页与 add_page / switch_page / create_page 都在基类里
            super().__init__(parent=parent,objectName="Classes")
            # 是否有改过但还没重启生效的修改
            self.pending_restart=False

            self.add_page("import",FluentIcon.FOLDER,"从文件导入",self.build_import_page())
            self.add_page("grade",FluentIcon.FLAG,"年级",self.build_grade_page())
            self.add_page("class",FluentIcon.BOOK_SHELF,"班级",self.build_class_page())
            self.add_page("subject",FluentIcon.EDUCATION,"学科",self.build_subject_page())
            self.add_page("teacher",FluentIcon.PEOPLE,"任课教师",self.build_teacher_page())

            self.switch_page("import")
            self.refresh_all()

            # 待生效提示：有改动后才出现
            self.pending_bar=QWidget()
            pending_layout=QHBoxLayout(self.pending_bar)
            pending_layout.setContentsMargins(0,0,0,0)
            self.restart_banner=WarningBanner(self.pending_bar)
            pending_layout.addWidget(self.restart_banner,1)
            self.restart_button=button("立即重启",self.pending_bar,pending_layout,0)
            self.restart_button.setIcon(FluentIcon.SYNC)
            self.restart_button.setFixedSize(130,40)
            self.restart_button.clicked.connect(self.restart_now)
            self.pending_bar.setVisible(False)
            add_widget(self.pending_bar,self.main_layout,10)
            logging.info("课程信息页面加载完成")
        except Exception as error:
            log_page_error(self,error,"课程信息页面")

    # ------------------------------------------------------------------
    # 各分页内容
    # ------------------------------------------------------------------
    def build_import_page(self)->QWidget:
        page,layout=self.create_page("从文件导入","上传存储任课老师及课时、班级信息的表格，导入后会覆盖当前课程信息并自动重启应用。")
        self.user_info_card=SettingCard(icon=FluentIcon.INFO,title="课程信息文件",content="同一格填多位老师（如“张三 李四”）即为联合授课")
        add_widget(self.user_info_card,layout)

        self.download_template_button=button("下载导入模板",page,self.user_info_card.layout())
        self.download_template_button.setFixedSize(150,35)
        self.download_template_button.setIcon(FluentIcon.DOWNLOAD)
        self.download_template_button.clicked.connect(self.download_template)

        self.upload_button=button("上传课程信息文件",page,self.user_info_card.layout())
        self.upload_button.setFixedSize(180,35)
        self.upload_button.setIcon(FluentIcon.FOLDER)
        self.upload_button.clicked.connect(self.upload_lessons_info)

        # 模板格式说明
        self.template_card=CardWidget(page)
        template_layout=QVBoxLayout(self.template_card)
        template_layout.setContentsMargins(20,16,20,16)
        subheader("模板格式",self.template_card,template_layout,10)
        self.template_image=FillWidthImageLabel("images/template.png",self.template_card)
        self.template_image.setBorderRadius(8,8,8,8)
        # setImage 会把尺寸固定成原图大小，这里放开宽度让图片随卡片一起伸缩
        self.template_image.setMinimumWidth(0)
        self.template_image.setMaximumWidth(16777215)
        self.template_image.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        template_layout.addWidget(self.template_image)
        add_widget(self.template_card,layout)

        layout.addStretch(1)
        return page

    def build_grade_page(self)->QWidget:
        page,layout=self.create_page("年级信息","年级用于按年段生成课表，一个班级只属于一个年级。")

        grade_operations_layout=QHBoxLayout()
        layout.addLayout(grade_operations_layout)

        self.add_grade_button=button("添加年级",page,grade_operations_layout,0)
        self.add_grade_button.setIcon(FluentIcon.ADD)
        self.add_grade_button.setFixedWidth(200)
        self.add_grade_button.clicked.connect(self.add_grade)

        self.edit_grade_button=button("编辑年级",page,grade_operations_layout,0)
        self.edit_grade_button.setIcon(FluentIcon.EDIT)
        self.edit_grade_button.setFixedWidth(200)
        self.edit_grade_button.setEnabled(False)
        self.edit_grade_button.clicked.connect(self.edit_grade)

        self.del_grade_button=button("删除年级",page,grade_operations_layout,50)
        self.del_grade_button.setIcon(FluentIcon.DELETE)
        self.del_grade_button.setFixedWidth(200)
        self.del_grade_button.setEnabled(False)
        self.del_grade_button.clicked.connect(self.del_grade)

        self.grade_up_button=TransparentToolButton()
        self.grade_up_button.setIcon(FluentIcon.UP)
        self.grade_up_button.setToolTip("上移")
        self.grade_up_button.setEnabled(False)
        self.grade_up_button.clicked.connect(lambda:self.change_grade_pos("up"))
        add_widget(self.grade_up_button,grade_operations_layout)

        self.grade_down_button=TransparentToolButton()
        self.grade_down_button.setIcon(FluentIcon.DOWN)
        self.grade_down_button.setToolTip("下移")
        self.grade_down_button.setEnabled(False)
        self.grade_down_button.clicked.connect(lambda:self.change_grade_pos("down"))
        add_widget(self.grade_down_button,grade_operations_layout)
        grade_operations_layout.addStretch(1)

        self.grade_table=LineTableWidget()
        self.grade_table.setColumnCount(2)
        self.grade_table.setHorizontalHeaderLabels(["年级名称","所含班级"])
        self.grade_table.setColumnWidth(1,1000)
        self.grade_table.verticalHeader().hide()
        self.grade_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.grade_table.clicked.connect(self.refresh_grade_button)
        self.grade_table.itemDoubleClicked.connect(self.edit_grade)
        self.grade_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grade_table.customContextMenuRequested.connect(self.show_grade_menu)
        add_widget(self.grade_table,layout)

        return page

    def build_class_page(self)->QWidget:
        page,layout=self.create_page("班级信息","每个班级在这里设置各学科的任课老师与每周课时。")

        class_operations_layout=QHBoxLayout()
        layout.addLayout(class_operations_layout)

        self.add_class_button=button("添加班级",page,class_operations_layout,0)
        self.add_class_button.setIcon(FluentIcon.ADD)
        self.add_class_button.setFixedWidth(200)
        self.add_class_button.clicked.connect(self.add_class)

        self.edit_class_button=button("编辑班级",page,class_operations_layout,0)
        self.edit_class_button.setIcon(FluentIcon.EDIT)
        self.edit_class_button.setFixedWidth(200)
        self.edit_class_button.setEnabled(False)
        self.edit_class_button.clicked.connect(self.edit_class)

        self.del_class_button=button("删除班级",page,class_operations_layout)
        self.del_class_button.setIcon(FluentIcon.DELETE)
        self.del_class_button.setFixedWidth(200)
        self.del_class_button.setEnabled(False)
        self.del_class_button.clicked.connect(self.del_class)
        class_operations_layout.addStretch(1)

        self.class_table=LineTableWidget()
        self.class_table.setColumnCount(4)
        self.class_table.setHorizontalHeaderLabels(["班级","所属年级","学科","每周课时"])
        self.class_table.setColumnWidth(0,200)
        self.class_table.setColumnWidth(1,200)
        self.class_table.setColumnWidth(2,600)
        self.class_table.setColumnWidth(3,150)
        self.class_table.verticalHeader().hide()
        self.class_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.class_table.itemSelectionChanged.connect(self.refresh_class_button)
        self.class_table.itemDoubleClicked.connect(self.edit_class)
        self.class_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.class_table.customContextMenuRequested.connect(self.show_class_menu)
        add_widget(self.class_table,layout)

        return page

    def build_subject_page(self)->QWidget:
        page,layout=self.create_page("学科信息","学科的排列顺序即课程表里各学科列的顺序，可用右侧按钮上下调整。")

        subject_operations_layout=QHBoxLayout()
        layout.addLayout(subject_operations_layout)

        self.add_subject_button=button("添加学科",page,subject_operations_layout,0)
        self.add_subject_button.setIcon(FluentIcon.ADD)
        self.add_subject_button.setFixedWidth(200)
        self.add_subject_button.clicked.connect(self.add_subject)

        self.rename_subject_button=button("重命名学科",page,subject_operations_layout,0)
        self.rename_subject_button.setIcon(FluentIcon.EDIT)
        self.rename_subject_button.setFixedWidth(200)
        self.rename_subject_button.setEnabled(False)
        self.rename_subject_button.clicked.connect(self.edit_subject)

        self.del_subject_button=button("删除学科",page,subject_operations_layout,50)
        self.del_subject_button.setIcon(FluentIcon.DELETE)
        self.del_subject_button.setFixedWidth(200)
        self.del_subject_button.setEnabled(False)
        self.del_subject_button.clicked.connect(self.del_subject)

        self.subject_up_button=TransparentToolButton()
        self.subject_up_button.setIcon(FluentIcon.UP)
        self.subject_up_button.setToolTip("上移")
        self.subject_up_button.setEnabled(False)
        self.subject_up_button.clicked.connect(lambda:self.change_subject_pos("up"))
        add_widget(self.subject_up_button,subject_operations_layout)

        self.subject_down_button=TransparentToolButton()
        self.subject_down_button.setIcon(FluentIcon.DOWN)
        self.subject_down_button.setToolTip("下移")
        self.subject_down_button.setEnabled(False)
        self.subject_down_button.clicked.connect(lambda:self.change_subject_pos("down"))
        add_widget(self.subject_down_button,subject_operations_layout)
        subject_operations_layout.addStretch(1)

        self.subject_table=LineTableWidget()
        self.subject_table.setColumnCount(4)
        self.subject_table.setHorizontalHeaderLabels(["学科名称","任教班级","任课教师","每周总课时"])
        self.subject_table.setColumnWidth(0,140)
        self.subject_table.setColumnWidth(1,260)
        self.subject_table.setColumnWidth(2,380)
        self.subject_table.setColumnWidth(3,120)
        # 班级/老师较多时不换行撑高行高，超出部分显示省略号，完整内容看悬停提示
        self.subject_table.setWordWrap(False)
        self.subject_table.verticalHeader().hide()
        self.subject_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.subject_table.itemSelectionChanged.connect(self.refresh_subject_button)
        self.subject_table.itemDoubleClicked.connect(self.edit_subject)
        self.subject_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.subject_table.customContextMenuRequested.connect(self.show_subject_menu)
        add_widget(self.subject_table,layout)

        return page

    def build_teacher_page(self)->QWidget:
        page,layout=self.create_page("任课教师","教师名单来自各班的课程信息，也可以先添加教师，再回到“班级”页勾选。")

        teacher_operations_layout=QHBoxLayout()
        layout.addLayout(teacher_operations_layout)

        self.add_teacher_button=button("添加教师",page,teacher_operations_layout,0)
        self.add_teacher_button.setIcon(FluentIcon.ADD)
        self.add_teacher_button.setFixedWidth(200)
        self.add_teacher_button.clicked.connect(self.add_teacher)

        self.rename_teacher_button=button("重命名教师",page,teacher_operations_layout,0)
        self.rename_teacher_button.setIcon(FluentIcon.EDIT)
        self.rename_teacher_button.setFixedWidth(200)
        self.rename_teacher_button.setEnabled(False)
        self.rename_teacher_button.clicked.connect(self.rename_teacher)

        self.del_teacher_button=button("删除教师",page,teacher_operations_layout)
        self.del_teacher_button.setIcon(FluentIcon.DELETE)
        self.del_teacher_button.setFixedWidth(200)
        self.del_teacher_button.setEnabled(False)
        self.del_teacher_button.clicked.connect(self.del_teacher)
        teacher_operations_layout.addStretch(1)

        self.teacher_table=LineTableWidget()
        self.teacher_table.setColumnCount(4)
        self.teacher_table.setHorizontalHeaderLabels(["教师","任教学科","任教班级","每周课时"])
        self.teacher_table.setColumnWidth(0,200)
        self.teacher_table.setColumnWidth(1,300)
        self.teacher_table.setColumnWidth(2,600)
        self.teacher_table.setColumnWidth(3,150)
        self.teacher_table.setWordWrap(False)
        self.teacher_table.verticalHeader().hide()
        self.teacher_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.teacher_table.itemSelectionChanged.connect(self.refresh_teacher_button)
        self.teacher_table.itemDoubleClicked.connect(self.rename_teacher)
        self.teacher_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.teacher_table.customContextMenuRequested.connect(self.show_teacher_menu)
        add_widget(self.teacher_table,layout)

        return page

    # ------------------------------------------------------------------
    # 刷新界面
    # ------------------------------------------------------------------
    def refresh_all(self):
        self.show_grades()
        self.show_classes()
        self.show_subjects()
        self.show_teachers()
        self.refresh_grade_button()
        self.refresh_class_button()
        self.refresh_subject_button()
        self.refresh_teacher_button()

    def mark_pending(self):
        """记录“已修改、待重启生效”的状态"""
        self.pending_restart=True
        self.pending_bar.setVisible(True)
        self.restart_button.setEnabled(True)
        self.restart_banner.show_warning("课程信息已修改",[
            "新的课程信息需要重启应用后才会生效",
            "可以继续修改，完成后点击“立即重启”",
        ])

    def restart_now(self):
        logging.info("用户从课程信息页重启应用")
        Toast.info("正在重启应用","",parent=self,duration=1200)
        restart_app(1200)

    # ------------------------------------------------------------------
    # 年级
    # ------------------------------------------------------------------
    def selected_grade_name(self)->str:
        items=self.grade_table.selectedItems()
        if not items:
            return ""
        item=self.grade_table.item(items[0].row(),0)
        return item.text() if item else ""

    def refresh_grade_button(self):
        name=self.selected_grade_name()
        grade_names=list((cfg.grades_info.value or {}).keys())
        index=grade_names.index(name) if name in grade_names else -1
        self.edit_grade_button.setEnabled(bool(name))
        self.del_grade_button.setEnabled(bool(name))
        self.grade_up_button.setEnabled(index>0)
        self.grade_down_button.setEnabled(0<=index<len(grade_names)-1)

    def show_grades(self):
        grades=cfg.grades_info.value or {}
        self.grade_table.setRowCount(len(grades))
        r=0
        for grade,classes in grades.items():
            name_item=QTableWidgetItem(grade)
            name_item.setTextAlignment(Qt.AlignCenter)
            self.grade_table.setItem(r,0,name_item)
            class_item=QTableWidgetItem("、".join(classes))
            class_item.setTextAlignment(Qt.AlignCenter)
            self.grade_table.setItem(r,1,class_item)
            r+=1

    def show_grade_menu(self,pos):
        show_item_menu(
            self.grade_table,pos,self,
            edit_text="编辑",edit_slot=self.edit_grade,delete_slot=self.del_grade,
            on_selected=self.refresh_grade_button
        )

    def add_grade(self):
        msgbox=GradeMsgbox(self)
        if not msgbox.exec():
            return
        grades=dict(cfg.grades_info.value or {})
        grades[msgbox.grade_name_input.text().strip()]=[item.text for item in msgbox.classes_combo.selectedItems()]
        cfg.grades_info.value=grades
        save_settings()
        # 班级的所属年级跟着变，班级表格要同步刷新
        self.refresh_all()
        self.mark_pending()

    def edit_grade(self):
        grade_name=self.selected_grade_name()
        if not grade_name:
            return
        msgbox=GradeMsgbox(self,True,grade_name)
        if not msgbox.exec():
            return
        new_grade_name=msgbox.grade_name_input.text().strip()
        new_grade_info={}
        for grade in (cfg.grades_info.value or {}):
            if grade==grade_name:
                new_grade_info[new_grade_name]=[item.text for item in msgbox.classes_combo.selectedItems()]
            else:
                new_grade_info[grade]=cfg.grades_info.value[grade]
        cfg.grades_info.value=new_grade_info
        save_settings()
        self.refresh_all()
        self.mark_pending()

    def del_grade(self):
        grade_name=self.selected_grade_name()
        if not grade_name:
            return
        grades=dict(cfg.grades_info.value or {})
        classes=grades.pop(grade_name,[])
        cfg.grades_info.value=grades
        save_settings()
        self.refresh_all()
        self.mark_pending()
        Toast.info("已删除年级",f"“{grade_name}”下的 {len(classes)} 个班级已变为{UNGRADED}",parent=self,duration=3000)

    def change_grade_pos(self,drct:str):
        grade_name=self.selected_grade_name()
        grade_names=list((cfg.grades_info.value or {}).keys())
        if grade_name not in grade_names:
            return
        idx=grade_names.index(grade_name)
        if drct=="up" and idx>0:
            target=idx-1
        elif drct=="down" and idx<len(grade_names)-1:
            target=idx+1
        else:
            return
        grade_names[idx],grade_names[target]=grade_names[target],grade_names[idx]
        grade_info=cfg.grades_info.value or {}
        cfg.grades_info.value={grade:grade_info[grade] for grade in grade_names}
        save_settings()
        # 刷新会重建表格，选中状态要放在刷新之后恢复
        self.refresh_all()
        self.grade_table.setCurrentIndex(self.grade_table.model().index(target,0))
        self.refresh_grade_button()

    # ------------------------------------------------------------------
    # 班级
    # ------------------------------------------------------------------
    def selected_class_name(self)->str:
        items=self.class_table.selectedItems()
        if not items:
            return ""
        item=self.class_table.item(items[0].row(),0)
        return item.text() if item else ""

    def refresh_class_button(self):
        has_class=bool(self.selected_class_name())
        self.edit_class_button.setEnabled(has_class)
        self.del_class_button.setEnabled(has_class)

    def show_classes(self):
        lessons=config_lessons()
        subjects=config_subjects()
        self.class_table.setRowCount(len(lessons))
        for r,row in enumerate(lessons):
            class_name=str(row.get("班级",""))
            class_subjects=[subject for subject in subjects if row_teachers(row,subject)]
            total_hours=sum(row_hours(row,subject) for subject in class_subjects)
            values=[
                class_name,
                class_grade(class_name),
                "、".join(class_subjects) if class_subjects else "（尚未设置任课老师）",
                str(total_hours),
            ]
            for c,value in enumerate(values):
                item=QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.class_table.setItem(r,c,item)

    def show_class_menu(self,pos):
        show_item_menu(
            self.class_table,pos,self,
            edit_text="编辑",edit_slot=self.edit_class,delete_slot=self.del_class,
            on_selected=self.refresh_class_button
        )

    def add_class(self):
        msgbox=ClassMsgbox(self)
        if not msgbox.exec():
            return
        self.apply_class_info(msgbox)
        self.refresh_all()
        self.mark_pending()
        Toast.success("班级已保存",f"“{msgbox.class_name}”将在重启应用后出现在课表中",parent=self,duration=3000)

    def edit_class(self):
        class_name=self.selected_class_name()
        if not class_name:
            return
        msgbox=ClassMsgbox(self,True,class_name)
        if not msgbox.exec():
            return
        self.apply_class_info(msgbox,class_name)
        self.refresh_all()
        self.mark_pending()
        Toast.success("班级已保存","重启应用后生效",parent=self,duration=3000)

    def apply_class_info(self,msgbox:ClassMsgbox,old_name:str|None=None):
        """把班级对话框的结果写进配置"""
        # 对话框里新填的学科追加到学科列表末尾
        subjects=config_subjects()
        for subject in msgbox.new_subjects:
            if subject not in subjects:
                subjects.append(subject)
        if subjects!=config_subjects():
            cfg.subjects_info.value=subjects

        new_row=build_lesson_row(msgbox.class_name,msgbox.teacher_map,msgbox.hours_map)
        lessons=config_lessons()
        names=[str(row.get("班级","")) for row in lessons]
        target=old_name or msgbox.class_name
        if target in names:
            # 原位替换：改名时班级也保持在原来的位置上
            lessons[names.index(target)]=new_row
        else:
            lessons.append(new_row)
        apply_lessons(lessons)

        set_class_grade(msgbox.class_name,msgbox.grade)
        if old_name and old_name!=msgbox.class_name:
            # 规则、并课、其它年级里引用了旧班级名的，一并改名
            rename_reference(old_name,msgbox.class_name)
        save_settings()

    def del_class(self):
        class_name=self.selected_class_name()
        if not class_name:
            return
        dialog=MessageBox(
            "删除班级",
            f"确定要删除班级“{class_name}”吗？\n该班级在年级、生成规则、并课设置中的引用也会被删除",
            self
        )
        if not dialog.exec():
            return
        lessons=[row for row in config_lessons() if str(row.get("班级",""))!=class_name]
        apply_lessons(lessons)
        cleanup_references({class_name},set(),set())
        save_settings()
        self.refresh_all()
        self.mark_pending()
        Toast.success("班级已删除","重启应用后生效",parent=self,duration=3000)

    # ------------------------------------------------------------------
    # 学科
    # ------------------------------------------------------------------
    def selected_subject_name(self)->str:
        items=self.subject_table.selectedItems()
        if not items:
            return ""
        item=self.subject_table.item(items[0].row(),0)
        return item.text() if item else ""

    def refresh_subject_button(self):
        subject=self.selected_subject_name()
        subjects=config_subjects()
        index=subjects.index(subject) if subject in subjects else -1
        self.rename_subject_button.setEnabled(bool(subject))
        self.del_subject_button.setEnabled(bool(subject))
        self.subject_up_button.setEnabled(index>0)
        self.subject_down_button.setEnabled(0<=index<len(subjects)-1)

    def show_subjects(self):
        subjects=config_subjects()
        self.subject_table.setRowCount(len(subjects))
        for r,subject in enumerate(subjects):
            classes,teachers,hours=subject_statistics(subject)
            values=[
                subject,
                "、".join(classes) if classes else "（暂无班级）",
                "、".join(teachers) if teachers else "（暂无任课老师）",
                str(hours),
            ]
            for c,value in enumerate(values):
                item=QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip(value)
                self.subject_table.setItem(r,c,item)

    def show_subject_menu(self,pos):
        show_item_menu(
            self.subject_table,pos,self,
            edit_text="重命名",edit_slot=self.edit_subject,delete_slot=self.del_subject,
            on_selected=self.refresh_subject_button
        )

    def add_subject(self):
        subjects=config_subjects()
        msgbox=SubjectNameMsgbox(self,subjects,subjects)
        if not msgbox.exec():
            return
        name=msgbox.subject_input.text().strip()
        cfg.subjects_info.value=subjects+[name]
        save_settings()
        self.refresh_all()
        self.mark_pending()
        Toast.success("学科已添加",f"“{name}”已加入学科列表，重启应用后生效",parent=self,duration=3000)

    def edit_subject(self):
        old_name=self.selected_subject_name()
        if not old_name:
            return
        subjects=config_subjects()
        msgbox=SubjectNameMsgbox(
            self,subjects,[subject for subject in subjects if subject!=old_name],
            edit=True,subject_name=old_name
        )
        if not msgbox.exec():
            return
        new_name=msgbox.subject_input.text().strip()
        if new_name==old_name:
            return
        rename_subject(old_name,new_name)
        self.refresh_all()
        self.mark_pending()
        Toast.success("学科已重命名",f"“{old_name}”已改为“{new_name}”，重启应用后生效",parent=self,duration=3000)

    def del_subject(self):
        subject=self.selected_subject_name()
        if not subject:
            return
        classes,teachers,hours=subject_statistics(subject)
        dialog=MessageBox(
            "删除学科",
            f"确定要删除学科“{subject}”吗？\n该学科有 {len(classes)} 个班级、每周共 {hours} 课时，"
            f"删除后这些班级的课时与任课老师信息、相关规则与并课设置都会一并删除",
            self
        )
        if not dialog.exec():
            return
        remove_subject(subject)
        cleanup_references(set(),set(),{subject})
        save_settings()
        self.refresh_all()
        self.mark_pending()
        Toast.success("学科已删除","重启应用后生效",parent=self,duration=3000)

    def change_subject_pos(self,drct:str):
        subject=self.selected_subject_name()
        subjects=config_subjects()
        if subject not in subjects:
            return
        idx=subjects.index(subject)
        if drct=="up" and idx>0:
            target=idx-1
        elif drct=="down" and idx<len(subjects)-1:
            target=idx+1
        else:
            return
        subjects[idx],subjects[target]=subjects[target],subjects[idx]
        cfg.subjects_info.value=subjects
        save_settings()
        self.refresh_all()
        self.subject_table.setCurrentIndex(self.subject_table.model().index(target,0))
        self.refresh_subject_button()
        self.mark_pending()

    # ------------------------------------------------------------------
    # 任课教师
    # ------------------------------------------------------------------
    def selected_teacher_name(self)->str:
        items=self.teacher_table.selectedItems()
        if not items:
            return ""
        item=self.teacher_table.item(items[0].row(),0)
        return item.text() if item else ""

    def refresh_teacher_button(self):
        has_teacher=bool(self.selected_teacher_name())
        self.rename_teacher_button.setEnabled(has_teacher)
        self.del_teacher_button.setEnabled(has_teacher)

    def teacher_statistics(self,teacher_name:str)->tuple[list[str],list[str],int]:
        """统计某位老师任教的学科、班级和每周总课时"""
        subjects=[]
        classes=[]
        hours=0
        for row in config_lessons():
            class_name=str(row.get("班级",""))
            for subject in config_subjects():
                if teacher_name not in row_teachers(row,subject):
                    continue
                if subject not in subjects:
                    subjects.append(subject)
                if class_name not in classes:
                    classes.append(class_name)
                hours+=row_hours(row,subject)
        return subjects,classes,hours

    def show_teachers(self):
        teachers=config_teachers()
        self.teacher_table.setRowCount(len(teachers))
        for r,teacher in enumerate(teachers):
            subjects,classes,hours=self.teacher_statistics(teacher)
            values=[
                teacher,
                "、".join(subjects) if subjects else "（暂未任教）",
                "、".join(classes) if classes else "（暂未任教）",
                str(hours),
            ]
            for c,value in enumerate(values):
                item=QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.teacher_table.setItem(r,c,item)

    def show_teacher_menu(self,pos):
        show_item_menu(
            self.teacher_table,pos,self,
            edit_text="重命名",edit_slot=self.rename_teacher,delete_slot=self.del_teacher,
            on_selected=self.refresh_teacher_button
        )

    def add_teacher(self):
        msgbox=TeacherMsgbox(self)
        if not msgbox.exec():
            return
        teachers=config_teachers()
        teachers.append(msgbox.name_input.text().strip())
        cfg.teachers_info.value=teachers
        save_settings()
        self.refresh_all()
        self.mark_pending()

    def rename_teacher(self):
        teacher_name=self.selected_teacher_name()
        if not teacher_name:
            return
        msgbox=TeacherMsgbox(self,True,teacher_name)
        if not msgbox.exec():
            return
        new_name=msgbox.name_input.text().strip()
        if new_name==teacher_name:
            return
        cfg.teachers_info.value=[new_name if teacher==teacher_name else teacher for teacher in config_teachers()]

        lessons=[]
        for row in config_lessons():
            row=dict(row)
            for subject in config_subjects():
                key=f"{subject} - 任课老师"
                teacher_names=split_teacher_names(row.get(key))
                if teacher_name in teacher_names:
                    row[key]=" ".join([new_name if name==teacher_name else name for name in teacher_names])
            lessons.append(row)
        apply_lessons(lessons)
        rename_reference(teacher_name,new_name)
        save_settings()
        self.refresh_all()
        self.mark_pending()
        Toast.success("教师已重命名",f"“{teacher_name}”已改为“{new_name}”，重启应用后生效",parent=self,duration=3000)

    def del_teacher(self):
        teacher_name=self.selected_teacher_name()
        if not teacher_name:
            return
        subjects,classes,hours=self.teacher_statistics(teacher_name)
        dialog=MessageBox(
            "删除教师",
            f"确定要删除教师“{teacher_name}”吗？\n该老师任教 {len(classes)} 个班级、每周 {hours} 课时，"
            f"删除后这些班级对应学科将不再有任课老师，相关规则也会一并清理",
            self
        )
        if not dialog.exec():
            return
        cfg.teachers_info.value=[teacher for teacher in config_teachers() if teacher!=teacher_name]

        lessons=[]
        for row in config_lessons():
            row=dict(row)
            for subject in config_subjects():
                key=f"{subject} - 任课老师"
                teacher_names=split_teacher_names(row.get(key))
                if teacher_name in teacher_names:
                    row[key]=" ".join([name for name in teacher_names if name!=teacher_name])
            lessons.append(row)
        apply_lessons(lessons)
        cleanup_references(set(),{teacher_name},set())
        save_settings()
        self.refresh_all()
        self.mark_pending()
        Toast.success("教师已删除","重启应用后生效",parent=self,duration=3000)

    # ------------------------------------------------------------------
    # 文件导入 / 导出
    # ------------------------------------------------------------------
    def download_template(self):
        filename,_=QFileDialog.getSaveFileName(
            self,
            "保存课程信息模板",
            "",
            "Excel文件 (*.xlsx *.xls)"
        )
        if not filename:
            return
        try:
            shutil.copy("template.xlsx",filename)
            os.startfile(filename)
        except Exception as error:
            logging.error(f"下载课程信息模板失败：\n{traceback.format_exc()}")
            show_error(self,error)

    def upload_lessons_info(self):
        user_info_file,_=QFileDialog.getOpenFileName(
            self,
            "选择课程信息文件",
            "",
            "Excel文件 (*.xlsx *.xls)"
        )
        if not user_info_file:
            logging.debug("用户取消选择课程信息文件")
            return
        logging.info(f"选择课程信息文件: {user_info_file}")
        try:
            logging.debug("开始解析课程信息文件")
            user_info=pd.read_excel(user_info_file)
            rename_dict={}
            for i in range(2,len(user_info.keys()),2):
                rename_dict[user_info.keys()[i]]=user_info.keys()[i-1]+" - 任课老师"
                rename_dict[user_info.keys()[i-1]]=user_info.keys()[i-1]+" - 课时"
            user_info=user_info.rename(columns=rename_dict)
            new_lessons_info=user_info.to_dict(orient="records")
            new_classes=[]
            for class_ in new_lessons_info:
                new_classes.append(class_["班级"])
                for key,value in class_.items():
                    if pd.isna(value):
                        class_[key]=None

            new_subjects=[user_info.keys()[i][:-len(" - 课时")] for i in range(1,len(user_info.keys()),2)]
            new_teachers=set()
            for subject in new_subjects:
                # 一个单元格里可能填了多个老师（联合授课），要拆成多位老师
                for cell in user_info[subject+" - 任课老师"].to_list():
                    new_teachers|=set(split_teacher_names(cell))
            new_teachers=sorted(name for name in new_teachers if not pd.isna(name))

            logging.debug(f"解析完成：{len(new_classes)}个班级，{len(new_subjects)}个科目，{len(new_teachers)}个老师")
            diff_classes,diff_teachers,diff_subjects=diff_cfg(new_classes,new_teachers,new_subjects)
            if diff_classes or diff_teachers or diff_subjects:
                logging.warning(f"检测到差异：{len(diff_classes)}个班级, {len(diff_teachers)}个老师, {len(diff_subjects)}个科目")

            dialog=MessageBox(
                "确认要更新课程信息表吗？",
                "以下班级在新课程信息表中不存在：\n"+"、".join(diff_classes)+
                "\n以下老师在新课程信息表中不存在：\n"+"、".join(diff_teachers)+
                "\n以下科目在新课程信息表中不存在：\n"+"、".join(diff_subjects)+
                "\n与以上信息相关的设置将被删除",
                self
            )
            if not dialog.exec():
                logging.info("用户取消更新课程信息")
                return

            cfg.lessons_info.value=new_lessons_info
            cfg.subjects_info.value=new_subjects
            cfg.teachers_info.value=new_teachers
            cleanup_references(diff_classes,diff_teachers,diff_subjects)
            save_settings()
            self.refresh_all()
            logging.info("课程信息表更新成功，准备重启应用")
            Toast.success("课程信息表更新成功，应用将自动重启","",parent=self,duration=1500)
            restart_app(1500)
        except Exception as error:
            logging.error(f"解析课程信息文件时出错：\n{traceback.format_exc()}")
            show_error(self,error)
