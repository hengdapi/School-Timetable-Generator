"""生成页面用到的各种对话框（前端组件，不含业务逻辑）"""

import os.path

from PySide6.QtCore import QSize

from pages.ui_widgets import *


class SaveTimetablePlan(MessageBoxBase):
    def __init__(self, plan_time, parent=None):
        super().__init__(parent=parent)
        subheader("保存课程表方案",self,self.viewLayout)
        write("方案名称（若选择已有方案名称则覆盖该方案）：",self,self.viewLayout,0)
        self.name_input=EditableComboBox()
        self.name_input.addItems(cfg.timetable_plans.value.keys())
        self.name_input.setCompleter(QCompleter(cfg.timetable_plans.value.keys(),self.name_input))
        self.name_input.setText(f"{plan_time} 保存的方案")
        self.name_input.textChanged.connect(self.on_input_name)
        add_widget(self.name_input,self.viewLayout)
        write("方案描述：",self,self.viewLayout,0)
        self.desc_input=LineEdit()
        add_widget(self.desc_input,self.viewLayout)
        self.yesButton.setText("保存方案")
        self.yesButton.setIcon(FluentIcon.SAVE)
        self.cancelButton.setText("取消")
        
    def validate(self) -> bool:
        if not self.name_input.text():
            Toast.error("请输入方案名称","",duration=-1,parent=self)
            return False
        return True

    def on_input_name(self):
        if self.name_input.text() in cfg.timetable_plans.value:
            self.desc_input.setText(cfg.timetable_plans.value[self.name_input.text()]["desc"])
            self.yesButton.setText("覆盖方案")
        else:
            self.yesButton.setText("保存方案")

class LoadTimetablePlan(MessageBoxBase):
    def __init__(self,parent=None):
        super().__init__(parent=parent)
        subheader("加载课程表方案",self,self.viewLayout)
        self.plan_list=RoundListWidget(self)
        # 通过自定义 Delegate 设置项高度（不破坏原有 QSS）
        self.delegate=RoundListItemDelegate(self.plan_list)
        self.delegate.sizeHint=lambda option,idx:QSize(option.rect.width(),72)
        self.plan_list.setItemDelegate(self.delegate)
        for plan_name,plan_info in cfg.timetable_plans.value.items():
            self.plan_list.addItem(f"{plan_name}\n保存时间：{plan_info['time']}\n描述：{plan_info['desc']}")
        add_widget(self.plan_list,self.viewLayout,0)
        self.yesButton.setText("加载方案")
        self.yesButton.setIcon(FluentIcon.HISTORY)

    def validate(self) -> bool:
        if not self.plan_list.selectedItems():
            Toast.error("请选择要加载的方案","",duration=-1,parent=self)
            return False
        plan_name=self.plan_list.selectedItems()[0].text().split("\n")[0]
        if not os.path.exists(os.path.join(appdata,cfg.timetable_plans.value[plan_name]["filename"])):
            Toast.error("方案文件已丢失，无法加载","",duration=-1,parent=self)
            return False
        return True

class DelTimetablePlan(MessageBoxBase):
    def __init__(self,parent=None):
        super().__init__(parent=parent)
        subheader("删除课程表方案",self,self.viewLayout)
        write("在下方列表拖动或按住ctrl可多选：",self,self.viewLayout,0)
        self.plan_list=RoundListWidget(self)
        # 通过自定义 Delegate 设置项高度（不破坏原有 QSS）
        self.delegate=RoundListItemDelegate(self.plan_list)
        self.delegate.sizeHint=lambda option,idx:QSize(option.rect.width(),72)
        self.plan_list.setItemDelegate(self.delegate)
        self.plan_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for plan_name,plan_info in cfg.timetable_plans.value.items():
            self.plan_list.addItem(f"{plan_name}\n保存时间：{plan_info['time']}\n描述：{plan_info['desc']}")
        add_widget(self.plan_list,self.viewLayout,0)
        self.yesButton.setText("删除方案")
        self.yesButton.setIcon(FluentIcon.DELETE)

    def validate(self) -> bool:
        if not self.plan_list.selectedItems():
            Toast.error("请选择要删除的方案","",duration=-1,parent=self)
            return False
        return True

