import random
import time

from core.rules import *
def check(clas: Class,time: Time,subject: Subject,failed_reasons:set|None=None,conflict_lessons:set|None=None,manual:bool=False) -> bool:
    try:
        if isinstance(failed_reasons,set):
            reasons_num=len(failed_reasons)
        else:
            reasons_num=0
        logging.debug(f"检查能否在 {clas} 的 {time} 安排 {subject}")
        if subject not in clas.left_subjects:
            if failed_reasons is None:
                return False
            failed_reasons.add(f"课程冲突：{clas} 的 {subject} 已经排完")
            return False
        teacher=clas.get_teacher(subject)
        if not teacher.check(time,subject,failed_reasons,conflict_lessons):
            if failed_reasons is None:
                return False
        if subject in clas.set_lessons:
            if failed_reasons is None:
                return False
            failed_reasons.add(f"规则冲突：{subject} 是固定课程")
        time=time.all_week
        for rule in lesson_info.rules:
            if clas not in rule.scope:
                continue
            if isinstance(rule,SetTimeRule):
                if time in rule.times and rule.subject!=subject:
                    if failed_reasons is None:
                        return False
                    failed_reasons.add(f"规则冲突：{time} 必须排 {rule.subject}")
            # 不能排在指定时间
            elif isinstance(rule,AvoidTimeRule):
                # 支持只写节次（如"上午第4节"）
                if subject in rule.subjects and time in rule.times:
                    if failed_reasons is None:
                        return False
                    failed_reasons.add(f"规则冲突：{subject} 不能排在 {time} ")
            # 同一时间最多排几节课
            elif isinstance(rule,SetNumRule):
                if subject in rule.subjects and subject.get_time_num(time)>=int(rule.number):
                    if failed_reasons is None:
                        return False
                    failed_reasons.add(f"规则冲突：{subject} 同一时间 最多排 {rule.number} 节课")
            # 学科不能与另一学科同一时间
            elif isinstance(rule,AvoidSubjectRule):
                if subject in rule.subjectsA:
                    for subjectB in rule.subjectsB:
                        if subjectB.timetable.get(time):
                            if failed_reasons is None:
                                return False
                            failed_reasons.add(f"规则冲突：已经在 {", ".join([clas.name for clas in subjectB.timetable.get(time)])} 的 {time} 安排了与 {subject} 冲突的 {subjectB}")
                elif subject in rule.subjectsB:
                    for subjectA in rule.subjectsA:
                        if subjectA.timetable.get(time):
                            if failed_reasons is None:
                                return False
                            failed_reasons.add(f"规则冲突：已经在 {", ".join([clas.name for clas in subjectA.timetable.get(time)])} 的 {time} 安排了与 {subject} 冲突的 {subjectA}")
            # 老师不能与另一老师同一时间有课
            elif isinstance(rule,AvoidTeacherRule):
                if teacher in rule.teachersA:
                    for teacherB in rule.teachersB:
                        if teacherB.timetable.get(time):
                            if failed_reasons is None:
                                return False
                            failed_reasons.add(f"规则冲突：{subject} 的教师 {teacher} 和 {teacherB} 在 {time} 会冲突")
                elif teacher in rule.teachersB:
                    for teacherA in rule.teachersA:
                        if teacherA.timetable.get(time):
                            if failed_reasons is None:
                                return False
                            failed_reasons.add(f"规则冲突：{subject} 的教师 {teacher} 和 {teacherA} 在 {time} 会冲突")
            elif isinstance(rule,TeacherAvoidTimeRule):
                if teacher in rule.teachers and time in rule.times:
                    if failed_reasons is None:
                        return False
                    failed_reasons.add(f"规则冲突：{subject} 的教师 {teacher} 不能在 {time} 排课")
            elif manual and isinstance(rule,SubjectOrderRule):
                if subject not in rule.subjects:
                    continue
                for clas2 in rule.scope:
                    if clas2.left_subjects:
                        continue
                    if clas2.count_subject(subject,end=time)<clas.count_subject(subject,end=time):
                        if failed_reasons is None:
                            return False
                        failed_reasons.add(f"规则冲突：{clas2} 在 {time} 之前 {subject} 只有{clas2.count_subject(subject,end=time)}个课时，而调课后 {clas} 会有{clas.count_subject(subject,end=time)+1}个课时")
                    if clas2.count_subject(subject,end=time)>clas.count_subject(subject,end=time)+1:
                        if failed_reasons is None:
                            return False
                        failed_reasons.add(f"规则冲突：{clas2} 在 {time} 之前 {subject} 已经有{clas2.count_subject(subject,end=time)}个课时，而调课后 {clas} 只有{clas.count_subject(subject,end=time)+1}个课时")

        if isinstance(failed_reasons,set) and len(failed_reasons)>reasons_num:
            logging.debug(f"不能排课，原因：\n{"\n".join(failed_reasons)}")
            return False
        return True
    except:
        e=traceback.format_exc()
        logging.error(f"检查时出错：\n{e}")
        return False

