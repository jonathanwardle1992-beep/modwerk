# Private test patch for the Octatrack TRACK TRIG EDIT menu.
# Not a module: it rewrites a copy of the owner's OS 1.40C and packs a card
# image outside this repository. Do not commit the image or the OS extract.
#
# Row order is TRIGS, MICRO T, SLIDE, SWING, REC.TRG. The list holds five
# rows and the window shows four, so REC.TRG scrolls into the frame and TRIGS
# scrolls off the top. LEVEL calls the stock per-trig MICRO TIMING writer
# for every step of the selected track. With the MIDI button off that is
# the audio field; with it on, the MIDI field, and the other is left alone.
# The footer prints the stock fractions. The lane's dots are shifted so
# the on-grid cursor sits on the centre 0.
#
# The first card image put this stub in the trailing zero pad at 0x40108800.
# FUNC+BANK jumps to the label entry at 0x40108832. On the unit that fetch
# raised VEC 0x0B (unimplemented line F). The word in the file there is
# jsr (4EB9), which is not line F and which the stock menu already uses, so
# the pad no longer held the stub when the menu opened. This build places
# the stub in an interior zero gap that the image actually keeps.

import hashlib
import os
import struct
import subprocess
import sys

from capstone import CS_ARCH_M68K, CS_MODE_M68K_040, Cs

BASE = 0x40000400
# Interior gap: zeros from 0x400d24d0, and one live load of the zero long at
# 0x400d2cdc. Stay clear of that long.
ORG = 0x400D2500
ORG_LIMIT = 0x400D2CD0
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MAIN_PATH = os.path.join(os.environ["TEMP"], "ot-main-private.bin")
PATCHED_PATH = os.path.join(os.environ["TEMP"], "ot-main-microt.bin")
LISTING_PATH = os.path.join(os.environ["TEMP"], "micro-t-listing.txt")
STOCK_BIN = r"C:\Users\Roy Walker\.cache\modwerk-native\os-dist\OCTATRACK_OS1.40C.bin"
OUT_BIN = r"C:\Users\Roy Walker\Desktop\MICRO-T-9\OCTATRACK_OS1.40C.bin"
VERSION = "MICRO T9"
PAGE = 0x460D1018
SETTER = 0x4002D640
PATLIVE = 0x100B14D0

MIDI = 0x40033970
MODE = 0x40033990
DRAW = 0x4007B780
LEVEL_STOCK = 0x4007BD64
LABEL_RET = 0x4007B874
FOOT_TST = 0x4007B9AE
FOOT_AFTER = 0x4007B9E0
TEXT = 0x40013904
FONT = 0x400BA876
REFRESH = 0x4009DA20
DIRTYFN = 0x40027E00
BANKPTR = 0x46C82456
BANKB = 0x800065BD
PATB = 0x800065BE
TRACKB = 0x100B14CC
SEL = 0x460E73E4
SCROLL = 0x460E73DC
LIST = 0x460E73DC
LINE = 0x40012254
ROWTEXT = 0x40012BD8
FRAC = 0x400B2528
ONGRID = 0x400B4024
MAGIC = 0x100F8FFC
TABLE = 0x100F9000
BATT = 0x1001614E
DIRTYF = 0x100F8598
MAGIC_VAL = 0x4D54494D


def expect(blob, text):
    ins = next(Cs(CS_ARCH_M68K, CS_MODE_M68K_040).disasm(blob, 0x40108800))
    got = f"{ins.mnemonic} {ins.op_str}".strip()
    if got != text or ins.size != len(blob):
        raise SystemExit(f"{blob.hex()}: {got!r} size {ins.size}, expected {text!r}")


def preflight():
    samples = {
        "242f0008": "move.l $8(a7), d2",
        "4298": "clr.l (a0)+",
        "0280ffffe07f": "andi.l #$ffffe07f, d0",
        "0081ffffffc0": "ori.l #$ffffffc0, d1",
        "2200": "move.l d0, d1",
        "2c00": "move.l d0, d6",
        "117c00540001": "move.b #$54, $1(a0)",
        "10bc004d": "move.b #$4d, (a0)",
        "42280007": "clr.b $7(a0)",
        "363c08b0": "move.w #$8b0, d3",
        "47f91001614e": "lea.l $1001614e.l, a3",
        "d082": "add.l d2, d0",
        "9c83": "sub.l d3, d6",
        "4481": "neg.l d1",
        "74e9": "moveq #$e9, d2",
        "ef88": "lsl.l #$7, d0",
        "ee89": "lsr.l #$7, d1",
        "c2c3": "mulu.w d3, d1",
        "2f13": "move.l (a3), -(a7)",
        "2f0c": "move.l a4, -(a7)",
        "2080": "move.l d0, (a0)",
        "3080": "move.w d0, (a0)",
        "3280": "move.w d0, (a1)",
        "3010": "move.w (a0), d0",
        "1080": "move.b d0, (a0)",
        "1010": "move.b (a0), d0",
        "4fef0024": "lea.l $24(a7), a7",
        "48780025": "pea.l $25.w",
        "4878ffff": "pea.l $ffff.w",
        "42a7": "clr.l -(a7)",
        "2f00": "move.l d0, -(a7)",
        "0c82ffffffe9": "cmpi.l #$ffffffe9, d2",
        "d1fc0009b332": "adda.l #$9b332, a0",
        "d5fc00000830": "adda.l #$830, a2",
        "247946c82456": "movea.l $46c82456.l, a2",
        "244a": "movea.l a2, a2",
    }
    # movea.l a2, a0 is 204A, not 244A. Checked below.
    samples["204a"] = "movea.l a2, a0"
    samples["224b"] = "movea.l a3, a1"
    del samples["244a"]
    for blob, text in samples.items():
        expect(bytes.fromhex(blob), text)


