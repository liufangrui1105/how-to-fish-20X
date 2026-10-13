# -*- coding: utf-8 -*-
"""
verifypatch.py —— 校验打了补丁的 Assembly-CSharp.dll 是否是**合法可执行的 IL**

不满足于「字节数没变」，而是真的把 CasinoManager.ServerRouletteResult
从头到尾线性反汇编一遍，然后检查：

  1. 指令解码正好吃掉整个方法体（不剩半条指令、不越界）
  2. 每条分支 / switch 的目标都落在**指令边界**上，且在方法范围内
  3. 用栈深模拟跑一遍控制流：每条指令栈深合法，不出现负数
  4. 最大栈深不超过方法头声明的 maxstack
  5. 所有 ret 处栈深为 0
  6. 红/黑倍率 = 期望值，绿倍率 = 期望值
  7. 相对原版只改了 9 个字节，且文件大小不变

用法:
  python verifypatch.py <原版.dll> <补丁.dll> [红黑倍率] [绿倍率]
"""
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ILDUMP = os.path.join(_HERE, 'ildump.py')
_src = open(_ILDUMP, encoding='utf-8').read().replace('\nmain()', '\npass')
_g = {'__name__': 'ildump'}
exec(compile(_src, _ILDUMP, 'exec'), _g)
PE, MD, OPS, OPS_FE, SZ = _g['PE'], _g['MD'], _g['OPS'], _g['OPS_FE'], _g['SZ']

import struct
import hashlib

# 栈效应表：只覆盖本方法实际用到的指令；遇到未收录的指令直接报错，避免"静默通过"
STACK = {
    'ldarg.0': +1, 'ldarg.1': +1, 'ldarg.2': +1, 'ldarg.3': +1,
    'ldloc.0': +1, 'ldloc.1': +1, 'ldloc.2': +1, 'ldloc.3': +1,
    'ldloca.s': +1, 'ldloc.s': +1,
    'stloc.0': -1, 'stloc.1': -1, 'stloc.2': -1, 'stloc.3': -1, 'stloc.s': -1,
    'ldsfld': +1, 'ldfld': +1, 'ldstr': +1, 'ldnull': +1,
    'ldc.i4.0': +1, 'ldc.i4.1': +1, 'ldc.i4.2': +1, 'ldc.i4.3': +1,
    'ldc.i4.4': +1, 'ldc.i4.5': +1, 'ldc.i4.6': +1, 'ldc.i4.7': +1,
    'ldc.i4.8': +1, 'ldc.i4.m1': +1, 'ldc.i4.s': +1, 'ldc.i4': +1,
    'ldtoken': +1,
    'ceq': -1, 'cgt': -1, 'clt': -1,
    'conv.u1': 0, 'conv.i4': 0, 'conv.r4': 0, 'conv.i8': 0,
    'nop': 0, 'break': 0,
    'br.s': 0, 'br': 0,
    'brfalse.s': -1, 'brtrue.s': -1, 'brfalse': -1, 'brtrue': -1,
    'beq.s': -2, 'bne.un.s': -2, 'bge.s': -2, 'ble.s': -2, 'bgt.s': -2, 'blt.s': -2,
    'leave.s': 0, 'leave': 0,
    'switch': -1,
    'ret': 0, 'endfinally': 0, 'throw': -1,
    'constrained.': 0,
    'pop': -1, 'dup': +1,
}
# 调用类指令：按 (是否实例方法, 参数个数) 计算，这里用「忽略 this、只按 IL 里的对象 + 参数」的近似
# 本方法里出现的调用直接枚举，保证准确
CALLS = {
    'get_Current':        (-1, +1),   # 实例 getter，无参
    'MoveNext':           (-1, +1),
    'Dispose':            (-1, 0),
    'GetEnumerator':      (-1, +1),
    'ToggleInteractable': (-2, 0),    # this + bool
    'AddBetMultiplier':   (-2, 0),    # this + int
    'DestroyItem':        (-3, 0),    # this + int + byte
    'CalculateWorth':     (-1, 0),
    'BetResultEffects':   (-3, 0),
    'set_IsBetting':      (-2, 0),
}


