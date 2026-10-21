# FH6 Car Mod Manager 0.8.2 — 记住缩略图生成失败状态

## 0.8.2 缩略图失败不再自动重试

- 模组预览生成失败后，将记录保存到 `%LOCALAPPDATA%\FH6CarModManager\thumbnails\failed-previews.json`。重开管理器会直接跳过，原文件无需再次读取或启动渲染器。
- 启用、禁用和同名版本改名不会触发重试；相同内容的副本首次读取哈希后也会跳过渲染。
- 需要重试时，选中车辆并点击“重建所选缩略图”。成功后清除该内容的失败记录；模组内容改变后允许重新生成。
- 游戏启动、暂停任务、关闭程序及任务被替换造成的中断，不写入失败记录。
- 卡片支持中英文失败提示。清理 PNG 缓存不会清理失败记录。
- 旧版没有持久保存失败状态，因此升级后，过去失败的模组可能会再尝试一次以建立记录。

本版为源码构建包，不含预编译 Windows EXE。在 Windows 解压后运行 `Build_EXE.bat`。本次仅修改 Python 管理器，沿用 0.8.1 渲染组件。

## 0.8.1 渲染器 XAML 资源构建修复

用户上传的 0.8.0 日志确认 C# 编译成功，但渲染自检在 `ViewportPage.InitializeComponent()` 报 `XamlParseException`，未进入车辆读取。日志未给出具体资源名，不能仅凭这一异常断定某个 DLL 缺失。

独立工程遗漏了原工程的 `EnableMsixTooling=true`。本版恢复该配置，显式启用 MRT 资源构建、统一应用资源索引名为 `resources.pri`，并补齐显式 XAML 项目的 Generator / XamlRuntime 元数据。保留精简后的源码和资源清单，不恢复完整编辑器。

- 构建自动清理独立渲染器自己的 obj / bin 缓存和发布 renderer，避免旧 XAML / PRI 混入；不删除游戏、模组和管理器设置。
- 发布后新增 `renderer-resources.log`，检查应用的 `resources.pri` 存在且非空。依赖库的 PRI 不算通过，XBF 可以合法嵌入 PRI，因此不强制要求独立 XBF 文件。
- 资源文件检查只验证发布完整性；之后仍必须通过原有 WinUI / Direct3D / PNG 实际自检，失败会停止打包。
- 保留 XBF 行号，更新启动日志版本号及资源文件信息，以便仍有异常时继续定位。
- 保留圆角导航、署名、中英文和缓存空间优化。

本版 107 项 Python 测试通过。0.8.1 的 Windows 编译、资源生成和实际渲染仍待实机确认，不能视为已通过。请关闭游戏和管理器，解压到新目录，运行 `Build_EXE.bat`。不需要因这次错误重装 Python。如果仍失败，请提供 `build-windows.log`、`renderer-resources.log`、`renderer-check.log`。

本包仍为源码构建包，不含预编译 EXE。

## 0.8.0 空间优化与界面调整

- 顶部“模组管理 / 设置 / 帮助”改为圆角按钮，文字和背景一起绘制，保留中英文、键盘操作和游戏运行锁定。
- 底部居中显示加粗署名 `BY：bilibili _-菠小萝-_`。
- Windows 构建改用独立的 `FH6ThumbnailRenderer.csproj`：明确选取 110 个 C# 源文件、5 个 XAML 页面，不再编译完整主编辑器、文档页面和 Markdown 组件，也不复制宣传图片、文档及编辑预设。保留共享查看器内部所需的材质、动画及导出辅助代码；这不是完全重写的最小渲染引擎。
- 保留模型、贴图解码、SQLite 资源查询及 .NET / Windows App SDK 自包含运行库。避免通过直接删除 DLL 破坏预览，使用者仍不需单独安装这些运行库。
- 预览按当前可见卡片请求；命中缓存时不再生成整份车辆 ZIP 的临时副本。未命中时仍使用临时副本保护原文件，渲染资源组合 ZIP 使用快速压缩。
- PNG 缓存默认限制为 256 MiB，清理 30 天未访问的旧预览，超额按最近使用顺序淘汰；当前新生成图片受保护。清理本版带所有权标记且超过 24 小时的残留临时任务，不处理旧版无标记目录。错误日志超过 2 MiB 时轮换并保留一份旧日志。限额不包括生成过程中的临时文件。
- 构建前清除旧输出中的 renderer，避免旧组件混入。成功构建会生成 `package-size-report.txt`，列出安装目录总大小、渲染组件大小和最大的 30 个文件。

