# 風見ニュータウン（風情ウォッチバスターズのフィールド）を Blender で作り、
#   models/kazami.glb と 当たり判定・ミニマップ・出口のデータ models/kazami.col.json を書き出す。
#   使い方：python tools/blender/kazami_build.py models/kazami.glb   （pip の bpy・shapely・mapbox_earcut がいる）
#
#   設計図は 添付の地図の画像。配置は kazami_layout.py（画像のピクセル座標）に書いてある。
#   ・道路は 中心線と幅から shapely で 形をつくる（交差点のかどは 丸める）。歩道・縁石・水路・芝生も 形の足し引きで出す
#   ・家は 1けんずつ（12 の型 × 屋根と壁の色）。施設は 専用の作り
#   ・木・草・電柱など くりかえす物は 同じメッシュを使いまわす（ゲームでは まとめて インスタンス描画）
#   ・ゲームの座標：x 東、y 上、z 南（画像の下）がプラス。1 = 1m（インポニャンは 約 1.8m）
import sys, os, math, random, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
import numpy as np
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, box as sbox, MultiLineString
from shapely.ops import unary_union, linemerge
from shapely import affinity
from kazami_geo import *
import kazami_geo as KG
import kazami_layout as L

out = sys.argv[-1] if sys.argv[-1].endswith('.glb') else os.path.join(ROOT, 'models', 'kazami.glb')
rnd = random.Random(7)
bpy.ops.wm.read_factory_settings(use_empty=True)

W = L.to_w
def WP(pts): return [W(p) for p in pts]
def WR(r):                                 # rect px → (x0, z0, x1, z1)
    a, b = W((r[0], r[1])), W((r[2], r[3])); return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

# =====================================================================
#  階層（KazamiNewTown の下に 種類ごとの節）
# =====================================================================
SCN = bpy.context.scene.collection
GROUPS = ['Terrain', 'MainRoads', 'ResidentialRoads', 'Sidewalks', 'ResidentialAreas', 'Houses', 'KazamiElementarySchool', 'Gymnasium',
          'SwimmingPool', 'SchoolGround', 'HidamariNursery', 'MitsubaPark', 'MarufukuMart', 'AsakuraHouse', 'TsukimoriHouse', 'Hanabiyori',
          'KomugiBakery', 'Uomaru', 'FutabaBank', 'TsubamePostOffice', 'ForestShop', 'OtherBuildings', 'Waterways', 'Bridges', 'Trees',
          'Vegetation', 'StreetProps', 'Colliders', 'MapExits', 'Lighting', 'EnvironmentalEffects', 'Minimap']
def empty(name, parent=None):
    e = bpy.data.objects.new(name, None); SCN.objects.link(e)
    if parent: e.parent = parent
    return e
ROOTE = empty('KazamiNewTown')
GRP = {g: empty(g, ROOTE) for g in GROUPS}
def put(mb, group, parent=None):
    return mb.build(parent or GRP[group], SCN)

# 当たり判定・ミニマップ・出口
COL = {'box': [], 'circle': [], 'seg': []}
def colbox(x0, z0, x1, z1, h=3.0, note=''): COL['box'].append([round(min(x0, x1), 2), round(max(x0, x1), 2), round(min(z0, z1), 2), round(max(z0, z1), 2), round(h, 2), note])
def colcircle(x, z, r, h=3.0, note=''): COL['circle'].append([round(x, 2), round(z, 2), round(r, 2), round(h, 2), note])
def colseg(a, b, r=.12, h=3.0, note=''):
    if math.hypot(b[0] - a[0], b[1] - a[1]) < .02: return
    COL['seg'].append([round(a[0], 2), round(a[1], 2), round(b[0], 2), round(b[1], 2), round(r, 2), round(h, 2), note])
MINI = {'buildings': [], 'icons': [], 'labels': []}

# =====================================================================
#  1. 形の足し引き（shapely）
# =====================================================================
O = Polygon(WP(L.OUTLINE)).buffer(0)
def roadshape(pts, w):
    ls = LineString(WP(pts)); return ls.buffer(w / 2, cap_style='flat', join_style='round')
def ends(pts, w):
    return [Point(W(p)).buffer(w / 2, 24) for p in (pts[0], pts[-1])]
main_parts, res_parts = [], []
for name, kind, pts, w in L.ROADS:
    (main_parts if kind == 'main' else res_parts).append(roadshape(pts, w))
    for e in ends(pts, w): (main_parts if kind == 'main' else res_parts).append(e)
def closing(g, r): return g.buffer(r, 24).buffer(-r, 24)
R_all = closing(unary_union(main_parts + res_parts), 2.6).intersection(O)
R_main = closing(unary_union(main_parts), 1.5).intersection(R_all)
R_res = R_all.difference(R_main)
Wfull = unary_union([LineString(WP(pts)).buffer(w / 2, cap_style='flat', join_style='mitre') for n, pts, w in L.WATER]).intersection(O.buffer(-.3))
Wt = Wfull.difference(R_all)                                   # 道の下（橋）をのぞいた 水路
BRIDGE = R_all.intersection(Wfull)
PATH = unary_union([LineString(WP(pts)).buffer(w / 2, 16) for k, pts, w in L.PATHS if k == 'brick']).intersection(O).difference(R_all).difference(Wfull.buffer(.3))
DPATH = unary_union([LineString(WP(pts)).buffer(w / 2, 16) for k, pts, w in L.PATHS if k == 'dirt']).intersection(O).difference(R_all).difference(Wfull.buffer(.3)).difference(PATH)
CURB = R_all.buffer(.2, 16).difference(R_all).intersection(O).difference(Wfull.buffer(.25))
SIDE = R_all.buffer(1.5, 16).difference(R_all.buffer(.2, 16)).intersection(O).difference(Wfull.buffer(.25)).difference(PATH)
PARK = unary_union([Polygon(WP(p)) for p in L.PARKS]).difference(R_all.buffer(1.5)).difference(Wfull).intersection(O.buffer(-.4))
DIRTG = unary_union([Polygon(WP(p)) for p in L.DIRT]).difference(R_all.buffer(1.5)).intersection(O)
GRASSG = unary_union([Polygon(WP(p)) for p in L.GRASS]).intersection(O)
USED = unary_union([R_all, CURB, SIDE, Wfull.buffer(.25), PATH, DPATH])
FREE = O.difference(USED)                                      # 道・歩道・水路でない ところ（区画）
from shapely.prepared import prep
ALLOW = prep(FREE.buffer(-.4))
FIT = {}
def fit(x0, z0, x1, z1, name, maxshift=4.0):
    """画像より道が太いぶん、建物が 道や歩道に かからないよう 少し ずらす・ちぢめる（いちばん小さい変化をえらぶ）"""
    if ALLOW.contains(sbox(x0, z0, x1, z1)): return (x0, z0, x1, z1)
    cx, cz, w, d = (x0 + x1) / 2, (z0 + z1) / 2, x1 - x0, z1 - z0; best = None
    shifts = sorted([(dx, dz) for dx in np.arange(-maxshift, maxshift + .01, .25) for dz in np.arange(-maxshift, maxshift + .01, .25)], key=lambda t: abs(t[0]) + abs(t[1]))
    for sw in (1, .92, .84, .76, .68):
        for sd in (1, .92, .84, .76, .68):
            sc_cost = (2 - sw - sd) * 18
            if best and sc_cost >= best[0]: continue
            for dx, dz in shifts:
                cost = abs(dx) + abs(dz) + sc_cost
                if best and cost >= best[0]: break
                r = sbox(cx + dx - w * sw / 2, cz + dz - d * sd / 2, cx + dx + w * sw / 2, cz + dz + d * sd / 2)
                if ALLOW.contains(r): best = (cost, r.bounds); break
    if not best: print('！ 区画に入らない：', name); return (x0, z0, x1, z1)
    FIT[name] = round(best[0], 2)
    return best[1]

def polys(g):
    if g.is_empty: return []
    if isinstance(g, Polygon): return [g]
    return [p for p in getattr(g, 'geoms', []) if isinstance(p, Polygon) and p.area > .01]
def rings(p): return [list(p.exterior.coords)] + [list(i.coords) for i in p.interiors]
def fill(mb, g, y, col=None, tex=None):
    for p in polys(g):
        p = p.simplify(.02)
        if p.is_empty or p.area < .02: continue
        for q in polys(p): flat(mb, rings(q), y, col, tex)
def lines(g):
    if g.is_empty: return []
    if isinstance(g, LineString): return [g]
    out = []
    for x in getattr(g, 'geoms', []): out += lines(x)
    return out
def seglist(g, step=None):
    """線 → (a, b) の区間の列"""
    out = []
    for ln in lines(g):
        c = list(ln.coords)
        for i in range(len(c) - 1): out.append((c[i], c[i + 1]))
    return out
def boundary_segs(g):
    out = []
    for p in polys(g):
        for r in rings(p):
            for i in range(len(r) - 1): out.append((r[i], r[i + 1]))
    return out

# =====================================================================
#  2. 住宅の庭（家のまわりの 塀の中）を先に決める
# =====================================================================
FACE = {'s': 0, 'e': 90, 'n': 180, 'w': -90}
houses = []
for i, (r, roof, wall, typ, face) in enumerate(L.HOUSES):
    x0, z0, x1, z1 = fit(*WR(r), 'House_%02d' % i)
    houses.append(dict(i=i, x0=x0, z0=z0, x1=x1, z1=z1, roof=roof, wall=wall, typ=typ, face=face, name='House_%02d' % i))
def yard_rect(h, front=2.4, side=1.1, back=.9):
    m = {'s': (side, back, side, front), 'n': (side, front, side, back), 'e': (back, side, front, side), 'w': (front, side, back, side)}[h['face']]
    return sbox(h['x0'] - m[0], h['z0'] - m[1], h['x1'] + m[2], h['z1'] + m[3])
YARD_SPECIAL = {'asakura': 'R', 'tsukimori': 'b', 'hanaHouse': 'g', 'hanaHouse2': 'g'}
yard_list = [(yard_rect(h), h) for h in houses]
for k in ('asakura', 'tsukimori', 'hanaHouse', 'hanaHouse2'):
    x0, z0, x1, z1 = fit(*WR(L.FACILITIES[k]), k, 6.0); f = {'asakura': 'w', 'tsukimori': 's', 'hanaHouse': 's', 'hanaHouse2': 's'}[k]
    yard_list.append((yard_rect(dict(x0=x0, z0=z0, x1=x1, z1=z1, face=f)), dict(name=k, face=f, x0=x0, z0=z0, x1=x1, z1=z1)))
YARD = unary_union([y for y, h in yard_list]).intersection(FREE.buffer(-.15)).difference(GRASSG.difference(unary_union([y for y, h in yard_list])))
YARD = unary_union([p for p in polys(YARD) if p.area > 6])

# =====================================================================
#  3. 地面
# =====================================================================
# ---- ジオラマの側面（外形の ふち）----
mb = MB('Terrain_edge')
ext = list(O.exterior.coords)
for i in range(len(ext) - 1):
    a, b = ext[i], ext[i + 1]
    mx, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; nx, nz = b[1] - a[1], -(b[0] - a[0]); l = math.hypot(nx, nz) or 1
    n = (nx, 0, nz) if not O.contains(Point(mx + nx / l * .05, mz + nz / l * .05)) else (-nx, 0, -nz)   # 外向き
    mb.face([(a[0], -4.0, a[1]), (b[0], -4.0, b[1]), (b[0], 0, b[1]), (a[0], 0, a[1])], tex='soil', n=n)
put(mb, 'Terrain')
# ---- 区画・芝生・土 ----
PARKG = unary_union([sbox(*WR(r)) for r in L.PARKING]).intersection(FREE)
PLAZA = unary_union([sbox(*WR(r)) for r in L.PLAZAS]).intersection(FREE).difference(YARD).difference(PARKG)
LOT = FREE.difference(GRASSG).difference(DIRTG).difference(PARK).difference(YARD).difference(PARKG).difference(PLAZA)
mb = MB('Terrain_plaza'); fill(mb, PLAZA, 0, tex='paving'); fill(mb, PARKG, 0, tex='asphalt'); put(mb, 'Sidewalks')
mb = MB('Terrain_lots'); fill(mb, LOT, 0, tex='lot'); put(mb, 'ResidentialAreas')
mb = MB('Terrain_grass'); fill(mb, FREE.intersection(GRASSG).difference(DIRTG).difference(PARK).difference(YARD), 0, tex='grass'); fill(mb, PARK, 0, tex='grass'); put(mb, 'Terrain')
mb = MB('Terrain_paths'); fill(mb, PATH, 0, tex='brick'); fill(mb, DPATH, 0, tex='dirt'); put(mb, 'Sidewalks')
# ---- 道路・歩道・縁石 ----
mb = MB('MainRoads_asphalt'); fill(mb, R_main, 0, tex='asphalt'); put(mb, 'MainRoads')
mb = MB('ResidentialRoads_asphalt'); fill(mb, R_res, 0, tex='asphalt'); put(mb, 'ResidentialRoads')
mb = MB('Sidewalks_paving'); fill(mb, SIDE, 0, tex='paving'); put(mb, 'Sidewalks')
mb = MB('Sidewalks_curb')
for p in polys(CURB):
    p = p.simplify(.02)
    for q in polys(p):
        flat(mb, rings(q), .12, col='#d9d4c8')
        for r in rings(q):
            for i in range(len(r) - 1):
                a, b = r[i], r[i + 1]
                if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-4: continue
                mx, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; nx, nz = b[1] - a[1], -(b[0] - a[0]); l = math.hypot(nx, nz)
                outp = Point(mx + nx / l * .03, mz + nz / l * .03)
                n = (nx, 0, nz) if not q.contains(outp) else (-nx, 0, -nz)
                mb.face([(a[0], 0, a[1]), (b[0], 0, b[1]), (b[0], .12, b[1]), (a[0], .12, a[1])], col='#c4beb1', n=n)
put(mb, 'Sidewalks')

# ---- 道路の白線・横断歩道・止まれ ----
WHITE = '#f4f3ee'
mb = MB('RoadMarkings')
def strip(mb, a, b, w, y=.012, col=WHITE):
    dx, dz = b[0] - a[0], b[1] - a[1]; l = math.hypot(dx, dz)
    if l < .05: return
    nx, nz = -dz / l * w / 2, dx / l * w / 2
    mb.face([(a[0] - nx, y, a[1] - nz), (b[0] - nx, y, b[1] - nz), (b[0] + nx, y, b[1] + nz), (a[0] + nx, y, a[1] + nz)], col=col, n=(0, 1, 0))
road_lines = [(n, k, LineString(WP(p)), w) for n, k, p, w in L.ROADS]
def others_union(skip, extra=2.0):
    return unary_union([ls.buffer(w / 2 + extra) for n, k, ls, w in road_lines if n != skip])
