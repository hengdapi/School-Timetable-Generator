"""课程表编辑的后端逻辑：撤销/重做历史、调课检查、课程表方案存取

本模块只处理数据，不创建任何界面组件；界面层（pages/generate.py）负责渲染与交互。
"""

from core.generate_core import check,check_exchange
from core.rules import *


# ==================== 调课检查 ====================
def reason_key(clas:Class,subjects:list[Subject],source_time:Time|None,target_time:Time)->str:
    """生成"某节课挪到某个位置"的原因分类键

    :param clas: 课程所在的班级
    :param subjects: 要挪动的课程（1 节或单双周 2 节）
    :param source_time: 源位置；从暂存区拖入时为 None
    :param target_time: 目标位置
    :return: 形如"高一1班 星期一上午第1节 语文 → 星期五下午第2节"的分类键
    """
    subject_names=", ".join([str(subject) for subject in subjects])
    if source_time is None:  # 从暂存区拖入，没有源位置
        return f"{clas} {subject_names} → {target_time}"
    return f"{clas} {source_time} {subject_names} → {target_time}"

def check_merged_placement(clas:Class,subject:Subject,source_time:Time|None,target_time:Time,reasons:dict[str,set[str]],conflicts:set,check_time:Time|None=None):
    """并课的其他班级要跟着一起调课，把它们的冲突原因单独分类记录

    :param clas: 当前预览的班级
    :param subject: 要挪动的课程
    :param source_time: 源位置；从暂存区拖入时为 None
    :param target_time: 目标位置（用于生成原因分类键）
    :param reasons: 原因分类字典，会为每个并课班级写入一项
    :param conflicts: 冲突课程集合
    :param check_time: 实际检查的时间（单双周课程的某一周），默认与 target_time 相同
    """
    for merged_classes in lesson_info.merged_lessons.get(subject,[]):
        if clas not in merged_classes:
            continue
        for clas2 in merged_classes:
            if clas2==clas:
                continue
            key=reason_key(clas2,[subject],source_time,target_time)
            reason_set: set[str]=set()
            reasons[key]=reason_set
            check(clas2,check_time or target_time,subject,reason_set,conflicts,True,True)

def check_placement(clas:Class,source_subjects:list[Subject],source_time:Time|None=None,exchange:bool=True):
    """遍历整个课表，检查源课程能否放到（或交换到）每个位置

    :param clas: 当前预览的班级
    :param source_subjects: 源位置上的课程（1 节或单双周 2 节）
    :param source_time: 源位置；exchange 为 True 时必填
    :param exchange: True 为交换课程，False 为把课程放到某个位置（如从暂存区拖入）
    :return: (check_result, failed_reasons, conflict_lessons)
             check_result[位置]=能否放置
             failed_reasons[位置]["班级 源位置 课程 → 目标位置"]=这次移动不能完成的原因（并课班级各占一项）
             conflict_lessons[位置]=冲突的课程
    """
    check_result:dict[Time,bool]={}
    failed_reasons:dict[Time,dict[str,set[str]]]={}
    conflict_lessons:dict[Time,set[tuple[Class,Time]]]={}
    for day in range(1,6):
        for lesson in range(1,cfg.day_class_num+1):
            target_time=Time(day,lesson)
            target_subjects=clas.get_lessons(target_time)
            can_place=False
            reasons:dict[str,set[str]]={}
            conflicts=set()
            if exchange and source_time:
                # 交换模式：目标不能是自身，且要通过 check_exchange
                if target_time!=source_time:
                    if target_subjects:
                        can_place=check_exchange(clas,source_time,target_time,reasons,conflicts)
                    else:
                        # 目标是空位：直接检查源课程能否放入
                        key=reason_key(clas,source_subjects,source_time,target_time)
                        reason_set: set[str]=set()
                        reasons[key]=reason_set
                        if len(source_subjects)==1:
                            can_place=check(clas,target_time,source_subjects[0],reason_set,conflicts,True)
                        elif len(source_subjects)==2:
                            check1=check(clas,target_time.sin_week,source_subjects[0],reason_set,conflicts,True)
                            check2=check(clas,target_time.dou_week,source_subjects[1],reason_set,conflicts,True)
                            can_place=check1 and check2
                        for subject in source_subjects:
                            check_merged_placement(clas,subject,source_time,target_time,reasons,conflicts)
            else:
                # 添加模式（如从暂存区拖来）
                subject=source_subjects[0]
                key=reason_key(clas,[subject],None,target_time)
                reason_set=reasons.setdefault(key,set[str]())
                if target_subjects and len(target_subjects)==1 and target_subjects[0] in clas.half_subjects and subject in clas.half_subjects:
                    check_time=target_time.dou_week  # 目标已有单周课程，可以拼成单双周
                elif not target_subjects and subject in clas.half_subjects:
                    check_time=target_time.sin_week
                else:
                    check_time=target_time  # 已有课程时只检查新课程能否放这里（原课程会被移入暂存区）
                can_place=check(clas,check_time,subject,reason_set,conflicts,True)
                check_merged_placement(clas,subject,None,target_time,reasons,conflicts,check_time)
            if target_subjects==source_subjects:  # 相同学科无需调整
                can_place=False
            check_result[target_time]=can_place
            failed_reasons[target_time]=reasons
            conflict_lessons[target_time]=conflicts
    return check_result,failed_reasons,conflict_lessons


