# FH6 Car Mod Manager

**《极限竞速：地平线 6》车辆模组管理器 · v0.8.8**  
**Forza Horizon 6 Car Mod Manager · v0.8.8**

在一个窗口中导入、启用、切换和删除车辆模组，通过缩略图宫格区分不同车辆及同名模组版本。  
Import, enable, switch and delete car mods in one window. Thumbnail cards help you distinguish vehicles and different versions of the same mod.

**支持 Steam / Xbox 版 · 简体中文 / English · Windows 10 / 11 x64**  
**Supports Steam and Xbox editions · Simplified Chinese / English · Windows 10 / 11 x64**

**BY：bilibili \_-菠小萝-\_**

## 使用方法 / How to use

### 1. 下载与启动 / Download and launch

1. 在仓库的 **Releases** 页面下载适用于 Windows 的程序压缩包。  
   Download the Windows application ZIP from the repository’s **Releases** page.
2. 完整解压到一个可写的文件夹。  
   Extract the entire ZIP into a writable folder.
3. 关闭游戏，运行 `FH6CarModManager.exe`。  
   Close the game and launch `FH6CarModManager.exe`.

请保留程序文件夹中的全部文件，不要只移动 EXE，也不要直接在压缩包内运行。  
Keep all files in the application folder. Do not move only the EXE or run it directly from inside the ZIP.

### 2. 确认游戏目录 / Confirm the game folders

程序会自动查找 `forzahorizon6.exe`，区分 Steam 与 Xbox 的目录结构，并在需要时创建模组文件夹。识别完成后，已有模组会直接显示在宫格中。  
The manager automatically looks for `forzahorizon6.exe`, identifies the Steam or Xbox folder layout, and creates the mod folder if needed. Existing mods then appear in the grid.

| 游戏版本 / Edition | 游戏程序 / Game executable | 模组目录 / Mod folder | 原版车辆校验目录 / Original car folder for validation |
| --- | --- | --- | --- |
| Steam | `Forza Horizon 6\forzahorizon6.exe` | `Forza Horizon 6\mediapc\cars` | `Forza Horizon 6\media\cars` |
| Xbox | `Forza Horizon 6\Content\forzahorizon6.exe` | `Forza Horizon 6\Content\mediapc\Cars` | `Forza Horizon 6\Content\media\cars` |

如果自动检测失败，在 **设置** 页选择游戏 EXE 或手动指定模组文件夹。使用自定义位置时，也要确认原版车辆校验目录正确。  
If detection fails, open **Settings** and select the game EXE or specify the mod folder manually. When using a custom location, also check that the original car folder used for filename validation is correct.

### 3. 导入车辆模组 / Import car mods

将一个或多个车辆 `.zip` 文件拖入程序窗口，或点击 **导入车辆 ZIP / Import ZIP** 选择文件。无需解压车辆 ZIP。  
Drag one or more car `.zip` files into the window, or click **Import ZIP** to select them. Do not extract the car ZIP files.

拖入时会显示高亮提示和 ZIP 数量；安装过程中显示当前文件、处理阶段和进度。进度表示已处理的工作量，拒绝或跳过的文件也算已处理，请以完成提示中的结果为准。  
Dragging ZIP files into the window displays a highlight and file count. During installation, the manager shows the current file, processing stage and progress. Progress includes rejected or skipped files, so check the completion message for the actual result.

导入文件的名称必须以原版 `media\cars` 文件夹中的某个车辆文件名开头，不区分大小写。浏览器下载时添加的 `(1)` 等后缀可以直接导入，管理器会在模组目录中改为它支持的命名：没有同名版本时使用原始车辆文件名，已有时作为禁用的备用版本保存。车辆名称后面必须是空格、括号、下划线、短横线等分隔符；有多个车辆名称符合时，使用最长的那个。  
The filename must start with a car filename from the original `media\cars` folder; matching is case-insensitive. Browser suffixes such as `(1)` can be imported as they are: the manager renames the file in the mod folder to its own naming, using the original car filename when that car has no version yet, or saving it as a disabled backup version otherwise. The car name must be followed by a separator such as a space, bracket, underscore or hyphen; when several car names fit, the longest one is used.

例如，原版目录中有 `Example_Car.zip`：  
For example, if the original folder contains `Example_Car.zip`:

