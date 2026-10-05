# Install-RouletteMod.ps1
# 把《How to Fish》轮盘赌的红/黑赔率改成 20 倍（绿色保持 35 倍）
#
# 用法（任选其一）：
#   1) 右键本文件 → "使用 PowerShell 运行"
#   2) 双击同目录的「安装轮盘赌补丁.cmd」
#   3) powershell -ExecutionPolicy Bypass -File "本文件路径"
#
# 还原：双击「还原原版赔率.cmd」，或加 -Revert 运行本脚本。
#
# ---- 设计要点（针对游戏更新）------------------------------------------------
# 本脚本**不硬编码文件偏移、也不依赖固定哈希**来判断版本：
#   它按字节特征在 DLL 里搜索 ServerRouletteResult 的 switch 结构，
#   因此游戏更新导致偏移变化后依然可用；只要轮盘逻辑没改，补丁就有效。
# 已用两代游戏验证：
#   旧版 870400 字节 (Unity 6000.0.x)  IL_0000 偏移 0x1C1D5
#   新版 910848 字节 (Unity 6000.4.4f1) IL_0000 偏移 0x1E734
#
# 备份策略：$GameDll.bak 保存的必须是**当前这个游戏版本的原版 DLL**。
#   如果发现 .bak 属于旧版本（游戏刚更新过），会自动把它改名归档成
#   Assembly-CSharp.dll.bak.old-<哈希前8位>，再生成新的 .bak，
#   避免「还原」时把游戏 DLL 换回旧版本导致游戏崩溃。

param(
  [string]$GameDll = '',
  [int]$RedBlackMultiplier = 20,
  [int]$GreenMultiplier = 35,
  [switch]$Revert,
  [switch]$WhatIf,
  [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$RB = [byte]($RedBlackMultiplier -band 0xFF)
$GR = [byte]($GreenMultiplier -band 0xFF)

# ---- 原始 / 补丁 两种字节特征（30 字节，-1 = 通配）----
$ANCHOR_ORIGINAL = [int[]]@(
  0x45,0x03,0x00,0x00,0x00, 0x02,0x00,0x00,0x00, 0x06,0x00,0x00,0x00, 0x0A,0x00,0x00,0x00,
  0x2B,0x0B, 0x18,0x0B,0x2B,0x07, 0x18,0x0B,0x2B,0x03, 0x1F,0x23,0x0B
)
$ANCHOR_PATCHED = [int[]]@(
  0x45,0x03,0x00,0x00,0x00, 0x02,0x00,0x00,0x00, 0x02,0x00,0x00,0x00, 0x0A,0x00,0x00,0x00,
  0x2B,0x0B, 0x1F,-1,0x0B,0x2B,0x06, 0x00,0x00,0x00, 0x1F,-1,0x0B
)
$BLOCK_FROM_ANCHOR = 19      # IL_0022 相对 switch 表起点

$ORIGINAL_BLOCK  = [byte[]]@(0x18,0x0B,0x2B,0x07, 0x18,0x0B,0x2B,0x03, 0x1F,0x23,0x0B)

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Pause-Exit([int]$code, [string]$msg = '按回车退出') {
  if (-not $NonInteractive) { Read-Host $msg | Out-Null }
  exit $code
}

function Get-Sha([byte[]]$bytes) {
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '') }
  finally { $sha.Dispose() }
}
function Get-FileSha([string]$p) { Get-Sha ([System.IO.File]::ReadAllBytes($p)) }

# ---- 自动定位游戏 DLL（方便分享给别人：不用改脚本里的路径）----
$DLL_TAIL = 'How to Fish_Data\Managed\Assembly-CSharp.dll'

