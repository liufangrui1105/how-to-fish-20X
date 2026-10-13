# -*- coding: utf-8 -*-
"""
cmpver.py —— 对比两个 Assembly-CSharp.dll 版本，判断游戏更新是否动了赌场/轮盘代码

用法:
  python cmpver.py <旧.dll> <新.dll> [输出.txt]

做三件事:
  1. 方法/类型/字段数量对比
  2. 新增 / 删除的方法清单
  3. 对赌场相关类型逐个方法做**反汇编文本**对比
     （注意：不能直接比 IL 原始字节 —— 程序集一旦增删方法，IL 里的
       metadata token 会整体重编号，字节必然不同，但语义可能完全一样。
       所以这里比较的是解析后的助记符文本。）
"""
import sys
import os

# ---- 复用同目录 ildump.py 的解析器（不执行它的 main）----
_HERE = os.path.dirname(os.path.abspath(__file__))
_ILDUMP = os.path.join(_HERE, 'ildump.py')
_src = open(_ILDUMP, encoding='utf-8').read().replace('\nmain()', '\npass')
_g = {'__name__': 'ildump'}
exec(compile(_src, _ILDUMP, 'exec'), _g)
PE, MD, OPS, OPS_FE, SZ = _g['PE'], _g['MD'], _g['OPS'], _g['OPS_FE'], _g['SZ']

import struct

CASINO_HINT = ('Casino', 'BetButton', 'SlotMachine', 'Roulette', 'DazedCommands', 'Item::Destroy')


def load(path):
    data = open(path, 'rb').read()
    pe = PE(data)
    md = MD(data, pe.metadata)
    md.pe = pe
    return md


def all_methods(md):
    out = {}
    for tidx in range(1, len(md.typedefs) + 1):
        tn = md.type_name(tidx)
        for mi in md.methods_of(tidx):
            out[tn + '::' + md.methods[mi]['name']] = md.il_of(mi)
    return out


def disasm(md, key):
    """把某个方法反汇编成文本行（token 尽量解析成名字）"""
    tidx, _, mname = key.rpartition('::')
    tid = md.type_of_typedef(tidx)
    if not tid:
        return None
    for mi in md.methods_of(tid):
        m = md.methods[mi]
        if m['name'] != mname:
            continue
        il = md.il_of(mi)
        if il is None:
            return ['    [无 IL]']
        out = []
        i = 0
        while i < len(il):
            start = i
            b = il[i]
            if b == 0xFE:
                name, kind = OPS_FE.get(il[i + 1], ('<fe%02x>' % il[i + 1], 'n'))
                i += 2
            else:
                name, kind = OPS.get(b, ('<%02x>' % b, 'n'))
                i += 1
            pos = i
            if kind == 'sw':
                n = struct.unpack_from('<i', il, pos)[0]
                base = pos + 4 + 4 * n
                i = base
                txt = '(%d) %s' % (n, ', '.join(
                    'case%d->IL_%04x' % (k, base + struct.unpack_from('<i', il, pos + 4 + 4 * k)[0])
                    for k in range(n)))
            else:
                i = pos + SZ[kind]
                if kind == 'n':
                    txt = ''
                elif kind == 'i1':
                    v = il[pos]
                    txt = str(v - 256 if v > 127 else v)
                elif kind == 'var1':
                    txt = 'V%d' % il[pos]
                elif kind == 'var2':
                    txt = 'V%d' % struct.unpack_from('<H', il, pos)[0]
                elif kind == 'br1':
                    dd = il[pos]
                    txt = 'IL_%04x' % (i + (dd - 256 if dd > 127 else dd))
                elif kind == 'br4':
                    txt = 'IL_%04x' % (i + struct.unpack_from('<i', il, pos)[0])
                elif kind == 'i4':
                    txt = str(struct.unpack_from('<i', il, pos)[0])
                elif kind == 'i8':
                    txt = str(struct.unpack_from('<q', il, pos)[0])
                elif kind == 'r4':
                    txt = str(struct.unpack_from('<f', il, pos)[0])
                elif kind == 'r8':
                    txt = str(struct.unpack_from('<d', il, pos)[0])
                elif kind in ('fld', 'mth', 'typ', 'tok', 'sig', 'str'):
                    tok = struct.unpack_from('<I', il, pos)[0]
                    if kind == 'fld':
                        txt = md.resolve_field(tok) or ('0x%08x' % tok)
                    elif kind == 'mth':
                        cls, nm = md.resolve_method(tok)
                        txt = (cls + '::' + nm) if cls else (nm or ('0x%08x' % tok))
                    elif kind == 'str':
                        base = md.streams['#US'][0]
                        o = base + (tok & 0xFFFFFF)
                        ln = md.d[o]
                        if ln & 0x80:
                            ln = ((ln & 0x7f) << 8) | md.d[o + 1]
                            o += 2
                        else:
                            o += 1
                        txt = '"' + md.d[o:o + ln - 1].decode('utf-16-le', 'replace') + '"'
                    elif kind in ('typ', 'tok'):
                        txt = md.token_type_name(tok)
                    else:
                        txt = '0x%08x' % tok
                else:
                    txt = ''
            out.append('    IL_%04x: %-12s %s' % (start, name, txt))
        return out
    return None


def main():
    oldp, newp = sys.argv[1], sys.argv[2]
    outp = sys.argv[3] if len(sys.argv) > 3 else None
    old, new = load(oldp), load(newp)
    om, nm = all_methods(old), all_methods(new)

    L = []
    def w(s=''):
        L.append(s)

    w('版本对比报告')
    w('  旧: %s' % oldp)
    w('  新: %s' % newp)
    w()
    w('  TypeDef : %d -> %d' % (len(old.typedefs), len(new.typedefs)))
    w('  Field   : %d -> %d' % (len(old.fields), len(new.fields)))
    w('  Method  : %d -> %d' % (len(old.methods), len(new.methods)))
    w()
    added = sorted(set(nm) - set(om))
    removed = sorted(set(om) - set(nm))
    w('=== 新增方法 (%d) ===' % len(added))
    for k in added:
        w('  + ' + k)
    w()
    w('=== 删除方法 (%d) ===' % len(removed))
    for k in removed:
        w('  - ' + k)
    w()

    # 赌场相关类型：逐方法反汇编对比
    common = sorted(set(om) & set(nm))
    casino = [k for k in common if any(t in k for t in CASINO_HINT)]
    same, diff = [], []
    for k in casino:
        a = disasm(old, k)
        b = disasm(new, k)
        (same if a == b else diff).append(k)

    w('=== 赌场相关类型反汇编对比 (%d 个方法) ===' % len(casino))
    w('  完全一致 : %d' % len(same))
    w('  IL 有变化: %d' % len(diff))
    w()
    for k in diff:
        a = disasm(old, k) or []
        b = disasm(new, k) or []
        w('--- %s ---' % k)
        if len(a) == len(b):
            for i in range(len(a)):
                if a[i] != b[i]:
                    w('    v1 |' + a[i])
                    w('    v2 |' + b[i])
        else:
            w('    (方法长度不同，列出全部)')
            for line in a:
                w('    v1 |' + line)
            for line in b:
                w('    v2 |' + line)
        w()
    if not diff:
        w('  （所有赌场相关方法反汇编逐行一致，游戏更新没有改动轮盘/赌场逻辑）')
        w()

    txt = '\n'.join(L)
    if outp:
        open(outp, 'w', encoding='utf-8').write(txt)
        print('WROTE %s (%d lines)' % (outp, len(L)))
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        print(txt)


if __name__ == '__main__':
    main()