104 项 Python 测试通过；实际 Tk 窗口检查了圆角导航文字、125% 等效字体缩放、中英文切换、署名和游戏锁定。C# 独立工程已做静态文件清单检查，**尚未在 Windows 编译或验收真实车辆渲染**。Windows 构建继续强制执行管理器启动及渲染 PNG 自检，失败则停止打包。

本包是源码与构建脚本，**不含预编译 Windows EXE**。关闭游戏和管理器后，建议解压到新目录，运行 `Build_EXE.bat`。精简针对构建输出；为方便检查和后续维护，源码包仍保留上游源码与许可。因此不能用源码 ZIP 大小推算安装目录的节省量，实际大小以 Windows 构建报告为准。

## 0.7.1 顶部文字修复、中英文切换、单车预览重建

- 顶部明确显示“模组管理 / 设置 / 帮助”，英文为“Mods / Settings / Help”。导航改用独立文字按钮并增加高度，避免旧版自绘按钮文字区域被挤压；游戏运行时仍全部灰显锁定。
- “重建所选缩略图”仅使当前选中车辆的缓存失效并重新生成，不再清空全部车辆缓存。没有选择时提示先选车。原有后台首次预览生成仍正常进行。
- 为单车任务加入独立修订编号，忽略刷新前的旧任务结果；暂停后继续重试，其他车辆的任务与缓存保留。图片生成后自动更新显示。
- 设置页顶部新增“界面语言 / Language”：简体中文、English。选择后立即生效，并保存至现有 settings.json；切换游戏目录不丢失语言偏好。
- 切换语言保留当前页面、筛选、搜索和选中车辆。菜单、状态、帮助、确认弹窗及常见文件操作错误均支持英文。游戏运行或文件操作期间不能更改语言。

94 项 Python 测试通过；实际 Tk 窗口已验证中英文切换、偏好持久化、游戏锁定、125% 等效字体缩放下的导航文字尺寸，以及小窗口布局。Windows 构建自检现在会创建完整界面，检查顶部按钮文字与高度，并检查语言选择器和锁定状态。当前环境未编译 Windows EXE，Windows 实际显示仍需构建后确认。

关闭管理器和游戏，完整解压或覆盖原项目后运行 `Build_EXE.bat`，使用新输出的 EXE。新增 `i18n.py` 会自动打包，不需额外安装翻译组件；本版未改动 C# 渲染器。

### English quick start

Build on Windows with `Build_EXE.bat`, then launch `dist/FH6CarModManager/FH6CarModManager.exe`. Keep the complete output folder, including `_internal` and `renderer`.
Open **设置 → 界面语言 / Language → English**. The language changes immediately and is remembered. Select a vehicle card and click **Rebuild preview** to regenerate only that vehicle's thumbnail. Game-running protection also locks the language selector.

## 0.7.0 界面改版

