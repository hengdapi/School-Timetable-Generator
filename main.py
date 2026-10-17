# coding=utf-8
import sys,logging,time
import darkdetect
from PySide6 import QtWidgets
from PySide6.QtGui import QIcon,QFont
from PySide6.QtCore import QLocale,QSize,QByteArray,QTimer,QEvent,Qt
from qfluentwidgets_pro import MSFluentWindow,SplashScreen,FluentTranslator,setThemeColor,setTheme,Theme,qconfig
from qfluentwidgets_pro.common.icon import FluentIcon

from locals import lesson_info
from pages import home,settings,generate
from qframelesswindow.utils import getSystemAccentColor
from wr_settings import save_settings, cfg

class Window(MSFluentWindow):
    def __init__(self):
        super().__init__()
        logging.debug("初始化主窗口")
        # 记录普通状态下的几何信息，用于关闭时保存，避免 showNormal()/saveGeometry() 不同步
        self._normal_geometry = None
        if sys.platform in ["win32","darwin"]:
            setThemeColor(getSystemAccentColor(),save=False)
        setTheme(Theme.AUTO,save=False)
        self.setWindowTitle("课程表生成器")
        self.setWindowIcon(QIcon("logo.ico"))
        self.setFont(QFont("Microsoft YaHei", 20))

        # ===== 恢复窗口位置/大小 =====
        # 先恢复普通几何，不立即应用最大化；等窗口显示并布局完成后再最大化，
        # 避免无边框窗口在启动时内容区域计算错误（缩在左上角）
        geom_b64 = cfg.window_geometry.value
        if geom_b64:
            try:
                data = QByteArray.fromBase64(geom_b64.encode())
                self.restoreGeometry(data)
                # 兼容旧配置：如果 geometry 里仍带最大化状态，先恢复为普通尺寸，
                # 避免后续布局计算时内容区域异常
                if self.isMaximized():
                    self.showNormal()
                logging.debug("成功恢复窗口位置和大小")
            except Exception as e:
                logging.warning(f"恢复窗口位置失败，使用默认设置: {e}")
                self._default_geometry()
        else:
            self._default_geometry()
            logging.debug("使用默认窗口位置和大小")

        # 记录初始普通几何，避免窗口从未处于普通状态就关闭时无法保存
        self._normal_geometry = self.geometry()

        #启动页面
        splashScreen=SplashScreen(self.windowIcon(),self)
        splashScreen.setIconSize(QSize(150,150))
        self.show()

        # 布局稳定后再恢复最大化状态
        if cfg.window_maximized.value:
            self.showMaximized()
            logging.debug("恢复窗口最大化状态")

        self.home=home.Home()
        self.settings=settings.Settings()
        self.generate=generate.Generate()

        self.addSubInterface(self.home,FluentIcon.HOME,"主页")
        self.addSubInterface(self.settings,FluentIcon.SETTING,"设置")
        self.addSubInterface(self.generate,FluentIcon.BRUSH,"生成")
        logging.debug("已添加所有子页面")

        splashScreen.finish()
        # 监听系统颜色模式，运行时跟随系统热切换（无需重启）
        self._init_system_theme_watcher()
        logging.info("主窗口初始化完成")

    def _init_system_theme_watcher(self):
        """定时检测系统颜色模式（读取注册表/系统设置，开销极小）"""
        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(1000)
        self._theme_timer.timeout.connect(self._on_system_theme_tick)
        self._theme_timer.start()

    def _on_system_theme_tick(self):
        """系统颜色模式发生变化时热切换界面主题"""
        try:
            # 仅在“跟随系统”模式下生效；若用户手动指定过颜色模式则不覆盖
            if cfg.themeMode.value is not Theme.AUTO:
                return
            system_theme = Theme.DARK if str(darkdetect.theme()).lower() == "dark" else Theme.LIGHT
            if system_theme == qconfig.theme:
                return
            logging.info(f"检测到系统颜色模式切换为{'深色' if system_theme is Theme.DARK else '浅色'}，正在热切换界面主题")
            # 先让 qconfig 依据系统重新求解实际主题，再刷新全部样式表
            qconfig.theme = Theme.AUTO
            setTheme(Theme.AUTO, save=False)
        except Exception as error:
            logging.debug(f"检测系统颜色模式失败：{error}")

    def resizeEvent(self, event):
        """普通状态下记录当前几何，便于关闭时保存普通尺寸"""
        if not self.isMaximized() and not self.isMinimized() and not self.isFullScreen():
            self._normal_geometry = self.geometry()
        super().resizeEvent(event)

    def moveEvent(self, event):
        """普通状态下记录当前几何，便于关闭时保存普通位置"""
        if not self.isMaximized() and not self.isMinimized() and not self.isFullScreen():
            self._normal_geometry = self.geometry()
        super().moveEvent(event)

    def changeEvent(self, event):
        """窗口从最小化恢复后，强制触发一次布局更新，修正无边框窗口客户区错位"""
        if event.type() == QEvent.Type.WindowStateChange:
            old_state = event.oldState()
            if old_state & Qt.WindowState.WindowMinimized:
                # 等状态切换完成后再更新，避免拿到中间尺寸
                QTimer.singleShot(0, self.update)
        super().changeEvent(event)

    def _default_geometry(self):
        """没有记录时的默认尺寸和居中"""
        self.resize(1300, 700)
        screen = self.screen().availableGeometry()
        size = self.size()
        self.move(
            int((screen.width() - size.width()) / 2),
            int((screen.height() - size.height()) / 2)
        )

    def closeEvent(self, e):
        """窗口关闭时保存 geometry 和最大化状态到配置"""
        try:
            if not lesson_info.saved:
                reply=QtWidgets.QMessageBox.question(self,"方案未保存","您当前的方案未保存，是否前往保存？\n若不保存，即使您已经导出了Excel版课程表，也无法再恢复当前方案了",QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No|QtWidgets.QMessageBox.Cancel)
                if reply==QtWidgets.QMessageBox.Yes:
                    self.switchTo(self.generate)
                    self.generate.save_plan()
                    if not lesson_info.saved:
                        e.ignore()
                        return
                elif reply==QtWidgets.QMessageBox.Cancel:
                    e.ignore()
                    return

            is_max = self.isMaximized()
            cfg.window_maximized.value = is_max

            # 若当前处于最大化，先恢复为普通状态再保存 geometry，
            # 否则 saveGeometry 会保存最大化后的尺寸，导致下次启动异常。
            if is_max:
                self.showNormal()
                if self._normal_geometry:
                    self.setGeometry(self._normal_geometry)

            state = self.saveGeometry()              # QByteArray
            cfg.window_geometry.value = bytes(state.toBase64()).decode()
            save_settings()
        except Exception:
            pass
        super().closeEvent(e)


if __name__ == '__main__':
    try:
        import platform
        logging.info(f"操作系统名称：{platform.system()} {platform.release()}")
        logging.info(f"操作系统版本：{platform.version()}")
    except:
        pass
    
    app=QtWidgets.QApplication(sys.argv)
    translator=FluentTranslator(QLocale(QLocale.Chinese,QLocale.China))
    app.installTranslator(translator)
    ui=Window()
    ui.show()
    logging.info("主窗口已显示")
    exit_code = app.exec()
    logging.info(f"程序退出，退出码：{exit_code}")
    sys.exit(exit_code)