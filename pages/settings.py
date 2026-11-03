# coding=utf-8
import shutil

from core.rules import *
from pages.timeline import TimelineEditor
from pages.ui_widgets import *

class RuleMessageBox(MessageBoxBase):
    def __init__(self,parent=None,edit=False,rule:Rule=None):
        super().__init__(parent)
        self.curr_rule=rule
        self.edit=edit
        if edit:
            self.yesButton.setText("编辑规则")
            subheader("编辑规则",self,self.viewLayout)
        else:
            self.yesButton.setText("添加规则")
            subheader("添加规则",self,self.viewLayout)
        self.cancelButton.setText("取消")
        self.times=[day+lesson2str(lesson) for day in days[1:] for lesson in range(1,cfg.day_class_num+1)]
        self.string_elements={}
        self.string_layouts=[]

        self.rule_combo=ComboBox()
        self.rule_combo.setPlaceholderText("请选择规则类型")
        for type,rule_class in rule_types.items():
            self.rule_combo.addItem(rule_class.text.replace("|"," "),userData=[rule_class,type])
        add_widget(self.rule_combo,self.viewLayout,0)
        if edit:
            self.rule_combo.setCurrentText(rule.text.replace("|"," "))
            self.show_rule_strings()
        else:
            self.rule_combo.setCurrentIndex(-1)
        self.rule_combo.currentIndexChanged.connect(self.show_rule_strings)

    def check_rule(self,new_rule:Rule):
        rules=lesson_info.rules
        if self.edit and self.curr_rule in rules:
            rules.remove(self.curr_rule)
        if new_rule==self.curr_rule:
            return True,None
        if not new_rule.validate():
            return False,new_rule
        for rule in rules:
            if not rule.check_conflict(new_rule):
                return False,rule
        return True,None

    def show_rule_strings(self):
        rule_class:Rule=self.rule_combo.currentData()[0]
        name=rule_class.text
        for layout in self.string_layouts:
            while layout.count():
                item=layout.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
        if hasattr(self,"scope_combo"):
            self.scope_combo.deleteLater()
            self.scope_label.deleteLater()
            self.scope_tip.deleteLater()
            self.desc_label.deleteLater()
        self.string_elements.clear()

        self.desc_label=write(f"规则说明：{rule_class.desc}",self,self.viewLayout,0)
        self.desc_label.setFont(QFont("Microsoft YaHei",12))
        name=name.split("|")
        string_layout=QGridLayout()
        for i in range(len(name)):
            string=name[i]
            if string[0]=="{" and string[-1]=="}":
                string_name=string[1:-1]
                self.viewLayout.addLayout(string_layout)
                name_label=BodyLabel()
                name_label.setFont(fonts.write)
                name_label.setMaximumWidth(200)
                name_label.setText(f"请填写{string_name}字段：")
                string_layout.addWidget(name_label,i,0,alignment=Qt.AlignmentFlag.AlignLeft)
                if rule_class.args[string_name].type=="multi":
                    input_widget=MultiSelectComboBox()
                    input_widget.setChipsMode(True)
                elif rule_class.args[string_name].type=="single":
                    input_widget=EditableComboBox()
                elif rule_class.args[string_name].type=="int":
                    input_widget=SpinBox()
                    input_widget.setRange(1,1000)
                else:
                    input_widget=LineEdit()
                items=[]
                if "subject" in string_name:
                    items=cfg.subjects_info.value
                elif "time" in string_name:
                    input_widget=TimeMultiSelectionCombobox()
                elif "teacher" in string_name:
                    items=cfg.teachers_info.value
                if isinstance(input_widget,(EditableComboBox,MultiSelectComboBox)):
                    input_widget.addItems(items)
                    if isinstance(input_widget,EditableComboBox):
                        input_widget.setCompleter(QCompleter(items,input_widget))
                if self.edit and hasattr(self.curr_rule,string_name):
                    if isinstance(input_widget,EditableComboBox):
                        input_widget.setCurrentText(str(getattr(self.curr_rule,string_name)))
                    elif isinstance(input_widget,MultiSelectComboBox):
                        if isinstance(input_widget,TimeMultiSelectionCombobox):
                            input_widget.setCheckedTexts([str(time) for time in getattr(self.curr_rule,string_name)])
                        else:
                            input_widget.setSelectedIndices({items.index(str(item)) for item in getattr(self.curr_rule,string_name)})
                    elif isinstance(input_widget,SpinBox):
                        input_widget.setValue(getattr(self.curr_rule,string_name))
                input_widget.setMaximumWidth(400)
                string_layout.addWidget(input_widget,i,1)
                self.string_layouts.append(string_layout)
                self.string_elements[string_name]=[name_label,input_widget]
        self.scope_label=BodyLabel()
        self.scope_label.setText("请选择规则生效范围：")
        self.scope_label.setFont(fonts.write)
        self.scope_label.setMaximumWidth(200)
        string_layout.addWidget(self.scope_label,i+1,0,alignment=Qt.AlignmentFlag.AlignLeft)
        self.scope_combo=ClassMultiSelectionCombobox()
        self.scope_combo.setMaximumWidth(400)
        if self.edit:
            self.scope_combo.setCheckedTexts([clas.name for clas in self.curr_rule.scope])
        else:
            self.scope_combo.setAllItemsChecked(True)
        string_layout.addWidget(self.scope_combo,i+1,1)
        self.scope_tip=write("为范围之外的班级排课时，程序将不会检查是否满足本条规则",self,self.viewLayout,0)

    def validate(self) -> bool:
        name,kind=self.rule_combo.currentData()
        new_rule={"type":kind}
        for string_name,elements in self.string_elements.items():
            input_widget=elements[1]
            if isinstance(input_widget,EditableComboBox):
                if input_widget.currentText() not in [item.text for item in input_widget.items]:
                    settings_error(self,f"请填写字段“{string_name}”")
                    return False
                new_rule[string_name]=input_widget.currentText()
            elif isinstance(input_widget,MultiSelectComboBox):
                if not input_widget.selectedItems():
                    settings_error(self,f"请填写字段“{string_name}”")
                    return False
                new_rule[string_name]=[item.text for item in input_widget.selectedItems()]
            elif isinstance(input_widget,SpinBox):
                new_rule[string_name]=input_widget.value()
        if not self.scope_combo.checkedItems():
            settings_error(self,"请选择规则生效范围")
            return False
        new_rule["scope"]=self.scope_combo.checkedTexts()
        self.new_rule=get_rule(**new_rule)
        success,rule=self.check_rule(self.new_rule)
        if not success:
            settings_error(self,"新规则冲突、重复或不合法："+str(rule))
        return success