- 参考 Plain Craft Launcher 的蓝白配色、顶部导航、侧边栏和圆角卡片，独立实现界面；没有引入 PCL 源码、图片或标识。
- 顶部提供“模组管理 / 设置 / 帮助”三个页面，路径检测与车辆校验设置集中到设置页。
- 左侧可筛选全部、已启用、已禁用、同名版本，筛选可与文件名搜索组合使用。
- 保留大尺寸车辆宫格：图片在上、文件名在下，选中卡片显示蓝色边框；底部集中提供启停、删除和重新生成预览。
- 游戏运行时，新增导航与筛选按钮也会灰显锁定，运行状态始终显示在侧栏。
- 保留 0.6.6 的缩略图构图与辅助点隐藏处理，以及所有模组安装、版本切换和文件保护逻辑。

86 项 Python 测试通过，并在实际 Tk 窗口验证页面切换、组合筛选、游戏运行锁定及三列/两列布局。本包是源码与 Windows 构建脚本，不含预编译 EXE；新界面的 Windows 字体与系统缩放效果需在你的电脑上确认。
关闭管理器与游戏，完整解压到新目录或覆盖原项目，双击 `Build_EXE.bat`，再启动新生成的 EXE。

## 0.6.6 放大车辆预览并隐藏编辑辅助图形

- 宫格卡片从 250×218 调整到 360×286，图片区域从约 232×130 调整到 342×192；窗口变窄时自动减少列数。
- 查看器会将没有三角面索引的数据画为绿色点云。这类数据不属于可渲染车身表面，现在在缩略图模式中隐藏，同时隐藏定位点、骨骼、线框、包围盒、损伤及物理辅助图形。
- 用可见三角网格的世界坐标范围计算相机位置，考虑宽高比和透视深度，目标是在限制方向保留约 5% 单边边距。不会把点云等辅助对象纳入构图。
- 更新缓存配方，重新构建并启动后自动生成新缩略图；不修改游戏或模组 ZIP。

86 项 Python 测试通过，Tk 宫格的三列/两列窗口切换、320×180 PNG 展示、选择、滚动与锁定已验证。用户截图已确认旧版能渲染车辆；新版 C# 构图和隐藏辅助点的真实车辆效果仍需 Windows 验证。
关闭管理器与游戏，覆盖项目后重新运行 `Build_EXE.bat`，启动新生成的 EXE。首次打开会重新生成预览。

## 0.6.5 Windows 环境变量测试修复

修复新增测试固定读取 `Path` 而 Windows `os.environ` 将键名规范化为 `PATH` 导致的 `KeyError`。路径过滤测试用独立映射覆盖 `Path`、`PATH`、`path` 三种拼写；新增真实进程环境测试，在系统规范化键名后保存快照，验证子进程过滤不会修改父进程环境。
当前 Linux 环境下 86 项测试通过；用户上次的 Windows 构建停在测试阶段，尚未执行 0.6.4 新增的渲染器自检。保留此前全部渲染修复及自检，覆盖项目后重新运行 `Build_EXE.bat`。

## 0.6.4 渲染组件异常退出处理与自检

收到的日志中所有车辆均以 `3221226107 / 0xC000027B` 退出。该码不足以确定内部异常原因；这版针对代码中发现的启动与视图生命周期问题进行修复，并补充诊断。

- 启动独立 WinUI 渲染器时暂时清除 PyInstaller 的 DLL 搜索目录，随后立即恢复；子进程 PATH 排除 `_internal`，不修改用户系统设置。
- 保持 3D 视图在原容器内，避免与原查看器的排队挂载逻辑冲突及重新挂载引发的渲染宿主重建；仅导出视图缓冲区。
- 提前记录 WinRT、App XAML、视图、模型、贴图和 PNG 导出阶段；临时目录删除前将错误详情保留到 `thumbnails/errors.log`。
- 完整构建新增渲染器自检：由已打包管理器启动 WinUI/Direct3D 并导出测试 PNG，失败则停止发布，详情在项目根目录 `renderer-check.log`。此自检不读取车辆，也不代表真实车辆资源已通过验证。
- 发布明确禁用程序集裁剪，保留 XAML 与反射需要的类型。

