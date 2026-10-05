# How to Fish —— 轮盘赌红/黑赔率补丁（2× → 20×）

> **状态：已适配 2026-09-30 的游戏更新。** 补丁脚本现在**不依赖任何硬编码偏移或哈希**，
> 按字节特征搜索目标代码，游戏以后更新只要没改轮盘逻辑就继续可用。

---

## 本次更新做了什么（v1 → v2）

游戏在 **2026-09-30** 推送了一次内容更新（弓、木桶、瓶子、成就等，`Assembly-CSharp.dll`
从 870400 → 910848 字节，方法数 5157 → 5402，Unity 6000.4.4f1）。

逐方法反汇编对比结果（见 `v2_vs_v1_diff.txt`）：

| 项目 | 结论 |
|---|---|
| `CasinoManager.ServerRouletteResult`（补丁目标方法） | **149 字节方法体逐字节相同**，反汇编逐行一致 |
| 赌场/轮盘相关 137 个方法 | 129 个完全一致，8 个有实质变化 |
| 那 8 个变化 | 4 个 `DazedCommands`（开发者指令）、`Server::RpcWriter___UpdateRoulette`（RPC 常量 32→34）、3 个 `SlotMachine`（音量/时长微调）—— **都与赔率无关** |
| 赔率逻辑 | 未变，红/黑仍是 2×，绿仍是 35× |

所以补丁原理完全不变，只是文件偏移整体后移了：

| 版本 | DLL 大小 | `IL_0000` 文件偏移 | 方法体长度 |
|---|---|---|---|
| v1（更新前） | 870400 | `0x1C1C4` | 149 字节 |
| **v2（当前）** | **910848** | **`0x1E734`** | 149 字节 |

**修掉的一个隐患**：游戏更新后，游戏目录里的 `Assembly-CSharp.dll.bak` 还是**上一版**的原版
（870400 字节）。旧版安装脚本看到 `.bak` 已存在就直接跳过备份，将来「还原」会把游戏 DLL 换成
旧版本，可能导致游戏启动异常。新脚本会检测这种情况，自动把旧备份归档成
`Assembly-CSharp.dll.bak.old-<哈希前8位>`，再生成对应的新备份。

---

## 这个补丁做了什么

把轮盘赌里**押红 / 押黑**赢了的倍率从 **2 倍** 改成 **20 倍**。
**绿色的 35 倍保持不变。**（绿色是成就「一把梭哈」的条件，改高改低没意义，就留着了。）

改动方式是**等长字节替换**，只动了 `Assembly-CSharp.dll` 里的 **9 个字节**，
没有移动任何偏移、没有改变方法长度、没有动任何其它代码。

---

## 怎么安装

**关掉游戏**，然后任选一种：

| 方式 | 操作 |
|---|---|
| 最简单 | 双击 **`安装轮盘赌补丁.cmd`** |
| 用 PowerShell | 右键 `Install-RouletteMod.ps1` → 「使用 PowerShell 运行」 |
| 手动 | 把 `Assembly-CSharp.patched.dll` 复制成游戏目录下的 `Assembly-CSharp.dll`（先备份原文件！）⚠️ 仅当你的游戏是同一 build 时才能这么做 |

脚本会自动：
1. 检查游戏是否在运行
2. **自动定位游戏目录**（读注册表 + 所有 Steam 库的 `libraryfolders.vdf`；找不到会提示你把 DLL 拖进窗口）
3. 按字节特征识别当前 DLL 是原版 / 已打补丁 / 无法识别（无法识别会拒绝修改）
4. 确保 `.bak` 是**当前游戏版本**的原版（旧版本备份自动归档）
5. 安装补丁
6. 校验：文件大小不变 + 相对原版只差 9 个字节 + 重新识别状态为「已打补丁」

本机当前路径（自动查到的就是这个）：

```
E:\SteamLibrary\steamapps\common\How to Fish\How to Fish\How to Fish_Data\Managed\Assembly-CSharp.dll
```

要手动指定就加 `-GameDll "完整路径或游戏文件夹"`（文件夹、拖拽格式 `& '...'` 都能识别）。