for name, kind, ls, w in road_lines:
    if kind == 'alley': continue
    oth = others_union(name, 1.2)
    clip = ls.intersection(O.buffer(-1)).difference(oth)
    if kind == 'main':
        for seg in lines(clip):                                     # 中央の点線
            L_ = seg.length; t = 0.0
            while t + 3 < L_:
                strip(mb, seg.interpolate(t).coords[0], seg.interpolate(t + 3).coords[0], .15); t += 6
    for side in (-1, 1):                                            # 外側線
        off = ls.offset_curve(side * (w / 2 - .35))
        for seg in lines(off.intersection(O.buffer(-1)).difference(oth)):
            c = list(seg.coords)
            for i in range(len(c) - 1): strip(mb, c[i], c[i + 1], .12)
# 交差点：横断歩道（主要道路と 住宅の道の太いもの）・止まれ
STOP_SIGNS = []
for i, (n1, k1, l1, w1) in enumerate(road_lines):
    for j, (n2, k2, l2, w2) in enumerate(road_lines):
        if i == j: continue
        inter = l1.intersection(l2)
        pts = [inter] if isinstance(inter, Point) else [g for g in getattr(inter, 'geoms', []) if isinstance(g, Point)]
        for P in pts:
            if not O.buffer(-3).contains(P): continue
            s0 = l1.project(P)
            for sgn in (-1, 1):
                d = w2 / 2 + 2.3; s = s0 + sgn * d
                if s < 1 or s > l1.length - 1: continue
                c = l1.interpolate(s); a = l1.interpolate(max(0, s - .5)); b = l1.interpolate(min(l1.length, s + .5))
                dx, dz = b.x - a.x, b.y - a.y; ll = math.hypot(dx, dz); ux, uz = dx / ll, dz / ll; nx, nz = -uz, ux
                if any(o[2].distance(c) < o[3] / 2 + .5 for o in road_lines if o[0] not in (n1, n2)): continue
                if k1 == 'main' or (k1 == 'res' and k2 == 'main') or w1 >= 5:
                    # しま模様（道の幅いっぱい・道の向きに 長さ 3m）
                    k = -w1 / 2 + .5
                    while k + .45 <= w1 / 2 - .4:
                        cx, cz = c.x + nx * (k + .225), c.y + nz * (k + .225)
                        strip(mb, (cx - ux * 1.5, cz - uz * 1.5), (cx + ux * 1.5, cz + uz * 1.5), .45, .013); k += .9
                if k1 != 'main' and k2 == 'main':
                    # 止まれ（停止線と 文字）
                    sl = s - sgn * 2.2
                    if 1 < sl < l1.length - 1:
                        q = l1.interpolate(sl)
                        strip(mb, (q.x - nx * (w1 / 2 - .4), q.y - nz * (w1 / 2 - .4)), (q.x + nx * (w1 / 2 - .4), q.y + nz * (w1 / 2 - .4)), .35, .013)
                        q2 = l1.interpolate(s - sgn * 4.6)
                        STOP_SIGNS.append((q2.x, q2.y, ux * -sgn, uz * -sgn, nx, nz, w1))
put(mb, 'MainRoads')
# 「止まれ」の文字（路面）とマンホール：すけるテクスチャ（ゲームで alphaTest にする）
def decal_tomare():
    im = Image.new('RGBA', (256, 512), (0, 0, 0, 0)); d = ImageDraw.Draw(im); f = KG.F(150)
    for k, ch in enumerate('れま止'): d.text((128, 90 + k * 160), ch, font=f, fill=(244, 243, 238, 255), anchor='mm')
    return im
def decal_manhole():
    im = Image.new('RGBA', (256, 256), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse([8, 8, 248, 248], fill=(86, 88, 92, 255)); d.ellipse([22, 22, 234, 234], fill=(122, 124, 128, 255))
    for k in range(-6, 7):
        d.line([(128 + k * 16 - 90, 40), (128 + k * 16 + 90, 216)], fill=(98, 100, 104, 255), width=5)
    d.ellipse([96, 96, 160, 160], fill=(108, 110, 114, 255)); d.text((128, 128), '風', font=KG.F(44), fill=(150, 152, 156, 255), anchor='mm')
    return im
def decal_gutter():
    im = Image.new('RGBA', (64, 256), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 63, 255], fill=(118, 116, 110, 255))
    for y in range(6, 256, 16): d.rectangle([10, y, 54, y + 8], fill=(60, 60, 58, 255))
    return im
TOMARE = KG.pic_mat('decal_tomare', decal_tomare(), alpha=True)
MANHOLE = KG.pic_mat('decal_manhole', decal_manhole(), alpha=True)
mb = MB('RoadDecals')
for (x, z, ux, uz, nx, nz, w) in STOP_SIGNS:
    # 文字の上が 交差点がわ（運転する人から読める向き）
    hw, hl = min(1.3, w / 2 - .5), 2.6
    p = lambda a, b: (x + nx * a + ux * b, .014, z + nz * a + uz * b)
    quad_uv(mb, [p(-hw, -hl), p(hw, -hl), p(hw, hl), p(-hw, hl)], TOMARE)
