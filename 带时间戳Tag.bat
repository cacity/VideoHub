@echo off
chcp 65001
title 一键打Tag 上传代码（带时间戳版）

setlocal enabledelayedexpansion

:: 处理日期，去掉星期几
for /f "tokens=2 delims= " %%i in ('date /t') do set today=%%i

:: 处理时间，去掉前面的空格
for /f "tokens=1-2 delims=: " %%i in ('time /t') do (
    set hh=%%i
    set min=%%j
)

:: 日期分割
set yyyy=%today:~0,4%
set mm=%today:~5,2%
set dd=%today:~8,2%

:: 时间补零（如果小时或分钟是一位数）
if 1%hh% LSS 110 (
    set hh=0%hh%
)
if 1%min% LSS 110 (
    set min=0%min%
)


:: 生成Tag
set tag_name=v%yyyy%-%mm%%dd%-%hh%%min%

echo 自动生成的Tag名称为：%tag_name%

:: 读取提交信息
echo 请输入提交信息（留空则跳过提交）：
set /p commit_message=

echo 🔍 当前 Git 状态：
git status

:: 如果有提交，提交并推送
if not "%commit_message%"=="" (
    echo 📝 添加所有修改并提交...
    git add .
    git commit -m "%commit_message%"
    git push
) else (
    echo ⚡️ 跳过提交，直接打Tag。
)

:: 打Tag
echo 🏷️ 创建Tag: %tag_name%
git tag -a %tag_name% -m "发布 %tag_name%"

:: 推送Tag
echo 🚀 推送代码和Tag到远程...
git push
git push origin %tag_name%

echo ✅ 完成！项目已经打Tag并上传。
pause