---

## 怎么还原

双击 **`还原原版赔率.cmd`**（或运行 `Install-RouletteMod.ps1 -Revert`）。

还原走的是「就地反打补丁」（把 9 个字节改回去），不依赖 `.bak`，
所以即使备份丢了也能安全还原。也可以直接用 Steam 的「验证游戏文件完整性」。

---

## 分享给别人用

**可以直接分享，对方不需要任何编程知识。** 已经打好一个现成的包：

> **`HowToFish-轮盘赌20x-分享包.zip`**（12 KB，直接发给对方）
> 或者直接发 `分享包-HowToFish轮盘赌20x/` 这个文件夹。

对方拿到后：**退出游戏 → 双击「安装轮盘赌补丁.cmd」→ 看到 `[OK] 校验通过` 就成了。**

### 为什么对方也能用

| 关键点 | 说明 |
|---|---|
| **不认版本号，认代码特征** | 脚本在 DLL 里搜 `ServerRouletteResult` 的 switch 字节特征，不依赖固定偏移或哈希。已验证 v1(870400) 和 v2(910848) 两个版本都能打。 |
| **不认固定路径** | 脚本会读注册表里 Steam 的安装位置 + 所有 `libraryfolders.vdf` 库，自动找到游戏。装在任何盘都能找到。 |
| **找不到也不会卡住** | 实在找不到会把游戏里的 `Assembly-CSharp.dll` 拖进窗口即可；也可以 `-GameDll "D:\...\Assembly-CSharp.dll"` 指定。 |
| **认不出来就拒绝动手** | 如果 DLL 既不是原版也不是本补丁的产物（比如装过别的 Mod），脚本直接拒绝修改，不会把游戏改坏。 |

### ⚠️ 分享时**不要**把这两个文件发出去

`Assembly-CSharp.patched.dll` 和 `Assembly-CSharp.original.dll` —— 它们是**和游戏版本绑定**的
完整 DLL。对方的游戏版本只要差一个 build，直接覆盖过去就会让游戏起不来。
分享包里故意只放了脚本，让脚本在对方自己的 DLL 上就地打补丁，这样最安全。

### ⚠️ 非技术层面的两点提醒

1. **联机影响**：赔率由**主机**结算。别人装了补丁开房，你进去也会跟着按 20× 走（你不需要装）；
   你装了补丁当房主，房间里所有人也都会按 20× 结算 —— **包括陌生人**。
   拿去和熟人玩没问题，但拿这个去公开房间影响不认识的人，性质就不一样了，请自行判断。
2. **修改游戏文件本身**：这是改 `Assembly-CSharp.dll`。目前游戏**没有任何文件完整性校验**
   （已全程序集扫描确认，没有 MD5/SHA/Checksum 相关调用），所以不会被检测或报错；
   但开发者以后如果加了校验，或者对 Mod 有明确态度，风险要自己承担。
   Steam「验证文件完整性」随时能一键还原。

### 想自己重新打包

```powershell
# 改完脚本后，重新生成分享包（只放脚本，不放 DLL）
$share = ".\分享包-HowToFish轮盘赌20x"
Remove-Item -Recurse -Force $share -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $share | Out-Null
Copy-Item .\Install-RouletteMod.ps1, .\Patch-Roulette.ps1, ".\安装轮盘赌补丁.cmd", ".\还原原版赔率.cmd", ".\使用说明-给朋友.txt" $share
Compress-Archive -Path "$share\*" -DestinationPath ".\HowToFish-轮盘赌20x-分享包.zip" -Force
```

> 注意：`.ps1` 和 `.txt` 必须存成 **UTF-8 带 BOM**，否则 Windows PowerShell 5.1 会按 ANSI
> 解码中文导致语法错误。用文本编辑器另存为时记得选「UTF-8 带 BOM」。

---

## 文件说明