for name, kind, ls, w in road_lines:                              # マンホール
    if kind == 'alley': continue
    s = 9.0
    while s < ls.length - 5:
        c = ls.interpolate(s)
        if O.buffer(-2).contains(c) and not any(o[2].distance(c) < o[3] / 2 + 1 for o in road_lines if o[0] != name):
            r_ = .35; mb.face([(c.x - r_, .015, c.y + r_), (c.x + r_, .015, c.y + r_), (c.x + r_, .015, c.y - r_), (c.x - r_, .015, c.y - r_)], None, MANHOLE, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
        s += 31
put(mb, 'MainRoads')
# 側溝（住宅の道のはしの グレーチング）
GUTTER = KG.pic_mat('decal_gutter', decal_gutter(), alpha=True)
mb = MB('Gutters')
for name, kind, ls, w in road_lines:
    if kind != 'res': continue
    oth = others_union(name, .6)
    for side in (-1, 1):
        off = ls.offset_curve(side * (w / 2 - .17))
        for seg in lines(off.intersection(O.buffer(-1)).difference(oth).difference(Wfull.buffer(.5))):
            c = list(seg.coords)
            for i in range(len(c) - 1):
                a, b = c[i], c[i + 1]; dx, dz = b[0] - a[0], b[1] - a[1]; l = math.hypot(dx, dz)
                if l < .3: continue
                nx, nz = -dz / l * .15, dx / l * .15; t = 0
                while t < l - .05:
                    t2 = min(l, t + 1.0); pa = (a[0] + dx * t / l, a[1] + dz * t / l); pb = (a[0] + dx * t2 / l, a[1] + dz * t2 / l)
                    mb.face([(pa[0] - nx, .011, pa[1] - nz), (pb[0] - nx, .011, pb[1] - nz), (pb[0] + nx, .011, pb[1] + nz), (pa[0] + nx, .011, pa[1] + nz)], None, GUTTER,
                            uvs=[(0, 0), (0, (t2 - t)), (1, (t2 - t)), (1, 0)], n=(0, 1, 0))
                    t = t2
put(mb, 'ResidentialRoads')

# ---- 水路：水面・側壁・橋・さく ----
mb = MB('Waterways_water'); fill(mb, Wfull, -.55, tex='water'); put(mb, 'Waterways')
mb = MB('Waterways_walls')
for p in polys(Wfull):
    for r in rings(p):
        for i in range(len(r) - 1):
            a, b = r[i], r[i + 1]
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-4: continue
            mx, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; nx, nz = b[1] - a[1], -(b[0] - a[0]); l = math.hypot(nx, nz)
            inside = p.contains(Point(mx + nx / l * .05, mz + nz / l * .05))
            n = (nx, 0, nz) if inside else (-nx, 0, -nz)           # 水の がわを向く
            mb.face([(a[0], -1.4, a[1]), (b[0], -1.4, b[1]), (b[0], 0, b[1]), (a[0], 0, a[1])], tex='concrete', n=n)
put(mb, 'Waterways')
mb = MB('Bridges_deck')
for p in polys(BRIDGE): prism(mb, [c for c in p.exterior.coords][:-1], -.45, -.005, tex='concrete', top=False)
put(mb, 'Bridges')
# さく：水路のふち（道の上は 橋の らんかん）。当たり判定もここで
mb = MB('Waterways_fence'); mbb = MB('Bridges_railing')
for a, b in boundary_segs(Wt):
    l = math.hypot(b[0] - a[0], b[1] - a[1])
    if l < .05: continue
    mid = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    onroad = R_all.buffer(.05).contains(mid)
    colseg(a, b, .15, 1.2, '橋の らんかん' if onroad else '水路のさく')
    if onroad:
        # 橋の らんかん：低いコンクリート＋白い手すり
        nx, nz = (b[1] - a[1]) / l * .12, -(b[0] - a[0]) / l * .12
        prism(mbb, [(a[0] - nx, a[1] - nz), (b[0] - nx, b[1] - nz), (b[0] + nx, b[1] + nz), (a[0] + nx, a[1] + nz)], 0, .45, col='#d8d3c6')
        n = max(1, int(l / 1.2))
        for k in range(n + 1):
            t = k / n; x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t; bar(mbb, (x, .45, z), (x, 1.05, z), .04, '#eef0f2')
        bar(mbb, (a[0], 1.05, a[1]), (b[0], 1.05, b[1]), .05, '#eef0f2')
    else:
        n = max(1, int(l / 1.8))
        for k in range(n + 1):
            t = k / n; x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t; bar(mb, (x, 0, z), (x, 1.0, z), .035, '#5d8a6a')
        for y in (.5, 1.0): bar(mb, (a[0], y, a[1]), (b[0], y, b[1]), .028, '#5d8a6a')
put(mb, 'Waterways'); put(mbb, 'Bridges')

# 外形の当たり判定（出口もここで ふさぐ：まだ行けない）
for i in range(len(ext) - 1): colseg(ext[i], ext[i + 1], .2, 9, 'マップのはし')

# =====================================================================
#  4. 家（1けんずつ）・庭の塀と門・芝生
# =====================================================================
from kazami_bldg import *
BLD = []                                                          # 建物の外形（木や電柱を置かないところ）
def add_building_info(name, x0, z0, x1, z1, color, kind='house', h=8.0, note=None):
    BLD.append(sbox(x0, z0, x1, z1)); colbox(x0, z0, x1, z1, h, note or name)
    MINI['buildings'].append([round(x0, 1), round(z0, 1), round(x1, 1), round(z1, 1), color, kind])
def check_clear(name, x0, z0, x1, z1):
    g = sbox(x0, z0, x1, z1)
    if g.intersects(R_all.buffer(.6)) or g.intersects(Wfull): print('！ 道か水路に かかっている：', name)
for h in houses:
    W_, D_ = (h['x1'] - h['x0'], h['z1'] - h['z0'])
    if h['face'] in 'ew': W_, D_ = D_, W_
    cx, cz = (h['x0'] + h['x1']) / 2, (h['z0'] + h['z1']) / 2
    check_clear(h['name'], h['x0'], h['z0'], h['x1'], h['z1'])
    hroot = empty(h['name'], GRP['Houses'])
    mb = MB(h['name'] + '_mesh'); lod = MB(h['name'] + '_LOD')
    Hh, top = house(mb, cx, cz, W_ - .2, D_ - .2, h['typ'], h['roof'], h['wall'], h['face'], random.Random(h['i'] * 7 + 1), lod)
    put(mb, 'Houses', hroot); put(lod, 'Houses', hroot)
    add_building_info(h['name'], h['x0'] + .1, h['z0'] + .1, h['x1'] - .1, h['z1'] - .1, ROOFCOL.get(h['roof'], '#888888'), 'house', top)
    h['top'] = top

# ---- 庭の塀（ブロック塀・生垣・白いさく）と門 ----
WALL_STYLE = ['block', 'hedge', 'fence', 'block', 'hedge']
def gate_point(h):
    cx, cz = (h['x0'] + h['x1']) / 2, (h['z0'] + h['z1']) / 2
    d = {'s': (0, 1), 'n': (0, -1), 'e': (1, 0), 'w': (-1, 0)}[h['face']]
    far = (cx + d[0] * 30, cz + d[1] * 30)
    ray = LineString([(cx, cz), far]); inter = ray.intersection(YARD.boundary)
    pts = [g for g in (inter.geoms if hasattr(inter, 'geoms') else [inter]) if isinstance(g, Point)]
    if not pts: return None
    return min(pts, key=lambda p: p.distance(Point(cx, cz)))
gates = []
for y_, h in yard_list:
    gp = gate_point(h)
    if gp is not None: gates.append((gp, h))
gate_holes = unary_union([gp.buffer(.75) for gp, h in gates]) if gates else Polygon()
def style_at(p):
    best = None; bd = 1e9
    for y_, h in yard_list:
        d = y_.distance(p)
        if d < bd: bd = d; best = h
    i = best.get('i', 3) if best else 0
    return WALL_STYLE[i % len(WALL_STYLE)]
mb = MB('ResidentialAreas_walls')
for p in polys(YARD):
    for r in rings(p):
        ln = LineString(r).difference(gate_holes)
        for a, b in seglist(ln):
            l = math.hypot(b[0] - a[0], b[1] - a[1])
            if l < .05: continue
            st = style_at(Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
            ux, uz = (b[0] - a[0]) / l, (b[1] - a[1]) / l; nx, nz = -uz, ux
            if st == 'block':
                t = .08; q = [(a[0] - nx * t, a[1] - nz * t), (b[0] - nx * t, b[1] - nz * t), (b[0] + nx * t, b[1] + nz * t), (a[0] + nx * t, a[1] + nz * t)]
                prism(mb, q, 0, 1.0, col='#c3bfb4'); t2 = .11
                prism(mb, [(a[0] - nx * t2, a[1] - nz * t2), (b[0] - nx * t2, b[1] - nz * t2), (b[0] + nx * t2, b[1] + nz * t2), (a[0] + nx * t2, a[1] + nz * t2)], 1.0, 1.08, col='#a9a59b')
                k = .4
                while k < l:                                         # ブロックの目地
                    x, z = a[0] + ux * k, a[1] + uz * k
                    for s_ in (-1, 1): mb.face([(x - ux * .01 + s_ * nx * (t + .002), .05, z - uz * .01 + s_ * nz * (t + .002)), (x + ux * .01 + s_ * nx * (t + .002), .05, z + uz * .01 + s_ * nz * (t + .002)),
                                                (x + ux * .01 + s_ * nx * (t + .002), .98, z + uz * .01 + s_ * nz * (t + .002)), (x - ux * .01 + s_ * nx * (t + .002), .98, z - uz * .01 + s_ * nz * (t + .002))], col='#aaa69c', n=(s_ * nx, 0, s_ * nz))
                    k += .4
                colseg(a, b, .15, 1.1, 'ブロック塀')
            elif st == 'hedge':
                t = .3; q = [(a[0] - nx * t, a[1] - nz * t), (b[0] - nx * t, b[1] - nz * t), (b[0] + nx * t, b[1] + nz * t), (a[0] + nx * t, a[1] + nz * t)]
                prism(mb, q, 0, .25, col='#b5b0a6'); prism(mb, [(x * 1, z) for x, z in q], .25, 1.05, col='#4f8f45')
                t2 = .24; prism(mb, [(a[0] - nx * t2, a[1] - nz * t2), (b[0] - nx * t2, b[1] - nz * t2), (b[0] + nx * t2, b[1] + nz * t2), (a[0] + nx * t2, a[1] + nz * t2)], 1.05, 1.18, col='#6aab55')
                colseg(a, b, .32, 1.2, '生垣')
            else:
                t = .1; q = [(a[0] - nx * t, a[1] - nz * t), (b[0] - nx * t, b[1] - nz * t), (b[0] + nx * t, b[1] + nz * t), (a[0] + nx * t, a[1] + nz * t)]
                prism(mb, q, 0, .35, col='#c8c3b8')
                n = max(1, int(l / .25))
                for k in range(n + 1):
                    x, z = a[0] + ux * l * k / n, a[1] + uz * l * k / n; box(mb, x - .035, x + .035, .35, 1.05, z - .035, z + .035, col='#f4f2ec', top=True)
                for yy in (.55, .95): bar(mb, (a[0], yy, a[1]), (b[0], yy, b[1]), .025, '#f4f2ec', 4)
                colseg(a, b, .14, 1.1, 'さく')
# 門柱・ポスト・表札
for gp, h in gates:
    cx, cz = (h['x0'] + h['x1']) / 2, (h['z0'] + h['z1']) / 2
    d = {'s': (0, 1), 'n': (0, -1), 'e': (1, 0), 'w': (-1, 0)}[h['face']]; tx, tz = -d[1], d[0]
    for s_ in (-1, 1):
        px, pz = gp.x + tx * s_ * .78, gp.y + tz * s_ * .78
        box(mb, px - .18, px + .18, 0, 1.25, pz - .18, pz + .18, col='#d9d2c2'); box(mb, px - .21, px + .21, 1.25, 1.32, pz - .21, pz + .21, col='#9b958a')
        colcircle(px, pz, .25, 1.3, '門柱')
    px, pz = gp.x + tx * .78 + d[0] * .2, gp.y + tz * .78 + d[1] * .2
    box(mb, px - .14, px + .14, .75, 1.08, pz - .06, pz + .1, col=random.Random(h.get('i', 1)).choice(['#c0392b', '#2f6fb8', '#3a3a3a', '#d6a23a']))   # ポスト
    # 門から玄関への 小道（石だたみ）
    ex, ez = cx + d[0] * ((h['x1'] - h['x0']) / 2 if d[0] else (h['z1'] - h['z0']) / 2), cz + d[1] * ((h['x1'] - h['x0']) / 2 if d[0] else (h['z1'] - h['z0']) / 2)
    for k in range(5):
        t = (k + .5) / 5; x, z = gp.x + (ex - gp.x) * t, gp.y + (ez - gp.y) * t
        box(mb, x - .32, x + .32, 0, .03, z - .32, z + .32, col='#cfc8b8')
put(mb, 'ResidentialAreas')
# 庭の芝生と 植木ばち
mb = MB('ResidentialAreas_yards')
fill(mb, YARD, 0, tex='grass')                                      # 家の下も しく（半透明のとき 空が見えないように）
put(mb, 'ResidentialAreas')

# =====================================================================
#  5. 施設
# =====================================================================
FACR = {}
def fac(name):
    if name not in FACR: FACR[name] = fit(*WR(L.FACILITIES[name]), name, 6.0) if name not in ('ground', 'busstop') else WR(L.FACILITIES[name])
    return FACR[name]
def rect_center(r): return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, r[2] - r[0], r[3] - r[1])
def sign_board(xf, fr, u, y, w, h, text, bg, fg, border=None, sub=None, d=.06, light=True):
    """かべに 看板（文字は ラノベPOP v2）"""
    key = KG.sign_mat(text, w, h, bg, fg, border, sub)
    panel(xf, fr, u - w / 2 - .06, u + w / 2 + .06, y - .06, y + h + .06, 0, d, '#3d3a36')
    P = lambda uu, yy: wp(fr, uu, yy, d + .005)
    xf.face([P(u - w / 2, y), P(u + w / 2, y), P(u + w / 2, y + h), P(u - w / 2, y + h)], None, key, uvs=[(0, 0), (1, 0), (1, 1), (0, 1)], n=fr[2])
    return key
def awning(xf, fr, u0, u1, y, depth, c1, c2, n=8, drop=.35):
    """しま模様の 日よけ（ななめ）"""
    w = (u1 - u0) / n
    for k in range(n):
        a, b = u0 + k * w, u0 + (k + 1) * w; c = c1 if k % 2 == 0 else c2
        xf.face([wp(fr, a, y - drop, depth), wp(fr, b, y - drop, depth), wp(fr, b, y, 0), wp(fr, a, y, 0)], col=c, n=(fr[2][0], 1, fr[2][2]))
        xf.face([wp(fr, a, y - drop - .3, depth), wp(fr, b, y - drop - .3, depth), wp(fr, b, y - drop, depth), wp(fr, a, y - drop, depth)], col=c, n=fr[2])
        xf.face([wp(fr, b, y - drop, depth), wp(fr, a, y - drop, depth), wp(fr, a, y, 0), wp(fr, b, y, 0)], col='#e8e2d6', n=(-fr[2][0], -1, -fr[2][2]))
def shop_front(xf, fr, u0, u1, y0, y1, frame='#4a4540', clear=True):
    """お店の 大きなガラスの前面（中が見える）"""
    panel(xf, fr, u0 - .1, u1 + .1, y0, y0 + .12, 0, .1, frame)
    panel(xf, fr, u0 - .1, u1 + .1, y1 - .08, y1 + .04, 0, .1, frame)
    n = max(2, int((u1 - u0) / 1.6))
    for k in range(n + 1): u = u0 + (u1 - u0) * k / n; panel(xf, fr, u - .04, u + .04, y0, y1, 0, .1, frame)
    P = lambda uu, yy: wp(fr, uu, yy, .05)
    xf.face([P(u0, y0 + .12), P(u1, y0 + .12), P(u1, y1 - .08), P(u0, y1 - .08)], None, 'clear' if clear else 'glass', uvs=[(0, 0), (1, 0), (1, 1), (0, 1)], n=fr[2])
def interior(xf, W, D, y0, h, shelves=3, cols=('#e8564a', '#f2c94c', '#6fbf5a', '#5a9ad6', '#f29b4c'), counter=True, rnd_=None):
    """窓から見える 店の中（床・おくのかべ・たな・レジ・天井の明かり）"""
    r_ = rnd_ or random.Random(3)
    box(xf, -W / 2 + .15, W / 2 - .15, y0, y0 + .02, -D / 2 + .15, D / 2 - .15, col='#e9e6de', sides='')
    for k in range(shelves):
        z = -D / 2 + 1.2 + k * (D - 2.6) / max(1, shelves - 1) if shelves > 1 else 0
        x0, x1 = -W / 2 + 1.2, W / 2 - 2.6
        box(xf, x0, x1, y0, y0 + 1.5, z - .3, z + .3, col='#d8d6d0')
        for lvl in range(3):
            yy = y0 + .35 + lvl * .4; x = x0 + .05
            while x < x1 - .25:
                w = r_.uniform(.18, .4); c = r_.choice(cols)
                for s_ in (-1, 1): box(xf, x, x + w - .03, yy, yy + .28, z + s_ * .3, z + s_ * .36, col=c, top=True)
                x += w
    if counter: box(xf, W / 2 - 2.2, W / 2 - .6, y0, y0 + 1.0, D / 2 - 2.6, D / 2 - 1.8, col='#c9a26b')
    for k in range(3): box(xf, -W / 3 + k * W / 3 - .8, -W / 3 + k * W / 3 + .8, y0 + h - .12, y0 + h - .06, -.2, .2, None, 'lamp')
    xf.face([(-W / 2 + .14, y0, -D / 2 + .14), (W / 2 - .14, y0, -D / 2 + .14), (W / 2 - .14, y0 + h, -D / 2 + .14), (-W / 2 + .14, y0 + h, -D / 2 + .14)], col='#f4f2ec', n=(0, 0, 1))
def vending(mb, x, z, ang, col='#d93a3a'):
    xf = XF(mb, x, z, ang)
    box(xf, -.5, .5, 0, 1.85, -.35, .35, col=col)
    fr = wall_frame('+z', 1.0, .7)
    panel(xf, fr, -.42, .42, 1.0, 1.7, 0, .02, None, 'neon')
    for r_ in range(3):
        for c in range(6): panel(xf, fr, -.36 + c * .13, -.27 + c * .13, 1.1 + r_ * .2, 1.24 + r_ * .2, .02, .06, ['#e44', '#4a4', '#48d', '#fa3', '#eee', '#a4d'][(c + r_) % 6])
    panel(xf, fr, -.3, .3, .15, .35, 0, .08, '#2b2b2b')
    colbox(x - .55, z - .55, x + .55, z + .55, 1.9, '自動販売機')
def lot_fence(mb, ring_pts, gaps=(), h=1.8, col='#4f7d5c', note='フェンス', step=2.4):
    """金あみのフェンス（school など）：点の列に そって。gaps は (x, z, はば) のあな"""
    ln = LineString(ring_pts)
    if gaps: ln = ln.difference(unary_union([Point(g[0], g[1]).buffer(g[2] / 2) for g in gaps]))
    for a, b in seglist(ln):
        l = math.hypot(b[0] - a[0], b[1] - a[1])
        if l < .05: continue
        n = max(1, int(l / step))
        for k in range(n + 1):
            t = k / n; x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t; cyl(mb, x, 0, z, .045, h, col, seg=6, cap=True)
        for yy in (.1, h * .5, h - .03): bar(mb, (a[0], yy, a[1]), (b[0], yy, b[1]), .025, col, 4)
        ux, uz = (b[0] - a[0]) / l, (b[1] - a[1]) / l; nx, nz = -uz * .01, ux * .01
        for s_ in (1, -1):                                         # あみ（すけない 板で かわりに：うすい色の面）
            mb.face([(a[0] + nx * s_, .1, a[1] + nz * s_), (b[0] + nx * s_, .1, b[1] + nz * s_), (b[0] + nx * s_, h - .03, b[1] + nz * s_), (a[0] + nx * s_, h - .03, a[1] + nz * s_)], None, 'pic:fencenet', uvs=[(0, 0), (l / 1.0, 0), (l / 1.0, h), (0, h)], n=(nx * s_, 0, nz * s_))
        colseg(a, b, .1, h, note)
def fencenet_img():
    im = Image.new('RGBA', (64, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k in range(-64, 128, 16): d.line([(k, 0), (k + 64, 64)], fill=(70, 120, 86, 255), width=2); d.line([(k + 64, 0), (k, 64)], fill=(70, 120, 86, 255), width=2)
    return im
KG.pic_mat('fencenet', fencenet_img(), alpha=True)

# ---- 風見第一小学校（3階建て）・体育館・プール・校庭 ----
x0, z0, x1, z1 = fac('school'); cx, cz, Ws, Ds = rect_center((x0, z0, x1, z1)); check_clear('school', x0, z0, x1, z1)
mb = MB('KazamiElementarySchool_main'); xf = XF(mb, cx, cz, 0)
FHs = 3.7; Hs = .5 + FHs * 3
SW = '#efe2c4'; SB = '#dcc9a2'
box(xf, -Ws / 2, Ws / 2, 0, .5, -Ds / 2, Ds / 2, col='#a69f92', top=False)
box(xf, -Ws / 2, Ws / 2, .5, Hs, -Ds / 2, Ds / 2, col=SW, top=False)
flat_roof(xf, Ws, Ds, Hs, SW, cap='#cbbd9d', top='#9ea7a6', par=.9)
fr = wall_frame('+z', Ws, Ds); frb = wall_frame('-z', Ws, Ds)
for k in range(1, 4): panel(xf, fr, -Ws / 2, Ws / 2, .5 + k * FHs - .12, .5 + k * FHs + .05, 0, .35, SB); panel(xf, frb, -Ws / 2, Ws / 2, .5 + k * FHs - .12, .5 + k * FHs + .05, 0, .25, SB)
TW = 7.0                                                           # まんなかの 玄関と 時計の塔
for fl in range(3):
    y = .5 + fl * FHs + .95
    for f_ in (fr, frb):
        u = -Ws / 2 + 1.4
        while u < Ws / 2 - 1.4:
            if abs(u) > TW / 2 + 1.0 or f_ is frb:
                window(xf, f_, u, y, 2.3, 1.9, frame='#cfe0ea', sill=False, curtain='#f4ecd0' if rnd.random() < .3 else None)
            u += 3.0
    for s_ in ('+x', '-x'): win_row(xf, wall_frame(s_, Ws, Ds), Ds, y, 1.9, 4, w=2.0)
xt = XF(mb, cx, cz + Ds / 2 + .6, 0)                               # 塔（前に すこし出す）
box(xt, -TW / 2, TW / 2, 0, Hs + 2.6, -1.2, 1.2, col='#f6ecd2', top=True)
box(xt, -TW / 2 - .1, TW / 2 + .1, Hs + 2.6, Hs + 2.8, -1.3, 1.3, col='#cbbd9d')
ft = wall_frame('+z', TW, 2.4)
for fl in (1, 2): window(xt, ft, 0, .5 + fl * FHs + .8, 3.6, 2.2, frame='#cfe0ea', sill=False)
cyl(xt, 0, Hs + .7, 1.22, 1.05, .12, '#3a3a3a', seg=24, cap=False) if False else None
clock_y = Hs + 1.3
for rr, c in ((1.0, '#6a5c48'), (.86, '#fbfaf3')):
    pts = [(math.cos(k / 24 * math.tau) * rr, clock_y + math.sin(k / 24 * math.tau) * rr, 1.21 + (1.0 - rr) * .05) for k in range(24)]
    xt.face(pts, col=c, n=(0, 0, 1))
for k in range(12):
    a = k / 12 * math.tau; px, py = math.sin(a) * .72, clock_y + math.cos(a) * .72
    xt.face([(px - .04, py - .08, 1.275), (px + .04, py - .08, 1.275), (px + .04, py + .08, 1.275), (px - .04, py + .08, 1.275)], col='#3a3a3a', n=(0, 0, 1))
bar(xt, (0, clock_y, 1.28), (0, clock_y + .55, 1.28), .04, '#2b2b2b', 4); bar(xt, (0, clock_y, 1.29), (.38, clock_y - .2, 1.29), .04, '#2b2b2b', 4)
# 玄関：ひさし・ガラスのとびら・階段
panel(xt, ft, -TW / 2 - .6, TW / 2 + .6, 3.2, 3.5, 0, 2.6, '#d9d3c4')
for s_ in (-1, 1): bar(xt, wp(ft, s_ * (TW / 2 + .3), 0, 2.4), wp(ft, s_ * (TW / 2 + .3), 3.2, 2.4), .14, '#efeadf', 10)
for k in range(4): panel(xt, ft, -2.6 + k * 1.3, -1.4 + k * 1.3, .5, 2.9, 0, .06, '#9fb6c2'); glassq(xt, ft, -2.5 + k * 1.3, -1.5 + k * 1.3, .6, 2.8, .065)
for k in range(3): panel(xt, ft, -TW / 2 - .6, TW / 2 + .6, 0, .5 - k * .16, 0, 1.2 + k * .55, '#cfc9bc')
sign_board(xt, ft, 0, Hs + .3, 5.0, .75, '風見第一小学校', '#f6f1e3', '#1d2f5a', '#1d2f5a')
# 屋上：フェンス・給水タンク・室外機
for (a, b) in [((-Ws / 2 + .3, -Ds / 2 + .3), (Ws / 2 - .3, -Ds / 2 + .3)), ((Ws / 2 - .3, -Ds / 2 + .3), (Ws / 2 - .3, Ds / 2 - .3)), ((Ws / 2 - .3, Ds / 2 - .3), (-Ws / 2 + .3, Ds / 2 - .3)), ((-Ws / 2 + .3, Ds / 2 - .3), (-Ws / 2 + .3, -Ds / 2 + .3))]:
    A, B = xf.P((a[0], 0, a[1])), xf.P((b[0], 0, b[1])); l = math.hypot(B[0] - A[0], B[2] - A[2]); n = int(l / 2)
    for k in range(n + 1): t = k / n; bar(mb, (A[0] + (B[0] - A[0]) * t, Hs + .9, A[2] + (B[2] - A[2]) * t), (A[0] + (B[0] - A[0]) * t, Hs + 2.1, A[2] + (B[2] - A[2]) * t), .03, '#5d8a6a', 4)
    bar(mb, (A[0], Hs + 2.1, A[2]), (B[0], Hs + 2.1, B[2]), .035, '#5d8a6a', 4)
cyl(mb, cx + Ws / 2 - 5, Hs, cz - 3, 1.3, 2.4, '#d9dfe2', seg=16); cyl(mb, cx + Ws / 2 - 5, Hs + 2.4, cz - 3, 1.3, .3, '#b7c0c4', seg=16, r2=.2)
for k in range(4): box(mb, cx - Ws / 2 + 3 + k * 1.6, cx - Ws / 2 + 4.2 + k * 1.6, Hs, Hs + .9, cz - 4, cz - 3.2, col='#e8e7e2')
box(mb, cx - 6, cx - 1, Hs, Hs + 2.6, cz - Ds / 2 + 1.5, cz - Ds / 2 + 5, col=SW); box(mb, cx - 6.2, cx - .8, Hs + 2.6, Hs + 2.8, cz - Ds / 2 + 1.3, cz - Ds / 2 + 5.2, col='#cbbd9d')
put(mb, 'KazamiElementarySchool')
add_building_info('風見第一小学校', x0, z0, x1, z1 + 1.8, '#e8d6b0', 'school', Hs + 2.8)
colbox(cx - TW / 2 - .7, z1, cx + TW / 2 + .7, z1 + 3.3, 3.5, '風見第一小学校の玄関')
MINI['icons'].append(['school', round(cx, 1), round(cz, 1)])

x0, z0, x1, z1 = fac('gym'); cx, cz, Wg, Dg = rect_center((x0, z0, x1, z1)); check_clear('gym', x0, z0, x1, z1)
mb = MB('Gymnasium_main'); xf = XF(mb, cx, cz, 90); Wl, Dl = Dg, Wg     # 入口は 東（学校の通路がわ）
box(xf, -Wl / 2, Wl / 2, 0, .4, -Dl / 2, Dl / 2, col='#a69f92', top=False)
box(xf, -Wl / 2, Wl / 2, .4, 7.2, -Dl / 2, Dl / 2, col='#e6dcc8', top=False)
gable_roof(xf, Wl, Dl, 7.2, 'g', '#e6dcc8', pitch=.28, ov=.6, ovx=.5)
for s_ in ('+x', '-x'):
    f_ = wall_frame(s_, Wl, Dl)
    u = -Dl / 2 + 1.2
    while u < Dl / 2 - 1:
        window(xf, f_, u, 4.6, 1.5, 1.8, frame='#cfe0ea', sill=False); window(xf, f_, u, 1.2, 1.5, 1.1, frame='#cfe0ea', sill=False, grid=False); u += 2.1
f_ = wall_frame('+z', Wl, Dl)
panel(xf, f_, -2.2, 2.2, .4, 3.2, 0, .06, '#7d8f9a'); glassq(xf, f_, -2.0, 2.0, .5, 3.0, .065)
panel(xf, f_, -3.0, 3.0, 3.4, 3.6, 0, 1.8, '#d9d3c4')
for k in range(2): panel(xf, f_, -2.6, 2.6, 0, .4 - k * .2, 0, .8 + k * .5, '#cfc9bc')
sign_board(xf, f_, 0, 4.0, 2.6, .6, '体育館', '#f6f1e3', '#1d2f5a', '#1d2f5a')
put(mb, 'Gymnasium')
add_building_info('体育館', x0, z0, x1, z1, '#647c90', 'gym', 9.2)

x0, z0, x1, z1 = fac('pool'); cx, cz, Wp, Dp = rect_center((x0, z0, x1, z1)); check_clear('pool', x0, z0, x1, z1)
mb = MB('SwimmingPool_main')
box(mb, x0, x1, 0, .45, z0, z1, col='#e9e6de')                         # プールサイド（すこし高い）
px0, px1, pz0, pz1 = x0 + 1.6, x1 - 1.6, z0 + 1.6, z1 - 1.6
box(mb, px0, px1, .2, .2, pz0, pz1, col='#e9e6de', sides='', top=False)
# 水（すこし ひくい）とプールの かべ
quad_uv(mb, [(px0, .25, pz1), (px1, .25, pz1), (px1, .25, pz0), (px0, .25, pz0)], 'water', uvs=[(px0 / 4, -pz1 / 4), (px1 / 4, -pz1 / 4), (px1 / 4, -pz0 / 4), (px0 / 4, -pz0 / 4)])
for (a, b) in [((px0, pz0), (px1, pz0)), ((px1, pz0), (px1, pz1)), ((px1, pz1), (px0, pz1)), ((px0, pz1), (px0, pz0))]:
    mx, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2; n = ((cx - mx), 0, (cz - mz))
    mb.face([(a[0], .25, a[1]), (b[0], .25, b[1]), (b[0], .46, b[1]), (a[0], .46, a[1])], col='#79c7e6', n=n)
# プールサイドの上面に 穴をあける（4つの帯で）
for (a0, a1, b0, b1) in [(x0, x1, z0, pz0), (x0, x1, pz1, z1), (x0, px0, pz0, pz1), (px1, x1, pz0, pz1)]:
    mb.face([(a0, .46, b1), (a1, .46, b1), (a1, .46, b0), (a0, .46, b0)], col='#f1efe9', n=(0, 1, 0))
nl = 6
for k in range(1, nl):                                                    # コースロープ
    z = pz0 + (pz1 - pz0) * k / nl
    for j in range(int((px1 - px0) / .3)):
        x = px0 + j * .3; ball(mb, x + .15, .28, z, .1, .06, .1, ['#e04848', '#f4f2ec', '#2f6fb8'][(j // 3) % 3], seg=6, rings=4)
for k in range(nl):
    z = pz0 + (pz1 - pz0) * (k + .5) / nl; box(mb, px0 + .5, px1 - .5, .251, .253, z - .08, z + .08, col='#2f5f9a', sides='')
    box(mb, px0 - .7, px0 - .1, .45, .8, z - .3, z + .3, col='#f4f2ec')   # スタート台
put(mb, 'SwimmingPool')
mb = MB('SwimmingPool_fence')
lot_fence(mb, [(x0, z0), (x1, z0), (x1, z1), (x0, z1), (x0, z0)], h=1.8, note='プールのフェンス')
put(mb, 'SwimmingPool')
colbox(x0, z0, x1, z1, 1.9, 'プール'); BLD.append(sbox(x0, z0, x1, z1))
MINI['buildings'].append([round(x0, 1), round(z0, 1), round(x1, 1), round(z1, 1), '#79c7e6', 'pool'])

x0, z0, x1, z1 = fac('ground'); cx, cz, Wgr, Dgr = rect_center((x0, z0, x1, z1))
mb = MB('SchoolGround_main')
fill(mb, DIRTG, 0, tex='dirt') if False else None
# トラック（白線 4レーン）：直線の半分 Lh、内側の半径 Rr
Lh, Rr, lane = Wgr / 2 - 12, 7.0, 1.0
tcx, tcz = cx + .5, cz + 1.0
def track_line(rr, w=.09):
    pts = []
    for k in range(25): a = math.pi / 2 + k / 24 * math.pi; pts.append((tcx - Lh + math.cos(a) * rr, tcz + math.sin(a) * rr))
    for k in range(25): a = -math.pi / 2 + k / 24 * math.pi; pts.append((tcx + Lh + math.cos(a) * rr, tcz + math.sin(a) * rr))
    pts.append(pts[0])
    for i in range(len(pts) - 1): strip(mb, pts[i], pts[i + 1], w, .012)
for k in range(5): track_line(Rr + k * lane)
strip(mb, (tcx, tcz + Rr), (tcx, tcz + Rr + 4 * lane), .12, .012)
# 朝礼台（北のはし）・鉄棒（東）
sx, sz = cx - 4, z0 + 2.5
box(mb, sx - 1.8, sx + 1.8, 0, 1.1, sz - 1.1, sz + 1.1, col='#c9c4b8'); box(mb, sx - 1.75, sx + 1.75, 1.1, 1.14, sz - 1.05, sz + 1.05, col='#2f6fb8')
for k in range(3): box(mb, sx - .7, sx + .7, 0, .28 * (k + 1), sz + 1.1 + (2 - k) * .3, sz + 1.1 + (3 - k) * .3, col='#c9c4b8')
colbox(sx - 1.85, sz - 1.15, sx + 1.85, sz + 2.05, 1.2, '朝礼台')
for k, hh in enumerate((.9, 1.15, 1.4)):
    xa = x1 - 9 + k * 2.2; xb = xa + 1.8; zz = z0 + 2.2
    for xx in (xa, xb): cyl(mb, xx, 0, zz, .06, hh, ['#e04848', '#2f6fb8', '#e8c030'][k], seg=8); colcircle(xx, zz, .12, hh, '鉄棒')
    bar(mb, (xa, hh, zz), (xb, hh, zz), .025, '#b8bcc0', 6)
put(mb, 'SchoolGround')
mb = MB('SchoolGround_dirt'); fill(mb, DIRTG, .002, tex='dirt'); put(mb, 'SchoolGround')
MINI['buildings'].append([round(x0, 1), round(z0, 1), round(x1, 1), round(z1, 1), '#e6c48c', 'ground'])

# 学校のまわりの フェンス（正門・東門は あけておく）
SCH = Polygon(WP([(165, 150), (452, 150), (452, 268), (452, 300), (566, 300), (566, 452), (165, 452)])).intersection(O.buffer(-.6)).difference(R_all.buffer(1.7)).difference(PATH.buffer(.2))
mb = MB('KazamiElementarySchool_fence')
gw = [W((320, 452)) + (5.0,), W((540, 452)) + (4.0,), W((462, 300)) + (4.0,)]
for p in polys(SCH):
    lot_fence(mb, list(p.exterior.coords), gaps=gw, h=2.0, note='学校のフェンス')
put(mb, 'KazamiElementarySchool')
# 正門の 門柱と 校名
gx, gz = W((320, 452)); gx2 = gx
mb = MB('KazamiElementarySchool_gate')
for s_ in (-1, 1):
    box(mb, gx + s_ * 2.9 - .4, gx + s_ * 2.9 + .4, 0, 2.0, gz - .4 - 1.6, gz + .4 - 1.6, col='#c8c2b4'); colcircle(gx + s_ * 2.9, gz - 1.6, .5, 2, '校門')
xg = XF(mb, gx - 2.9, gz - 1.6, 0); sign_board(xg, wall_frame('+z', .8, .8), 0, .5, .45, 1.3, '風見第一小学校', '#f4f1e8', '#1d1b19', None, d=.02)
put(mb, 'KazamiElementarySchool')

# ---- 店や施設の 共通の作り：箱の建物（ローカル W×D、正面 +z）----
def facility(group, key, face, floors, wall, roof, sign=None, fh=3.0, shop=False, roofkind='flat', parapet=.5, objname=None, mini_col=None, kind='shop', icon=None):
    x0, z0, x1, z1 = fac(key); cx, cz, wx, dz = rect_center((x0, z0, x1, z1)); check_clear(key, x0, z0, x1, z1)
    Wl, Dl = (wx, dz) if face in 'sn' else (dz, wx)
    mb = MB(objname or (group + '_main')); xf = XF(mb, cx, cz, FACE_ANG[face])
    H = .35 + floors * fh
    box(xf, -Wl / 2, Wl / 2, 0, .35, -Dl / 2, Dl / 2, col=FOUND, top=False)
    box(xf, -Wl / 2, Wl / 2, .35, H, -Dl / 2, Dl / 2, col=wall, top=False, sides=['-z', '+x', '-x'] if shop else 'all')
    if roofkind == 'flat': top = flat_roof(xf, Wl, Dl, H, wall, par=parapet)
    elif roofkind == 'gable': top = gable_roof(xf, Wl, Dl, H, roof, wall, pitch=.45)
    elif roofkind == 'hip': top = hip_roof(xf, Wl, Dl, H, roof, pitch=.42)
    else: top = H
    fr = {s: wall_frame(s, Wl, Dl) for s in ('+z', '-z', '+x', '-x')}
    for fl in range(floors):
        y = .35 + fl * fh
        for s in ('-z', '+x', '-x'): win_row(xf, fr[s], Dl if 'x' in s else Wl, y + .9, 1.2, max(1, int(((Dl if 'x' in s else Wl) - 1) / 2.8)), w=1.0)
    add_building_info(sign or key, x0, z0, x1, z1, mini_col or ('#8a8a8a' if roofkind == 'flat' else ROOFCOL.get(roof, '#888')), kind, top)
    if icon: MINI['icons'].append([icon, round(cx, 1), round(cz, 1)])
    return mb, xf, fr, Wl, Dl, H, (x0, z0, x1, z1)

# ---- ひだまり保育園 ----
mb, xf, fr, Wl, Dl, H, R_ = facility('HidamariNursery', 'nursery', 's', 2, '#f6dcb2', 'b', 'ひだまり保育園', fh=3.0, roofkind='gable', icon='nursery')
f = fr['+z']
for fl in range(2):
    u = -Wl / 2 + 1.4
    while u < Wl / 2 - 1.2:
        if fl or abs(u - 3.5) > 1.8: window(xf, f, u, .35 + fl * 3 + .8, 1.4, 1.4, frame=['#f29b4c', '#6fbf5a', '#5a9ad6', '#f2c94c'][int(u * 3) % 4], curtain='#fff3c4' if fl else None)
        u += 2.6
door(xf, f, 3.5, .35, '#5a9ad6')
awning(xf, f, 1.6, 5.4, 3.0, 1.4, '#3f7fd0', '#f4f2ec', 6)
panel(xf, f, -Wl / 2, Wl / 2, 3.25, 3.42, 0, .5, '#f29b4c')                        # オレンジの帯
sign_board(xf, f, -3.5, 6.75, 6.2, 1.0, 'ひだまり保育園', '#fff8e8', '#e07b1f', '#e07b1f')
for k, c in enumerate(['#e8564a', '#f2c94c', '#6fbf5a', '#5a9ad6', '#c77ad6']):    # かべの 色の まる
    u = -Wl / 2 + 1.5 + k * 1.1; pts = [wp(f, u + math.cos(a / 12 * math.tau) * .35, 5.7 + math.sin(a / 12 * math.tau) * .35, .02) for a in range(12)]; xf.face(pts, col=c, n=f[2])
put(mb, 'HidamariNursery')
# 園庭：低い白いさく・花だん・すな場
x0, z0, x1, z1 = R_
gz0, gz1 = z1 + .4, z1 + 4.2
mb = MB('HidamariNursery_garden')
ring = [(x0 - .5, z1), (x0 - .5, gz1), (x1 + .5, gz1), (x1 + .5, z1)]
ln = LineString(ring).difference(Point(xf.P((3.5, 0, Dl / 2 + 3.8))[0], gz1).buffer(.8))
for a, b in seglist(ln):
    l = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, int(l / .3))
    for k in range(n + 1): x, z = a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n; box(mb, x - .04, x + .04, 0, .9, z - .04, z + .04, col='#fbfaf6')
    for yy in (.35, .75): bar(mb, (a[0], yy, a[1]), (b[0], yy, b[1]), .025, '#fbfaf6', 4)
    colseg(a, b, .12, .9, '保育園のさく')
for k in range(6):
    x = x0 + 1.5 + k * 1.2; box(mb, x - .5, x + .5, 0, .25, gz1 - 1.0, gz1 - .4, col='#a9774d')
    for j in range(4): ball(mb, x - .35 + j * .23, .35, gz1 - .7, .12, .1, .12, ['#e8564a', '#f2c94c', '#f4f2ec', '#e889b0'][(k + j) % 4], seg=6, rings=4)
box(mb, x1 - 5, x1 - 1.5, 0, .2, gz0 + .3, gz0 + 2.4, col='#e3cc9a'); box(mb, x1 - 5.1, x1 - 1.4, 0, .25, gz0 + .2, gz0 + .3, col='#c9884d')
put(mb, 'HidamariNursery')

# ---- 風見町公民館 ----
mb, xf, fr, Wl, Dl, H, R_ = facility('OtherBuildings', 'hall', 's', 2, '#ece6d8', 's', '風見町公民館', fh=3.4, roofkind='flat', parapet=.7, objname='CommunityHall', mini_col='#7d9aa6', kind='hall', icon='hall')
f = fr['+z']
for fl in range(2):
    u = -Wl / 2 + 1.6
    while u < Wl / 2 - 1.4:
        if fl or abs(u) > 3.2: window(xf, f, u, .35 + fl * 3.4 + .9, 2.0, 1.6, frame='#5f8a96', sill=False)
        u += 2.7
panel(xf, f, -3, 3, .35, 3.3, 0, .06, '#4d6f78'); glassq(xf, f, -2.8, 2.8, .45, 3.2, .065)
panel(xf, f, -3.6, 3.6, 3.4, 3.65, 0, 2.2, '#5f8a96')
for s_ in (-1, 1): bar(xf, wp(f, s_ * 3.3, 0, 2.0), wp(f, s_ * 3.3, 3.4, 2.0), .12, '#efeadf', 8)
panel(xf, f, -Wl / 2, Wl / 2, H - .5, H - .1, 0, .12, '#5f8a96')
sign_board(xf, f, 0, 4.0, 5.2, .9, '風見町公民館', '#f6f1e3', '#4d2f86', '#4d2f86')
put(mb, 'OtherBuildings')

# ---- まる福マート（コンビニ）----
mb, xf, fr, Wl, Dl, H, R_ = facility('MarufukuMart', 'mart', 's', 1, '#f4f2ec', 's', 'まる福マート', fh=4.0, shop=True, roofkind='flat', parapet=.3, mini_col='#4fae3a', icon='mart')
f = fr['+z']
interior(xf, Wl, Dl, .35, 3.4, shelves=3, rnd_=random.Random(11))
shop_front(xf, f, -Wl / 2 + .2, Wl / 2 - .2, .35, 3.0)
panel(xf, f, -1.1, 1.1, .35, 2.8, .1, .14, '#9aa6ae')                                # 自動ドアの わく
box(xf, -Wl / 2, Wl / 2, .35, H, -Dl / 2, -Dl / 2 + .01, col='#f4f2ec', sides='', top=False)
panel(xf, f, -Wl / 2 - .05, Wl / 2 + .05, 3.0, H + .3, 0, .25, '#f4f2ec')            # 看板の帯（緑・オレンジ・青のライン）
for k, c in enumerate(['#3f9a2a', '#f29b4c', '#2f6fb8']): panel(xf, f, -Wl / 2 - .05, Wl / 2 + .05, 3.05 + k * .14, 3.17 + k * .14, .25, .27, c)
sign_board(xf, f, 0, 3.55, 6.5, .8, 'まる福マート', '#ffffff', '#2f8a1f', None, d=.28)
put(mb, 'MarufukuMart')
x0, z0, x1, z1 = R_
mb = MB('MarufukuMart_front')
for k in range(5):                                                                    # 駐車場の白線
    x = x0 + 2 + k * 2.8; strip(mb, (x, z1 + 1.2), (x, z1 + 5.0), .12, .012)
    box(mb, x + .6, x + 2.2, 0, .12, z1 + 4.4, z1 + 4.6, col='#d0ccc2')
vending(mb, x1 - .8, z1 + .7, 0, '#d93a3a'); vending(mb, x1 - 1.9, z1 + .7, 0, '#2f6fb8')
for k in range(4):                                                                    # 自転車置き場（ラック）
    x = x0 + .8 + k * .7; bar(mb, (x, 0, z1 + .3), (x, .5, z1 + .3), .025, '#9aa1a3', 4); bar(mb, (x, .5, z1 + .3), (x, .5, z1 + 1.2), .025, '#9aa1a3', 4); bar(mb, (x, 0, z1 + 1.2), (x, .5, z1 + 1.2), .025, '#9aa1a3', 4)
colbox(x0 + .5, z1 + .1, x0 + 3.4, z1 + 1.3, .6, '自転車置き場')
box(mb, x0 + 3.8, x0 + 4.4, 0, .9, z1 + .3, z1 + .8, col='#3f9a2a'); box(mb, x0 + 4.5, x0 + 5.1, 0, .9, z1 + .3, z1 + .8, col='#2f6fb8')   # ごみ箱
colbox(x0 + 3.75, z1 + .25, x0 + 5.15, z1 + .85, 1.0, 'ごみ箱')
for x in (x0 + 7, x1 - 4): ball(mb, x, .7, z1 + .5, .5, .45, .5, '#4f8f45', seg=8, rings=5); box(mb, x - .45, x + .45, 0, .4, z1 + .1, z1 + .9, col='#a98058')
put(mb, 'MarufukuMart')

# ---- 小さな事務所（公民館の道の西）・西のアパート ----
mb, xf, fr, Wl, Dl, H, R_ = facility('OtherBuildings', 'office', 's', 2, '#efe6d2', 's', '事務所', fh=3.0, roofkind='flat', objname='SmallOffice', mini_col='#a8a49a', kind='office')
f = fr['+z']; door(xf, f, -Wl / 2 + 1.3, .35, '#5d6e7a'); window(xf, f, 1.0, 1.2, 3.0, 1.5, sill=False); window(xf, f, 0, 4.2, Wl - 2, 1.3)
awning(xf, f, -Wl / 2 + .3, Wl / 2 - .3, 3.0, 1.0, '#3f9a5a', '#3f9a5a', 4, .2)
put(mb, 'OtherBuildings')
mb, xf, fr, Wl, Dl, H, R_ = facility('OtherBuildings', 'apart', 'e', 3, '#e8d8bc', 's', 'アパート', fh=2.9, roofkind='flat', objname='Apartment', mini_col='#9a8f80', kind='apart')
f = fr['+z']
for fl in range(3):
    y = .35 + fl * 2.9; n = 4
    for k in range(n):
        u = -Wl / 2 + (k + .5) * Wl / n
        window(xf, f, u, y + .2, 1.6, 2.0, grid=True, sill=False)
        if fl: balcony(xf, f, u - 1.15, u + 1.15, y, .9, col='#f4f2ee')
door(xf, f, 0, .35, '#5d6e7a') if False else None
put(mb, 'OtherBuildings')

# ---- 朝倉家・月森家（となりと ちがう見た目に）----
x0, z0, x1, z1 = fac('asakura'); cx, cz, wx, dz = rect_center((x0, z0, x1, z1)); check_clear('asakura', x0, z0, x1, z1)
mb = MB('AsakuraHouse_main'); lod = MB('AsakuraHouse_LOD')
Hh, top = house(mb, cx, cz, wx - .2, dz - .2, 'I', 'r', 'be', 's', random.Random(101), lod)
xf = XF(mb, cx, cz, 0); f = wall_frame('+z', wx - .2, dz - .2)
sign_board(xf, f, -(wx / 2 - 2.0), 1.2, .5, .22, '朝倉', '#f4efe2', '#2b2b2b', None, d=.03)
bar(mb, (cx + wx / 2 - 1.2, top - 1.0, cz - 1.0), (cx + wx / 2 - 1.2, top + .4, cz - 1.0), .3, '#8a4a3a', 8)   # えんとつ
put(mb, 'AsakuraHouse'); put(lod, 'AsakuraHouse')
add_building_info('朝倉家', x0 + .1, z0 + .1, x1 - .1, z1 - .1, '#d8643c', 'asakura', top); MINI['icons'].append(['home', round(cx, 1), round(cz, 1)])
x0, z0, x1, z1 = fac('tsukimori'); cx, cz, wx, dz = rect_center((x0, z0, x1, z1)); check_clear('tsukimori', x0, z0, x1, z1)
mb = MB('TsukimoriHouse_main'); lod = MB('TsukimoriHouse_LOD')
Hh, top = house(mb, cx, cz, wx - .2, dz - .2, 'G', 'g', 'w', 's', random.Random(202), lod)
xf = XF(mb, cx, cz, 0); f = wall_frame('+z', wx - .2, dz - .2)
sign_board(xf, f, -(wx / 2 - 2.0), 1.2, .5, .22, '月森', '#eef2f6', '#2b2b2b', None, d=.03)
put(mb, 'TsukimoriHouse'); put(lod, 'TsukimoriHouse')
add_building_info('月森家', x0 + .1, z0 + .1, x1 - .1, z1 - .1, '#647c90', 'tsukimori', top); MINI['icons'].append(['home', round(cx, 1), round(cz, 1)])
for key, typ, rc, wc in (('hanaHouse', 'A', 'g', 'w'), ('hanaHouse2', 'B', 'g', 'cr')):
    x0, z0, x1, z1 = fac(key); cx, cz, wx, dz = rect_center((x0, z0, x1, z1))
    hroot = empty('House_' + key, GRP['Houses']); mb = MB('House_' + key + '_mesh'); lod = MB('House_' + key + '_LOD')
    Hh, top = house(mb, cx, cz, wx - .2, dz - .2, typ, rc, wc, 's', random.Random(len(key)), lod)
    put(mb, 'Houses', hroot); put(lod, 'Houses', hroot); add_building_info(key, x0 + .1, z0 + .1, x1 - .1, z1 - .1, ROOFCOL[rc], 'house', top)

# ---- 花日和（花屋）----
mb, xf, fr, Wl, Dl, H, R_ = facility('Hanabiyori', 'hana', 's', 2, '#fbf3ea', 'o', '花日和', fh=2.9, shop=True, roofkind='gable', icon='flower')
f = fr['+z']
interior(xf, Wl, Dl, .35, 2.6, shelves=1, cols=('#e8564a', '#f2c94c', '#e889b0', '#f4f2ec', '#6fbf5a'), counter=True, rnd_=random.Random(5))
shop_front(xf, f, -Wl / 2 + .2, Wl / 2 - .2, .35, 2.7)
box(xf, -Wl / 2, Wl / 2, 3.25, H, Dl / 2 - .01, Dl / 2, col='#fbf3ea', sides=['+z'], top=False)
window(xf, f, 0, 4.0, 1.6, 1.2, curtain='#f8d7e0')
awning(xf, f, -Wl / 2 - .1, Wl / 2 + .1, 3.0, 1.3, '#e8638e', '#fbf6f0', 8)
sign_board(xf, f, 0, 3.15, 3.0, .55, '花日和', '#fff6f8', '#d6336c', '#d6336c', d=.3) if False else None
put(mb, 'Hanabiyori')
x0, z0, x1, z1 = R_
mb = MB('Hanabiyori_display')
xs = XF(mb, (x0 + x1) / 2, z1, 0); fs = wall_frame('+z', Wl, .01)
sign_board(xs, fs, 0, 3.7, 3.2, .6, '花日和', '#fff6f8', '#d6336c', '#d6336c', d=.05)
for k in range(3):                                                                    # ひな段の 花だな
    y = .15 + k * .25; zz = z1 + 1.3 - k * .35
    box(mb, x0 + .4, x1 - .4, 0, y + .05, zz - .17, zz + .17, col='#a98058')
    for j in range(int((x1 - x0 - .8) / .45)):
        x = x0 + .65 + j * .45; c = ['#e8564a', '#f2c94c', '#e889b0', '#f4f2ec', '#c77ad6', '#ff9f43'][(j + k) % 6]
        cyl(mb, x, y + .05, zz, .14, .22, '#b5653f', seg=8, r2=.17); ball(mb, x, y + .4, zz, .2, .16, .2, '#4f9a45', seg=7, rings=4)
        for q in range(3): ball(mb, x + math.cos(q * 2.1) * .1, y + .48, zz + math.sin(q * 2.1) * .1, .07, .06, .07, c, seg=6, rings=4)
colbox(x0 + .3, z1 + .1, x1 - .3, z1 + 1.55, .9, '花の だな')
for j in range(4):                                                                    # バケツの 切り花
    x = x0 + .5 + j * .6; cyl(mb, x, 0, z1 + 1.9, .2, .45, '#9fb6c2', seg=8); 
    for q in range(5): bar(mb, (x, .4, z1 + 1.9), (x + math.cos(q * 1.3) * .15, .95, z1 + 1.9 + math.sin(q * 1.3) * .15), .012, '#4f9a45', 3); ball(mb, x + math.cos(q * 1.3) * .15, .98, z1 + 1.9 + math.sin(q * 1.3) * .15, .07, .07, .07, ['#e8564a', '#f2c94c', '#e889b0'][(q + j) % 3], seg=6, rings=4)
colbox(x0 + .2, z1 + 1.6, x0 + 2.6, z1 + 2.2, .6, '花のバケツ')
put(mb, 'Hanabiyori')

# ---- こむぎベーカリー ----
mb, xf, fr, Wl, Dl, H, R_ = facility('KomugiBakery', 'bakery', 'n', 2, '#f6e3c2', 'o', 'こむぎベーカリー', fh=3.0, shop=True, roofkind='gable', icon='bakery')
f = fr['+z']
interior(xf, Wl, Dl, .35, 2.7, shelves=2, cols=('#c9853f', '#e0a75a', '#b86b2c', '#f0c98a', '#a35a24'), rnd_=random.Random(8))
shop_front(xf, f, -Wl / 2 + .2, Wl / 2 - .2, .35, 2.8, frame='#6b4630')
box(xf, -Wl / 2, Wl / 2, 3.35, H, Dl / 2 - .01, Dl / 2, col='#f6e3c2', sides=['+z'], top=False)
for u in (-Wl / 4, Wl / 4): window(xf, f, u, 4.1, 1.4, 1.1, frame='#6b4630', curtain='#fff3dc')
awning(xf, f, -Wl / 2 - .1, Wl / 2 + .1, 3.1, 1.3, '#8a4f2a', '#f6e3c2', 10)
sign_board(xf, f, 0, 5.6, 6.0, .8, 'こむぎベーカリー', '#fff6e6', '#8a4f2a', '#8a4f2a', d=.1)
put(mb, 'KomugiBakery')
x0, z0, x1, z1 = R_
mb = MB('KomugiBakery_front')
box(mb, x0 + 1, x0 + 1.6, 0, .9, z0 - 1.2, z0 - .6, col='#2b2b2b')                     # 黒板の 看板
box(mb, x0 + 1.05, x0 + 1.55, .3, .85, z0 - 1.21, z0 - 1.2, col='#3f5f4a')
colbox(x0 + .9, z0 - 1.3, x0 + 1.7, z0 - .5, .9, '黒板の看板')
put(mb, 'KomugiBakery')

# ---- 魚まる ----
mb, xf, fr, Wl, Dl, H, R_ = facility('Uomaru', 'uomaru', 's', 2, '#eef1f2', 'b', '魚まる', fh=3.0, shop=True, roofkind='gable', icon='fish')
f = fr['+z']
interior(xf, Wl, Dl, .35, 2.7, shelves=1, cols=('#9fb6c2', '#e8564a', '#f4f2ec', '#5a9ad6'), rnd_=random.Random(9))
shop_front(xf, f, -Wl / 2 + .2, Wl / 2 - .2, .35, 2.8, frame='#3a4f78')
box(xf, -Wl / 2, Wl / 2, 3.35, H, Dl / 2 - .01, Dl / 2, col='#eef1f2', sides=['+z'], top=False)
for u in (-Wl / 3, 0, Wl / 3): window(xf, f, u, 4.1, 1.4, 1.1)
awning(xf, f, -Wl / 2 - .1, Wl / 2 + .1, 3.15, 1.6, '#d93a3a', '#fbfaf6', 12)
sign_board(xf, f, 0, 5.5, 4.2, .85, '魚まる', '#1f5fbf', '#ffffff', '#ffffff', d=.1)
put(mb, 'Uomaru')
x0, z0, x1, z1 = R_
mb = MB('Uomaru_front')
cx = (x0 + x1) / 2
box(mb, cx - 4, cx + 4, 0, .8, z1 + .4, z1 + 1.4, col='#d8dde0')                       # 商品ケース
mb.face([(cx - 3.9, .81, z1 + 1.35), (cx + 3.9, .81, z1 + 1.35), (cx + 3.9, 1.0, z1 + .45), (cx - 3.9, 1.0, z1 + .45)], None, 'clear', uvs=[(0, 0), (1, 0), (1, 1), (0, 1)])
for k in range(14):
    x = cx - 3.6 + k * .52; box(mb, x, x + .36, .8, .84, z1 + .6, z1 + 1.2, col='#f4f2ec'); ball(mb, x + .18, .88, z1 + .9, .15, .05, .06, ['#9fb6c2', '#e8564a', '#c0c8cc'][k % 3], seg=6, rings=4)
colbox(cx - 4.05, z1 + .35, cx + 4.05, z1 + 1.45, 1.0, '商品ケース')
for k in range(3):                                                                      # 発泡スチロールの 箱
    for j in range(2 + k % 2):
        x = x1 - 1.6 + (k % 2) * .1; z = z1 + .7 + k * .0; y = j * .32
        box(mb, x - .5 + k * .02, x + .5, y, y + .3, z - .3 + k * .65 - .4, z + .3 + k * .65 - .4, col='#f7f7f4')
colbox(x1 - 2.2, z1 + .0, x1 - .9, z1 + 2.0, 1.0, '発泡スチロールの箱')
put(mb, 'Uomaru')

# ---- ふたば銀行 ----
mb, xf, fr, Wl, Dl, H, R_ = facility('FutabaBank', 'bank', 's', 2, '#eadcbe', 'b', 'ふたば銀行', fh=3.6, roofkind='hip', icon='bank')
f = fr['+z']
for fl in range(2):
    u = -Wl / 2 + 1.5
    while u < Wl / 2 - 1.3:
        if fl or abs(u) > 3.0: window(xf, f, u, .35 + fl * 3.6 + 1.0, 2.0, 1.4, frame='#d9cfb4', sill=True)
        u += 2.6
panel(xf, f, -2.6, 2.6, .35, 3.4, 0, .06, '#8f7c58'); glassq(xf, f, -2.4, 2.4, .45, 3.3, .065)
panel(xf, f, -3.4, 3.4, 3.6, 3.9, 0, 2.4, '#d9cfb4')
for s_ in (-1, 1):
    for k in (2.9, 1.6): cyl(xf, s_ * k, .35, Dl / 2 + 2.1, .22, 3.25, '#f4f0e4', seg=12) if False else bar(xf, wp(f, s_ * k, .35, 2.1), wp(f, s_ * k, 3.6, 2.1), .2, '#f4f0e4', 10)
for k in range(3): panel(xf, f, -3.4, 3.4, 0, .35 - k * .11, 0, 2.6 + k * .5, '#d3cbbb')
sign_board(xf, f, 0, 4.35, 5.6, .9, 'ふたば銀行', '#1f5fbf', '#ffffff', '#ffffff', d=.1)
for k in range(2): panel(xf, f, Wl / 2 - 3.2 + k * 1.2, Wl / 2 - 2.3 + k * 1.2, .35, 2.0, 0, .3, '#9fb6c2')   # ATM
put(mb, 'FutabaBank')

# ---- つばめ郵便（赤いアクセント・ポスト）----
mb, xf, fr, Wl, Dl, H, R_ = facility('TsubamePostOffice', 'post', 'e', 1, '#f4efe6', 's', 'つばめ郵便', fh=3.6, roofkind='flat', parapet=.5, mini_col='#d93a3a', icon='post')
f = fr['+z']
panel(xf, f, -Wl / 2 - .05, Wl / 2 + .05, 2.9, 3.6, 0, .2, '#d93a3a')
window(xf, f, -Wl / 4 - .6, 1.0, 2.6, 1.6, frame='#d93a3a', sill=False); window(xf, f, Wl / 4 + .9, 1.0, 1.8, 1.6, frame='#d93a3a', sill=False)
door(xf, f, .8, .35, '#9fb6c2', canopy=False)
sign_board(xf, f, -.2, 3.0, 4.2, .5, '〒 つばめ郵便', '#d93a3a', '#ffffff', None, d=.23)
put(mb, 'TsubamePostOffice')
x0, z0, x1, z1 = R_
mb = MB('TsubamePostOffice_post')
px, pz = x1 + 1.0, z0 + 2.0
cyl(mb, px, 0, pz, .1, .4, '#3a3a3a', seg=8); box(mb, px - .3, px + .3, .4, 1.4, pz - .3, pz + .3, col='#d93a3a'); cyl(mb, px, 1.4, pz, .32, .15, '#c0302a', seg=12)
box(mb, px + .3, px + .31, 1.05, 1.15, pz - .18, pz + .18, col='#2b2b2b')
colcircle(px, pz, .4, 1.5, 'ポスト')
put(mb, 'TsubamePostOffice')

# ---- 青いしまの お店（つばめ郵便のとなり）----
mb, xf, fr, Wl, Dl, H, R_ = facility('OtherBuildings', 'shop2', 's', 2, '#f4f2ec', 'b', '風見商店', fh=3.0, shop=True, roofkind='flat', parapet=.3, objname='KazamiStore', mini_col='#4a7fc4')
f = fr['+z']
interior(xf, Wl, Dl, .35, 2.7, shelves=2, rnd_=random.Random(12))
shop_front(xf, f, -Wl / 2 + .2, Wl / 2 - .2, .35, 2.8)
box(xf, -Wl / 2, Wl / 2, 3.35, H, Dl / 2 - .01, Dl / 2, col='#f4f2ec', sides=['+z'], top=False)
for u in (-Wl / 3, 0, Wl / 3): window(xf, f, u, 4.1, 1.4, 1.1)
awning(xf, f, -Wl / 2 - .1, Wl / 2 + .1, 3.1, 1.4, '#2f6fb8', '#fbfaf6', 12)
sign_board(xf, f, 0, 5.4, 4.0, .7, '風見商店', '#ffffff', '#1f4f9a', '#1f4f9a', d=.08)
put(mb, 'OtherBuildings')

# ---- フォレストショップ（木のかべ・緑の大きな屋根）----
mb, xf, fr, Wl, Dl, H, R_ = facility('ForestShop', 'forest', 's', 1, '#b58658', 'G', 'フォレストショップ', fh=4.4, shop=True, roofkind='gable', icon='forest')
f = fr['+z']
for k in range(int(Wl / .3)):                                                           # 板ばりの すじ
    u = -Wl / 2 + k * .3
    for s_ in ('-z', '+x', '-x'):
        ff = fr[s_]; L_ = Dl if 'x' in s_ else Wl
        if u < L_ / 2: panel(xf, ff, u, u + .03, .35, H - .05, 0, .02, '#9a6f45')
interior(xf, Wl, Dl, .35, 3.6, shelves=2, cols=('#6fbf5a', '#a98058', '#4f9a45', '#e0c070', '#c77a4a'), rnd_=random.Random(13))
shop_front(xf, f, -Wl / 2 + .3, Wl / 2 - .3, .35, 3.4, frame='#6b4630')
box(xf, -Wl / 2, Wl / 2, 3.75, H, Dl / 2 - .01, Dl / 2, col='#b58658', sides=['+z'], top=False)
panel(xf, f, -4.0, 4.0, 3.7, 3.85, 0, 2.2, '#6b4630')
for s_ in (-1, 1): bar(xf, wp(f, s_ * 3.8, 0, 2.0), wp(f, s_ * 3.8, 3.7, 2.0), .16, '#7a5232', 8)
sign_board(xf, f, 0, H + .6, 7.0, 1.0, 'フォレストショップ', '#2f6f2a', '#f4f2dc', '#f4f2dc', d=.15)
put(mb, 'ForestShop')
x0, z0, x1, z1 = R_
mb = MB('ForestShop_front')
for k in range(5):
    x = x0 + 1.5 + k * ((x1 - x0) - 3) / 4
    if abs(x - (x0 + x1) / 2) < 4.5: continue
    box(mb, x - .6, x + .6, 0, .55, z1 + 2.6, z1 + 3.4, col='#8a5a36'); ball(mb, x, 1.0, z1 + 3.0, .7, .6, .5, '#4f9a45', seg=8, rings=5)
    colbox(x - .65, z1 + 2.55, x + .65, z1 + 3.45, .7, 'プランター')
put(mb, 'ForestShop')

# ---- バス停（屋根つきの いす）----
x0, z0, x1, z1 = fac('busstop'); cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
mb = MB('BusStop')
box(mb, cx - 1.4, cx + 1.4, 2.3, 2.42, cz - .8, cz + .5, col='#3f9a5a')
for s_ in (-1, 1): bar(mb, (cx + s_ * 1.3, 0, cz - .7), (cx + s_ * 1.3, 2.3, cz - .7), .05, '#9aa1a3')
box(mb, cx - 1.3, cx + 1.3, .1, 2.2, cz - .74, cz - .7, col='#cfe0ea')
box(mb, cx - 1.1, cx + 1.1, .42, .48, cz - .6, cz - .25, col='#a98058'); box(mb, cx - 1.0, cx + 1.0, 0, .42, cz - .5, cz - .45, col='#9aa1a3')
bar(mb, (cx + 1.8, 0, cz), (cx + 1.8, 2.4, cz), .04, '#9aa1a3'); xs = XF(mb, cx + 1.8, cz + .04, 0)
sign_board(xs, wall_frame('+z', .6, .02), 0, 2.4, .6, .6, 'バス', '#2f6fb8', '#ffffff', None, d=.02)
colbox(cx - 1.45, cz - .85, cx + 1.45, cz - .2, 2.4, 'バス停'); colcircle(cx + 1.8, cz, .12, 2.4, 'バス停の標識')
put(mb, 'StreetProps')

# ---- みつば公園（すべり台・ブランコ・すな場・ベンチ・花だん・看板）----
mb = MB('MitsubaPark_main')
pk = max(polys(PARK), key=lambda p: p.area)
pc = pk.representative_point(); bx0, bz0, bx1, bz1 = pk.bounds
def free_in_park(x, z, r): return pk.buffer(-r).contains(Point(x, z))
def find_spot(x, z, r):
    best = None
    for k in range(400):
        a = k * 2.399; d = math.sqrt(k) * .5; xx, zz = x + math.cos(a) * d, z + math.sin(a) * d
        if free_in_park(xx, zz, r) and not any(Point(xx, zz).distance(Point(q[0], q[1])) < q[2] + r for q in PARK_USED): return xx, zz
    return None
PARK_USED = []
# すべり台
s = find_spot(bx0 + (bx1 - bx0) * .3, bz0 + (bz1 - bz0) * .3, 3.0)
if s:
    x, z = s; h = 1.8; PARK_USED.append((x, z, 3.0))
    for (dx, dz) in [(-.5, -.5), (.5, -.5), (-.5, .5), (.5, .5)]: bar(mb, (x + dx, 0, z + dz), (x + dx, h + .8, z + dz), .05, '#e04848')
    box(mb, x - .6, x + .6, h - .08, h, z - .6, z + .6, col='#f2c94c')
    for k in range(6): y = .3 + k * .28; bar(mb, (x - .45, y, z - .65 - (h - y) * .3), (x + .45, y, z - .65 - (h - y) * .3), .025, '#9aa1a3')
    L_ = 3.4; quad = [(x - .42, h, z + .6), (x + .42, h, z + .6), (x + .42, .3, z + .6 + L_), (x - .42, .3, z + .6 + L_)]
    mb.face(quad, col='#5a9ad6', n=(0, 1, 1))
    for s_ in (-1, 1): mb.face([(x + s_ * .42, h, z + .6), (x + s_ * .42, .3, z + .6 + L_), (x + s_ * .42, .6, z + .6 + L_), (x + s_ * .42, h + .3, z + .6)], col='#3f7fd0', n=(s_, 0, 0))
    colbox(x - .7, z - 1.3, x + .7, z + .7 + L_, 1.2, 'すべり台')
# ブランコ（2つ）
s = find_spot(bx0 + (bx1 - bx0) * .7, bz0 + (bz1 - bz0) * .35, 2.6)
if s:
    x, z = s; PARK_USED.append((x, z, 2.6))
    for zz in (z - 1.6, z + 1.6):
        for s_ in (-1, 1): bar(mb, (x + s_ * 1.1, 0, zz), (x, 2.4, zz), .05, '#3f9a5a'); colcircle(x + s_ * 1.1, zz, .12, 2.4, 'ブランコ')
    bar(mb, (x, 2.4, z - 1.6), (x, 2.4, z + 1.6), .06, '#3f9a5a')
    for zc in (z - .75, z + .75):
        for dz in (-.2, .2): bar(mb, (x, 2.4, zc + dz), (x, .5, zc + dz), .01, '#9aa1a3', 3)
        box(mb, x - .18, x + .18, .45, .5, zc - .25, zc + .25, col='#e04848')
    box(mb, x - 1.9, x - 1.8, 0, .65, z - 1.8, z + 1.8, col='#f2c94c'); colbox(x - 1.95, z - 1.8, x - 1.75, z + 1.8, .65, 'ブランコの さく')
# すな場
s = find_spot(pc.x, pc.y + 2, 2.0)
if s:
    x, z = s; PARK_USED.append((x, z, 2.0))
    for (a0, a1, b0, b1) in [(x - 1.8, x + 1.8, z - 1.8, z - 1.6), (x - 1.8, x + 1.8, z + 1.6, z + 1.8), (x - 1.8, x - 1.6, z - 1.8, z + 1.8), (x + 1.6, x + 1.8, z - 1.8, z + 1.8)]: box(mb, a0, a1, 0, .3, b0, b1, col='#a98058')
    box(mb, x - 1.6, x + 1.6, 0, .18, z - 1.6, z + 1.6, col='#ead6a6'); ball(mb, x - .4, .2, z, .7, .3, .55, '#e3cc9a', seg=8, rings=4)
    cyl(mb, x + .7, .18, z + .6, .13, .2, '#e04848', seg=8); 
# ベンチ・看板・花だん・自販機
for k in range(2):
    s = find_spot(bx0 + (bx1 - bx0) * (.2 + .6 * k), bz1 - 2, 1.2)
    if not s: continue
    x, z = s; PARK_USED.append((x, z, 1.2))
    box(mb, x - .9, x + .9, .42, .48, z - .22, z + .22, col='#a98058'); box(mb, x - .9, x + .9, .55, .95, z + .2, z + .25, col='#a98058')
    for xx in (x - .75, x + .75): box(mb, xx - .06, xx + .06, 0, .42, z - .2, z + .2, col='#5d6064')
    colbox(x - .95, z - .25, x + .95, z + .3, .5, 'ベンチ')
s = find_spot(bx0 + 1.5, bz0 + 1.5, .8)
if s:
    x, z = s; PARK_USED.append((x, z, .8))
    for xx in (x - .7, x + .7): bar(mb, (xx, 0, z), (xx, 1.2, z), .05, '#7a5232')
    xs = XF(mb, x, z, 0); sign_board(xs, wall_frame('+z', 1.6, .1), 0, 1.0, 1.5, .5, 'みつば公園', '#f4f1e2', '#2f6f2a', '#2f6f2a', d=.04)
    colbox(x - .8, z - .12, x + .8, z + .12, 1.6, '公園の看板')
s = find_spot(pc.x + 3, pc.y - 3, .7)
if s: x, z = s; PARK_USED.append((x, z, .7)); vending(mb, x, z, 180, '#3f9a5a')
fb = pk.buffer(-.4).exterior
for k in range(int(fb.length / 1.4)):                                                     # ふちの 花だん（低い）
    p = fb.interpolate(k * 1.4)
    if any(Point(p.x, p.y).distance(Point(q[0], q[1])) < q[2] for q in PARK_USED): continue
    if R_all.buffer(2.2).contains(p): continue
    ball(mb, p.x, .25, p.y, .32, .25, .32, '#5aa04a', seg=7, rings=4)
    ball(mb, p.x + .1, .45, p.y, .09, .07, .09, ['#e8564a', '#f2c94c', '#f4f2ec', '#e889b0'][k % 4], seg=5, rings=3)
put(mb, 'MitsubaPark')
MINI['icons'].append(['park', round(pc.x, 1), round(pc.y, 1)])

# =====================================================================
#  6. 木・草・花（同じメッシュを使いまわす：ゲームで インスタンス描画）
# =====================================================================
TPL = {}
def template(name, fn):
    mb = MB(name); fn(mb); o = mb.build(None, SCN); o.hide_render = False
    TPL[name] = o.data; bpy.data.objects.remove(o); return o
def t_trunk(mb, h=1.6, r=.16):
    cyl(mb, 0, 0, 0, r * 1.3, .3, '#6e4c34', seg=8, r2=r); cyl(mb, 0, .3, 0, r, h - .3, '#7a5438', seg=8, r2=r * .75)
def t_round(seed):
    def f(mb):
        r = random.Random(seed)
        for k in range(6):
            a = k / 6 * math.tau + r.random() * .5; d = r.uniform(.4, .9)
            ball(mb, math.cos(a) * d, 2.4 + r.uniform(-.2, .3), math.sin(a) * d, r.uniform(.8, 1.0), r.uniform(.7, .9), r.uniform(.8, 1.0), '#4f9a45', seg=10, rings=7, jitter=.06, rnd=r)
        for k in range(4):
            a = k / 4 * math.tau + r.random(); d = r.uniform(.1, .5)
            ball(mb, math.cos(a) * d, 3.1 + r.uniform(0, .4), math.sin(a) * d, r.uniform(.75, .9), r.uniform(.6, .75), r.uniform(.75, .9), '#6cb653', seg=10, rings=7, jitter=.06, rnd=r)
        ball(mb, 0, 3.6, 0, .7, .55, .7, '#86c766', seg=10, rings=6)
    return f
def t_cone(mb):
    for k, (y, r_, h) in enumerate([(1.0, 1.25, 1.9), (1.9, 1.0, 1.7), (2.8, .7, 1.5)]): cone(mb, 0, y, 0, r_, h, ['#2f7a4a', '#3a8a55', '#4a9a60'][k], seg=10)
def t_sakura(seed):
    def f(mb):
        r = random.Random(seed)
        for k in range(4):
            a = k / 4 * math.tau + r.random(); bar(mb, (0, 1.6, 0), (math.cos(a) * 1.2, 2.6, math.sin(a) * 1.2), .08, '#5e4232', 5)
        for k in range(9):
            a = r.random() * math.tau; d = r.random() * 1.4
            ball(mb, math.cos(a) * d, 2.6 + r.random() * 1.1, math.sin(a) * d, r.uniform(.7, .95), r.uniform(.55, .7), r.uniform(.7, .95), r.choice(['#f6b6c8', '#f9cddb', '#f2a2ba']), seg=10, rings=6, jitter=.05, rnd=r)
    return f
def t_bush(mb):
    r = random.Random(5)
    for k in range(4):
        a = k / 4 * math.tau; ball(mb, math.cos(a) * .35, .45, math.sin(a) * .35, .55, .45, .55, '#4f9a45' if k % 2 else '#5fa84f', seg=8, rings=5, jitter=.05, rnd=r)
    ball(mb, 0, .75, 0, .5, .4, .5, '#74ba5c', seg=8, rings=5)
def t_tuft(mb):
    r = random.Random(9)
    for k in range(5):
        a = k / 5 * math.tau + r.random() * .4; x, z = math.cos(a) * .08, math.sin(a) * .08; h = r.uniform(.25, .4); lean = .1
        tx, tz = x + math.cos(a) * lean, z + math.sin(a) * lean
        pts = [(x - .03 * math.sin(a), 0, z + .03 * math.cos(a)), (x + .03 * math.sin(a), 0, z - .03 * math.cos(a)), (tx, h, tz)]
        mb.face(pts, col='#5fa84f'); mb.face(pts[::-1], col='#5fa84f')
def t_flower(col):
    def f(mb):
        bar(mb, (0, 0, 0), (0, .32, 0), .012, '#4f9a45', 3)
        for k in range(5):
            a = k / 5 * math.tau; ball(mb, math.cos(a) * .05, .33, math.sin(a) * .05, .045, .02, .045, col, seg=5, rings=3)
        ball(mb, 0, .34, 0, .03, .02, .03, '#f2c94c', seg=5, rings=3)
    return f
def both(*fs):
    def f(mb):
        for g in fs: g(mb)
    return f
def t_flowers(mb):
    r = random.Random(4)
    for k, col in enumerate(['#e8564a', '#f2c94c', '#f6f4ee', '#e889b0']):
        a = k / 4 * math.tau + r.random(); x, z = math.cos(a) * .14, math.sin(a) * .14; h = r.uniform(.24, .36)
        bar(mb, (x, 0, z), (x, h, z), .012, '#4f9a45', 3)
        for j in range(5):
            b = j / 5 * math.tau; ball(mb, x + math.cos(b) * .05, h + .01, z + math.sin(b) * .05, .045, .02, .045, col, seg=5, rings=3)
        ball(mb, x, h + .02, z, .03, .02, .03, '#f2c94c', seg=5, rings=3)
for nm, fn in [('tree_round_a', both(lambda mb: t_trunk(mb, 2.0, .17), t_round(1))), ('tree_round_b', both(lambda mb: t_trunk(mb, 2.0, .17), t_round(2))),
               ('tree_cone', both(lambda mb: t_trunk(mb, 1.2, .14), t_cone)), ('tree_sakura', both(lambda mb: t_trunk(mb, 1.9, .16), t_sakura(4))),
               ('bush', t_bush), ('grass_tuft', t_tuft), ('flower_clump', t_flowers)]:
    template(nm, fn)
INST = {}
def inst(tpl, x, z, s=1.0, rot=0.0, group='Trees', parent=None, y=0.0):
    o = bpy.data.objects.new('%s.%03d' % (tpl, INST.get(tpl, 0)), TPL[tpl]); INST[tpl] = INST.get(tpl, 0) + 1
    SCN.objects.link(o); o.location = bl((x, y, z)); o.rotation_euler = (0, 0, rot); o.scale = (s, s, s); o.parent = parent or GRP[group]
    return o
TREE_POS = []
def tree(kind, x, z, s=None):
    s = s or rnd.uniform(1.0, 1.4); rot = rnd.random() * math.tau
    if kind == 'round':
        inst(rnd.choice(['tree_round_a', 'tree_round_b']), x, z, s, rot); colcircle(x, z, .3 * s, 4, '木')
    elif kind == 'cone':
        inst('tree_cone', x, z, s, rot); colcircle(x, z, .28 * s, 4, '木')
    elif kind == 'sakura':
        inst('tree_sakura', x, z, s, rot); colcircle(x, z, .3 * s, 4, '桜の木')
    else:
        inst('bush', x, z, s * rnd.uniform(.8, 1.2), rot, 'Vegetation')
    TREE_POS.append((x, z, kind, s))
BLOCKED = unary_union(BLD).buffer(2.0).union(R_all.buffer(2.2)).union(Wfull.buffer(1.6)).union(PATH.buffer(1.0)).union(DPATH.buffer(1.0)).union(YARD.buffer(.3)).union(DIRTG.buffer(1.5))
BLOCKED = BLOCKED.union(PARK)
for p, kind in L.TREES:
    x, z = W(p)
    if not O.buffer(-1.0).contains(Point(x, z)): continue
    if kind != 'bush' and (unary_union(BLD).buffer(1.6).contains(Point(x, z)) or R_all.buffer(1.8).contains(Point(x, z)) or Wfull.buffer(1.2).contains(Point(x, z))): print('木をよけた', p); continue
    tree(kind, x, z)
# 緑地に 木を足す（ポアソン円盤：道・建物・水路・小道から はなす）
GZ = FREE.intersection(GRASSG).difference(BLOCKED).buffer(-.8)
bx0, bz0, bx1, bz1 = GZ.bounds
cand = []
for k in range(9000):
    x, z = rnd.uniform(bx0, bx1), rnd.uniform(bz0, bz1)
    if not GZ.contains(Point(x, z)): continue
    if any((x - t[0]) ** 2 + (z - t[1]) ** 2 < 7.0 ** 2 for t in TREE_POS) or any((x - c[0]) ** 2 + (z - c[1]) ** 2 < 7.0 ** 2 for c in cand): continue
    cand.append((x, z))
for x, z in cand: tree(rnd.choice(['round', 'round', 'round', 'cone', 'bush', 'round']), x, z)
# 区画の うら庭（家と家のあいだ）にも 木を
LZ = LOT.difference(unary_union(BLD).buffer(1.8)).difference(PLAZA.buffer(1)).difference(PARKG.buffer(1)).buffer(-1.0)
bx0, bz0, bx1, bz1 = LZ.bounds; cand = []
for k in range(9000):
    x, z = rnd.uniform(bx0, bx1), rnd.uniform(bz0, bz1)
    if not LZ.contains(Point(x, z)): continue
    if any((x - t[0]) ** 2 + (z - t[1]) ** 2 < 5.5 ** 2 for t in TREE_POS) or any((x - c[0]) ** 2 + (z - c[1]) ** 2 < 5.5 ** 2 for c in cand): continue
    cand.append((x, z))
for x, z in cand: tree(rnd.choice(['round', 'round', 'bush', 'cone', 'bush']), x, z, rnd.uniform(.8, 1.15))
# 草の たば・花（芝生の上だけ）
GG = FREE.intersection(GRASSG).union(YARD).union(PARK).difference(unary_union(BLD).buffer(.5)).difference(DIRTG.buffer(.8)).difference(PATH.buffer(.3)).difference(DPATH.buffer(.3))
bx0, bz0, bx1, bz1 = GG.bounds; n_t = 0; n_f = 0
for k in range(22000):
    x, z = rnd.uniform(bx0, bx1), rnd.uniform(bz0, bz1)
    if not GG.contains(Point(x, z)): continue
    if any((x - t[0]) ** 2 + (z - t[1]) ** 2 < 1.0 for t in TREE_POS[-60:]): continue
    if rnd.random() < .12:
        inst('flower_clump', x, z, rnd.uniform(.8, 1.3), rnd.random() * math.tau, 'Vegetation'); n_f += 1
    else:
        inst('grass_tuft', x, z, rnd.uniform(.8, 1.5), rnd.random() * math.tau, 'Vegetation'); n_t += 1
    if n_t > 2600: break
print('木', len(TREE_POS), '草', n_t, '花', n_f)

# =====================================================================
#  7. 道の小物：電柱と電線・街灯・カーブミラー・標識
# =====================================================================
def t_pole(mb):
    cyl(mb, 0, 0, 0, .17, 8.0, '#b9b6ad', seg=10, r2=.12)
    for y in (6.9, 7.6):
        box(mb, -.8, .8, y - .06, y + .06, -.06, .06, col='#8a8780')
        for x in (-.65, 0, .65): cyl(mb, x, y + .06, 0, .05, .14, '#e8e6e0', seg=6)
    for k in range(10): box(mb, .12, .3, 1.8 + k * .45, 1.84 + k * .45, -.02, .02, col='#77746e')   # 足場ボルト
    box(mb, -.21, .21, 2.4, 3.1, -.18, .18, col='#e9e3c9')                                           # 巻きつけ広告（なし）
def t_trans(mb):
    cyl(mb, .45, 5.4, 0, .28, .9, '#9fa4a8', seg=10); cyl(mb, .45, 6.3, 0, .29, .06, '#7f8488', seg=10)
def t_lamp(mb):
    bar(mb, (0, 5.2, 0), (0, 5.6, 1.1), .04, '#8f9296'); box(mb, -.16, .16, 5.45, 5.6, .95, 1.45, col='#8f9296')
    mb.face([(-.13, 5.44, 1.42), (.13, 5.44, 1.42), (.13, 5.44, .98), (-.13, 5.44, .98)], None, 'lamp', uvs=[(0, 0), (1, 0), (1, 1), (0, 1)], n=(0, -1, 0))
def t_mirror(mb):
    cyl(mb, 0, 0, 0, .05, 2.9, '#e9a23a', seg=8)
    pts = [(math.cos(k / 16 * math.tau) * .38, 2.75 + math.sin(k / 16 * math.tau) * .38, .1) for k in range(16)]
    mb.face(pts, col='#e07b1f', n=(0, 0, 1)); mb.face([(p[0] * .85, p[1] * .85 + 2.75 * .15, .12) for p in pts], None, 'glass', uvs=[((p[0] / .76) + .5, (p[1] - 2.75) / .76 + .5) for p in pts], n=(0, 0, 1))
    mb.face([(p[0], p[1], .08) for p in pts], col='#e07b1f', n=(0, 0, -1))
def t_stop(mb):
    cyl(mb, 0, 0, 0, .04, 2.2, '#c9ccce', seg=8)
    pts = [(math.sin(k / 3 * math.tau + math.pi) * .45, 2.25 + math.cos(k / 3 * math.tau + math.pi) * .45, .05) for k in range(3)]
    quad_uv(mb, [pts[1], pts[2], (0, 2.25 - .45, .05), pts[0]] if False else [pts[0], pts[1], pts[2], pts[2]], STOPSIGN)
    mb.face([(p[0], p[1], .03) for p in pts[::-1]], col='#c9ccce')
def stop_img():
    im = Image.new('RGBA', (256, 256), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.polygon([(8, 20), (248, 20), (128, 236)], fill=(255, 255, 255, 255)); d.polygon([(26, 30), (230, 30), (128, 214)], fill=(214, 40, 40, 255))
    d.text((128, 88), '止まれ', font=KG.F(54), fill=(255, 255, 255, 255), anchor='mm')
    return im
STOPSIGN = KG.pic_mat('decal_stopsign', stop_img(), alpha=True)
for nm, fn in [('pole', t_pole), ('pole_trans', t_trans), ('pole_lamp', t_lamp), ('curve_mirror', t_mirror)]: template(nm, fn)
# 止まれの標識（三角）：板は 1枚の四角に 三角の絵（まわりは すける）
def t_stop2(mb):
    cyl(mb, 0, 0, 0, .04, 2.2, '#c9ccce', seg=8)
    quad_uv(mb, [(-.5, 1.85, .05), (.5, 1.85, .05), (.5, 2.85, .05), (-.5, 2.85, .05)], STOPSIGN, uvs=[(0, 1), (1, 1), (1, 0), (0, 0)])
    mb.face([(.42, 2.75, .03), (-.42, 2.75, .03), (0, 1.95, .03)], col='#c9ccce', n=(0, 0, -1))
template('stop_sign', t_stop2)
POLES = []
wires = MB('StreetProps_wires')
for name, kind, ls, w in road_lines:
    if kind == 'alley' or ls.length < 20: continue
    side = 1 if (hash(name) % 2) else -1
    off = ls.offset_curve(side * (w / 2 + .75))
    chain = []
    for seg in lines(off):
        s = 6.0
        while s < seg.length - 3:
            c = seg.interpolate(s); P_ = Point(c.x, c.y)
            ok = O.buffer(-1.5).contains(P_) and not R_all.buffer(.25).contains(P_) and not unary_union(BLD).buffer(.6).contains(P_) and not Wfull.buffer(.6).contains(P_) \
                 and not any(math.hypot(c.x - q[0], c.y - q[1]) < 6 for q in POLES)
            if ok:
                a_ = seg.interpolate(max(0, s - .5)); b_ = seg.interpolate(min(seg.length, s + .5)); rot = math.atan2(-(b_.y - a_.y), b_.x - a_.x)
                inst('pole', c.x, c.y, 1, rot, 'StreetProps'); colcircle(c.x, c.y, .25, 8, '電柱')
                k = len(POLES)
                if k % 3 == 1: inst('pole_trans', c.x, c.y, 1, rot, 'StreetProps')
                if k % 2 == 0:
                    inst('pole_lamp', c.x, c.y, 1, rot + (math.pi if side > 0 else 0) + math.pi / 2 * 0, 'StreetProps')
                POLES.append((c.x, c.y, rot)); chain.append((c.x, c.y, rot)); s += 24
            else: s += 2
    for i in range(len(chain) - 1):                                                  # 電線（たるみ）
        (ax, az, ar), (bx, bz, br) = chain[i], chain[i + 1]
        if math.hypot(bx - ax, bz - az) > 34: continue
        for dx, y in ((-.65, 7.62), (.65, 7.62), (0, 6.96)):
            pa = (ax + math.cos(ar) * dx, az - math.sin(ar) * dx); pb = (bx + math.cos(br) * dx, bz - math.sin(br) * dx)
            prev = None
            for k in range(9):
                t = k / 8; x = pa[0] + (pb[0] - pa[0]) * t; z = pa[1] + (pb[1] - pa[1]) * t; yy = y - math.sin(t * math.pi) * .45
                if prev: bar(wires, prev, (x, yy, z), .018, '#2e2e30', 3)
                prev = (x, yy, z)
put(wires, 'StreetProps')
# カーブミラー・止まれの標識（住宅の道が 主要道路に出るところ）
for (x, z, ux, uz, nx, nz, w) in STOP_SIGNS:
    px, pz = x + nx * (w / 2 + .6) - ux * 1.0, z + nz * (w / 2 + .6) - uz * 1.0
    if R_all.buffer(.2).contains(Point(px, pz)) or unary_union(BLD).buffer(.3).contains(Point(px, pz)): px, pz = x - nx * (w / 2 + .6) - ux * 1.0, z - nz * (w / 2 + .6) - uz * 1.0
    if R_all.buffer(.2).contains(Point(px, pz)): continue
    inst('stop_sign', px, pz, 1, math.atan2(-ux, -uz), 'StreetProps'); colcircle(px, pz, .12, 2.5, '止まれの標識')
    mx, mz = x + nx * (w / 2 + .7) + ux * 4.5, z + nz * (w / 2 + .7) + uz * 4.5
    if not R_all.buffer(.2).contains(Point(mx, mz)) and not unary_union(BLD).buffer(.3).contains(Point(mx, mz)):
        inst('curve_mirror', mx, mz, 1, math.atan2(ux, uz) * -1, 'StreetProps'); colcircle(mx, mz, .12, 3, 'カーブミラー')

# =====================================================================
#  8. 出口（つぎのマップへの 入り口）：通行止めの さくと 地下水路の入口
# =====================================================================
EXITS = []
def barricade(mb, x, z, ang, w):
    xf = XF(mb, x, z, ang)
    for s_ in (-1, 1):
        for dz in (-.3, .3): bar(xf, (s_ * w / 2, 0, dz), (s_ * w / 2, 1.0, 0), .04, '#f2c94c', 5)
    for k in range(int(w / .5)):
        u0 = -w / 2 + k * .5; c = '#f2c94c' if k % 2 else '#2b2b2b'
        box(xf, u0, u0 + .5, .7, .95, -.04, .04, col=c)
    for s_ in (-1, 1): cone(xf, s_ * (w / 2 + .6), 0, .4, .25, .7, '#f07a2a', seg=10); box(xf, s_ * (w / 2 + .6) - .25, s_ * (w / 2 + .6) + .25, 0, .04, .15, .65, col='#2b2b2b')
mb = MB('MapExits_barricades')
for eid, nm, p, d in L.EXITS:
    x, z = W(p); ang = {'n': 0, 's': 180, 'e': 90, 'w': -90}[d]
    dirv = {'n': (0, -1), 's': (0, 1), 'e': (1, 0), 'w': (-1, 0)}[d]
    # 外形の 内がわ 1.2m に さく（道の はばに あわせる）
    bx, bz = x - dirv[0] * 1.4, z - dirv[1] * 1.4
    road_w = 6.0
    for n_, k_, ls_, w_ in road_lines:
        if ls_.distance(Point(x, z)) < 4: road_w = w_
    if eid.startswith('chika'):
        # 地下水路の入口：コンクリートの 箱と 鉄のとびら・下へ行く階段
        xf = XF(mb, x - dirv[0] * 3.2, z - dirv[1] * 3.2, ang + 180)
        box(xf, -2.2, 2.2, 0, 2.6, -1.6, 1.6, col='#b9b6ad', top=True); box(xf, -2.35, 2.35, 2.6, 2.8, -1.75, 1.75, col='#9f9c94')
        fr_ = wall_frame('+z', 4.4, 3.2)
        panel(xf, fr_, -1.2, 1.2, 0, 2.1, 0, .05, '#3f4a52')
        for k in range(8): panel(xf, fr_, -1.15 + k * .3, -1.0 + k * .3, .1, 2.0, .05, .08, '#56626b')
        panel(xf, fr_, -1.5, 1.5, 2.15, 2.3, 0, .3, '#9f9c94')
        sign_board(xf, fr_, 0, 2.35, 2.2, .35, nm, '#2f6fb8', '#ffffff', None, d=.31)
        for k in range(3): panel(xf, fr_, -1.3, 1.3, 0, .12, .1 + k * .35, .45 + k * .35, '#a9a59b')
        cx_, cz_ = x - dirv[0] * 3.2, z - dirv[1] * 3.2
        hw, hd = (2.3, 1.7) if d in 'ns' else (1.7, 2.3)
        colbox(cx_ - hw, cz_ - hd, cx_ + hw, cz_ + hd, 3, nm + 'の入口')
        trig = (x - dirv[0] * 6.2, z - dirv[1] * 6.2)
    else:
        barricade(mb, bx, bz, ang, road_w - 1.0)
        trig = (x - dirv[0] * 4.0, z - dirv[1] * 4.0)
        ex, ez = -dirv[1], dirv[0]
        colseg((bx - ex * (road_w / 2 + 1.5), bz - ez * (road_w / 2 + 1.5)), (bx + ex * (road_w / 2 + 1.5), bz + ez * (road_w / 2 + 1.5)), .3, 1.2, nm + 'へは まだ行けない')
    EXITS.append({'id': eid, 'name': nm, 'x': round(trig[0], 2), 'z': round(trig[1], 2), 'r': 3.2, 'dir': list(dirv), 'ax': round(x, 2), 'az': round(z, 2), 'ready': False})
put(mb, 'MapExits')

# =====================================================================
#  9. ミニマップ用のデータと 書き出し
# =====================================================================
def rings_of(g, tol=.25):
    out = []
    for p in polys(g):
        p = p.simplify(tol)
        for q in polys(p):
            out.append([[round(c[0], 1), round(c[1], 1)] for c in q.exterior.coords] + [])
            for h in q.interiors: out.append({'hole': [[round(c[0], 1), round(c[1], 1)] for c in h.coords]})
    return out
def poly_list(g, tol=.25):
    res = []
    for p in polys(g):
        p = p.simplify(tol)
        for q in polys(p):
            res.append([[[round(c[0], 1), round(c[1], 1)] for c in q.exterior.coords]] + [[[round(c[0], 1), round(c[1], 1)] for c in h.coords] for h in q.interiors])
    return res
MINI['outline'] = [[round(c[0], 1), round(c[1], 1)] for c in O.exterior.coords]
MINI['roads'] = poly_list(R_all); MINI['side'] = poly_list(SIDE.union(PLAZA)); MINI['paths'] = poly_list(PATH.union(DPATH)); MINI['water'] = poly_list(Wfull)
MINI['grass'] = poly_list(FREE.intersection(GRASSG).union(YARD).difference(DIRTG)); MINI['park'] = poly_list(PARK); MINI['dirt'] = poly_list(DIRTG)
MINI['trees'] = [[round(x, 1), round(z, 1), k[0]] for x, z, k, s in TREE_POS if k != 'bush']
for t, p, c in L.LABELS: x, z = W(p); MINI['labels'].append([t, round(x, 1), round(z, 1), c])
sx, sz = W((640, 688))
KG.finish_palette()
# いらなくなった型（テンプレート）のオブジェクトは もう ない。共有メッシュは インスタンスが使う
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_apply=True, export_yup=True, export_image_format='AUTO', export_extras=False)
bounds = [round(c, 2) for c in O.bounds]
data = dict(COL)
data.update({'field': True, 'name': '風見ニュータウン', 'bounds': None, 'aabb': bounds, 'start': [round(sx, 2), 0, round(sz, 2)], 'exits': EXITS,
             'mini': MINI, 'camera': {'pitch': 45, 'fov': 45, 'dist': 13}})
with open(out.replace('.glb', '.col.json'), 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
nv = sum(len(o.data.vertices) for o in bpy.data.objects if o.type == 'MESH')
print('wrote', out, 'objects', len(bpy.data.objects), 'verts(all instances)', nv, 'box', len(COL['box']), 'circle', len(COL['circle']), 'seg', len(COL['seg']))