function Get-SteamLibraries {
  $steamRoots = New-Object System.Collections.ArrayList
  foreach ($k in @('HKCU:\Software\Valve\Steam',
                   'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam',
                   'HKLM:\SOFTWARE\Valve\Steam')) {
    try {
      $p = Get-ItemProperty -Path $k -ErrorAction Stop
      foreach ($n in @('SteamPath', 'InstallPath')) {
        if ($p.PSObject.Properties[$n] -and $p.$n) { [void]$steamRoots.Add([string]$p.$n) }
      }
    } catch { }
  }
  foreach ($d in @('C:\Program Files (x86)\Steam', 'C:\Program Files\Steam',
                   'D:\Steam', 'E:\Steam', 'D:\SteamLibrary', 'E:\SteamLibrary')) {
    [void]$steamRoots.Add($d)
  }

  $libs = New-Object System.Collections.ArrayList
  foreach ($root in $steamRoots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    [void]$libs.Add($root)
    $vdf = Join-Path $root 'steamapps\libraryfolders.vdf'
    if (Test-Path -LiteralPath $vdf) {
      $txt = Get-Content -LiteralPath $vdf -Raw -ErrorAction SilentlyContinue
      if ($txt) {
        foreach ($m in [regex]::Matches($txt, '"path"\s+"([^"]+)"')) {
          $lp = $m.Groups[1].Value -replace '\\\\', '\'
          if (Test-Path -LiteralPath $lp) { [void]$libs.Add($lp) }
        }
      }
    }
  }
  return ($libs | Select-Object -Unique)
}

function Find-GameDll {
  $libs = Get-SteamLibraries
  $cands = New-Object System.Collections.ArrayList
  foreach ($lib in $libs) {
    # 常见两种目录层级都试
    [void]$cands.Add((Join-Path $lib "steamapps\common\How to Fish\How to Fish\$DLL_TAIL"))
    [void]$cands.Add((Join-Path $lib "steamapps\common\How to Fish\$DLL_TAIL"))
  }
  foreach ($c in $cands) {
    if (Test-Path -LiteralPath $c -PathType Leaf) { return $c }
  }
  # 兜底：在 Steam 库的 common\How to Fish 下递归找
  foreach ($lib in $libs) {
    $root = Join-Path $lib 'steamapps\common\How to Fish'
    if (-not (Test-Path -LiteralPath $root)) { continue }
    $hit = Get-ChildItem -LiteralPath $root -Recurse -Filter 'Assembly-CSharp.dll' -ErrorAction SilentlyContinue |
           Where-Object { $_.DirectoryName -like '*How to Fish_Data\Managed' } |
           Select-Object -First 1
    if ($hit) { return $hit.FullName }
  }
  return $null
}

function Resolve-GameDll([string]$p) {
  if (-not $p) { return $null }
  $p = $p.Trim()
  if ($p.StartsWith('&')) { $p = $p.Substring(1).Trim() }        # 拖拽进来会带 & 前缀
  $p = $p.Trim('"').Trim("'").Trim()
  if (-not $p) { return $null }
  if (Test-Path -LiteralPath $p -PathType Container) {
    $c = Join-Path $p $DLL_TAIL
    if (Test-Path -LiteralPath $c -PathType Leaf) { return $c }
    $c = Join-Path $p 'Assembly-CSharp.dll'
    if (Test-Path -LiteralPath $c -PathType Leaf) { return $c }
    return $null
  }
  if (Test-Path -LiteralPath $p -PathType Leaf) { return $p }
  return $null
}

function Find-Anchor([byte[]]$bytes, [int[]]$pat) {
  $hits = New-Object System.Collections.ArrayList
  $start = 0
  while ($true) {
    $i = [Array]::IndexOf($bytes, [byte]$pat[0], $start)
    if ($i -lt 0) { break }
    if ($i + $pat.Length -le $bytes.Length) {
      $ok = $true
      for ($j = 1; $j -lt $pat.Length; $j++) {
        if ($pat[$j] -lt 0) { continue }
        if ($bytes[$i + $j] -ne [byte]$pat[$j]) { $ok = $false; break }
      }
      if ($ok) { [void]$hits.Add($i) }
    }
    $start = $i + 1
  }
  return $hits
}

function Get-State([byte[]]$bytes) {
  $o = Find-Anchor $bytes $ANCHOR_ORIGINAL
  if ($o.Count -eq 1) { return @{ State='Original'; Offset=$o[0]; RB=$null; GR=$null } }
  if ($o.Count -gt 1) { return @{ State='Ambiguous'; Offset=-1; Count=$o.Count } }
  $p = Find-Anchor $bytes $ANCHOR_PATCHED
  if ($p.Count -eq 1) {
    $b = $p[0] + $BLOCK_FROM_ANCHOR
    $rb = [int]$bytes[$b+1]; if ($rb -gt 127) { $rb -= 256 }
    $gr = [int]$bytes[$b+9]; if ($gr -gt 127) { $gr -= 256 }
    return @{ State='Patched'; Offset=$p[0]; RB=$rb; GR=$gr }
  }
  if ($p.Count -gt 1) { return @{ State='Ambiguous'; Offset=-1; Count=$p.Count } }
  return @{ State='Unknown'; Offset=-1 }
}

