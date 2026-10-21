# 第三方来源与修改记录

本包内 `vendor/ForzaTechStudio` 来源于：

- https://github.com/D3FEKT/ForzaTechStudio
- 固定提交：`4f373c5fb192551ce5249e320dd79b1399b693ca`
- 原始许可文件完整保留于 `vendor/ForzaTechStudio/LICENSE`（MIT，Copyright (c) 2023 Nenkai）。
- 该目录包含上游自带的原生依赖；保留原始文件及上游声明，未将游戏资源加入分发包。

本次修改：

- `ThumbnailJob.cs`：请求协议、临时原版/模组条目组合、游戏进程保护、错误输出。
- `Views/ViewportPage.Thumbnail.cs`：加载真实场景、等待贴图、固定相机、捕获 Direct3D 缓冲区 PNG。
- `App.xaml.cs`：添加 `--fh6-thumbnail-request <json>` 专用启动分支。
- `Views/ViewportPage.xaml.cs`、`Views/ViewportPage.FileLoading.cs`：缩略图模式避免重复的异步贴图加载和文件监视。
- `Services/SettingsService.cs`：缩略图模式使用独立设置路径。
- `ForzaTechStudio.csproj`：专用构建保留标准输出目录结构；上游未附带的动画 ACL DLL 设为可选。静态车辆缩略图不依赖动画播放。

渲染调用基于上游已引用的 HelixToolkit.WinUI 2.27.3 / SharpDX。
相关接口已对照 https://github.com/helix-toolkit/helix-toolkit 的 v2.27.3 源码检查。
各 NuGet/Python 依赖继续遵循其自身许可证；发布时保留依赖附带的许可与版权声明。

本工具不是 Forza、Xbox 或 ForzaTech Studio 的官方产品。

## 界面参考

0.7.0 的蓝白配色与导航、卡片布局参考 [Plain Craft Launcher](https://github.com/Meloong-Git/PCL)。本项目使用 Tk 独立实现，未复制或分发 PCL 源码、图片、图标或标识；不是 PCL 官方产品。

## 0.8.0 独立渲染构建

- 新增 `FH6ThumbnailRenderer.csproj`，以显式文件清单编译渲染所需的共享源码；完整上游源码继续保留供审查。
- `App.xaml.cs` 和 `MaterialShaderParametersViewModel.cs` 用 `FH6_THUMBNAIL` 条件隔离主编辑器入口及页面返回逻辑。
- `ThumbnailJob.cs` 的临时组合 ZIP 改为快速压缩，游戏和模组原文件保持不变。
- 独立工程不引用 Markdown 组件，不发布编辑器宣传素材、文档和预设；保留渲染和资源查找依赖及原许可声明。

## 0.8.1 资源构建修复

恢复独立工程遗漏的 `EnableMsixTooling`，明确 MRT / PRI 和 XAML 元数据设置，补充启动资源诊断；原有渲染自检保持必需。
