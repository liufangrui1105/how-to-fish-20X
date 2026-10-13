# -*- coding: utf-8 -*-
"""
ildump.py —— 纯 Python 的 .NET 元数据 + IL 分析器
（不依赖 PowerShell 语言模式，直接解析 PE / CLI metadata / IL）

用法:
  python ildump.py <dll> <out.txt> fields [TypeName]
  python ildump.py <dll> <out.txt> dump   <TypeName> [方法名,方法名]
  python ildump.py <dll> <out.txt> xref   <名字1,名字2,...>
  python ildump.py <dll> <out.txt> susp
  python ildump.py <dll> <out.txt> calls  <TypeName> <方法名>
"""
import sys, struct

# ------------------------------------------------------------------ IL 操作码
# name, operand kind: n=none i1=short inline i(1) i4=inline i(4) i8(8)
# r4(4) r8(8) var1=short inline var var2=2 br1=short branch br4=branch
# fld=inline field(4) mth=inline method(4) typ=inline type(4) str=inline string(4)
# sig=inline sig(4) tok=inline tok(4) sw=switch
OPS = {
 0x00:('nop','n'),0x01:('break','n'),0x02:('ldarg.0','n'),0x03:('ldarg.1','n'),
 0x04:('ldarg.2','n'),0x05:('ldarg.3','n'),0x06:('ldloc.0','n'),0x07:('ldloc.1','n'),
 0x08:('ldloc.2','n'),0x09:('ldloc.3','n'),0x0A:('stloc.0','n'),0x0B:('stloc.1','n'),
 0x0C:('stloc.2','n'),0x0D:('stloc.3','n'),0x0E:('ldarg.s','var1'),0x0F:('ldarga.s','var1'),
 0x10:('starg.s','var1'),0x11:('ldloc.s','var1'),0x12:('ldloca.s','var1'),0x13:('stloc.s','var1'),
 0x14:('ldnull','n'),0x15:('ldc.i4.m1','n'),0x16:('ldc.i4.0','n'),0x17:('ldc.i4.1','n'),
 0x18:('ldc.i4.2','n'),0x19:('ldc.i4.3','n'),0x1A:('ldc.i4.4','n'),0x1B:('ldc.i4.5','n'),
 0x1C:('ldc.i4.6','n'),0x1D:('ldc.i4.7','n'),0x1E:('ldc.i4.8','n'),0x1F:('ldc.i4.s','i1'),
 0x20:('ldc.i4','i4'),0x21:('ldc.i8','i8'),0x22:('ldc.r4','r4'),0x23:('ldc.r8','r8'),
 0x25:('dup','n'),0x26:('pop','n'),0x27:('jmp','mth'),0x28:('call','mth'),
 0x29:('calli','sig'),0x2A:('ret','n'),0x2B:('br.s','br1'),0x2C:('brfalse.s','br1'),
 0x2D:('brtrue.s','br1'),0x2E:('beq.s','br1'),0x2F:('bge.s','br1'),0x30:('bgt.s','br1'),
 0x31:('ble.s','br1'),0x32:('blt.s','br1'),0x33:('bne.un.s','br1'),0x34:('bge.un.s','br1'),
 0x35:('bgt.un.s','br1'),0x36:('ble.un.s','br1'),0x37:('blt.un.s','br1'),0x38:('br','br4'),
 0x39:('brfalse','br4'),0x3A:('brtrue','br4'),0x3B:('beq','br4'),0x3C:('bge','br4'),
 0x3D:('bgt','br4'),0x3E:('ble','br4'),0x3F:('blt','br4'),0x40:('bne.un','br4'),
 0x41:('bge.un','br4'),0x42:('bgt.un','br4'),0x43:('ble.un','br4'),0x44:('blt.un','br4'),
 0x45:('switch','sw'),
 0x46:('ldind.i1','n'),0x47:('ldind.u1','n'),0x48:('ldind.i2','n'),0x49:('ldind.u2','n'),
 0x4A:('ldind.i4','n'),0x4B:('ldind.u4','n'),0x4C:('ldind.i8','n'),0x4D:('ldind.i','n'),
 0x4E:('ldind.r4','n'),0x4F:('ldind.r8','n'),0x50:('ldind.ref','n'),0x51:('stind.ref','n'),
 0x52:('stind.i1','n'),0x53:('stind.i2','n'),0x54:('stind.i4','n'),0x55:('stind.i8','n'),
 0x56:('stind.r4','n'),0x57:('stind.r8','n'),0x58:('add','n'),0x59:('sub','n'),
 0x5A:('mul','n'),0x5B:('div','n'),0x5C:('div.un','n'),0x5D:('rem','n'),0x5E:('rem.un','n'),
 0x5F:('and','n'),0x60:('or','n'),0x61:('xor','n'),0x62:('shl','n'),0x63:('shr','n'),
 0x64:('shr.un','n'),0x65:('neg','n'),0x66:('not','n'),0x67:('conv.i1','n'),0x68:('conv.i2','n'),
 0x69:('conv.i4','n'),0x6A:('conv.i8','n'),0x6B:('conv.r4','n'),0x6C:('conv.r8','n'),
 0x6D:('conv.u4','n'),0x6E:('conv.u8','n'),0x6F:('callvirt','mth'),0x70:('cpobj','typ'),
 0x71:('ldobj','typ'),0x72:('ldstr','str'),0x73:('newobj','mth'),0x74:('castclass','typ'),
 0x75:('isinst','typ'),0x76:('conv.r.un','n'),0x79:('unbox','typ'),0x7A:('throw','n'),
 0x7B:('ldfld','fld'),0x7C:('ldflda','fld'),0x7D:('stfld','fld'),0x7E:('ldsfld','fld'),
 0x7F:('ldsflda','fld'),0x80:('stsfld','fld'),0x81:('stobj','typ'),0x82:('conv.ovf.i1.un','n'),
 0x83:('conv.ovf.i2.un','n'),0x84:('conv.ovf.i4.un','n'),0x85:('conv.ovf.i8.un','n'),
 0x86:('conv.ovf.u1.un','n'),0x87:('conv.ovf.u2.un','n'),0x88:('conv.ovf.u4.un','n'),
 0x89:('conv.ovf.u8.un','n'),0x8A:('conv.ovf.i.un','n'),0x8B:('conv.ovf.u.un','n'),
 0x8C:('box','typ'),0x8D:('newarr','typ'),0x8E:('ldlen','n'),0x8F:('ldelema','typ'),
 0x90:('ldelem.i1','n'),0x91:('ldelem.u1','n'),0x92:('ldelem.i2','n'),0x93:('ldelem.u2','n'),
 0x94:('ldelem.i4','n'),0x95:('ldelem.u4','n'),0x96:('ldelem.i8','n'),0x97:('ldelem.i','n'),
 0x98:('ldelem.r4','n'),0x99:('ldelem.r8','n'),0x9A:('ldelem.ref','n'),0x9B:('stelem.i','n'),
 0x9C:('stelem.i1','n'),0x9D:('stelem.i2','n'),0x9E:('stelem.i4','n'),0x9F:('stelem.i8','n'),
 0xA0:('stelem.r4','n'),0xA1:('stelem.r8','n'),0xA2:('stelem.ref','n'),0xA3:('ldelem','typ'),
 0xA4:('stelem','typ'),0xA5:('unbox.any','typ'),0xB3:('conv.ovf.i1','n'),0xB4:('conv.ovf.u1','n'),
 0xB5:('conv.ovf.i2','n'),0xB6:('conv.ovf.u2','n'),0xB7:('conv.ovf.i4','n'),0xB8:('conv.ovf.u4','n'),
 0xB9:('conv.ovf.i8','n'),0xBA:('conv.ovf.u8','n'),0xC2:('refanyval','typ'),0xC3:('ckfinite','n'),
 0xC6:('mkrefany','typ'),0xD0:('ldtoken','tok'),0xD1:('conv.u2','n'),0xD2:('conv.u1','n'),
 0xD3:('conv.i','n'),0xD4:('conv.ovf.i','n'),0xD5:('conv.ovf.u','n'),0xD6:('add.ovf','n'),
 0xD7:('add.ovf.un','n'),0xD8:('mul.ovf','n'),0xD9:('mul.ovf.un','n'),0xDA:('sub.ovf','n'),
 0xDB:('sub.ovf.un','n'),0xDC:('endfinally','n'),0xDD:('leave','br4'),0xDE:('leave.s','br1'),
 0xDF:('stind.i','n'),0xE0:('conv.u','n'),
}
OPS_FE = {
 0x00:('arglist','n'),0x01:('ceq','n'),0x02:('cgt','n'),0x03:('cgt.un','n'),0x04:('clt','n'),
 0x05:('clt.un','n'),0x06:('ldftn','mth'),0x07:('ldvirtftn','mth'),0x09:('ldarg','var2'),
 0x0A:('ldarga','var2'),0x0B:('starg','var2'),0x0C:('ldloc','var2'),0x0D:('ldloca','var2'),
 0x0E:('stloc','var2'),0x0F:('localloc','n'),0x11:('endfilter','n'),0x12:('unaligned.','i1'),
 0x13:('volatile.','n'),0x14:('tail.','n'),0x15:('initobj','typ'),0x16:('constrained.','typ'),
 0x17:('cpblk','n'),0x18:('initblk','n'),0x19:('no.','i1'),0x1A:('rethrow','n'),
 0x1C:('sizeof','typ'),0x1D:('refanytype','n'),0x1E:('readonly.','n'),
}
SZ = {'n':0,'i1':1,'var1':1,'br1':1,'var2':2,'i4':4,'r4':4,'br4':4,'fld':4,'mth':4,
      'typ':4,'str':4,'sig':4,'tok':4,'i8':8,'r8':8}