class Asm:
    def __init__(self):
        self.org = ORG
        self.pc = ORG
        self.buf = bytearray()
        self.labels = {}
        self.branches = []
        self.absolutes = []

    def label(self, name):
        if name in self.labels:
            raise SystemExit("duplicate " + name)
        self.labels[name] = self.pc

    def raw(self, data):
        self.buf += data
        self.pc += len(data)

    def w(self, value):
        self.raw(struct.pack(">H", value & 0xFFFF))

    def l(self, value):
        self.raw(struct.pack(">I", value & 0xFFFFFFFF))

    def branch(self, op, name):
        self.branches.append((self.pc, name))
        self.raw(bytes([op, 0x00, 0x00, 0x00]))

    def beq(self, name):
        self.branch(0x67, name)

    def bne(self, name):
        self.branch(0x66, name)

    def bra(self, name):
        self.branch(0x60, name)

    def blt(self, name):
        self.branch(0x6D, name)

    def bge(self, name):
        self.branch(0x6C, name)

    def ble(self, name):
        self.branch(0x6F, name)

    def bmi(self, name):
        self.branch(0x6B, name)

    def abs_long(self, name):
        self.absolutes.append((self.pc, name))
        self.l(0)

    def jsr_abs(self, addr):
        self.raw(b"\x4e\xb9")
        self.l(addr)

    def jsr_lbl(self, name):
        self.raw(b"\x4e\xb9")
        self.abs_long(name)

    def jmp_abs(self, addr):
        self.raw(b"\x4e\xf9")
        self.l(addr)

    def rts(self):
        self.raw(b"\x4e\x75")

    def moveq(self, imm, dn):
        self.raw(bytes([0x70 | (dn << 1), imm & 0xFF]))

    def cmpi_l(self, imm, dn):
        self.raw(bytes([0x0C, 0x80 | dn]))
        self.l(imm)

    def move_l_imm(self, imm, dn):
        self.raw(bytes([0x20 | (dn << 1), 0x3C]))
        self.l(imm)

    def move_w_imm(self, imm, dn):
        self.raw(bytes([0x30 | (dn << 1), 0x3C]))
        self.w(imm)

    def move_l_rr(self, src, dst):
        self.raw(bytes([0x20 | (dst << 1), src & 7]))

    def move_l_abs_dn(self, addr, dn):
        self.raw(bytes([0x20 | (dn << 1), 0x39]))
        self.l(addr)

    def move_l_dn_abs(self, dn, addr):
        self.raw(bytes([0x23, 0xC0 | dn]))
        self.l(addr)

    def move_b_abs_dn(self, addr, dn):
        self.raw(bytes([0x10 | (dn << 1), 0x39]))
        self.l(addr)

    def movea_l_abs(self, addr, an):
        self.raw(bytes([0x20 | (an << 1), 0x79]))
        self.l(addr)

    def lea_lbl(self, name, an):
        self.raw(bytes([0x41 | (an << 1), 0xF9]))
        self.abs_long(name)

    def lea_abs(self, addr, an):
        self.raw(bytes([0x41 | (an << 1), 0xF9]))
        self.l(addr)

    def movea_l_an(self, src, dst):
        self.raw(bytes([0x20 | (dst << 1), 0x48 | src]))

    def add_l(self, src, dst):
        self.raw(bytes([0xD0 | (dst << 1), 0x80 | src]))

    def sub_l(self, src, dst):
        self.raw(bytes([0x90 | (dst << 1), 0x80 | src]))

    def or_l(self, src, dst):
        self.raw(bytes([0x80 | (dst << 1), 0x80 | src]))

    def adda_l_dn(self, dn, an):
        self.raw(bytes([0xD0 | (an << 1) | 1, 0xC0 | dn]))

    def adda_l_imm(self, imm, an):
        self.raw(bytes([0xD0 | (an << 1) | 1, 0xFC]))
        self.l(imm)

    def addi_l(self, imm, dn):
        self.raw(bytes([0x06, 0x80 | dn]))
        self.l(imm)

    def subi_l(self, imm, dn):
        self.raw(bytes([0x04, 0x80 | dn]))
        self.l(imm)

    def andi_l(self, imm, dn):
        self.raw(bytes([0x02, 0x80 | dn]))
        self.l(imm)

    def ori_l(self, imm, dn):
        self.raw(bytes([0x00, 0x80 | dn]))
        self.l(imm)

    def addq_l(self, n, dn):
        enc = 0 if n == 8 else n
        self.raw(bytes([0x50 | (enc << 1), 0x80 | dn]))

    def subq_l(self, n, dn):
        enc = 0 if n == 8 else n
        self.raw(bytes([0x50 | (enc << 1) | 1, 0x80 | dn]))

    def lsl_l(self, n, dn):
        self.raw(bytes([0xE0 | (n << 1) | 1, 0x88 | dn]))

    def lsr_l(self, n, dn):
        self.raw(bytes([0xE0 | (n << 1), 0x88 | dn]))

    def mulu_w(self, src, dst):
        self.raw(bytes([0xC0 | (dst << 1), 0xC0 | src]))

    def ext_w(self, dn):
        self.raw(bytes([0x48, 0x80 | dn]))

    def ext_l(self, dn):
        self.raw(bytes([0x48, 0xC0 | dn]))

    def neg_l(self, dn):
        self.raw(bytes([0x44, 0x80 | dn]))

    def tst_l(self, dn):
        self.raw(bytes([0x4A, 0x80 | dn]))

    def clr_l_post(self, an):
        self.raw(bytes([0x42, 0x98 | an]))

    def move_l_sp(self, disp, dn):
        self.raw(bytes([0x20 | (dn << 1), 0x2F]))
        self.w(disp)

    def move_b_imm_an(self, imm, an):
        self.raw(bytes([0x10 | (an << 1), 0xBC]))
        self.w(imm & 0xFF)

    def move_b_imm_d16(self, imm, disp, an):
        self.raw(bytes([0x10 | (an << 1) | 1, 0x7C]))
        self.w(imm & 0xFF)
        self.w(disp)

    def move_b_dn_d16(self, dn, disp, an):
        self.raw(bytes([0x10 | (an << 1) | 1, 0x40 | dn]))
        self.w(disp)

    def clr_b_d16(self, disp, an):
        self.raw(bytes([0x42, 0x28 | an]))
        self.w(disp)

    def move_b_an_dn(self, an, dn):
        self.raw(bytes([0x10 | (dn << 1), 0x10 | an]))

    def move_b_dn_an(self, dn, an):
        self.raw(bytes([0x10 | (an << 1), 0x80 | dn]))

    def move_w_an_dn(self, an, dn):
        self.raw(bytes([0x30 | (dn << 1), 0x10 | an]))

    def move_w_dn_an(self, dn, an):
        self.raw(bytes([0x30 | (an << 1), 0x80 | dn]))

    def move_l_dn_an(self, dn, an):
        self.raw(bytes([0x20 | (an << 1), 0x80 | dn]))

    def move_l_ind_predec_sp(self, an):
        self.raw(bytes([0x2F, 0x10 | an]))

    def move_l_an_predec_sp(self, an):
        self.raw(bytes([0x2F, 0x08 | an]))

    def move_l_dn_predec_sp(self, dn):
        self.raw(bytes([0x2F, dn & 7]))

    def pea_abs(self, addr):
        self.raw(b"\x48\x79")
        self.l(addr)

    def pea_lbl(self, name):
        self.raw(b"\x48\x79")
        self.abs_long(name)

    def pea_w(self, imm):
        self.raw(b"\x48\x78")
        self.w(imm)

    def clr_l_sp(self):
        self.raw(b"\x42\xa7")

    def lea_sp(self, disp):
        self.raw(b"\x4f\xef")
        self.w(disp)

    def move_b_imm_post(self, imm, an):
        self.raw(bytes([0x10, 0xFC | (an << 1)]))
        self.w(imm & 0xFF)

    def move_b_post_dn(self, an, dn):
        self.raw(bytes([0x10 | (dn << 1), 0x18 | an]))

    def move_b_dn_post(self, dn, an):
        self.raw(bytes([0x10 | (an << 1), 0xC0 | dn]))

    def movea_l_ind(self, an):
        self.raw(bytes([0x22, 0x50 | an]))

    def movea_l_dn(self, dn, an):
        self.raw(bytes([0x20 | (an << 1), 0x40 | dn]))

    def pop_l_dn(self, dn):
        self.raw(bytes([0x20 | (dn << 1), 0x1F]))

    def cmp_l(self, src, dst):
        self.raw(bytes([0xB0 | (dst << 1), 0x80 | src]))

    def move_l_an_dn(self, an, dn):
        self.raw(bytes([0x20 | (dn << 1), 0x08 | an]))

    def resolve(self):
        for addr, name in self.branches:
            disp = self.labels[name] - (addr + 2)
            if disp == 0 or not -32768 <= disp <= 32767:
                raise SystemExit(f"branch {name} from {addr:#x} disp {disp}")
            off = addr - self.org + 2
            self.buf[off : off + 2] = struct.pack(">h", disp)
        for addr, name in self.absolutes:
            off = addr - self.org
            self.buf[off : off + 4] = struct.pack(">I", self.labels[name])

    def disassemble(self, end):
        code = bytes(self.buf[: end - self.org])
        insns = list(Cs(CS_ARCH_M68K, CS_MODE_M68K_040).disasm(code, self.org))
        covered = sum(ins.size for ins in insns)
        if covered != len(code):
            raise SystemExit(f"cave disassembly covered {covered} of {len(code)}")
        starts = {ins.address for ins in insns}
        for ins in insns:
            if ins.mnemonic.startswith("."):
                raise SystemExit(f"undecoded {ins.mnemonic} at {ins.address:#x}")
            if ins.bytes[0] & 0xF0 == 0xF0:
                raise SystemExit(f"line F opcode at {ins.address:#x}: {ins.bytes.hex()} {ins.mnemonic}")
            banned = ins.mnemonic.split(".")[0]
            if banned in {
                "bfchg", "bfclr", "bfexts", "bfextu", "bfffo", "bfins", "bfset", "bftst",
                "cas", "cas2", "chk", "chk2", "cmp2", "callm", "rtm", "pack", "unpk",
                "moves", "movep", "exg", "addx", "subx", "abcd", "sbcd", "nbcd",
                "rtd", "rtr", "trapv", "dbra", "dbf", "tdiv", "divs", "divu",
            }:
                raise SystemExit(f"ColdFire rejects {ins.mnemonic} at {ins.address:#x}")
            root = ins.mnemonic.split(".")[0]
            if root in {"bra", "beq", "bne", "blt", "bge", "ble", "bmi", "bpl", "bgt", "bls"}:
                target = int(ins.op_str.lstrip("$"), 16)
                if target not in starts:
                    raise SystemExit(f"{ins.mnemonic} at {ins.address:#x} -> {target:#x}")
        return insns