当前 Linux 环境 85 项 Python 测试通过，其中 Windows DLL 调用与渲染进程使用测试替身。C# 编译、Windows 原生渲染和真实车辆缩略图仍需实机验证。
关闭游戏及管理器，覆盖源码后运行 `Build_EXE.bat`。完成后使用 `dist/FH6CarModManager/FH6CarModManager.exe`，保留整个输出目录。若自检失败，提供 `renderer-check.log` 和 `build-windows.log`；若仅车辆预览失败，提供新的 `errors.log`。

参考：
- https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application
- https://learn.microsoft.com/en-us/shows/inside/c000027b

## 0.6.3 本机游戏安装导致的测试误报修复

将磁盘与环境变量目录探测独立为 `default_paths()`；测试隔离进程、注册表和默认目录来源，避免真实安装的游戏混入临时测试结果。正常运行的自动检测范围保持不变。
新增多安装目录与去重回归测试，并修复单元测试模拟 EXE 启动时提前打印“Packaged EXE / Tk grid: OK”的误导输出。
当前 Linux 环境下 76 项测试通过；Windows EXE 完整构建与真实 3D 预览仍待实机验证。覆盖原项目后重新运行 `Build_EXE.bat`，无需重装 Python。

## 0.6.2 Windows 测试路径修复

统一测试临时目录为 `Path(...).resolve()`，避免 Windows 短路径（例如 `LITTLE~1`）和完整用户名路径指向同一目录，却在路径断言中被误判为不同目录。
构建继续严格执行全部测试，不跳过失败。测试详细输出独立写入 `test-results.log`，不依赖 PowerShell 转录是否完整捕获标准错误。
已用目录别名模拟同一目录的不同路径写法，75 项测试全部通过；实际 Windows 重打包仍需验证。

## 0.6.1 打包修复

修复 Windows PowerShell 向 `python -c` 传递代码时丢失内层引号的问题（`NameError: name 'P' is not defined`）。环境校验与 EXE 启动检查均改为执行独立 `build_checks.py`，不再内嵌 Python 代码。

覆盖原项目文件后重新运行 `Build_EXE.bat` 即可，无需因该错误重装 Python 或删除 `.build-venv`。
新增 4 项构建检查测试通过；环境校验也已在当前 Python 上直接运行。完整 Windows 编译仍待实机确认。

Windows 中文车辆模组管理器，支持 Steam 与 Xbox 版。直接管理 `forzahorizon6.exe` 同级目录下 `mediapc\cars` 中的车辆 ZIP。

安装与切换时，将 ZIP **作为模组文件本身**复制和重命名，不修改 ZIP 内部内容。缩略图只读取临时副本；渲染用的资源组合也仅写入临时目录。

## 启动

1. 完整解压本压缩包。
2. 安装含 Tcl/Tk 的 Python 3.10 或更高版本，无需任何第三方 Python 包。
3. 双击 `Start.bat`。

交付状态：这是源码及 Windows 构建包，**不含已经编译好的 Windows EXE**。主程序入口为 `app.py`。

## 0.6 新增：宫格与缩略图

- 上图下文件名的自适应宫格，显示启用状态及大小；底部显示选中文件的完整名称。
- 单击选择、双击或空格切换启用；方向键选择；鼠标滚轮滚动。大量模组只绘制可见卡片。
- 保留同名版本、车辆文件名校验、Steam/Xbox 检测、删除回收站、游戏运行锁定。
- 后台队列通过修改过的 ForzaTech Studio 渲染器导出 PNG；按模组内容、原版车辆内容、游戏路径和渲染器版本缓存。
- `.zipdisabled` 复制到临时 `.zip` 读取，不需要启用，不改动游戏或模组文件。
- 模组条目优先、匹配原版 ZIP 补全缺失条目；渲染器从游戏资源目录解析共用贴图。使用固定相机、LOD0，隐藏网格和辅助信息。
- 游戏运行或文件操作期间，暂停队列并终止当前渲染子进程。退出游戏后重新排队。
- “重建所选缩略图”用于当前选中车辆的失败重试、共用贴图变更后刷新缓存；其他车辆的缓存保留。
- 缓存：`%LOCALAPPDATA%\FH6CarModManager\thumbnails`；诊断日志：其中的 `errors.log`。

