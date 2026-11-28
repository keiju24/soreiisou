# 小学校の校庭マップ（風情小学校）を Blender で作り、models/schoolyard.glb と 当たり判定 models/schoolyard.col.json を書き出す。
#   使い方：python tools/blender/schoolyard_build.py models/schoolyard.glb   （pip の bpy でも、Blender の Python でもよい）
#
# ・校庭は 70m × 50m（x −35〜35、z −25〜25。奥 z −25 がわに校舎）。まわりはフェンスと閉じた校門で、外には出られない
# ・校舎（3階建て）と体育館は 花だん・植えこみの向こう。中には入れない（当たり判定の「さかい」で止まる）
# ・校庭：トラック（白線・4レーン）、サッカーのライン、朝礼台、国旗のポール、手洗い場、二宮金次郎の像、
#   鉄棒・のぼり棒・雲梯・ジャングルジム・ブランコ・砂場・すべり台・タイヤとび・百葉箱・ベンチ・体育倉庫・バックネット・サッカーゴール・桜の木
# ・外：道路・歩道・電柱・家（見えるだけ）
# 当たり判定（col.json）：box＝[x0, x1, z0, z1, 高さ, メモ]、circle＝[x, z, 半径, 高さ, メモ]。bounds＝歩ける範囲
import sys, os, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fwb_common import *
import fwb_common as K
out = sys.argv[-1] if sys.argv[-1].endswith('.glb') else os.path.join(ROOT, 'models', 'schoolyard.glb')
rnd = random.Random(3)
reset()

X0, X1, Z0, Z1 = -35.0, 35.0, -25.0, 25.0          # 校庭
TR = dict(cx=0.0, cz=3.0, L=12.0, R=11.0, lane=1.1, n=4)   # トラック：直線の半分 L、内側の半径 R

# =====================================================================
#  テクスチャ
# =====================================================================
def ground_img():
    W, H = 2048, 1463; sx, sz = W / (X1 - X0), H / (Z1 - Z0)
    px = lambda x: (x - X0) * sx; pz = lambda z: (z - Z0) * sz
    n = noise(W, H, 96, 1) * .5 + noise(W, H, 24, 2) * .3 + noise(W, H, 4, 3) * .2
    im = tint((184, 148, 108), n, .28); d = ImageDraw.Draw(im)
    r = np.random.default_rng(4)
    for _ in range(9000):                               # 小石
        x, y = r.random() * W, r.random() * H; s = r.random() * 1.6 + .4; c = int(120 + r.random() * 90)
        d.ellipse([x - s, y - s, x + s, y + s], fill=(c, int(c * .86), int(c * .7)))
    # トラックの いちばん内がわのレーンは すりへって 少し暗い
    cx, cz, L, R, lw = TR['cx'], TR['cz'], TR['L'], TR['R'], TR['lane']
    def oval(rr, col, w):
        d.arc([px(cx - L - rr), pz(cz - rr), px(cx - L + rr), pz(cz + rr)], 90, 270, fill=col, width=w)
        d.arc([px(cx + L - rr), pz(cz - rr), px(cx + L + rr), pz(cz + rr)], 270, 90, fill=col, width=w)
        d.line([(px(cx - L), pz(cz - rr)), (px(cx + L), pz(cz - rr))], fill=col, width=w)
        d.line([(px(cx - L), pz(cz + rr)), (px(cx + L), pz(cz + rr))], fill=col, width=w)
    oval(R + lw * .5, (160, 124, 88), int(lw * sx * .8))
    for k in range(TR['n'] + 1): oval(R + k * lw, (246, 244, 236), 4)
    # スタート／ゴールの線（手前の直線）と レーンの番号のしるし
    d.line([(px(cx), pz(cz + R)), (px(cx), pz(cz + R + lw * TR['n']))], fill=(246, 244, 236), width=5)
    for k in range(TR['n']): d.text((px(cx) - 22, pz(cz + R + lw * (k + .5))), str(k + 1), font=F(26), fill=(246, 244, 236), anchor='mm')
    # サッカーのライン（トラックの内がわ）
    d.line([(px(0), pz(cz - R + 1)), (px(0), pz(cz + R - 1))], fill=(246, 244, 236), width=3)
    d.ellipse([px(-3.5), pz(cz - 3.5), px(3.5), pz(cz + 3.5)], outline=(246, 244, 236), width=3)
    for s in (-1, 1):
        x = s * (L + R - 1.0); d.rectangle(sorted([px(x), px(x - s * 5)]) and [min(px(x), px(x - s * 5)), pz(cz - 6), max(px(x), px(x - s * 5)), pz(cz + 6)], outline=(246, 244, 236), width=3)
    # 朝礼台の前の 整列の しるし
    for k in range(-6, 7): d.line([(px(k * 1.6), pz(-14.6)), (px(k * 1.6), pz(-14.2))], fill=(246, 244, 236), width=3)
    return im
def grass_img():
    W = H = 512; n = noise(W, H, 32, 11) * .6 + noise(W, H, 4, 12) * .4
    return tint((96, 140, 70), n, .4)
def asphalt_img():
    W = H = 512; n = noise(W, H, 8, 21) * .5 + noise(W, H, 2, 22) * .5
    return tint((92, 94, 98), n, .35)
def wall_img(base):
    def f():
        W = H = 256; n = noise(W, H, 32, 31) * .6 + noise(W, H, 4, 32) * .4
        return tint(base, n, .1)
    return f