def check_exchange(clas:Class,time1:Time,time2:Time,failed_reasons:set,conflict_lessons:set)->bool:
    subjects1=clas.get_lessons(time1)
    subjects2=clas.get_lessons(time2)
    if not subjects1 or not subjects2:
        return False
    if time1.day!=time2.day:
        for subject1 in subjects1:
            if subject1 in clas.everyday_subjects and clas.count_subject(subject1,Time(time1.day,1),Time(time1.day,cfg.day_class_num))==1:
                failed_reasons.add(f"规则冲突：{subject1} 每天至少排一节课")
                return False
        for subject2 in subjects2:
            if subject2 in clas.everyday_subjects and clas.count_subject(subject2,Time(time1.day,1),Time(time1.day,cfg.day_class_num))==1:
                failed_reasons.add(f"规则冲突：{subject2} 每天至少排一节课")
                return False

    # 两个半周课程：检查能否拼接
    if len(subjects1)==1 and subjects1[0] in clas.half_subjects and len(subjects2)==1 and subjects2[0] in clas.half_subjects and check(clas,time2.dou_week,subjects1[0],failed_reasons):
        return True
    # 目标位置是空位：直接检查源课程能否放入
    if not subjects2:
        if len(subjects1)==1:
            return check(clas,time2,subjects1[0],failed_reasons,conflict_lessons,True)
        elif len(subjects1)==2:
            check1=check(clas,time2.sin_week,subjects1[0],failed_reasons,conflict_lessons,True)
            check2=check(clas,time2.dou_week,subjects1[1],failed_reasons,conflict_lessons,True)
            return check1 and check2
        return False
    # 源位置是空位：理论上不应该发生
    if not subjects1:
        return False
    if (time1,subjects1[0]) in clas.set_lessons.items():
        failed_reasons.add(f"规则冲突：{time1} 必须排 {subjects1[0]}")
        return False
    if (time2,subjects2[0]) in clas.set_lessons.items():
        failed_reasons.add(f"规则冲突：{time2} 必须排 {subjects2[0]}")
        return False
    clas.remove_lesson(time1)
    clas.remove_lesson(time2)
    if len(subjects2)==1:
        check1=check(clas,time1,subjects2[0],failed_reasons,conflict_lessons,True)
    else:
        check1=check(clas,time1.sin_week,subjects2[0],failed_reasons,conflict_lessons,True)
        check2=check(clas,time1.dou_week,subjects2[1],failed_reasons,conflict_lessons,True)
        check1=check1 and check2
    if len(subjects1)==1:
        check2=check(clas,time2,subjects1[0],failed_reasons,conflict_lessons,True)
    else:
        check2=check(clas,time2.sin_week,subjects1[0],failed_reasons,conflict_lessons,True)
        check3=check(clas,time2.dou_week,subjects1[1],failed_reasons,conflict_lessons,True)
        check2=check2 and check3
    for subject in subjects1:
        clas.add_lesson(time1,subject)
    for subject in subjects2:
        clas.add_lesson(time2,subject)

    clas.timetable[time1],clas.timetable[time2]=subjects2,subjects1
    check_continue=True
    for subject in subjects1:
        if clas.get_continue_times(subject)<clas.continue_num[subject]:
            check_continue=False
            failed_reasons.add(f"规则冲突：交换后 {subject} 只能连堂 {clas.get_continue_times(subject)} 次（规则要求连堂 {clas.continue_num[subject]} 次） ")
    for subject in subjects2:
        if clas.get_continue_times(subject)<clas.continue_num[subject]:
            check_continue=False
            failed_reasons.add(f"规则冲突：交换后 {subject} 只能连堂 {clas.get_continue_times(subject)} 次（规则要求连堂 {clas.continue_num[subject]} 次） ")
    clas.timetable[time1],clas.timetable[time2]=subjects1,subjects2
    return check1 and check2 and check_continue