**渲染组件状态：** 用户提供的旧版 Windows 截图已确认能够生成车辆预览；0.6.6 新增的紧凑构图与辅助点隐藏效果仍需实机确认。
源码运行时如果旁边没有 `renderer/ForzaTech Studio.exe`，卡片明确显示“未安装 3D 渲染组件”。不会生成假预览。

渲染使用 WinUI/Direct3D，需要 Windows 图形会话与显卡；可能显示一个不主动抢焦点的小型渲染窗口，不属于无窗口服务器渲染。
不同模组的材质、车辆附件组合可能仍需调试，预览不保证与游戏内完全一致；仅修改性能数据的模组外观可能相同。

## 构建 Windows EXE

详见 `WINDOWS_QUICKSTART.md`。Windows 上安装 Python x64、.NET 9 SDK 与 Windows 构建依赖后，双击 `Build_EXE.bat`。
脚本运行测试、构建管理器，再编译随包附带的独立缩略图工程，输出可分发的完整文件夹和 ZIP。

主入口：`dist/FH6CarModManager/FH6CarModManager.exe`

必须保留同目录的 `_internal`、`renderer` 及许可文件。正常使用者不需单独安装 Python。
构建日志：`build-windows.log`。打包失败会明确报错，不会把不完整输出标为成功。
`.github/workflows/build-windows.yml` 可在你自己的 GitHub 仓库手动触发 Windows 构建；本次未上传或运行远程构建。

## 当前验证范围

116 项 Python 测试通过，包括新增的 9 项失败记录回归测试，覆盖重启跳过、改名、副本、内容变更、手动重试和中断处理。
缩略图测试使用模拟渲染子进程验证协议和文件保护，**不是 ForzaTech Studio 实际渲染通过的证明**。
另已在 Linux 虚拟显示环境通过 Tk 宫格窗口创建、滚动定位，以及完整界面的按钮锁定/解锁检查。Windows 字体与视觉效果仍待实机确认。
当前环境是 Linux，没有完成 Windows EXE 编译、WinUI/DirectX 运行及真实 FH6 模组效果验收。

## Steam / Xbox 目录支持（0.5 新增）

以下以 `Forza Horizon 6` 表示对应版本的游戏安装文件夹：

| 项目 | Steam 版 | Xbox 版 |
| --- | --- | --- |
| EXE | `Forza Horizon 6\forzahorizon6.exe` | `Forza Horizon 6\Content\forzahorizon6.exe` |
| 模组目录 | `Forza Horizon 6\mediapc\cars` | `Forza Horizon 6\Content\mediapc\Cars` |
| 车辆名称校验目录 | `Forza Horizon 6\media\cars` | `Forza Horizon 6\Content\media\cars` |

Steam 默认检查 `Steam\steamapps\common\Forza Horizon 6`，也读取 Steam 的 `libraryfolders.vdf` 来识别其他磁盘上的库。根据 `steamapps\common` 下的 EXE 识别 Steam 布局，根据 `Content` 下的 EXE 识别 Xbox 布局。其他手动选择的根目录 EXE 显示为“根目录布局”，同样不额外添加 Content。

自动发现和手动选择 EXE 都使用同一套路径规则；界面会显示版本，发现多个安装位置时会带版本标签供选择。缺少模组目录时创建对应路径，但不会创建或修改原版 `media\cars`。

## 删除所选模组（0.5 新增）

1. 在宫格中选择一个已启用或已禁用的模组。
2. 点击“删除所选模组”，核对文件名及状态后确认。
3. 默认交给 Windows 回收站处理，完成后宫格自动刷新。