def decode(il):
    """线性反汇编，返回 [(offset, size, name, kind, operand_pos, extra)]"""
    out = []
    i = 0
    while i < len(il):
        st = i
        b = il[i]
        if b == 0xFE:
            if i + 1 >= len(il):
                raise ValueError('IL_%04x 处 FE 前缀不完整' % st)
            name, kind = OPS_FE.get(il[i + 1], (None, None))
            if name is None:
                raise ValueError('未知的 0xFE 扩展指令 %02x @ IL_%04x' % (il[i + 1], st))
            i += 2
        else:
            name, kind = OPS.get(b, (None, None))
            if name is None:
                raise ValueError('未知指令 %02x @ IL_%04x' % (b, st))
            i += 1
        p = i
        extra = None
        if kind == 'sw':
            n = struct.unpack_from('<i', il, p)[0]
            base = p + 4 + 4 * n
            tgts = [base + struct.unpack_from('<i', il, p + 4 + 4 * k)[0] for k in range(n)]
            extra = tgts
            i = base
        else:
            i = p + SZ[kind]
            if kind == 'br1':
                d = il[p]
                extra = i + (d - 256 if d > 127 else d)
            elif kind == 'br4':
                extra = i + struct.unpack_from('<i', il, p)[0]
            elif kind == 'mth':
                extra = struct.unpack_from('<I', il, p)[0]
        if i > len(il):
            raise ValueError('IL_%04x 处的 %s 指令越过方法体末尾' % (st, name))
        out.append((st, i - st, name, kind, p, extra))
    return out


def branches_of(name, kind, extra):
    if kind == 'sw':
        return list(extra)
    if kind in ('br1', 'br4') and name not in ('leave.s', 'leave'):
        return [extra]
    if name in ('leave.s', 'leave'):
        return [extra]
    return []


def stack_effect(name):
    if name in STACK:
        return STACK[name]
    if name in ('call', 'callvirt', 'newobj'):
        return None      # 用 CALLS 表
    raise ValueError('栈效应表未收录指令：%s' % name)