def tile_img():
    W = H = 256; im = Image.new('RGB', (W, H), (176, 170, 160)); d = ImageDraw.Draw(im)
    for i in range(4):
        for j in range(4): d.rectangle([i * 64 + 2, j * 64 + 2, i * 64 + 61, j * 64 + 61], fill=(206, 200, 190) if (i + j) % 2 else (196, 190, 180))
    return im
def sand_img():
    W = H = 256; n = noise(W, H, 16, 41) * .5 + noise(W, H, 2, 42) * .5
    return tint((222, 200, 160), n, .3)

G = dict(
    ground=tmat('ground', ground_img, .95, jpeg=True), grass=tmat('grass', grass_img, .95), asphalt=tmat('asphalt', asphalt_img, .9),
    wall=tmat('school_wall', wall_img((236, 231, 220)), .85), wall2=tmat('gym_wall', wall_img((214, 206, 192)), .85), tile=tmat('tile', tile_img, .8),
    sand=tmat('sand', sand_img, .95),
)
M = dict(
    white=C('#f2f0ea', .6), line=C('#f6f4ec', .8), conc=C('#b9b6ae', .85), conc2=C('#9c9a94', .85), glass=C('#577a96', .12, .2),
    glass2=C('#7fa2bd', .1, .2), frame=C('#c9ccc8', .35, .6), green=C('#2f7d4a', .5, .3), green2=C('#3f8f5a', .6), fence=C('#2f6b45', .45, .4),
    red=C('#c0392b', .5), yellow=C('#e8c030', .5), blue=C('#2f6fb8', .5), orange=C('#e0782f', .5), steel=C('#9aa1a3', .35, .7),
    dark=C('#2c2d2a', .6), rubber=C('#232325', .9), wood=C('#9a7148', .7), wood2=C('#6b4a2c', .7), bark=C('#5a4030', .9),
    sakura=C('#f4b8c8', .8), sakura2=C('#f8cfdb', .8), leaf=C('#4f8a3d', .8), leaf2=C('#6aa64c', .8), hedge=C('#3e7a3a', .9),
    roofg=C('#4c7a5a', .6, .2), clock=C('#fbfaf5', .5), bronze=C('#7a6a4a', .45, .6), stone=C('#8f8c86', .8), pink=C('#e86a8a', .7),
    flower_r=C('#e04848', .7), flower_y=C('#f2cf3a', .7), flower_w=C('#f4f2ea', .7), soil=C('#5a4030', .95), net=C('#e8e6df', .6),
    roof_house=C('#4a5a6a', .6), roof_house2=C('#8a4a3a', .6), house=C('#e8e0d0', .8), house2=C('#d8d0c0', .8),
)

# =====================================================================
#  地面・外まわり
# =====================================================================
CUR[0] = 'MAP'
plane(G['ground'], 0, 0, 0, X1 - X0, Z1 - Z0, '+y', 'ground')
# 外の芝生（校庭のまわり）と道路・歩道
for (a, b, c, d_) in [(-90, 90, Z1, 70), (-90, 90, -80, Z0), (-90, X0, Z0, Z1), (X1, 90, Z0, Z1)]:
    quad(G['grass'], [(a, -.02, d_), (b, -.02, d_), (b, -.02, c), (a, -.02, c)], [(a / 6, d_ / 6), (b / 6, d_ / 6), (b / 6, c / 6), (a / 6, c / 6)], 'grass')
box(C('#c9c4b8', .85), -90, 90, -.02, .08, Z1 + .6, Z1 + 3.6, tile=2)               # 歩道
quad(G['asphalt'], [(-90, .0, Z1 + 11), (90, .0, Z1 + 11), (90, .0, Z1 + 3.6), (-90, .0, Z1 + 3.6)], [(-15, 2), (15, 2), (15, 0), (-15, 0)], 'road')
for x in range(-88, 90, 6): box(M['line'], x, x + 3, .005, .012, Z1 + 7.2, Z1 + 7.4)
for x in (-40, -12, 16, 44):
    cyl(C('#a8a6a0', .8), x, 4.5, Z1 + 3.2, .16, 9, 'y', 12); box(C('#a8a6a0', .8), x - 1.2, x + 1.2, 8.2, 8.35, Z1 + 3.1, Z1 + 3.3)
for (x0, x1) in [(-40, -12), (-12, 16), (16, 44)]:
    for dy in (7.9, 8.3): bar(C('#222222', .9), (x0, dy, Z1 + 3.2), (x1, dy, Z1 + 3.2), .02, 6)
