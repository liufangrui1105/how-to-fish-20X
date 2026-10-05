# Patch-Roulette.ps1 —— 把《How to Fish》轮盘赌的红/黑赔率从 2 改成任意值
#
# 目标方法：CasinoManager.ServerRouletteResult
#     bool won = (winColor == _curBetColor);
#     int k = 0;
#     if (won) switch ((int)winColor) { case 0: k = 2; case 1: k = 2; case 2: k = 35; }
#   IL_000f  switch (3)  case0->IL_0022, case1->IL_0026, case2->IL_002a
#   IL_0020  2B 0B                  br.s IL_002d      （default：没押中）
#   IL_0022  18 0B 2B 07            ldc.i4.2 ; stloc.1 ; br.s IL_002d   (Black = 2)
#   IL_0026  18 0B 2B 03            ldc.i4.2 ; stloc.1 ; br.s IL_002d   (Red   = 2)
#   IL_002a  1F 23 0B               ldc.i4.s 35 ; stloc.1               (Green = 35)
#   IL_002d  ...（继续遍历押注物品）
#
# 难点：ldc.i4.2 只占 1 字节，而 20 需要 ldc.i4.s 20 占 2 字节 —— 直接替换会让后面所有
#       字节位移，分支目标、异常处理表、maxstack 全废。
#
# 补丁（等长，11 字节 -> 11 字节，不移动任何偏移）：
#   switch 表里 case1 的目标从 IL_0026 改成 IL_0022（红黑共用同一段代码）
#   IL_0022  1F 14 0B 2B 06   ldc.i4.s 20 ; stloc.1 ; br.s IL_002d
#   IL_0027  00 00 00         nop x3（填位）
#   IL_002a  1F 23 0B         ldc.i4.s 35 ; stloc.1   （绿保持不变）
#
# 由于整个改动是「等长原地替换」，本脚本**不依赖任何硬编码文件偏移**：
# 它按字节特征搜索 switch 结构，所以游戏更新换了偏移也能照常工作。
# 已用两代游戏验证：
#   旧版 (870400 B, Unity 6000.0.x) IL_0000 文件偏移 0x1C1D5
#   新版 (910848 B, Unity 6000.4.4f1) IL_0000 文件偏移 0x1E734
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\Patch-Roulette.ps1 `
#       -DllPath "E:\...\Assembly-CSharp.dll" -RedBlackMultiplier 20 -GreenMultiplier 35
#   加 -WhatIf 只预览不写入。

param(
  [Parameter(Mandatory=$true)][string]$DllPath,
  [int]$RedBlackMultiplier = 20,
  [int]$GreenMultiplier = 35,
  [switch]$WhatIf,
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

if ($RedBlackMultiplier -lt -128 -or $RedBlackMultiplier -gt 127) {
  throw "RedBlackMultiplier 必须在 -128..127 之间（IL 用 ldc.i4.s 单字节编码）"
}
if ($GreenMultiplier -lt -128 -or $GreenMultiplier -gt 127) {
  throw "GreenMultiplier 必须在 -128..127 之间"
}

$RB = [byte]($RedBlackMultiplier -band 0xFF)
$GR = [byte]($GreenMultiplier -band 0xFF)

# ---- 原始形态锚点（30 字节）----
#       switch(3){+2,+6,+10} + br.s + [ldc.i4.2;stloc.1;br.s] x2 + [ldc.i4.s 35;stloc.1]
$ANCHOR_ORIGINAL = [int[]]@(
  0x45,0x03,0x00,0x00,0x00,
  0x02,0x00,0x00,0x00,
  0x06,0x00,0x00,0x00,
  0x0A,0x00,0x00,0x00,
  0x2B,0x0B,
  0x18,0x0B,0x2B,0x07,
  0x18,0x0B,0x2B,0x03,
  0x1F,0x23,0x0B
)

# ---- 补丁后形态锚点（30 字节，-1 = 通配，用来读出当前已装的倍率）----
$ANCHOR_PATCHED = [int[]]@(
  0x45,0x03,0x00,0x00,0x00,
  0x02,0x00,0x00,0x00,
  0x02,0x00,0x00,0x00,
  0x0A,0x00,0x00,0x00,
  0x2B,0x0B,
  0x1F,-1,0x0B,0x2B,0x06,
  0x00,0x00,0x00,
  0x1F,-1,0x0B
)

# 补丁块相对 IL_0000 的偏移：IL_0022 = 0x22，相对 switch 表起点(=$o)为 0x22-0x0F = 0x13 = 19
$BLOCK_FROM_ANCHOR = 19

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
  if ($o.Count -eq 1) { return @{ State = 'Original'; Offset = $o[0]; RB = $null; GR = $null } }
  if ($o.Count -gt 1) { return @{ State = 'Ambiguous'; Offset = -1; RB = $null; GR = $null; Count = $o.Count } }
  $p = Find-Anchor $bytes $ANCHOR_PATCHED
  if ($p.Count -eq 1) {
    $b = $p[0] + $BLOCK_FROM_ANCHOR
    $rb = [int]$bytes[$b + 1]; if ($rb -gt 127) { $rb -= 256 }
    $gr = [int]$bytes[$b + 9]; if ($gr -gt 127) { $gr -= 256 }
    return @{ State = 'Patched'; Offset = $p[0]; RB = $rb; GR = $gr }
  }
  if ($p.Count -gt 1) { return @{ State = 'Ambiguous'; Offset = -1; RB = $null; GR = $null; Count = $p.Count } }
  return @{ State = 'Unknown'; Offset = -1; RB = $null; GR = $null }
}

# ================================ 主流程 ================================
if (-not (Test-Path -LiteralPath $DllPath)) { throw "找不到文件：$DllPath" }

$b = [System.IO.File]::ReadAllBytes($DllPath)
if (-not $Quiet) {
  "目标文件 : $DllPath"
  "文件大小 : $($b.Length) 字节"
  "SHA256   : $((Get-FileHash -LiteralPath $DllPath -Algorithm SHA256).Hash)"
  ""
}

$st = Get-State $b
if ($st.State -eq 'Ambiguous') {
  throw "锚点不唯一（$($st.Count) 处匹配），出于安全考虑放弃修改。"
}
if ($st.State -eq 'Unknown') {
  throw "未找到目标 switch 结构 —— 该 DLL 可能已被其它 Mod 修改，或游戏改了轮盘逻辑。" + `
        "请先用 ildump.py dump CasinoManager 核对 ServerRouletteResult 的反汇编。"
}
if ($st.State -eq 'Patched') {
  if (-not $Quiet) {
    "当前状态 : 已打补丁（红/黑 $($st.RB)x，绿 $($st.GR)x）"
    "IL_0000 文件偏移 : 0x$('{0:X}' -f ($st.Offset - 0x0F))"
    ""
  }
  if ($st.RB -eq $RedBlackMultiplier -and $st.GR -eq $GreenMultiplier) {
    if (-not $Quiet) { "目标倍率与当前一致，无需改动。" }
    return
  }
  if (-not $Quiet) { "需改倍率 -> 红/黑 $RedBlackMultiplier x，绿 $GreenMultiplier x`n" }
} else {
  if (-not $Quiet) {
    "当前状态 : 原版（红/黑 2x，绿 35x）"
    "IL_0000 文件偏移 : 0x$('{0:X}' -f ($st.Offset - 0x0F))"
    ""
  }
}

