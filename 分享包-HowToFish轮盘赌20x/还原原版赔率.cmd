@echo off
chcp 65001 >nul
title How to Fish - Restore Original Payout
rem 还原成原版 2x。会自动查找 Steam 游戏目录。
rem 也可手动指定：在本文件后加 -GameDll "D:\...\Assembly-CSharp.dll"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-RouletteMod.ps1" -Revert %*
