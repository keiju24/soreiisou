# 風見ニュータウンの 建物づくり（家の型・窓・玄関・屋根・ベランダ など）。
#   建物の中の座標（ローカル）：x 右、y 上、z 正面（玄関の面が +z）。XF で 回して 置く。
import math, random
from kazami_geo import *

class XF:
    """MB に ローカル座標で書きこむための 入れもの（回転 ang 度・平行移動）"""
    def __init__(self, mb, cx, cz, ang=0.0):
        self.mb = mb; a = math.radians(ang); self.c, self.s = math.cos(a), math.sin(a); self.cx, self.cz = cx, cz
    def P(self, p): x, y, z = p; return (self.cx + x * self.c + z * self.s, y, self.cz - x * self.s + z * self.c)
    def N(self, n): x, y, z = n; return (x * self.c + z * self.s, y, -x * self.s + z * self.c)
    def face(self, pts, col=None, tex=None, uvs=None, smooth=False, n=None):
        self.mb.face([self.P(p) for p in pts], col, tex, uvs, smooth, None if n is None else self.N(n))
    def mesh(self, verts, faces, col=None, tex=None, smooth=True, uvs=None):
        self.mb.mesh([self.P(p) for p in verts], faces, col, tex, smooth, uvs)

FACE_ANG = {'s': 0, 'e': 90, 'n': 180, 'w': -90}
WALLCOL = {'w': '#f3efe6', 'be': '#ecd9b4', 'ly': '#f4e7b2', 'lb': '#d3e3ee', 'br': '#a87d58', 'cr': '#f6ecd4'}
TRIM = '#fbfaf6'; DARK = '#4a4540'; FOUND = '#99948a'; SOFFIT = '#efe9dc'; FRAME = '#e9ecee'; DOORC = ['#8a5a36', '#6b4630', '#f2f0ea', '#3f5f7a', '#a0703c']

# ---- かべの座標系（u：かべに そって右へ、y：上、d：かべから外へ）----
def wall_frame(side, W, D):
    return {'+z': ((0, 0, D / 2), (1, 0, 0), (0, 0, 1), W), '-z': ((0, 0, -D / 2), (-1, 0, 0), (0, 0, -1), W),
            '+x': ((W / 2, 0, 0), (0, 0, -1), (1, 0, 0), D), '-x': ((-W / 2, 0, 0), (0, 0, 1), (-1, 0, 0), D)}[side]
def wp(fr, u, y, d):
    o, t, n, _ = fr; return (o[0] + t[0] * u + n[0] * d, y, o[2] + t[2] * u + n[2] * d)
def panel(xf, fr, u0, u1, y0, y1, d0, d1, col=None, tex=None, back=False):
    """かべに はりつく 箱（前・上・下・左右の 5面）"""
    P = lambda u, y, d: wp(fr, u, y, d); o, t, n, _ = fr
    xf.face([P(u0, y0, d1), P(u1, y0, d1), P(u1, y1, d1), P(u0, y1, d1)], col, tex, n=n)
    xf.face([P(u0, y1, d0), P(u0, y1, d1), P(u1, y1, d1), P(u1, y1, d0)], col, tex, n=(0, 1, 0))
    xf.face([P(u0, y0, d0), P(u1, y0, d0), P(u1, y0, d1), P(u0, y0, d1)], col, tex, n=(0, -1, 0))
    xf.face([P(u1, y0, d0), P(u1, y1, d0), P(u1, y1, d1), P(u1, y0, d1)], col, tex, n=t)
    xf.face([P(u0, y0, d1), P(u0, y1, d1), P(u0, y1, d0), P(u0, y0, d0)], col, tex, n=(-t[0], 0, -t[2]))
def glassq(xf, fr, u0, u1, y0, y1, d):
    P = lambda u, y: wp(fr, u, y, d)
    xf.face([P(u0, y0), P(u1, y0), P(u1, y1), P(u0, y1)], None, 'glass', uvs=[(0, 0), (1, 0), (1, 1), (0, 1)], n=fr[2])
