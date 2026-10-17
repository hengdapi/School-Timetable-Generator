import random
import time

from core.rules import *
def check(clas: Class,time: Time,subject: Subject,failed_reasons:set|None=None,conflict_lessons:set|None=None,manual:bool=False,merged:bool=False,merged_failed_reasons:set|None=None) -> bool:
    try:
        if isinstance(failed_reasons,set):
            reasons_num=len(failed_reasons)
        else:
            reasons_num=0
        logging.debug(f"检查能否在 {clas} 的 {time} 安排 {subject}")
        teacher=clas.get_teacher(subject)
        if not merged and not teacher.check(time,subject,failed_reasons,conflict_lessons):
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
                    time2=Time(1,1)
                    clas2_cnt=clas_cnt=0
                    while True:
                        if clas2.get_lessons(time2) and subject in clas2.get_lessons(time2):
                            clas2_cnt+=1
                        if clas.get_lessons(time2) and subject in clas.get_lessons(time2):
                            clas_cnt+=1
                        if time2>=time:
                            clas_cnt+=1
                        if clas2_cnt<clas_cnt-1:
                            if failed_reasons is None:
                                return False
                            failed_reasons.add(f"规则冲突：{clas2} 在 {time2} 之前 {subject} 只有{clas2_cnt}个课时，而调课后 {clas} 会有{clas_cnt}个课时")
                            break
                        if clas2_cnt>clas_cnt+1:
                            if failed_reasons is None:
                                return False
                            failed_reasons.add(f"规则冲突：{clas2} 在 {time2} 之前 {subject} 已经有{clas2_cnt}个课时，而调课后 {clas} 只有{clas_cnt}个课时")
                            break
                        if time2>=time:
                            clas_cnt-=1
                        time2=time2.next
                        if time2==Time(1,1):
                            break

        if not merged:
            for merged_classes in lesson_info.merged_lessons.get(subject,[]):
                if clas not in merged_classes:
                    continue
                for clas2 in merged_classes:
                    if clas!=clas2:
                        check(clas2,time,subject,merged_failed_reasons,conflict_lessons,True,True)
        if isinstance(failed_reasons,set) and len(failed_reasons)>reasons_num:
            logging.debug(f"不能排课，原因：\n{"\n".join(failed_reasons)}")
            return False
        return True
    except:
        e=traceback.format_exc()
        logging.error(f"检查时出错：\n{e}")
        return False

def check_exchange(clas:Class,time1:Time,time2:Time,failed_reasons:dict[str,set],conflict_lessons:set)->bool:
    subjects1=clas.get_lessons(time1)
    subjects2=clas.get_lessons(time2)
    if not subjects1 or not subjects2:
        return False
    failed_reasons1=failed_reasons[f"{clas} {time1} {", ".join([str(s) for s in subjects1])} → {time2}"]=set()
    failed_reasons2=failed_reasons[f"{clas} {time2} {", ".join([str(s) for s in subjects2])} → {time1}"]=set()

    def check_merged(subject:Subject,from_time:Time,to_time:Time):
        """并课的其他班级要跟着一起调课，把它们的冲突原因单独分类记录"""
        for merged_classes in lesson_info.merged_lessons.get(subject,[]):
            if clas not in merged_classes:
                continue
            for clas2 in merged_classes:
                if clas2==clas:
                    continue
                key=f"{clas2} {from_time} {subject} → {to_time}"
                check(clas2,to_time,subject,failed_reasons.setdefault(key,set()),conflict_lessons,True,True)

    if time1.day!=time2.day:
        for subject1 in subjects1:
            if subject1 in clas.everyday_subjects and clas.count_subject(subject1,Time(time1.day,1),Time(time1.day,cfg.day_class_num))==1:
                failed_reasons1.add(f"规则冲突：{subject1} 每天至少排一节课")
                return False
        for subject2 in subjects2:
            # subject2 原本在 time2，要按 time2 所在的那天统计当天是否只剩这一节
            if subject2 in clas.everyday_subjects and clas.count_subject(subject2,Time(time2.day,1),Time(time2.day,cfg.day_class_num))==1:
                failed_reasons2.add(f"规则冲突：{subject2} 每天至少排一节课")
                return False

    # 两个半周课程：检查能否拼接
    if len(subjects1)==1 and subjects1[0] in clas.half_subjects and len(subjects2)==1 and subjects2[0] in clas.half_subjects and check(clas,time2.dou_week,subjects1[0],failed_reasons1,conflict_lessons,True):
        return True
    if time1 in clas.set_lessons:
        failed_reasons1.add(f"规则冲突：{time1} 必须排 {clas.set_lessons[time1]}")
        return False
    if time2 in clas.set_lessons:
        failed_reasons2.add(f"规则冲突：{time2} 必须排 {clas.set_lessons[time2]}")
        return False
    clas.remove_lesson(time1)
    clas.remove_lesson(time2)
    if len(subjects2)==1:
        check1=check(clas,time1,subjects2[0],failed_reasons2,conflict_lessons,True)
        check_merged(subjects2[0],time2,time1)
    else:
        check1=check(clas,time1.sin_week,subjects2[0],failed_reasons2,conflict_lessons,True)
        check_merged(subjects2[0],time2.sin_week,time1.sin_week)
        check2=check(clas,time1.dou_week,subjects2[1],failed_reasons2,conflict_lessons,True)
        check_merged(subjects2[1],time2.dou_week,time1.dou_week)
        check1=check1 and check2
    if len(subjects1)==1:
        check2=check(clas,time2,subjects1[0],failed_reasons1,conflict_lessons,True)
        check_merged(subjects1[0],time1,time2)
    else:
        check2=check(clas,time2.sin_week,subjects1[0],failed_reasons1,conflict_lessons,True)
        check_merged(subjects1[0],time1.sin_week,time2.sin_week)
        check3=check(clas,time2.dou_week,subjects1[1],failed_reasons1,conflict_lessons,True)
        check_merged(subjects1[1],time1.dou_week,time2.dou_week)
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
            failed_reasons1.add(f"规则冲突：交换后 {subject} 只能连堂 {clas.get_continue_times(subject)} 次（规则要求连堂 {clas.continue_num[subject]} 次） ")
    for subject in subjects2:
        if clas.get_continue_times(subject)<clas.continue_num[subject]:
            check_continue=False
            failed_reasons2.add(f"规则冲突：交换后 {subject} 只能连堂 {clas.get_continue_times(subject)} 次（规则要求连堂 {clas.continue_num[subject]} 次） ")
    clas.timetable[time1],clas.timetable[time2]=subjects1,subjects2
    return check1 and check2 and check_continue

