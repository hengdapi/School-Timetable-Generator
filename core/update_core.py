import logging
import os
import traceback
import webbrowser
from threading import Thread

import requests
from PySide6.QtCore import QThread,QUrl,QByteArray,Qt
from PySide6.QtGui import QTextDocument,QImage
from packaging import version

from locals import app_version,gitcode_url,show_error
from style import *


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
        except requests.exceptions.ConnectionError:
            pass
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