# ==================== 并课跟随调整 ====================
def get_merged_classes(clas:Class,subjects:list[Subject])->dict[Class,list[Subject]]:
    """获取与这些课程并课的其他班级

    :param clas: 当前操作的班级
    :param subjects: 参与调课的课程
    :return: {并课班级: [与该班并课的课程, ...]}；没有并课班级时返回空字典
    """
    merged:dict[Class,list[Subject]]={}
    for subject in subjects:
        for merged_classes in lesson_info.merged_lessons.get(subject,[]):
            if clas not in merged_classes:
                continue
            for clas2 in merged_classes:
                if clas2!=clas:
                    merged.setdefault(clas2,[]).append(subject)
    return merged

def _find_lesson_time(clas:Class,subject:Subject,prefer_time:Time|None=None)->Time|None:
    """查找班级中某门课当前所在的位置；prefer_time 位置上有这门课时优先返回它"""
    if prefer_time is not None and subject in clas.get_lessons(prefer_time):
        return prefer_time
    for time,subjects in clas.timetable.items():
        if subject in subjects:
            return time
    return None

def _move_merged_subject(clas:Class,subject:Subject,source_time:Time|None,target_time:Time)->bool:
    """把并课班级的一门对应课程调到目标位置，返回是否进行了调整

    目标位置已有课程时整体交换，没有则整体移动，与当前班级的操作保持一致。
    """
    curr_time=_find_lesson_time(clas,subject,source_time)
    if curr_time is None or curr_time==target_time:
        return False  # 没有排这门课，或已经在目标位置
    if curr_time in clas.set_lessons or target_time in clas.set_lessons:
        return False  # 固定课程不能调
    curr_subjects=clas.get_lessons(curr_time)
    target_subjects=clas.get_lessons(target_time)
    if curr_subjects and target_subjects:
        clas.exchange_lessons(curr_time,target_time)
    elif curr_subjects:
        clas.remove_lesson(curr_time)
        for subject2 in curr_subjects:
            clas.add_lesson(target_time,subject2)
    logging.info(f"并课跟随调整：{clas} {curr_time} 的课程已调到 {target_time}")
    return True

def adjust_merged_lessons(clas:Class,source_time:Time,target_time:Time,source_subjects:list[Subject])->list[Class]:
    """并课班级跟着当前班级一起调课：把并课班级的对应课程调到目标位置

    调用前应完成当前班级的调课；source_subjects 传调课前源位置上的课程。
    交换课程时需要调用两次，分别处理两个方向上的课程。

    :param clas: 当前操作的班级
    :param source_time: 源位置
    :param target_time: 目标位置
    :param source_subjects: 源位置上参与调课的课程（调课前的课程）
    :return: 实际跟着调整了的并课班级
    """
    adjusted:list[Class]=[]
    for clas2,merged_subjects in get_merged_classes(clas,source_subjects).items():
        moved=False
        for subject in merged_subjects:
            moved=_move_merged_subject(clas2,subject,source_time,target_time) or moved
        if moved:
            adjusted.append(clas2)
    return adjusted

