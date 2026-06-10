@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

if "%~1"=="" (
    echo 用法: compressimg ^<图片文件1^> [^<图片文件2^> ...]
    echo 示例: compressimg 123.jpg
    echo 说明: 支持 .jpg .jpeg .png .webp，输出文件自动加 s 后缀
    pause
    exit /b 1
)

:loop
if "%~1"=="" goto end

set "input=%~1"

if not exist "%input%" (
    echo 文件不存在: %input%
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
echo [压缩] %input%
echo [输出] !output!

if /i "%ext%"==".jpg" (
    ffmpeg -y -i "%input%" -q:v 8 "!output!" >nul 2>&1
) else if /i "%ext%"==".jpeg" (
    ffmpeg -y -i "%input%" -q:v 8 "!output!" >nul 2>&1
) else if /i "%ext%"==".png" (
    ffmpeg -y -i "%input%" -compression_level 9 "!output!" >nul 2>&1
) else if /i "%ext%"==".webp" (
    ffmpeg -y -i "%input%" -q:v 75 "!output!" >nul 2>&1
) else (
    echo 不支持的格式: %ext%
    shift
    goto loop
)

if exist "!output!" (
    echo 完成 ^(压缩后: !output!^)
) else (
    echo 压缩失败
)

shift
goto loop

:end
endlocal
