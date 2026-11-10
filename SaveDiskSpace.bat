@echo off
setlocal
rem Optional: compress this program's files with the NTFS compression built into Windows
rem (compact /EXE:LZX).  Nothing is deleted and everything runs as before; Windows unpacks
rem files in memory as they are read.  "SaveDiskSpace.bat /undo" restores the originals.
for /f "tokens=2 delims=:" %%c in ('chcp') do set "FH6_OLD_CP=%%c"
chcp 65001 >nul
cd /d "%~dp0"
title FH6 Car Mod Manager - 节省硬盘空间
echo.
echo  FH6 车辆模组管理器 - 节省硬盘空间
echo  ----------------------------------------
echo  用 Windows 自带的 NTFS 压缩功能压缩本文件夹里的程序文件。
echo  不删除任何文件，程序照常运行，通常能让本文件夹的实际占用减少一半以上。
echo  需要 NTFS 格式的磁盘（绝大多数电脑都是）。重新解压新版本后可以再运行一次。
echo  还原：在命令行运行 SaveDiskSpace.bat /undo
echo.
tasklist /fi "imagename eq FH6CarModManager.exe" 2>nul | find /i "FH6CarModManager.exe" >nul
if not errorlevel 1 goto running
tasklist /fi "imagename eq ForzaTech Studio.exe" 2>nul | find /i "ForzaTech Studio.exe" >nul
if not errorlevel 1 goto running
if /i "%~1"=="/undo" goto undo

echo  正在压缩，可能需要一两分钟，请不要关闭这个窗口……
echo.
compact /c /s /i /q /exe:lzx
echo.
echo  完成。上面的“压缩率”就是现在的实际占用比例（文件夹“属性”里的“占用空间”也会变小）。
goto done

:undo
echo  正在还原为未压缩的文件……
echo.
compact /u /s /i /q /exe
echo.
echo  已还原。
goto done

:running
echo  请先关闭 FH6 车辆模组管理器（以及正在生成缩略图的渲染器），再运行本工具。

:done
echo.
pause
if defined FH6_OLD_CP chcp %FH6_OLD_CP% >nul
endlocal