只删除当前选中的一份文件。同名其他版本、原始下载文件及原版车辆校验目录中的文件不会被连带删除。删除启用版本后不会自动启用备用版本。

如果系统无法回收该文件（例如回收站条件不满足），保留 Windows 的永久删除警告，由你决定是否继续；程序不会在系统删除失败后自行改用永久删除。取消删除或遇到错误时显示原因。存在未完成切换时，先恢复切换，再删除。

游戏运行期间删除按钮与其他按钮一同变灰；确认后执行前也会再次检查进程状态。确认期间所选文件大小或修改时间变化时，会停止删除并要求重新选择。

## 导入前校对车辆文件名（0.4 新增）

每次导入都会重新读取该版本 EXE 同级 `media\cars` 中的车辆文件名（Xbox 位于 Content 内，Steam 位于游戏根目录）。导入 ZIP 的**完整文件名（包含 `.zip`）必须匹配其中一个实际文件**，按 Windows 习惯不区分大小写。不进行模糊匹配，不自动删除额外文字或版本号。

假设车辆目录中有 `POR_911_23.zip`：

| 待导入文件 | 结果 |
| --- | --- |
| `POR_911_23.zip` | 允许导入 |
| `por_911_23.ZIP` | 允许导入，采用车辆目录中的名称大小写 |
| `POR_911_23 (1).zip` | 拒绝 |
| `POR_911_23_v2.zip` | 拒绝 |
| `POR_911_24.zip` | 没有同名车辆文件则拒绝 |

校验发生在复制之前。同名版本必须先使用正确的原始车辆文件名导入，通过校验后，管理器再为备用版本自动添加 `__fh6mm_v数字.zipdisabled` 后缀。不会拿添加后缀后的备用名称去与原版车辆名称比对。

- 自动定位 EXE 时，车辆校验目录取 EXE 同级的 `media\cars`。
- 手动选择标准 `mediapc\cars` 时，会自动推导与 mediapc 同级的 `media\cars`，适用于两种版本。
- 手动选择自定义模组目录时，可点击“选择车辆校验目录”，指定该版本游戏 EXE 同级的 `media\cars`。
- 找不到、无法读取或未指定车辆校验目录时，拒绝导入，不跳过校验。空目录也不会允许任何 ZIP 导入。
- 校验目录不能与模组安装目录相同，防止拿已安装模组验证其自身。
- 批量导入逐个判断：符合的继续导入，不符合的列出拒绝原因。
- `media\cars` 只读，不会被创建、修改或覆盖；安装仍写入 `mediapc\Cars`。

此功能校验文件名，不验证 ZIP 内容是否与该车辆兼容。目录中已经存在的模组仍按原规则显示和启停，不会被本次新增校验自动删除。

## 游戏运行时自动锁定（0.3 新增）

- 约每秒检测一次进程名 `forzahorizon6.exe`，不区分大小写。检测运行状态不需要读取游戏进程的完整 EXE 路径。
- 检测到游戏运行时，全部应用按钮变灰；搜索框、卡片点击 / 双击 / 空格切换，以及窗口拖放全部禁用。
- 侧栏显示“FH6 正在运行，全部操作已锁定”，游戏退出后自动恢复。
- 游戏运行期间拖入的文件不会缓存为待安装任务，退出游戏后不会自动安装这些文件。
- 首次检测尚未完成或进程枚举失败时暂时锁定，继续自动重试。仍可通过窗口标题栏关闭管理器。
- 每次操作执行前再次检查；文件选择窗口打开后如果游戏启动，返回的选择不会应用。
- 游戏运行时启动管理器，会先显示上次记录目录中的现有文件（如果目录仍在），目录自动定位和创建推迟到退出游戏后进行。

运行检测采用 Windows 原生进程快照，不通过反复启动 PowerShell 来轮询。后台文件任务结束时会重新检查锁定状态，避免游戏仍运行时误解锁按钮。