def add_merged_lesson(clas:Class,target_time:Time,subject:Subject)->list[Class]:
    """从暂存区放入并课课程时，并课班级也放入对应课程（并课班级要在同一时间上这门课）

    :param clas: 当前操作的班级
    :param target_time: 放入的位置
    :param subject: 放入的课程
    :return: 实际跟着放入课程的并课班级
    """
    adjusted:list[Class]=[]
    for clas2 in get_merged_classes(clas,[subject]):
        if subject in clas2.get_lessons(target_time):
            continue  # 并课班级该位置已经是这门课
        if _move_merged_subject(clas2,subject,None,target_time):
            adjusted.append(clas2)  # 并课班级排了这门课，已调到目标位置
            continue
        if clas2.get_subject_left_num(subject)<=0:
            continue  # 并课班级没有剩余课时
        if target_time in clas2.set_lessons:
            continue  # 并课班级该位置是固定课程
        target_subjects=clas2.get_lessons(target_time)
        if len(target_subjects)==1 and target_subjects[0] in clas2.half_subjects and subject in clas2.half_subjects:
            clas2.add_lesson(target_time.dou_week,subject)  # 目标已有单周课程，拼成单双周
        elif not target_subjects and subject in clas2.half_subjects:
            clas2.add_lesson(target_time.sin_week,subject)
        else:
            if target_subjects:
                clas2.remove_lesson(target_time)  # 原课程移回暂存区
            clas2.add_lesson(target_time,subject)
        adjusted.append(clas2)
        logging.info(f"并课跟随调整：{subject} 已同步放入 {clas2} 的 {target_time}")
    return adjusted

def store_merged_lessons(clas:Class,time:Time,subjects:list[Subject])->list[Class]:
    """并课班级的对应课程一起收回暂存区（把课程拖到暂存区时调用）

    :param clas: 当前操作的班级
    :param time: 课程所在位置
    :param subjects: 该位置上参与并课的课程
    :return: 实际跟着收回暂存区的并课班级
    """
    adjusted:list[Class]=[]
    for clas2,merged_subjects in get_merged_classes(clas,subjects).items():
        stored=False
        for subject in merged_subjects:
            curr_time=_find_lesson_time(clas2,subject,time)
            if curr_time is None or curr_time in clas2.set_lessons:
                continue  # 没有排这门课，或是固定课程
            clas2.remove_lesson(curr_time)
            stored=True
            logging.info(f"并课跟随调整：{clas2} {curr_time} 的 {subject} 已收回暂存区")
        if stored:
            adjusted.append(clas2)
    return adjusted


# ==================== 一键检查冲突 ====================
class Conflict:
    """一处课程冲突或规则冲突"""

    def __init__(self,category:str,clas:Class,time:Time,message:str):
        self.category=category  # 冲突类别：课程冲突 / 规则冲突
        self.clas=clas          # 冲突所在班级（用于跳转）
        self.time=time          # 冲突所在时间（用于跳转）
        self.message=message    # 冲突描述

    @property
    def sort_key(self)->tuple:
        return (self.category,self.clas.name,self.time.day,self.time.lesson)

def _is_merged_together(clas1:Class,clas2:Class,subject:Subject)->bool:
    """两个班级是否在该学科上并课（并课班级在同一时间上课是正常的）"""
    for merged_classes in lesson_info.merged_lessons.get(subject,[]):
        if clas1 in merged_classes and clas2 in merged_classes:
            return True
    return False

def _teacher_time_entries(teacher:Teacher,time:Time)->list[tuple[Class,Subject,set[str]]]:
    """获取某教师在某个时间位置上的全部课程，及每节课占用的周次"""
    entries:list[tuple[Class,Subject,set[str]]]=[]
    for variant,weeks in ((time.sin_week,{"sin"}),(time.dou_week,{"dou"}),(time.all_week,{"sin","dou"})):
        for clas,subject in teacher.timetable.get(variant,[]):
            entries.append((clas,subject,weeks))
    return entries

