"""
CSES 课表交换格式导出模块

将本程序的班级课表导出为 CSES（通用课程表交换格式，版本 2）YAML 文件。
规范见：https://github.com/SmartTeachCN/CSES

导出规则：
- 每个班级生成一个 .yaml 文件，文件名为班级名
- 周期固定为两周（周一至周五上课，周末休息），用于表达单双周交替课表
  - 第一周：第 1-5 个上课日（周一~周五）
  - 第二周：第 6-10 个上课日（周一~周五）
- 单双周课程（half_subjects）通过拆分为"星期X-单周 / 星期X-双周"两个日课表表示
- 无单双周交替的日期只生成一个日课表，enable_day 同时覆盖两周的对应上课日
"""
from __future__ import annotations

import re

from locals import *

# 周期定义：两周（每 5 个上课日 + 2 个休息日），可表达单双周交替
WORK_DAYS_PER_WEEK = 5
REST_DAYS_PER_WEEK = 2
CYCLE_WORK_COUNT = 10
CYCLE_REST_COUNT = 4

# 数字转星期名称
DAY_NAMES = ["", "星期一", "星期二", "星期三", "星期四", "星期五"]

# 需要加引号的 YAML 标量字符串特征
_QUOTE_RE = re.compile(r'^[\s\d\-?.,:\[\]{}#&*!|>%@`\'"]|:\s|#\s')
_QUOTED_KEYWORDS = {"null", "true", "false", "yes", "no", "on", "off", "y", "n"}


def clean_subject_name(name: str) -> str:
    """去除课程名中的【连】【单】【双】排课标记前缀"""
    for prefix in ["【连】", "【单】", "【双】"]:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def lesson_time_range(lesson: int) -> tuple[str, str]:
    """获取某节次的起止时间字符串（HH:MM:SS）"""
    start_h, start_m = cfg.lessons_time.value[str(lesson)][0]
    end_h, end_m = cfg.lessons_time.value[str(lesson)][1]
    return f"{start_h:02d}:{start_m:02d}:00", f"{end_h:02d}:{end_m:02d}:00"


def _get_class_teacher(clas: Class, subject: Subject) -> Teacher | None:
    """按课程名获取班级任课教师（兼容带【单】【双】【连】前缀的课程名）"""
    teacher = clas.teachers.get(subject.name)
    if teacher is None:
        teacher = clas.teachers.get(clean_subject_name(subject.name))
    return teacher


def _subject_weeks(clas: Class, time: Time, subject: Subject) -> tuple[bool, bool]:
    """
    返回 (单周是否有课, 双周是否有课)。

    对于单双周课程（half_subjects），通过教师 timetable 中 sin/dou 周的记录判断；
    普通课程两周都有课。
    """
    if subject in half_subjects:
        teacher = _get_class_teacher(clas, subject)
        if teacher is None:
            return False, False
        in_sin = any(c is clas and s is subject
                     for c, s in teacher.timetable[time.sin_week])
        return in_sin, not in_sin
    return True, True


