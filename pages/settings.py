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

def merge_key(merged_lesson)->tuple:
    """统一成 (学科, 班级元组)，避免元组 / 列表两种存法比较不上"""
    return merged_lesson[0],tuple(merged_lesson[1])


class MergeLessonsMsgbox(MessageBoxBase):
    """添加 / 编辑一组并课：班级可多选，学科单选"""

    def __init__(self,parent=None,edit=False,merged_lesson:tuple=None):
        super().__init__(parent)
        self.origin_merged=merged_lesson
        self.new_merged=None
        subheader("编辑并课" if edit else "添加并课",self,self.viewLayout)

        self.form_layout=QGridLayout()
        self.form_layout.setColumnStretch(1,1)
        self.form_layout.addWidget(write("并课班级：",self,QVBoxLayout()),0,0)
        self.class_combo=ClassMultiSelectionCombobox()
        self.class_combo.setMinimumWidth(400)
        self.form_layout.addWidget(self.class_combo,0,1)
        self.form_layout.addWidget(write("并课学科：",self,QVBoxLayout()),1,0)
        self.subject_combo=ComboBox()
        self.subject_combo.setMinimumWidth(400)
        self.subject_combo.addItems(lesson_info.subject_names)
        self.form_layout.addWidget(self.subject_combo,1,1)
        self.viewLayout.addLayout(self.form_layout)

        if merged_lesson:
            self.subject_combo.setCurrentText(merged_lesson[0])
            self.class_combo.setCheckedTexts(merged_lesson[1])

        self.yesButton.setText("编辑并课" if edit else "添加并课")
        self.cancelButton.setText("取消")

    def check(self):
        classes=self.class_combo.checkedTexts()
        subject=self.subject_combo.currentText()
        if len(classes)<2:
            Toast.error("请选择至少2个并课班级","",parent=self,duration=2000)
            return False
        if not subject:
            Toast.error("请选择并课学科","",parent=self,duration=2000)
            return False
        new_key=(subject,tuple(classes))
        origin_key=merge_key(self.origin_merged) if self.origin_merged else None
        for merged_lesson in cfg.merged_lessons.value:
            key=merge_key(merged_lesson)
            if key==origin_key:
                continue
            if key==new_key:
                Toast.error("该组并课设置已存在","",parent=self,duration=2000)
                return False
            if key[0]==subject and set(key[1])&set(classes):
                Toast.error("并课设置冲突",f"与并课设置“{", ".join(merged_lesson[1])} 的 {merged_lesson[0]} 学科并课”冲突",parent=self,duration=-1)
                return False
        self.new_merged=(subject,classes)
        return True

    def validate(self) -> bool:
        return self.check()


