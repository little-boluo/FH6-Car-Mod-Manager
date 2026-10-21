# Windows 构建与使用

本压缩包是 0.8.1 源码构建包，不含预编译 EXE。旧版预览已由用户截图确认能显示车辆；新版界面与缩略图构图效果需在 Windows 上确认。

## 完整构建

在 Windows 10/11 x64 上准备：

1. Python 3.12 x64，安装时包含 Tcl/Tk、pip 和 Python launcher。
2. .NET 9 SDK x64。
3. Visual Studio 2022 / Build Tools 的 .NET 桌面与 Windows 应用构建组件、Windows SDK。
4. 可访问 PyPI 和 NuGet 的网络。

解压到可写目录，双击 `Build_EXE.bat`。

成功后启动 `dist\FH6CarModManager\FH6CarModManager.exe`。
完整便携包是 `dist\FH6CarModManager-win-x64.zip`。
不要只复制 EXE；需保留 `_internal`、`renderer` 以及许可文件。

脚本在独立 `.build-venv` 中安装 PyInstaller，不修改你已有的 Python 包。
渲染器发布为 .NET 和 Windows App SDK 自包含目录；C# 编译链本次尚未实测。
失败时查看 `build-windows.log`，不要将残留 `dist` 视为完整成品。

## 仅测试宫格管理器

如果暂时不构建 3D 渲染器，可运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1 -ManagerOnly
```

这会得到可独立运行的管理器 EXE，但缩略图位置会显示“未安装 3D 渲染组件”。
渲染器必须使用本包修改过的分支；直接复制官网下载的原版 FTS EXE 不支持这里的新命令行入口。

## 首次验收

先使用一份你熟悉的车辆模组检查：

- 导入后宫格显示 PNG，模型与贴图符合该模组；失败时查看缩略图日志。
- 两个同名版本具有各自正确预览，切换启用状态后图片仍跟随文件内容。
- 游戏启动后所有操作按钮锁定，渲染停止；退出后恢复。
- 删除、关闭、重开程序后缓存与模组文件保持一致。

初次生成需要读入模型与贴图，耗时取决于模组大小和显卡；缓存命中后无需重新渲染。

## 修复旧版打包错误

若旧版出现 `NameError: name 'P' is not defined`，请同时更新 `build_windows.ps1` 和新增的 `build_checks.py`，然后重新运行 `Build_EXE.bat`。此错误来自脚本引号传递，不足以判断你的 Python 或 Tcl/Tk 安装有问题。

0.6.2 同时修复 Windows 临时目录短路径造成的测试误报；如构建仍停在测试阶段，请提供 `test-results.log` 和 `build-windows.log`。不要跳过测试。

0.6.3 修复测试自动扫描到本机真实游戏而失败的问题；自动检测功能保留。测试不会再提前显示模拟的 EXE 检查成功提示。

0.6.4：构建前关闭 FH6 和管理器。完整构建新增 WinUI / Direct3D / PNG 自检。失败时提供项目根目录 `renderer-check.log` 和 `build-windows.log`；若自检通过但车辆预览失败，提供 `%LOCALAPPDATA%\FH6CarModManager\thumbnails\errors.log`。需重新构建管理器及渲染器，仅覆盖 Python 源码不会更新已打包的 EXE。

0.6.5：修复 Windows 把环境变量键名规范化为大写引发的 `KeyError: Path` 测试错误。关闭管理器和游戏后覆盖原项目，重新运行 `Build_EXE.bat`。

0.6.6：放大宫格与图片区域，按车身网格收紧构图，隐藏黄绿色点云及辅助标记。需重新构建管理器和渲染器，启动后自动生成新版缓存。

0.7.0：采用 PCL 风格的蓝白界面，增加顶部页面导航与侧栏筛选。目录与校验设置移到“设置”页；其余操作与原版一致。请完整覆盖项目（包括新增的 `ui_theme.py`）并重新构建。

0.7.1：修复顶部导航文字显示；缩略图重建只针对宫格中选中的车辆。设置页顶部可以切换简体中文 / English，立即生效并记忆选择。需完整覆盖项目（包含新增 `i18n.py`）并重新构建。Windows 构建自检新增完整界面的顶部文字、高度与语言选择器检查。

0.8.0：使用独立缩略图工程，排除主编辑器和文档组件，保留自包含运行库。新增缓存限额、临时任务清理、圆角顶部导航和居中署名。建议解压到新目录重新构建；构建输出会清除旧 renderer。完成后查看 `package-size-report.txt` 获取实际安装体积。缓存限额不包含渲染过程中使用的临时空间。

0.8.1：修正独立渲染工程遗漏的资源构建设置，增加应用 PRI 发布检查。建议解压到新目录，关闭游戏和管理器后重新运行 `Build_EXE.bat`；脚本自动清理该渲染器的旧中间文件。若失败，请提供 `renderer-resources.log`、`renderer-check.log` 和 `build-windows.log`。0.8.0 的 C# 编译已由用户日志证实成功，但 PNG 自检失败；0.8.1 仍需 Windows 运行验证。
