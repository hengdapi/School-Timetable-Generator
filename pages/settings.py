# coding=utf-8
import shutil

from PySide6.QtCore import QTime
from core.rules import *
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
        name=self.rule_combo.currentData()[0].text
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
                if self.edit:
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

class GradeMsgbox(MessageBoxBase):
    def __init__(self,parent=None,edit=False,grade_name:str=""):
        super().__init__(parent)
        self.edit=edit
        self.grade_name=grade_name
        if self.edit:
            self.classes=cfg.grades_info.value[grade_name]
        subheader("添加年级" if not edit else "编辑年级",self,self.viewLayout)
        write("年级名称：",self,self.viewLayout,0)
        self.grade_name_input=LineEdit()
        self.grade_name_input.setPlaceholderText("X年级")
        if self.edit:
            self.grade_name_input.setText(grade_name)
        add_widget(self.grade_name_input,self.viewLayout)
        write("所含班级：",self,self.viewLayout,0)
        self.classes_combo=MultiSelectComboBox()
        left_classes=set(lesson_info.class_names)
        for classes in cfg.grades_info.value.values():
            left_classes-=set(classes)
        left_classes=list(left_classes)
        if self.edit:
            left_classes+=self.classes
        left_classes.sort(key=lambda clas:lesson_info.class_names.index(clas))
        self.classes_combo.addItems(left_classes)
        if self.edit:
            self.classes_combo.setSelectedIndices({left_classes.index(clas) for clas in self.classes})
        add_widget(self.classes_combo,self.viewLayout)
        self.yesButton.setText("添加年级")

    def validate(self) -> bool:
        curr_grade_name=self.grade_name_input.text()
        if not curr_grade_name:
            Toast.error("请输入年级名称","",parent=self,duration=2000)
            return False
        if not self.classes_combo.selectedItems():
            Toast.error("请选择所含班级","",parent=self,duration=2000)
            return False
        grade_names=list(cfg.grades_info.value.keys())
        if curr_grade_name!=self.grade_name and curr_grade_name in grade_names:
            Toast.error("请勿设置名称重复的年级",f"名称“{curr_grade_name}”重复",parent=self,duration=2000)
            return False
        return True

