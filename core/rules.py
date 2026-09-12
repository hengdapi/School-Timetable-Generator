from __future__ import annotations
from locals import *

class RuleArg:
    def __init__(self,name,arg_type:str):
        """
        :param name: 参数名称
        :param arg_type: 参数类型（single单选，multi多选，int数字）
        """
        self.name=name
        self.type=arg_type

class Rule:
    type=""
    text=""
    desc=""
    args:dict[str,RuleArg]={}
    def __init__(self,scope:list[str]):
        self.scope=[lesson_info.classes[class_name] for class_name in scope]

    def __str__(self):
        ans=self.text.replace("|","").replace("{"," ").replace("}"," ")
        for string in self.__dict__:
            if string=="scope" or self.__dict__[string] is None:
                continue
            if isinstance(self.__dict__[string],list):
                ans=ans.replace(string,", ".join([str(x) for x in self.__dict__[string]]))
            else:
                ans=ans.replace(string,str(self.__dict__[string]))
        return ans

    def to_dict(self)->dict:
        ans:dict[str,list[str]|str]={"type":self.type,"scope":[clas.name for clas in self.scope]}
        for string in self.__dict__:
            if string=="scope" or self.__dict__[string] is None:
                continue
            if self.args[string].type=="multi":
                ans[string]=[str(x) for x in list(self.__dict__[string])]
            elif self.args[string].type=="single":
                ans[string]=str(self.__dict__[string])
            else:
                ans[string]=self.__dict__[string]
        return ans

    def __eq__(self, other):
        if not isinstance(other,Rule):
            return False
        return self.type==other.type and self.__dict__==other.__dict__
    
    def check_conflict(self,other:Rule)->bool:
        """
        检查是否与其他规则冲突
        :param other: 其他规则
        :return: 是否冲突
        """
        return True
    
    def validate(self)->bool:
        """
        检查规则自身是否合法
        :return: 是否合法
        """
        return True

class SetTimeRule(Rule):
    type="set_time"
    text="{times}|必须排|{subject}|学科"
    desc="必须在指定时间排指定学科的课程"
    args={"times":RuleArg("times","multi"),"subject":RuleArg("subject","single")}
    def __init__(self,scope:list[str],times:list[str],subject:str):
        super().__init__(scope)
        self.times=[Time(string=time_str) for time_str in times]
        self.subject=lesson_info.subjects.get(subject)

    def check_conflict(self,other:Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,(SetTimeRule,PriorityTimeRule)) and set(other.times)&set(self.times) or\
                isinstance(other,AvoidTimeRule) and set(other.times)&set(self.times) and self.subject in other.subjects:
            return False
        return True

class TeacherSetTimeRule(Rule):
    type="teacher_set_time"
    text="{teachers}|老师必须在|{times}|排课"
    desc="指定老师必须在指定时间排课"
    args={"teachers":RuleArg("teachers","multi"),"times":RuleArg("times","multi")}
    def __init__(self,scope:list[str],times: list[str],teachers:list[str]):
        super().__init__(scope)
        self.times=[Time(string=time_str) for time_str in times]
        self.teachers=[lesson_info.teachers.get(teacher_name) for teacher_name in teachers]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,(TeacherAvoidTimeRule,TeacherSetTimeRule)) and set(other.times)&set(self.times) and set(other.teachers)&set(self.teachers):
            return False
        return True

class AvoidTimeRule(Rule):
    type="avoid_time"
    text="{times}|不能排|{subjects}|学科"
    desc="指定时间不能排指定学科的课程，可用于空出学科教研的时间"
    args={"times":RuleArg("times","multi"),"subjects":RuleArg("subjects","multi")}
    def __init__(self,scope:list[str],times: list[str],subjects:list[str]):
        super().__init__(scope)
        self.times=[Time(string=time_str) for time_str in times]
        self.subjects=[lesson_info.subjects.get(subject_name) for subject_name in subjects]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,SetTimeRule) and other.subject in self.subjects and set(other.times)&set(self.times) or\
                isinstance(other,PriorityTimeRule) and set(other.times)&set(self.times) and set(other.subjects)&set(self.subjects):
            return False
        return True