# 从任意状态还原出「当前游戏版本的原版 DLL」（内存中，不写盘）
function Get-Pristine([byte[]]$bytes, $st) {
  $copy = [byte[]]::new($bytes.Length)
  [Array]::Copy($bytes, $copy, $bytes.Length)
  if ($st.State -eq 'Original') { return $copy }
  if ($st.State -ne 'Patched') { return $null }
  $o = $st.Offset
  $copy[$o+9] = 0x06; $copy[$o+10] = 0x00; $copy[$o+11] = 0x00; $copy[$o+12] = 0x00
  for ($k = 0; $k -lt $ORIGINAL_BLOCK.Length; $k++) { $copy[$o + $BLOCK_FROM_ANCHOR + $k] = $ORIGINAL_BLOCK[$k] }
  return $copy
}

function New-Patched([byte[]]$pristine) {
  $st = Get-State $pristine
  if ($st.State -ne 'Original') { throw '内部错误：原始副本未通过原版校验。' }
  $o = $st.Offset
  $copy = [byte[]]::new($pristine.Length)
  [Array]::Copy($pristine, $copy, $pristine.Length)
  $copy[$o+9] = 0x02; $copy[$o+10] = 0x00; $copy[$o+11] = 0x00; $copy[$o+12] = 0x00
  $blk = [byte[]]@(0x1F,$RB, 0x0B, 0x2B,0x06, 0x00,0x00,0x00, 0x1F,$GR, 0x0B)
  for ($k = 0; $k -lt $blk.Length; $k++) { $copy[$o + $BLOCK_FROM_ANCHOR + $k] = $blk[$k] }
  return $copy
}

# ======================================================================
Say ''
Say '=== How to Fish 轮盘赌红黑赔率补丁 ===' Cyan
Say "     红/黑 -> ${RedBlackMultiplier}x    绿 -> ${GreenMultiplier}x" Cyan
Say ''

# ---- 0. 游戏是否在运行 ----
$proc = Get-Process -Name 'How to Fish' -ErrorAction SilentlyContinue
if ($proc) {
  Say "[X] 游戏正在运行 (PID $($proc.Id))，请先完全退出游戏再运行本脚本。" Red
  Pause-Exit 1
}

$rawInput = $GameDll
if (-not $GameDll) {
  Write-Host -NoNewline '正在自动查找游戏目录... '
  $found = Find-GameDll
  if ($found) {
    $GameDll = $found
    Say '找到了。' Green
  } else {
    Say '没找到。' Yellow
    Say ''
    Say '请把游戏里的 Assembly-CSharp.dll 完整路径填进来：' Cyan
    Say '  或直接把那个文件**拖进这个窗口**再回车。' Cyan
    Say '  典型位置：<Steam库>\steamapps\common\How to Fish\How to Fish\How to Fish_Data\Managed\Assembly-CSharp.dll' Cyan
    Say ''
    if ($NonInteractive) {
      Say '[X] 非交互模式下无法询问路径，请用 -GameDll 参数指定。' Red
      exit 1
    }
    $rawInput = Read-Host '路径'
    $GameDll = Resolve-GameDll $rawInput
  }
} else {
  $GameDll = Resolve-GameDll $GameDll
}

if (-not $GameDll -or -not (Test-Path -LiteralPath $GameDll -PathType Leaf)) {
  Say ''
  Say "[X] 找不到游戏文件：$rawInput" Red
  Say '    请确认路径指向游戏里的 Assembly-CSharp.dll，或用 -GameDll 参数指定，例如：' Red
  Say '    powershell -ExecutionPolicy Bypass -File .\Install-RouletteMod.ps1 -GameDll "D:\...\Assembly-CSharp.dll"' Red
  Pause-Exit 1
}

$bak = "$GameDll.bak"

$cur       = [System.IO.File]::ReadAllBytes($GameDll)
$curSha    = Get-Sha $cur
$curState  = Get-State $cur