def program():
    a = Asm()
    a.label("level")
    a.move_l_abs_dn(SEL, 0)
    a.cmpi_l(1, 0)
    a.bne("level_stock")
    # Same slot the swing handler reads, before this frame moves the stack.
    a.move_l_sp(8, 2)
    a.raw(b"\x4f\xef\xff\xd4")
    a.raw(b"\x48\xd7\x7c\xfc")
    a.jsr_lbl("apply")
    a.raw(b"\x4c\xd7\x7c\xfc")
    a.raw(b"\x4f\xef\x00\x2c")
    a.jmp_abs(DRAW)
    a.label("level_stock")
    a.jmp_abs(LEVEL_STOCK)

    a.label("label")
    a.jsr_abs(MIDI)
    a.tst_l(0)
    a.beq("label_stock")
    a.cmpi_l(1, 2)
    a.bne("label_stock")
    a.pea_lbl("micro")
    a.bra("label_ff")
    a.label("label_stock")
    a.move_l_ind_predec_sp(3)
    a.label("label_ff")
    a.pea_w(0xFFFF)
    a.jmp_abs(LABEL_RET)

    a.label("footer")
    a.move_l_abs_dn(SEL, 0)
    a.cmpi_l(1, 0)
    a.bne("footer_stock")
    a.jsr_lbl("format")
    a.label("footer_draw")
    a.pea_w(0x25)
    a.pea_lbl("strbuf")
    a.pea_lbl("strbuf")
    a.clr_l_sp()
    a.clr_l_sp()
    a.pea_w(6)
    a.pea_w(6)
    a.move_l_an_predec_sp(4)
    a.pea_abs(FONT)
    a.jsr_abs(TEXT)
    a.lea_sp(0x24)
    a.jmp_abs(FOOT_AFTER)
    a.label("footer_stock")
    a.jsr_abs(MODE)
    a.jmp_abs(FOOT_TST)

    a.label("format")
    a.jsr_lbl("current")
    a.move_l_rr(0, 1)
    a.lea_lbl("strbuf", 0)
    a.move_b_imm_post(ord("M"), 0)
    a.move_b_imm_post(ord("T"), 0)
    a.moveq(0, 0)
    a.move_b_abs_dn(TRACKB, 0)
    a.andi_l(7, 0)
    a.addq_l(1, 0)
    a.addi_l(0x30, 0)
    a.move_b_dn_post(0, 0)
    a.move_b_imm_post(ord(":"), 0)
    a.jsr_lbl("write_metric")
    a.rts()

    a.label("current")
    a.jsr_lbl("ensure")
    a.moveq(0, 0)
    a.move_b_abs_dn(BANKB, 0)
    a.andi_l(0xF, 0)
    a.lsl_l(7, 0)
    a.moveq(0, 1)
    a.move_b_abs_dn(PATLIVE, 1)
    a.andi_l(0xF, 1)
    a.lsl_l(3, 1)
    a.add_l(1, 0)
    a.moveq(0, 1)
    a.move_b_abs_dn(TRACKB, 1)
    a.andi_l(7, 1)
    a.add_l(1, 0)
    a.lea_abs(TABLE, 0)
    a.adda_l_dn(0, 0)
    a.move_b_an_dn(0, 0)
    a.ext_w(0)
    a.ext_l(0)
    a.rts()

    a.label("ensure")
    a.move_l_abs_dn(MAGIC, 0)
    a.cmpi_l(MAGIC_VAL, 0)
    a.beq("ensure_ok")
    a.lea_abs(TABLE, 0)
    a.move_l_imm(512, 0)
    a.label("ensure_loop")
    a.clr_l_post(0)
    a.subq_l(1, 0)
    a.bne("ensure_loop")
    a.move_l_imm(MAGIC_VAL, 0)
    a.move_l_dn_abs(0, MAGIC)
    a.label("ensure_ok")
    a.rts()

    a.label("apply")
    a.cmpi_l(23, 2)
    a.ble("apply_dlo")
    a.moveq(23, 2)
    a.bra("apply_dok")
    a.label("apply_dlo")
    a.cmpi_l(-23, 2)
    a.bge("apply_dok")
    a.moveq(-23 & 0xFF, 2)
    a.label("apply_dok")
    a.tst_l(2)
    a.beq("apply_rts")
    a.jsr_lbl("current")
    a.move_l_rr(0, 3)
    a.add_l(2, 0)
    a.cmpi_l(23, 0)
    a.ble("apply_nlo")
    a.moveq(23, 0)
    a.bra("apply_nok")
    a.label("apply_nlo")
    a.cmpi_l(-23, 0)
    a.bge("apply_nok")
    a.moveq(-23 & 0xFF, 0)
    a.label("apply_nok")
    a.move_b_dn_an(0, 0)
    a.cmp_l(3, 0)
    a.beq("apply_rts")
    a.move_l_rr(0, 6)
    a.jsr_lbl("rewrite")
    a.jsr_lbl("dirty")
    a.label("apply_rts")
    a.rts()

    # Same writer the per-trig page calls. The MIDI button picks the field:
    # off is the audio tracks, on is the MIDI tracks.
    a.label("rewrite")
    a.move_l_abs_dn(PAGE, 0)
    a.move_l_dn_predec_sp(0)
    a.jsr_abs(MIDI)
    a.tst_l(0)
    a.beq("rewrite_audio")
    a.moveq(2, 0)
    a.bra("rewrite_set")
    a.label("rewrite_audio")
    a.moveq(0, 0)
    a.label("rewrite_set")
    a.move_l_dn_abs(0, PAGE)
    a.jsr_lbl("steps")
    a.pop_l_dn(0)
    a.move_l_dn_abs(0, PAGE)
    a.rts()

    a.label("steps")
    a.moveq(0, 4)
    a.label("step")
    a.move_l_dn_predec_sp(4)
    a.move_l_dn_predec_sp(6)
    a.move_l_dn_predec_sp(6)
    a.move_l_dn_predec_sp(4)
    a.jsr_abs(SETTER)
    a.lea_sp(8)
    a.pop_l_dn(6)
    a.pop_l_dn(4)
    a.addq_l(1, 4)
    a.cmpi_l(64, 4)
    a.blt("step")
    a.rts()

    a.label("dirty")
    a.movea_l_abs(BANKPTR, 1)
    a.movea_l_an(1, 0)
    a.adda_l_imm(0x9B332, 0)
    a.moveq(1, 0)
    a.move_l_dn_an(0, 0)
    a.move_l_dn_abs(0, DIRTYF)
    a.jsr_abs(DIRTYFN)
    a.moveq(0, 0)
    a.move_b_abs_dn(TRACKB, 0)
    a.andi_l(7, 0)
    a.move_l_dn_predec_sp(0)
    a.jsr_abs(REFRESH)
    a.lea_sp(4)
    a.moveq(0, 0)
    a.move_b_abs_dn(TRACKB, 0)
    a.andi_l(7, 0)
    a.addq_l(8, 0)
    a.move_l_dn_predec_sp(0)
    a.jsr_abs(REFRESH)
    a.lea_sp(4)
    a.rts()

    # MIDI selection landed on SLIDE: park it on MICRO T (the row above).
    a.label("force1")
    a.pea_w(1)
    a.pea_abs(0x460E73DC)
    a.jsr_abs(0x4007EDB0)
    a.lea_sp(8)
    a.rts()

    # One audio machine hides TRIGS and SLIDE. Skip those new indices only.
    a.label("hide_slide_label")
    a.cmpi_l(0, 2)
    a.beq("hide_slide_label_yes")
    a.cmpi_l(2, 2)
    a.bne("hide_slide_label_no")
    a.label("hide_slide_label_yes")
    a.jmp_abs(0x4007B8AE)
    a.label("hide_slide_label_no")
    a.jmp_abs(0x4007B86E)

    a.label("hide_slide_grid")
    a.cmpi_l(0, 7)
    a.beq("hide_slide_grid_yes")
    a.cmpi_l(2, 7)
    a.bne("hide_slide_grid_no")
    a.label("hide_slide_grid_yes")
    a.jmp_abs(0x4007BD24)
    a.label("hide_slide_grid_no")
    a.jmp_abs(0x4007BAC4)

    # This menu can select row 4. The shared clamp still tops out at 3.
    a.label("mode4")
    a.move_l_sp(4, 0)
    a.cmpi_l(4, 0)
    a.branch(0x63, "mode4_ok")
    a.moveq(4, 0)
    a.label("mode4_ok")
    a.move_l_dn_abs(0, 0x460D5DB4)
    a.raw(b"\x42\xaf\x00\x04")
    a.jmp_abs(0x4007E998)

    # First visible row is the scroll offset. The name pointer is already
    # the new table; walk it forward by one entry per scrolled row.
    a.label("label_origin")
    a.move_l_abs_dn(SCROLL, 2)
    a.move_l_rr(2, 0)
    a.lsl_l(2, 0)
    a.adda_l_dn(0, 3)
    a.raw(b"\x34\x7c\x00\x27")
    a.jmp_abs(0x4007B7FE)

    a.label("label_limit")
    a.pea_abs(LIST)
    a.raw(b"\x22\x44")
    a.raw(b"\x4e\x91")
    a.raw(b"\x58\x8f")
    a.raw(b"\xd0\xb9")
    a.l(SCROLL)
    a.cmpi_l(5, 0)
    a.ble("label_capped")
    a.moveq(5, 0)
    a.label("label_capped")
    a.jmp_abs(0x4007B8C0)

    a.label("grid_origin")
    a.move_l_abs_dn(SCROLL, 7)
    a.raw(b"\x36\x7c\x00\x28")
    a.jmp_abs(0x4007BA5E)

    a.label("grid_step")
    a.addq_l(1, 7)
    a.raw(b"\x5f\x8b")
    a.move_l_abs_dn(SCROLL, 1)
    a.addq_l(4, 1)
    a.cmpi_l(5, 1)
    a.ble("grid_capped")
    a.moveq(5, 1)
    a.label("grid_capped")
    a.raw(b"\xb2\x87")
    a.beq("grid_done")
    a.jmp_abs(0x4007BA6A)
    a.label("grid_done")
    a.jmp_abs(0x4007BD30)

    # The dashes are shifted one pixel right, so one of them lands on the
    # centre of the row. The 0 and the on-grid cursor share that dash.
    a.label("lane_row")
    a.cmpi_l(1, 7)
    a.bne("lane_stock")
    a.move_l_an_dn(3, 0)
    a.addq_l(1, 0)
    a.movea_l_dn(0, 2)
    a.moveq(0, 6)
    a.moveq(0x29, 5)
    a.label("dash_loop")
    a.pea_w(1)
    a.move_l_an_predec_sp(2)
    a.move_l_dn_predec_sp(5)
    a.move_l_an_predec_sp(2)
    a.move_l_rr(5, 0)
    a.subq_l(1, 0)
    a.move_l_dn_predec_sp(0)
    a.move_l_an_predec_sp(4)
    a.jsr_abs(LINE)
    a.lea_sp(0x18)
    a.addq_l(3, 5)
    a.addq_l(1, 6)
    a.cmpi_l(16, 6)
    a.blt("dash_loop")
    a.pea_lbl("zero")
    a.pea_w(0xFFFF)
    a.move_l_an_dn(3, 0)
    a.subq_l(1, 0)
    a.move_l_dn_predec_sp(0)
    a.pea_w(0x3D)
    a.move_l_an_predec_sp(4)
    a.pea_abs(FONT)
    a.jsr_abs(ROWTEXT)
    a.lea_sp(0x18)
    a.jsr_lbl("current")
    a.addi_l(0x3E, 0)
    a.cmpi_l(0x56, 0)
    a.blt("cursor_lo")
    a.moveq(0x55, 0)
    a.label("cursor_lo")
    a.cmpi_l(0x28, 0)
    a.bge("cursor_x")
    a.moveq(0x28, 0)
    a.label("cursor_x")
    a.move_l_rr(0, 5)
    a.move_l_an_dn(3, 0)
    a.subq_l(2, 0)
    a.move_l_an_dn(3, 1)
    a.addq_l(3, 1)
    a.pea_w(1)
    a.move_l_dn_predec_sp(1)
    a.move_l_dn_predec_sp(5)
    a.move_l_dn_predec_sp(0)
    a.move_l_dn_predec_sp(5)
    a.move_l_an_predec_sp(4)
    a.jsr_abs(LINE)
    a.lea_sp(0x18)
    a.jmp_abs(0x4007BCFC)
    a.label("lane_stock")
    a.movea_l_abs(BANKPTR, 0)
    a.jmp_abs(0x4007BC48)

    # d1 is the signed offset, a0 the destination. Appends the stock text.
    a.label("write_metric")
    a.tst_l(1)
    a.beq("metric_grid")
    a.bmi("metric_neg")
    a.move_b_imm_post(ord("+"), 0)
    a.bra("metric_copy")
    a.label("metric_neg")
    a.move_b_imm_post(ord("-"), 0)
    a.neg_l(1)
    a.label("metric_copy")
    a.lea_abs(FRAC, 1)
    a.move_l_rr(1, 0)
    a.lsl_l(2, 0)
    a.adda_l_dn(0, 1)
    a.movea_l_ind(1)
    a.bra("metric_chars")
    a.label("metric_grid")
    a.lea_abs(ONGRID, 1)
    a.label("metric_chars")
    a.move_b_post_dn(1, 0)
    a.move_b_dn_post(0, 0)
    a.bne("metric_chars")
    a.rts()

    code_end = a.pc
    a.label("micro")
    a.raw(b"MICRO T\x00")
    if a.pc & 1:
        a.raw(b"\x00")
    a.label("strbuf")
    a.raw(b"\x00" * 16)
    a.label("zero")
    a.raw(b"0\x00")
    if a.pc & 1:
        a.raw(b"\x00")
    a.label("names")
    a.l(0x400B4AC0)
    a.abs_long("micro")
    a.l(0x400B4AF9)
    a.l(0x400B4B3D)
    a.l(0x400B73BF)
    a.resolve()
    insns = a.disassemble(code_end)
    return a, code_end, insns