class TeacherAvoidTimeRule(Rule):
    type="teacher_avoid_time"
    text="{teachers}|老师不能在|{times}|排课"
    desc="指定老师不能在指定时间排课"
    args={"teachers":RuleArg("teachers","multi"),"times":RuleArg("times","multi")}
    def __init__(self,scope:list[str],times: list[str],teachers:list[str]):
        super().__init__(scope)
        self.times=[Time(string=time_str) for time_str in times]
        self.teachers=[lesson_info.teachers.get(teacher_name) for teacher_name in teachers]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,TeacherSetTimeRule) and set(other.teachers)&set(self.teachers) and set(other.times)&set(self.times):
            return False
        return True

class PriorityTimeRule(Rule):
    type="priority_time"
    text="{times}|优先排|{subjects}|学科"
    desc="指定时间优先排指定学科的课程"
    args={"times":RuleArg("times","multi"),"subjects":RuleArg("subjects","multi")}
    def __init__(self,scope:list[str],times: list[str],subjects:list[str]):
        super().__init__(scope)
        self.times=[Time(string=time_str) for time_str in times]
        self.subjects=[lesson_info.subjects.get(subject_name) for subject_name in subjects]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,SetTimeRule) and set(other.times)&set(self.times) or\
            isinstance(other,AvoidTimeRule) and set(other.times)&set(self.times) and set(other.subjects)&set(self.subjects):
            return False
        return True

class SetNumRule(Rule):
    type="set_num"
    text="{subjects}|学科同一时间最多排|{number}|节课"
    desc=("指定学科同一时间最多排指定数量的课程，该规则可用于防止专业课教室冲突\n"
          "与下方“设置老师同时上课最大数量”不同的是，该规则限制的是同一学科、不同班级、不同教师在同一时间的最大排课数量")
    args={"number":RuleArg("number","int"),"subjects":RuleArg("subjects","multi")}
    def __init__(self,scope:list[str],number:int,subjects:list[str]):
        super().__init__(scope)
        self.number=number
        self.subjects=[lesson_info.subjects.get(subject_name) for subject_name in subjects]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,SetNumRule) and set(other.subjects)&set(self.subjects):
            return False
        return True

class AvoidSubjectRule(Rule):
    type="avoid_subject"
    text="{subjectsA}|学科与|{subjectsB}|学科不能排在同一时间"
    desc="指定的两门学科不能排在同一时间，该规则可用于防止专业课教室冲突"
    args={"subjectsA":RuleArg("subjectsA","multi"),"subjectsB":RuleArg("subjectsB","multi")}
    def __init__(self,scope:list[str],subjectsA:list[str],subjectsB:list[str]):
        super().__init__(scope)
        self.subjectsA=[lesson_info.subjects.get(subject_name) for subject_name in subjectsA]
        self.subjectsB=[lesson_info.subjects.get(subject_name) for subject_name in subjectsB]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,AvoidSubjectRule) and set(self.subjectsA)|set(self.subjectsB)==set(other.subjectsA)|set(other.subjectsB):
            return False
        return True

    def validate(self) ->bool:
        return not set(self.subjectsA)&set(self.subjectsB)

class AvoidTeacherRule(Rule):
    type="avoid_teacher"
    text="{teachersA}|老师与|{teachersB}|老师不能在同一时间排课"
    desc="指定的两位教师不能在同一时间排课"
    args={"teachersA":RuleArg("teachersA","multi"),"teachersB":RuleArg("teachersB","multi")}
    def __init__(self,scope:list[str],teachersA:list[str],teachersB:list[str]):
        super().__init__(scope)
        self.teachersA=[lesson_info.teachers.get(teacher_name) for teacher_name in teachersA]
        self.teachersB=[lesson_info.teachers.get(teacher_name) for teacher_name in teachersB]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,AvoidTeacherRule) and set(self.teachersA)|set(self.teachersB)==set(other.teachersA)|set(other.teachersB):
            return False
        return True

    def validate(self) ->bool:
        return not set(self.teachersA)&set(self.teachersB)

class SetContinueRule(Rule):
    type="set_continue"
    text="{subjects}|学科每周连堂|{number}|次"
    desc="指定学科每周连堂次数，如每周需要1节作文课，可设置语文课每周连堂1次"
    args={"number":RuleArg("number","int"),"subjects":RuleArg("subjects","multi")}
    def __init__(self,scope:list[str],number:int,subjects:list[str]):
        super().__init__(scope)
        self.number=number
        self.subjects=[lesson_info.subjects.get(subject_name) for subject_name in subjects]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,SetContinueRule) and set(self.subjects)&set(other.subjects):
            return False
        if isinstance(other,SubjectOrderRule) and set(self.subjects)&set(other.subjects):
            return False
        return True