def _count_subject_at(subject:Subject,time:Time)->int:
    """统计某个时间排了某门课的班级数（一组并课算一节课）"""
    classes=list(subject.timetable.get(time,[]))
    count=0
    for merged_classes in lesson_info.merged_lessons.get(subject,[]):
        if any(clas in classes for clas in merged_classes):
            count+=1
            classes=[clas for clas in classes if clas not in merged_classes]
    return count+len(classes)

def _check_teacher_conflicts(classes:list[Class])->list[Conflict]:
    """检查同一教师在同一时间有多节课的冲突（并课课程除外）

    只报告涉及检查范围内班级的冲突（与范围外班级的冲突也会列出，便于对照），
    冲突挂到范围内第一个涉及的班级上。
    """
    class_set=set(classes)
    conflicts:list[Conflict]=[]
    for teacher in lesson_info.teacher_lst:
        for day in range(1,6):
            for lesson in range(1,cfg.day_class_num+1):
                time=Time(day,lesson)
                entries=_teacher_time_entries(teacher,time)
                if len(entries)<2:
                    continue
                # 找出与其他课在周次上冲突的课（并课班级的同一门课不算冲突）
                conflicting:list[tuple[Class,Subject]]=[]
                for clas1,subject1,weeks1 in entries:
                    for clas2,subject2,weeks2 in entries:
                        if (clas1,subject1)==(clas2,subject2) or not (weeks1&weeks2):
                            continue
                        if subject1==subject2 and _is_merged_together(clas1,clas2,subject1):
                            continue
                        if (clas1,subject1) not in conflicting:
                            conflicting.append((clas1,subject1))
                in_scope=[entry for entry in conflicting if entry[0] in class_set]
                if in_scope:
                    lessons="、".join([f"{clas} 的 {subject}" for clas,subject in conflicting])
                    conflicts.append(Conflict("课程冲突",in_scope[0][0],time,
                        f"教师冲突：{teacher} 老师在 {time} 同时有 {lessons}"))
    return conflicts

def _check_cell_conflicts(classes:list[Class])->list[Conflict]:
    """检查同一时间排了多节课、单双周课程没有成对安排等冲突"""
    conflicts:list[Conflict]=[]
    for clas in classes:
        for time,subjects in clas.timetable.items():
            if len(subjects)>1 and not (len(subjects)==2 and subjects[0] in clas.half_subjects and subjects[1] in clas.half_subjects):
                conflicts.append(Conflict("课程冲突",clas,time,
                    f"课程冲突：{time} 同时排了 {'、'.join([str(s) for s in subjects])}（非单双周课程不能排在同一时间）"))
        # 单双周课程要成对安排（两周各上一次），不能多次只排在单周
        for subject in clas.half_subjects:
            total=clas.count_subject(subject)
            if total<2:
                continue
            sin_num=0
            first_time=None
            for time,subjects in clas.timetable.items():
                if subject not in subjects:
                    continue
                if first_time is None:
                    first_time=time
                if len(subjects)==1 or subjects[0] is subject:
                    sin_num+=1  # 单独排的一节在单周；与另一门单双周课配对时，排在前面的一节也在单周
            if sin_num>(total+1)//2:
                conflicts.append(Conflict("规则冲突",clas,first_time or Time(1,1),
                    f"规则冲突：{subject} 是单双周课程，但 {clas} 有 {sin_num} 节课排在单周（共 {total} 节，应单双周交替安排）"))
    return conflicts