def window(xf, fr, u, y0, w, h, frame=FRAME, shutter=None, sill=True, grid=True, curtain=None):
    panel(xf, fr, u - w / 2 - .07, u + w / 2 + .07, y0 - .07, y0 + h + .07, 0, .05, frame)
    glassq(xf, fr, u - w / 2, u + w / 2, y0, y0 + h, .055)
    if curtain: panel(xf, fr, u - w / 2 + .02, u - w / 2 + w * .28, y0 + .03, y0 + h - .03, .05, .056, curtain)
    if grid:
        if w > .9: panel(xf, fr, u - .025, u + .025, y0, y0 + h, .05, .075, frame)
        if h > 1.2: panel(xf, fr, u - w / 2, u + w / 2, y0 + h * .55, y0 + h * .55 + .04, .05, .075, frame)
    if sill: panel(xf, fr, u - w / 2 - .12, u + w / 2 + .12, y0 - .15, y0 - .07, 0, .14, frame)
    if shutter: panel(xf, fr, u - w / 2 - .1, u + w / 2 + .1, y0 + h + .08, y0 + h + .32, 0, .16, shutter)   # 雨戸の戸袋（上）
def door(xf, fr, u, y0, col, canopy=True, w=.95, lampc=True):
    panel(xf, fr, u - w / 2 - .08, u + w / 2 + .08, y0, y0 + 2.2, 0, .04, TRIM)
    panel(xf, fr, u - w / 2, u + w / 2, y0, y0 + 2.12, .04, .07, col)
    glassq(xf, fr, u - .1, u + .1, y0 + .9, y0 + 1.9, .072)
    panel(xf, fr, u + w / 2 - .18, u + w / 2 - .12, y0 + .95, y0 + 1.15, .07, .12, '#d8c58a')     # とって
    if canopy:
        panel(xf, fr, u - w / 2 - .45, u + w / 2 + .45, y0 + 2.35, y0 + 2.47, 0, .85, '#e7e3da')
        panel(xf, fr, u - w / 2 - .45, u + w / 2 + .45, y0 + 2.31, y0 + 2.35, .8, .85, '#9c968c')
    if lampc: panel(xf, fr, u - w / 2 - .32, u - w / 2 - .18, y0 + 1.7, y0 + 1.95, 0, .1, None, 'lamp')
    panel(xf, fr, u - w / 2 - .3, u + w / 2 + .3, 0, y0, 0, .7, '#b9b4aa')                           # ポーチの段
def downspout(xf, fr, u, y1):
    a = wp(fr, u, .05, .08); b = wp(fr, u, y1, .08); bar(xf, a, b, .045, '#d6d2ca', 6)
def ac_unit(xf, fr, u):
    panel(xf, fr, u - .4, u + .4, .05, .65, .1, .4, '#ecebe6')
    panel(xf, fr, u - .2, u + .2, .15, .55, .4, .405, '#5d5f62')
    panel(xf, fr, u - .42, u + .42, .0, .05, .08, .42, '#8c8a85')
def balcony(xf, fr, u0, u1, y, depth=1.0, col='#f4f2ee', solid=True):
    panel(xf, fr, u0, u1, y - .15, y, 0, depth, '#d9d5cc')
    if solid:
        panel(xf, fr, u0, u1, y, y + 1.0, depth - .06, depth, col)
        panel(xf, fr, u0, u0 + .06, y, y + 1.0, 0, depth, col); panel(xf, fr, u1 - .06, u1, y, y + 1.0, 0, depth, col)
        panel(xf, fr, u0, u1, y + 1.0, y + 1.06, -.02, depth + .02, '#c9c4ba')
    else:
        for k in range(int((u1 - u0) / .14) + 1):
            uu = u0 + k * .14; bar(xf, wp(fr, uu, y, depth - .04), wp(fr, uu, y + 1.0, depth - .04), .015, col, 4)
        bar(xf, wp(fr, u0, y + 1.0, depth - .04), wp(fr, u1, y + 1.0, depth - .04), .035, col, 6)
        panel(xf, fr, u0, u0 + .05, y, y + 1.0, 0, depth, col); panel(xf, fr, u1 - .05, u1, y, y + 1.0, 0, depth, col)
    # 物干しざお
    bar(xf, wp(fr, u0 + .2, y + 1.55, depth * .6), wp(fr, u1 - .2, y + 1.55, depth * .6), .02, '#b8bcc0', 4)

