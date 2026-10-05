@echo off
chcp 65001 >nul
title How to Fish - Roulette Payout Patch (2x to 20x)
rem 会自动查找 Steam 游戏目录；找不到会提示你粘贴/拖入 Assembly-CSharp.dll 路径。
rem 也可手动指定：在本文件后加 -GameDll "D:\...\Assembly-CSharp.dll"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-RouletteMod.ps1" %*