class MergeLessonsMsgbox(MessageBoxBase):
    def __init__(self,parent=None):
        super().__init__(parent)
        subheader("设置并课",self,self.viewLayout)
        self.merged_lessons_list=RoundListWidget()
        self.merged_lessons_list.currentItemChanged.connect(self.on_list_selected)
        self.merged_lessons_list.clicked.connect(self.refresh_button_states)
        self.viewLayout.addWidget(self.merged_lessons_list)
        self.operation_layout=QGridLayout()
        self.operation_layout.setColumnStretch(1,1)
        self.operation_layout.addWidget(write("并课班级：",self,QVBoxLayout()),0,0)
        self.operation_layout.addWidget(write("并课学科：",self,QVBoxLayout()),1,0)
        self.class_combo=ClassMultiSelectionCombobox()
        self.class_combo.setMaximumWidth(400)
        self.operation_layout.addWidget(self.class_combo,0,1)
        self.subject_combo=ComboBox()
        self.subject_combo.setMaximumWidth(400)
        self.subject_combo.addItems(lesson_info.subject_names)
        self.operation_layout.addWidget(self.subject_combo,1,1)
        self.viewLayout.addLayout(self.operation_layout)

        self.yesButton.setText("添加并课")
        self.yesButton.setIcon(FluentIcon.ADD)
        self.editButton=PushButton("编辑并课")
        self.editButton.setIcon(FluentIcon.EDIT)
        self.editButton.clicked.connect(self.edit_lesson)
        self.buttonLayout.insertWidget(1,self.editButton)
        self.deleteButton=PushButton("删除并课")
        self.deleteButton.setIcon(FluentIcon.DELETE)
        self.deleteButton.clicked.connect(self.del_lesson)
        self.buttonLayout.insertWidget(2,self.deleteButton)
        self.cancelButton.setText("设置完成")
        self.cancelButton.setIcon(FluentIcon.CLOSE)
        self.refresh_lessons_list()

    def refresh_button_states(self):
        self.editButton.setEnabled(bool(self.merged_lessons_list.selectedItems()))
        self.deleteButton.setEnabled(bool(self.merged_lessons_list.selectedItems()))

    def refresh_lessons_list(self):
        self.merged_lessons_list.clear()
        self.merged_lessons_list.setFixedHeight(min(275,len(cfg.merged_lessons.value)*50))
        for merged_lesson in cfg.merged_lessons.value:
            item=QListWidgetItem(f"{", ".join(merged_lesson[1])} 的 {merged_lesson[0]} 学科并课")
            item.setData(Qt.UserRole,merged_lesson)
            self.merged_lessons_list.addItem(item)
        self.refresh_button_states()

    def check(self):
        if len(self.class_combo.checkedClasses())<2:
            Toast.error("请选择至少2个并课班级","",parent=self,duration=2000)
            return False
        if not self.subject_combo.currentText():
            Toast.error("请选择并课学科","",parent=self,duration=2000)
            return False
        if (self.subject_combo.currentText(),self.class_combo.checkedTexts()) in cfg.merged_lessons.value:
            Toast.error("该组并课设置已存在","",parent=self,duration=2000)
            return False
        for merged_lesson in cfg.merged_lessons.value:
            if merged_lesson[0]==self.subject_combo.currentText() and set(merged_lesson[1])&set(self.class_combo.checkedTexts()):
                Toast.error("并课设置冲突",f"与并课设置“{", ".join(merged_lesson[1])} 的 {merged_lesson[0]} 学科并课”冲突",parent=self,duration=-1)
                return False
        return True

    def validate(self) -> bool:
        if not self.check():
            return False
        cfg.merged_lessons.value.append((self.subject_combo.currentText(),self.class_combo.checkedTexts()))
        save_settings()
        self.refresh_lessons_list()
        return False

    def on_list_selected(self,item:QListWidgetItem):
        if not item:
            return
        merged_lesson=item.data(Qt.UserRole)
        self.subject_combo.setCurrentText(merged_lesson[0])
        self.class_combo.setCheckedTexts(merged_lesson[1])
        self.refresh_button_states()

    def del_lesson(self):
        if not self.merged_lessons_list.selectedItems():
            return
        selected_item=self.merged_lessons_list.selectedItems()[0]
        cfg.merged_lessons.value.remove(selected_item.data(Qt.UserRole))
        save_settings()
        self.refresh_lessons_list()

    def edit_lesson(self):
        if not self.merged_lessons_list.selectedItems() or not self.check():
            return
        selected_item=self.merged_lessons_list.selectedItems()[0]
        idx=cfg.merged_lessons.value.index(selected_item.data(Qt.UserRole))
        cfg.merged_lessons.value.remove(selected_item.data(Qt.UserRole))
        cfg.merged_lessons.value.insert(idx,(self.subject_combo.currentText(),self.class_combo.checkedTexts()))
        save_settings()
        self.refresh_lessons_list()
        # 刷新后行号重新映射，按原位置重新选中，保持编辑焦点
        self.merged_lessons_list.setCurrentRow(idx)