# ------------------------------------------------------------------ PE / metadata
class PE:
    def __init__(self, data):
        self.d = data
        e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
        assert data[e_lfanew:e_lfanew+4] == b'PE\0\0', 'not a PE'
        coff = e_lfanew + 4
        nsec, = struct.unpack_from('<H', data, coff+2)
        optsize, = struct.unpack_from('<H', data, coff+16)
        opt = coff + 20
        magic, = struct.unpack_from('<H', data, opt)
        ddoff = opt + (96 if magic == 0x10B else 112)
        cli_rva, cli_sz = struct.unpack_from('<II', data, ddoff + 14*8)
        sec = opt + optsize
        self.sections = []
        for i in range(nsec):
            b = sec + i*40
            name = data[b:b+8].rstrip(b'\0').decode('latin1')
            vsz, va, rsz, praw = struct.unpack_from('<IIII', data, b+8)
            self.sections.append((va, vsz, rsz, praw))
        self.cli = self.rva(cli_rva)
        md_rva, md_sz = struct.unpack_from('<II', data, self.cli + 8)
        self.metadata = self.rva(md_rva)

    def rva(self, rva):
        for va, vsz, rsz, praw in self.sections:
            if va <= rva < va + max(vsz, rsz):
                return praw + (rva - va)
        raise ValueError('bad rva 0x%x' % rva)