class ForceExchangeMsgbox(MessageBoxBase):
    def __init__(self,failed_reasons:set[str],conflict_lessons:set[tuple[Class,Time]], parent=None):
        super().__init__(parent=parent)
        subheader("强制调课",self,self.viewLayout)
        write("由于以下原因，您的调课操作无法完成：",self,self.viewLayout,0)
        self.reason_list=RoundListWidget()
        self.reason_list.setFixedSize(700,min(len(failed_reasons)*50,230))
        self.reason_list.addItems(failed_reasons)
        add_widget(self.reason_list,self.viewLayout,0)
        write("是否要强制调课？",self,self.viewLayout,0)
        if conflict_lessons:
            write("强制调课后，以下导致冲突的课程将会自动放在对应班级的暂存区中：",self,self.viewLayout,0)
            self.conflict_list=RoundListWidget()
            self.conflict_list.setFixedSize(700,min(len(conflict_lessons)*50,230))
            for lesson in conflict_lessons:
                self.conflict_list.addItem(f"{lesson[0]} {lesson[1]} {lesson[0].get_lessons(lesson[1])[0 if lesson[1].all or lesson[1].sin else 1]}")
            add_widget(self.conflict_list,self.viewLayout,0)
        write("若原因中包含规则冲突，强制调课后将无视导致冲突的规则",self,self.viewLayout,0)
        self.yesButton.setText("强制调课")
        self.yesButton.setIcon(FluentIcon.SYNC)

class SelectCustomClassesMsgbox(MessageBoxBase):
    def __init__(self,mode:str,parent=None):
        super().__init__(parent=parent)
        if mode=="generate":
            subheader("自定义生成部分课表",self,self.viewLayout)
            write("请选择为哪些班级生成课表：",self,self.viewLayout,0)
            self.yesButton.setText("生成课表")
            self.yesButton.setIcon(FluentIcon.BRUSH)
        else:
            subheader("自定义清空部分课表",self,self.viewLayout)
            write("请选择清空哪些班级的课表：",self,self.viewLayout,0)
            self.yesButton.setText("清空课表")
            self.yesButton.setIcon(FluentIcon.DELETE)
        self.class_combo=ClassMultiSelectionCombobox()
        add_widget(self.class_combo,self.viewLayout)

    def validate(self) -> bool:
        if not self.class_combo.checkedTexts():
            Toast.error("请选择班级","",duration=-1,parent=self)
            return False
        return True

class ChooseLessonMsgbox(MessageBoxBase):
    """某个位置有多节课时，选择要跳转到哪一节"""

    def __init__(self,title:str,lessons:list[tuple[Class,Subject,Time]],parent=None):
        """
        :param title: 弹窗标题（说明是谁在该位置有多少节课）
        :param lessons: 多个班级课程组成的列表，每个元素为(班级,学科,Time)
        :param parent: 父窗口
        """
        super().__init__(parent=parent)
        self.lessons=lessons
        self.selected_lesson=None  # 用户选择的结果
        subheader(title,self,self.viewLayout)
        write("双击时可跳转到对应班级的对应课程，请选择要跳转的课程：",self,self.viewLayout,0)
        self.class_list=RoundListWidget(self)
        # 通过自定义 Delegate 设置项高度（不破坏原有 QSS）
        self.delegate=RoundListItemDelegate(self.class_list)
        self.delegate.sizeHint=lambda option,idx:QSize(option.rect.width(),48)
        self.class_list.setItemDelegate(self.delegate)
        self.class_list.setFixedHeight(min(len(lessons)*50,300))
        for clas,subject,time in lessons:
            self.class_list.addItem(f"{clas}  {subject}  {time}")
        add_widget(self.class_list,self.viewLayout,0)
        self.yesButton.setText("跳转")
        self.yesButton.setIcon(FluentIcon.SEND)

    def validate(self) -> bool:
        if not self.class_list.selectedItems():
            Toast.error("请先选择课程","",duration=-1,parent=self)
            return False
        selected_row=self.class_list.indexFromItem(self.class_list.selectedItems()[0]).row()
        if 0<=selected_row<len(self.lessons):
            self.selected_lesson=self.lessons[selected_row]
        return True