def _check_rule_conflicts(classes:list[Class])->list[Conflict]:
    """对照已配置的规则，检查课表中违反规则的地方"""
    class_set=set(classes)
    conflicts:list[Conflict]=[]
    all_times=[Time(day,lesson) for day in range(1,6) for lesson in range(1,cfg.day_class_num+1)]
    for clas in classes:
        if clas.empty:
            continue  # 整张课表都是空的，没有什么可冲突的
        clas_rules=[rule for rule in lesson_info.rules if clas in rule.scope]
        # ---- 与位置相关的规则 ----
        for time in all_times:
            subjects=clas.get_lessons(time)
            for rule in clas_rules:
                if isinstance(rule,SetTimeRule):
                    if time in rule.times and rule.subject not in subjects:
                        detail=f"，实际排了 {'、'.join([str(s) for s in subjects])}" if subjects else "，但该位置没有排课"
                        conflicts.append(Conflict("规则冲突",clas,time,f"规则冲突：{time} 必须排 {rule.subject}{detail}"))
                elif isinstance(rule,AvoidTimeRule):
                    if time in rule.times:
                        for subject in subjects:
                            if subject in rule.subjects:
                                conflicts.append(Conflict("规则冲突",clas,time,f"规则冲突：{subject} 不能排在 {time}"))
                elif isinstance(rule,SetNumRule):
                    for subject in subjects:
                        if subject in rule.subjects:
                            num=_count_subject_at(subject,time)
                            if num>rule.number:
                                conflicts.append(Conflict("规则冲突",clas,time,
                                    f"规则冲突：{time} 有 {num} 个班级排 {subject}（规则要求同一时间最多排 {rule.number} 节）"))
                elif isinstance(rule,AvoidSubjectRule):
                    seen=set()
                    for subject in subjects:
                        others=rule.subjectsB if subject in rule.subjectsA else rule.subjectsA if subject in rule.subjectsB else []
                        for other in others:
                            if other is subject or not other.timetable.get(time):
                                continue
                            pair=frozenset({subject.name,other.name})
                            if pair in seen:
                                continue
                            seen.add(pair)
                            classes="、".join([str(c) for c in other.timetable.get(time)])
                            conflicts.append(Conflict("规则冲突",clas,time,
                                f"规则冲突：{subject} 与 {other} 不能排在同一时间，{time} {clas} 排了 {subject}，{classes} 排了 {other}"))
                elif isinstance(rule,AvoidTeacherRule):
                    for subject in subjects:
                        teacher=clas.get_teacher(subject)
                        others=rule.teachersB if teacher in rule.teachersA else rule.teachersA if teacher in rule.teachersB else []
                        for teacher2 in others:
                            if teacher2 is teacher:
                                continue
                            entries=_teacher_time_entries(teacher2,time)
                            if entries:
                                detail="、".join([f"{c} 的 {s}" for c,s,_ in entries])
                                conflicts.append(Conflict("规则冲突",clas,time,
                                    f"规则冲突：{teacher} 老师与 {teacher2} 老师不能在同一时间排课，{time} {clas} 的 {subject} 由 {teacher} 授课，{teacher2} 同时有 {detail}"))
                elif isinstance(rule,TeacherAvoidTimeRule):
                    if time in rule.times:
                        for subject in subjects:
                            teacher=clas.get_teacher(subject)
                            if teacher in rule.teachers:
                                conflicts.append(Conflict("规则冲突",clas,time,
                                    f"规则冲突：{teacher} 老师不能在 {time} 排课，但 {clas} 在该时间有 {subject} 课"))
        # ---- 与整个班级课表相关的规则 ----
        for rule in clas_rules:
            if isinstance(rule,EverydaySubjectRule):
                for subject in rule.subjects:
                    for day in range(1,6):
                        if clas.count_subject(subject,Time(day,1),Time(day,cfg.day_class_num))==0:
                            conflicts.append(Conflict("规则冲突",clas,Time(day,1),
                                f"规则冲突：{subject} 每天至少排一次课，但 {clas} {Time(day,1).to_str(True,False)} 没有排"))
            elif isinstance(rule,SetContinueRule):
                for subject in rule.subjects:
                    have=clas.get_continue_times(subject)
                    if have<rule.number:
                        conflicts.append(Conflict("规则冲突",clas,Time(1,1),
                            f"规则冲突：{subject} 每周需要连堂 {rule.number} 次，但 {clas} 只有 {have} 次"))
    # ---- 跨班级的规则 ----
    for rule in lesson_info.rules:
        if not rule.scope:
            continue
        if isinstance(rule,TeacherSetTimeRule):
            in_scope=[clas for clas in rule.scope if clas in class_set]
            if not in_scope:
                continue  # 检查范围内没有该规则涉及的班级
            for teacher in rule.teachers:
                for rule_time in rule.times:
                    if not any(clas.get_teacher(subject)==teacher
                               for clas in rule.scope for subject in clas.get_lessons(rule_time)):
                        conflicts.append(Conflict("规则冲突",in_scope[0],rule_time,
                            f"规则冲突：{teacher} 老师必须在 {rule_time} 排课，但该时间没有排课"))
        elif isinstance(rule,SubjectOrderRule):
            # 只比较已经排完的班级（还有课在暂存区的班级进度不完整，与调课检查的逻辑保持一致）
            scope=[clas for clas in rule.scope if not clas.left_subjects]
            if not any(clas in class_set for clas in scope):
                continue  # 检查范围内没有该规则涉及的班级
            for subject in rule.subjects:
                if len(scope)<2:
                    continue
                counts={clas.name:0 for clas in scope}
                time=Time(1,1)
                while True:
                    for clas in scope:
                        counts[clas.name]+=clas.get_lessons(time).count(subject)
                    if max(counts.values())-min(counts.values())>1:
                        detail="，".join([f"{name} {num} 个课时" for name,num in counts.items()])
                        worst=max(scope,key=lambda c:counts[c.name])
                        attach=worst if worst in class_set else next(c for c in scope if c in class_set)
                        conflicts.append(Conflict("规则冲突",attach,time,
                            f"规则冲突：{subject} 的教学进度在 {time} 不一致（{detail}）"))
                        break
                    time=time.next
                    if time==Time(1,1):
                        break
    return conflicts