| 文件 | 说明 |
|---|---|
| `HowToFish-轮盘赌20x-分享包.zip` | **发给别人的成品包**（仅脚本，12 KB） |
| `分享包-HowToFish轮盘赌20x/` | 上者的解压内容 |
| `使用说明-给朋友.txt` | 面向非技术用户的说明（也打进分享包） |
| `安装轮盘赌补丁.cmd` | 双击安装（推荐） |
| `还原原版赔率.cmd` | 双击还原 |
| `Install-RouletteMod.ps1` | 安装/还原主脚本：自动找游戏、内容识别、备份管理。**单文件即可独立使用** |
| `Patch-Roulette.ps1` | 通用补丁器，可指定任意倍率：`-RedBlackMultiplier 20 -GreenMultiplier 35` |
| `Assembly-CSharp.patched.dll` | 已打补丁并验证过的完整 DLL（v2，哈希 `6F0E3DD1…EFC8`）⚠️ 仅限本版本，别外发 |
| `Assembly-CSharp.original.dll` | v2 原版备份（哈希 `E3EC0BEF…84B1`）⚠️ 仅限本版本，别外发 |
| `ServerRouletteResult.il` | v2 原版目标方法的 149 字节 IL（十六进制） |
| `ServerRouletteResult.patched.il` | v2 打补丁后同一方法的 149 字节 IL，可逐字节对照 |
| `ildump.py` | 自建 .NET 元数据 + IL 解析器（纯 Python，只读） |
| `cmpver.py` | 版本对比工具：判定游戏更新有没有动赌场代码 |
| `verifypatch.py` | 补丁自检：反汇编 + 分支目标 + 栈深数据流 + maxstack + 倍率取值 |
| `v2_vs_v1_diff.txt` | v1 ↔ v2 全程序集对比报告 |
| `v2_CasinoManager.txt` 等 `v2_*.txt` | v2 赌场相关类反汇编 |
| `out_*.txt` | v1 时期的反汇编（保留作对照） |
| `archive-v1-870400/` | v1 的原始/补丁 DLL 与 IL 参考 |


---

## 补丁原理（技术细节）

目标方法 `CasinoManager.ServerRouletteResult` 的原始 IL（v1/v2 完全相同）：

```
IL_000f: switch (3)  case0->IL_0022, case1->IL_0026, case2->IL_002a
IL_0020: br.s  IL_002d            // default：没押中
IL_0022: ldc.i4.2  ; stloc.1 ; br.s IL_002d     // Black = 2
IL_0026: ldc.i4.2  ; stloc.1 ; br.s IL_002d     // Red   = 2
IL_002a: ldc.i4.s 35 ; stloc.1                  // Green = 35
IL_002d: （继续遍历押注物品）
```

问题是 `ldc.i4.2` 只占 **1 字节**，而 20 需要 `ldc.i4.s 20` 占 **2 字节** —— 直接替换会让后面所有字节位移，分支目标和异常处理表全废。

所以补丁**让红黑共用同一段代码**（把 switch 表里 case1 的目标从 `IL_0026` 改成 `IL_0022`）：

```
IL_000f: switch (3)  case0->IL_0022, case1->IL_0022, case2->IL_002a
IL_0020: br.s  IL_002d
IL_0022: ldc.i4.s 20 ; stloc.1 ; br.s IL_002d   // Black = 20  ← 红黑共用
IL_0027: nop ; nop ; nop                        // 填位
IL_002a: ldc.i4.s 35 ; stloc.1                  // Green = 35（不变）
IL_002d: （继续）
```

**字节数完全一致（11 → 11）**，所有偏移、分支、异常处理表、maxstack 全部不变。

v2 实际改动的 9 个字节（文件偏移 = `IL_0000` 偏移 `0x1E734` + 相对偏移）：

```
文件偏移      原值 → 新值
0x1E743   switch 表起点（IL_000f）
0x1E74C       06 → 02          (switch 表 case1 目标 6 → 2)
0x1E756       18 → 1F          (ldc.i4.2 → ldc.i4.s)
0x1E757       0B → 14          (操作数: 20)
0x1E758       2B → 0B          (br.s → stloc.1)
0x1E759       07 → 2B          (br.s 操作数)
0x1E75A       18 → 06          (填充重排)
0x1E75B       0B → 00          (nop)
0x1E75C       2B → 00          (nop)
0x1E75D       03 → 00          (nop)
```