Say "目标文件 : $GameDll"
Say "文件大小 : $($cur.Length) 字节"
Say "当前哈希 : $curSha"
switch ($curState.State) {
  'Original'  { Say '当前状态 : 原版（红/黑 2x，绿 35x）' Green }
  'Patched'   { Say "当前状态 : 已打补丁（红/黑 $($curState.RB)x，绿 $($curState.GR)x）" Yellow }
  'Ambiguous' { Say "当前状态 : !! 特征匹配到 $($curState.Count) 处，无法安全处理 !!" Red }
  default     { Say '当前状态 : !! 无法识别（可能被其它 Mod 改过，或游戏改了轮盘逻辑）!!' Red }
}
if ($curState.State -eq 'Original' -or $curState.State -eq 'Patched') {
  Say ("           IL_0000 文件偏移 0x{0:X}" -f ($curState.Offset - 0x0F))
}
Say ''

if ($curState.State -eq 'Ambiguous') {
  Say '[X] 特征不唯一，拒绝修改。请用 Steam「验证游戏文件完整性」恢复后再试。' Red
  Pause-Exit 1
}

# ---- 还原模式 ----
if ($Revert) {
  if ($curState.State -eq 'Original') {
    Say '[i] 当前已经是原版，无需还原。' Green
    Pause-Exit 0
  }
  if ($curState.State -eq 'Unknown') {
    Say '[X] 无法识别当前 DLL 的形态：它不是原版、也不是本补丁改出来的版本。' Red
    Say '    本脚本不会去覆盖它。建议：Steam → 右键游戏 → 属性 → 已安装文件 → 验证文件完整性。' Red
    Pause-Exit 1
  }
  $pristine = Get-Pristine $cur $curState
  $pristineSha = Get-Sha $pristine

  if (Test-Path -LiteralPath $bak) {
    $bakSha = Get-FileSha $bak
    if ($bakSha -eq $pristineSha) { Say '[i] 备份文件与还原目标一致，校验通过。' Green }
    else { Say '[!] 警告：.bak 与还原目标不一致（可能是旧版本备份），本次不用它，改用「就地反打补丁」。' Yellow }
  }

  if ($WhatIf) { Say "[-WhatIf] 未写入。还原后哈希会是 $pristineSha"; Pause-Exit 0 }

  [System.IO.File]::WriteAllBytes($GameDll, $pristine)
  $final = [System.IO.File]::ReadAllBytes($GameDll)
  $fs = Get-State $final
  Say ''
  Say "还原后哈希 : $(Get-Sha $final)"
  if ($fs.State -eq 'Original' -and (Get-Sha $final) -eq $pristineSha) {
    Say '[OK] 已还原为原版（红/黑 2x，绿 35x）。' Green
    Pause-Exit 0
  } else {
    Say '[!] 还原结果校验失败，请用 Steam「验证游戏文件完整性」。' Red
    Pause-Exit 1
  }
}

# ---- 安装模式 ----
if ($curState.State -eq 'Unknown') {
  Say '[X] 当前 DLL 既不是原版、也不是本补丁的产物，拒绝在其上打补丁。' Red
  Say '    建议先用 Steam「验证游戏文件完整性」恢复成原版，再运行本脚本。' Red
  Pause-Exit 1
}

$pristine    = Get-Pristine $cur $curState
$pristineSha = Get-Sha $pristine
$patchedBytes = New-Patched $pristine
$patchedSha   = Get-Sha $patchedBytes

if ($curSha -eq $patchedSha) {
  Say "[i] 目标文件已经是打过补丁的版本（红/黑 ${RedBlackMultiplier}x，绿 ${GreenMultiplier}x），无需重复安装。" Green
  Say ''
  Say '小提示：鼠标悬停在红/黑按钮上时提示文字仍然显示 x2 ——' Cyan
  Say '        那是按钮上的独立 UI 数字（BetButton._multiplier），不参与结算，属于已知外观差异。' Cyan
  Pause-Exit 0
}

Say "原版哈希   : $pristineSha"
Say "补丁后哈希 : $patchedSha"
Say ''

if ($WhatIf) { Say '[-WhatIf] 预览完成，未写入任何文件。'; Pause-Exit 0 }