def _scalar(value) -> str:
    """将标量值序列化为 YAML 标量字符串"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if s == "" or _QUOTE_RE.search(s) or s.lower() in _QUOTED_KEYWORDS:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def yaml_dump(data, indent: int = 0) -> str:
    """将 dict/list/标量 数据序列化为 YAML 文本（结构简单，无需 PyYAML 依赖）"""
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return pad + "{}"
        lines = []
        for key, value in data.items():
            key_str = _scalar(key)
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}{key_str}:")
                lines.append(yaml_dump(value, indent + 1))
            else:
                lines.append(f"{pad}{key_str}: {_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return pad + "[]"
        lines = []
        for item in data:
            if isinstance(item, dict):
                item_lines = []
                for idx, (k, v) in enumerate(item.items()):
                    prefix = f"{pad}- " if idx == 0 else f"{pad}  "
                    if isinstance(v, (dict, list)):
                        item_lines.append(f"{prefix}{_scalar(k)}:")
                        item_lines.append(yaml_dump(v, indent + 2))
                    else:
                        item_lines.append(f"{prefix}{_scalar(k)}: {_scalar(v)}")
                lines.append("\n".join(item_lines))
            elif isinstance(item, list):
                lines.append(f"{pad}-")
                lines.append(yaml_dump(item, indent + 1))
            else:
                lines.append(f"{pad}- {_scalar(item)}")
        return "\n".join(lines)
    return pad + _scalar(data)


def _collect_used_subjects(clas: Class) -> list[Subject]:
    """收集班级课表中实际使用的科目（按首次出现顺序去重）"""
    used: list[Subject] = []
    seen: set[Subject] = set()
    for day in range(1, 6):
        for lesson in range(1, cfg.day_class_num + 1):
            for subject in (clas.get_lessons(Time(day, lesson)) or []):
                if subject not in seen:
                    seen.add(subject)
                    used.append(subject)
    return used


def _build_subjects(clas: Class) -> list[dict]:
    subjects = []
    for subject in _collect_used_subjects(clas):
        name = clean_subject_name(subject.name)
        simplified = name
        for suffix in ("(0.5)", "（0.5）"):  # 忽略 0.5 课时标记后取首字作简化名
            if simplified.endswith(suffix):
                simplified = simplified[:-len(suffix)]
        entry = {"name": name, "simplified_name": simplified[0]}
        teacher = _get_class_teacher(clas, subject)
        if teacher:
            entry["teacher"] = teacher.name
        subjects.append(entry)
    return subjects


def _build_schedules(clas: Class) -> list[dict]:
    schedules = []
    for day in range(1, 6):
        sin_classes: list[tuple[int, Subject]] = []
        dou_classes: list[tuple[int, Subject]] = []
        for lesson in range(1, cfg.day_class_num + 1):
            time = Time(day, lesson)
            for subject in (clas.get_lessons(time) or []):
                in_sin, in_dou = _subject_weeks(clas, time, subject)
                if in_sin:
                    sin_classes.append((lesson, subject))
                if in_dou:
                    dou_classes.append((lesson, subject))

        def to_classes(items: list[tuple[int, Subject]]) -> list[dict]:
            return [
                {"subject": clean_subject_name(subject.name),
                 "start_time": lesson_time_range(lesson)[0],
                 "end_time": lesson_time_range(lesson)[1]}
                for lesson, subject in items
            ]

        sin_key = [(lesson, subject.name) for lesson, subject in sin_classes]
        dou_key = [(lesson, subject.name) for lesson, subject in dou_classes]
        if sin_key == dou_key:
            # 单双周一致（无非单双周课程），一个日课表覆盖两周对应天
            schedules.append({"name": DAY_NAMES[day],
                              "enable_day": [day, day + WORK_DAYS_PER_WEEK],
                              "classes": to_classes(sin_classes)})
        else:
            schedules.append({"name": f"{DAY_NAMES[day]}-单周",
                              "enable_day": [day],
                              "classes": to_classes(sin_classes)})
            schedules.append({"name": f"{DAY_NAMES[day]}-双周",
                              "enable_day": [day + WORK_DAYS_PER_WEEK],
                              "classes": to_classes(dou_classes)})
    return schedules


def _build_schedules_v1(clas: Class) -> list[dict]:
    """
    构建 CSES v1 日课表列表。

    v1 与 v2 的区别：
    - enable_day 为单个整数（1-7，周一~周日），而非两周上课日编号数组
    - 用 weeks 字段（all/odd/even）表达全周/单周/双周，而非拆成不同 enable_day
    """
    schedules = []
    for day in range(1, 6):
        sin_classes: list[tuple[int, Subject]] = []
        dou_classes: list[tuple[int, Subject]] = []
        for lesson in range(1, cfg.day_class_num + 1):
            time = Time(day, lesson)
            for subject in (clas.get_lessons(time) or []):
                in_sin, in_dou = _subject_weeks(clas, time, subject)
                if in_sin:
                    sin_classes.append((lesson, subject))
                if in_dou:
                    dou_classes.append((lesson, subject))

        def to_classes(items: list[tuple[int, Subject]]) -> list[dict]:
            return [
                {"subject": clean_subject_name(subject.name),
                 "start_time": lesson_time_range(lesson)[0],
                 "end_time": lesson_time_range(lesson)[1]}
                for lesson, subject in items
            ]

        sin_key = [(lesson, subject.name) for lesson, subject in sin_classes]
        dou_key = [(lesson, subject.name) for lesson, subject in dou_classes]
        if sin_key == dou_key:
            # 单双周一致（无非单双周课程），weeks=all
            schedules.append({"name": DAY_NAMES[day],
                              "enable_day": day,
                              "weeks": "all",
                              "classes": to_classes(sin_classes)})
        else:
            # 单双周不同，拆成 odd/even 两个日课表（enable_day 相同）
            schedules.append({"name": f"{DAY_NAMES[day]}-单周",
                              "enable_day": day,
                              "weeks": "odd",
                              "classes": to_classes(sin_classes)})
            schedules.append({"name": f"{DAY_NAMES[day]}-双周",
                              "enable_day": day,
                              "weeks": "even",
                              "classes": to_classes(dou_classes)})
    return schedules


def class_to_cses_v1(clas: Class, grade: str = "") -> dict:
    """将一个班级的课表转换为 CSES v1 格式字典（主流软件兼容）"""
    # subjects 的 name/simplified_name/teacher 字段 v1/v2 通用；v1 教室字段为 room（本程序暂无教室数据，省略）
    return {
        "version": 1,
        "subjects": _build_subjects(clas),
        "schedules": _build_schedules_v1(clas),
    }


def class_to_cses(clas: Class, grade: str = "") -> dict:
    """将一个班级的课表转换为 CSES v2 格式字典"""
    description = cfg.school_name.value
    if grade:
        description = f"{description} {grade}".strip()
    return {
        "version": 2,
        "configuration": {
            "name": f"{clas.name}课表",
            "description": description,
            "cycle": {
                "work_count": CYCLE_WORK_COUNT,
                "rest_count": CYCLE_REST_COUNT,
                "spans": [
                    {"activity": "work", "count": WORK_DAYS_PER_WEEK},
                    {"activity": "rest", "count": REST_DAYS_PER_WEEK},
                    {"activity": "work", "count": WORK_DAYS_PER_WEEK},
                    {"activity": "rest", "count": REST_DAYS_PER_WEEK},
                ],
            },
        },
        "subjects": _build_subjects(clas),
        "schedules": _build_schedules(clas),
    }


def export_cses_all_v1(dir_path: str) -> list[str]:
    """为所有班级导出 CSES v1 文件（主流软件兼容），返回导出的文件路径列表"""
    os.makedirs(dir_path, exist_ok=True)
    exported: list[str] = []
    for grade, class_names in cfg.grades_info.value.items():
        for class_name in class_names:
            clas = lesson_info.classes[class_name]
            data = class_to_cses_v1(clas, grade)
            file_path = os.path.join(dir_path, f"{class_name}.yaml")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(yaml_dump(data))
            exported.append(file_path)
            logging.info(f"已导出CSES v1课表：{file_path}")
    return exported


def export_cses_all(dir_path: str) -> list[str]:
    """为所有班级导出 CSES v2 文件，返回导出的文件路径列表"""
    os.makedirs(dir_path, exist_ok=True)
    exported: list[str] = []
    for grade, class_names in cfg.grades_info.value.items():
        for class_name in class_names:
            clas = lesson_info.classes[class_name]
            data = class_to_cses(clas, grade)
            file_path = os.path.join(dir_path, f"{class_name}.yaml")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(yaml_dump(data))
            exported.append(file_path)
            logging.info(f"已导出CSES课表：{file_path}")
    return exported


if __name__ == "__main__":
    # 命令行调试入口：python cses_core.py <输出目录>
    import sys
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "cses_out"
    files = export_cses_all(out_dir)
    print(f"已导出 {len(files)} 个 CSES 文件到 {out_dir}")
    for file_path in files:
        print(f"  - {file_path}")
