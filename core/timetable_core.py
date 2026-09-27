"""课程表编辑的后端逻辑：撤销/重做历史、调课检查、课程表方案存取

本模块只处理数据，不创建任何界面组件；界面层（pages/generate.py）负责渲染与交互。
"""

from core.generate_core import check,check_exchange
from core.rules import *


# ==================== 调课检查 ====================
def check_placement(clas:Class,source_subjects:list[Subject],source_time:Time|None=None,exchange:bool=True):
    """遍历整个课表，检查源课程能否放到（或交换到）每个位置

    :param clas: 当前预览的班级
    :param source_subjects: 源位置上的课程（1 节或单双周 2 节）
    :param source_time: 源位置；exchange 为 True 时必填
    :param exchange: True 为交换课程，False 为把课程放到某个位置（如从暂存区拖入）
    :return: (check_result, failed_reasons, conflict_lessons)
             check_result[位置]=能否放置；failed_reasons[位置]=不能放置的原因；conflict_lessons[位置]=冲突的课程
    """
    check_result:dict[Time,bool]={}
    failed_reasons:dict[Time,set[str]]={}
    conflict_lessons:dict[Time,set[tuple[Class,Time]]]={}
    for day in range(1,6):
        for lesson in range(1,cfg.day_class_num+1):
            target_time=Time(day,lesson)
            target_subjects=clas.get_lessons(target_time)
            can_place=False
            reasons=set()
            conflicts=set()
            if exchange and source_time:
                # 交换模式：目标不能是自身，且要通过 check_exchange
                if target_time!=source_time:
                    if target_subjects and check_exchange(clas,source_time,target_time,reasons,conflicts):
                        can_place=True
                    # 目标是空位：直接检查能否放置
                    elif not target_subjects:
                        if len(source_subjects)==1:
                            can_place=check(clas,target_time,source_subjects[0],reasons,conflicts,True)
                        elif len(source_subjects)==2:
                            check1=check(clas,target_time.sin_week,source_subjects[0],reasons,conflicts,True)
                            check2=check(clas,target_time.dou_week,source_subjects[1],reasons,conflicts,True)
                            can_place=check1 and check2
            else:
                # 添加模式（如从暂存区拖来）
                if target_subjects:
                    if len(target_subjects)==1 and target_subjects[0] in clas.half_subjects and source_subjects[0] in clas.half_subjects:
                        can_place=check(clas,target_time.dou_week,source_subjects[0],reasons,conflicts,True)
                    else:
                        # 已有课程：只检查新课程能否放这里（原课程会被移入暂存区）
                        can_place=check(clas,target_time,source_subjects[0],reasons,conflicts,True)
                elif source_subjects[0] in clas.half_subjects:
                    can_place=check(clas,target_time.sin_week,source_subjects[0],reasons,conflicts,True)
                else:
                    can_place=check(clas,target_time,source_subjects[0],reasons,conflicts,True)
            if target_subjects==source_subjects:  # 相同学科无需调整
                can_place=False
            check_result[target_time]=can_place
            failed_reasons[target_time]=reasons
            conflict_lessons[target_time]=conflicts
    return check_result,failed_reasons,conflict_lessons


# ==================== 撤销 / 重做 ====================
def diff_timetables(state1:dict,state2:dict)->dict[str,set[Time]]:
    """对比两份课表快照，返回每个班级中发生变化的位置"""
    changed={}
    for class_name,timetable in state1.items():
        other=state2.get(class_name,{})
        times=set()
        for time_str in set(timetable)|set(other):
            if timetable.get(time_str)!=other.get(time_str):
                times.add(Time(string=time_str).all_week)
        changed[class_name]=times
    return changed

def restore_timetables(snapshot:tuple,changed:dict[str,set[Time]]|None=None):
    """把课表恢复到某个快照；changed 不为 None 时只重新排发生变化的班级"""
    timetables,extra=snapshot
    changed_classes=[class_name for class_name in timetables if changed is None or changed.get(class_name)]
    for class_name in changed_classes:  # 先清空，再按快照重新排课
        clas=lesson_info.classes.get(class_name)
        if clas is not None:
            clas.reset()
    for class_name in changed_classes:
        clas=lesson_info.classes.get(class_name)
        if clas is None:
            continue
        for time_str,subject_names in timetables[class_name].items():
            if not subject_names:
                continue
            subjects=[lesson_info.subjects.get(name) for name in subject_names]
            if not all(subjects):
                continue
            curr_time=Time(string=time_str)
            if len(subjects)==1:
                clas.add_lesson(curr_time,subjects[0])
            else:  # 单双周两节课
                clas.add_lesson(curr_time.sin_week,subjects[0])
                clas.add_lesson(curr_time.dou_week,subjects[1])
    if "saved" in extra:
        lesson_info.saved=extra["saved"]