def u16(d, o): return struct.unpack_from('<H', d, o)[0]
def u32(d, o): return struct.unpack_from('<I', d, o)[0]

class MD:
    def __init__(self, data, root):
        d = data
        assert u32(d, root) == 0x424A5342, 'bad metadata sig'
        ver_len = u32(d, root + 12)
        p = root + 16 + ((ver_len + 3) & ~3)
        nstreams = u16(d, p + 2)
        p += 4
        self.streams = {}
        for i in range(nstreams):
            off, size = struct.unpack_from('<II', d, p)
            p += 8
            e = d.index(b'\0', p)
            nm = d[p:e].decode('latin1')
            p = e + 1
            p = (p + 3) & ~3
            self.streams[nm] = (root + off, size)
        self.d = d
        tbase, tsize = self.streams['#~']
        self.tables_off = tbase
        heapsizes = d[tbase + 6]
        valid = struct.unpack_from('<Q', d, tbase + 8)[0]
        p2 = tbase + 24
        self.rows = [0]*64
        for i in range(64):
            if valid & (1 << i):
                self.rows[i] = u32(d, p2); p2 += 4
        self.str_size = 4 if heapsizes & 1 else 2
        self.guid_size = 4 if heapsizes & 2 else 2
        self.blob_size = 4 if heapsizes & 4 else 2
        self.compute_sizes()
        self.parse()

    def idx(self, tbl): return 4 if self.rows[tbl] >= 0x10000 else 2
    def coded(self, tables, bits):
        m = max(self.rows[t] for t in tables)
        return 4 if m >= (1 << (16 - bits)) else 2

    def compute_sizes(self):
        R = self.rows; S = self.str_size; B = self.blob_size; G = self.guid_size
        c = self.coded
        td_or_ref = c([2,1,0x1B],2)
        has_const = c([4,8,0x17],2)
        has_ca    = c([6,4,1,2,8,9,0x0A,0,0x0E,0x17,0x14,0x11,0x1A,0x1B,0x20,0x23,0x26,0x27,0x28,0x2A,0x2C,0x2B],5)
        has_fm    = c([4,8],1)
        has_ds    = c([2,6,0x20],2)
        mrp       = c([2,1,0x1A,6,0x1B],3)
        has_sem   = c([0x14,0x17],1)
        mdor      = c([6,0x0A],1)
        mfwd      = c([4,6],1)
        impl      = c([0x26,0x23,0x27],2)
        cat       = c([0,0,6,0x0A,0],3)
        rs        = c([0,0x1A,0x23,1],2)
        tomd      = c([2,6],1)
        self.sizes = {
          0x00: 2+S+G+G+G, 0x01: rs+S+S, 0x02: 4+S+S+td_or_ref+self.idx(4)+self.idx(6),
          0x03: self.idx(4), 0x04: 2+S+B, 0x05: self.idx(6),
          0x06: 4+2+2+S+B+self.idx(8), 0x07: self.idx(8), 0x08: 2+2+S,
          0x09: self.idx(2)+td_or_ref, 0x0A: mrp+S+B, 0x0B: 2+has_const+B,
          0x0C: has_ca+cat+B, 0x0D: has_fm+B, 0x0E: 2+has_ds+B,
          0x0F: 2+4+self.idx(2), 0x10: 4+self.idx(4), 0x11: B,
          0x12: self.idx(2)+self.idx(0x14), 0x13: self.idx(0x14),
          0x14: 2+S+td_or_ref, 0x15: self.idx(2)+self.idx(0x17), 0x16: self.idx(0x17),
          0x17: 2+S+B, 0x18: 2+self.idx(6)+has_sem, 0x19: self.idx(2)+mdor+mdor,
          0x1A: S, 0x1B: B, 0x1C: 2+mfwd+S+self.idx(0x1A), 0x1D: 4+self.idx(4),
          0x1E: 8, 0x1F: 4, 0x20: 4+2+2+2+2+4+B+S+S,
          0x21: 4, 0x22: 12, 0x23: 2+2+2+2+4+B+S+S+B,
          0x24: 4+self.idx(0x23), 0x25: 12+self.idx(0x23), 0x26: 4+S+B,
          0x27: 4+4+S+S+impl, 0x28: 4+4+S+impl, 0x29: self.idx(2)+self.idx(2),
          0x2A: 2+2+tomd+S, 0x2B: mdor+B, 0x2C: self.idx(0x2A)+td_or_ref,
        }
        self.offs = {}
        p = self.tables_off + 24 + 4*bin(self.valid()).count('1') if False else 0
        # 重新计算表数据起点
        tbase = self.streams['#~'][0]
        valid = struct.unpack_from('<Q', self.d, tbase + 8)[0]
        p = tbase + 24 + 4*bin(valid).count('1')
        for i in range(64):
            self.offs[i] = p
            if self.rows[i]:
                p += self.rows[i]*self.sizes.get(i, 0)

    def valid(self):
        tbase = self.streams['#~'][0]
        return struct.unpack_from('<Q', self.d, tbase + 8)[0]

    def s(self, o):  # #Strings
        base = self.streams['#Strings'][0]
        e = self.d.index(b'\0', base+o)
        return self.d[base+o:e].decode('utf-8', 'replace')

    def row(self, tbl, i):
        return self.offs[tbl] + i*self.sizes[tbl]

    def sr(self, o):
        """读一个 #Strings 堆索引（2 或 4 字节）"""
        return u32(self.d, o) if self.str_size == 4 else u16(self.d, o)

    def br(self, o):
        """读一个 #Blob 堆索引"""
        return u32(self.d, o) if self.blob_size == 4 else u16(self.d, o)

    def ri(self, size, o):
        """按给定宽度（2 或 4）读一个索引"""
        return u32(self.d, o) if size == 4 else u16(self.d, o)

    def parse(self):
        d = self.d
        td_or_ref = self.coded([2,1,0x1B],2)
        mrp       = self.coded([2,1,0x1A,6,0x1B],3)
        rs        = self.coded([0,0x1A,0x23,1],2)
        self.typedefs = []
        for i in range(self.rows[2]):
            o = self.row(2, i)
            flags, = struct.unpack_from('<I', d, o)
            n_off = self.sr(o+4)
            ns_off = self.sr(o+4+self.str_size)
            base = o+4+2*self.str_size
            self.typedefs.append({'flags':flags,'name':self.s(n_off),'ns':self.s(ns_off),
                                  'fieldlist':self.ri(self.idx(4), base+td_or_ref),
                                  'methodlist':self.ri(self.idx(6), base+td_or_ref+self.idx(4))})
        self.fields = []
        for i in range(self.rows[4]):
            o = self.row(4, i)
            self.fields.append({'flags':u16(d,o),'name':self.s(self.sr(o+2))})
        self.methods = []
        for i in range(self.rows[6]):
            o = self.row(6, i)
            self.methods.append({'rva':u32(d,o),'flags':u16(d,o+6),'name':self.s(self.sr(o+8))})
        self.typerefs = []
        for i in range(self.rows[1]):
            o = self.row(1, i)
            self.typerefs.append({'name':self.s(self.sr(o+rs)),
                                  'ns':self.s(self.sr(o+rs+self.str_size))})
        self.memberrefs = []
        for i in range(self.rows[0x0A]):
            o = self.row(0x0A, i)
            self.memberrefs.append({'class':self.ri(mrp, o),'name':self.s(self.sr(o+mrp))})

    def type_name(self, tidx):
        if 0 < tidx <= len(self.typedefs):
            t = self.typedefs[tidx-1]
            return (t['ns']+'.' if t['ns'] else '')+t['name']
        return '?'

    def type_of_typedef(self, name):
        for i, t in enumerate(self.typedefs):
            if t['name'] == name or (t['ns']+'.'+t['name']) == name:
                return i+1
        return 0

    # 字段/方法 归属
    def methods_of(self, tidx):
        if tidx > len(self.typedefs): return []
        start = self.typedefs[tidx-1]['methodlist']-1
        end = self.typedefs[tidx]['methodlist']-1 if tidx < len(self.typedefs) else len(self.methods)
        return list(range(start, end))

    def fields_of(self, tidx):
        if tidx > len(self.typedefs): return []
        start = self.typedefs[tidx-1]['fieldlist']-1
        end = self.typedefs[tidx]['fieldlist']-1 if tidx < len(self.typedefs) else len(self.fields)
        return list(range(start, end))

    def resolve_memberref_class(self, cls):
        tag = cls & 7; idx = cls >> 3
        if tag == 0: return self.type_name(idx)
        if tag == 1: return self.typerefs[idx-1]['name'] if 0 < idx <= len(self.typerefs) else '?'
        if tag == 2: return 'ModuleRef'
        if tag == 3: return self.methods[idx-1]['name'] if 0 < idx <= len(self.methods) else '?'
        if tag == 4: return 'TypeSpec'
        return '?'

    def resolve_field(self, tok):
        t = tok >> 24; idx = tok & 0xFFFFFF
        if t == 0x04 and 0 < idx <= len(self.fields): return self.fields[idx-1]['name']
        if t == 0x0A and 0 < idx <= len(self.memberrefs): return self.memberrefs[idx-1]['name']
        return None

    def resolve_method(self, tok):
        t = tok >> 24; idx = tok & 0xFFFFFF
        if t == 0x06 and 0 < idx <= len(self.methods):
            return (None, self.methods[idx-1]['name'])
        if t == 0x0A and 0 < idx <= len(self.memberrefs):
            mr = self.memberrefs[idx-1]
            return (self.resolve_memberref_class(mr['class']), mr['name'])
        if t == 0x2B: return (None, 'MethodSpec')
        return (None, None)

    def il_of(self, midx):
        """返回 (il_bytes, 说明)"""
        m = self.methods[midx]
        if m['rva'] == 0: return None
        off = self.pe.rva(m['rva'])
        d = self.pe.d
        b = d[off]
        if (b & 3) == 2:            # tiny header
            size = b >> 2
            return d[off+1:off+1+size]
        else:                        # fat header: Flags(2) MaxStack(2) CodeSize(4) LocalVarSigTok(4)
            code_size = u32(d, off + 4)
            return d[off+12:off+12+code_size]

    # ---------------------------------------------------------- 类型 token 解析
    # IL 指令里的 inline type token 是**原始 4 字节 metadata token**
    # （高字节 = 表号，低 3 字节 = RID），不是压缩编码的 TypeDefOrRef。
    ELEM = {0x01:'void', 0x02:'bool', 0x03:'char', 0x04:'sbyte', 0x05:'byte',
            0x06:'short', 0x07:'ushort', 0x08:'int', 0x09:'uint', 0x0A:'long',
            0x0B:'ulong', 0x0C:'float', 0x0D:'double', 0x0E:'string',
            0x16:'TypedReference', 0x18:'IntPtr', 0x19:'UIntPtr', 0x1C:'object'}

    def _cint(self, d, p):
        """ECMA-335 II.23.2 压缩无符号整数"""
        b0 = d[p]
        if b0 & 0x80 == 0:
            return b0, p + 1
        if b0 & 0xC0 == 0x80:
            return ((b0 & 0x3F) << 8) | d[p + 1], p + 2
        return ((b0 & 0x1F) << 24) | (d[p + 1] << 16) | (d[p + 2] << 8) | d[p + 3], p + 4

    def typeref_name(self, rid):
        if 0 < rid <= len(self.typerefs):
            tr = self.typerefs[rid - 1]
            return (tr['ns'] + '.' if tr['ns'] else '') + tr['name']
        return 'TypeRef#%d' % rid

    def token_type_name(self, tok):
        """原始 metadata token -> 类型名"""
        tbl = tok >> 24
        rid = tok & 0xFFFFFF
        if tbl == 0x01: return self.typeref_name(rid)
        if tbl == 0x02: return self.type_name(rid)
        if tbl == 0x1B: return self.typespec_name(rid)
        return '0x%08x' % tok

    def typespec_name(self, rid):
        """TypeSpec 表 -> 尽量还原成可读类型名"""
        if not (0 < rid <= self.rows[0x1B]):
            return 'TypeSpec#%d' % rid
        if rid in getattr(self, '_ts_busy', ()):
            return 'TypeSpec#%d' % rid              # 防御：自引用
        busy = getattr(self, '_ts_busy', set())
        busy.add(rid)
        self._ts_busy = busy
        try:
            o = self.row(0x1B, rid - 1)
            blob = self.br(o)
            p = self.streams['#Blob'][0] + blob
            _ln, p = self._cint(self.d, p)
            nm, _ = self.sig_type(p, 0)
            return nm
        except Exception:
            return 'TypeSpec#%d' % rid
        finally:
            busy.discard(rid)

    def sig_type(self, p, depth):
        """解析一个 Type 签名，返回 (名字, 新位置)"""
        if depth > 12 or p >= len(self.d):
            return '...', p
        d = self.d
        e = d[p]; p += 1
        if e in self.ELEM:
            return self.ELEM[e], p
        if e in (0x11, 0x12):                       # VALUETYPE / CLASS
            tok, p = self._cint(d, p)               # 这里是 TypeDefOrRef **压缩**编码
            tag = tok & 3; idx = tok >> 2
            if tag == 0:   nm = self.type_name(idx)
            elif tag == 1: nm = self.typeref_name(idx)
            else:          nm = self.typespec_name(idx)
            return nm, p
        if e == 0x15:                               # GENERICINST
            if p >= len(d): return '...', p
            p += 1                                  # 跳过 class/valuetype 标记
            base, p = self.sig_type(p, depth + 1)
            n, p = self._cint(d, p)
            if n > 64: return base, p               # 防御：畸形 blob
            args = []
            for _ in range(n):
                a, p = self.sig_type(p, depth + 1)
                args.append(a)
            return '%s<%s>' % (base, ', '.join(args)), p
        if e == 0x1D:                               # SZARRAY
            t, p = self.sig_type(p, depth + 1)
            return t + '[]', p
        if e == 0x14:                               # ARRAY
            t, p = self.sig_type(p, depth + 1)
            rank, p = self._cint(d, p)
            nsizes, p = self._cint(d, p)
            if rank > 64 or nsizes > 64: return t + '[...]', p
            for _ in range(nsizes): _x, p = self._cint(d, p)
            nlo, p = self._cint(d, p)
            if nlo > 64: return t + '[...]', p
            for _ in range(nlo):
                _x, p = self._cint(d, p)
                _y, p = self._cint(d, p)
            return t + '[%s]' % (',' * (rank - 1)), p
        if e == 0x13:                               # VAR  (!0)
            n, p = self._cint(d, p); return '!%d' % n, p
        if e == 0x1E:                               # MVAR (!!0)
            n, p = self._cint(d, p); return '!!%d' % n, p
        if e == 0x0F:                               # PTR
            t, p = self.sig_type(p, depth + 1); return t + '*', p
        if e == 0x10:                               # BYREF
            t, p = self.sig_type(p, depth + 1); return t + '&', p
        if e in (0x1F, 0x20):                       # CMOD_REQD / CMOD_OPT
            _tok, p = self._cint(d, p)
            return self.sig_type(p, depth + 1)
        return 'elem%02x' % e, p