class GenerateThread(QThread):
    finished_signal=Signal(set)  # 生成成功
    progress_signal=Signal(tuple)  # 进度信息

    def __init__(self,class_lst:list[Class],parent=None):
        super().__init__(parent)
        self.class_lst=class_lst
        self.last_progress_time=0  # 记录上次发送进度的时间
        self.progress_interval=0.8  # 进度更新间隔（秒）
        self.goto_lesson:tuple[Class,Time]|None=None
        self.skipped_lessons:set[tuple[Class,Time]]=set()
        self.teacher_fair_load:dict[Teacher,float]={}  # 每位老师的日均课时，用于负荷均摊
        self.subject_total:dict[Class,dict[Subject,int]]={}  # 每个班级各学科的周课时总数
        self.tried_times:dict[Class,dict[Time,int]]={clas:{Time(day,lesson):0 for day in range(1,6) for lesson in range(1,cfg.day_class_num+1)} for clas in self.class_lst}
        logging.debug("创建GenerateThread实例")

    def run(self):
        # 执行耗时的课程表生成逻辑
        try:
            logging.info("开始生成课程表...")
            start_time = time.time()
            
            logging.debug("重新初始化班级，填充固定课程")
            for clas in self.class_lst:
                clas.reset()
            # 统计每位老师一周的总课时，换算为"日均课时"
            # 排课时据此做教师负荷均摊，避免某位老师的课被全部挤到周四周五
            teacher_total:dict[Teacher,int]={}
            for clas in self.class_lst:
                subject_total:dict[Subject,int]={}
                for subject in clas.left_subjects:
                    teacher=clas.get_teacher(subject)
                    teacher_total[teacher]=teacher_total.get(teacher,0)+1
                    subject_total[subject]=subject_total.get(subject,0)+1
                self.subject_total[clas]=subject_total
            self.teacher_fair_load={teacher:max(total/5,1) for teacher,total in teacher_total.items()}
            for clas in self.class_lst:
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

    def sort_candidates(self,clas:Class,curr_time:Time,curr_subjects:list[Subject],curr_priority:list[Subject],order_leader_count:dict[Subject,int])->list[Subject]:
        """
        为本节点的候选学科计算权重并原地排序，权重越低越先尝试

        原先是在遍历候选学科的过程中增删列表元素，迭代顺序会错乱，
        部分学科会被一路甩到队尾，最终堆积在周四周五，这里改为先算权重再统一排序。

        :param clas: 当前班级
        :param curr_time: 当前时间
        :param curr_subjects: 候选学科列表
        :param curr_priority: 当前时间的优先学科（来自"优先排某学科"规则）
        :param order_leader_count: 保持教学进度学科 -> 范围内已排班级的最大课时数
        :return: 排序后的候选学科列表
        """
        remaining_days=5-curr_time.day+1
        # 本周内越靠近当前时间排过的学科越往后放，避免同一学科扎堆
        recent_used=clas.last_lesson_distance(curr_time) if cfg.average_subjects.value or clas.order_subjects_scope else {}
        day_load_cache:dict[Teacher,int]={}

        def _get_day_load(teacher:Teacher)->int:
            if teacher not in day_load_cache:
                day_load_cache[teacher]=teacher.day_load(curr_time.day)
            return day_load_cache[teacher]

        def _weight(subject:Subject)->float:
            teacher=clas.get_teacher(subject)
            left_num=clas.get_subject_left_num(subject)
            weight=0.0
            # 教师当天已排课时越接近（或超过）其日均课时，越往后放：
            # 前面的班级会先占满老师前几天的空档，若不在这里做均摊，
            # 后面班级的该老师就只剩周四周五可用，导致课程全部堆到周末
            weight+=_get_day_load(teacher)/self.teacher_fair_load.get(teacher,1)*60
            # 该学科最近刚排过则往后放，距离越近权重越高
            if subject in recent_used:
                weight+=30/(recent_used[subject]+1)
            # 减少连堂：该老师上一节已有课则往后放
            if cfg.reduce_continue.value and teacher.is_busy(curr_time.prev):
                weight+=15
            # 学科均摊：剩余课时多于剩余天数说明落后于进度，优先排
            if cfg.average_subjects.value and left_num>remaining_days:
                weight-=300
            # 每天至少一节：剩余天数刚好够时必须排
            if subject in clas.everyday_subjects and left_num>=remaining_days:
                weight-=500
            # 保持教学进度
            if subject in clas.order_subjects_scope:
                total=self.subject_total.get(clas,{}).get(subject,0)
                if total:
                    # 本班该学科相邻两个课时不能挨太近，
                    # 否则后序班级要在同样的时间窗里塞进同样多的课时，几乎必然无解
                    min_gap=min(cfg.day_class_num,max(2,5*cfg.day_class_num//total//2))
                    if subject in recent_used and recent_used[subject]+1<min_gap:
                        weight+=400
                    # 落后于进度时优先排，否则会被"进度差超过 1"的判断直接剪枝
                    placed=total-left_num
                    if subject in order_leader_count:
                        lag=order_leader_count[subject]-placed
                    else:
                        # 本班是排头兵，按时间均匀推进，别把课时挤在一起
                        elapsed=(curr_time.day-1)*cfg.day_class_num+curr_time.lesson-1
                        lag=total*elapsed/(5*cfg.day_class_num)-placed
                    if lag>0:
                        weight-=200+lag*60
            # 用户在指定时间设置的优先学科
            if subject in curr_priority:
                weight-=1000
            return weight

        curr_subjects.sort(key=_weight)
        return curr_subjects

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

                    # 保持教学进度：与范围内其他班级的进度差不能超过 1 个课时
                    # 该判断与候选学科无关，原先写在候选学科循环内，会对每个候选重复遍历整周；
                    # 这里提到排序前只算一次，既能提前剪枝省掉后续排序开销，又能顺带得到进度参照值
                    order_leader_count:dict[Subject,int]={}
                    for order_subject,scope in clas.order_subjects_scope.items():
                        clas_order_count=clas.count_subject(order_subject,end=curr_time)
                        leader:int=-1  # 范围内已排好班级的最大课时数，-1 表示还没有参照班级
                        for clas2 in scope:
                            if clas2.left_subjects:
                                continue
                            count=clas2.count_subject(order_subject,end=curr_time)
                            if count>clas_order_count+1:
                                return
                            if count>leader:
                                leader=count
                        if leader>=0:
                            order_leader_count[order_subject]=int(leader)

                    self.sort_candidates(clas,curr_time,curr_subjects,curr_priority,order_leader_count)

                    logging.debug(f"当前课程：{[i.name for i in curr_subjects]}")

                    for subject in curr_subjects:
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
                        # 并课
                        add_merged_classes=[]
                        for merged_classes in lesson_info.merged_lessons.get(subject,[]):
                            if clas not in merged_classes:
                                continue
                            for merged_class in merged_classes:
                                if merged_class==clas:
                                    continue
                                if not merged_class.get_subject_left_num(subject) or not check(merged_class,curr_time,subject,merged=True):
                                    return
                            for merged_class in merged_classes:
                                if merged_class!=clas:
                                    merged_class.add_lesson(curr_time,subject)
                                    add_merged_classes.append(merged_class)

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
                            for merged_class in add_merged_classes:
                                merged_class.remove_lesson(curr_time)
                    return
            if not last:
                if curr_time==Time(5,cfg.day_class_num):
                    self.dfs(self.class_lst[self.class_lst.index(clas)+1],Time(1,1))
                else:
                    self.dfs(clas,next_time)
            if last and not clas.left_subjects:
                self.finish=True
        except:
            e=traceback.format_exc()
            logging.critical(f"生成课程表出错：{clas} {curr_time}\n{e}")