| 文件名 / Filename | 结果 / Result |
| --- | --- |
| `Example_Car.zip` | 导入为 / Imported as `Example_Car.zip` |
| `example_car.ZIP` | 导入为 / Imported as `Example_Car.zip` |
| `Example_Car (1).zip` | 导入并改名 / Imported and renamed to `Example_Car.zip` |
| `Example_Car_Custom.zip` | 导入并改名 / Imported and renamed to `Example_Car.zip` |
| `Example_Car2.zip` | 拒绝导入 / Rejected（车辆名后不是分隔符 / no separator after the car name） |
| `Other_Car.zip` | 拒绝导入 / Rejected（不以车辆文件名开头 / does not start with a car filename） |

已有同名版本时，新文件保存为 `Example_Car__fh6mm_v1.zipdisabled` 等禁用版本。导入完成的提示会列出所有被改名的文件。导入会复制文件到模组目录，保留下载的原文件，也不会覆盖原版车辆目录中的文件；如果 `Example_Car (1).zip` 这类文件已经在模组目录中，导入它会直接就地改名。  
If the car already has a version, the new file is saved as a disabled version such as `Example_Car__fh6mm_v1.zipdisabled`. The completion message lists every renamed file. Importing copies the file into the mod folder, preserves the downloaded original and does not overwrite files in the original car folder; if a file such as `Example_Car (1).zip` is already in the mod folder, importing it renames it in place.

### 4. 启用、禁用与切换版本 / Enable, disable and switch versions

单击车辆卡片后，使用底部按钮管理该模组；也可以双击卡片切换启用状态。  
Click a vehicle card and use the buttons at the bottom to manage it. You can also double-click a card to toggle its enabled state.

- **启用 / Enable**：让所选版本使用游戏识别的车辆 ZIP 文件名。  
  Give the selected version the car ZIP filename recognized by the game.
- **禁用 / Disable**：将扩展名改为 `.zipdisabled`。  
  Change the extension to `.zipdisabled`.
- **仅启用此版本 / Use this variant**：启用所选版本，同时禁用该车辆的其他版本。  
  Enable the selected version and disable the other versions of that car.

同一车辆可以保留多份模组，但最多同时启用一份。备用版本会自动添加区分后缀；切换时，管理器会自动调整名称，无需手动交换文件名。  
You can keep multiple mods for the same car, with at most one enabled at a time. Backup versions receive distinguishing suffixes automatically. The manager adjusts their names when switching, so you do not need to swap filenames manually.

### 5. 搜索与筛选 / Search and filter

左侧可筛选 **全部模组、已启用、已禁用、同名版本**。搜索框按文件名查找，可与筛选同时使用。  
Use the sidebar to show **All mods, Enabled, Disabled or Variants**. Search by filename using the search box; search and filters can be combined.

### 6. 自动缩略图与手动重试 / Automatic previews and retries

程序会为可见的车辆卡片自动生成预览并保存结果，禁用的模组也可以生成缩略图。预览可能与游戏内显示不同。  
The manager automatically generates and saves previews for visible vehicle cards, including disabled mods. Previews may differ from the in-game appearance.

生成失败后会显示 **预览失败 · 手动重试 / Preview failed · Retry manually**。重启管理器不会反复尝试。选中车辆并点击 **重建所选缩略图 / Rebuild preview**，可手动重试，仅影响所选模组。  
After a failure, the card displays **Preview failed · Retry manually**. Restarting the manager does not repeatedly retry it. Select the vehicle and click **Rebuild preview** to retry only that mod.

更换模组内容后允许重新生成。游戏启动、暂停或关闭管理器造成的中断，不会被记为预览失败。  
Replacing the mod’s contents allows a new preview attempt. Interruptions caused by starting the game, pausing generation or closing the manager are not recorded as preview failures.

### 7. 手动导入缩略图 / Import a custom preview

1. 选中需要更换图片的车辆卡片。  
   Select the vehicle card whose picture you want to change.
2. 点击底部 **导入缩略图 / Import preview**。  
   Click **Import preview** at the bottom.
3. 选择一张 **PNG、JPG / JPEG、WebP 或 BMP** 图片。  
   Choose a **PNG, JPG / JPEG, WebP or BMP** image.