def main():
    dll, outp, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    data = open(dll, 'rb').read()
    pe = PE(data)
    md = MD(data, pe.metadata)
    md.pe = pe
    lines = []
    def w(s=''): lines.append(s)

    if mode == 'dbg':
        w('heapsizes: str=%d guid=%d blob=%d' % (md.str_size, md.guid_size, md.blob_size))
        w('valid=0x%016x' % md.valid())
        for i in range(64):
            if md.rows[i]:
                w('  table 0x%02x rows=%-6d size=%-4d off=0x%x' % (i, md.rows[i], md.sizes.get(i, 0), md.offs[i]))
        w('parsed: typedefs=%d fields=%d methods=%d typerefs=%d memberrefs=%d'
          % (len(md.typedefs), len(md.fields), len(md.methods), len(md.typerefs), len(md.memberrefs)))
        w('--- 前 15 个 TypeDef ---')
        for i in range(min(15, len(md.typedefs))):
            t = md.typedefs[i]
            w('  TD[%d] name=%-28r ns=%-22r fieldlist=%-6d methodlist=%d'
              % (i, t['name'], t['ns'], t['fieldlist'], t['methodlist']))
        w('--- 找 LocalCasino / CasinoManager ---')
        for i, t in enumerate(md.typedefs):
            if t['name'] in ('LocalCasino', 'CasinoManager', 'Item'):
                w('  TD[%d] %s fieldlist=%d methodlist=%d' % (i, t['name'], t['fieldlist'], t['methodlist']))
        open(outp, 'w', encoding='utf-8').write('\n'.join(lines))
        print('WROTE')
        return

    if mode == 'fields':
        target = sys.argv[4] if len(sys.argv) > 4 else None
        for i, t in enumerate(md.typedefs):
            tidx = i+1
            if target and t['name'] != target: continue
            fs = md.fields_of(tidx)
            w('=== %s (%d 字段) ===' % (md.type_name(tidx), len(fs)))
            for k, fi in enumerate(fs):
                f = md.fields[fi]
                w('  %-3d %-34s flags=0x%04x' % (k, f['name'], f['flags']))

    elif mode == 'dump':
        target = sys.argv[4]
        only = sys.argv[5].split(',') if len(sys.argv) > 5 else None
        tidx = md.type_of_typedef(target)
        w('=== %s ===' % md.type_name(tidx))
        for mi in md.methods_of(tidx):
            m = md.methods[mi]
            if only and m['name'] not in only: continue
            w('  ---- %s ----' % m['name'])
            il = md.il_of(mi)
            if il is None: w('    [无 IL]'); continue
            i = 0
            while i < len(il):
                start = i; b = il[i]
                if b == 0xFE:
                    name, kind = OPS_FE.get(il[i+1], ('<fe%02x>' % il[i+1], 'n')); i += 2
                else:
                    name, kind = OPS.get(b, ('< %02x>' % b, 'n')); i += 1
                pos = i
                if kind == 'sw':
                    n = struct.unpack_from('<i', il, pos)[0]
                    base = pos+4+4*n; i = base
                    parts = []
                    for k in range(n):
                        dd = struct.unpack_from('<i', il, pos+4+4*k)[0]
                        parts.append('case%d->IL_%04x' % (k, base+dd))
                    txt = '(%d) %s' % (n, ', '.join(parts))
                else:
                    sz = SZ[kind]; i = pos + sz
                    if kind == 'n': txt = ''
                    elif kind == 'i1':
                        v = il[pos]; v = v-256 if v > 127 else v; txt = str(v)
                    elif kind == 'var1': txt = 'V%d' % il[pos]
                    elif kind == 'var2': txt = 'V%d' % struct.unpack_from('<H', il, pos)[0]
                    elif kind == 'br1':
                        dd = il[pos]; dd = dd-256 if dd > 127 else dd
                        txt = 'IL_%04x' % (i+dd)
                    elif kind == 'br4':
                        dd = struct.unpack_from('<i', il, pos)[0]; txt = 'IL_%04x' % (i+dd)
                    elif kind == 'i4': txt = str(struct.unpack_from('<i', il, pos)[0])
                    elif kind == 'i8': txt = str(struct.unpack_from('<q', il, pos)[0])
                    elif kind == 'r4': txt = str(struct.unpack_from('<f', il, pos)[0])
                    elif kind == 'r8': txt = str(struct.unpack_from('<d', il, pos)[0])
                    elif kind in ('fld','mth','typ','tok','sig','str'):
                        tok = struct.unpack_from('<I', il, pos)[0]
                        if kind == 'fld':
                            nm = md.resolve_field(tok); txt = nm or ('0x%08x' % tok)
                        elif kind == 'mth':
                            cls, nm = md.resolve_method(tok)
                            txt = (cls+'::'+nm) if cls else (nm or ('0x%08x' % tok))
                        elif kind == 'str':
                            base = md.streams['#US'][0]
                            o = base + (tok & 0xFFFFFF)
                            ln = md.d[o]
                            if ln & 0x80:
                                ln = ((ln & 0x7f) << 8) | md.d[o+1]; o += 2
                            else: o += 1
                            txt = '"' + md.d[o:o+ln-1].decode('utf-16-le', 'replace') + '"'
                        elif kind in ('typ', 'tok'):
                            txt = md.token_type_name(tok)
                        else:
                            txt = '0x%08x' % tok
                    else: txt = ''
                w('    IL_%04x: %-12s %s' % (start, name, txt))

    elif mode == 'xref':
        names = set(sys.argv[4].split(','))
        res = {n: [] for n in names}
        for tidx in range(1, len(md.typedefs)+1):
            tname = md.type_name(tidx)
            for mi in md.methods_of(tidx):
                m = md.methods[mi]
                il = md.il_of(mi)
                if il is None: continue
                i = 0
                while i < len(il):
                    b = il[i]
                    if b == 0xFE:
                        name, kind = OPS_FE.get(il[i+1], ('?','n')); i += 2
                    else:
                        name, kind = OPS.get(b, ('?','n')); i += 1
                    pos = i
                    if kind == 'sw':
                        n = struct.unpack_from('<i', il, pos)[0]; i = pos+4+4*n; continue
                    i = pos + SZ[kind]
                    if kind == 'fld':
                        nm = md.resolve_field(struct.unpack_from('<I', il, pos)[0])
                        if nm in names:
                            act = '★写' if name in ('stfld','stsfld') else '读  '
                            res[nm].append('%s %s::%s' % (act, tname, m['name']))
                    elif kind == 'mth':
                        cls, nm = md.resolve_method(struct.unpack_from('<I', il, pos)[0])
                        if nm in names:
                            res[nm].append('调用 %s::%s   <- %s' % (cls, nm, tname))
        for n in sys.argv[4].split(','):
            w('')
            w('########## %s ##########' % n)
            rows = sorted(set(res.get(n, [])))
            if not rows: w('  （无引用）')
            for r in rows: w('  ' + r)

    elif mode == 'susp':
        keys = ('last','prev','streak','pity','histor','result','seed','random','rig','cheat',
                'bias','luck','chance','odds','payout','multiplier','weight','forcecolor','rigged')
        w('=== 名字可疑的字段 ===')
        for tidx in range(1, len(md.typedefs)+1):
            tname = md.type_name(tidx)
            for fi in md.fields_of(tidx):
                f = md.fields[fi]
                low = f['name'].lower()
                for k in keys:
                    if k in low:
                        w('  %-26s %-36s' % (tname, f['name'])); break

    elif mode == 'calls':
        tidx = md.type_of_typedef(sys.argv[4]); want = sys.argv[5]
        for mi in md.methods_of(tidx):
            m = md.methods[mi]
            if m['name'] != want: continue
            w('=== %s::%s 调用了 ===' % (md.type_name(tidx), m['name']))
            il = md.il_of(mi)
            if il is None: continue
            i = 0
            while i < len(il):
                b = il[i]
                if b == 0xFE: name, kind = OPS_FE.get(il[i+1], ('?','n')); i += 2
                else: name, kind = OPS.get(b, ('?','n')); i += 1
                pos = i
                if kind == 'sw':
                    n = struct.unpack_from('<i', il, pos)[0]; i = pos+4+4*n; continue
                i = pos + SZ[kind]
                if kind == 'mth' and name in ('call','callvirt','newobj'):
                    cls, nm = md.resolve_method(struct.unpack_from('<I', il, pos)[0])
                    w('  %s::%s' % (cls, nm))
    open(outp, 'w', encoding='utf-8').write('\n'.join(lines))
    print('WROTE %s (%d lines)' % (outp, len(lines)))

main()