def bit_tests():
    def apply_micro(word, delta):
        raw = (word >> 7) & 0x3F
        val = raw - 64 if raw & 0x20 else raw
        val = max(-23, min(23, val + delta))
        return (word & 0xFFFFE07F) | ((val & 0x3F) << 7) & 0xFFFF

    def row(old, delta):
        new = max(-23, min(23, old + delta))
        return new, new - old

    assert apply_micro(0, 5) == (5 << 7)
    assert apply_micro(10 << 7, 5) == (15 << 7)
    assert apply_micro(20 << 7, 5) == (23 << 7)
    assert apply_micro(23 << 7, 5) == (23 << 7)
    assert apply_micro(10 << 7, -3) == (7 << 7)
    assert apply_micro(5 << 7, -5) == 0
    neg = ((-23) & 0x3F) << 7
    assert apply_micro(neg, -5) == neg
    assert apply_micro(0xE07F, 5) & 0x7F == 0x7F
    assert (apply_micro(0xE07F, 5) >> 13) & 7 == 7
    assert apply_micro(0xFFFF, 0) == 0xFFFF
    assert row(20, 5) == (23, 3)
    assert row(23, 1) == (23, 0)
    assert row(-20, -5) == (-23, -3)
    assert row(4, -4) == (0, -4)