class TimetableHistory:
    """课表修改历史（撤销/重做），只保存与恢复数据，不触碰界面"""

    def __init__(self,limit:int=50):
        self.undo_stack:list[tuple]=[]  # 撤销栈：每次修改课表前的快照
        self.redo_stack:list[tuple]=[]  # 重做栈：被撤销的快照
        self.limit=limit  # 最多记录的步数

    @property
    def can_undo(self)->bool:
        return bool(self.undo_stack)

    @property
    def can_redo(self)->bool:
        return bool(self.redo_stack)

    def snapshot(self,extra:dict|None=None)->tuple[dict,dict]:
        """获取当前课表快照：(各班课表, 附加状态)；附加状态由界面传入（如保存状态、方案名）"""
        return {class_name:clas.__json__() for class_name,clas in lesson_info.classes.items()},dict(extra or {})

    def push(self,snapshot:tuple|None=None):
        """记录一步可撤销的操作，应在修改课表之前调用"""
        if snapshot is None:
            snapshot=self.snapshot()
        self.undo_stack.append(snapshot)
        if len(self.undo_stack)>self.limit:
            del self.undo_stack[0]
        self.redo_stack.clear()

    def undo(self,curr_snapshot:tuple)->tuple[tuple,dict[str,set[Time]]]|None:
        """撤销一步，返回(恢复到的快照, 发生变化的班级及位置)；没有可撤销的操作时返回 None"""
        if not self.undo_stack:
            return None
        self.redo_stack.append(curr_snapshot)
        if len(self.redo_stack)>self.limit:
            del self.redo_stack[0]
        target=self.undo_stack.pop()
        changed=diff_timetables(target[0],curr_snapshot[0])
        restore_timetables(target,changed)
        return target,changed

    def redo(self,curr_snapshot:tuple)->tuple[tuple,dict[str,set[Time]]]|None:
        """重做一步，返回(恢复到的快照, 发生变化的班级及位置)；没有可重做的操作时返回 None"""
        if not self.redo_stack:
            return None
        self.undo_stack.append(curr_snapshot)
        if len(self.undo_stack)>self.limit:
            del self.undo_stack[0]
        target=self.redo_stack.pop()
        changed=diff_timetables(target[0],curr_snapshot[0])
        restore_timetables(target,changed)
        return target,changed


# ==================== 课程表方案存取 ====================
def plan_file_path(plan_name:str)->str:
    """按方案名生成不重复的方案文件路径（过滤 Windows 文件名非法字符）"""
    filename=plan_name.translate(str.maketrans({'\\':'_','/':'_',':':'_','*':'_','?':'_','"':'_','<':'_','>':'_','|':'_'}))
    plan_dir=os.path.join(appdata,"timetable_plans")
    while os.path.exists(os.path.join(plan_dir,filename+".json")):
        filename+="_"
    os.makedirs(plan_dir,exist_ok=True)
    return os.path.join(plan_dir,filename+".json")

def save_current_plan(plan_name:str,plan_desc:str,plan_time:str)->str:
    """把当前课表保存为方案（已存在的方案会被覆盖），返回方案文件路径"""
    filename=cfg.timetable_plans.value.get(plan_name,{}).get("filename") or plan_file_path(plan_name)
    cfg.timetable_plans.value[plan_name]={"desc":plan_desc,"time":plan_time,"filename":filename}
    save_settings()
    with open(filename,"w",encoding="utf-8") as f:
        json.dump(lesson_info.classes,f,cls=LessonInfoEncoder,ensure_ascii=False)
    logging.info(f"课程表方案已保存：{plan_name} -> {filename}")
    return filename

def read_plan_file(filename:str)->dict:
    """读取方案文件中的课表"""
    with open(filename,"r",encoding="utf-8") as f:
        return json.load(f)

def check_plan_compatible(plan:dict)->bool:
    """检查方案是否与当前设置匹配（班级、节次、学科都存在）"""
    for class_name,timetable in plan.items():
        if class_name not in lesson_info.class_names:
            return False
        for time_str,subjects in timetable.items():
            if Time(string=time_str).lesson>cfg.day_class_num:
                return False
            for subject_name in subjects:
                if subject_name not in lesson_info.subjects:
                    return False
    return True

def apply_plan(plan:dict):
    """把方案中的课表应用到当前课表（调用前应先用 check_plan_compatible 校验）"""
    for class_name,timetable in plan.items():
        clas=lesson_info.classes[class_name]
        clas.reset()
        for time_str,subjects in timetable.items():
            if len(subjects)==1:
                clas.add_lesson(Time(string=time_str),lesson_info.subjects[subjects[0]])
            elif len(subjects)==2:
                clas.add_lesson(Time(string=time_str).sin_week,lesson_info.subjects[subjects[0]])
                clas.add_lesson(Time(string=time_str).dou_week,lesson_info.subjects[subjects[1]])

def delete_plans(plan_names:list[str]):
    """删除课程表方案（文件与配置）"""
    for plan_name in plan_names:
        filename=cfg.timetable_plans.value[plan_name]["filename"]
        if os.path.exists(filename):
            os.remove(filename)
        del cfg.timetable_plans.value[plan_name]
    save_settings()


# ==================== 课程查询 ====================
def get_teacher_lessons_at_cell(teacher:Teacher,row:int,column:int)->list[tuple[Class,Subject,Time]]:
    """获取某教师 (row,column) 位置上的所有课程（含单周与双周）"""
    base_time=Time(column+1,row+1)
    lessons=[]
    for curr_time in (base_time.all_week,base_time.sin_week,base_time.dou_week):
        for clas,subject in teacher.get_lessons(curr_time):
            lessons.append((clas,subject,curr_time))
    return lessons

def get_subject_lessons_at_cell(subject:Subject,row:int,column:int,class_scope=None)->list[tuple[Class,Subject,Time]]:
    """获取某学科 (row,column) 位置上的所有课程；class_scope 不为空时只统计范围内的班级"""
    curr_time=Time(column+1,row+1)
    lessons=[(clas,subject,curr_time) for clas in subject.timetable.get(curr_time,[])]
    if class_scope is None:
        return lessons
    return [lesson for lesson in lessons if lesson[0] in class_scope]