# ---- 屋根 ----
def roof_face(xf, pts, key, nh, slope_k):
    """屋根の面：u ＝ 軒に そって、v ＝ 上へ（2m で 1枚）"""
    ex, ez = -nh[2], nh[0]
    uvs = [((p[0] * ex + p[2] * ez) / 2.0, -(p[0] * nh[0] + p[2] * nh[2]) * slope_k / 2.0) for p in pts]
    xf.face(pts, None, key, uvs=uvs, n=(nh[0], 1, nh[2]))
def under(xf, pts, t, col=SOFFIT):
    xf.face([(p[0], p[1] - t, p[2]) for p in pts], col, n=(0, -1, 0))
def edge(xf, a, b, t, col):
    """屋根のふちの 厚み（a→b の線から 下へ t）"""
    xf.face([(a[0], a[1] - t, a[2]), (b[0], b[1] - t, b[2]), b, a], col, n=None)
    xf.face([a, b, (b[0], b[1] - t, b[2]), (a[0], a[1] - t, a[2])], col, n=None)
def gable_roof(xf, W, D, H, rc, wall, pitch=.55, ov=.55, ovx=.4, t=.16, fascia='#5a524a'):
    key = 'roof_' + rc; X = W / 2 + ovx; Ze = D / 2 + ov; ye = H - ov * pitch; yr = H + D / 2 * pitch; k = math.sqrt(1 + pitch * pitch)
    for s in (1, -1):
        pts = [(-X, ye, s * Ze), (X, ye, s * Ze), (X, yr, 0), (-X, yr, 0)]
        if s < 0: pts = [pts[1], pts[0], pts[3], pts[2]]
        roof_face(xf, pts, key, (0, 0, s), k); under(xf, pts, t)
        edge(xf, (-X, ye, s * Ze), (X, ye, s * Ze), t, fascia)
        for sx in (-1, 1): edge(xf, (sx * X, ye, s * Ze), (sx * X, yr, 0), t, fascia)
    xf.face([(-X, yr - .02, 0), (X, yr - .02, 0), (X, yr + .1, 0), (-X, yr + .1, 0)], col=fascia)     # 棟
    bar(xf, (-X, yr + .04, 0), (X, yr + .04, 0), .09, fascia, 6)
    for sx in (-1, 1):                                                                              # 妻（三角のかべ）
        pts = [(sx * W / 2, H, -sx * D / 2), (sx * W / 2, H, sx * D / 2), (sx * W / 2, H + D / 2 * pitch, 0)]
        xf.face(pts, col=wall, n=(sx, 0, 0))
    return yr
def hip_roof(xf, W, D, H, rc, pitch=.5, ov=.55, t=.16, fascia='#5a524a'):
    key = 'roof_' + rc; Xo, Zo = W / 2 + ov, D / 2 + ov; ye = H - ov * pitch
    short = min(Xo, Zo); yr = ye + short * pitch; k = math.sqrt(1 + pitch * pitch)
    if Xo >= Zo: r1, r2 = (-(Xo - Zo), yr, 0), ((Xo - Zo), yr, 0)
    else: r1, r2 = (0, yr, (Zo - Xo)), (0, yr, -(Zo - Xo))
    A, B, C, Dd = (-Xo, ye, Zo), (Xo, ye, Zo), (Xo, ye, -Zo), (-Xo, ye, -Zo)
    if Xo >= Zo:
        faces = [([A, B, r2, r1], (0, 0, 1)), ([C, Dd, r1, r2], (0, 0, -1)), ([B, C, r2], (1, 0, 0)), ([Dd, A, r1], (-1, 0, 0))]
    else:
        faces = [([A, B, r1], (0, 0, 1)), ([C, Dd, r2], (0, 0, -1)), ([B, C, r2, r1], (1, 0, 0)), ([Dd, A, r1, r2], (-1, 0, 0))]
    for pts, nh in faces: roof_face(xf, pts, key, nh, k); under(xf, pts, t)
    for a, b in ((A, B), (B, C), (C, Dd), (Dd, A)): edge(xf, a, b, t, fascia)
    for a, b in ((A, r1 if Xo >= Zo else r1), (B, r2 if Xo >= Zo else r1), (C, r2), (Dd, r1 if Xo >= Zo else r2)): bar(xf, a, b, .05, fascia, 5)
    if r1 != r2: bar(xf, r1, r2, .08, fascia, 6)
    return yr