class TeacherMaxnumMsgbox(MessageBoxBase):
    def __init__(self, parent=None):
        super().__init__(parent)
        subheader("设置老师同时上课最大数量",self,self.viewLayout,10)
        self.teacher_combo=EditableComboBox()
        self.teacher_combo.addItems(lesson_info.teacher_names)
        self.teacher_combo.setCurrentIndex(-1)
        self.teacher_combo.setPlaceholderText("请选择老师")
        self.teacher_combo.setCompleter(QCompleter(lesson_info.teacher_names,self.teacher_combo))
        self.teacher_combo.currentTextChanged.connect(self.show_cards)
        add_widget(self.teacher_combo,self.viewLayout,0)

        self.max_num_cards:list[SettingCard]=[]
        self.max_nums=cfg.teachers_max_num.value

        self.yesButton.setText("保存设置")

    def show_cards(self):
        teacher_name=self.teacher_combo.currentText()
        if teacher_name not in lesson_info.teacher_names:
            return
        teacher=lesson_info.teachers[teacher_name]
        for card in self.max_num_cards:
            card.deleteLater()
        self.max_num_cards.clear()
        for subject in teacher.subjects:
            max_num_card=SettingCard("",f"{subject} 同时最大上课数量","")
            max_num_card.hBoxLayout.addSpacing(50)
            max_num_spinbox=SpinBox()
            max_num_spinbox.setRange(1,len(lesson_info.classes))
            max_num_spinbox.setValue(cfg.teachers_max_num.value[teacher_name][subject.name])
            max_num_spinbox.valueChanged.connect(lambda value,teacher=teacher_name,subject=subject.name:self.update_value(value,teacher,subject))
            add_widget(max_num_spinbox,max_num_card.hBoxLayout)
            add_widget(max_num_card,self.viewLayout,0)
            self.max_num_cards.append(max_num_card)

    def update_value(self,value,teacher_name,subject_name):
        self.max_nums[teacher_name][subject_name]=value

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
        self.show_lesson_time_group()
        # 新增课次的起止时间默认为空，需要重新校验并提示
        self.refresh_time_warnings()

    def set_teachers_max_num(self):
        msgbox=TeacherMaxnumMsgbox(self)
        if not msgbox.exec():
            return
        for teacher in lesson_info.teacher_lst:
            for subject in teacher.subjects:
                cfg.teachers_max_num.value[teacher.name][subject.name]=msgbox.max_nums[teacher.name][subject.name]
        save_settings()

    def show_lessons_info(self):
        lessons_info=pd.DataFrame(cfg.lessons_info.value)
        display_df_in_table(self.lessons_info_table,lessons_info)

    def download_template(self):
        filename,_=QFileDialog.getSaveFileName(
            self,
            "保存课程信息模板",
            "",
            "Excel文件 (*.xlsx *.xls)"
        )
        if not filename:
            return
        shutil.copy("template.xlsx",filename)
        os.startfile(filename)

    def pick_lessons_info(self):
        user_info_file,_=QFileDialog.getOpenFileName(
            self,
            "选择课程信息文件",
            "",
            "Excel文件 (*.xlsx *.xls)"
        )
        # 处理上传的课程信息文件或使用已有配置
        if not user_info_file:
            logging.debug("用户取消选择课程信息文件")
            if cfg.lessons_info.value!="":
                cfg.lessons_info.value=pd.DataFrame(cfg.lessons_info.value).to_json(orient="records", lines=False, force_ascii=False)
            return
        logging.info(f"选择课程信息文件: {user_info_file}")
        try:
            logging.debug("开始解析课程信息文件")
            user_info=pd.read_excel(user_info_file)
            old_classes=[]
            rename_dict={}
            for i in range(2,len(user_info.keys()),2):
                rename_dict[user_info.keys()[i]]=user_info.keys()[i-1]+" - 任课老师"
                rename_dict[user_info.keys()[i-1]]=user_info.keys()[i-1]+" - 课时"
            user_info=user_info.rename(columns=rename_dict)
            new_lessons_info=user_info.to_dict(orient="records")
            for class_ in new_lessons_info:
                old_classes.append(class_["班级"])
                for key,value in class_.items():
                    if pd.isna(value):
                        class_[key]=None

            new_subjects=[user_info.keys()[i][:-5] for i in range(1,len(user_info.keys()),2)]
            new_teachers=set()
            for subject in new_subjects:
                new_teachers|=set(user_info[subject+" - 任课老师"].to_list())
            new_teachers=[x for x in new_teachers if not pd.isna(x)]

            logging.debug(f"解析完成：{len(old_classes)}个班级，{len(new_subjects)}个科目，{len(new_teachers)}个老师")
            diff_classes,diff_teachers,diff_subjects=diff_cfg(old_classes,new_teachers,new_subjects)

            if diff_classes or diff_teachers or diff_subjects:
                logging.warning(f"检测到差异：{len(diff_classes)}个班级, {len(diff_teachers)}个老师, {len(diff_subjects)}个科目")

            dialog=MessageBox("确认要更新课程信息表吗？","以下班级在新课程信息表中不存在：\n"+"、".join(diff_classes)+"\n以下老师在新课程信息表中不存在：\n"+"、".join(diff_teachers)+"\n以下科目在新课程信息表中不存在：\n"+"、".join(diff_subjects)+"\n与以上信息相关的设置将被删除",self)
            if not dialog.exec():
                logging.info("用户取消更新课程信息")
                return

            cfg.lessons_info.value=new_lessons_info
            cfg.subjects_info.value=new_subjects
            cfg.teachers_info.value=new_teachers
            del_cfg_diff(diff_classes,diff_teachers,diff_subjects)
            save_settings()
            self.show_lessons_info()
            logging.info("课程信息表更新成功，准备重启应用")
            Toast.success("课程信息表更新成功，应用将自动重启","",parent=self,duration=1500)
            restart_app(1500)
        except Exception as error:
            e=traceback.format_exc()
            logging.error(f"解析课程信息文件时出错：\n{e}")
            show_error(self,error)

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
            self.rule_list.addItem(str(rule))
            # 获取刚添加的项并设置userData
            item=self.rule_list.item(self.rule_list.count()-1)
            item.setData(Qt.UserRole,rule)

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

    def lesson_time_changed(self,lesson:int,end:bool,time:QTime):
        cfg.lessons_time.value[str(lesson)][end]=[time.hour(),time.minute()]
        save_settings()
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

        返回 (课程警告,活动警告)，分别对应显示在“课程起止时间”与“活动信息”位置。
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

        校验不通过时只在对应位置弹出 warning 横幅提示，不阻止用户保存配置；
        全部合法时隐藏横幅，并自动按时间顺序排列活动。
        """
        # 页面尚未构建完对应区域时直接跳过
        if self.lesson_banner is None or self.activity_banner is None:
            return
        lesson_messages,activity_messages=self.check_time_valid()
        if lesson_messages:
            self.lesson_banner.show_warning("课程时间设置有冲突",lesson_messages)
        else:
            self.lesson_banner.hide_warning()
        if activity_messages:
            self.activity_banner.show_warning("活动时间设置有冲突",activity_messages)
        else:
            self.activity_banner.hide_warning()
        if not lesson_messages and not activity_messages:
            self.sort_activities()

    def sort_activities(self):
        """时间全部合法时，按开始时间（相同则按结束时间）为活动排序并刷新表格"""
        activities=sorted(
            cfg.activity_info.value.items(),
            key=lambda item:(item[1][0][0]*60+item[1][0][1],item[1][1][0]*60+item[1][1][1])
        )
        if [name for name,_ in activities]==list(cfg.activity_info.value.keys()):
            return
        cfg.activity_info.value=dict(activities)
        save_settings()
        self.show_activities()
        logging.info("活动已按时间顺序重新排序")

    def show_lesson_time_group(self):
        group_idx=self.layout.indexOf(self.lesson_length_group)
        self.lesson_length_group.hide()
        self.lesson_length_group.deleteLater()
        status=self.lesson_length_group.isExpand
        self.lesson_length_group=ExpandGroupSettingCard(FluentIcon.STOP_WATCH,"课程起止时间","显示在对应课时下方")
        for lesson in range(1,cfg.day_class_num+1):
            curr_time=Time(1,lesson)
            lesson_length_card=SettingCard("",curr_time.to_str(False,True))
            start_time=TimePicker()
            start_time.setTime(QTime(cfg.lessons_time.value[str(lesson)][0][0],cfg.lessons_time.value[str(lesson)][0][1]))
            start_time.timeChanged.connect(lambda time,l=lesson: self.lesson_time_changed(l,False,time))
            lesson_length_card.hBoxLayout.addWidget(start_time)
            lesson_length_card.hBoxLayout.addWidget(QLabel("  ~  "))
            end_time=TimePicker()
            end_time.setTime(QTime(cfg.lessons_time.value[str(lesson)][1][0],cfg.lessons_time.value[str(lesson)][1][1]))
            end_time.timeChanged.connect(lambda time,l=lesson: self.lesson_time_changed(l,True,time))
            lesson_length_card.hBoxLayout.addWidget(end_time)
            lesson_length_card.hBoxLayout.addSpacing(20)
            self.lesson_length_group.addGroupWidget(lesson_length_card)
        self.layout.insertWidget(group_idx,self.lesson_length_group)
        self.lesson_length_group.setExpand(status)

    def show_activities(self):
        self.save_activity_lock=True
        self.activity_table.setRowCount(len(cfg.activity_info.value))
        self.activity_table.setFixedHeight(min(300,len(cfg.activity_info.value)*50+50))
        r=0
        for activity,(start_time,end_time) in cfg.activity_info.value.items():
            item=QTableWidgetItem(activity)
            item.setTextAlignment(Qt.AlignCenter)
            self.activity_table.setItem(r,0,item)
            start_timePicker=TimePicker()
            start_timePicker.setTime(QTime(start_time[0],start_time[1]))
            start_timePicker.timeChanged.connect(self.save_activity)
            self.activity_table.setCellWidget(r,1,start_timePicker)
            end_timePicker=TimePicker()
            end_timePicker.setTime(QTime(end_time[0],end_time[1]))
            end_timePicker.timeChanged.connect(self.save_activity)
            self.activity_table.setCellWidget(r,2,end_timePicker)
            r+=1
        self.del_activity_button.setEnabled(bool(self.activity_table.selectedItems()))
        self.save_activity_lock=False

    def add_activity(self):
        cfg.activity_info.value[f"新活动{len(cfg.activity_info.value)+1}"]=[[0,0],[0,0]]
        save_settings()
        self.show_activities()
        self.refresh_time_warnings()

    def del_activity(self):
        cfg.activity_info.value.pop(self.activity_table.item(self.activity_table.currentRow(),0).text())
        save_settings()
        self.show_activities()
        self.refresh_time_warnings()

    def save_activity(self):
        if self.save_activity_lock:
            return
        # 直接操作时间选择器时可能没有任何选中行，此处需要容错
        current_row=self.activity_table.currentRow()
        current_item=self.activity_table.item(current_row,0)
        activity_info={}
        if current_item is not None:
            names=[self.activity_table.item(r,0).text() for r in range(self.activity_table.rowCount())]
            if names.count(current_item.text())>1:
                Toast.error("请勿设置名称重复的活动",f"名称“{current_item.text()}”重复",parent=self,duration=2000)
                self.save_activity_lock=True
                current_item.setText(list(cfg.activity_info.value.keys())[current_row])
                self.save_activity_lock=False
        for r in range(self.activity_table.rowCount()):
            activity_info[self.activity_table.item(r,0).text()]=[
                [self.activity_table.cellWidget(r,1).time.hour(),self.activity_table.cellWidget(r,1).time.minute()],
                [self.activity_table.cellWidget(r,2).time.hour(),self.activity_table.cellWidget(r,2).time.minute()]
            ]
        cfg.activity_info.value=activity_info
        save_settings()
        self.refresh_time_warnings()

    def refresh_grade_button(self):
        idx=list(cfg.grades_info.value.keys()).index(self.grade_table.item(self.grade_table.currentRow(),0).text())
        self.edit_grade_button.setEnabled(bool(self.grade_table.selectedItems()))
        self.del_grade_button.setEnabled(bool(self.grade_table.selectedItems()))
        self.grade_up_button.setEnabled(bool(self.grade_table.selectedItems()) and idx!=0)
        self.grade_down_button.setEnabled(bool(self.grade_table.selectedItems()) and idx!=len(cfg.grades_info.value)-1)

    def show_grades(self):
        self.grade_table.setRowCount(len(cfg.grades_info.value))
        self.grade_table.setFixedHeight(min(400,len(cfg.grades_info.value)*50+50))
        r=0
        for grade,classes in cfg.grades_info.value.items():
            name_item=QTableWidgetItem(grade)
            name_item.setTextAlignment(Qt.AlignCenter)
            self.grade_table.setItem(r,0,name_item)
            class_item=QTableWidgetItem(", ".join(classes))
            class_item.setTextAlignment(Qt.AlignCenter)
            self.grade_table.setItem(r,1,class_item)
            r+=1

    def add_grade(self):
        add_grade_msgbox=GradeMsgbox(self)
        if not add_grade_msgbox.exec():
            return
        cfg.grades_info.value[add_grade_msgbox.grade_name_input.text()]=[item.text for item in add_grade_msgbox.classes_combo.selectedItems()]
        save_settings()
        self.show_grades()

    def edit_grade(self):
        edit_grade_msgbox=GradeMsgbox(self,True,self.grade_table.item(self.grade_table.currentRow(),0).text())
        if not edit_grade_msgbox.exec():
            return
        new_grade_info={}
        for grade in cfg.grades_info.value:
            if grade==self.grade_table.item(self.grade_table.currentRow(),0).text():
                new_grade_info[edit_grade_msgbox.grade_name_input.text()]=[item.text for item in edit_grade_msgbox.classes_combo.selectedItems()]
            else:
                new_grade_info[grade]=cfg.grades_info.value[grade]
        cfg.grades_info.value=new_grade_info
        save_settings()
        self.show_grades()
        self.refresh_grade_button()

    def del_grade(self):
        cfg.grades_info.value.pop(self.grade_table.item(self.grade_table.currentRow(),0).text())
        save_settings()
        self.show_grades()
        self.refresh_grade_button()

    def change_grade_pos(self,drct:str):
        new_grade_info={}
        new_keys=list(cfg.grades_info.value.keys())
        idx=new_keys.index(self.grade_table.item(self.grade_table.currentRow(),0).text())
        if drct=="up":
            new_keys[idx-1],new_keys[idx]=new_keys[idx],new_keys[idx-1]
            self.grade_table.setCurrentIndex(self.grade_table.model().index(idx-1,0))
        else:
            new_keys[idx+1],new_keys[idx]=new_keys[idx],new_keys[idx+1]
            self.grade_table.setCurrentIndex(self.grade_table.model().index(idx+1,0))
        for grade in new_keys:
            new_grade_info[grade]=cfg.grades_info.value[grade]
        cfg.grades_info.value=new_grade_info
        save_settings()
        self.show_grades()
        self.refresh_grade_button()

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
            # 时间合法性警告横幅，在构建对应区域时创建
            self.lesson_banner=None
            self.activity_banner=None
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
            # 课程信息设置区域
            biggersubheader("课程信息",self,self.layout)

            # 上传课程信息文件
            self.user_info_card=SettingCard(icon=FluentIcon.INFO,title="课程信息文件",content="存储任课老师及课时、班级信息的表格")
            add_widget(self.user_info_card,self.layout)
            self.download_template_button=button("下载导入模板",self,self.user_info_card.layout())
            self.download_template_button.setFixedSize(150,35)
            self.download_template_button.setIcon(FluentIcon.DOWNLOAD)
            self.download_template_button.clicked.connect(self.download_template)

            self.user_info_file=button("选择文件",self,self.user_info_card.layout())
            self.user_info_file.setFixedSize(130,35)
            self.user_info_file.setIcon(FluentIcon.FOLDER)
            self.user_info_file.clicked.connect(self.pick_lessons_info)

            self.lessons_info_table=LineTableWidget()
            self.show_lessons_info()
            self.lessons_info_table.setFixedHeight(300)
            self.lessons_info_table.setEditTriggers(TableWidget.NoEditTriggers)
            add_widget(self.lessons_info_table,self.layout)

            # 设置每天上午和下午的课程数量
            self.morning_class_num=RangeSettingCard(cfg.morning_class_num,FluentIcon.FLAG,title="每天上午上课数量",content="学校每天上午的上课数量")
            self.morning_class_num.valueChanged.connect(lambda :self.on_class_num_changed("morning"))
            add_widget(self.morning_class_num,self.layout,0)
            self.afternoon_class_num=RangeSettingCard(cfg.afternoon_class_num,FluentIcon.FLAG,title="每天下午上课数量",content="学校每天下午的上课数量")
            self.afternoon_class_num.valueChanged.connect(lambda :self.on_class_num_changed("afternoon"))
            add_widget(self.afternoon_class_num,self.layout,0)

            self.lesson_length_group=ExpandGroupSettingCard(FluentIcon.DATE_TIME,"课程起止时间（显示在课时下方）")
            add_widget(self.lesson_length_group,self.layout,0)
            self.on_class_num_changed()

            # 课程时间设置的警告横幅（紧跟在课程起止时间分组下方）
            self.lesson_banner=WarningBanner(self)
            self.layout.insertWidget(self.layout.indexOf(self.lesson_length_group)+1,self.lesson_banner)

            subheader("年级信息",self,self.layout)

            grade_operations_layout=QHBoxLayout()
            self.layout.addLayout(grade_operations_layout)

            self.add_grade_button=button("添加年级",self,grade_operations_layout,0)
            self.add_grade_button.setIcon(FluentIcon.ADD)
            self.add_grade_button.setFixedWidth(200)
            self.add_grade_button.clicked.connect(self.add_grade)

            self.edit_grade_button=button("编辑年级",self,grade_operations_layout,0)
            self.edit_grade_button.setIcon(FluentIcon.EDIT)
            self.edit_grade_button.setFixedWidth(200)
            self.edit_grade_button.setEnabled(False)
            self.edit_grade_button.clicked.connect(self.edit_grade)

            self.del_grade_button=button("删除年级",self,grade_operations_layout,50)
            self.del_grade_button.setIcon(FluentIcon.DELETE)
            self.del_grade_button.setFixedWidth(200)
            self.del_grade_button.setEnabled(False)
            self.del_grade_button.clicked.connect(self.del_grade)

            self.grade_up_button=TransparentToolButton()
            self.grade_up_button.setIcon(FluentIcon.UP)
            self.grade_up_button.setToolTip("上移")
            self.grade_up_button.setEnabled(False)
            self.grade_up_button.clicked.connect(lambda :self.change_grade_pos("up"))
            add_widget(self.grade_up_button,grade_operations_layout)

            self.grade_down_button=TransparentToolButton()
            self.grade_down_button.setIcon(FluentIcon.DOWN)
            self.grade_down_button.setToolTip("下移")
            self.grade_down_button.setEnabled(False)
            self.grade_down_button.clicked.connect(lambda :self.change_grade_pos("down"))
            add_widget(self.grade_down_button,grade_operations_layout)

            self.grade_table=LineTableWidget()
            self.grade_table.setColumnCount(2)
            self.grade_table.setHorizontalHeaderLabels(["年级名称","所含班级"])
            self.grade_table.setColumnWidth(1,1000)
            self.grade_table.verticalHeader().hide()
            self.grade_table.setEditTriggers(TableWidget.NoEditTriggers)
            self.grade_table.clicked.connect(self.refresh_grade_button)
            self.show_grades()
            add_widget(self.grade_table,self.layout)

            grade_operations_layout.addStretch(1)
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
            self.teachers_max_num_group=PushSettingCard("设置数量",FluentIcon.BOOK_SHELF,"老师同时最大上课数量","设置同一时间每个老师各个学科可以同时上课最大的数量（即最多允许该老师同时上几个班级该学科的课）")
            add_widget(self.teachers_max_num_group,self.layout,0)
            self.max_tries_card=RangeSettingCard(cfg.max_tries,FluentIcon.CANCEL,"最大尝试次数","设置自动生成时同一时间最多尝试生成多少次，如果在尝试次数内无法生成出完全满足规则的课表，则会跳过该时间，并把剩余课程放在暂存区中")
            add_widget(self.max_tries_card,self.layout)
            self.teachers_max_num_group.clicked.connect(self.set_teachers_max_num)

            add_widget(SeparatorWidget(orient=Qt.Horizontal),self.layout)

            biggersubheader("活动信息",self,self.layout)

            self.activity_operation_layout=QHBoxLayout()
            self.layout.addLayout(self.activity_operation_layout)

            self.add_activity_button=button("添加活动",self,self.activity_operation_layout,0)
            self.add_activity_button.setIcon(FluentIcon.ADD)
            self.add_activity_button.clicked.connect(self.add_activity)
            self.add_activity_button.setFixedWidth(200)
            self.del_activity_button=button("删除活动",self,self.activity_operation_layout)
            self.del_activity_button.setIcon(FluentIcon.DELETE)
            self.del_activity_button.setFixedWidth(200)
            self.del_activity_button.setEnabled(False)
            self.del_activity_button.clicked.connect(self.del_activity)
            self.activity_operation_layout.addStretch(1)

            self.save_activity_lock=False
            self.activity_table=LineTableWidget()
            self.activity_table.setColumnCount(3)
            self.activity_table.setHorizontalHeaderLabels(["活动名称","开始时间","结束时间"])
            for c in range(3):
                self.activity_table.setColumnWidth(c,300)
            self.activity_table.verticalHeader().hide()
            self.show_activities()
            self.activity_table.cellChanged.connect(self.save_activity)
            self.activity_table.clicked.connect(lambda :self.del_activity_button.setEnabled(True))
            add_widget(self.activity_table,self.layout)

            # 活动时间设置的警告横幅（显示在活动表格下方）
            self.activity_banner=WarningBanner(self)
            self.layout.insertWidget(self.layout.indexOf(self.activity_table)+1,self.activity_banner)

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