图片会自动校正方向、等比例缩放并居中留边，不拉伸、不裁切；透明区域使用预览背景色，动画图片使用第一帧。  
The image is automatically oriented, resized proportionally and centered with padding, without stretching or cropping. Transparent areas use the preview background color. Animated images use their first frame.

手动图片优先于自动预览，即使自动生成失败或没有安装渲染组件，也可以使用。取消选择或导入失败时，原有图片会保留，所选图片和车辆 ZIP 均不会被修改。  
Custom pictures take priority over automatic previews and work even if automatic generation fails or the rendering component is unavailable. Cancelling or a failed import preserves the previous picture. Neither the selected image nor the car ZIP is modified.

图片仅绑定所选模组文件。重启、启用、禁用及同名版本改名后仍会保留，不会同时替换其他文件的图片。重新复制为另一个文件或更换模组内容后，需要重新指定图片。  
The picture belongs only to the selected mod file. It survives restarts, enabling, disabling and variant renames without changing other files’ pictures. If you create a new copy or replace the mod’s contents, assign a picture again.

**再次导入可替换手动图片；点击“重建所选缩略图”会移除手动图片并尝试自动生成。**  
**Import another image to replace the custom picture. Clicking “Rebuild preview” removes it and attempts automatic generation.**

### 8. 删除模组 / Delete a mod

选中卡片，点击 **删除所选模组 / Delete**，核对文件名后确认。默认交由 Windows 回收站处理；请留意系统显示的删除提示。  
Select a card, click **Delete**, check the filename and confirm. The manager normally sends the file to the Windows Recycle Bin; pay attention to any system deletion prompts.

删除只影响选中的一份文件，不会连带删除同名其他版本。删除启用版本后，不会自动启用备用版本。成功后卡片消失，其余卡片补位；失败时保留卡片并提示错误。  
Only the selected file is deleted; other versions of the same car remain. Deleting an enabled version does not automatically enable a backup. After successful deletion, its card disappears and the remaining cards move into place. On failure, the card stays and an error is shown.

### 9. 更改语言 / Change the language

打开 **设置 → 界面语言 / Language**，选择 **简体中文** 或 **English**。更改立即生效，并在下次打开时保留。  
Open **Settings → Language** and choose **简体中文** or **English**. The change takes effect immediately and is remembered for the next launch.

### 10. 游戏运行锁定 / Game-running protection

游戏运行时，操作按钮、拖放和设置修改会被锁定，自动预览生成也会暂停。退出游戏后恢复操作。无法确认游戏状态时同样保持锁定。  
While the game is running, action buttons, drag-and-drop and settings changes are locked, and automatic preview generation is paused. Controls become available again after the game exits. They also remain locked when the game’s status cannot be confirmed.

文件操作期间请等待完成。锁定期间的拖放请求不会在解锁后补执行，需要重新拖入。  
Wait for ongoing file operations to finish. Drops made while controls are locked are not carried out later; drag the files in again after unlocking.

### 11. 查看与清理缩略图 / Find and clear preview images

按 **Win + R**，粘贴以下路径并回车：  
Press **Win + R**, paste the following path and press Enter:

`%LOCALAPPDATA%\FH6CarModManager\thumbnails`

自动生成的图片默认最多保留 **256 MiB**，并清理 **30 天未访问**的旧预览。该限额不包括生成过程中的临时空间和手动图片。  
Automatically generated images have a default **256 MiB** limit, with old previews cleared after **30 days without access**. This limit excludes temporary generation space and custom pictures.

手动导入的图片单独保存在：  
Custom pictures are stored separately in:

`%LOCALAPPDATA%\FH6CarModManager\thumbnails\manual`

手动图片不会被自动缓存清理删除。已删除或已替换的模组可能留下旧图片；需要清理时，请先关闭管理器。清空此文件夹会移除全部手动缩略图，但不会删除车辆模组。  
Automatic cache cleanup does not remove custom pictures. Deleted or replaced mods may leave old pictures behind; close the manager before cleaning them up. Emptying this folder removes all custom previews but does not delete any car mods.

如果只是想重新生成某一辆车的图片，请使用 **重建所选缩略图**，无需清空整个缓存目录。  
To regenerate just one vehicle’s picture, use **Rebuild preview** instead of clearing the entire cache folder.