def shed_roof(xf, W, D, H, rc, wall, rise=1.4, ov=.5, t=.16, fascia='#3f3a36'):
    key = 'roof_' + rc; X = W / 2 + .35; Zf, Zb = D / 2 + ov, -D / 2 - ov; p = rise / D
    yf, yb = H - ov * p, H + rise + ov * p; k = math.sqrt(1 + p * p)
    pts = [(-X, yf, Zf), (X, yf, Zf), (X, yb, Zb), (-X, yb, Zb)]
    roof_face(xf, pts, key, (0, 0, 1), k); under(xf, pts, t)
    for a, b in ((pts[0], pts[1]), (pts[1], pts[2]), (pts[2], pts[3]), (pts[3], pts[0])): edge(xf, a, b, t, fascia)
    for sx in (-1, 1): xf.face([(sx * W / 2, H, D / 2), (sx * W / 2, H, -D / 2), (sx * W / 2, H + rise, -D / 2)], col=wall, n=(sx, 0, 0))
    xf.face([(W / 2, H, -D / 2), (-W / 2, H, -D / 2), (-W / 2, H + rise, -D / 2), (W / 2, H + rise, -D / 2)], col=wall, n=(0, 0, -1))
    return H + rise
def flat_roof(xf, W, D, H, wall, cap='#d8d3c8', top='#a3a29c', par=.55):
    box(xf, -W / 2, W / 2, H, H + .04, -D / 2, D / 2, col=top, sides='', top=True)
    for (x0, x1, z0, z1) in [(-W / 2, W / 2, D / 2 - .18, D / 2), (-W / 2, W / 2, -D / 2, -D / 2 + .18), (-W / 2, -W / 2 + .18, -D / 2, D / 2), (W / 2 - .18, W / 2, -D / 2, D / 2)]:
        box(xf, x0, x1, H, H + par, z0, z1, col=wall)
        box(xf, x0 - .03, x1 + .03, H + par, H + par + .07, z0 - .03, z1 + .03, col=cap)
    return H + par

# ---- 家の型 ----
#  A 2階 切妻 / B 2階 寄棟 / C 平屋 寄棟 / D 2階 切妻＋1階の はなれ / E 3階 細長い 平屋根 / F 2階 片流れ /
#  G 2階 切妻＋広いベランダ / H 和風 瓦の寄棟（下屋つき）/ I 2階 切妻＋前に出た妻 / J アパート（外階段）/ K 2階 箱形 平屋根 / L 2階 切妻＋出窓＋ポーチ
FH = 2.75; BASE = .42
def walls(xf, W, D, y0, y1, wall, band=None):
    box(xf, -W / 2, W / 2, y0, y1, -D / 2, D / 2, col=wall, top=False)
    if band: box(xf, -W / 2 - .04, W / 2 + .04, band - .06, band + .06, -D / 2 - .04, D / 2 + .04, col=TRIM, top=False)
def foundation(xf, W, D):
    box(xf, -W / 2 - .04, W / 2 + .04, 0, BASE, -D / 2 - .04, D / 2 + .04, col=FOUND, top=False)
def win_row(xf, fr, L, y0, h, n, skip=None, shutter=None, curtain=None, w=1.1, margin=.9):
    if n <= 0: return
    if n == 1: us = [0.0]
    else: us = [-L / 2 + margin + (L - 2 * margin) * k / (n - 1) for k in range(n)]
    for u in us:
        if skip is not None and abs(u - skip) < 1.3: continue
        window(xf, fr, u, y0, w, h, shutter=shutter, curtain=curtain)