def _check_merged_sync(classes:list[Class])->list[Conflict]:
    """检查并课班级是否都在同一时间上这门课

    正确的判定是：每个并课班级排这门课的「时间集合」要完全一致。
    一门课一周排多节（如体育一周两节）时，只要所有并课班级都在同样的时间集合上，
    就视为同步——旧实现只统计“总共占了多少个不同时间”，会误报未同步。
    """
    class_set=set(classes)
    conflicts:list[Conflict]=[]
    for subject,groups in lesson_info.merged_lessons.items():
        for group in groups:
            # 没有这门课的班级、整张课表还是空的班级不参与并课
            group=[clas for clas in group if subject.name in clas.teachers and not clas.empty]
            if len(group)<2:
                continue
            if not any(clas in class_set for clas in group):
                continue  # 检查范围内没有该并课小组的班级
            # 每个并课班级排这门课的时间集合
            placement:dict[Class,set[Time]]={}
            for clas in group:
                placement[clas]={time for time,subjects in clas.timetable.items() if subject in subjects}
            reference=set().union(*placement.values())
            if not reference:
                continue  # 都还没有排这门课
            for clas in group:
                missing=reference-placement[clas]
                if not missing:
                    continue  # 该班排这门课的时间与并课小组一致
                first_time=min(missing)
                others="、".join([str(c) for c in group if c is not clas and first_time in placement[c]])
                attach=clas if clas in class_set else next(c for c in group if c in class_set)
                details="；".join(f"{t} 未排" for t in sorted(missing))
                conflicts.append(Conflict("课程冲突",attach,first_time,
                    f"并课未同步：{clas} 的 {subject} 在 {details}，但并课班级 {others} 在这些时间排了 {subject}"))
    return conflicts

def check_all_conflicts(classes:list[Class]|None=None)->list[Conflict]:
    """一键检查课表，返回全部课程冲突与规则冲突

    :param classes: 要检查的班级列表；None 表示检查全部班级
    :return: 冲突列表（按类别、班级、时间排序）
    """
    if classes is None:
        classes=lesson_info.class_lst
    conflicts:list[Conflict]=[]
    conflicts+=_check_teacher_conflicts(classes)
    conflicts+=_check_cell_conflicts(classes)
    conflicts+=_check_rule_conflicts(classes)
    conflicts+=_check_merged_sync(classes)
    conflicts.sort(key=lambda conflict:conflict.sort_key)
    return conflicts


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