## 更新内容 / Release notes

### v0.8.8 — 支持下载副本文件名 / Import download copies

- 文件名以原版车辆文件名开头即可导入，例如浏览器下载时变成的 `Example_Car (1).zip`；车辆名后须是空格、括号、下划线、短横线等分隔符，多个车辆名称符合时取最长的。  
  Files whose names start with an original car filename can be imported, such as browser copies like `Example_Car (1).zip`; the car name must be followed by a separator (space, bracket, underscore, hyphen…), and the longest matching car name wins.
- 导入后在模组目录中自动改为管理器命名：没有同名版本时使用原始车辆文件名，已有时保存为禁用的备用版本。  
  Imported files are renamed in the mod folder to the manager naming: the original car filename when the car has no version yet, otherwise a disabled backup version.
- 已在模组目录中的 `Example_Car (1).zip` 类文件，导入时直接就地改名。  
  Files such as `Example_Car (1).zip` that are already in the mod folder are renamed in place when imported.
- 导入完成的提示列出所有被改名的文件。  
  The import summary lists every renamed file.

### v0.8.7 — 缩略图提速与省空间 / Faster thumbnails, less disk

- 已生成过的缩略图在重启后直接显示，不再每次启动重新读取全部模组和原版车辆文件（文件内容摘要按文件身份持久记录）。  
  Previews that already exist appear right after a restart; content hashes are remembered per file, so launches no longer re-read every mod and original car.
- 原版车辆 ZIP 不再复制到临时目录；渲染组件只合并缩略图实际用到的文件（模型、材质、贴图），并直接复制已压缩的数据，不再解压后重新压缩。  
  The original car ZIP is no longer copied; the renderer merges only the files a thumbnail uses (models, materials, textures) and copies their compressed data as is instead of decompressing and recompressing.
- 渲染组件只解析一次每个 ZIP 的目录，游戏贴图并行解码，贴图最大使用 1024 px 的 mip 级别，内存与显存占用更低。  
  The renderer parses each ZIP directory once, decodes game textures in parallel and uses texture mip levels up to 1024 px, lowering memory and video memory use.
- 缓存的缩略图以 512×288 优化 PNG 保存，约为原来的一半大小；旧缓存在下次显示时自动压缩。  
  Cached previews are stored as optimised 512×288 PNGs, about half the previous size; older cached previews shrink the next time they are shown.
- 渲染组件以较低优先级运行，屏幕上可见的卡片优先生成。  
  The renderer runs at lower priority, and cards on screen are generated first.
- 生成缩略图时不再弹出渲染窗口：窗口放在所有显示器之外，也不出现在任务栏和 Alt+Tab 中。排查问题时可设置环境变量 `FH6MM_RENDER_VISIBLE=1` 让窗口照常显示。  
  Generating previews no longer pops up the renderer window: it stays beyond every monitor and out of the taskbar and Alt+Tab. Set the environment variable `FH6MM_RENDER_VISIBLE=1` to show it again when troubleshooting.
- 更新后渲染组件已更换，已有缩略图会按新组件重新生成一次。  
  Because the renderer changed, existing previews are regenerated once with the new renderer.

### v0.8.6 — PCL 风格界面 / PCL-style interface

- 参考 PCL2 的界面库重绘全部界面：PCL 配色，48 px 渐变标题栏与带图标的胶囊页签，当前页为白底蓝字。  
  Redrew the whole interface after PCL2's UI library: PCL colours, a 48 px gradient title bar with pill-shaped icon tabs, the current page shown as a white pill.
- 白色侧边栏：筛选项带图标、选中强调条与实时数量。  
  White sidebar: filters with icons, an accent bar on the selected item and live counts.
- 卡片采用 6 px 圆角与柔和阴影，悬停时阴影和标题变蓝；模组卡片显示选中勾、状态标签与粗体文件名，宫格居中排列。  
  Cards have 6 px corners and soft shadows that turn blue on hover; mod cards show a selection check, status pills and bold file names, and the grid is centred.
- 描边按钮分普通、蓝色和红色（删除）三种并配图标；新增带图标与占位文字的搜索框；滚动条变细，无内容可滚动时自动隐藏。  
  Outlined buttons in normal, blue and red (delete) styles with icons; a search box with icon and placeholder; slimmer scroll bars that hide when there is nothing to scroll.
