<p align="center">
  <img width="20%" align="center" src="logo.ico" alt="logo">
</p>
<h1 align="center">课程表生成器</h1>
<p align="center">
  一个可以帮助学校生成符合需求的课程表的小工具
</p>
<div align="center">


[![GPLv3](https://img.shields.io/badge/License-GPLv3-blue?color=#4ec820)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.9+-green.svg)
![Version](https://img.shields.io/badge/version-2.3.0-blue.svg)

![img.png](docs/海报.png)
</div>

## 项目介绍
这是一个排课工具，可以帮助学校老师轻松生成全校班级和教师的课程安排表。

https://github.com/user-attachments/assets/54e25ec6-498b-427b-86a1-bcbc8a48aced
## 主要亮点
- 界面简洁易上手，几乎无学习成本
- 课程信息可在软件内直接维护，也支持导入 Excel 表格
- 课程表生成规则支持自定义（内置 11 种规则，可按班级设置生效范围）
- 支持并课与联合授课：合班上课、一科多师都能正确排课与导出
- 功能人性化，如减少教师连堂、平均分配课程、撤销 / 重做、一键检查冲突
- 支持导出 CSES 通用课表，一键同步到班级大屏

## 支持的功能
### 课程信息
![课程信息表模板](images/template.png)
- 在软件内维护年级、班级与任课教师，支持双击编辑、右键菜单
- 可直接上传 Excel 课程信息表（内置模板下载），导入后覆盖当前课程信息并自动重启生效
- 同一格填写多位老师（如「张三 李四」）即为联合授课，排课、规则检查与导出均支持

### 排课设置
`排课设置` 采用分页布局，包含课程数量、活动时间、排课规则、并课设置、功能设置、表格样式、导出/导入七个分页：
- **课程数量**：设置每天上午、下午的课程数量
- **活动时间**：在统一时间轴上拖拽或双击调整课程与活动的起止时间，时间冲突会即时提醒
- **排课规则**：自定义生成规则（共 11 种）——必须排、不能排、优先排、每天必排、同时最多排、不能同时排、保持课时顺序、老师不能同时排、老师不能排、连堂、单双周；每条规则可指定生效班级，范围之外不检查该规则
- **并课设置**：并课的班级会在同一时间上同学科的课程，适合两个班一起上课；调课时并课班级的课程会一起调整
- **功能设置**：减少教师连堂、平均分配课程、允许跨上下午连堂、调整最大尝试次数
- **表格样式**：学校名称、是否显示教师姓名、导出文字字体与字号
- **导出/导入**：备份与恢复本机的排课设置

![设置选项（v2.0 界面，v2.3 已改为分页布局）](docs/设置-长截图.png)
![](docs/生成规则.png)

### 生成与手动调整
![](docs/拖拽交换课程.gif)
- 可选择班级范围一键生成；生成时任务栏显示进度，仅在窗口失焦时推送系统通知
- 生成结果支持撤销 / 重做（Ctrl+Z / Ctrl+Y）
- 支持一键检查冲突，双击冲突项可直接跳转到对应位置
- 表格内拖拽可交换
- 点击课程时或拖拽过程中可用不同颜色显示能否交换，并在右侧同步显示任课教师的课程表便于对照
![](docs/课程暂存.gif)
- 可将课程拖拽至暂存区暂放（左侧会有小红点提醒未排完）
![](docs/单双周课程合并.gif)
- 单双周课程可以通过拖拽合并、拆分
- 右侧教师课表适配联合授课：按教师人数纵向排列，人数较多时自动滚动
- 支持主题热切换，跟随系统深浅色实时生效
- 排课完成，或仍有课程未能自动安排时，会推送系统通知提醒

### 方案管理
- 保存、加载、删除课程表方案合并到统一的方案管理对话框，支持列表多选与实时刷新
- 覆盖已有方案时会给出提示，并默认填入当前方案名称

### 调整后直接导出
最终可直接导出以下表格（信息为示例，点击图片可跳转至excel文件），并支持导出 CSES 通用课表：
- 班级课表（按年段整理）
[![](docs/导出-班级课表.png)](docs/导出示例-各班课表（年级）.xlsx)
- 教师课表（按年段整理）
[![](docs/导出-教师课表.png)](docs/导出示例-教师课表（年级）.xlsx)
- 班级总表（全校的班级汇总课表）
[![](docs/导出-班级总表.png)](docs/导出示例-班级总表（横）.xlsx)
- 教师总表（全校的教师汇总课表）
[![](docs/导出-教师总表.png)](docs/导出示例-教师总表（横）.xlsx)

此外还支持导出 **CSES 通用课表（v1 / v2）**，每个班级生成一个 YAML 文件，可直接导入 Class Island、Class Widgets 等班级大屏课表软件（部分软件暂未适配 v2，如导入失败请改用 v1）。加上 4 种 Excel 表格，共支持 6 种导出格式。

启动时会自动检查更新，更新详情对话框支持图片说明，自动更新残留的安装包会自动清理。

## 使用方法（二选一）
### 一、自行搭建运行环境
1. 前往[Python官网](https://python.org/downloads)下载并安装Python3.9+版本
2. 将本项目下载解压到本地
3. 在项目根目录运行`pip install -r requirements.txt`（报错可搜索`pip换源`）
4. 双击`main.py`或运行`python main.py`即可启动
### 二、使用[Releases](https://github.com/hengdapi/School-Timetable-Generator/releases)中的安装包
- 选择对应版本的安装包（后缀为`Setup.exe`），双击安装即可
- 下载压缩包（`.zip`格式）解压到任意位置，双击运行`School-Timetable-Generator.exe`
## 许可证
根据 GPL v3.0 许可证分发。打开 [`LICENSE`](LICENSE) 查看更多内容。

Copyright © 2026 Hengxiaopi.
## 致谢
本项目使用了以下开源项目：
- [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
- [PySide6-Fluent-Widgets-Pro](https://github.com/Fairy-Oracle-Sanctuary/PySide6-Fluent-Widgets-Pro)

感谢以下贡献者：
[![](http://contrib.nn.ci/api?repo=hengdapi/School-Timetable-Generator)](https://github.com/hengdapi/School-Timetable-Generator/graphs/contributors)

特别感谢[buBailai](https://github.com/buBailai)为本项目的开发提供宝贵数据和建议