## 自动定位目录

程序启动后优先寻找实际存在的 `forzahorizon6.exe`，检查上次记录的位置、正在运行的游戏进程、Windows 安装记录、Steam 库与常见的 XboxGames / Games 目录。

例如找到：

`E:\XboxGames\Forza Horizon 6\Content\forzahorizon6.exe`

则使用：

`E:\XboxGames\Forza Horizon 6\Content\mediapc\Cars`

`mediapc` 或 `Cars` 不存在时会自动创建；不会多加一层 `Content`。检测到多个安装位置时会让你选择。

未检测到 EXE 时，才询问是否手动选择模组文件夹。如果此前手动指定过目录，会先询问是否继续使用该位置。你也可以随时通过“选择游戏 EXE”或“手动选择目录”按钮切换位置。

自动检测不递归扫描整个硬盘。安装在任意自定义目录且没有相关安装记录时，可能需要手动定位一次。

## 现有文件与启停

识别到目录后立即扫描其顶层文件，每两秒检查列表变化：

| 文件名 | 状态 |
| --- | --- |
| `CAR.zip` | 启用 |
| `CAR.zipdisabled` | 禁用 |
| `CAR__fh6mm_v1.zipdisabled` | 同名备用版本，禁用 |

双击卡片、按空格或点击下方启停按钮，即可切换。启用时恢复 `.zip`，停用时改为 `.zipdisabled`。

列表依据扩展名显示目录中的全部 ZIP / ZIPDISABLED，无法自动区分游戏自带文件和后装模组。新导入的文件必须通过上述车辆文件名校验，但不会自动判断 ZIP 内容是否适配 FH6。识别现有文件只扫描，不会自动更改其状态。

## 拖放和批量导入

- 从 Windows 文件资源管理器将一个或多个实际 `.zip` 文件拖入管理器窗口。
- 或点击“导入 ZIP（可多选）”。
- 文件直接复制到已选模组目录，原始下载文件保留。
- 新名称的首次导入默认启用。
- 相同名称再次导入时，保留原有版本，新版本使用唯一后缀并禁用。
- 如果该同名组当前全部禁用，新版本也保持禁用。
- 已在当前模组目录中的文件会跳过，不重复复制。
- 一个批次中某个文件失败时，会列出失败原因，其他有效文件继续导入。

拖放使用 Windows 原生接口，不依赖 tkinterdnd2。请使用普通用户权限启动程序；Windows 可能阻止资源管理器向以管理员权限运行的程序拖文件。请从实际文件夹拖入 ZIP，不要拖压缩软件窗口中的虚拟文件。

## 同名版本切换规则

同名比较不区分大小写。程序使用 `__fh6mm_v1`、`__fh6mm_v2` 等后缀区分备用文件。

例如先后导入两个来源目录里的 `CAR.zip`：

| 文件内容 | 切换前 | 启用版本 B 后 |
| --- | --- | --- |
| 版本 A | `CAR.zip` | `CAR__fh6mm_v1.zipdisabled` |
| 版本 B | `CAR__fh6mm_v1.zipdisabled` | `CAR.zip` |

启用另一个版本时，它取得原始名称；原本启用的版本接过它的禁用文件名。再次选择同一个备用文件名，就可以切回。其他备用文件保持不变。

**后缀编号表示备用文件位置，并不是永久版本编号。** 由于你要求切换时转移后缀，编号会随切换转移到另一份文件上。宫格同时显示缩略图、文件名和大小，便于区分。

`__fh6mm_v数字` 是本程序保留的分组后缀。其他自行命名的版本号（例如 `CAR_v2.zip`）会被视为另一个名称，不会擅自推断成同组。

如果外部手动改名造成同组多个 `.zip` 同时启用，列表会显示冲突。选中要保留的版本，点击“仅启用此版本”，其余同组文件会被禁用。

## 中断恢复