def write_listing(insns, labels):
    names = {addr: name for name, addr in labels.items()}
    lines = []
    for ins in insns:
        if ins.address in names:
            lines.append(names[ins.address] + ":")
        lines.append(f"{ins.address:08x}: {ins.bytes.hex():20} {ins.mnemonic} {ins.op_str}")
    text = "\n".join(lines) + "\n"
    with open(LISTING_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    required = [
        "move.l $8(a7), d2",
        "lea.l $400b2528.l, a1",
        "jmp $4007b780.l",
        "jmp $4007bd64.l",
        "jmp $4007b874.l",
        "jmp $4007b9ae.l",
        "jmp $4007b9e0.l",
        "jsr $4002d640.l",
        "move.l d0, $460d1018.l",
        "jsr $40027e00.l",
        "jsr $4009da20.l",
    ]
    for item in required:
        if item not in text:
            raise SystemExit("listing missing " + item)
    return text


def file_off(addr):
    return addr - BASE


def patch(asm):
    main = bytearray(open(MAIN_PATH, "rb").read())
    if len(main) != 1112560:
        raise SystemExit(f"main OS length {len(main)}")
    digest = hashlib.sha256(main).hexdigest()
    if not digest.startswith("164f31224bf61181"):
        raise SystemExit("extract is not stock 1.40C main OS")
    cave_off = file_off(ORG)
    if any(main[cave_off : cave_off + len(asm.buf)]):
        raise SystemExit("cave is not empty")
    main[cave_off : cave_off + len(asm.buf)] = asm.buf
    changed = [(cave_off, len(asm.buf))]

    def put(addr, old, new):
        if len(old) != len(new):
            raise SystemExit(f"{addr:#x} replacement size")
        off = file_off(addr)
        got = bytes(main[off : off + len(old)])
        if got != old:
            raise SystemExit(f"{addr:#x} is {got.hex()} not {old.hex()}")
        main[off : off + len(new)] = new
        changed.append((off, len(new)))

    # Five names: TRIGS, MICRO T, SLIDE, SWING, REC.TRG. The live table at
    # 0x400b2e66 stays put; only this menu's lea uses the new one.
    put(0x4007B7F4, bytes.fromhex("400b2e66"), struct.pack(">I", asm.labels["names"]))
    # Five rows in the list, four on screen, so the fifth scrolls into the frame.
    put(0x4007C07A, bytes.fromhex("48780004"), bytes.fromhex("48780005"))
    put(
        0x4007B7F8,
        bytes.fromhex("4282347c0027"),
        b"\x4e\xf9" + struct.pack(">I", asm.labels["label_origin"]),
    )
    put(
        0x4007B8B4,
        bytes.fromhex("4879460e73dc22444e91588f"),
        b"\x4e\xf9" + struct.pack(">I", asm.labels["label_limit"]) + b"\x4e\x71" * 3,
    )
    put(
        0x4007BA58,
        bytes.fromhex("4287367c0028"),
        b"\x4e\xf9" + struct.pack(">I", asm.labels["grid_origin"]),
    )
    put(
        0x4007BC42,
        bytes.fromhex("207946c82456"),
        b"\x4e\xf9" + struct.pack(">I", asm.labels["lane_row"]),
    )
    put(
        0x4007BD24,
        bytes.fromhex("52875f8b7204b2876600fd3c"),
        b"\x4e\xf9" + struct.pack(">I", asm.labels["grid_step"]) + b"\x4e\x71" * 3,
    )
    # MIDI hides SLIDE (2) and REC.TRG (4), in the label draw and the trig grid.
    put(0x4007B824, bytes.fromhex("7001"), bytes.fromhex("7002"))
    put(0x4007B82C, bytes.fromhex("7203"), bytes.fromhex("7204"))
    put(0x4007BA74, bytes.fromhex("7a01"), bytes.fromhex("7a02"))
    put(0x4007BA7C, bytes.fromhex("7003"), bytes.fromhex("7004"))
    # Grid body for the old SLIDE and SWING rows follows the new indices.
    put(0x4007BB62, bytes.fromhex("7001"), bytes.fromhex("7002"))
    put(0x4007BBCE, bytes.fromhex("7002"), bytes.fromhex("7003"))
    # SWING was row 2. Its footer, side widget and LEVEL check move to row 3.
    put(0x4007B8CC, bytes.fromhex("7202"), bytes.fromhex("7203"))
    put(0x4007B9EC, bytes.fromhex("7202"), bytes.fromhex("7203"))
    put(0x4007BD76, bytes.fromhex("7202"), bytes.fromhex("7203"))
    # REC.TRG was row 3. The exit check and the post-grid widget move to row 4.
    put(0x4007B736, bytes.fromhex("7003"), bytes.fromhex("7004"))
    put(0x4007BD36, bytes.fromhex("7403"), bytes.fromhex("7404"))
    # Shared mode store still clamps at 3. These two menu calls allow row 4.
    put(0x4007B4CA, bytes.fromhex("4eb940037da4"), b"\x4e\xb9" + struct.pack(">I", asm.labels["mode4"]))
    put(0x4007B72E, bytes.fromhex("4eb940037da4"), b"\x4e\xb9" + struct.pack(">I", asm.labels["mode4"]))
    # Catch-all and both arrow handlers. A skipped row moves to the neighbour.
    put(0x4007B67C, bytes.fromhex("7001"), bytes.fromhex("7002"))
    put(0x4007B696, bytes.fromhex("7203"), bytes.fromhex("7204"))
    put(0x4007B6A0, bytes.fromhex("48780002"), bytes.fromhex("48780003"))
    put(0x4007BFB8, bytes.fromhex("7001"), bytes.fromhex("7002"))
    put(0x4007BFC2, bytes.fromhex("48780002"), bytes.fromhex("48780003"))
    put(0x4007BFD4, bytes.fromhex("7003"), bytes.fromhex("7004"))
    put(0x4007BFDE, bytes.fromhex("48780002"), bytes.fromhex("48780003"))
    put(0x4007C010, bytes.fromhex("7001"), bytes.fromhex("7002"))
    put(0x4007C02A, bytes.fromhex("7003"), bytes.fromhex("7004"))
    put(0x4007C034, bytes.fromhex("48780002"), bytes.fromhex("48780003"))
    force = b"\x4e\xb9" + struct.pack(">I", asm.labels["force1"]) + b"\x4e\x71" * 5
    block = bytes.fromhex("42a74879460e73dc4eb94007edb0508f")
    put(0x4007B686, block, force)
    put(0x4007C01A, block, force)
    # That one audio machine still skips TRIGS and SLIDE, not the new row.
    put(0x4007B6F2, bytes.fromhex("48780003"), bytes.fromhex("48780004"))
    put(0x4007B704, bytes.fromhex("7401"), bytes.fromhex("7402"))
    put(0x4007B70E, bytes.fromhex("48780003"), bytes.fromhex("48780004"))
    put(
        0x4007B866,
        bytes.fromhex("3a3c0001ba826440"),
        b"\x4e\xf9" + struct.pack(">I", asm.labels["hide_slide_label"]) + b"\x4e\x71",
    )
    put(
        0x4007BABC,
        bytes.fromhex("7001b08764000262"),
        b"\x4e\xf9" + struct.pack(">I", asm.labels["hide_slide_grid"]) + b"\x4e\x71",
    )
    put(0x4007B9A8, bytes.fromhex("4eb940033990"), b"\x4e\xf9" + struct.pack(">I", asm.labels["footer"]))
    put(0x400D01F2, bytes.fromhex("4007bd64"), struct.pack(">I", asm.labels["level"]))
    original = open(MAIN_PATH, "rb").read()
    allowed = set()
    for off, size in changed:
        allowed.update(range(off, off + size))
    for index, (old, new) in enumerate(zip(original, main)):
        if old != new and index not in allowed:
            raise SystemExit(f"unexpected change at {BASE + index:#x}")
    if main[file_off(0x400B2E66) : file_off(0x400B2E66) + 16] != bytes.fromhex("400b4ac0400b4af9400b4b3d400b73bf"):
        raise SystemExit("live label table was modified")
    check_patched_menu(main, asm)
    with open(PATCHED_PATH, "wb") as handle:
        handle.write(main)


def check_patched_menu(main, asm):
    md = Cs(CS_ARCH_M68K, CS_MODE_M68K_040)

    def dis(addr, count):
        code = bytes(main[file_off(addr) : file_off(addr) + count * 8])
        return list(md.disasm(code, addr))[:count]

    lea = dis(0x4007B7F2, 1)[0]
    if lea.mnemonic != "lea.l" or asm.labels["names"] != int(lea.op_str.split("$")[1].split(".")[0], 16):
        raise SystemExit(f"name table lea is {lea.mnemonic} {lea.op_str}")
    for addr, imm in (
        (0x4007C07A, 5),
        (0x4007C07E, 4),
    ):
        ins = dis(addr, 1)[0]
        if ins.mnemonic != "pea.l" or ins.op_str != f"${imm}.w":
            raise SystemExit(f"{addr:#x} is {ins.mnemonic} {ins.op_str}")
    for addr, text in (
        (0x4007B824, "#$2"),
        (0x4007B82C, "#$4"),
        (0x4007BA74, "#$2"),
        (0x4007BA7C, "#$4"),
        (0x4007BD76, "#$3"),
        (0x4007BB62, "#$2"),
        (0x4007BBCE, "#$3"),
    ):
        ins = dis(addr, 1)[0]
        if ins.mnemonic != "moveq" or not ins.op_str.startswith(text):
            raise SystemExit(f"{addr:#x} is {ins.mnemonic} {ins.op_str}")
    push = dis(0x4007B86E, 1)[0]
    if push.mnemonic != "move.l" or "(a3)" not in push.op_str:
        raise SystemExit(f"label push is {push.mnemonic} {push.op_str}")
    for addr in (0x4007B9A8, 0x4007B866, 0x4007BABC, 0x4007B7F8, 0x4007B8B4, 0x4007BA58, 0x4007BC42, 0x4007BD24):
        ins = dis(addr, 1)[0]
        if ins.mnemonic != "jmp" or ins.size != 6:
            raise SystemExit(f"{addr:#x} is {ins.mnemonic} size {ins.size}")
    level = int.from_bytes(main[file_off(0x400D01F2) : file_off(0x400D01F2) + 4], "big")
    if level != asm.labels["level"]:
        raise SystemExit(f"level pointer {level:#x}")


def pack():
    script = os.path.join(os.environ["TEMP"], "pack-micro-t.mjs")
    with open(script, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            """
import { readFileSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
const elek = pathToFileURL(process.argv[2]).href
const { decodeFirmware, encodeFirmware } = await import(elek)
const stock = decodeFirmware(readFileSync(process.argv[3]))
const orig = readFileSync(process.argv[4])
const patched = readFileSync(process.argv[5])
if (stock.mainOs.length !== orig.length) throw new Error('stock length')
for (let i = 0; i < orig.length; i++) {
  if (stock.mainOs[i] !== orig[i]) throw new Error('stock main mismatch at ' + i)
}
const out = encodeFirmware(stock, patched, process.argv[7])
writeFileSync(process.argv[6], out)
const back = decodeFirmware(out)
const version = new TextDecoder().decode(back.header.subarray(8, 18))
for (let i = 0; i < patched.length; i++) {
  if (back.mainOs[i] !== patched[i]) throw new Error('round trip at ' + i)
}
console.log('version=' + JSON.stringify(version))
console.log('bytes=' + out.length)
""".strip()
        )
    os.makedirs(os.path.dirname(OUT_BIN), exist_ok=True)
    elek = os.path.join(ROOT, "src", "engine", "elek.ts")
    result = subprocess.run(
        ["node", "--experimental-strip-types", script, elek, STOCK_BIN, MAIN_PATH, PATCHED_PATH, OUT_BIN, VERSION],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stdout + "\n" + result.stderr)
    print(result.stdout.strip())
    digest = hashlib.sha256(open(OUT_BIN, "rb").read()).hexdigest()
    print("sha256=" + digest)
    print("path=" + OUT_BIN)
    version = result.stdout.split("version=", 1)[1].splitlines()[0]
    padded = f'"{VERSION:<10}"'
    if version != padded:
        raise SystemExit("unexpected version field " + version)


def verify_fractions():
    import math

    main = open(MAIN_PATH, "rb").read()

    def cstr(addr):
        off = addr - BASE
        end = main.index(b"\x00", off)
        return main[off:end].decode()

    if cstr(ONGRID) != "ON GRID":
        raise SystemExit("stock zero label changed")
    for n in range(24):
        ptr = int.from_bytes(main[FRAC - BASE + 4 * n : FRAC - BASE + 4 * n + 4], "big")
        got = cstr(ptr)
        if n == 0:
            expect = "ON GRID"
        else:
            factor = math.gcd(n, 384)
            expect = f"{n // factor}/{384 // factor}"
        if got != expect:
            raise SystemExit(f"fraction {n} is {got!r}, expected {expect!r}")


def main():
    preflight()
    bit_tests()
    verify_fractions()
    asm, code_end, insns = program()
    if asm.buf[asm.labels["micro"] - ORG : asm.labels["micro"] - ORG + 8] != b"MICRO T\x00":
        raise SystemExit("label string missing")
    write_listing(insns, asm.labels)
    if ORG + len(asm.buf) > ORG_LIMIT:
        raise SystemExit(f"stub ends at {ORG + len(asm.buf):#x}, past {ORG_LIMIT:#x}")
    print(f"cave {ORG:#x} size {code_end - ORG} code, {len(asm.buf)} with strings")
    patch(asm)
    pack()


if __name__ == "__main__":
    sys.exit(main())