class Settings(PagedPage):
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

    # ------------------------------------------------------------------
    # 并课设置
    # ------------------------------------------------------------------
    def refresh_merge_list(self):
        self.merge_list.clear()
        for merged_lesson in cfg.merged_lessons.value:
            item=QListWidgetItem(f"{", ".join(merged_lesson[1])} 的 {merged_lesson[0]} 学科并课")
            item.setData(Qt.UserRole,merged_lesson)
            self.merge_list.addItem(item)
        self.enable_merge_button()

    def enable_merge_button(self):
        selected=bool(self.merge_list.selectedItems())
        self.edit_merge_button.setEnabled(selected)
        self.del_merge_button.setEnabled(selected)

    def save_merged_lessons(self):
        save_settings()
        # 只重建并课信息：重新解析整个课程信息会换掉所有班级对象，
        # 界面缓存的班级、已生成的课表、各规则引用的班级就全对不上了
        lesson_info.parse_merged_lessons()
        self.refresh_merge_list()

    def add_merge(self):
        logging.info("用户点击添加并课按钮")
        dialog=MergeLessonsMsgbox(self)
        if dialog.exec():
            cfg.merged_lessons.value.append(dialog.new_merged)
            self.save_merged_lessons()
            logging.info("成功添加并课")
        else:
            logging.debug("用户取消添加并课")

    def edit_merge(self):
        if not self.merge_list.selectedItems():
            return
        logging.info("用户编辑并课")
        selected_item=self.merge_list.selectedItems()[0]
        old_merged=selected_item.data(Qt.UserRole)
        dialog=MergeLessonsMsgbox(self,True,old_merged)
        if not dialog.exec():
            logging.debug("用户取消编辑并课")
            return
        index=self.merge_list.row(selected_item)
        old_key=merge_key(old_merged)
        for i,merged_lesson in enumerate(cfg.merged_lessons.value):
            if merge_key(merged_lesson)==old_key:
                cfg.merged_lessons.value[i]=dialog.new_merged
                break
        self.save_merged_lessons()
        # 刷新后行号重新映射，按原位置重新选中，保持编辑焦点
        if 0<=index<self.merge_list.count():
            self.merge_list.setCurrentRow(index)
        logging.info("并课编辑成功")

    def del_merge(self):
        if not self.merge_list.selectedItems():
            return
        logging.info("用户删除并课")
        target_key=merge_key(self.merge_list.selectedItems()[0].data(Qt.UserRole))
        for i,merged_lesson in enumerate(cfg.merged_lessons.value):
            if merge_key(merged_lesson)==target_key:
                del cfg.merged_lessons.value[i]
                break
        self.save_merged_lessons()
        logging.info("并课删除成功")

    def show_merge_menu(self,pos):
        """并课列表右键菜单：编辑、删除"""
        show_item_menu(
            self.merge_list,pos,self,
            edit_text="编辑",edit_slot=self.edit_merge,delete_slot=self.del_merge,
            on_selected=self.enable_merge_button
        )

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
        show_item_menu(
            self.rule_list,pos,self,
            edit_text="编辑",edit_slot=self.edit_rule,delete_slot=self.del_rule,
            on_selected=self.enable_rule_button
        )

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
            # 顶部导航、堆叠分页与 add_page / switch_page / create_page 都在基类里
            super().__init__(parent=parent,objectName="Settings")
            logging.info("开始加载设置页面")
            # 课程/活动时间合法性警告横幅，在“上课时间”分页中创建
            self.time_banner=None

            self.add_page("time",FluentIcon.DATE_TIME,"课程数量",self.build_time_page())
            self.add_page("timeline",FluentIcon.CALENDAR,"活动时间",self.build_timeline_page())
            self.add_page("rule",FluentIcon.EDUCATION,"排课规则",self.build_rule_page())
            self.add_page("merge",FluentIcon.BOOK_SHELF,"并课设置",self.build_merge_page())
            self.add_page("feature",FluentIcon.DEVELOPER_TOOLS,"功能设置",self.build_feature_page())
            self.add_page("style",FluentIcon.FONT,"表格样式",self.build_style_page())
            self.add_page("io",FluentIcon.SHARE,"导出/导入",self.build_io_page())

            self.switch_page("time")
            # 校验课程与活动时间，需要时显示警告横幅
            self.refresh_time_warnings()
            logging.info("设置页面加载完成")
        except Exception as error:
            log_page_error(self,error,"设置页面")

    # ------------------------------------------------------------------
    # 各分页内容
    # ------------------------------------------------------------------
    def build_time_page(self)->QWidget:
        page,layout=self.create_page("课程数量","设置每天上午、下午的课程数量；各节课与活动的起止时间在“活动时间”页调整。")

        # 设置每天上午和下午的课程数量
        self.morning_class_num=RangeSettingCard(cfg.morning_class_num,FluentIcon.FLAG,title="每天上午上课数量",content="学校每天上午的上课数量")
        self.morning_class_num.valueChanged.connect(lambda :self.on_class_num_changed("morning"))
        add_widget(self.morning_class_num,layout,0)
        self.afternoon_class_num=RangeSettingCard(cfg.afternoon_class_num,FluentIcon.FLAG,title="每天下午上课数量",content="学校每天下午的上课数量")
        self.afternoon_class_num.valueChanged.connect(lambda :self.on_class_num_changed("afternoon"))
        add_widget(self.afternoon_class_num,layout,0)

        # 课程与活动时间冲突的警告横幅
        self.time_banner=WarningBanner(page)
        add_widget(self.time_banner,layout)
        self.on_class_num_changed()

        layout.addStretch(1)
        return page

    def build_timeline_page(self)->QWidget:
        page,layout=self.create_page("活动时间","拖动时间块可调整课程与活动的起止时间，双击时间块可精确编辑。")
        self.timeline_editor=TimelineEditor(page)
        # 时间被修改后同步刷新“上课时间”页的时间冲突提示
        self.timeline_editor.dataChanged.connect(self.refresh_time_warnings)
        layout.addWidget(self.timeline_editor,1)
        return page

    def build_rule_page(self)->QWidget:
        page,layout=self.create_page("排课规则","规则按列表顺序参与生成，越靠前的规则越先生效，可拖动调整先后。")

        rule_list_layout=QHBoxLayout()
        layout.addLayout(rule_list_layout)

        self.add_rule_button=button("添加规则",page,rule_list_layout,0)
        self.add_rule_button.setIcon(FluentIcon.ADD)
        self.add_rule_button.setFixedWidth(200)
        self.add_rule_button.clicked.connect(self.add_rule)

        self.edit_rule_button=button("编辑规则",page,rule_list_layout,0)
        self.edit_rule_button.setEnabled(False)
        self.edit_rule_button.setIcon(FluentIcon.EDIT)
        self.edit_rule_button.setFixedWidth(200)
        self.edit_rule_button.clicked.connect(self.edit_rule)

        self.del_rule_button=button("删除规则",page,rule_list_layout)
        self.del_rule_button.setEnabled(False)
        self.del_rule_button.setIcon(FluentIcon.DELETE)
        self.del_rule_button.setFixedWidth(200)
        self.del_rule_button.clicked.connect(self.del_rule)
        rule_list_layout.addStretch(1)

        self.rule_list=RoundListWidget()
        self.rule_list.setDragEnabled(True)
        self.rule_list.setDropIndicatorShown(True)
        self.rule_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.rule_list.itemClicked.connect(self.enable_rule_button)
        self.rule_list.itemDoubleClicked.connect(self.edit_rule)
        self.rule_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rule_list.customContextMenuRequested.connect(self.show_rule_menu)
        self.rule_list.model().rowsMoved.connect(self.on_drag_rules)
        self.show_rules()
        add_widget(self.rule_list,layout)

        return page

    def build_merge_page(self)->QWidget:
        page,layout=self.create_page("并课设置","并课的班级会在同一时间上同学科的课程，适合两个班一起上课；调课时并课班级的课程会一起调整。")

        merge_operations_layout=QHBoxLayout()
        layout.addLayout(merge_operations_layout)

        self.add_merge_button=button("添加并课",page,merge_operations_layout,0)
        self.add_merge_button.setIcon(FluentIcon.ADD)
        self.add_merge_button.setFixedWidth(200)
        self.add_merge_button.clicked.connect(self.add_merge)

        self.edit_merge_button=button("编辑并课",page,merge_operations_layout,0)
        self.edit_merge_button.setIcon(FluentIcon.EDIT)
        self.edit_merge_button.setFixedWidth(200)
        self.edit_merge_button.setEnabled(False)
        self.edit_merge_button.clicked.connect(self.edit_merge)

        self.del_merge_button=button("删除并课",page,merge_operations_layout)
        self.del_merge_button.setIcon(FluentIcon.DELETE)
        self.del_merge_button.setFixedWidth(200)
        self.del_merge_button.setEnabled(False)
        self.del_merge_button.clicked.connect(self.del_merge)
        merge_operations_layout.addStretch(1)

        self.merge_list=RoundListWidget()
        self.merge_list.itemClicked.connect(self.enable_merge_button)
        self.merge_list.itemDoubleClicked.connect(self.edit_merge)
        self.merge_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.merge_list.customContextMenuRequested.connect(self.show_merge_menu)
        self.refresh_merge_list()
        add_widget(self.merge_list,layout)

        return page

    def build_feature_page(self)->QWidget:
        page,layout=self.create_page("功能设置","")

        self.reduce_continue_card=SwitchSettingCard(FluentIcon.STOP_WATCH,"减少教师连堂","生成时尽可能避免教师连堂上课",cfg.reduce_continue)
        add_widget(self.reduce_continue_card,layout,0)
        self.average_subjects_card=SwitchSettingCard(FluentIcon.SPEED_MEDIUM,"平均分配课程","生成时尽量将学科平均分配到每一天（在不违背生成规则的前提下）",cfg.average_subjects)
        add_widget(self.average_subjects_card,layout,0)
        self.forbid_noon_continuous_card=SwitchSettingCard(FluentIcon.CALENDAR,"允许跨上下午连堂","允许将连堂课排在上午最后一节和下午第一节",cfg.allow_noon_continuous)
        add_widget(self.forbid_noon_continuous_card,layout,0)
        self.max_tries_card=RangeSettingCard(cfg.max_tries,FluentIcon.CANCEL,"最大尝试次数","设置自动生成时同一时间最多尝试生成多少次，如果在尝试次数内无法生成出完全满足规则的课表，则会跳过该时间，并把剩余课程放在暂存区中")
        add_widget(self.max_tries_card,layout)

        layout.addStretch(1)
        return page

    def build_style_page(self)->QWidget:
        page,layout=self.create_page("表格样式","设置课程表的表头文字与文字样式。")

        self.school_name_card=SettingCard(FluentIcon.INFO,"学校名称","设置学校名称（作为表头）")
        self.school_name=LineEdit()
        self.school_name.setText(cfg.school_name.value)
        add_widget(self.school_name,self.school_name_card.hBoxLayout)
        self.school_name.textChanged.connect(lambda :self.save_cfg("school_name",self.school_name.text()))
        add_widget(self.school_name_card,layout,0)

        # 设置是否显示教师姓名和表格排版方式
        show_teachers=SwitchSettingCard(configItem=cfg.show_teachers,icon=FluentIcon.TAG,title="显示教师姓名",content="在课程名称下方标注任课教师姓名")
        add_widget(show_teachers,layout,0)

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
        add_widget(text_style,layout)

        layout.addStretch(1)
        return page

    def build_io_page(self)->QWidget:
        page,layout=self.create_page("导出/导入","把本机的排课设置备份到别处，或从备份文件恢复。")

        settingio_layout=QHBoxLayout()
        self.export_setting_button=button("导出设置",page,settingio_layout)
        self.export_setting_button.setFixedSize(130,40)
        self.export_setting_button.setIcon(FluentIcon.SHARE)
        self.export_setting_button.clicked.connect(self.export_settings)

        self.import_setting_button=button("导入设置",page,settingio_layout)
        self.import_setting_button.setFixedSize(130,40)
        self.import_setting_button.setIcon(FluentIcon.DOWNLOAD)
        self.import_setting_button.clicked.connect(self.import_settings)
        settingio_layout.addStretch(1)
        layout.addLayout(settingio_layout)
        layout.addSpacing(10)

        self.io_card=CardWidget(page)
        io_layout=QVBoxLayout(self.io_card)
        io_layout.setContentsMargins(20,16,20,16)
        subheader("设置文件包含什么",self.io_card,io_layout,10)
        write("settings.json 里保存着课程信息（班级、学科、任课老师）、年级、排课规则、功能开关与表格样式。",self.io_card,io_layout,0)
        add_widget(self.io_card,layout)

        layout.addStretch(1)
        return page