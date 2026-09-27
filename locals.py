from __future__ import annotations

import copy
import sys
import webbrowser
from functools import total_ordering
from threading import Thread
from typing import Literal,Any

import pandas as pd
import requests
from PySide6.QtCore import QByteArray,QTimer,Qt,QThread,QUrl
from PySide6.QtGui import QImage,QTextDocument
from packaging import version

from style import *
from wr_settings import *

with open("app_version.txt","r",encoding="utf-8") as f:
    app_version=f.read()
logging.basicConfig(format="[%(levelname)s] %(asctime)s %(filename)s %(funcName)s %(lineno)d行:\t%(message)s",
                    level=logging.INFO,
                    filename=None,
                    encoding="utf-8")

if os.path.exists("log.txt"):
    log_file_size=os.path.getsize("log.txt")
else:
    log_file_size=0
file_handler = logging.FileHandler("log.txt", mode="a" if log_file_size<=10*1024*1024 else "w", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s %(filename)s %(funcName)s %(lineno)d行:\t%(message)s"))
logging.getLogger().addHandler(file_handler)

logging.info("\n\n"+"="*60)
logging.info(f"程序开始启动")
appdata=os.path.join(os.environ["APPDATA"],"School-Timetable-Generator")
gitcode_url="https://gitcode.com/hengdapi/School-Timetable-Generator"
github_url="https://github.com/hengdapi/School-Timetable-Generator"

class CheckUpdateThread(QThread):
    """检查更新线程：网络请求在子线程执行，避免阻塞 UI"""
    has_update=Signal(dict)   # 发现新版本，携带 release 数据
    no_update=Signal()        # 无新版本
    error=Signal(str)         # 检查出错

    def run(self):
        try:
            url="https://api.gitcode.com/api/v5/repos/2603_96523924/School-Timetable-Generator/releases/latest"

            payload={}
            headers={
                'Accept':'application/json'
            }

            response=requests.get(url,headers=headers,data=payload,timeout=10).json()
            logging.debug(f"检查更新api返回内容：{response}")

            if version.parse(response["tag_name"])<=version.parse(app_version):
                self.no_update.emit()
            else:
                self.has_update.emit(response)
        except Exception as err:
            e=traceback.format_exc()
            logging.critical(f"检查更新出错：\n{e}")
            self.error.emit(str(err))

class MarkdownBrowser(TextBrowser):
    """支持异步加载远程图片的 Markdown 浏览器（不依赖 QtWebEngine）

    QTextDocument 排版遇到图片时会回调 loadResource()，默认实现不会发起网络请求，
    这里用 requests 在子线程下载后回填资源，再触发重新排版。
    视频/音频无法在文本控件中播放，会以链接形式展示（点击用浏览器打开）。
    """

    image_loaded=Signal(str,QByteArray)   # 图片下载完成：子线程 → 主线程

    def __init__(self,parent=None,base_url:str=""):
        super().__init__(parent)
        self.base_url=base_url     # 用于解析相对路径的图片地址
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setStyleSheet("background-color:transparent; border: none;")
        self._image_cache:dict[str,QImage]={}
        self._pending:set[str]=set()
        self._threads:list[Thread]=[]
        self.image_loaded.connect(self._on_image_loaded)

    def loadResource(self,resource_type,url):
        """文档需要资源时回调：远程图片改为异步下载，下载完成前返回占位"""
        if int(resource_type)!=int(QTextDocument.ResourceType.ImageResource):
            return super().loadResource(resource_type,url)

        full_url=self._resolve(url)
        key=full_url.toString()
        if key in self._image_cache:
            return self._image_cache[key]
        if full_url.scheme() in ("http","https") and key not in self._pending:
            self._pending.add(key)
            thread=Thread(target=self._download,args=(key,),daemon=True)
            self._threads.append(thread)   # 持有引用，防止线程被提前回收
            thread.start()
        return super().loadResource(resource_type,full_url)

    def _resolve(self,url)->QUrl:
        """把相对路径按 release 页面地址补全"""
        if url.isRelative() and self.base_url:
            return QUrl(self.base_url).resolved(url)
        return url

    def _download(self,url:str):
        try:
            data=requests.get(url,headers={"User-Agent":"Mozilla/5.0"},timeout=15).content
            self.image_loaded.emit(url,QByteArray(data))
        except RuntimeError:
            pass      # 控件已销毁，忽略
        except Exception as err:
            logging.warning(f"加载更新日志图片失败：{url}，{err}")

    def _on_image_loaded(self,url:str,data:QByteArray):
        image=QImage()
        if not image.loadFromData(data):
            logging.warning(f"更新日志图片格式无法识别：{url}")
            return
        if image.width()>440:
            image=image.scaledToWidth(440,Qt.TransformationMode.SmoothTransformation)
        self._image_cache[url]=image
        self.document().addResource(QTextDocument.ResourceType.ImageResource,QUrl(url),image)
        # 强制重新排版，让图片占位替换为真实图片
        self.document().markContentsDirty(0,self.document().characterCount())

class UpdateMessageBox(MessageBoxBase):
    """更新详情对话框：展示新版本的更新日志，用户可选择下载更新或暂不更新"""

    def __init__(self, response: dict, parent=None):
        super().__init__(parent=parent)
        self.response=response
        tag_name=response.get("tag_name","未知版本")
        body=response.get("body","") or "暂无更新说明"

        self.title_label=subheader(f"发现新版本 {tag_name}",self,self.viewLayout,0)
        write("更新内容如下：",self,self.viewLayout,10)

        self.change_log=MarkdownBrowser(self,f"{gitcode_url}/releases/{tag_name}")
        self.change_log.setFixedSize(600,min(max(round(len(body)/16*25),120),400))
        # release 说明可能直接贴 HTML（含 <img>/<video>），Markdown 渲染器不解析 HTML 标签，故做兜底
        if any(tag in body.lower() for tag in ("<img","<video","<source")):
            self.change_log.setHtml(body)
        else:
            self.change_log.setMarkdown(body)
        self.viewLayout.addWidget(self.change_log)

        self.yesButton.setText("下载更新")
        self.yesButton.setIcon(FluentIcon.DOWNLOAD)
        self.cancelButton.setText("暂不更新")

        # 在浏览器中查看：不关闭对话框，方便用户对照
        self.view_in_browser_button=PushButton(FluentIcon.LINK,"在浏览器中查看",self.buttonGroup)
        self.view_in_browser_button.clicked.connect(lambda:webbrowser.open(f"{gitcode_url}/releases/{tag_name}"))
        # 插在「下载更新」之后，保持「下载更新」位于最左侧
        self.buttonLayout.insertWidget(1,self.view_in_browser_button,1,Qt.AlignmentFlag.AlignVCenter)

        self.widget.setMinimumWidth(540)

def _close_update_notification(window):
    """安全关闭更新提醒通知（可能已被用户手动关闭或销毁）"""
    toast=getattr(window,"update_msg",None)
    window.update_msg=None
    if toast is None:
        return
    try:
        toast.close()
    except RuntimeError:
        pass

def _show_update_detail(window,response:dict):
    """弹出显示更新日志的消息框，用户可选择下载更新或暂不更新"""
    try:
        _close_update_notification(window)
        dialog=UpdateMessageBox(response,window)
        if dialog.exec():
            download_update(window,response)
        else:
            logging.info("用户选择暂不更新")
    except Exception as err:
        e=traceback.format_exc()
        logging.critical(f"显示更新详情出错：\n{e}")
        show_error(window,err)

def _show_update_notification(window,response:dict):
    """在主线程弹出新版本通知（由 CheckUpdateThread 信号触发，只显示版本号和查看详情按钮）"""
    try:
        logging.info(f"发现新版本：{response['tag_name']}")
        _close_update_notification(window)

        tag_name=response.get("tag_name","未知版本")
        toast=Toast.info("发现新版本",f"新版本 {tag_name} 现已发布，可查看更新详情",duration=-1,parent=window)
        window.update_msg=toast

        view_update_button=PushButton()
        view_update_button.setIcon(FluentIcon.INFO)
        view_update_button.setText("查看详细信息")
        view_update_button.clicked.connect(lambda:_show_update_detail(window,response))
        toast.addWidget(view_update_button,alignment=Qt.AlignmentFlag.AlignLeft)
        toast.show()
    except Exception as err:
        e=traceback.format_exc()
        logging.critical(f"检查更新出错：\n{e}")
        show_error(window,err)

def check_update(window,show_no_update=False):
    """检查更新：网络请求在子线程执行，不阻塞 UI"""
    check_thread=CheckUpdateThread(window)
    window.check_update_thread=check_thread  # 持有引用，防止被垃圾回收
    check_thread.has_update.connect(lambda response:_show_update_notification(window,response))
    check_thread.no_update.connect(lambda:Toast.info("无可用更新",f"当前已是最新版本：{app_version}",duration=3000,parent=window) if show_no_update else None)
    check_thread.error.connect(lambda err:show_error(window,err))
    check_thread.start()

class UpdateThread(Thread):
    def __init__(self,response:dict):
        super().__init__()
        self.response=response

    def run(self):
        try:
            logging.info("开始下载更新")
            download_url=None
            for asset in self.response["assets"]:
                if asset["name"].endswith("Setup.exe"):
                    download_url:str=asset.get("browser_download_url")
                    break
            if download_url is None:
                logging.error("未找到安装包")
                return
            logging.info(f"找到最新版本，开始从 {download_url} 下载")

            r = requests.get(download_url,stream=True)
            with open("update.exe", "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            logging.info("下载完成，自动运行安装包update.exe")
            os.startfile("update.exe")
        except Exception:
            e=traceback.format_exc()
            logging.critical(f"下载更新出错：\n{e}")

def download_update(window,response:dict):
    try:
        _close_update_notification(window)
        Toast.info("正在后台下载更新","下载完成后将为您自动运行安装包",duration=3000,parent=window)
        update_thread=UpdateThread(response)
        logging.debug("更新线程已创建")
        update_thread.start()
    except Exception as err:
        e=traceback.format_exc()
        logging.critical(f"下载更新出错：\n{e}")
        show_error(window,err)

def lesson2str(lesson):
    """
    根据课程节次生成时间描述

    :param lesson: 课程节次
    :return: 时间描述（如"上午第1节"）
    """
    # 判断课程是在上午还是下午
    if lesson<=cfg.morning_class_num.value:
        time="上午"
    else:
        time="下午"
        # 调整课程节次为下午的相对节次
        lesson-= cfg.morning_class_num.value

    return f"{time}第{lesson}节"

def str2subject(subject_name:str)->Subject:
    """
    去除前缀，查找 Subject 对象
    """
    clean_name=subject_name
    for prefix in ["【连】","【单】","【双】"]:
        if clean_name.startswith(prefix):
            clean_name=clean_name[len(prefix):]
            break
    return lesson_info.subjects[clean_name]

def show_error(page,error:Exception):
    Toast.error("发生错误",str(error)+"\n错误信息已存入日志，可通过首页按钮反馈",duration=-1,parent=page)

def restart_app(delay_ms=100):
    """重启程序"""
    logging.info(f'重启程序，sys.executable:{sys.executable}，sys.argv:{sys.argv}')

    def _restart():
        app=QApplication.instance()
        if app:
            app.quit()
            app.processEvents()
        os.execl(sys.executable,sys.executable,*sys.argv)

    QTimer.singleShot(delay_ms,_restart)

def is_special(subject:str):
    """
    判断给定的课程名称是否为特殊课程

    :param subject: 课程名称
    :return: 如果课程是特殊课程，则返回True；否则返回False
    """
    return subject.endswith("(0.5)") or subject.endswith("（0.5）")

# 定义工作日列表
days = ["","星期一", "星期二", "星期三", "星期四", "星期五"]

def display_df_in_table(table_widget: TableWidget|QTableWidget, df: pd.DataFrame):
    table_widget.clear()
    df.columns=df.columns.astype(str)
    # 设置行数和列数
    table_widget.setRowCount(df.shape[0])
    table_widget.setColumnCount(df.shape[1])

    # 设置表头
    table_widget.setHorizontalHeaderLabels(df.columns)
    table_widget.setVerticalHeaderLabels([str(idx) for idx in df.index])

    # 填充数据
    for i in range(df.shape[0]):
        for j in range(df.shape[1]):
            if str(df.iat[i, j]) in ["nan","None"]:
                continue
            item = QTableWidgetItem(str(df.iat[i, j]))
            item.setTextAlignment(Qt.AlignCenter)
            table_widget.setItem(i, j, item)

def table_style(content=None)->pd.DataFrame:
    table_style={}
    for day in days[1:]:
        table_style[day]={}
        for lesson in range(1,cfg.morning_class_num.value+1):
            table_style[day][f"上午第{lesson}节"]=content
        for lesson in range(1,cfg.afternoon_class_num.value+1):
            table_style[day][f"下午第{lesson}节"]=content
    return pd.DataFrame(table_style)

def class_total_dataframe()->pd.DataFrame:
    data={}
    for clas in lesson_info.class_lst:
        data[clas.name]={}
        timetable=clas.timetable_dataframe.to_dict()
        for day,lessons in timetable.items():
            for time,lesson in lessons.items():
                data[clas.name][day+time]=lesson
    return pd.DataFrame(data).transpose()

def teacher_total_dataframe()->pd.DataFrame:
    data={}
    for teacher in lesson_info.teacher_lst:
        data[teacher.name]={}
        timetable=teacher.timetable_dataframe.to_dict()
        for day,lessons in timetable.items():
            for time,lesson in lessons.items():
                data[teacher.name][day+time]=lesson
    dataframe=pd.DataFrame(data).transpose()
    dataframe=dataframe[[str(Time(day,lesson)) for day in range(1,6) for lesson in range(1,cfg.day_class_num+1)]]
    return dataframe

@total_ordering
class Time:
    def __init__(self,day:int=0,lesson:int=0,week:Literal["sin","dou","all"]="all",string:str|None=None):
        if string:
            if "【单】" in string:
                self.week="sin"
                string=string.replace("【单】","")
            elif "【双】" in string:
                self.week="dou"
                string=string.replace("【双】","")
            else:
                self.week="all"
            self.day=days.index(string[:3])
            self.lesson=int(string[6:-1])
            if "下午" in string:
                self.lesson+=cfg.morning_class_num.value
        else:
            self.day=day
            self.lesson=lesson
            self.week=week
        self.sin=(self.week=="sin")
        self.dou=(self.week=="dou")
        self.all=(self.week=="all")
        self.half=not self.all
    def __eq__(self, other):
        if not isinstance(other,Time):
            return False
        return self.day==other.day and self.lesson==other.lesson and self.week==other.week
    def __lt__(self, other):
        if not isinstance(other,Time):
            return False
        if self.day!=other.day:
            return self.day<other.day
        return self.lesson<other.lesson
    def __hash__(self):
        return hash((self.day,self.lesson,self.week))
    def __str__(self):
        return {"sin":"【单】","dou":"【双】","all":""}[self.week]+days[self.day]+lesson2str(self.lesson)

    def to_str(self,day:bool,lesson:bool,week:bool=False):
        string=""
        if week:
            string+={"sin":"【单】","dou":"【双】","all":""}[self.week]
        if day:
            string+=days[self.day]
        if lesson:
            string+=lesson2str(self.lesson)
        return string

    @property
    def sin_week(self):
        return Time(self.day,self.lesson,"sin")
    @property
    def dou_week(self):
        return Time(self.day,self.lesson,"dou")
    @property
    def all_week(self):
        return Time(self.day,self.lesson,"all")

    @property
    def next(self):
        next_time=self.all_week
        if self.lesson==cfg.day_class_num:
            if self.day==5:
                next_time.day=next_time.lesson=1
            else:
                next_time.day+=1
                next_time.lesson=1
        else:
            next_time.lesson+=1
        return next_time

    @property
    def prev(self):
        prev_time=self.all_week
        if self.lesson==1:
            if self.day==1:
                prev_time.day=5
                prev_time.lesson=cfg.day_class_num
            else:
                prev_time.day-=1
                prev_time.lesson=cfg.day_class_num
        else:
            prev_time.lesson-=1
        return prev_time

class Teacher:
    """
    教师类，用于管理教师的课程时间
    """
    def __init__(self, name:str):
        """
        初始化教师对象

        :param name: 教师姓名
        """
        self.name = name
        self.subjects:set[Subject]=set()
        self.left_num:dict[Subject,dict[Time,int]]={}
        self.timetable:dict[Time,list[tuple[Class,Subject]]]={Time(day,lesson,week):[] for day in range(1,6) for lesson in range(1,cfg.day_class_num+1) for week in ["sin","dou","all"]}  # 记录教师已占用的课程时间

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if not isinstance(other, Teacher):
            return False
        return self.name==other.name

    def __hash__(self):
        return hash(self.name)

    def add_lesson(self,time:Time,clas:Class,subject:Subject):
        """
        添加教师的课程时间
        """
        self.timetable[time].append((clas,subject))
        self.timetable[time].sort(key=lambda x:lesson_info.class_lst.index(x[0]))
        self.left_num[subject][time]-=1

    def get_lessons(self,time:Time):
        return self.timetable[time]

    def is_busy(self,time:Time):
        """
        检查教师在特定时间是否有课
        :return: 是否有课
        """
        if time.all:
            return self.timetable[time.dou_week] or self.timetable[time.sin_week] or self.timetable[time.all_week]
        elif time.sin:
            return self.timetable[time.sin_week] or self.timetable[time.all_week]
        else:
            return self.timetable[time.dou_week] or self.timetable[time.all_week]

    def check(self,time:Time,subject:Subject,failed_reasons:set|None=None,conflict_lessons:set|None=None)->bool:
        res=True
        if not self.is_busy(time):
            return True
        if self.left_num[subject][time]<=0 or not self.timetable[time] or self.timetable[time][0][1]!=subject:
            res=False
            if failed_reasons is None:
                return False
            for conflict_time in (time.sin_week,time.dou_week,time.all_week) if time.all else (time,time.all_week):
                if not self.get_lessons(conflict_time):
                    continue
                for conflict_class,conflict_subject in self.get_lessons(conflict_time):
                    failed_reasons.add(f"课程冲突：{subject} 的任课老师 {self} 在 {conflict_time} 有 {conflict_class} 的 {conflict_subject} 课")
                    conflict_lessons.add((conflict_class,conflict_time))
        return res

    def remove_lesson(self,time:Time,clas:Class|None=None):
        """
        移除教师在特定时间上的课程
        """
        for lessons in self.timetable[time]:
            if lessons[0]==clas or not clas:
                self.left_num[lessons[1]][time]+=1
                self.timetable[time].remove(lessons)

    @property
    def timetable_dataframe(self)->pd.DataFrame:
        data=copy.deepcopy(table_style())
        for time,lessons in self.timetable.items():
            for lesson in lessons:
                if data.loc[time.to_str(False,True),time.to_str(True,False)]:
                    lines=data.loc[time.to_str(False,True),time.to_str(True,False)].split("\n")
                    lines[0]+=f"/{time.to_str(False,False,True)}{lesson[0]}"
                    lines[1]+=f"/{time.to_str(False,False,True)}{lesson[1]}"
                    data.loc[time.to_str(False,True),time.to_str(True,False)]="\n".join(lines)
                else:
                    data.loc[time.to_str(False,True),time.to_str(True,False)]=f"{time.to_str(False,False,True)}{lesson[0]}\n{time.to_str(False,False,True)}{lesson[1]}"
        return data

class Subject:
    def __init__(self, name:str):
        """
        初始化课程对象

        :param name: 课程名称
        """
        self.name = name
        self.time_list:dict[Time,int]={Time(day,lesson):0 for day in range(1,6) for lesson in range(1,cfg.day_class_num+1)}
        self.timetable:dict[Time,list[Class]]={Time(day,lesson):[] for day in range(1,6) for lesson in range(1,cfg.day_class_num+1)}

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if not isinstance(other,Subject):
            return False
        return self.name == other.name

    def __hash__(self):
        return hash(self.name)

    def get_time_num(self,time:Time):
        return self.time_list[time]

    def add_lesson(self,clas:Class,time:Time):
        self.time_list[time]+=1
        self.timetable[time].append(clas)

    def remove_lesson(self,clas:Class,time:Time):
        self.time_list[time]-=1
        self.timetable[time].remove(clas)

    def timetable_dataframe(self,class_scope:list[Class]) -> pd.DataFrame:
        data=copy.deepcopy(table_style())
        for time,classes in self.timetable.items():
            for clas in classes:
                if clas not in class_scope:
                    continue
                if data.loc[time.to_str(False,True),time.to_str(True,False)]:
                    lines=data.loc[time.to_str(False,True),time.to_str(True,False)].split("\n")
                    lines[0]+=f"/{time.to_str(False,False,True)}{clas}"
                    lines[1]+=f"/{time.to_str(False,False,True)}{clas.get_teacher(self)}"
                    data.loc[time.to_str(False,True),time.to_str(True,False)]="\n".join(lines)
                else:
                    data.loc[time.to_str(False,True),time.to_str(True,False)]=f"{time.to_str(False,False,True)}{clas}\n{time.to_str(False,False,True)}{clas.get_teacher(self)}"
        return data

class Class:
    def __init__(self,name,teachers:dict[str,Teacher]):
        """
        初始化班级对象

        :param name: 班级名称
        :param teachers: 班级任课教师列表({学科:老师})
        """
        self.name=name
        self.grade=None
        self.teachers=teachers
        self.timetable:dict[Time,list[Subject]]={Time(day,lesson):[] for day in range(1,6) for lesson in range(1,cfg.day_class_num+1)}
        self.left_subjects:list[Subject]=[]

        self.priority_subjects: dict[Time,list[Subject]]={}
        self.half_subjects: set[Subject]=set()
        self.continue_num: dict[Subject,int]={}
        self.set_lessons: dict[Time,Subject]={}
        self.order_subjects_scope: dict[Subject,list[Class]]={}
        self.everyday_subjects: set[Subject]=set()

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __json__(self):
        timetable={}
        for time,subjects in self.timetable.items():
            timetable[str(time)]=[subject.name for subject in subjects]
        return timetable

    def reset(self):
        for day in range(1,6):
            for lesson in range(1,cfg.day_class_num+1):
                self.remove_lesson(Time(day,lesson))

    def get_teacher(self,subject:Subject):
        return self.teachers[subject.name]

    def get_subject_left_num(self,subject:Subject)->int:
        return self.left_subjects.count(subject)

    def add_lesson(self,time:Time,subject:Subject):
        if subject in self.half_subjects and time.all:
            if not self.get_lessons(time):
                time=time.sin_week
            else:
                time=time.dou_week
        logging.debug(f"在 {self.name} 的 {time} 安排 {subject}")
        self.get_teacher(subject).add_lesson(time,self,subject)
        time=time.all_week
        if time in self.timetable:
            self.timetable[time].append(subject)
        else:
            self.timetable[time]=[subject]
        subject.add_lesson(self,time)
        self.left_subjects.remove(subject)

    def remove_lesson(self,time:Time):
        subjects=self.get_lessons(time)
        if subjects:
            if time.all and len(subjects)==2:
                self.remove_lesson(time.dou_week)
                self.remove_lesson(time.sin_week)
                return
            if len(subjects)==1 and subjects[0] in self.half_subjects:
                time=time.sin_week
            if time.sin or time.all:
                subject=subjects[0]
            elif len(subjects)==2:
                subject=subjects[1]
            else:
                return
            logging.debug(f"删除 {self} {time} 的 {subject}")
            self.get_teacher(subject).remove_lesson(time,self)
            time=time.all_week
            self.timetable[time].remove(subject)
            subject.remove_lesson(self,time)
            self.left_subjects.append(subject)

    def get_lessons(self,time:Time)->list[Subject]|None:
        return copy.copy(self.timetable.get(time.all_week))

    def exchange_lessons(self,time1:Time,time2:Time):
        subjects1=self.get_lessons(time1)
        subjects2=self.get_lessons(time2)
        if not subjects1 or not subjects2:
            return
        if len(subjects1)==1 and subjects1[0] in self.half_subjects and len(subjects2)==1 and subjects2[0] in self.half_subjects:
            self.remove_lesson(time1.sin_week)
            self.add_lesson(time2.dou_week,subjects1[0])
        else:
            # 先从两个位置移除
            self.remove_lesson(time1)
            self.remove_lesson(time2)
            # 把源课程放入目标位置
            if len(subjects1)==1:
                self.add_lesson(time2,subjects1[0])
            else:
                self.add_lesson(time2.sin_week,subjects1[0])
                self.add_lesson(time2.dou_week,subjects1[1])
            # 把目标课程放入源位置（真正的交换）
            if len(subjects2)==1:
                self.add_lesson(time1,subjects2[0])
            else:
                self.add_lesson(time1.sin_week,subjects2[0])
                self.add_lesson(time1.dou_week,subjects2[1])

    def get_continue_times(self,subject:Subject) -> int:
        """
        获取本班某学科的连堂次数
        """
        times=0
        for time,subjects in self.timetable.items():
            if subjects!=[subject]:
                continue
            if time.lesson!=1 and (cfg.allow_noon_continuous.value or time.lesson!=cfg.morning_class_num.value+1):
                if self.get_lessons(time.prev)==[subject]:
                    times+=1
        return times

    def count_subject(self,subject:Subject,start:Time=Time(1,1),end:Time=Time(5,cfg.day_class_num)):
        cnt=0
        time=start
        while time<=end:
            subjects=self.get_lessons(time)
            if subjects:
                cnt+=subjects.count(subject)
            time=time.next
            if time==Time(1,1):
                break
        return cnt

    @property
    def empty(self)->bool:
        for time,subjects in self.timetable.items():
            if subjects:
                return False
        return True

    @property
    def timetable_dataframe(self)->pd.DataFrame:
        data=copy.deepcopy(table_style())
        for time,subjects in self.timetable.items():
            if len(subjects)==1:
                subject=subjects[0]
                data.loc[time.to_str(False,True),time.to_str(True,False)]=str(subject)
                if cfg.show_teachers.value:
                    data.loc[time.to_str(False,True),time.to_str(True,False)]+=f"\n{self.get_teacher(subject)}"
            elif len(subjects)==2:
                data.loc[time.to_str(False,True),time.to_str(True,False)]=f"【单】{subjects[0]}/"
                data.loc[time.to_str(False,True),time.to_str(True,False)]+=f"【双】{subjects[1]}"
                if cfg.show_teachers.value:
                    data.loc[time.to_str(False,True),time.to_str(True,False)]+=f"\n【单】{self.get_teacher(subjects[0])}/"
                    data.loc[time.to_str(False,True),time.to_str(True,False)]+=f"【双】{self.get_teacher(subjects[1])}"
        return data

class Grade:
    def __init__(self,name,classes:list[Class]):
        self.name=name
        self.classes=classes

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, value: object, /) -> bool:
        if not isinstance(value,Grade):
            return False
        return self.name == value.name

class LessonInfoEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if hasattr(o, "__json__"):
            return o.__json__()
        return super().default(o)

# 解析课程信息
class LessonInfo:
    def __init__(self):
        self.teachers: dict[str,Teacher]={}
        self.teacher_names:list[str]=cfg.teachers_info.value
        self.subjects: dict[str,Subject]={}
        self.subject_names:list[str]=cfg.subjects_info.value
        self.classes: dict[str,Class]={}
        self.class_names:list[str]=[]
        self.class_lst:list[Class]=[]
        self.grades:dict[str,Grade]={}
        self.saved=True
        logging.info("正在解析课程信息...")
        lessons=cfg.lessons_info.value
        
        logging.debug(f"课程信息：{len(lessons)}个班级，{len(self.subject_names)}个科目，{len(self.teacher_names)}个老师")
        
        for subject in self.subject_names:
            self.subjects[subject]=Subject(subject)
        logging.debug(f"已创建 {len(self.subjects)} 个科目对象")

        for teacher in self.teacher_names:
            self.teachers[teacher]=Teacher(teacher)
        logging.debug(f"已创建 {len(self.teachers)} 个教师对象")
        
        for idx, clas in enumerate(lessons):
            class_name=clas["班级"]
            self.classes[class_name]=Class(class_name,{})
            total_lessons=0
            for subject in self.subject_names:
                if clas[subject+" - 任课老师"]:
                    self.classes[class_name].teachers[subject]=self.teachers[clas[subject+" - 任课老师"]]
                    self.teachers[clas[subject+" - 任课老师"]].subjects.add(self.subjects[subject])
                    max_num=cfg.teachers_max_num.value.get(clas[subject+" - 任课老师"],{}).get(subject,1)
                    self.teachers[clas[subject+" - 任课老师"]].left_num[self.subjects[subject]]={Time(day,lesson,week):max_num for day in range(1,6) for lesson in range(1,cfg.day_class_num+1) for week in ["sin","dou","all"]}
                    lesson_count=int(clas[subject+" - 课时"])
                    for i in range(lesson_count):
                        self.classes[class_name].left_subjects.append(self.subjects[subject])
                    self.classes[class_name].continue_num[self.subjects[subject]]=0
                    total_lessons+=lesson_count
            logging.debug(f"解析班级 {idx+1}/{len(lessons)}：{len(self.classes[class_name].teachers)} 位任课老师，{total_lessons} 节课")

        for grade_name,grade_classes in cfg.grades_info.value.items():
            self.grades[grade_name]=Grade(grade_name,[])
            for class_name in grade_classes:
                self.grades[grade_name].classes.append(self.classes[class_name])
                self.classes[class_name].grade=self.grades[grade_name]

        self.class_names=list(self.classes.keys())
        self.class_lst=list(self.classes.values())
        self.teacher_lst=list(self.teachers.values())
        self.subject_lst=list(self.subjects.values())
        self.grade_names=list(self.grades.keys())
        self.grade_lst=list(self.grades.values())
        sys.setrecursionlimit(max(len(self.classes)*5*cfg.day_class_num*2,1000))

        for teacher in self.teacher_lst:
            if teacher.name not in cfg.teachers_max_num.value:
                cfg.teachers_max_num.value[teacher.name]={}
            for subject in teacher.subjects:
                if subject.name not in cfg.teachers_max_num.value[teacher.name]:
                    cfg.teachers_max_num.value[teacher.name][subject.name]=1
        save_settings()
        logging.debug("课程信息解析完成")
lesson_info=LessonInfo()

logging.info("课程信息解析完毕，生成初始化完成")

def diff_cfg(new_classes:list,new_teachers:list,new_subjects:list)->tuple[set,set,set]:
    old_classes=set(lesson_info.class_names)
    diff_classes=old_classes-set(new_classes)
    diff_teachers=set(lesson_info.teachers)-set(new_teachers)
    diff_subjects=set(lesson_info.subjects)-set(new_subjects)
    return diff_classes,diff_teachers,diff_subjects

def del_cfg_diff(diff_classes:set,diff_teachers:set,diff_subjects:set)->None:
    for grade,classes in cfg.grades_info.value.items():
        cfg.grades_info.value[grade]=list(set(classes)-diff_classes)
        cfg.grades_info.value[grade].sort(key=lambda clas:lesson_info.class_names.index(clas))
    new_rules=[]
    for rule in cfg.rules.value:
        flag=True
        for arg,value in rule.items():
            if isinstance(value,list):
                value=list(set(value)-diff_classes-diff_teachers-diff_subjects)
                rule[arg]=value
            elif value in diff_classes or value in diff_teachers or value in diff_subjects:
                flag=False
                break
        if not flag:
            continue
        for class_name in copy.copy(rule["scope"]):
            if class_name in diff_classes:
                rule["scope"].remove(class_name)
        new_rules.append(rule)
    cfg.rules.value=new_rules