$o = $st.Offset

# ---- 构造 11 字节补丁块 ----
$newBlock = [byte[]]@(
  0x1F, $RB,        # ldc.i4.s <红黑倍率>
  0x0B,             # stloc.1
  0x2B, 0x06,       # br.s IL_002d  (下一条在 IL_0027，+6 = IL_002d)
  0x00, 0x00, 0x00, # nop x3（填位）
  0x1F, $GR,        # ldc.i4.s <绿色倍率>
  0x0B              # stloc.1，自然落到 IL_002d
)

if (-not $Quiet) {
  "打补丁前:"
  "  switch 表 case1 目标 : " + (($b[($o+9)..($o+12)]  | ForEach-Object { $_.ToString('x2') }) -join ' ')
  "  IL_0022 代码块       : " + (($b[($o+19)..($o+29)] | ForEach-Object { $_.ToString('x2') }) -join ' ')
}

# case1 目标改到 IL_0022（与 case0 共用）
$b[$o+9]  = 0x02; $b[$o+10] = 0x00; $b[$o+11] = 0x00; $b[$o+12] = 0x00
for ($k = 0; $k -lt $newBlock.Length; $k++) { $b[$o + $BLOCK_FROM_ANCHOR + $k] = $newBlock[$k] }

if (-not $Quiet) {
  ""
  "打补丁后:"
  "  switch 表 case1 目标 : " + (($b[($o+9)..($o+12)]  | ForEach-Object { $_.ToString('x2') }) -join ' ')
  "  IL_0022 代码块       : " + (($b[($o+19)..($o+29)] | ForEach-Object { $_.ToString('x2') }) -join ' ')
  ""
}

if ($WhatIf) { if (-not $Quiet) { "[-WhatIf] 未写入文件。" } ; return }

if (Test-Path -LiteralPath "$DllPath.bak") {
  if (-not $Quiet) { "备份已存在，跳过: $DllPath.bak" }
} else {
  # 注意：这里备份的是「当前文件」，若当前文件已是补丁版，备份的也是补丁版。
  # 正常的备份策略由 Install-RouletteMod.ps1 负责，本脚本只提供最小保护。
  Copy-Item -LiteralPath $DllPath -Destination "$DllPath.bak" -Force
  if (-not $Quiet) { "已备份当前文件 -> $DllPath.bak" }
}

[System.IO.File]::WriteAllBytes($DllPath, $b)
if (-not $Quiet) {
  "已写入补丁。"
  "新 SHA256 : $((Get-FileHash -LiteralPath $DllPath -Algorithm SHA256).Hash)"
}