切换通过临时文件名分两步完成。每份文件的内容均校验 SHA-256，不会用新版本覆盖旧版本的内容。

若进程中断，重新打开相同模组目录并点击“恢复中断切换”。程序会继续完成原先请求的切换。恢复前若发现文件缺失、内容变化或目标路径被外部文件占用，会停止并保留全部现有文件。

模组目录中可能出现 `.fh6mm-transaction.json`、`.fh6mm-switch-*.tmp` 和 `.fh6mm.lock`。前两类在存在中断操作时用于恢复，请保留；锁文件可长期存在且不参与 ZIP 列表。复制中断可能留下 `.fh6mm-import-*.tmp`，它们不以 ZIP 结尾，不会显示为启用模组。程序正常复制失败时会清理自己的临时文件。

程序检测到 FH6 进程时会锁定操作。已经开始的文件操作不会被强制终止；周期检测不是与游戏进程之间的完整互斥锁，因此请等待当前文件操作完成再启动游戏，并避免同时使用其他工具更改相同文件。

## 数据位置

- 模组文件：所选 `Cars` 文件夹，直接管理，不另建模组缓存。
- 配置及错误日志：`%LOCALAPPDATA%\FH6CarModManager`。
- 本版不读取或删除 0.1 的原文件备份；如实际使用过 0.1 修改游戏文件，应先在 0.1 中完成对应恢复。

## 原有功能验证情况

0.5 版已在 Linux / Python 3.12 上通过 58 项自动测试，包括原有 46 项文件管理、进程锁定和文件名校验测试，以及新增 12 项平台路径和删除测试。新增测试覆盖 Steam / Xbox 路径、其他 Steam 库、只删除所选版本、保留同名文件、取消 / 失败处理、回收站接口参数和游戏运行时阻止删除。

Windows 原生拖放、回收站和 Windows 注册表 / 进程检测代码已经接入；这些 Windows 接口及控件使用模拟测试，平台路径使用临时目录测试。当前开发环境无法运行 Windows 界面，因此**尚未在 Windows 或真实 FH6 安装上实测**。如需用测试目录试运行，请同时准备独立的车辆校验目录，并放入与测试 ZIP 同名的参照文件，确认启停和切换后再选择真实游戏目录。

运行测试：`python -m unittest discover -s tests -v`

## 源码

- `app.py`：中文界面、后台任务和交互。
- `core.py`：ZIP 扫描、复制、重命名、同名版本互斥和中断恢复。
- `discovery.py`：游戏 EXE 自动检测。
- `windows_drop.py`：Windows 原生窗口文件拖放。
- `process_watch.py`：按进程名称检测 FH6 是否运行。
- `windows_recycle.py`：将所选文件交给 Windows 回收站处理。
- `tests/test_core.py`：核心流程测试。
- `tests/test_process_lock.py`：进程检测和界面锁定逻辑测试。
- `tests/test_vehicle_names.py`：车辆文件名校验和只读参照目录测试。
- `tests/test_platform_delete.py`：Steam / Xbox 路径及删除行为测试。

Windows 拖放接口参考：[DragQueryFileW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-dragqueryfilew)、[SetWindowSubclass](https://learn.microsoft.com/en-us/windows/win32/api/commctrl/nf-commctrl-setwindowsubclass)、[DefSubclassProc](https://learn.microsoft.com/en-us/windows/win32/api/commctrl/nf-commctrl-defsubclassproc)。

运行检测接口参考：[CreateToolhelp32Snapshot](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot)、[PROCESSENTRY32W](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)。

删除接口参考：[SHFileOperationW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shfileoperationw)、[SHFILEOPSTRUCTW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/ns-shellapi-shfileopstructw)。

0.6 新增文件：`mod_grid.py`、`thumbnails.py`、`tests/test_thumbnails.py`、Windows 构建脚本和 `vendor/ForzaTechStudio` 修改分支。