class Settings(QFrame):
    def save_cfg(self,attr:str,value):
        setattr(getattr(cfg,attr),"value",value)
        save_settings()

    def on_class_num_changed(self,time=None):
        if time:
            logging.info(f"修改{"上午" if time=="morning" else "下午"}课程数量")
        if cfg.day_class_num>len(cfg.lessons_time.value):
            for lesson in range(len(cfg.lessons_time.value)+1,cfg.day_class_num+1):
                cfg.lessons_time.value[str(lesson)]=[[0,0],[0,0]]
        save_settings()
        # 新增课次的起止时间默认为空，需要重新校验并提示
        self.refresh_time_warnings()

    def merge_lessons(self):
        MergeLessonsMsgbox(self).exec()
        # 只重建并课信息：重新解析整个课程信息会换掉所有班级对象，
        # 界面缓存的班级、已生成的课表、各规则引用的班级就全对不上了
        lesson_info.parse_merged_lessons()

    def enable_rule_button(self):
        self.edit_rule_button.setEnabled(True)
        self.del_rule_button.setEnabled(True)

    def add_rule(self):
        logging.info("用户点击添加规则按钮")
        rule_dialog=RuleMessageBox(self)
        if rule_dialog.exec():
            cfg.rules.value.append(rule_dialog.new_rule.to_dict())
            save_settings()
            # 重新应用规则，让新规则的副作用立刻写到各班级对象上
            apply_rules()
            self.show_rules()
            logging.info("成功添加规则")
        else:
            logging.info("用户取消添加规则")

    def edit_rule(self):
        curr_item=self.rule_list.selectedItems()[0]
        curr_rule=curr_item.data(Qt.UserRole)
        logging.info("用户编辑规则")
        rule_dialog=RuleMessageBox(self,True,curr_rule)
        if rule_dialog.exec():
            rule_index=self.rule_list.row(curr_item)
            old_rule=curr_rule.to_dict()
            new_rule=rule_dialog.new_rule.to_dict()
            # 原地替换，保持规则的原有顺序不变
            if old_rule in cfg.rules.value:
                cfg.rules.value[cfg.rules.value.index(old_rule)]=new_rule
            elif 0<=rule_index<len(cfg.rules.value):
                cfg.rules.value[rule_index]=new_rule
            else:
                cfg.rules.value.append(new_rule)
            save_settings()
            # 重新应用规则，让编辑结果立刻写到各班级对象上
            apply_rules()
            self.show_rules()
            # 保持编辑后规则的选中状态
            if rule_index<self.rule_list.count():
                self.rule_list.setCurrentRow(rule_index)
            logging.info("规则编辑成功")
        else:
            logging.debug("用户取消编辑规则")

    def del_rule(self):
        try:
            selected_rule=self.rule_list.selectedItems()[0]
            rule_data=selected_rule.data(Qt.UserRole)
            logging.info("用户删除规则")
            cfg.rules.value.remove(rule_data.to_dict())
            save_settings()
            # 重新应用规则，把被删除规则产生的副作用一并清除
            apply_rules()
            self.rule_list.takeItem(self.rule_list.row(selected_rule))
            self.del_rule_button.setEnabled(bool(len(lesson_info.rules)))
            self.edit_rule_button.setEnabled(bool(len(lesson_info.rules)))
            logging.info("规则删除成功")
        except Exception as error:
            e=traceback.format_exc()
            logging.error(f"删除规则时出错：\n{e}")
            show_error(self,error)

    def show_rules(self):
        self.rule_list.clear()
        for rule in lesson_info.rules:
            item=QListWidgetItem(str(rule))
            item.setData(Qt.UserRole,rule)
            self.rule_list.addItem(item)

    def show_rule_menu(self,pos):
        """规则列表右键菜单：编辑、删除"""
        item=self.rule_list.itemAt(pos)
        if not item:
            return
        self.rule_list.setCurrentItem(item)
        self.enable_rule_button()
        menu=RoundMenu(parent=self)
        edit_action=Action(FluentIcon.EDIT,"编辑")
        edit_action.triggered.connect(self.edit_rule)
        menu.addAction(edit_action)
        delete_action=Action(FluentIcon.DELETE,"删除")
        delete_action.triggered.connect(self.del_rule)
        menu.addAction(delete_action)
        menu.exec(self.rule_list.viewport().mapToGlobal(pos),aniType=MenuAnimationType.DROP_DOWN)

    def on_drag_rules(self):
        new_rules=[]
        for i in range(self.rule_list.count()):
            item=self.rule_list.item(i)
            rule=item.data(Qt.UserRole)
            if rule:
                new_rules.append(rule.to_dict())

        # 更新配置并保存
        cfg.rules.value=new_rules
        save_settings()

        # 重新应用规则，同步 lesson_info.rules 及各班级的规则数据
        apply_rules()

    def open_timeline_editor(self):
        """打开时间段活动编辑窗口（独立窗口）"""
        if self.timeline_window is None:
            self.timeline_window=TimelineEditor(self.window())
            self.timeline_window.destroyed.connect(self.on_timeline_window_closed)
            # 时间轴里改完时间后同步刷新本页的时间冲突提示
            self.timeline_window.dataChanged.connect(self.on_timeline_data_changed)
        self.timeline_window.show()
        self.timeline_window.raise_()
        self.timeline_window.activateWindow()

    def on_timeline_window_closed(self):
        self.timeline_window=None

    def on_timeline_data_changed(self):
        """时间段编辑窗口里的时间被修改，同步刷新本页的时间冲突提示"""
        self.refresh_time_warnings()

    @staticmethod
    def format_clock(time:list[int])->str:
        """把 [时,分] 格式化成为 HH:MM"""
        return f"{time[0]:02d}:{time[1]:02d}"

    @staticmethod
    def limit_warning_messages(messages:list[str],max_num:int=10)->list[str]:
        """限制横幅中显示的冲突条数，避免配置错误过多时横幅过长"""
        if len(messages)<=max_num:
            return messages
        return messages[:max_num]+[f"……等共 {len(messages)} 处时间冲突"]

    def check_time_valid(self)->tuple[list[str],list[str]]:
        """
        校验课程起止时间与活动起止时间是否合法：

        - 每节课、每个活动的结束时间必须晚于开始时间
        - 各课次的时间不能互相交叉
        - 各活动的时间不能互相交叉
        - 活动时间不能与任何课次的时间交叉

        返回 (课程警告,活动警告)；课程与活动的时间都在“时间段编辑”窗口里修改，
        这里只负责把冲突提示显示在设置页的“课程起止时间”卡片下方。
        """
        lesson_messages=[]
        activity_messages=[]
        lessons=[]  # (名称,开始分钟,结束分钟,起止文本)
        for lesson in range(1,cfg.day_class_num+1):
            start,end=cfg.lessons_time.value[str(lesson)]
            name=Time(1,lesson).to_str(False,True)
            span=f"{self.format_clock(start)} ~ {self.format_clock(end)}"
            start_minutes,end_minutes=start[0]*60+start[1],end[0]*60+end[1]
            if end_minutes<=start_minutes:
                lesson_messages.append(f"{name}（{span}）的结束时间必须晚于开始时间")
                continue
            lessons.append((name,start_minutes,end_minutes,span))
        # 各课次之间不能交叉
        for idx,(name,start_minutes,end_minutes,span) in enumerate(lessons):
            for other_name,other_start,other_end,other_span in lessons[idx+1:]:
                if start_minutes<other_end and other_start<end_minutes:
                    lesson_messages.append(f"{name}（{span}）与{other_name}（{other_span}）时间交叉")
        # 活动自身的起止时间
        activities=[]
        for activity,(start,end) in cfg.activity_info.value.items():
            span=f"{self.format_clock(start)} ~ {self.format_clock(end)}"
            start_minutes,end_minutes=start[0]*60+start[1],end[0]*60+end[1]
            if end_minutes<=start_minutes:
                activity_messages.append(f"活动“{activity}”（{span}）的结束时间必须晚于开始时间")
                continue
            activities.append((activity,start_minutes,end_minutes,span))
        # 各活动之间不能交叉
        for idx,(name,start_minutes,end_minutes,span) in enumerate(activities):
            for other_name,other_start,other_end,other_span in activities[idx+1:]:
                if start_minutes<other_end and other_start<end_minutes:
                    activity_messages.append(
                        f"活动“{name}”（{span}）与活动“{other_name}”（{other_span}）时间交叉"
                    )
        # 活动与课次之间不能交叉
        for name,start_minutes,end_minutes,span in activities:
            for lesson_name,lesson_start,lesson_end,lesson_span in lessons:
                if start_minutes<lesson_end and lesson_start<end_minutes:
                    message=f"活动“{name}”（{span}）与{lesson_name}（{lesson_span}）时间交叉"
                    activity_messages.append(message)
                    lesson_messages.append(message)
        return self.limit_warning_messages(lesson_messages),self.limit_warning_messages(activity_messages)

    def refresh_time_warnings(self):
        """
        刷新课程与活动时间的警告横幅。

        校验不通过时只弹出 warning 横幅提示，不阻止用户保存配置；
        全部合法时隐藏横幅，并自动按时间顺序排列活动。
        """
        # 页面尚未构建完对应区域时直接跳过
        if self.time_banner is None:
            return
        lesson_messages,activity_messages=self.check_time_valid()
        messages=[]
        for message in lesson_messages+activity_messages:
            if message not in messages:
                messages.append(message)
        if messages:
            self.time_banner.show_warning("时间设置有冲突",messages)
        else:
            self.time_banner.hide_warning()
            self.sort_activities()

    def sort_activities(self):
        """时间全部合法时，按开始时间（相同则按结束时间）为活动排序"""
        activities=sorted(
            cfg.activity_info.value.items(),
            key=lambda item:(item[1][0][0]*60+item[1][0][1],item[1][1][0]*60+item[1][1][1])
        )
        if [name for name,_ in activities]==list(cfg.activity_info.value.keys()):
            return
        cfg.activity_info.value=dict(activities)
        save_settings()
        logging.info("活动已按时间顺序重新排序")

    def export_settings(self):
        filename,_=QFileDialog.getSaveFileName(self,"导出设置","","JSON 文件(*.json)")
        if not filename:
            logging.debug("用户取消导出设置")
            return
        logging.info(f"导出设置文件: {filename}")
        shutil.copy2(settings_file,filename)
        Toast.success("成功导出设置",f"已导出至{filename}",parent=self)
        logging.info("设置导出成功")

    def import_settings(self):
        global cfg
        filename,_=QFileDialog.getOpenFileName(self,"导入设置","","JSON 文件(*.json)")
        if not filename:
            logging.debug("用户取消导入设置")
            return
        logging.info(f"导入设置文件: {filename}")
        shutil.copy2(filename,settings_file)
        Toast.success("成功导入设置",f"已导入{filename}",parent=self,duration=3000)
        Toast.info("应用将自动重启以使设置生效","",parent=self,duration=1500)
        logging.info("设置导入成功，准备重启应用")
        cfg=load_settings()
        restart_app(1500)

    def __init__(self,parent=None):
        try:
            super().__init__(parent=parent)
            logging.info("开始加载设置页面")
            self.setObjectName("Settings")
            # 课程/活动时间合法性警告横幅，在构建对应区域时创建
            self.time_banner=None
            # 时间段编辑独立窗口（避免被垃圾回收，关闭后自动置空）
            self.timeline_window=None
            main_layout=QVBoxLayout(self)
            main_layout.setContentsMargins(20,20,0,0)

            self.scroll_area=SingleDirectionScrollArea(orient=Qt.Vertical)
            self.scroll_area.setStyleSheet("QScrollArea{background: transparent; border: none}")
            self.scroll_area.setWidgetResizable(True)

            view=QWidget()
            view.setStyleSheet("QWidget{background: transparent}")
            self.layout = QVBoxLayout(view)

            self.title = title("设置",self,self.layout)

            biggersubheader("导出/导入",self,self.layout)
            settingio_layout=QHBoxLayout()

            self.export_setting_button=button("导出设置",self,settingio_layout)
            self.export_setting_button.setFixedSize(130,40)
            self.export_setting_button.setIcon(FluentIcon.SHARE)
            self.export_setting_button.clicked.connect(self.export_settings)

            self.import_setting_button=button("导入设置",self,settingio_layout)
            self.import_setting_button.setFixedSize(130,40)
            self.import_setting_button.setIcon(FluentIcon.DOWNLOAD)
            self.import_setting_button.clicked.connect(self.import_settings)

            settingio_layout.addStretch(1)
            self.layout.addLayout(settingio_layout)
            self.layout.addSpacing(20)

            add_widget(SeparatorWidget(orient=Qt.Horizontal),self.layout)
            # 上课节次与时间设置区域（课程信息本身在“课程信息”页面管理）
            biggersubheader("上课时间",self,self.layout)

            # 设置每天上午和下午的课程数量
            self.morning_class_num=RangeSettingCard(cfg.morning_class_num,FluentIcon.FLAG,title="每天上午上课数量",content="学校每天上午的上课数量")
            self.morning_class_num.valueChanged.connect(lambda :self.on_class_num_changed("morning"))
            add_widget(self.morning_class_num,self.layout,0)
            self.afternoon_class_num=RangeSettingCard(cfg.afternoon_class_num,FluentIcon.FLAG,title="每天下午上课数量",content="学校每天下午的上课数量")
            self.afternoon_class_num.valueChanged.connect(lambda :self.on_class_num_changed("afternoon"))
            add_widget(self.afternoon_class_num,self.layout,0)

            self.lesson_time_card=PushSettingCard("设置",FluentIcon.DATE_TIME,"活动起止时间","设置每天各节课和其他活动的起止时间")
            self.lesson_time_card.clicked.connect(self.open_timeline_editor)
            add_widget(self.lesson_time_card,self.layout,0)

            # 课程与活动时间冲突的警告横幅（显示在“课程起止时间”卡片下方）
            self.time_banner=WarningBanner(self)
            add_widget(self.time_banner,self.layout)
            self.on_class_num_changed()

            add_widget(SeparatorWidget(orient=Qt.Horizontal),self.layout)

            # 生成规则设置区域
            biggersubheader("生成规则",self,self.layout)

            rule_list_layout=QHBoxLayout()
            self.layout.addLayout(rule_list_layout)

            self.add_rule_button=button("添加规则",self,rule_list_layout,0)
            self.add_rule_button.setIcon(FluentIcon.ADD)
            self.add_rule_button.setFixedWidth(200)
            self.add_rule_button.clicked.connect(self.add_rule)

            self.edit_rule_button=button("编辑规则",self,rule_list_layout,0)
            self.edit_rule_button.setEnabled(False)
            self.edit_rule_button.setIcon(FluentIcon.EDIT)
            self.edit_rule_button.setFixedWidth(200)
            self.edit_rule_button.clicked.connect(self.edit_rule)

            self.del_rule_button=button("删除规则",self,rule_list_layout)
            self.del_rule_button.setEnabled(False)
            self.del_rule_button.setIcon(FluentIcon.DELETE)
            self.del_rule_button.setFixedWidth(200)
            self.del_rule_button.clicked.connect(self.del_rule)
            rule_list_layout.addStretch(1)

            self.rule_list=RoundListWidget()
            self.rule_list.setFixedHeight(230)
            self.rule_list.setDragEnabled(True)
            self.rule_list.setDropIndicatorShown(True)
            self.rule_list.setDragDropMode(QAbstractItemView.InternalMove)
            self.rule_list.itemClicked.connect(self.enable_rule_button)
            self.rule_list.itemDoubleClicked.connect(self.edit_rule)
            self.rule_list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.rule_list.customContextMenuRequested.connect(self.show_rule_menu)
            self.rule_list.model().rowsMoved.connect(self.on_drag_rules)
            self.show_rules()
            add_widget(self.rule_list,self.layout)

            subheader("生成功能设置",self,self.layout)
            self.reduce_continue_card=SwitchSettingCard(FluentIcon.STOP_WATCH,"减少教师连堂","生成时尽可能避免教师连堂上课",cfg.reduce_continue)
            add_widget(self.reduce_continue_card,self.layout,0)
            self.average_subjects_card=SwitchSettingCard(FluentIcon.SPEED_MEDIUM,"平均分配课程","生成时尽量将学科平均分配到每一天（在不违背生成规则的前提下）",cfg.average_subjects)
            add_widget(self.average_subjects_card,self.layout,0)
            self.forbid_noon_continuous_card=SwitchSettingCard(FluentIcon.CALENDAR,"允许跨上下午连堂","允许将连堂课排在上午最后一节和下午第一节",cfg.allow_noon_continuous)
            add_widget(self.forbid_noon_continuous_card,self.layout,0)
            self.merge_lessons_group=PushSettingCard("设置",FluentIcon.BOOK_SHELF,"并课设置","设置哪些班级哪些学科要排在同一时间")
            self.merge_lessons_group.clicked.connect(self.merge_lessons)
            add_widget(self.merge_lessons_group,self.layout,0)
            self.max_tries_card=RangeSettingCard(cfg.max_tries,FluentIcon.CANCEL,"最大尝试次数","设置自动生成时同一时间最多尝试生成多少次，如果在尝试次数内无法生成出完全满足规则的课表，则会跳过该时间，并把剩余课程放在暂存区中")
            add_widget(self.max_tries_card,self.layout)

            add_widget(SeparatorWidget(orient=Qt.Horizontal),self.layout)

            # 表格样式设置区域
            biggersubheader("表格样式",self,self.layout)

            self.school_name_card=SettingCard(FluentIcon.INFO,"学校名称","设置学校名称（作为表头）")
            self.school_name=LineEdit()
            self.school_name.setText(cfg.school_name.value)
            add_widget(self.school_name,self.school_name_card.hBoxLayout)
            self.school_name.textChanged.connect(lambda :self.save_cfg("school_name",self.school_name.text()))
            add_widget(self.school_name_card,self.layout,0)

            # 设置是否显示教师姓名和表格排版方式
            show_teachers=SwitchSettingCard(configItem=cfg.show_teachers,icon=FluentIcon.TAG,title="显示教师姓名",content="在课程名称下方标注任课教师姓名")
            add_widget(show_teachers,self.layout,0)

            text_style=SettingCard(FluentIcon.FONT,"文字样式","设置课程表文字样式")
            self.font_combo=FontComboBox()
            self.font_combo.setCurrentText(cfg.text_font.value)
            self.font_combo.currentTextChanged.connect(lambda :self.save_cfg("text_font",self.font_combo.currentText()))
            add_widget(self.font_combo,text_style.hBoxLayout)

            self.text_size=SpinBox()
            self.text_size.setRange(1,100)
            self.text_size.setValue(cfg.text_size.value)
            self.text_size.valueChanged.connect(lambda :self.save_cfg("text_size",self.text_size.value()))
            add_widget(self.text_size,text_style.hBoxLayout)
            add_widget(text_style,self.layout)

            # 校验课程与活动时间，需要时显示警告横幅
            self.refresh_time_warnings()

            self.scroll_area.setWidget(view)
            main_layout.addWidget(self.scroll_area)
            logging.info("设置页面加载完成")
        except Exception as error:
            e=traceback.format_exc()
            logging.critical(f"加载设置页面出错：\n{e}")
            show_error(self,error)