- 修复部分控件调用 `configure()` 时出错的问题。  
  Fixed an error when calling `configure()` on some controls.

### v0.8.5 — 动画引擎重写 / Motion engine rewrite

- 参考 PCL 的动画模块重写动画引擎：全部控件共用一个按帧对齐的时钟，支持 Fluent / Back 缓动与叠加动画；Windows 上动画期间提高系统计时精度，消除 16/31 ms 交替造成的抖动。  
  Rewrote the animation engine after PCL's animation module: every control shares one frame-aligned clock with Fluent/Back easing and additive tweens; on Windows the system timer resolution is raised while animating, removing 16/31 ms frame jitter.
- 动画帧不再读取文件；缩略图在后台线程解码缩放，滚动和悬停不再卡顿。游戏进程检测与目录扫描移到后台线程。  
  Animation frames no longer touch the disk; thumbnails are decoded and scaled on a worker thread, so scrolling and hover stay smooth. Game detection and folder scans run on background threads.
- 画布元素只在数值变化时重绘，卡片按整像素移动；状态检测不再每秒重设全部按钮和文字，消除周期性闪烁。  
  Canvas items are only repainted when a value changes and cards move by whole pixels; periodic status checks no longer reconfigure every button and label, removing the once-per-second flicker.
- 新的 PCL 式动效：页面自上方落入并轻微回弹，卡片依次落入、删除时缩小淡出、其余卡片平滑补位；按钮悬停渐变、按下微缩；侧栏选中项出现强调条；卡片悬停描边加深；滚轮叠加平滑滚动。  
  New PCL-style motion: pages drop in with a slight overshoot, cards drop in one after another, shrink and fade when removed while the rest glide into place; buttons fade on hover and dip when pressed; the selected sidebar item grows an accent bar; cards deepen their outline on hover; the mouse wheel scrolls smoothly with additive easing.

### v0.8.4 — 手动缩略图 / Custom previews

- 新增 **导入缩略图**，支持 PNG、JPEG、WebP 和 BMP。  
  Added **Import preview**, supporting PNG, JPEG, WebP and BMP.
- 手动图片按模组独立保存，重启及切换启用状态后保留，并优先显示。  
  Custom pictures are saved separately for each mod, survive restarts and enabled-state changes, and take priority over automatic previews.
- 自动校正图片方向并等比例适配；导入失败保留旧图。  
  Images are automatically oriented and fitted proportionally; failed imports preserve the previous picture.
- 支持通过 **重建所选缩略图** 恢复自动生成。  
  Use **Rebuild preview** to return to automatic generation.

### v0.8.3 — 交互与动画 / Interaction and animation

- 优化页面切换，修复动画结束时的闪烁，并改善连续切换的衔接。  
  Improved page transitions, fixed flicker at the end of animations, and made rapid navigation smoother.
- 改善卡片刷新、悬停、选中和启用状态的过渡。  
  Improved card refreshes and transitions for hover, selection and enabled states.
- 新增 ZIP 拖入高亮、文件数量提示和安装进度动效。  
  Added ZIP drag-over highlighting, file-count feedback and animated installation progress.
- 删除成功后卡片收拢消失，其余卡片平滑补位。  
  Successfully deleted cards collapse away while the remaining cards move smoothly into place.
- 新增交互提示支持中英文，并遵循游戏运行锁定。  
  New interaction messages support Chinese and English and respect game-running protection.

### v0.8.2 — 记住预览失败状态 / Remember failed previews

- 预览失败后保存记录，重启不再反复尝试。  
  Preview failures are remembered, preventing repeated attempts after restarting.
- 启用、禁用及同名版本改名不会触发失败预览的自动重试。  
  Enabling, disabling and variant renames do not automatically retry failed previews.
- 保留所选车辆的手动重试；更换模组内容后可重新生成。  
  Manual retries remain available for the selected vehicle, and replacing a mod’s contents allows a new attempt.
- 游戏启动、暂停或关闭程序造成的中断不计为生成失败。  
  Interruptions caused by starting the game, pausing or closing the manager are not counted as generation failures.

---

**BY：bilibili \_-菠小萝-\_**