class GenerateThread(QThread):
    finished_signal=Signal(set)  # 生成成功
    progress_signal=Signal(tuple)  # 进度信息

    def __init__(self,class_lst:list[Class]|str,parent=None):
        super().__init__(parent)
        if isinstance(class_lst,str):
            self.generate_left=True
            self.class_lst=lesson_info.class_lst
        else:
            self.generate_left=False
            self.class_lst=class_lst
        self.last_progress_time=0  # 记录上次发送进度的时间
        self.progress_interval=0.8  # 进度更新间隔（秒）
        self.goto_lesson:tuple[Class,Time]|None=None
        self.skipped_lessons:set[tuple[Class,Time]]=set()
        self.tried_times:dict[Class,dict[Time,int]]={clas:{Time(day,lesson):0 for day in range(1,6) for lesson in range(1,cfg.day_class_num+1)} for clas in self.class_lst}
        logging.debug("创建GenerateThread实例")

    def run(self):
        # 执行耗时的课程表生成逻辑
        try:
            logging.info("开始生成课程表...")
            start_time = time.time()
            
            logging.debug("重新初始化班级，填充固定课程")
            if not self.generate_left:
                for clas in self.class_lst:
                    clas.reset()
                    for set_time,set_subject in clas.set_lessons.items():
                        clas.add_lesson(set_time,set_subject)

            logging.debug(f"开始DFS分配剩余课程，共{len(self.class_lst)}个班级")
            self.finish=False
            self.dfs(self.class_lst[0],Time(1,1))
            
            elapsed_time = time.time() - start_time
            logging.info(f"课程表生成完成，耗时{elapsed_time:.2f}秒")
        except:
            e=traceback.format_exc()
            logging.critical(f"生成课程表时错误：\n{e}")
        self.finish=True
        self.finished_signal.emit(self.skipped_lessons)

    def should_emit_progress(self):
        """判断是否应该发送进度信号"""
        current_time=time.time()
        if current_time-self.last_progress_time>=self.progress_interval:
            self.last_progress_time=current_time
            return True
        return False

    def dfs(self,clas: Class,curr_time: Time):
        try:
            if self.finish:
                return
            if self.should_emit_progress():
                percentage=round((self.class_lst.index(clas)*5*cfg.day_class_num+(curr_time.day-1)*cfg.day_class_num+curr_time.lesson)/(len(self.class_lst)*5*cfg.day_class_num)*100)
                self.progress_signal.emit((clas,curr_time,percentage))
            last=False
            if curr_time.day==5 and curr_time.lesson==cfg.day_class_num:
                if self.class_lst[-1]==clas:
                    last=True

            next_time=curr_time.next
            logging.debug(f"当前时间：{curr_time}")

            self.tried_times[clas][curr_time]+=1
            if self.tried_times[clas][curr_time]>cfg.max_tries.value:
                self.skipped_lessons.add((clas,curr_time))
                logging.debug(f"{curr_time} 尝试次数过多，跳过")
            else:
                must_add=None
                if curr_time.lesson==cfg.day_class_num:
                    for everyday_subject in clas.everyday_subjects:
                        if not clas.count_subject(everyday_subject,Time(curr_time.day,1),curr_time):
                            if must_add is not None:
                                return
                            must_add=everyday_subject

                if clas.get_lessons(curr_time):
                    logging.debug(f"{curr_time}存在已排课程")
                    if must_add:
                        return
                elif curr_time in clas.set_lessons:
                    logging.debug(f"{curr_time}存在固定课程")
                    if must_add or not check(clas,curr_time,clas.set_lessons[curr_time]):
                        return
                    clas.add_lesson(curr_time,clas.set_lessons[curr_time])
                else:
                    if curr_time in clas.priority_subjects:
                        curr_priority=clas.priority_subjects[curr_time]
                    else:
                        curr_priority=[]
                    logging.debug(f"当前优先课程：{[i.name for i in curr_priority]}")

                    curr_subjects=list(set(clas.left_subjects))
                    random.shuffle(curr_subjects)

                    if must_add:
                        if must_add in curr_subjects:
                            curr_subjects=[must_add]
                        else:
                            return

                    if cfg.average_subjects.value:
                        back_time=curr_time.prev
                        while back_time>Time(1,1):
                            lessons=clas.get_lessons(back_time)
                            if lessons:
                                if lessons[0] in curr_subjects:
                                    curr_subjects.remove(lessons[0])
                                    curr_subjects.append(lessons[0])
                                if len(lessons)>1 and lessons[1] in curr_subjects:
                                    curr_subjects.remove(lessons[1])
                                    curr_subjects.append(lessons[1])
                            back_time=back_time.prev

                    for subject in curr_subjects:
                        if cfg.reduce_continue.value and clas.get_teacher(subject).is_busy(curr_time.prev):
                            curr_subjects.remove(subject)
                            curr_subjects.append(subject)
                        elif subject in curr_priority or \
                                cfg.average_subjects.value and clas.get_subject_left_num(subject)>5-curr_time.day+1 or \
                                subject in clas.everyday_subjects and clas.get_subject_left_num(subject)>=5-curr_time.day+1:
                            curr_subjects.remove(subject)
                            curr_subjects.insert(0,subject)

                    logging.debug(f"当前课程：{[i.name for i in curr_subjects]}")

                    for subject in curr_subjects:
                        for order_subject,scope in clas.order_subjects_scope.items():
                            for clas2 in scope:
                                if clas2.left_subjects:
                                    continue
                                if clas2.count_subject(order_subject,end=curr_time)>clas.count_subject(order_subject,end=curr_time)+1:
                                    return
                        if subject not in clas.left_subjects:
                            continue
                        add_continue=False
                        # 单双周
                        if subject in clas.half_subjects:
                            if not check(clas, curr_time.sin_week, subject):
                                continue
                            clas.add_lesson(curr_time.sin_week,subject)
                            for subject2 in clas.half_subjects&set(clas.left_subjects):
                                if not check(clas, curr_time.dou_week, subject2):
                                    continue
                                clas.add_lesson(curr_time.dou_week,subject2)
                                if not last:
                                    if curr_time==Time(5,cfg.day_class_num):
                                        self.dfs(self.class_lst[self.class_lst.index(clas)+1],Time(1,1))
                                    else:
                                        self.dfs(clas,next_time)
                                    if self.finish:
                                        return
                                    clas.remove_lesson(curr_time.dou_week)
                            clas.remove_lesson(curr_time.sin_week)
                            continue
                        if not check(clas,curr_time,subject):
                            continue
                        if curr_time.day<5 and subject in clas.everyday_subjects:
                            if clas.get_subject_left_num(subject)==5-curr_time.day:
                                continue
                        if subject in clas.order_subjects_scope.keys():
                            too_many=False
                            for clas2 in clas.order_subjects_scope[subject]:
                                if clas2.left_subjects:
                                    continue
                                if clas2.count_subject(subject,end=curr_time)<clas.count_subject(subject,end=curr_time):
                                    too_many=True
                                    break
                            if too_many:
                                continue
                        if subject not in clas.half_subjects:
                            # 连堂
                            if clas.get_continue_times(subject)<clas.continue_num[subject] and clas.get_subject_left_num(subject)>=2:
                                if clas.continue_num[subject]-clas.get_continue_times(subject)==clas.get_subject_left_num(subject)/2:
                                    if check(clas,next_time,subject) and (cfg.allow_noon_continuous.value or curr_time.lesson!=cfg.morning_class_num.value) and curr_time.lesson!=cfg.day_class_num:
                                        add_continue=True
                                    else:
                                        continue
                                elif check(clas,next_time,subject) and (cfg.allow_noon_continuous.value or curr_time.lesson!=cfg.morning_class_num.value) and curr_time.lesson!=cfg.day_class_num:
                                    add_continue=random.choice([True,False])
                                if add_continue:
                                    clas.add_lesson(next_time,subject)
                                else:
                                    continue
                        clas.add_lesson(curr_time,subject)
                        if not last:
                            if curr_time==Time(5,cfg.day_class_num):
                                self.dfs(self.class_lst[self.class_lst.index(clas)+1],Time(1,1))
                            else:
                                self.dfs(clas,next_time)
                            if self.finish:
                                return
                            clas.remove_lesson(curr_time)
                            if add_continue:
                                clas.remove_lesson(next_time)
                    return
            if not last:
                if curr_time==Time(5,cfg.day_class_num):
                    self.dfs(self.class_lst[self.class_lst.index(clas)+1],Time(1,1))
                else:
                    self.dfs(clas,next_time)
            if last:
                self.finish=True
        except:
            e=traceback.format_exc()
            logging.critical(f"生成课程表出错：{clas} {curr_time}\n{e}")