# ---- 1. 备份（必须是当前游戏版本的原版）----
Write-Host -NoNewline '处理备份... '
if (Test-Path -LiteralPath $bak) {
  $bakSha = Get-FileSha $bak
  if ($bakSha -eq $pristineSha) {
    Say '已存在且是正确的原版备份，复用。' Green
  } else {
    $tag     = $bakSha.Substring(0, 8)
    $bakSize = (Get-Item -LiteralPath $bak).Length
    $arch    = "$bak.old-$tag"
    $n = 0
    while (Test-Path -LiteralPath $arch) { $n++; $arch = "$bak.old-$tag-$n" }
    Move-Item -LiteralPath $bak -Destination $arch -Force
    [System.IO.File]::WriteAllBytes($bak, $pristine)
    Say ''
    Say "[!] 旧备份与本版本游戏不匹配（$bakSize 字节，哈希 $tag…）——" Yellow
    Say "    已归档为 : $arch" Yellow
    Say "    已新建   : $bak  （对应当前 $($pristine.Length) 字节版本）" Green
    Say '    说明：游戏 2026-09-30 更新过，旧 .bak 属于上一版 DLL；' Yellow
    Say '          若不归档，将来「还原」会把游戏换回旧版 DLL 导致启动异常。' Yellow
  }
} else {
  [System.IO.File]::WriteAllBytes($bak, $pristine)
  Say "已新建原版备份 -> $bak" Green
  # 顺手在脚本目录留一份原版；脚本若放在只读位置（压缩包/网盘目录）失败也不影响安装
  try {
    $vault = Join-Path $here 'Assembly-CSharp.original.dll'
    [System.IO.File]::WriteAllBytes($vault, $pristine)
    Say "已同步一份原版到脚本目录 -> $vault" Green
  } catch {
    Say "[i] 脚本目录写入失败（不影响安装）：$($_.Exception.Message)" Yellow
  }
}

# ---- 2. 写入补丁 ----
[System.IO.File]::WriteAllBytes($GameDll, $patchedBytes)
Say '已写入补丁。' Green
Say ''

# ---- 3. 校验 ----
$final    = [System.IO.File]::ReadAllBytes($GameDll)
$finalSha = Get-Sha $final
$fs       = Get-State $final
Say "安装后哈希 : $finalSha"

$sizeOk = ($final.Length -eq $pristine.Length)
$byteOk = $true
$diffN  = 0
if ($sizeOk) {
  for ($i = 0; $i -lt $final.Length; $i++) {
    if ($final[$i] -ne $pristine[$i]) { $diffN++ }
  }
  $byteOk = ($diffN -eq 9)
}

if ($fs.State -eq 'Patched' -and $finalSha -eq $patchedSha -and $byteOk) {
  Say "[OK] 校验通过：红/黑 = ${RedBlackMultiplier}x，绿色 = ${GreenMultiplier}x。" Green
  Say "     文件大小不变（$($final.Length) 字节），相对原版只改动了 $diffN 个字节（等长替换）。" Green
  Say ''
  Say '使用说明：' Cyan
  Say '  * 赔率在「开赌场的主机」上结算 —— 你自己开房才生效。'
  Say '  * 别人加入你的房间会跟着你的结果走（服务器权威），朋友不需要装。'
  Say '  * 游戏内不会有任何提示；建议先押一件便宜物品试一把。'
  Say '  * 鼠标悬停按钮上的 "x2" 提示文字不会变（纯 UI 数字，不参与结算）。'
  Say '  * Steam「验证游戏文件完整性」或游戏更新会还原成 2x，重跑本脚本即可。'
  Say "  * 想还原：双击「还原原版赔率.cmd」，或运行本脚本加 -Revert。"
  Pause-Exit 0
} else {
  Say '[!] 校验失败：' Red
  if (-not $sizeOk) { Say "    文件大小变了：$($final.Length) != $($pristine.Length)" Red }
  if (-not $byteOk) { Say "    相对原版的差异字节数为 $diffN（预期 9）" Red }
  if ($fs.State -ne 'Patched') { Say "    重新检测到的状态为 $($fs.State)" Red }
  Say '    建议用 Steam「验证游戏文件完整性」恢复后重试。' Red
  Pause-Exit 1
}