def house(mb, cx, cz, W, D, typ, rc, wc, face='s', rnd=None, lod=None):
    """1けんの家。W×D はローカル（玄関の面が +z）。lod に MB をわたすと 遠くで使う かんたんな形も作る"""
    rnd = rnd or random.Random(0); xf = XF(mb, cx, cz, FACE_ANG[face]); wall = WALLCOL.get(wc, wc)
    curtain = rnd.choice([None, '#f3e3c4', '#dfeaf2', '#f2d7d7'])
    shutter = rnd.choice([None, '#8f8a82', '#b8b2a6']) if typ in 'ABCHL' else None
    door_u = rnd.choice([-1, 1]) * (W / 2 - 1.2) if W > 5 else 0
    dcol = rnd.choice(DOORC)
    fr = {s: wall_frame(s, W, D) for s in ('+z', '-z', '+x', '-x')}
    foundation(xf, W, D)
    floors = {'C': 1, 'H': 2, 'E': 3, 'J': 2}.get(typ, 2)
    H = BASE + floors * FH
    top = H
    if typ == 'H':                                                    # 和風：1階は広く、2階は 小さく まんなか
        walls(xf, W, D, BASE, BASE + FH, wall)
        W2, D2 = W * .7, D * .72
        box(xf, -W2 / 2, W2 / 2, BASE + FH, H, -D2 / 2, D2 / 2, col=wall, top=False)
        # 下屋（1階のまわりの ひさし屋根）
        key = 'roof_' + rc; yb = BASE + FH + .15; ov = .6; pitch = .45
        for nh in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0)):
            if nh[2]: a = (W / 2 + ov) ; b = (D / 2 + ov); inner_a, inner_b = W2 / 2, D2 / 2; s = nh[2]
            else: a = (D / 2 + ov); b = (W / 2 + ov); inner_a, inner_b = D2 / 2, W2 / 2; s = nh[0]
            yo = yb - (b - inner_b) * pitch
            if nh[2]: pts = [(-a, yo, s * b), (a, yo, s * b), (inner_a, yb, s * inner_b), (-inner_a, yb, s * inner_b)]
            else: pts = [(s * b, yo, a), (s * b, yo, -a), (s * inner_b, yb, -inner_a), (s * inner_b, yb, inner_a)]
            if (nh[2] < 0) or (nh[0] < 0): pts = [pts[1], pts[0], pts[3], pts[2]]
            roof_face(xf, pts, key, nh, math.sqrt(1 + pitch * pitch)); under(xf, pts, .14)
            edge(xf, pts[0], pts[1], .14, '#4a4038')
        top = hip_roof(XF(mb, cx, cz, FACE_ANG[face]), W2, D2, H, rc, pitch=.5, ov=.55)
        win_row(xf, fr['+z'], W, BASE + .75, 1.5, 3, skip=door_u, shutter=shutter, w=1.6)
        win_row(xf, wall_frame('+z', W2, D2), W2, BASE + FH + .8, 1.1, 2, curtain=curtain)
        for s in ('+x', '-x'): win_row(xf, fr[s], D, BASE + .8, 1.2, 2, shutter=shutter)
        door(xf, fr['+z'], door_u, BASE, '#6b4630', canopy=False)
        # 縁側（えんがわ）
        panel(xf, fr['+z'], -W / 2 + .3, W / 2 - .3, BASE - .05, BASE + .05, 0, .55, '#a98058')
    elif typ == 'J':                                                  # アパート：2階建て、外の廊下と階段
        walls(xf, W, D, BASE, H, wall, band=BASE + FH)
        top = hip_roof(xf, W, D, H, rc, pitch=.35, ov=.45)
        n = max(2, int(W / 3.6))
        for fl in range(2):
            y = BASE + fl * FH
            for k in range(n):
                u = -W / 2 + (k + .5) * W / n
                door(xf, fr['+z'], u - .7, y, '#8a9aa6', canopy=False, w=.8, lampc=True)
                window(xf, fr['+z'], u + .75, y + 1.0, .8, .9, grid=False)
            for s in ('-z',): win_row(xf, fr[s], W, y + .8, 1.3, n, curtain=curtain)
        # 2階の廊下と手すり
        panel(xf, fr['+z'], -W / 2, W / 2, BASE + FH - .2, BASE + FH, 0, 1.3, '#cfcac0')
        panel(xf, fr['+z'], -W / 2, W / 2, BASE + FH, BASE + FH + 1.0, 1.24, 1.3, '#f0ede6')
        panel(xf, fr['+z'], -W / 2, W / 2, BASE + FH + 1.0, BASE + FH + 1.06, 1.2, 1.34, '#9a958c')
        # 外階段（右はし）
        for k in range(12):
            y = (k + 1) * (BASE + FH) / 12
            panel(xf, fr['+x'], -.2 + 0, 1.0, y - .06, y, 0, .9, '#8f99a3') if False else None
        st = wall_frame('+x', W, D)
        for k in range(12):
            y = (k + 1) * (BASE + FH) / 12; u = D / 2 - .2 - k * (D - .6) / 12
            panel(xf, st, u - .3, u, y - .08, y, .05, 1.0, '#8f99a3')
        bar(xf, wp(st, D / 2 - .2, 1.0, 1.0), wp(st, -D / 2 + .5, BASE + FH + 1.0, 1.0), .03, '#6f7983')
        sign_name = None
    else:
        band = BASE + FH if floors >= 2 else None
        if typ == 'E':
            walls(xf, W, D, BASE, H, wall, band=None)
            top = flat_roof(xf, W, D, H, wall)
            for fl in range(3):
                y = BASE + fl * FH
                if fl == 0: door(xf, fr['+z'], 0 if W < 5 else door_u, y, dcol)
                else: window(xf, fr['+z'], 0, y + .7, min(W - 1.4, 2.2), 1.4, grid=True, curtain=curtain)
                for s in ('+x', '-x'): win_row(xf, fr[s], D, y + .9, 1.1, max(1, int(D / 3)), w=.8)
            panel(xf, fr['+z'], -W / 2, W / 2, BASE + FH * 2 - .1, BASE + FH * 2 + .02, 0, .6, '#d6d1c6')
        elif typ == 'K':
            walls(xf, W, D, BASE, H, wall)
            top = flat_roof(xf, W, D, H, wall, top='#9da09c', par=.4)
            panel(xf, fr['+z'], -W / 2, W / 2, BASE + FH - .1, BASE + FH + .05, 0, .35, '#5d5a55')      # 帯
            win_row(xf, fr['+z'], W, BASE + .5, 1.9, 2, skip=door_u, w=1.8)
            window(xf, fr['+z'], -W / 4, BASE + FH + .5, W * .4, 1.5, curtain=curtain)
            window(xf, fr['+z'], W / 4, BASE + FH + .9, W * .3, 1.0)
            door(xf, fr['+z'], door_u, BASE, '#3d3a36')
            for s in ('+x', '-x'):
                win_row(xf, fr[s], D, BASE + .9, 1.1, 2, w=.9); win_row(xf, fr[s], D, BASE + FH + .9, 1.1, 2, w=.9)
        else:
            walls(xf, W, D, BASE, H, wall, band=band)
            if typ in 'AGIL': top = gable_roof(xf, W, D, H, rc, wall)
            elif typ == 'D': top = gable_roof(xf, W * .72 if W > 6 else W, D, H, rc, wall) if False else gable_roof(xf, W, D, H, rc, wall)
            elif typ in 'BC': top = hip_roof(xf, W, D, H, rc, pitch=.5 if typ == 'B' else .45, ov=.6 if typ == 'C' else .55)
            elif typ == 'F': top = shed_roof(xf, W, D, H, rc, wall)
            for fl in range(floors):
                y = BASE + fl * FH
                nfront = max(1, int((W - 1) / 2.4))
                win_row(xf, fr['+z'], W, y + .8, 1.2 if fl else 1.4, nfront, skip=door_u if fl == 0 else None, shutter=shutter, curtain=curtain if fl else None)
                win_row(xf, fr['-z'], W, y + .9, 1.1, max(1, nfront - 1), shutter=shutter)
                for s in ('+x', '-x'): win_row(xf, fr[s], D, y + .9, 1.1, max(1, int((D - 1) / 3.2)), w=.9)
            door(xf, fr['+z'], door_u, BASE, dcol)
            if typ == 'G':
                balcony(xf, fr['+z'], -W / 2 + .3, W / 2 - .3, BASE + FH, 1.1, solid=True)
            elif typ in 'AB' and W > 6:
                bu = -door_u * .5
                balcony(xf, fr['+z'], bu - 1.6, bu + 1.6, BASE + FH, .9, solid=False, col='#e9ece9')
            if typ == 'I':                                            # 前に出た 妻（2階まで）
                w2 = min(W * .45, 3.6); u2 = -door_u * .6 if W > 5 else 0
                sub = XF(mb, *xf.P((u2, 0, D / 2 + .7))[::2], FACE_ANG[face])
                box(sub, -w2 / 2, w2 / 2, 0, BASE, -.7, .7, col=FOUND, top=False)
                box(sub, -w2 / 2, w2 / 2, BASE, H - .3, -.7, .7, col=wall, top=False, sides=['+z', '+x', '-x'])
                gable_roof(XF(mb, *xf.P((u2, 0, D / 2 + .6))[::2], FACE_ANG[face] + 90), 1.6, w2, H - .3, rc, wall, pitch=.7, ov=.4, ovx=.2)
                window(sub, wall_frame('+z', w2, 1.4), 0, BASE + FH + .7, 1.3, 1.2, shutter=shutter, curtain=curtain)
                window(sub, wall_frame('+z', w2, 1.4), 0, BASE + .8, 1.3, 1.3)
            if typ == 'L':                                            # 出窓とポーチの柱
                bu = -door_u * .55 if W > 5 else 0
                panel(xf, fr['+z'], bu - 1.0, bu + 1.0, BASE + .55, BASE + 2.05, 0, .45, wall)
                glassq(xf, fr['+z'], bu - .85, bu + .85, BASE + .7, BASE + 1.95, .455)
                panel(xf, fr['+z'], bu - 1.1, bu + 1.1, BASE + 2.05, BASE + 2.15, -.02, .55, rc and '#7d7268')
                for s in (-1, 1): bar(xf, wp(fr['+z'], door_u + s * .9, 0, 1.2), wp(fr['+z'], door_u + s * .9, BASE + 2.4, 1.2), .07, TRIM)
                panel(xf, fr['+z'], door_u - 1.1, door_u + 1.1, BASE + 2.4, BASE + 2.55, 0, 1.35, '#e7e3da')
            if typ == 'D':                                            # 1階の はなれ（片流れ屋根）を 横に
                side = -1 if door_u >= 0 else 1; ww = 2.6
                sub = XF(mb, *xf.P((side * (W / 2 + ww / 2), 0, .4))[::2], FACE_ANG[face])
                box(sub, -ww / 2, ww / 2, 0, BASE, -D / 2 + .6, D / 2 - .6, col=FOUND, top=False)
                box(sub, -ww / 2, ww / 2, BASE, BASE + FH, -D / 2 + .6, D / 2 - .6, col=wall, top=False)
                shed_roof(XF(mb, *xf.P((side * (W / 2 + ww / 2), 0, .4))[::2], FACE_ANG[face] + (90 if side > 0 else -90)), D - 1.2, ww, BASE + FH, rc, wall, rise=.6, ov=.35)
                window(sub, wall_frame('+z', ww, D - 1.2), 0, BASE + .8, 1.2, 1.1, shutter=shutter)
            if typ == 'F':
                panel(xf, fr['+z'], door_u - .3, door_u + .3, BASE + FH + .3, BASE + FH * 2 - .3, 0, .06, '#4a4540')   # たて長の まど わく
                glassq(xf, fr['+z'], door_u - .22, door_u + .22, BASE + FH + .38, BASE + FH * 2 - .38, .065)
    # 雨どい・室外機
    if typ not in 'EKJ':
        for s in (-1, 1): downspout(xf, fr['+z'], s * (W / 2 - .12), H - .1)
    ac_unit(xf, fr['+x' if door_u <= 0 else '-x'], rnd.uniform(-D / 4, D / 4))
    if typ in 'AGL' and rnd.random() < .35:                          # 太陽光パネル（南がわの屋根）
        p = .55; ze, zr = D / 2 - .3, .5; y0 = H + (D / 2 - ze) * p + .08; y1 = H + (D / 2 - zr) * p + .08
        xf.face([(-W / 3, y0, ze), (W / 3, y0, ze), (W / 3, y1, zr), (-W / 3, y1, zr)], col='#28385a', n=(0, 1, 1))
    if lod is not None:                                               # 遠くで使う かんたんな形
        lx = XF(lod, cx, cz, FACE_ANG[face])
        box(lx, -W / 2, W / 2, 0, H, -D / 2, D / 2, col=wall, top=typ in 'EKJ')
        if typ in 'EK': pass
        else:
            pc = ROOFCOL[rc] if rc in ROOFCOL else '#777777'
            yr = H + D / 2 * .55
            for s in (1, -1):
                pts = [(-W / 2 - .4, H - .3, s * (D / 2 + .55)), (W / 2 + .4, H - .3, s * (D / 2 + .55)), (W / 2 + .4, yr, 0), (-W / 2 - .4, yr, 0)]
                lx.face(pts, col=pc, n=(0, 1, s))
            for s in (-1, 1): lx.face([(s * W / 2, H, -D / 2), (s * W / 2, H, D / 2), (s * W / 2, yr, 0)], col=wall, n=(s, 0, 0))
    return H, top