class HalfNumRule(Rule):
    type="half_num"
    text="{subjects}|学科两周排一次课"
    desc="设置学科为单双周课程，用于缓解学科数量过多，可将优先级较低的学科设置为单双周课程"
    args={"subjects":RuleArg("subjects","multi")}
    def __init__(self,scope:list[str],subjects:list[str]):
        super().__init__(scope)
        self.subjects=[lesson_info.subjects.get(subject_name) for subject_name in subjects]

    def check_conflict(self,other: Rule):
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,HalfNumRule) and set(self.subjects)&set(other.subjects):
            return False
        return True

class SubjectOrderRule(Rule):
    type="subject_order"
    text="{subjects}|学科要保持范围内各班周内教学进度一致"
    desc="为指定学科排课时，保证范围内所有班级的第n课时都上完，才可以排第(n+1)课时"
    args={"subjects":RuleArg("subjects","multi")}
    def __init__(self,scope:list[str],subjects:list[str]):
        super().__init__(scope)
        self.subjects=[lesson_info.subjects.get(subject_name) for subject_name in subjects]

    def check_conflict(self,other:Rule) ->bool:
        if not set(other.scope)&set(self.scope):
            return True
        if isinstance(other,SubjectOrderRule) and set(self.subjects)&set(other.subjects):
            return False
        if isinstance(other,SetContinueRule) and set(self.subjects)&set(other.subjects):
            return False
        return True

class EverydaySubjectRule(Rule):
    type="everyday_subject"
    text="{subjects}|学科每天至少排一次课"
    desc="设置指定学科每天排一次课，一般设置主科每天排一次课"
    args={"subjects":RuleArg("subjects","multi")}
    def __init__(self,scope:list[str],subjects:list[str]):
        super().__init__(scope)
        self.subjects=[lesson_info.subjects.get(subject_name) for subject_name in subjects]

rule_types={
    "set_time": SetTimeRule,
    "avoid_time": AvoidTimeRule,
    "priority_time": PriorityTimeRule,
    "everyday_subject": EverydaySubjectRule,
    "set_num": SetNumRule,
    "avoid_subject": AvoidSubjectRule,
    "set_continue": SetContinueRule,
    "half_num": HalfNumRule,
    "subject_order": SubjectOrderRule,
    "avoid_teacher": AvoidTeacherRule,
    "teacher_avoid_time": TeacherAvoidTimeRule
}

def get_rule(**kwargs)->Rule:
    rule_type=kwargs["type"]
    del kwargs["type"]
    return rule_types[rule_type](**kwargs)

def apply_rules():
    """
    按 cfg.rules 重新应用全部规则到班级对象上（可重复调用）

    每次调用都会先清空上一条规则产生的副作用，再根据配置重新计算，
    所以在设置页增删改规则后直接调用本函数即可立刻生效。
    """
    for clas in lesson_info.classes.values():
        clas.set_lessons.clear()
        clas.priority_subjects.clear()
        clas.half_subjects.clear()
        clas.order_subjects_scope.clear()
        clas.everyday_subjects.clear()
        # continue_num 里每个学科都有默认值 0（解析课表时写入），不能清空，只能重置
        for subject in clas.continue_num:
            clas.continue_num[subject]=0
    lesson_info.rules=[]
    for rule_data in cfg.rules.value:
        rule=get_rule(**rule_data)
        lesson_info.rules.append(rule)
        for clas in rule.scope:
            if isinstance(rule,SetTimeRule):
                for rule_time in rule.times:
                    clas.set_lessons[rule_time]=rule.subject
            elif isinstance(rule,PriorityTimeRule):
                for rule_time in rule.times:
                    # 复制一份，避免多个班级共用同一个列表而相互污染
                    if rule_time not in clas.priority_subjects:
                        clas.priority_subjects[rule_time]=list(rule.subjects)
                    else:
                        clas.priority_subjects[rule_time].extend(rule.subjects)
            elif isinstance(rule,HalfNumRule):
                clas.half_subjects.update(rule.subjects)
            elif isinstance(rule,SetContinueRule):
                for subject in rule.subjects:
                    clas.continue_num[subject]=rule.number
            elif isinstance(rule,SubjectOrderRule):
                for subject in rule.subjects:
                    clas.order_subjects_scope[subject]=rule.scope
            elif isinstance(rule,EverydaySubjectRule):
                clas.everyday_subjects.update(rule.subjects)
    save_settings()

apply_rules()