# 外の家（見えるだけ）
def house(x, z, w, d, h, roof, wall):
    box(wall, x - w / 2, x + w / 2, 0, h, z - d / 2, z + d / 2)
    from mathutils import Vector as V
    for s in (-1, 1):
        quad(roof, [(x - w / 2 - .4, h, z + s * (d / 2 + .4)), (x + w / 2 + .4, h, z + s * (d / 2 + .4)), (x + w / 2 + .4, h + d * .35, z), (x - w / 2 - .4, h + d * .35, z)][::s], name='roof')
    for s in (-1, 1): quad(wall, [(x + s * w / 2, h, z - d / 2), (x + s * w / 2, h, z + d / 2), (x + s * w / 2, h + d * .35, z)][::s], ((0, 0), (1, 0), (.5, 1)), 'gable')
    for k in range(int(w // 2.4)): box(M['glass'], x - w / 2 + 1 + k * 2.4, x - w / 2 + 2.2 + k * 2.4, h * .55, h * .55 + 1.1, z + d / 2, z + d / 2 + .05)
for i, (x, z) in enumerate([(-58, 40), (-46, 41), (-30, 40), (-14, 41), (6, 40), (24, 41), (40, 40), (56, 41), (-52, 0), (-50, 14), (-53, -16), (50, -2), (52, 14), (49, -18)]):
    house(x, z, 8 + rnd.random() * 3, 7, 5.5 + rnd.random() * 2, M['roof_house'] if i % 2 else M['roof_house2'], M['house'] if i % 3 else M['house2'])

# =====================================================================
#  フェンス（緑の金あみ）・校門・植えこみ
# =====================================================================
def fence(a, b, h=2.6, step=.22):
    L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(L / 2.5))
    for i in range(n + 1):
        t = i / n; x = a[0] + (b[0] - a[0]) * t; z = a[1] + (b[1] - a[1]) * t
        cyl(M['fence'], x, h / 2, z, .045, h, 'y', 8)
    for yy in (.08, h * .5, h - .03): bar(M['fence'], (a[0], yy, a[1]), (b[0], yy, b[1]), .025, 6)
    k = int(L / step)
    ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    for i in range(k + 1):               # たての細い線（あみの目）
        x = a[0] + ux * i * step; z = a[1] + uz * i * step
        box(M['fence'], x - .008, x + .008, .08, h - .03, z - .008, z + .008)
    for j in range(1, int(h / .3)):      # よこの細い線
        yy = j * .3; box(M['fence'], min(a[0], b[0]) - .008, max(a[0], b[0]) + .008, yy - .008, yy + .008, min(a[1], b[1]) - .008, max(a[1], b[1]) + .008)
fence((X0, Z0), (X0, Z1)); fence((X1, Z0), (X1, Z1))
fence((X0, Z1), (-3.2, Z1)); fence((3.2, Z1), (X1, Z1))
colbox(X0 - 3, X0 + .4, Z0 - 3, Z1 + 3, 3, 'フェンス（左）'); colbox(X1 - .4, X1 + 3, Z0 - 3, Z1 + 3, 3, 'フェンス（右）')
colbox(X0 - 3, X1 + 3, Z1 - .4, Z1 + 3, 3, 'フェンス・校門（手前）')
# 校門：門柱（学校の名前）と 閉じた引き戸
for s in (-1, 1):
    box(C('#c8c2b4', .8), s * 3.2 - .45, s * 3.2 + .45, 0, 2.3, Z1 - .45, Z1 + .45, bevel=.03)
    box(C('#a9a396', .8), s * 3.2 - .55, s * 3.2 + .55, 2.3, 2.45, Z1 - .55, Z1 + .55)
    ball(C('#f2efe6', .5, 0, .5), s * 3.2, 2.62, Z1, .2, .18, .2)
sign('風情小学校', -3.2, 1.45, Z1 + .46, .5, 1.6, '+z', bg='#f4f1e8', fg='#1d1b19', border='#6b5a3a')
sign('風情小学校', -3.2, 1.45, Z1 - .46, .5, 1.6, '-z', bg='#f4f1e8', fg='#1d1b19', border='#6b5a3a')
for k in range(14):
    x = -2.75 + k * .42; box(M['steel'], x - .03, x + .03, .12, 1.6, Z1 - .04, Z1 + .04)
for yy in (.12, .85, 1.6): box(M['steel'], -2.75, 2.75, yy - .04, yy + .04, Z1 - .06, Z1 + .06)
for x in (-2.4, 2.4): cyl(M['rubber'], x, .1, Z1, .08, .06, 'x', 10)
box(M['steel'], -2.8, 2.8, 0, .02, Z1 - .1, Z1 + .1)
# 奥：花だんと 植えこみ（ここが 校舎がわの さかい）。昇降口の前（EX ± 3.8）は あけて タイルをしき、くさりで とおせんぼ
EX = -8.0      # 昇降口の まん中
GA, GB = EX - 3.8, EX + 3.8
box(C('#c9c4b8', .85), X0, X1, 0, .12, Z0 - 2.2, Z0 - 1.0, tile=2)                 # 校舎の前の通路
for (a, b) in [(X0, GA), (GB, X1)]:
    box(M['conc2'], a, b, 0, .35, Z0 - .9, Z0 - .75); box(M['conc2'], a, b, 0, .35, Z0 + .05, Z0 + .2)
    box(M['soil'], a, b, 0, .3, Z0 - .75, Z0 + .05)
    for x in np.arange(a + .6, b - .4, .55):
        c = [M['flower_r'], M['flower_y'], M['flower_w'], M['pink']][int((x * 7) % 4)]
        ball(M['leaf2'], float(x), .42, Z0 - .35 + (rnd.random() - .5) * .3, .22, .16, .2, 8)
        ball(c, float(x) + .05, .55, Z0 - .35 + (rnd.random() - .5) * .3, .09, .07, .09, 6)
    for x in np.arange(a + 1, b - .6, 2.2): ball(M['hedge'], float(x), .55, Z0 - 1.6, 1.0, .55, .45, 10)
box(G['tile'], GA, GB, 0, .03, Z0 - 2.2, Z0 + .2, tile=1.2)                          # 昇降口の前のタイル
for x in (GA + .15, GB - .15):
    cyl(M['white'], x, .4, Z0 + .1, .1, .8, 'y', 12); ball(M['white'], x, .82, Z0 + .1, .1, .06, .1, 10)
k = 12
for i in range(k):                                                                     # たれた くさり
    t0, t1 = i / k, (i + 1) / k
    xa, xb = GA + .15 + (GB - GA - .3) * t0, GA + .15 + (GB - GA - .3) * t1
    ya, yb = .7 - .25 * math.sin(math.pi * t0), .7 - .25 * math.sin(math.pi * t1)
    bar(M['red'] if i % 2 else M['white'], (xa, ya, Z0 + .1), (xb, yb, Z0 + .1), .025, 6)
colbox(X0 - 3, X1 + 3, Z0 - 3, Z0 + .25, 3, '花だん・校舎がわ')

# =====================================================================
#  校舎（3階建て）・体育館　…中には入れない
# =====================================================================
BX0, BX1, BZ = -34.0, 18.0, -27.0     # 校舎の前の面
FLH = 4.0
box(G['wall'], BX0, BX1, 0, FLH * 3 + .6, BZ - 9, BZ, tile=4, name='school')
for k in range(1, 4):   # 階の帯（ひさし）
    y = k * FLH; box(M['conc'], BX0 - .1, BX1 + .1, y - .1, y + .12, BZ - .1, BZ + .55)
box(M['conc'], BX0 - .15, BX1 + .15, FLH * 3 + .4, FLH * 3 + .9, BZ - 9.15, BZ + .15)                # 屋上のふち
for x in np.arange(BX0 + .2, BX1, 2.0): bar(M['fence'], (float(x), FLH * 3 + .9, BZ - .05), (float(x), FLH * 3 + 2.0, BZ - .05), .025, 6)
bar(M['fence'], (BX0 + .2, FLH * 3 + 2.0, BZ - .05), (BX1 - .2, FLH * 3 + 2.0, BZ - .05), .03, 6)
# 窓（各階）。ところどころカーテン
for fl in range(3):
    y0 = fl * FLH + 1.0; y1 = y0 + 2.1
    x = BX0 + 1.2
    while x + 2.6 < BX1 - .8:
        if fl == 0 and abs(x + 1.3 - EX) < 3.5: x += 3.2; continue
        box(M['frame'], x - .06, x + 2.66, y0 - .06, y1 + .06, BZ, BZ + .06)
        box(M['glass'] if rnd.random() < .7 else M['glass2'], x, x + 2.6, y0, y1, BZ + .06, BZ + .08)
        box(M['frame'], x + 1.27, x + 1.33, y0, y1, BZ + .08, BZ + .1); box(M['frame'], x, x + 2.6, y0 + 1.3, y0 + 1.36, BZ + .08, BZ + .1)
        if rnd.random() < .35: box(C('#f2e8c8', .9), x + .1, x + .9, y0 + .1, y1 - .1, BZ + .065, BZ + .07)
        box(M['conc'], x - .1, x + 2.7, y0 - .14, y0 - .06, BZ, BZ + .18)        # 窓台
        x += 3.2
# 昇降口：ひさし・ガラスのとびら・階段
box(M['conc'], EX - 3.4, EX + 3.4, 3.0, 3.3, BZ, BZ + 2.4); box(M['conc'], EX - 3.4, EX + 3.4, 3.3, 3.5, BZ + 2.2, BZ + 2.4)
for s in (-1, 1): cyl(M['white'], EX + s * 3.1, 1.5, BZ + 2.1, .14, 3.0, 'y', 12)
for k in range(4):
    x = EX - 2.8 + k * 1.4; box(M['frame'], x, x + 1.4, 0.2, 2.8, BZ, BZ + .06); box(M['glass2'], x + .08, x + 1.32, .3, 2.7, BZ + .06, BZ + .08)
    box(M['steel'], x + .64, x + .76, 1.1, 1.5, BZ + .08, BZ + .12)
for k in range(2): box(M['conc2'], EX - 3.4, EX + 3.4, 0, .1 + k * .1, BZ + 1.2 - k * .6, BZ + 2.4 - k * .6)
sign('昇降口', EX, 3.15, BZ + 2.42, 2.2, .5, '+z', bg='#f4f1e8', fg='#1d1b19', border='#6b5a3a')
# 時計と校章・学校の名前
cx, cy = EX, FLH * 3 - .2
cyl(M['conc'], cx, cy + 1.6, BZ + .1, 1.3, .3, 'z', 32); cyl(M['clock'], cx, cy + 1.6, BZ + .3, 1.1, .1, 'z', 32)
for k in range(12):
    a = k / 12 * math.tau; box(M['dark'], cx + math.sin(a) * .9 - .04, cx + math.sin(a) * .9 + .04, cy + 1.6 + math.cos(a) * .9 - .1, cy + 1.6 + math.cos(a) * .9 + .1, BZ + .36, BZ + .38)
bar(M['dark'], (cx, cy + 1.6, BZ + .4), (cx + .1, cy + 2.3, BZ + .4), .045, 6); bar(M['dark'], (cx, cy + 1.6, BZ + .41), (cx + .5, cy + 1.3, BZ + .41), .045, 6)
sign('風情小学校', -24, FLH * 3 + .65, BZ + .16, 6.0, .9, '+z', bg='#f4f1e8', fg='#1d1b19', border='#f4f1e8', frame=False)
# 屋上の塔屋（階段室）と給水タンク
box(G['wall'], -2, 4, FLH * 3 + .6, FLH * 3 + 3.6, BZ - 7, BZ - 3, tile=4); box(M['conc'], -2.2, 4.2, FLH * 3 + 3.6, FLH * 3 + 3.9, BZ - 7.2, BZ - 2.8)
cyl(C('#c9d1d4', .5, .2), 1, FLH * 3 + 4.9, BZ - 5, 1.0, 2.0, 'y', 24)
# 体育館（右の奥）：かまぼこ屋根
GX0, GX1 = 21.0, 35.0
box(G['wall2'], GX0, GX1, 0, 7.5, BZ - 16, BZ, tile=4, name='gym')
for k in range(16):
    a0, a1 = math.pi * k / 16, math.pi * (k + 1) / 16
    pts = lambda a: ((GX0 + GX1) / 2 - math.cos(a) * 7.4, 7.5 + math.sin(a) * 2.6)
    (xa, ya), (xb, yb) = pts(a0), pts(a1)
    quad(M['roofg'], [(xa, ya, BZ + .3), (xb, yb, BZ + .3), (xb, yb, BZ - 16.3), (xa, ya, BZ - 16.3)][::-1], name='gymroof')
    quad(G['wall2'], [(xa, ya, BZ + .01), (xb, yb, BZ + .01), ((GX0 + GX1) / 2, 7.5, BZ + .01)], ((0, 0), (1, 0), (.5, 1)), 'gymgable')
for k in range(6): x = GX0 + 1 + k * 2.2; box(M['glass'], x, x + 1.6, 5.2, 6.6, BZ, BZ + .06); box(M['frame'], x - .05, x + 1.65, 5.15, 5.22, BZ, BZ + .1)
box(M['frame'], 26.5, 29.5, 0, 3.2, BZ, BZ + .06); box(M['glass2'], 26.6, 29.4, .1, 3.1, BZ + .06, BZ + .08)
sign('体育館', 28, 4.2, BZ + .1, 2.6, .7, '+z', bg='#f4f1e8', fg='#1d1b19', border='#6b5a3a')
# 校舎と体育館のあいだの 渡りろうか
box(M['conc'], BX1, GX0, 3.0, 3.4, BZ - 4, BZ - 1.5); box(M['wall'] if False else G['wall'], BX1, GX0, 3.4, 4.2, BZ - 4, BZ - 1.5, tile=4)
for x in (BX1 + .3, GX0 - .3):
    for z in (BZ - 3.7, BZ - 1.8): cyl(M['white'], x, 1.5, z, .12, 3.0, 'y', 10)

# =====================================================================
#  校庭の物
# =====================================================================
# ---- 朝礼台（手すり・後ろの階段）と国旗のポール ----
def stage(x, z):
    box(M['conc'], x - 1.8, x + 1.8, 0, 1.2, z - 1.2, z + 1.2, bevel=.04)
    box(C('#2f6fb8', .7), x - 1.75, x + 1.75, 1.2, 1.24, z - 1.15, z + 1.15)
    for (a, b) in [((x - 1.7, z - 1.1), (x + 1.7, z - 1.1)), ((x - 1.7, z - 1.1), (x - 1.7, z + 1.1)), ((x + 1.7, z - 1.1), (x + 1.7, z + 1.1))]:
        bar(M['steel'], (a[0], 2.05, a[1]), (b[0], 2.05, b[1]), .035)
        for (xx, zz) in (a, b): bar(M['steel'], (xx, 1.24, zz), (xx, 2.05, zz), .03)
    for k in range(4): box(M['conc'], x - .8, x + .8, 0, .3 * (k + 1), z - 1.2 - (4 - k) * .35, z - 1.2 - (3 - k) * .35)
    cyl(M['steel'], x + 1.1, 1.24 + .5, z + .6, .03, 1.0, 'y', 8); ball(M['dark'], x + 1.1, 2.3, z + .6, .07, .1, .07)   # マイク
    colbox(x - 1.85, x + 1.85, z - 2.65, z + 1.25, 1.3, '朝礼台')
stage(0, -18.5)
for k, (x, c) in enumerate([(5.5, '#f4f1ea'), (6.6, '#e04848'), (7.7, '#2f6fb8')]):
    cyl(M['conc'], x, .15, -22.5, .35, .3, 'y', 12); bar(M['steel'], (x, 0, -22.5), (x, 9.0 - k * .4, -22.5), .05, 10); ball(M['yellow'], x, 9.05 - k * .4, -22.5, .1, .1, .1, 8)
    box(C(c, .8), x + .05, x + 1.0, 7.4 - k * .4, 8.0 - k * .4, -22.52, -22.48)
    colcircle(x, -22.5, .4, 9, 'ポール')
# ---- 手洗い場 ----
def sink(x, z):
    box(M['conc'], x - 2.5, x + 2.5, 0, .75, z - .5, z + .5, bevel=.03); box(M['conc2'], x - 2.4, x + 2.4, .6, .76, z - .4, z + .4)
    box(M['conc'], x - 2.5, x + 2.5, .75, 1.25, z - .5, z - .4)
    for k in range(6):
        xx = x - 2.0 + k * .8; bar(M['steel'], (xx, 1.1, z - .4), (xx, 1.1, z - .15), .02, 6); bar(M['steel'], (xx, 1.1, z - .15), (xx, .98, z - .15), .02, 6)
        cyl(M['steel'], xx, 1.17, z - .3, .04, .06, 'y', 8)
    colbox(x - 2.55, x + 2.55, z - .55, z + .55, 1.2, '手洗い場')
sink(-14, -22.2); sink(14, -22.2)
# ---- 二宮金次郎の像 ----
def statue(x, z):
    box(M['stone'], x - .7, x + .7, 0, 1.4, z - .7, z + .7, bevel=.04); box(M['stone'], x - .8, x + .8, 1.4, 1.55, z - .8, z + .8)
    b = M['bronze']; y = 1.55
    cyl(b, x - .12, y + .35, z, .09, .7); cyl(b, x + .12, y + .35, z, .09, .7)
    cyl(b, x, y + 1.05, z, .25, .8, 'y', 12, r2=.2); ball(b, x, y + 1.6, z, .17, .19, .17, 12)
    box(b, x - .3, x + .3, y + .75, y + 1.55, z + .15, z + .55)          # 背おった まき
    for k in range(4): cyl(b, x - .2 + k * .13, y + 1.15, z + .35, .06, .8, 'y', 6)
    box(b, x - .17, x + .17, y + 1.15, y + 1.3, z - .4, z - .22); bar(b, (x - .22, y + 1.25, z - .1), (x - .1, y + 1.25, z - .32), .05, 6); bar(b, (x + .22, y + 1.25, z - .1), (x + .1, y + 1.25, z - .32), .05, 6)
    colbox(x - .85, x + .85, z - .85, z + .85, 3.4, '二宮金次郎の像')
statue(-21, -22.3)
# ---- 鉄棒（3つの高さ）----
def tetsubo(x, z0):
    for k, h in enumerate((.9, 1.15, 1.4)):
        za = z0 + k * 2.0; zb = za + 1.8
        for zz in (za, zb): cyl(C(['#e04848', '#2f6fb8', '#e8c030'][k], .5), x, h / 2 + .02, zz, .06, h + .05, 'y', 10); colcircle(x, zz, .12, h, '鉄棒')
        bar(M['steel'], (x, h, za), (x, h, zb), .025, 8)
    box(G['sand'], x - 1.0, x + 1.0, 0, .01, z0 - .3, z0 + 6.1)
tetsubo(-31, -22)
# ---- のぼり棒 ----
def noboribo(x, z):
    for zz in (z - 2.2, z + 2.2): cyl(M['yellow'], x, 2.0, zz, .08, 4.0, 'y', 10); colcircle(x, zz, .15, 4, 'のぼり棒')
    bar(M['yellow'], (x, 4.0, z - 2.2), (x, 4.0, z + 2.2), .08, 10)
    for k in range(5): zz = z - 1.6 + k * .8; bar(M['steel'], (x, 0, zz), (x, 4.0, zz), .025, 8); colcircle(x, zz, .08, 4, 'のぼり棒')
    box(G['sand'], x - 1.0, x + 1.0, 0, .01, z - 2.5, z + 2.5)
noboribo(-31, -12.5)
# ---- 雲梯 ----
def untei(x, z0, z1):
    for zz in (z0, z1):
        for s in (-1, 1): bar(M['blue'], (x + s * .6, 0, zz), (x + s * .6, 2.2, zz), .05, 8); colcircle(x + s * .6, zz, .12, 2.2, '雲梯')
    for s in (-1, 1): bar(M['blue'], (x + s * .6, 2.2, z0), (x + s * .6, 2.2, z1), .05, 8)
    zz = z0 + .3
    while zz < z1: bar(M['steel'], (x - .6, 2.2, zz), (x + .6, 2.2, zz), .025, 6); zz += .35
    for s in (-1, 1):   # 両はしの はしご
        z = z0 if s < 0 else z1
        for yy in (.5, 1.0, 1.5): bar(M['steel'], (x - .6, yy, z), (x + .6, yy, z), .025, 6)
untei(-31, -8.0, -1.5)
# ---- ジャングルジム（3×3×3）----
def jungle(x0, z0, n=4, s=.9):
    cols = [M['red'], M['yellow'], M['blue'], M['green2']]
    for i in range(n):
        for j in range(n):
            bar(cols[(i + j) % 4], (x0 + i * s, 0, z0 + j * s), (x0 + i * s, (n - 1) * s, z0 + j * s), .03, 6)
            for k in range(n):
                y = k * s
                if i < n - 1: bar(cols[k % 4], (x0 + i * s, y, z0 + j * s), (x0 + (i + 1) * s, y, z0 + j * s), .025, 6)
                if j < n - 1: bar(cols[k % 4], (x0 + i * s, y, z0 + j * s), (x0 + i * s, y, z0 + (j + 1) * s), .025, 6)
    colbox(x0 - .1, x0 + (n - 1) * s + .1, z0 - .1, z0 + (n - 1) * s + .1, (n - 1) * s, 'ジャングルジム')
jungle(-32.4, 1.5)
# ---- ブランコ（4つ）----
def swing(x, z0, z1):
    for zz in (z0, z1):
        for s in (-1, 1): bar(M['red'], (x + s * 1.3, 0, zz), (x, 2.6, zz), .06, 8); colcircle(x + s * 1.3, zz, .14, 2.6, 'ブランコ')
    bar(M['red'], (x, 2.6, z0), (x, 2.6, z1), .07, 10)
    n = 4; step = (z1 - z0) / n
    for k in range(n):
        zc = z0 + step * (k + .5)
        for dz in (-.22, .22): bar(M['steel'], (x, 2.6, zc + dz), (x + .05, .55, zc + dz), .01, 4)
        box(M['yellow'] if k % 2 else M['blue'], x - .2, x + .25, .5, .56, zc - .28, zc + .28, bevel=.02)
    box(M['steel'], x - 2.2, x - 2.1, 0, .7, z0, z1); colbox(x - 2.2, x - 2.1, z0, z1, .7, 'ブランコの さく')   # まえの さく
swing(-31.5, 8.0, 15.0)
# ---- 砂場 ----
box(M['wood'], -33.6, -28.4, 0, .3, 17.8, 18.0); box(M['wood'], -33.6, -28.4, 0, .3, 22.0, 22.2); box(M['wood'], -33.6, -33.4, 0, .3, 17.8, 22.2); box(M['wood'], -28.6, -28.4, 0, .3, 17.8, 22.2)
box(G['sand'], -33.4, -28.6, 0, .2, 18.0, 22.0, tile=1.5)
ball(G['sand'], -31.5, .2, 20.0, .9, .35, .7, 10); cyl(M['red'], -30.2, .35, 19.0, .12, .2, 'y', 10); bar(M['blue'], (-29.6, .25, 21.0), (-29.3, .5, 21.3), .03, 6)
# ---- すべり台 ----
def slide(x, z):
    h = 2.2
    for (dx, dz) in [(-.6, -.6), (.6, -.6), (-.6, .6), (.6, .6)]: bar(M['steel'], (x + dx, 0, z + dz), (x + dx, h + .9, z + dz), .05, 8)
    box(M['orange'], x - .7, x + .7, h - .08, h, z - .7, z + .7, bevel=.02)
    for s in (-1, 1): bar(M['steel'], (x + s * .62, h + .9, z - .6), (x + s * .62, h + .9, z + .6), .04, 8)
    bar(M['steel'], (x - .62, h + .9, z - .62), (x + .62, h + .9, z - .62), .04, 8)
    for k in range(7):   # はしご（奥がわ）
        y = .3 + k * .3; bar(M['steel'], (x - .5, y, z - .75 - (h - y) * .25), (x + .5, y, z - .75 - (h - y) * .25), .025, 6)
    for s in (-1, 1): bar(M['steel'], (x + s * .5, 0, z - .75 - h * .25), (x + s * .5, h + .8, z - .75 + .2), .04, 8)
    # すべる面（手前に向かって）
    L = 4.2; zs, ze = z + .7, z + .7 + L
    quad(C('#d8dcde', .2, .8), [(x - .45, h, zs), (x + .45, h, zs), (x + .45, .35, ze), (x - .45, .35, ze)][::-1], name='slide')
    quad(C('#d8dcde', .2, .8), [(x + .45, .35, ze), (x + .45, .1, ze + .7), (x - .45, .1, ze + .7), (x - .45, .35, ze)][::-1], name='slide2')
    for s in (-1, 1):
        quad(M['blue'], [(x + s * .45, h, zs), (x + s * .45, h + .35, zs), (x + s * .45, .7, ze), (x + s * .45, .35, ze)][::s], name='slidewall')
        bar(M['steel'], (x + s * .48, .0, ze - .3), (x + s * .48, .4, ze - .3), .04, 6)
    colbox(x - .75, x + .75, z - 1.4, z + .75, h + 1, 'すべり台'); colbox(x - .55, x + .55, zs, ze + .6, 1.0, 'すべり台（すべる面）')
slide(31.0, -14.5)
# ---- 体育倉庫 ----
box(C('#8aa0a8', .6, .3), 28.6, 34.6, 0, 3.2, -24.6, -20.6)
for k in range(int(6 / .15)): x = 28.6 + k * .15; box(C('#7a8f97', .5, .4), x, x + .07, 0, 3.2, -20.6, -20.56)
box(C('#5a6e76', .6, .3), 28.4, 34.8, 3.2, 3.4, -24.8, -20.3)
box(C('#e8e6df', .6), 30.2, 33.0, .1, 2.6, -20.55, -20.5); bar(M['steel'], (31.0, 1.3, -20.45), (31.0, 1.6, -20.45), .02, 6)
sign('体育倉庫', 31.6, 2.85, -20.5, 2.0, .45, '+z', bg='#f4f1e8', fg='#1d1b19', border='#6b5a3a')
colbox(28.5, 34.7, -24.7, -20.5, 3.4, '体育倉庫')
# ---- タイヤとび ----
for k in range(9):
    zz = -6.0 + k * .95; cyl(M['rubber'], 31.0 + (k % 2) * .5, .35, zz, .42, .3, 'x', 20); cyl(C('#3a3a3c', .9), 31.0 + (k % 2) * .5, .35, zz, .25, .32, 'x', 16)
    for s in (-1, 1): box(C(['#e04848', '#e8c030', '#2f6fb8'][k % 3], .7), 31.0 + (k % 2) * .5 + s * .16 - .02, 31.0 + (k % 2) * .5 + s * .16 + .02, .5, .72, zz - .3, zz + .3)
colbox(30.5, 32.0, -6.5, 2.0, .8, 'タイヤとび')
# ---- 百葉箱 ----
for (dx, dz) in [(-.4, -.4), (.4, -.4), (-.4, .4), (.4, .4)]: bar(M['white'], (31 + dx, 0, 6 + dz), (31 + dx, 1.2, 6 + dz), .04, 6)
box(M['white'], 30.5, 31.5, 1.2, 2.1, 5.5, 6.5, bevel=.02)
for k in range(6): box(C('#e4e1d8', .8), 30.52, 31.48, 1.3 + k * .13, 1.36 + k * .13, 6.5, 6.53)
quad(M['white'], [(30.4, 2.1, 6.6), (31.6, 2.1, 6.6), (31.6, 2.4, 6.0), (30.4, 2.4, 6.0)], name='hroof'); quad(M['white'], [(31.6, 2.1, 5.4), (30.4, 2.1, 5.4), (30.4, 2.4, 6.0), (31.6, 2.4, 6.0)], name='hroof')
colbox(30.4, 31.6, 5.4, 6.6, 2.4, '百葉箱')
# ---- ベンチ ----
def bench(x, z, along='z', L=2.4):
    if along == 'z':
        box(M['wood'], x - .25, x + .25, .42, .48, z - L / 2, z + L / 2, bevel=.01)
        for zz in (z - L / 2 + .2, z + L / 2 - .2): box(M['conc'], x - .22, x + .22, 0, .42, zz - .08, zz + .08)
        colbox(x - .3, x + .3, z - L / 2, z + L / 2, .5, 'ベンチ')
    else:
        box(M['wood'], x - L / 2, x + L / 2, .42, .48, z - .25, z + .25, bevel=.01)
        for xx in (x - L / 2 + .2, x + L / 2 - .2): box(M['conc'], xx - .08, xx + .08, 0, .42, z - .22, z + .22)
        colbox(x - L / 2, x + L / 2, z - .3, z + .3, .5, 'ベンチ')
bench(33.6, 11.0); bench(33.6, 14.0); bench(-10, 22.6, 'x'); bench(10, 22.6, 'x')
# ---- バックネット（右手前のすみ）----
cxn, czn, rn = 30.0, 20.0, 4.2
for k in range(9):
    a = math.radians(-10 + k * 12.5); x = cxn + math.cos(a) * rn; z = czn + math.sin(a) * rn
    cyl(M['steel'], x, 3.0, z, .07, 6.0, 'y', 8); colcircle(x, z, .2, 6, 'バックネット')
    if k < 8:
        a2 = math.radians(-10 + (k + 1) * 12.5); x2 = cxn + math.cos(a2) * rn; z2 = czn + math.sin(a2) * rn
        for yy in (.1, 3.0, 5.9): bar(M['steel'], (x, yy, z), (x2, yy, z2), .03, 6)
        for t in np.linspace(0, 1, 8)[1:-1]: bar(M['net'], (x + (x2 - x) * t, .1, z + (z2 - z) * t), (x + (x2 - x) * t, 5.9, z + (z2 - z) * t), .008, 4)
        for yy in np.arange(.4, 5.9, .4): bar(M['net'], (x, float(yy), z), (x2, float(yy), z2), .008, 4)
        n = 6
        for i in range(n): colcircle(x + (x2 - x) * (i + .5) / n, z + (z2 - z) * (i + .5) / n, .25, 6, 'バックネット')
# ---- サッカーゴール ----
def goal(x, z, face):
    w, h, d = 5.0, 2.1, 1.4
    for s in (-1, 1): bar(M['white'], (x, 0, z + s * w / 2), (x, h, z + s * w / 2), .06, 10); colcircle(x, z + s * w / 2, .15, h, 'ゴール')
    bar(M['white'], (x, h, z - w / 2), (x, h, z + w / 2), .06, 10)
    xb = x - face * d
    for s in (-1, 1): bar(M['white'], (x, h, z + s * w / 2), (xb, 0, z + s * w / 2), .04, 8); bar(M['white'], (xb, 0, z + s * w / 2), (x, 0, z + s * w / 2), .04, 8)
    bar(M['white'], (xb, 0, z - w / 2), (xb, 0, z + w / 2), .04, 8)
    for t in np.linspace(0, 1, 13)[1:-1]: bar(M['net'], (x, h, z - w / 2 + w * t), (xb, 0, z - w / 2 + w * t), .008, 4)
    for t in np.linspace(0, 1, 6)[1:-1]: bar(M['net'], (x + (xb - x) * t, h * (1 - t), z - w / 2), (x + (xb - x) * t, h * (1 - t), z + w / 2), .008, 4)
    colbox(xb - .05, xb + .05, z - w / 2, z + w / 2, 2.1, 'ゴールのうしろ')
goal(-(TR['L'] + TR['R'] - 1.0), TR['cz'], 1); goal(TR['L'] + TR['R'] - 1.0, TR['cz'], -1)   # 線（ゴールライン）の上
# ---- 桜の木（フェンスぞい）----
def sakura(x, z, s=1.0):
    cyl(M['bark'], x, 1.6 * s, z, .22 * s, 3.2 * s, 'y', 10, r2=.15 * s)
    for k in range(4):
        a = k / 4 * math.tau + rnd.random(); bar(M['bark'], (x, 2.6 * s, z), (x + math.cos(a) * 1.4 * s, 3.8 * s, z + math.sin(a) * 1.4 * s), .09 * s, 6)
    for k in range(11):
        a = rnd.random() * math.tau; r = rnd.random() * 1.9 * s
        ball(M['sakura'] if k % 3 else M['sakura2'], x + math.cos(a) * r, (3.7 + rnd.random() * 1.6) * s, z + math.sin(a) * r, 1.1 * s, .8 * s, 1.1 * s, 10)
    colcircle(x, z, .35 * s, 4, '桜の木')
for x in (-30, -23, -16, -9, 9, 16, 23):
    sakura(x, 23.4, .95 + rnd.random() * .1)
for z in (-16, -2, 6, 16): sakura(33.8, z if z != 6 else 9.5, .9)
for z in (-17.5, -4.5, 6.5, 16.5): sakura(-33.9, z, .85)
# ---- 砂ぼこりよけの まく（手前）・時計の柱 ----
cyl(M['steel'], 12.0, 2.0, -16.5, .08, 4.0, 'y', 10); cyl(M['clock'], 12.0, 4.2, -16.5, .45, .2, 'z', 24); cyl(M['dark'], 12.0, 4.2, -16.6, .5, .15, 'z', 24)
bar(M['dark'], (12, 4.2, -16.39), (12, 4.5, -16.39), .025, 4); bar(M['dark'], (12, 4.2, -16.39), (12.2, 4.1, -16.39), .025, 4)
colcircle(12.0, -16.5, .2, 4, '時計の柱')

# 書き出し：歩ける範囲と はじめの場所もいっしょに
export(out, {'bounds': [X0 + .4, X1 - .4, Z0 + .25, Z1 - .4], 'start': [0, 0, 10], 'size': [X1 - X0, Z1 - Z0]})