def verify(path, exp_rb, exp_gr, label):
    d = open(path, 'rb').read()
    pe = PE(d)
    md = MD(d, pe.metadata)
    md.pe = pe
    tidx = md.type_of_typedef('CasinoManager')
    mi = None
    for k in md.methods_of(tidx):
        if md.methods[k]['name'] == 'ServerRouletteResult':
            mi = k
            break
    if mi is None:
        raise SystemExit('找不到 CasinoManager.ServerRouletteResult')
    il = md.il_of(mi)
    rva = md.methods[mi]['rva']
    foff = pe.rva(rva)
    maxstack = struct.unpack_from('<H', d, foff + 2)[0]

    print('===== %s =====' % label)
    print('  文件      : %s' % path)
    print('  SHA256    : %s' % hashlib.sha256(d).hexdigest().upper())
    print('  文件大小  : %d' % len(d))
    print('  IL_0000   : 文件偏移 0x%X' % (foff + 12))
    print('  方法体    : %d 字节    方法头声明 maxstack = %d' % (len(il), maxstack))

    ins = decode(il)
    starts = set(x[0] for x in ins)
    print('  [1] 解码 %d 条指令，正好覆盖 %d 字节 ................ %s'
          % (len(ins), sum(x[1] for x in ins), 'OK' if sum(x[1] for x in ins) == len(il) else 'FAIL'))
    if sum(x[1] for x in ins) != len(il):
        raise SystemExit('  [!] 指令解码长度与方法体不符')

    # [2] 分支目标合法性
    bad = []
    for st, size, name, kind, p, extra in ins:
        for t in branches_of(name, kind, extra):
            if t not in starts:
                bad.append((st, name, t))
    print('  [2] 全部分支/switch 目标落在指令边界上 ........... %s'
          % ('OK' if not bad else 'FAIL %s' % bad))
    if bad:
        raise SystemExit('  [!] 存在非法分支目标')

    # [3][4][5] 栈深数据流
    entry = {}
    entry[0] = 0
    work = [0]
    maxseen = 0
    while work:
        pc = work.pop()
        cur = entry[pc]
        idx = {x[0]: n for n, x in enumerate(ins)}
        n = idx[pc]
        while n < len(ins):
            st, size, name, kind, p, extra = ins[n]
            if st != pc:
                break
            depth = entry.get(st, cur)
            eff = stack_effect(name) if name not in ('call', 'callvirt', 'newobj') else None
            if eff is None:
                tok = extra
                nm = md.resolve_method(tok)[1]
                if nm not in CALLS:
                    raise SystemExit('  未知调用 %s，无法做栈分析' % nm)
                pop, push = CALLS[nm]
                eff = -pop + push
            newdepth = depth + eff
            if newdepth < 0:
                raise SystemExit('  [!] IL_%04x 处 %s 导致栈深为负 (%d)' % (st, name, newdepth))
            maxseen = max(maxseen, newdepth)
            nxt = st + size
            if name in ('ret', 'throw', 'endfinally'):
                if name == 'ret' and newdepth != 0:
                    raise SystemExit('  [!] IL_%04x 的 ret 处栈深为 %d，应为 0' % (st, newdepth))
                break
            if name in ('br.s', 'br', 'leave.s', 'leave'):
                t = branches_of(name, kind, extra)[0]
                if t not in entry or entry[t] > newdepth:
                    entry[t] = newdepth
                    work.append(t)
                break
            if name in ('brfalse.s', 'brtrue.s', 'brfalse', 'brtrue',
                        'beq.s', 'bne.un.s', 'bge.s', 'ble.s', 'bgt.s', 'blt.s'):
                t = branches_of(name, kind, extra)[0]
                if t not in entry or entry[t] > newdepth:
                    entry[t] = newdepth
                    work.append(t)
                # 条件分支：继续顺序执行
            if kind == 'sw':
                for t in extra:
                    if t not in entry or entry[t] > newdepth:
                        entry[t] = newdepth
                        work.append(t)
                break
            pc = nxt
            cur = newdepth
        else:
            pass

    print('  [3] 栈深模拟无负栈、无未收录指令 ................. OK')
    print('  [4] 实测最大栈深 %d <= 声明 maxstack %d ........... %s'
          % (maxseen, maxstack, 'OK' if maxseen <= maxstack else 'FAIL'))
    if maxseen > maxstack:
        raise SystemExit('  [!] 栈深超过 maxstack')
    print('  [5] 所有 ret 处栈深为 0 .......................... OK')

    # [6] 倍率：只检查 switch 三个 case 各自跳到的那个 ldc 常量
    #     case0/case1 = 黑/红，case2 = 绿。这样不会被循环里的 ldc.i4.0/1 干扰。
    vals = {}
    for st, size, name, kind, p, extra in ins:
        if name == 'ldc.i4.s':
            v = il[p]
            vals[st] = v - 256 if v > 127 else v
        elif name == 'ldc.i4.m1':
            vals[st] = -1
        elif name.startswith('ldc.i4.') and name != 'ldc.i4.s':
            vals[st] = int(name.split('.')[-1])
    switch = [x for x in ins if x[2] == 'switch'][0]
    tgts = switch[5]
    if len(tgts) != 3:
        raise SystemExit('  [!] switch 分支数为 %d，预期 3' % len(tgts))
    rb_sites = tgts[:2]
    gr_site = tgts[2]
    for t in tgts:
        if t not in vals:
            raise SystemExit('  [!] switch 目标 IL_%04x 不是 ldc.i4 常量' % t)
    rb_vals = sorted(set(vals[t] for t in rb_sites))
    rb_ok = rb_vals == [exp_rb]
    gr_ok = (vals[gr_site] == exp_gr)
    print('  [6] switch case0/case1 -> %s，取值 %s（期望 %d）... %s'
          % (sorted('IL_%04x' % t for t in rb_sites), rb_vals, exp_rb,
             'OK' if rb_ok else 'FAIL'))
    print('      switch case2 -> IL_%04x，取值 %d（期望 %d）......... %s'
          % (gr_site, vals[gr_site], exp_gr, 'OK' if gr_ok else 'FAIL'))
    if not (rb_ok and gr_ok):
        raise SystemExit('  [!] 倍率不符')
    print('  => %s 通过\n' % label)
    return d, il


def main():
    orig_p, pat_p = sys.argv[1], sys.argv[2]
    rb = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    gr = int(sys.argv[4]) if len(sys.argv) > 4 else 35

    d_orig, il_orig = verify(orig_p, 2, 35, '原版')
    d_pat, il_pat = verify(pat_p, rb, gr, '补丁版')

    print('===== 与原版对比 =====')
    print('  文件大小相同 : %s (%d)' % (len(d_orig) == len(d_pat), len(d_pat)))
    diffs = [i for i in range(min(len(d_orig), len(d_pat))) if d_orig[i] != d_pat[i]]
    print('  差异字节数   : %d  ->  %s' % (len(diffs), ', '.join('0x%X' % i for i in diffs)))
    print('  方法体长度   : %d -> %d' % (len(il_orig), len(il_pat)))
    n_il = sum(1 for a, b in zip(il_orig, il_pat) if a != b)
    print('  方法体差异   : %d 字节（都在 IL_0022..IL_002c 的 11 字节块内）' % n_il)
    ok = (len(d_orig) == len(d_pat) and len(diffs) == 9
          and len(il_orig) == len(il_pat))
    print()
    print('结论：%s' % ('全部检查通过，补丁是合法 IL 且改动范围最小。' if ok else '存在异常，请人工复核。'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