---

## 改任意倍率

`Patch-Roulette.ps1` 支持自定义（倍率范围 -128 ~ 127，受 `ldc.i4.s` 单字节编码限制）：

```powershell
powershell -ExecutionPolicy Bypass -File .\Patch-Roulette.ps1 `
  -DllPath "E:\SteamLibrary\...\Assembly-CSharp.dll" `
  -RedBlackMultiplier 10 `
  -GreenMultiplier 35
```

先加 `-WhatIf` 可以只预览不写入；加 `-Quiet` 只输出错误。
也可以在 `Install-RouletteMod.ps1` 上直接传 `-RedBlackMultiplier` / `-GreenMultiplier`，
它支持「已装 A 倍率 → 直接改成 B 倍率」。

---

## 已知外观差异（不是 bug）

**鼠标悬停在红/黑按钮上，提示文字仍然显示 `x2`，但实际赔 20×。**

`BetButton.Hover` 的 tooltip 里那个数字来自按钮自己的 `[SerializeField] int _multiplier`，
它**只被用来拼字符串**，任何地方都不参与结算（结算倍率硬编码在上面那 9 个字节里）。
它是场景里序列化的值，改它需要动 Unity 场景二进制文件，风险远大于收益，所以没做。

想验证的话，押一件**便宜物品**试一把即可，看赢了之后物品价值是不是 ×20。

---

## 注意事项

1. **联机时只在你当主机时生效** —— 赔率是在「服务器」端结算的（`ServerRouletteResult`）。你开房 → 全场按 20× 走；你加入别人的房 → 按房主的代码走（2×）。
2. **不需要给朋友装** —— 服务器权威，结果由主机算完广播给所有人。
3. **Steam 验证文件完整性 / 游戏更新会还原成 2×**，重跑一次安装脚本即可。
4. 赢来的倍率会**写进存档**（`Item._bettingMultiplier` → `SavedItem.BettingMultiplier`），卖出时按 ×20 价值结算。
5. 建议改完后先押一件**便宜物品**试一把，确认生效。
6. 这属于修改游戏文件。纯单人/合作玩耍没问题，但请自行留意开发者对 Mod 的态度。

---

## 下次游戏更新怎么办

1. 游戏更新后先运行 `安装轮盘赌补丁.cmd`：
   - 若输出「当前状态 : 原版」并校验通过 → 说明轮盘逻辑没变，补丁照常生效，**完事**。
   - 若输出「无法识别」→ 说明开发者改了 `ServerRouletteResult`，需要重新分析。
2. 重新分析用工作区自带工具（只读，不修改任何文件）：

```powershell
# 看目标方法现在的反汇编
python ildump.py "<游戏>\...\Assembly-CSharp.dll" cm.txt dump CasinoManager

# 和新版/旧版对比，判断改了哪些赌场方法
python cmpver.py "<旧 dll>" "<新 dll>" diff.txt
```

3. 打完补丁后可以跑一遍自检（会真的做栈深数据流分析，不只是比字节）：

```powershell
python verifypatch.py Assembly-CSharp.original.dll "<游戏>\...\Assembly-CSharp.dll" 20 35
```

输出示例（全部 6 项检查 + 差异范围）：

```
  [1] 解码 58 条指令，正好覆盖 149 字节 ................ OK
  [2] 全部分支/switch 目标落在指令边界上 ........... OK
  [3] 栈深模拟无负栈、无未收录指令 ................. OK
  [4] 实测最大栈深 1 <= 声明 maxstack 3 ........... OK
  [5] 所有 ret 处栈深为 0 .......................... OK
  [6] switch case0/case1 -> ['IL_0022', 'IL_0022']，取值 [20]（期望 20）... OK
      switch case2 -> IL_002a，取值 35（期望 35）......... OK
结论：全部检查通过，补丁是合法 IL 且改动范围最小。
```
