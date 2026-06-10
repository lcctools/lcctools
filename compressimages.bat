@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo 请拖入图片文件
    pause
    exit
)

:loop

if "%~1"=="" goto end

set "input=%~1"

if not exist "%input%" (
    shift
    goto loop
)

set "folder=%~dp1"
set "name=%~n1"
set "ext=%~x1"

set count=1

:findname
set "output=%folder%%name%s!count!!ext!"

if exist "!output!" (
    set /a count+=1
    goto findname
)

echo.
echo 正在压缩:
echo %input%
echo 输出:
echo !output!

:: jpg/jpeg
if /i "%ext%"==".jpg" (
    ffmpeg -y -i "%input%" -q:v 8 "!output!"
)

if /i "%ext%"==".jpeg" (
    ffmpeg -y -i "%input%" -q:v 8 "!output!"
)

:: png
if /i "%ext%"==".png" (
    ffmpeg -y -i "%input%" -compression_level 9 "!output!"
)

:: webp
if /i "%ext%"==".webp" (
    ffmpeg -y -i "%input%" -q:v 75 "!output!"
)

echo 完成

shift
goto loop

:end
exit