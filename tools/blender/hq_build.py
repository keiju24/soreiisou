# 風情ウォッチバスターズの本部（2階建ての消防署＋屋上）を Blender で作り、models/hq.glb に書き出す。
#   使い方：python tools/blender/hq_build.py models/hq.glb   （pip の bpy でも、Blender の Python でもよい。Pillow・numpy を使う）
#
# 前の版（ゲームのコードで箱を並べていた本部）と同じ間取り・大きさで、家具・内装をつくりこんだもの。
#   幅 RW 22m × 奥行き RD 12m、1階の高さ FH 4.6m。手前の壁はなく、ドールハウスのように上から見る
#   1F：受付・待合・ロッカー（防火服）／工房（ヘンリーの作業場）／出動口（救急車・シャッター）
#   2F：指令室（大モニター・指令台・通信機ラック・作戦テーブル・休憩コーナー・結成ボード・募集端末）
#   屋上：手すり・ホース乾燥塔・足場・室外機・給水タンク・朕銭ガシャ
#   1F→2F の階段は奥の壁ぞい（左から右へ）、2F→屋上は その手前（右から左へ）。2F から 1F へ すべり棒
#
# 座標：コードの中は ゲームと同じ（x 右、y 上、z 手前が 0・奥が −12）。Blender には (x, −z, y) で置く
# 書き出す glb のいちばん上の節：F1・F2・RF（屋上）・ST1（1F→2F 階段）・ST2（2F→屋上 階段）
#   → 見る側で「今いる階だけ見せる」ができる。床・壁は階ごとに 1 つのメッシュにまとめて軽くしてある
import bpy, bmesh, sys, os, math, random
import numpy as np
from mathutils import Vector, Matrix
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
out = sys.argv[-1] if sys.argv[-1].endswith('.glb') else os.path.join(ROOT, 'models', 'hq.glb')
rnd = random.Random(7)

RW, RD, FH, SL = 22.0, 12.0, 4.6, 0.3
WH = FH - SL
ST = dict(x0=1.4, x1=7.8, z0=-RD, z1=-10.5, n=16)
S2 = dict(xa=2.2, xb=8.6, z0=-10.3, z1=-8.5, n=16)
RY = FH * 2
POLE = (15.6, -5.6)          # すべり棒（2F → 1F）
CEIL_LIGHTS = False          # 天井から下がる蛍光灯（上から見るゲームのカメラだと 宙にういて見えるので 出さない）

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene

# =====================================================================
#  テクスチャ（numpy / Pillow で作って、glb の中に入れる）
# =====================================================================
from PIL import Image, ImageDraw, ImageFont, ImageFilter
def font_path():
    # ラノベPOP v2（fonts/ の woff2 を一時的に otf にもどす）→ なければ システムの日本語フォント
    w = os.path.join(ROOT, 'fonts', 'LightNovelPOPv2.woff2')
    if os.path.exists(w):
        try:
            from fontTools.ttLib import TTFont
            p = os.path.join(bpy.app.tempdir or '/tmp', 'lnpop.otf'); f = TTFont(w); f.flavor = None; f.save(p); return p
        except Exception as e: print('font', e)
    for p in ['/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf', '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf']:
        if os.path.exists(p): return p
    return None
FONT = font_path()
def F(sz): return ImageFont.truetype(FONT, sz) if FONT else ImageFont.load_default()

def to_image(name, pil):
    pil = pil.convert('RGBA'); w, h = pil.size
    a = np.asarray(pil, dtype=np.float32)[::-1] / 255.0
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(a.ravel()); img.file_format = 'PNG'; img.pack()
    return img
def noise(w, h, scale, seed):
    r = np.random.default_rng(seed); g = r.random((h // scale + 2, w // scale + 2)).astype(np.float32)
    im = Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32) / 255.0
def tex_concrete(seed=1, base=(150, 150, 146)):
    w = h = 512
    n = noise(w, h, 64, seed) * .55 + noise(w, h, 16, seed + 1) * .3 + noise(w, h, 4, seed + 2) * .15
    sp = (np.random.default_rng(seed + 3).random((h, w)) > .985) * -.25
    k = (.86 + (n - .5) * .22 + sp)[..., None]
    a = np.clip(np.array(base, np.float32)[None, None] * k, 0, 255).astype(np.uint8)
    return Image.fromarray(a)
def tex_tiles():
    w = h = 512; im = Image.new('RGB', (w, h), (214, 206, 186)); d = ImageDraw.Draw(im)
    for i in range(4):
        for j in range(4):
            c = (226, 219, 200) if (i + j) % 2 else (196, 186, 162)
            d.rectangle([i * 128 + 3, j * 128 + 3, i * 128 + 124, j * 128 + 124], fill=c)
    a = np.asarray(im, np.float32) * (.94 + noise(w, h, 32, 5)[..., None] * .1)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
def tex_wood():
    w, h = 512, 512; r = np.random.default_rng(11)
    a = np.zeros((h, w, 3), np.float32)
    rows = 8; ph = h // rows
    for k in range(rows):
        base = np.array([150, 104, 66], np.float32) * (.85 + r.random() * .3)
        y0 = k * ph; x = np.arange(w)
        grain = (np.sin(x[None, :] / (6 + r.random() * 6) + noise(w, ph, 8, 20 + k)[:, :] * 8) * .5 + .5)
        a[y0:y0 + ph] = base[None, None] * (.86 + grain[..., None] * .16)
        a[y0:y0 + 2] *= .55
        off = int(r.random() * w); a[y0:y0 + ph, off:off + 2] *= .6
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
def tex_plaster(base):
    w = h = 256; n = noise(w, h, 32, 31) * .6 + noise(w, h, 4, 32) * .4
    a = np.array(base, np.float32)[None, None] * (.95 + (n[..., None] - .5) * .1)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
def tex_hazard():
    w, h = 256, 64; im = Image.new('RGB', (w, h), (230, 186, 40)); d = ImageDraw.Draw(im)
    for x in range(-64, w + 64, 64): d.polygon([(x, h), (x + 32, h), (x + 32 + h, 0), (x + h, 0)], fill=(28, 26, 24))
    return im
def tex_roof():
    w = h = 512
    n = noise(w, h, 64, 41) * .6 + noise(w, h, 8, 42) * .4
    a = np.array([86, 128, 98], np.float32)[None, None] * (.88 + (n[..., None] - .5) * .25)
    a[::128, :] *= .7; a[:, ::128] *= .7
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
def tex_epoxy():
    w = h = 512; n = noise(w, h, 64, 51) * .7 + noise(w, h, 8, 52) * .3
    a = np.array([118, 126, 120], np.float32)[None, None] * (.9 + (n[..., None] - .5) * .18)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

def sign_img(text, w, h, bg, fg, border=None, size=None, sub=None):
    im = Image.new('RGB', (w, h), bg); d = ImageDraw.Draw(im)
    if border: d.rectangle([6, 6, w - 7, h - 7], outline=border, width=10)
    sz = size or int(h * .58); f = F(sz)
    while d.textlength(text, font=f) > w * .88 and sz > 10: sz -= 2; f = F(sz)
    ty = h / 2 if not sub else h * .4
    d.text((w / 2, ty), text, font=f, fill=fg, anchor='mm')
    if sub: d.text((w / 2, h * .78), sub, font=F(int(h * .2)), fill=fg, anchor='mm')
    return im

# =====================================================================
#  マテリアル
# =====================================================================
MATS = {}
def mat(name, col=(.8, .8, .8), rough=.7, metal=0.0, img=None, emit=0.0, alpha=None):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*col, 1) if len(col) == 3 else col
    b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    if img is not None:
        t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = img
        m.node_tree.links.new(t.outputs['Color'], b.inputs['Base Color'])
        if emit: m.node_tree.links.new(t.outputs['Color'], b.inputs['Emission Color'])
    elif emit:
        b.inputs['Emission Color'].default_value = (*col, 1)
    if emit: b.inputs['Emission Strength'].default_value = emit
    MATS[name] = m; return m
def glass_mat(name, col, alpha):
    m = mat(name, col, .05)
    b = m.node_tree.nodes.get('Principled BSDF'); b.inputs['Alpha'].default_value = alpha
    try: m.surface_render_method = 'BLENDED'
    except Exception: pass
    return m
def hexc(h):
    h = h.lstrip('#'); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x ** 2.2 for x in c)       # sRGB → リニア
def C(h, rough=.7, metal=0.0, emit=0.0): return mat('c' + h + f'{rough}{metal}{emit}', hexc(h), rough, metal, emit=emit)

T = {}
def timg(name, fn):
    if name not in T: T[name] = to_image(name, fn())
    return T[name]
M = dict(
    concrete=mat('concrete', img=timg('concrete', lambda: tex_concrete(1)), rough=.85),
    epoxy=mat('epoxy', img=timg('epoxy', tex_epoxy), rough=.45),
    tiles=mat('tiles', img=timg('tiles', tex_tiles), rough=.5),
    woodf=mat('wood_floor', img=timg('wood', tex_wood), rough=.55),
    wall1=mat('wall1', img=timg('plaster1', lambda: tex_plaster((226, 220, 204))), rough=.9),
    wall2=mat('wall2', img=timg('plaster2', lambda: tex_plaster((220, 226, 214))), rough=.9),
    hazard=mat('hazard', img=timg('hazard', tex_hazard), rough=.6),
    roof=mat('roof', img=timg('roof', tex_roof), rough=.8),
    ink=C('#1d1b19', .8), dark=C('#2c2d2a', .6), steel=C('#8c918a', .35, .6), steel2=C('#5a5f58', .5, .4),
    chrome=C('#d7d9d3', .2, .9), red=C('#b23a2a', .5), red2=C('#7a2a1e', .6), yellow=C('#d8b23f', .5), cream=C('#ece2c6', .8),
    wood=C('#9a7148', .6), wood2=C('#5e4027', .6), wdark=C('#43301f', .6), green=C('#5f8a45', .7), olive=C('#5d6b4a', .7),
    blue=C('#4f6f86', .6), navy=C('#2b3a4a', .6), white=C('#f1ece0', .6), glass=C('#9fc6dc', .1, 0, .15),
    sky=C('#cfe6f2', .9, 0, 1.2), crt=C('#9fe28c', .4, 0, 2.0), lampR=C('#ff4a33', .4, 0, 3.0), lampY=C('#ffd04a', .4, 0, 3.0),
    lampG=C('#8ff07a', .4, 0, 3.0), lampW=C('#fff6dc', .4, 0, 4.0), rubber=C('#1c1c1d', .9), rust=C('#a5452a', .55, .3),
    wain1=C('#7d6a4f', .7), wain2=C('#55697a', .7), base=C('#3a3530', .7), cork=C('#b38b57', .9), leaf=C('#4f8a3d', .7),
    leaf2=C('#6aa64c', .7), pot=C('#9a5a35', .8), cushion=C('#c0533f', .8), cushion2=C('#4f6f86', .8), paper=C('#f4efe2', .9),
    khaki=C('#b3a477', .8), orange=C('#e07a35', .6), pipe=C('#e2e0d8', .4, .2),
)

# =====================================================================
#  形をつくる道具（ゲームの座標で書く）
# =====================================================================
def P(x, y, z): return Vector((x, -z, y))
COLS = {}
def coll(name):
    if name not in COLS:
        c = bpy.data.collections.new(name); scn.collection.children.link(c); COLS[name] = c
    return COLS[name]
CUR = ['F1']
def link(o): coll(CUR[0]).objects.link(o); return o
def uv_box(bm, tile):
    uv = bm.loops.layers.uv.get('UVMap') or bm.loops.layers.uv.new('UVMap')   # 名前をそろえる（まとめたときに絵がずれないように）
    for f in bm.faces:
        n = f.normal; ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            co = l.vert.co
            u, v = [(co.y, co.z), (co.x, co.z), (co.x, co.y)][ax]
            l[uv].uv = (u / tile, v / tile)
def box(m, x0, x1, y0, y1, z0, z1, bevel=0.0, tile=1.0, name='box'):
    bm = bmesh.new()
    a, b = P(min(x0, x1), min(y0, y1), max(z0, z1)), P(max(x0, x1), max(y0, y1), min(z0, z1))
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((a.x + (v.co.x + .5) * (b.x - a.x), a.y + (v.co.y + .5) * (b.y - a.y), a.z + (v.co.z + .5) * (b.z - a.z)))
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect='EDGES', profile=.5)
    bm.normal_update(); uv_box(bm, tile)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(m)
    if bevel > 0:
        for p in me.polygons: p.use_smooth = False
    return link(bpy.data.objects.new(name, me))
def cyl(m, x, y, z, r, h, axis='y', seg=20, cap=True, name='cyl'):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=cap, segments=seg, radius1=r, radius2=r, depth=h)
    rot = {'y': Matrix.Identity(4), 'x': Matrix.Rotation(math.pi / 2, 4, 'Y'), 'z': Matrix.Rotation(math.pi / 2, 4, 'X')}[axis]
    bmesh.ops.transform(bm, matrix=Matrix.Translation(P(x, y, z)) @ rot, verts=bm.verts)
    uv_box(bm, 1); me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    return link(bpy.data.objects.new(name, me))
def bar(m, a, b, r, seg=12, name='bar'):
    A, B = P(*a), P(*b); d = B - A; L = d.length
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=L)
    q = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((A + B) / 2) @ q, verts=bm.verts)
    uv_box(bm, 1); me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    return link(bpy.data.objects.new(name, me))
def ball(m, x, y, z, rx, ry, rz, seg=16, name='ball'):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=1)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(P(x, y, z)) @ Matrix.Diagonal((rx, rz, ry, 1)), verts=bm.verts)
    uv_box(bm, 1); me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(m)
    for p in me.polygons: p.use_smooth = True
    return link(bpy.data.objects.new(name, me))
def plane(m, cx, cy, cz, w, h, face, name='plane'):
    # face：'+z'（手前を向く）'-z' '+x' '-x' '+y'（上を向く）
    hw, hh = w / 2, h / 2
    if face == '+z': q = [(cx - hw, cy - hh, cz), (cx + hw, cy - hh, cz), (cx + hw, cy + hh, cz), (cx - hw, cy + hh, cz)]
    elif face == '-z': q = [(cx + hw, cy - hh, cz), (cx - hw, cy - hh, cz), (cx - hw, cy + hh, cz), (cx + hw, cy + hh, cz)]
    elif face == '+x': q = [(cx, cy - hh, cz - hw), (cx, cy - hh, cz + hw), (cx, cy + hh, cz + hw), (cx, cy + hh, cz - hw)]
    elif face == '-x': q = [(cx, cy - hh, cz + hw), (cx, cy - hh, cz - hw), (cx, cy + hh, cz - hw), (cx, cy + hh, cz + hw)]
    else: q = [(cx - hw, cy, cz + hh), (cx + hw, cy, cz + hh), (cx + hw, cy, cz - hh), (cx - hw, cy, cz - hh)]
    me = bpy.data.meshes.new(name); me.from_pydata([P(*v) for v in q], [], [(0, 1, 2, 3)]); me.update()
    uv = me.uv_layers.new(name='UVMap'); [setattr(uv.data[i], 'uv', t) for i, t in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)])]
    me.materials.append(m)
    return link(bpy.data.objects.new(name, me))
SIGNS = {}
def sign(text, cx, cy, cz, w, h, face, bg='#cfae45', fg='#1d1b19', border='#1d1b19', px=None, sub=None, emit=0.0):
    key = (text, bg, fg, border, sub)
    if key not in SIGNS:
        W = px or int(512 * w / max(w, h)); H = int(W * h / w)
        SIGNS[key] = mat('sign_' + text + str(len(SIGNS)), img=to_image('sign_' + str(len(SIGNS)), sign_img(text, W, H, bg, fg, border, sub=sub)), rough=.7, emit=emit)
    off = {'+z': (0, 0, .006), '-z': (0, 0, -.006), '+x': (.006, 0, 0), '-x': (-.006, 0, 0), '+y': (0, .006, 0)}[face]
    d = {'+z': (0, 0, -.03), '-z': (0, 0, .03), '+x': (-.03, 0, 0), '-x': (.03, 0, 0), '+y': (0, -.03, 0)}[face]
    # 板（うしろの厚み）＋ 絵
    bx = (cx + d[0] - (w / 2 + .03 if face in '+z-z' or face == '+y' else .03), cx + d[0] + (w / 2 + .03 if face in '+z-z' or face == '+y' else .03))
    if face in ('+z', '-z'): box(M['ink'], cx - w / 2 - .03, cx + w / 2 + .03, cy - h / 2 - .03, cy + h / 2 + .03, cz + d[2] - .02, cz + d[2] + .02)
    elif face in ('+x', '-x'): box(M['ink'], cx + d[0] - .02, cx + d[0] + .02, cy - h / 2 - .03, cy + h / 2 + .03, cz - w / 2 - .03, cz + w / 2 + .03)
    return plane(SIGNS[key], cx + off[0], cy + off[1], cz + off[2], w, h, face, 'sign')
def picture(img_fn, key, cx, cy, cz, w, h, face, emit=0.0, rough=.8):
    if key not in SIGNS: SIGNS[key] = mat('pic_' + key, img=to_image('pic_' + key, img_fn()), rough=rough, emit=emit)
    off = {'+z': (0, 0, .006), '-z': (0, 0, -.006), '+x': (.006, 0, 0), '-x': (-.006, 0, 0), '+y': (0, .006, 0)}[face]
    return plane(SIGNS[key], cx + off[0], cy + off[1], cz + off[2], w, h, face, 'pic')

# =====================================================================
#  建物の殻（床・壁・腰壁・はば木・窓・手前の切り口）
# =====================================================================
def shell(i, floor_parts, wall_m, wain_m, windows):
    y = i * FH
    for (m, x0, x1, z0, z1, tile) in floor_parts: box(m, x0, x1, y - SL, y, z0, z1, tile=tile, name='floor')
    # 壁（奥・左・右）。右の壁は 1F だけ シャッターの口をあける
    box(wall_m, -.3, RW + .3, y, y + WH, -RD - .3, -RD, tile=2.5, name='wall')
    box(wall_m, -.3, 0, y, y + WH, -RD, 0, tile=2.5, name='wall')
    if i == 0:
        box(wall_m, RW, RW + .3, y, y + WH, -RD, -9.8, tile=2.5); box(wall_m, RW, RW + .3, y, y + WH, -2.4, 0, tile=2.5)
        box(wall_m, RW, RW + .3, y + 3.85, y + WH, -9.8, -2.4, tile=2.5)
    else: box(wall_m, RW, RW + .3, y, y + WH, -RD, 0, tile=2.5)
    # 腰壁（下 1m）・見切り・はば木
    for (a, b, c, d) in [(0, RW, -RD, -RD + .04)]:
        box(wain_m, a, b, y, y + 1.0, c, d, tile=1); box(M['wood2'], a, b, y + 1.0, y + 1.06, c, d + .03); box(M['base'], a, b, y, y + .12, c, d + .02)
    for (zA, zB) in ([(-RD, 0)]):
        box(wain_m, 0, .04, y, y + 1.0, zA, zB); box(M['wood2'], 0, .07, y + 1.0, y + 1.06, zA, zB); box(M['base'], 0, .06, y, y + .12, zA, zB)
    rz = [(-RD, -9.8), (-2.4, 0)] if i == 0 else [(-RD, 0)]
    for (zA, zB) in rz:
        box(wain_m, RW - .04, RW, y, y + 1.0, zA, zB); box(M['wood2'], RW - .07, RW, y + 1.0, y + 1.06, zA, zB); box(M['base'], RW - .06, RW, y, y + .12, zA, zB)
    # 窓（左の壁）：外の明るい空・枠・横の桟
    for (z0, z1, y0, y1) in windows:
        box(M['sky'], .005, .02, y + y0, y + y1, z0, z1)
        for zz in (z0, z1): box(M['white'], 0, .1, y + y0 - .06, y + y1 + .06, zz - .05, zz + .05)
        for yy in (y0, y1): box(M['white'], 0, .12, y + yy - .05, y + yy + .05, z0 - .05, z1 + .05)
        box(M['white'], 0, .07, y + (y0 + y1) / 2 - .02, y + (y0 + y1) / 2 + .02, z0, z1)
        box(M['white'], 0, .07, y + y0, y + y1, (z0 + z1) / 2 - .02, (z0 + z1) / 2 + .02)
        box(M['cream'], 0, .16, y + y0 - .1, y + y0 - .04, z0 - .1, z1 + .1)    # 窓台
    # 手前の切り口（黒いふち）と 床のふちの黄黒しま
    box(M['ink'], -.32, RW + .32, y - SL - .02, y + .02, -.02, .22)
    box(M['ink'], -.32, .02, y, y + WH, -.02, .22); box(M['ink'], RW - .02, RW + .32, y, y + WH, -.02, .22)
    box(M['hazard'], 0, RW, y + .002, y + .012, -.5, -.1, tile=.8)
    # 壁の上のふち
    box(M['ink'], -.32, RW + .32, y + WH, y + WH + .03, -RD - .32, -RD + .02)

def wall_clock(x, y, z, face='+z'):
    cyl(M['white'], x, y, z + .03, .28, .05, 'z', 28); cyl(M['ink'], x, y, z + .005, .31, .04, 'z', 28)
    box(M['ink'], x - .012, x + .012, y, y + .2, z + .06, z + .07); box(M['ink'], x, x + .15, y - .012, y + .012, z + .06, z + .07)
def extinguisher(x, y, z):
    cyl(M['red'], x, y + .3, z, .1, .55, 'y', 16); ball(M['red'], x, y + .58, z, .1, .06, .1); box(M['ink'], x - .03, x + .03, y + .6, y + .7, z - .02, z + .02)
    bar(M['ink'], (x + .05, y + .65, z), (x + .14, y + .4, z + .06), .015)
def plant(x, z, y=0, s=1.0):
    cyl(M['pot'], x, y + .22 * s, z, .24 * s, .44 * s, 'y', 18); cyl(M['dark'], x, y + .43 * s, z, .21 * s, .02, 'y', 18)
    for k in range(9):
        a = k / 9 * math.tau + rnd.random() * .4; r = (.12 + rnd.random() * .18) * s
        ball(M['leaf'] if k % 2 else M['leaf2'], x + math.cos(a) * r, y + (.7 + rnd.random() * .45) * s, z + math.sin(a) * r, .22 * s, .3 * s, .1 * s, 10)
def chair(x, z, y=0, face=0, m=None):
    m = m or M['navy']; c, s = math.cos(face), math.sin(face)
    R = lambda dx, dz: (x + dx * c - dz * s, z + dx * s + dz * c)
    cx, cz = R(0, 0); box(m, cx - .25, cx + .25, y + .45, y + .53, cz - .25, cz + .25, bevel=.02)
    bx, bz = R(0, .24); box(m, bx - .25, bx + .25, y + .53, y + 1.05, bz - .03, bz + .03, bevel=.02)
    cyl(M['steel2'], x, y + .25, z, .03, .4);
    for k in range(5):
        a = k / 5 * math.tau; bar(M['steel2'], (x, y + .06, z), (x + math.cos(a) * .28, y + .04, z + math.sin(a) * .28), .02)
        ball(M['rubber'], x + math.cos(a) * .28, y + .035, z + math.sin(a) * .28, .035, .035, .035, 8)
def monitor_screen(x, y, z, w, h, mat_scr, face='+z'):
    box(M['dark'], x - w / 2 - .04, x + w / 2 + .04, y - h / 2 - .04, y + h / 2 + .04, z - .05, z, bevel=.01)
    box(mat_scr, x - w / 2, x + w / 2, y - h / 2, y + h / 2, z, z + .004)

# ---- 画面・張り紙の絵 ----
def img_radar():
    W, H = 1024, 320; im = Image.new('RGB', (W, H), (8, 20, 10)); d = ImageDraw.Draw(im)
    for x in range(0, W, 48): d.line([(x, 0), (x, H)], fill=(36, 92, 40), width=2)
    for y in range(0, H, 48): d.line([(0, y), (W, y)], fill=(36, 92, 40), width=2)
    for (a, b, c, e) in [(100, 80, 320, 230), (430, 50, 600, 140), (690, 160, 940, 270)]: d.rectangle([a, b, c, e], fill=(40, 96, 44))
    cx, cy = 512, 160; d.line([(cx, cy), (cx + 300, cy - 120)], fill=(160, 240, 140), width=4)
    for r in (60, 120, 180): d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(80, 170, 80), width=2)
    for (x, y, n) in [(210, 150, '公園'), (520, 95, '商店街'), (810, 215, '繁華街')]:
        d.ellipse([x - 14, y - 14, x + 14, y + 14], fill=(220, 245, 110)); d.text((x + 22, y), n, font=F(30), fill=(170, 240, 150), anchor='lm')
    d.text((18, 24), 'FUJO BUSTERS  BUSUI RADAR', font=F(26), fill=(170, 240, 150), anchor='lm')
    for y in range(0, H, 4): d.line([(0, y), (W, y)], fill=(0, 0, 0), width=1)
    return im
def img_graph():
    W, H = 256, 160; im = Image.new('RGB', (W, H), (12, 24, 14)); d = ImageDraw.Draw(im)
    for i in range(7): d.line([(12, 18 + i * 20), (40 + (i * 53) % 190, 18 + i * 20)], fill=(150, 230, 130), width=5)
    return im
def img_map():
    W, H = 768, 384; im = Image.new('RGB', (W, H), (220, 208, 170)); d = ImageDraw.Draw(im)
    for i in range(10): d.line([(0, i * 40 + 10), (W, i * 40 + 30)], fill=(150, 132, 92), width=6); d.line([(i * 80, 0), (i * 80 + 30, H)], fill=(150, 132, 92), width=6)
    d.ellipse([120, 90, 300, 220], fill=(110, 150, 80)); d.rectangle([420, 60, 640, 160], fill=(170, 120, 90)); d.ellipse([500, 230, 620, 330], fill=(90, 140, 190))
    for (x, y) in [(200, 150), (540, 110), (560, 280)]: d.ellipse([x - 16, y - 16, x + 16, y + 16], fill=(200, 50, 40), outline=(30, 20, 20), width=4)
    d.text((24, 30), '風情町 全図', font=F(40), fill=(60, 40, 20), anchor='lm')
    return im
def img_whiteboard():
    W, H = 640, 320; im = Image.new('RGB', (W, H), (244, 242, 236)); d = ImageDraw.Draw(im)
    d.text((24, 40), '本日のブスイ反応', font=F(44), fill=(40, 58, 80), anchor='lm')
    for k, (t, c) in enumerate([('公園：大', (180, 50, 40)), ('商店街：中', (40, 58, 80)), ('駅前：小', (40, 58, 80)), ('住宅街：―', (40, 58, 80))]):
        d.text((50, 110 + k * 52), t, font=F(36), fill=c, anchor='lm')
    d.line([(360, 100), (600, 280)], fill=(180, 50, 40), width=6); d.ellipse([420, 130, 560, 250], outline=(40, 90, 160), width=6)
    return im
def img_formboard():
    W, H = 512, 320; im = Image.new('RGB', (W, H), (190, 150, 100)); d = ImageDraw.Draw(im)
    d.text((W / 2, 40), '結成ボード', font=F(44), fill=(30, 26, 24), anchor='mm')
    for i in range(4):
        x = 28 + i * 120; d.rectangle([x, 80, x + 100, 250], fill=(240, 232, 210))
        d.rectangle([x + 10, 90, x + 90, 170], fill=[(169, 64, 47), (79, 111, 134), (95, 138, 69), (154, 95, 125)][i])
        d.text((x + 50, 210), ['リーダー', 'なかま1', 'なかま2', 'なかま3'][i], font=F(22), fill=(30, 26, 24), anchor='mm')
        d.ellipse([x + 42, 74, x + 58, 90], fill=(200, 40, 40))
    return im
def img_recruit():
    W, H = 256, 160; im = Image.new('RGB', (W, H), (12, 24, 14)); d = ImageDraw.Draw(im)
    d.text((W / 2, 56), 'マルチ募集', font=F(36), fill=(160, 240, 140), anchor='mm'); d.text((W / 2, 110), 'ONLINE', font=F(28), fill=(160, 240, 140), anchor='mm')
    return im
def img_poster(t, c):
    def f():
        W, H = 256, 360; im = Image.new('RGB', (W, H), c); d = ImageDraw.Draw(im)
        d.rectangle([10, 10, W - 10, H - 10], outline=(30, 26, 24), width=6)
        d.text((W / 2, 80), t[0], font=F(46), fill=(30, 26, 24), anchor='mm'); d.text((W / 2, 150), t[1], font=F(34), fill=(30, 26, 24), anchor='mm')
        for k in range(5): d.line([(30, 210 + k * 26), (W - 30, 210 + k * 26)], fill=(90, 80, 70), width=4)
        return im
    return f
def img_vending():
    W, H = 256, 384; im = Image.new('RGB', (W, H), (235, 240, 245)); d = ImageDraw.Draw(im)
    for r in range(3):
        for c in range(4):
            x, y = 18 + c * 58, 30 + r * 90; d.rounded_rectangle([x, y, x + 44, y + 72], 10, fill=[(200, 60, 50), (60, 120, 200), (240, 190, 60), (80, 170, 90)][(r + c) % 4])
            d.rectangle([x + 4, y + 78, x + 40, y + 84], fill=(30, 30, 30))
    d.rectangle([20, 300, 236, 360], fill=(40, 40, 46))
    return im

# =====================================================================
#  1F：受付・待合・ロッカー・工房・出動口
# =====================================================================
def build1F():
    CUR[0] = 'F1'; y = 0
    shell(0, [(M['concrete'], -.3, 9.4, -RD - .3, .2, 2.0), (M['concrete'], 9.4, 16.8, -RD - .3, .2, 2.0), (M['epoxy'], 16.8, RW + .3, -RD - .3, .2, 3.0)],
          M['wall1'], M['wain1'], windows=[(-6.9, -4.7, 1.2, 2.9)])
    # 受付まわりの床（タイル）
    box(M['tiles'], .3, 9.0, .0, .012, -9.6, -.6, tile=1.0)
    # ---- 受付カウンター（L字・木の天板・前に表札）----
    box(M['wood2'], 2.2, 7.2, 0, 1.0, -6.4, -5.75, bevel=.02); box(M['wood2'], 2.2, 2.85, 0, 1.0, -8.4, -6.4, bevel=.02)
    box(M['wood'], 2.1, 7.3, 1.0, 1.08, -6.48, -5.62, bevel=.015); box(M['wood'], 2.1, 2.95, 1.0, 1.08, -8.5, -6.4, bevel=.015)
    box(M['wdark'], 2.4, 7.0, .12, .9, -5.75, -5.72)           # 前のへこみ
    for x in (3.2, 4.4, 5.6): box(M['wood'], x, x + .05, .14, .88, -5.73, -5.71)
    sign('風情ウォッチバスターズ 本部', 4.7, .62, -5.70, 2.4, .42, '+z', bg='#e6dcc0', fg='#a9402f', border='#5e4027')
    # カウンターの上：パソコン・キーボード・電話・呼び鈴・書類トレイ
    box(M['dark'], 3.05, 3.15, 1.08, 1.32, -6.25, -6.15); monitor_screen(3.1, 1.52, -6.05, .62, .4, M['crt'])
    box(M['dark'], 2.85, 3.4, 1.08, 1.1, -5.98, -5.78, bevel=.005)
    box(M['dark'], 4.0, 4.32, 1.08, 1.16, -6.2, -5.98, bevel=.02); bar(M['dark'], (4.04, 1.2, -6.09), (4.28, 1.2, -6.09), .03)
    cyl(M['chrome'], 6.6, 1.11, -6.0, .09, .06); ball(M['chrome'], 6.6, 1.15, -6.0, .1, .07, .1)
    for k in range(3): box(M['steel2'], 5.2, 5.6, 1.08 + k * .07, 1.1 + k * .07, -6.3, -6.0); box(M['paper'], 5.23, 5.57, 1.1 + k * .07, 1.12 + k * .07, -6.28, -6.02)
    chair(4.2, -7.0, face=math.pi)
    # 受付のうしろ：書類キャビネット・掲示板・時計
    for k in range(3):
        x0 = .3 + k * .6; box(M['olive'], x0, x0 + .56, 0, 1.4, -RD, -RD + .62, bevel=.01)
        for yy in (.12, .55, .98): box(M['steel'], x0 + .2, x0 + .36, yy + .25, yy + .29, -RD + .62, -RD + .65)
    box(M['cork'], .02, .08, 1.3, 2.6, -9.6, -7.2); box(M['wood2'], .02, .1, 1.25, 2.65, -9.65, -7.15)
    for (zz, yy, c) in [(-9.1, 2.1, '#f4efe2'), (-8.3, 1.9, '#d9c27a'), (-7.7, 2.25, '#a8c2c9'), (-8.6, 1.55, '#f4efe2')]:
        box(C(c, .9), .08, .09, yy - .25, yy + .25, zz - .22, zz + .22); ball(M['red'], .095, yy + .2, zz, .025, .025, .02, 8)
    wall_clock(15.8, 3.3, -RD + .02)
    sign('受付', 4.7, 2.75, -6.0, 1.6, .56, '+z', bg='#cfae45')                # カウンターの上につるす
    for dx in (-.6, .6): bar(M['steel'], (4.7 + dx, 3.03, -6.03), (4.7 + dx, WH, -6.03), .008)
    # ---- 待合：ベンチ（クッション）・植木・自販機・ウォーターサーバー・雑誌ラック ----
    for (x0, x1) in [(1.0, 3.6), (4.2, 6.8)]:
        box(M['steel2'], x0, x1, .38, .44, -2.3, -1.7); box(M['cushion2'], x0 + .05, x1 - .05, .44, .54, -2.28, -1.72, bevel=.03)
        box(M['cushion2'], x0 + .05, x1 - .05, .54, .95, -2.32, -2.22, bevel=.03)
        for x in (x0 + .1, x1 - .15): box(M['steel2'], x, x + .05, 0, .38, -2.25, -1.75)
    plant(.7, -4.0); plant(7.6, -1.3, s=.8)
    box(M['red'], 7.4, 8.4, 0, 1.85, -3.6, -2.9, bevel=.03); picture(img_vending, 'vend', 7.9, 1.15, -2.89, .78, 1.15, '+z', emit=.6)
    box(M['dark'], 7.6, 8.2, .2, .45, -2.92, -2.88)
    box(M['white'], 6.9, 7.25, 0, 1.1, -3.5, -3.15, bevel=.03); cyl(M['glass'], 7.075, 1.32, -3.32, .14, .44); cyl(M['blue'], 7.075, .78, -3.13, .03, .06, 'z')
    box(M['wood'], .1, .5, 0, 1.0, -1.4, -.8); [box(C(c), .12, .48, .3 + k * .25, .32 + k * .25, -1.38, -.82) for k, c in enumerate(['#c0533f', '#4f6f86', '#d8b23f'])]
    # ---- ロッカーと防火服かけ（左の壁ぞい・手前）----
    for k in range(3):
        z0 = -3.6 + k * .65
        box(M['olive'], .02, .58, 0, 2.0, z0, z0 + .62, bevel=.01)
        for yy in (1.62, 1.7, 1.78): box(M['ink'], .58, .59, yy, yy + .03, z0 + .12, z0 + .5)
        box(M['chrome'], .58, .61, .9, 1.15, z0 + .48, z0 + .53)
    # 防火服（ヘルメット・上着）を壁のフックに（受付の右うしろ）
    for k in range(4):
        x = 8.4 + k * .0; z = -RD + .15
    for k in range(3):
        x = 7.7 + k * .55
        box(M['steel'], x - .03, x + .03, 1.7, 1.78, -RD, -RD + .12)
        box(M['khaki'], x - .22, x + .22, .9, 1.68, -RD + .05, -RD + .3, bevel=.06)
        box(M['yellow'], x - .225, x + .225, 1.05, 1.1, -RD + .04, -RD + .31); box(M['yellow'], x - .225, x + .225, 1.4, 1.45, -RD + .04, -RD + .31)
        ball(M['red'] if k != 1 else M['yellow'], x, 1.98, -RD + .2, .17, .13, .2); box(M['red2'] if k != 1 else M['olive'], x - .22, x + .22, 1.88, 1.9, -RD + .02, -RD + .42)
        box(M['rubber'], x - .2, x - .02, 0, .42, -RD + .1, -RD + .35, bevel=.03); box(M['rubber'], x + .02, x + .2, 0, .42, -RD + .1, -RD + .35, bevel=.03)
    extinguisher(8.9, 0, -9.4)
    # ---- 工房（奥のまん中）：ペグボードと道具・作業台・万力・金床・素材の棚・工具ワゴン ----
    sign('工房', 12.2, 3.55, -RD + .04, 2.0, .7, '+z', bg='#a9402f', fg='#f4ecd8')
    box(C('#c49a66', .9), 9.6, 14.8, 1.2, 3.1, -RD, -RD + .04)
    for x in np.arange(9.8, 14.7, .25):
        for yy in np.arange(1.35, 3.0, .25): cyl(M['wdark'], float(x), float(yy), -RD + .045, .018, .01, 'z', 6)
    # 道具：ハンマー・レンチ・ドライバー・のこぎり・ペンチ
    bar(M['wood'], (10.2, 2.85, -RD + .1), (10.2, 2.05, -RD + .1), .035); box(M['steel2'], 10.05, 10.35, 2.8, 2.92, -RD + .06, -RD + .14)
    bar(M['chrome'], (10.7, 2.85, -RD + .09), (10.95, 2.1, -RD + .09), .03); cyl(M['chrome'], 10.7, 2.88, -RD + .09, .07, .03, 'z')
    for k, c in enumerate(['#b23a2a', '#d8b23f', '#4f6f86']): bar(C(c), (11.3 + k * .18, 2.8, -RD + .1), (11.3 + k * .18, 2.5, -RD + .1), .03); bar(M['chrome'], (11.3 + k * .18, 2.5, -RD + .1), (11.3 + k * .18, 2.25, -RD + .1), .01)
    box(M['steel'], 12.1, 13.0, 2.35, 2.62, -RD + .06, -RD + .08); box(M['wood'], 12.95, 13.15, 2.38, 2.6, -RD + .05, -RD + .12, bevel=.02)
    bar(M['red'], (13.5, 2.9, -RD + .1), (13.4, 2.4, -RD + .1), .025); bar(M['red'], (13.65, 2.9, -RD + .1), (13.75, 2.4, -RD + .1), .025)
    cyl(M['dark'], 14.3, 2.3, -RD + .1, .25, .07, 'z', 24); cyl(M['yellow'], 14.3, 2.3, -RD + .15, .12, .04, 'z', 16)
    for k in range(5): box(M['steel'], 10.0 + k * .9, 10.6 + k * .9, 1.4, 1.43, -RD + .05, -RD + .2)
    # 作業台（引き出しつき）
    box(M['wood'], 10.0, 14.4, .95, 1.05, -RD + .3, -RD + 1.3, bevel=.015)
    box(M['steel2'], 10.05, 11.4, .2, .95, -RD + .35, -RD + 1.25, bevel=.01); box(M['steel2'], 13.0, 14.35, .2, .95, -RD + .35, -RD + 1.25, bevel=.01)
    for x0 in (10.05, 13.0):
        for k in range(3): box(M['steel'], x0 + .1, x0 + 1.25, .3 + k * .22, .46 + k * .22, -RD + 1.25, -RD + 1.27); box(M['chrome'], x0 + .55, x0 + .8, .4 + k * .22, .42 + k * .22, -RD + 1.27, -RD + 1.3)
    box(M['steel2'], 11.4, 13.0, .2, .26, -RD + .4, -RD + 1.2)
    box(M['blue'], 13.6, 13.9, 1.05, 1.25, -RD + .5, -RD + .9, bevel=.01); box(M['steel'], 13.45, 14.05, 1.25, 1.33, -RD + .55, -RD + .85); bar(M['chrome'], (13.75, 1.2, -RD + .4), (13.75, 1.2, -RD + 1.0), .015)
    for k in range(6):
        c = ['#b88a5c', '#b7c0c4', '#dcbc55'][k % 3]; cyl(C(c, .3), 10.4 + k * .45, 1.2, -RD + .8, .11, .3); cyl(M['steel2'], 10.4 + k * .45, 1.38, -RD + .8, .08, .06)
    # 金床
    box(M['wdark'], 15.35, 16.05, 0, .55, -9.0, -8.3, bevel=.02)
    box(M['dark'], 15.4, 16.0, .55, .7, -8.95, -8.35); box(M['dark'], 15.1, 16.3, .7, .92, -9.05, -8.25, bevel=.02); ball(M['dark'], 16.35, .82, -8.65, .18, .08, .1, 10)
    # 素材の棚（箱・びん）
    box(M['olive'], 15.0, 16.6, 0, 2.4, -RD, -RD + .7, bevel=.01)
    for yy in (.6, 1.2, 1.8):
        box(M['steel'], 15.0, 16.6, yy, yy + .04, -RD, -RD + .7)
        for k in range(3):
            c = ['#b88a5c', '#b7c0c4', '#dcbc55'][(k + int(yy * 3)) % 3]
            box(C(c, .8), 15.1 + k * .5, 15.52 + k * .5, yy + .04, yy + .38, -RD + .1, -RD + .6, bevel=.02)
    # 工具ワゴン
    box(M['red'], 9.9, 10.7, .15, 1.0, -9.3, -8.8, bevel=.02)
    for k in range(4): box(M['chrome'], 10.0, 10.6, .3 + k * .18, .32 + k * .18, -8.8, -8.78)
    for (dx, dz) in [(.05, .05), (.75, .05), (.05, .45), (.75, .45)]: cyl(M['rubber'], 9.9 + dx, .07, -9.3 + dz, .06, .04, 'x', 10)
    extinguisher(14.9, 0, -9.6)
    # ---- 出動口：床の線・シャッター（波形）・救急車・ホースリール・パイロン・ドラム缶 ----
    box(M['hazard'], 16.8, RW, .005, .015, -11.6, -11.3, tile=.8); box(M['hazard'], 16.8, 17.1, .005, .015, -11.6, -1.0, tile=.8)
    for z in (-9.2, -3.2): box(M['yellow'], 17.6, 21.2, .005, .013, z - .05, z + .05)
    for k in range(int(3.6 / .12)):
        yy = k * .12; box(C('#a9adb0', .4, .5), RW - .1, RW - .03 - (.025 if k % 2 else 0), yy, yy + .12, -9.6, -2.6)
    box(M['steel2'], RW - .2, RW - .02, 3.6, 3.85, -9.8, -2.4); box(M['steel2'], RW - .14, RW - .02, 0, 3.6, -9.8, -9.6); box(M['steel2'], RW - .14, RW - .02, 0, 3.6, -2.6, -2.4)
    sign('出動口', RW - .05, 4.1, -6.1, 1.8, .45, '-x', bg='#a9402f', fg='#f4ecd8')
    for z in (-9.9, -2.3): ball(M['lampR'], RW - .25, 3.95, z, .22, .22, .22); box(M['dark'], RW - .12, RW, 3.75, 3.85, z - .15, z + .15)
    ambulance(19.3, -1.4)
    # ホースリール（壁）
    cyl(M['red'], 17.2, 1.5, -RD + .2, .5, .12, 'z', 28); cyl(C('#e9e6dc', .8), 17.2, 1.5, -RD + .27, .42, .1, 'z', 28); cyl(M['red'], 17.2, 1.5, -RD + .33, .2, .04, 'z', 20)
    for (x, z) in [(17.5, -.7), (18.2, -.6)]:
        cyl(M['orange'], x, .02, z, .18, .04, 'y', 4); bar(M['orange'], (x, .02, z), (x, .65, z), .1); bar(M['white'], (x, .3, z), (x, .4, z), .07)
    for k in range(2): cyl(C('#2f5a8a', .5, .3), 21.1, .45, -11.2 + k * .65, .29, .9, 'y', 20); cyl(M['dark'], 21.1, .91, -11.2 + k * .65, .29, .02, 'y', 20)
    # 天井から下がる蛍光灯（そこだけ）
    for (x, z) in ([(4.7, -4.0), (12.2, -6.5), (19.3, -6.0)] if CEIL_LIGHTS else []):
        box(M['white'], x - .9, x + .9, 3.9, 3.98, z - .12, z + .12); box(M['lampW'], x - .85, x + .85, 3.88, 3.9, z - .08, z + .08)
        for dx in (-.7, .7): bar(M['steel'], (x + dx, 3.98, z), (x + dx, WH, z), .01)

def ambulance(cx, front):
    w = 1.05; bw = C('#f2f0ea', .35, .1)
    box(bw, cx - w, cx + w, .55, 1.45, front - 1.3, front - .05, bevel=.12)              # ボンネット
    box(bw, cx - w, cx + w, .55, 2.75, front - 6.0, front - 1.2, bevel=.14)               # 箱
    box(M['glass'], cx - w + .1, cx + w - .1, 1.45, 2.3, front - 1.27, front - 1.2)       # 前の窓
    for s in (-1, 1):
        box(M['glass'], cx + s * w - .01, cx + s * w + .01, 1.55, 2.25, front - 2.4, front - 1.35)
        box(M['glass'], cx + s * w - .01, cx + s * w + .01, 1.8, 2.3, front - 5.4, front - 3.0)
        box(M['dark'], cx + s * (w + .02) - .04, cx + s * (w + .02) + .04, 1.55, 1.75, front - 1.45, front - 1.25)   # ミラー
        bar(M['dark'], (cx + s * w, 1.62, front - 1.35), (cx + s * (w + .12), 1.62, front - 1.35), .02)
    box(M['red'], cx - w - .01, cx + w + .01, 1.1, 1.3, front - 6.0, front - .1)         # 赤い帯
    box(M['red'], cx - w - .01, cx + w + .01, 2.45, 2.55, front - 6.0, front - 1.2)
    box(M['dark'], cx - .7, cx + .7, .62, .95, front - .07, front + .02, bevel=.02)        # グリル
    for k in range(5): box(M['chrome'], cx - .65, cx + .65, .66 + k * .06, .68 + k * .06, front + .01, front + .03)
    for s in (-1, 1): box(M['lampY'], cx + s * .85 - .14, cx + s * .85 + .14, .8, .98, front - .08, front + .02, bevel=.02)
    box(M['dark'], cx - w - .02, cx + w + .02, .5, .62, front - .15, front + .05)            # バンパー
    box(M['dark'], cx - .9, cx + .9, 2.75, 2.85, front - 1.7, front - 1.3);
    for s in (-1, 1): box(M['lampR'], cx + s * .5 - .3, cx + s * .5 + .3, 2.85, 3.0, front - 1.65, front - 1.35, bevel=.03)
    box(M['lampW'], cx - .15, cx + .15, 2.86, 2.98, front - 1.62, front - 1.38)
    sign('風情救急', cx - w - .015, 1.9, front - 3.7, 2.2, .55, '-x', bg='#f2f0ea', fg='#b23a2a', border='#f2f0ea')
    def cross():
        im = Image.new('RGB', (256, 256), (242, 240, 234)); d = ImageDraw.Draw(im)
        d.rectangle([98, 28, 158, 228], fill=(178, 58, 42)); d.rectangle([28, 98, 228, 158], fill=(178, 58, 42)); return im
    picture(cross, 'cross', cx + w + .015, 1.9, front - 3.8, .75, .75, '+x')
    picture(cross, 'cross', cx, 1.9, front - 6.015, .7, .7, '-z')
    box(M['dark'], cx - .9, cx + .9, .55, 2.6, front - 6.02, front - 6.0)   # うしろのとびら
    box(bw, cx - .86, cx - .02, .6, 2.55, front - 6.03, front - 6.01); box(bw, cx + .02, cx + .86, .6, 2.55, front - 6.03, front - 6.01)
    for (x, z) in [(cx - w, front - 1.6), (cx + w, front - 1.6), (cx - w, front - 5.0), (cx + w, front - 5.0)]:
        cyl(M['rubber'], x, .45, z, .45, .32, 'x', 28); cyl(M['chrome'], x + (.161 if x > cx else -.161), .45, z, .25, .01, 'x', 20)
        cyl(M['dark'], x + (.165 if x > cx else -.165), .45, z, .08, .01, 'x', 12)
        box(M['dark'], x - .05 if x > cx else x - .02, x + .02 if x > cx else x + .05, .5, 1.0, z - .6, z + .6)   # タイヤハウス

# =====================================================================
#  1F → 2F の階段
# =====================================================================
def stairs1():
    CUR[0] = 'ST1'
    run, rise = (ST['x1'] - ST['x0']) / ST['n'], FH / ST['n']
    for k in range(ST['n']):
        x0 = ST['x0'] + run * k; top = rise * (k + 1)
        box(C('#9a9c94', .85), x0, x0 + run, top - rise - .02, top, ST['z0'], ST['z1'], tile=1)
        box(M['yellow'], x0 + run - .07, x0 + run + .005, top - .02, top + .006, ST['z0'] + .05, ST['z1'] - .05)
    # 手前の側げた（ななめの鉄骨）
    bar(C('#7d7f78', .6, .4), (ST['x0'], .05, ST['z1'] + .04), (ST['x1'], FH - .05, ST['z1'] + .04), .09)
    zr = ST['z1'] + .1
    bar(M['yellow'], (ST['x0'], 1.0, zr), (ST['x1'], FH + 1.0, zr), .045)
    bar(M['steel'], (ST['x0'], .55, zr), (ST['x1'], FH + .55, zr), .025)
    for k in range(0, ST['n'] + 1, 2):
        x = ST['x0'] + run * k; bar(M['steel'], (x, rise * k, zr), (x, rise * k + 1.0, zr), .025)
    bar(M['yellow'], (ST['x0'], 1.0, -RD + .06), (ST['x1'], FH + 1.0, -RD + .06), .04)   # 壁の手すり
    # 2F の穴のまわりの柵
    CUR[0] = 'F2'
    for (a, b) in [((.4, ST['z1'] + .06), (ST['x1'] - 1.0, ST['z1'] + .06))]:
        bar(M['red'], (a[0], FH + 1.05, a[1]), (b[0], FH + 1.05, b[1]), .05); bar(M['red'], (a[0], FH + .55, a[1]), (b[0], FH + .55, b[1]), .03)
        x = a[0]
        while x <= b[0] + .01: bar(M['red'], (x, FH, a[1]), (x, FH + 1.05, a[1]), .035); x += .9

# =====================================================================
#  2F：指令室
# =====================================================================
def build2F():
    CUR[0] = 'F2'; y = FH
    px, pz = POLE
    floor = [(M['woodf'], -.3, RW + .3, y - SL, ST['z1'], 2.0)]
    floor = [(M['woodf'], -.3, RW + .3, ST['z1'], .2, 2.5), (M['woodf'], ST['x1'], RW + .3, -RD - .3, ST['z1'], 2.5), (M['woodf'], -.3, .4, -RD - .3, ST['z1'], 2.5)]
    # すべり棒の穴（1.2m 四方）をあける：手前がわの床を 4 つに分ける
    floor[0] = None
    parts = [p for p in floor if p]
    parts += [(M['woodf'], -.3, px - .6, ST['z1'], .2, 2.5), (M['woodf'], px + .6, RW + .3, ST['z1'], .2, 2.5),
              (M['woodf'], px - .6, px + .6, ST['z1'], pz - .6, 2.5), (M['woodf'], px - .6, px + .6, pz + .6, .2, 2.5)]
    shell(1, parts, M['wall2'], M['wain2'], windows=[(-6.5, -3.8, 1.2, 2.8)])
    sign('指令室', 12.5, y + 3.8, -RD + .04, 2.4, .7, '+z', bg='#4f6f86', fg='#f4ecd8')
    # 大モニター（奥の壁）と左右の小モニター
    box(M['dark'], 8.5, 16.5, y + .95, y + 3.5, -RD, -RD + .22, bevel=.03)
    picture(img_radar, 'radar', 12.5, y + 2.22, -RD + .225, 7.6, 2.35, '+z', emit=1.3)
    for x in (7.35, 17.65):
        box(M['dark'], x - .95, x + .95, y + 1.35, y + 2.85, -RD, -RD + .18, bevel=.02)
        picture(img_graph, 'graph', x, y + 2.1, -RD + .185, 1.7, 1.3, '+z', emit=1.2)
    # 指令台：パネル・ボタン・マイク・画面
    box(M['steel2'], 10.0, 15.0, y, y + .9, -8.4, -7.6, bevel=.02)
    box(M['dark'], 9.9, 15.1, y + .9, y + .98, -8.5, -7.5, bevel=.015)
    me = None
    for k in range(10): box([M['lampR'], M['lampY'], M['lampG']][k % 3], 10.3 + k * .45, 10.46 + k * .45, y + .98, y + 1.02, -7.95, -7.8, bevel=.01)
    for k in range(4): cyl(M['chrome'], 10.4 + k * .3, y + 1.0, -8.2, .06, .04)
    box(M['dark'], 11.6, 13.4, y + .98, y + 1.6, -8.42, -8.32, bevel=.01); box(M['crt'], 11.7, 13.3, y + 1.04, y + 1.54, -8.32, -8.31)
    bar(M['dark'], (14.4, y + .98, -8.0), (14.4, y + 1.3, -8.1), .015); ball(M['dark'], 14.4, y + 1.33, -8.12, .05, .07, .05)
    chair(12.5, -9.15, y, face=0, m=M['red2'])
    # 右の壁：通信機ラック（ランプ）
    for k in range(4):
        z0 = -10.8 + k * 1.5
        box(M['steel2'], RW - .9, RW, y, y + 2.2, z0, z0 + 1.2, bevel=.02)
        for r in range(5):
            for c in range(4): box([M['lampR'], M['lampY'], M['lampG'], M['dark']][(r + c + k) % 4], RW - .92, RW - .9, y + .5 + r * .3, y + .6 + r * .3, z0 + .15 + c * .25, z0 + .3 + c * .25)
        for r in range(3): box(M['dark'], RW - .93, RW - .9, y + .15 + r * .1, y + .2 + r * .1, z0 + .1, z0 + 1.1)
    # 作戦テーブルと地図・コマ
    box(M['wood2'], 10.2, 14.8, y + .72, y + .82, -4.6, -2.6, bevel=.02)
    for (x, z) in [(10.35, -4.45), (14.65, -4.45), (10.35, -2.75), (14.65, -2.75)]: box(M['wdark'], x - .06, x + .06, y, y + .72, z - .06, z + .06)
    picture(img_map, 'map', 12.5, y + .825, -3.6, 4.2, 1.8, '+y')
    for (x, z, c) in [(11.3, -3.4, '#b23a2a'), (13.0, -3.9, '#4f6f86'), (13.6, -3.0, '#d8b23f')]: cyl(C(c), x, y + .88, z, .07, .1); ball(C(c), x, y + .96, z, .06, .06, .06)
    for (x, z, f) in [(11.0, -5.0, 0), (14.0, -5.0, 0), (11.0, -2.2, math.pi), (14.0, -2.2, math.pi)]: chair(x, z, y, face=f)
    # 左手前：休憩コーナー（ソファ・ローテーブル・マグ・植木・本棚）
    box(M['olive'], 1.0, 4.4, y + .2, y + .55, -3.0, -2.0, bevel=.06); box(M['olive'], 1.0, 4.4, y + .55, y + 1.25, -3.05, -2.7, bevel=.06)
    for x in (1.0, 4.15): box(M['olive'], x, x + .25, y + .2, y + .85, -3.0, -2.0, bevel=.06)
    for k in range(3): box(C('#6b7a55', .9), 1.3 + k * 1.0, 2.2 + k * 1.0, y + .55, y + .68, -2.68, -2.08, bevel=.05)
    box(M['wood'], 1.6, 3.8, y + .35, y + .42, -1.6, -.9, bevel=.02); [box(M['wdark'], x, x + .06, y, y + .35, z, z + .06) for x in (1.65, 3.69) for z in (-1.55, -1.01)]
    for (x, z, c) in [(2.3, -1.25, '#f1ece0'), (3.0, -1.2, '#b23a2a')]: cyl(C(c), x, y + .48, z, .06, .12); bar(C(c), (x + .06, y + .5, z), (x + .1, y + .46, z), .012)
    plant(.8, -5.2, y)
    box(M['wood2'], .05, .45, y, y + 2.0, -1.8, -.4, bevel=.01)
    for k in range(4):
        yy = y + .1 + k * .48; box(M['wood'], .05, .45, yy, yy + .03, -1.8, -.4)
        zz = -1.75
        while zz < -.5:
            t = .05 + rnd.random() * .05; hh = .28 + rnd.random() * .12
            box(C(rnd.choice(['#b23a2a', '#4f6f86', '#d8b23f', '#5f8a45', '#f1ece0'])), .1, .4, yy + .03, yy + .03 + hh, zz, zz + t); zz += t + .01
    # 結成ボード（コルクにチーム表）
    for x in (2.5, 4.7): box(M['dark'], x, x + .08, y, y + 1.2, -7.05, -6.95)
    box(M['wood2'], 2.25, 4.95, y + 1.05, y + 2.65, -7.12, -6.93, bevel=.02)
    picture(img_formboard, 'form', 3.6, y + 1.85, -6.925, 2.5, 1.5, '+z')
    # 募集端末
    box(M['steel2'], 16.8, 18.0, y, y + 1.3, -3.2, -2.4, bevel=.04); box(M['dark'], 16.85, 17.95, y + 1.3, y + 2.1, -3.05, -2.75, bevel=.03)
    picture(img_recruit, 'recruit', 17.4, y + 1.7, -2.745, .92, .58, '+z', emit=1.2)
    bar(M['steel'], (17.7, y + 2.1, -2.9), (17.9, y + 2.8, -2.9), .025); ball(M['lampR'], 17.9, y + 2.85, -2.9, .09, .09, .09)
    # ホワイトボード・張り紙・時計・消火器
    box(M['steel'], 4.35, 7.25, y + 1.15, y + 2.65, -RD, -RD + .06, bevel=.01); picture(img_whiteboard, 'wb', 5.8, y + 1.9, -RD + .065, 2.8, 1.4, '+z', rough=.3)
    box(M['steel'], 4.4, 7.2, y + 1.08, y + 1.12, -RD, -RD + .14)
    for (z, c, t) in [(-9.6, (240, 232, 210), ('出動記録', '今月 12件')), (-8.6, (216, 194, 122), ('安全第一', 'ヨシ！'))]:
        picture(img_poster(t, c), 'poster' + t[0], .02, y + 2.1, z, .62, .86, '+x')
    wall_clock(16.8, y + 3.3, -RD + .02)
    extinguisher(9.0, y, -9.7)
    # すべり棒の穴の柵（3方・のぼり口なし）と ポール本体（1F から 2F の上まで）
    for (a, b) in [((px - .65, pz - .65), (px + .65, pz - .65)), ((px + .65, pz - .65), (px + .65, pz + .65)), ((px - .65, pz - .65), (px - .65, pz + .65))]:
        bar(M['yellow'], (a[0], y + 1.0, a[1]), (b[0], y + 1.0, b[1]), .04)
        for (xx, zz) in (a, b): bar(M['yellow'], (xx, y, zz), (xx, y + 1.0, zz), .035)
    box(M['hazard'], px - .7, px + .7, y + .002, y + .012, pz + .6, pz + .75, tile=.6)
    CUR[0] = 'F1'
    bar(M['chrome'], (px, 0, pz), (px, FH - SL, pz), .06, 20)            # 1F のぶん
    cyl(C('#3a6ea8', .9), px, .08, pz, .75, .16, 'y', 28)            # 下のマット
    CUR[0] = 'F2'
    bar(M['chrome'], (px, FH - SL, pz), (px, FH + 2.6, pz), .06, 20)     # 2F のぶん（天井へ）
    # 蛍光灯
    for (x, z) in ([(5.0, -5.0), (12.5, -6.0), (18.5, -6.0)] if CEIL_LIGHTS else []):
        box(M['white'], x - .9, x + .9, y + 3.9, y + 3.98, z - .12, z + .12); box(M['lampW'], x - .85, x + .85, y + 3.88, y + 3.9, z - .08, z + .08)
        for dx in (-.7, .7): bar(M['steel'], (x + dx, y + 3.98, z), (x + dx, y + WH, z), .01)

# =====================================================================
#  2F → 屋上 の階段
# =====================================================================
def stairs2():
    CUR[0] = 'ST2'; y = FH
    run, rise = (S2['xb'] - S2['xa']) / S2['n'], FH / S2['n']
    for k in range(S2['n']):
        x1 = S2['xb'] - run * k; x0 = x1 - run; top = y + rise * (k + 1)
        box(C('#8f9189', .8, .3), x0, x1, top - .08, top, S2['z0'], S2['z1'])
        box(M['yellow'], x0 - .005, x0 + .06, top - .02, top + .006, S2['z0'] + .05, S2['z1'] - .05)
    for z in (S2['z0'] + .05, S2['z1'] - .05): bar(M['steel2'], (S2['xb'], y, z), (S2['xa'], y + FH, z), .1)
    for z in (S2['z0'] - .03, S2['z1'] + .03):
        bar(M['yellow'], (S2['xb'], y + 1.0, z), (S2['xa'], y + FH + 1.0, z), .04)
        for k in range(0, S2['n'] + 1, 2): x = S2['xb'] - run * k; bar(M['steel'], (x, y + rise * k, z), (x, y + rise * k + 1.0, z), .025)
    bar(M['steel'], (9.2, y, -8.25), (9.2, y + 2.25, -8.25), .04)
    sign('屋上へ ↑', 9.2, y + 2.45, -8.2, 1.3, .42, '+z', bg='#cfae45')

# =====================================================================
#  屋上
# =====================================================================
def railing(a, b, y, post=1.4, m=None):
    m = m or M['rust']; L = math.hypot(b[0] - a[0], b[1] - a[1]); n = max(1, round(L / post))
    bar(m, (a[0], y + 1.1, a[1]), (b[0], y + 1.1, b[1]), .045); bar(m, (a[0], y + .6, a[1]), (b[0], y + .6, b[1]), .03)
    for i in range(n + 1):
        x = a[0] + (b[0] - a[0]) * i / n; z = a[1] + (b[1] - a[1]) * i / n; bar(m, (x, y, z), (x, y + 1.1, z), .035)
        if i < n:
            for j in range(1, 4):
                t = (i + j / 4) / n; xx = a[0] + (b[0] - a[0]) * t; zz = a[1] + (b[1] - a[1]) * t; bar(m, (xx, y + .1, zz), (xx, y + 1.1, zz), .012, 6)
def hose_tower(x0, z0, w, h, y):
    m = M['rust']; x1, z1 = x0 + w, z0 + w; seg = h / 6
    for (x, z) in [(x0, z0), (x1, z0), (x0, z1), (x1, z1)]: bar(m, (x, y, z), (x, y + h + 1.1, z), .09)
    for i in range(1, 7):
        yy = y + seg * i; y0 = yy - seg
        for (a, b) in [((x0, z0), (x1, z0)), ((x0, z1), (x1, z1)), ((x0, z0), (x0, z1)), ((x1, z0), (x1, z1))]: bar(m, (a[0], yy, a[1]), (b[0], yy, b[1]), .055)
        bar(m, (x0, y0, z1), (x1, yy, z1), .03); bar(m, (x1, y0, z1), (x0, yy, z1), .03); bar(m, (x0, y0, z0), (x0, yy, z1), .03); bar(m, (x1, y0, z1), (x1, yy, z0), .03)
    box(C('#7a3420', .6, .3), x0 - .35, x1 + .35, y + h, y + h + .12, z0 - .35, z1 + .35)
    for (a, b) in [((x0 - .35, z0 - .35), (x1 + .35, z0 - .35)), ((x0 - .35, z1 + .35), (x1 + .35, z1 + .35)), ((x0 - .35, z0 - .35), (x0 - .35, z1 + .35)), ((x1 + .35, z0 - .35), (x1 + .35, z1 + .35))]:
        bar(m, (a[0], y + h + 1.0, a[1]), (b[0], y + h + 1.0, b[1]), .04)
    for i in range(4):
        x = x0 + .45 + i * .43; bar(C(['#ece9e0', '#cbc8bd'][i % 2], .8), (x, y + h - .1, (z0 + z1) / 2), (x, y + h - 5.2 + (i % 2) * .8, (z0 + z1) / 2 + .1), .07)
    bar(M['steel2'], (x0 + .2, y + h - .1, (z0 + z1) / 2), (x1 - .2, y + h - .1, (z0 + z1) / 2), .05)
    for x in ((x0 + x1) / 2 - .28, (x0 + x1) / 2 + .28): bar(M['steel'], (x, y, z1 + .12), (x, y + h, z1 + .12), .03)
    yy = y + .35
    while yy < y + h: bar(M['steel'], ((x0 + x1) / 2 - .28, yy, z1 + .12), ((x0 + x1) / 2 + .28, yy, z1 + .12), .022); yy += .35
def gacha(x, z, y):
    box(M['red'], x - 1.1, x + 1.1, y, y + 1.25, z - .9, z + .9, bevel=.08)
    box(M['yellow'], x - 1.12, x + 1.12, y + 1.15, y + 1.3, z - .92, z + .92, bevel=.04)
    ball(glass_mat('gacha_glass', hexc('#d8f0fa'), .3), x, y + 2.05, z, .95, .8, .78, 28)
    for k in range(22):
        a = rnd.random() * math.tau; r = rnd.random() * .7; yy = y + 1.45 + rnd.random() * .45
        ball(C(rnd.choice(['#e0503c', '#3c7fd6', '#f0c048', '#5fbf5a', '#9a5fd0', '#f4f1ea']), .4), x + math.cos(a) * r, yy, z + math.sin(a) * r * .8, .14, .14, .14, 10)
    cyl(M['yellow'], x, y + 2.9, z, .3, .12); ball(M['lampR'], x, y + 3.05, z, .14, .14, .14)
    cyl(M['chrome'], x, y + .8, z + .91, .24, .08, 'z', 24); box(M['chrome'], x - .2, x + .2, y + .76, y + .84, z + .95, z + 1.0)
    box(M['dark'], x - .3, x + .3, y + .15, y + .45, z + .85, z + .92); box(M['steel2'], x + .55, x + .8, y + .85, y + 1.0, z + .9, z + .93)
    sign('朕銭ガシャ', x, y + 4.05, z - 1.65, 3.4, .8, '+z', bg='#2a211c', fg='#f0c048', border='#c9a545')
    for xx in (x - 1.6, x + 1.6): bar(M['wood2'], (xx, y, z - 1.7), (xx, y + 4.4, z - 1.7), .07)
def buildRoof():
    CUR[0] = 'RF'; y = RY
    for (x0, x1, z0, z1) in [(-.3, RW + .3, S2['z1'], .2), (-.3, RW + .3, -RD - .3, S2['z0']), (-.3, S2['xa'], S2['z0'], S2['z1']), (S2['xb'], RW + .3, S2['z0'], S2['z1'])]:
        box(M['roof'], x0, x1, y - SL, y, z0, z1, tile=2.5)
    par = C('#d8d4c8', .85)
    box(par, -.3, RW + .3, y, y + .4, -RD - .3, -RD); box(par, -.3, 0, y, y + .4, -RD, .2); box(par, RW, RW + .3, y, y + .4, -RD, .2); box(par, -.3, RW + .3, y, y + .4, -.1, .2)
    box(M['ink'], -.32, RW + .32, y + .4, y + .43, -.12, .22)
    for (a, b, p) in [((-.15, -RD - .15), (RW + .15, -RD - .15), 1.4), ((-.15, -RD - .15), (-.15, .05), 1.4), ((RW + .15, -RD - .15), (RW + .15, .05), 1.4), ((-.15, .05), (RW + .15, .05), 2.2)]:
        railing(a, b, y + .4, p)
    for (a, b) in [((S2['xa'] + .5, S2['z1'] + .05), (S2['xb'] + .05, S2['z1'] + .05)), ((S2['xa'] + .5, S2['z0'] - .05), (S2['xb'] + .05, S2['z0'] - .05)), ((S2['xb'] + .05, S2['z0'] - .05), (S2['xb'] + .05, S2['z1'] + .05))]:
        railing(a, b, y, 1.3)
    sign('↓ 2F', S2['xa'] + .9, y + 1.6, S2['z1'] + .1, .9, .36, '+z', bg='#cfae45')
    hose_tower(17.8, -11.4, 2.3, 8.4, y)
    # 足場（白いパイプ）
    for x in (.8, 3.0, 5.2):
        for z in (-6.4, -4.2): bar(M['pipe'], (x, y, z), (x, y + 2.6, z), .045)
    for yy in (1.3, 2.6):
        for z in (-6.4, -4.2): bar(M['pipe'], (.8, y + yy, z), (5.2, y + yy, z), .04)
        for x in (.8, 3.0, 5.2): bar(M['pipe'], (x, y + yy, -6.4), (x, y + yy, -4.2), .04)
    bar(M['pipe'], (.8, y + .2, -6.4), (3.0, y + 2.5, -6.4), .03); bar(M['pipe'], (3.0, y + .2, -4.2), (5.2, y + 2.5, -4.2), .03)
    box(M['wood'], .8, 5.2, y + 2.6, y + 2.66, -6.3, -5.3, tile=1)
    box(C('#b88a5c', .8), 1.2, 2.0, y, y + .6, -5.9, -5.1, bevel=.02); box(C('#b7c0c4', .8), 1.3, 1.9, y + .6, y + 1.05, -5.8, -5.2, bevel=.02)
    # 室外機（ファンつき）・配管
    for x in (19.0, 20.4):
        box(C('#e2e0d8', .6), x, x + 1.1, y, y + .78, -1.75, -.95, bevel=.03)
        cyl(M['dark'], x + .5, y + .4, -.94, .27, .02, 'z', 24)
        for k in range(4): bar(M['steel2'], (x + .5 + math.cos(k * .8) * .26, y + .4 + math.sin(k * .8) * .26, -.93), (x + .5 - math.cos(k * .8) * .26, y + .4 - math.sin(k * .8) * .26, -.93), .008)
        bar(M['steel'], (x + .9, y + .3, -1.75), (x + .9, y + .3, -2.4), .03)
    bar(M['steel'], (19.9, y + .3, -2.4), (21.3, y + .3, -2.4), .03)
    # 給水タンク
    for (x, z) in [(14.9, -11.4), (16.6, -11.4), (14.9, -10.0), (16.6, -10.0)]: bar(M['steel2'], (x, y, z), (x, y + 1.2, z), .05)
    box(M['steel2'], 14.8, 16.7, y + 1.2, y + 1.3, -11.5, -9.9)
    cyl(C('#c9d1d4', .5, .2), 15.75, y + 2.1, -10.7, .85, 1.6, 'y', 28); cyl(C('#aeb7bb', .5, .2), 15.75, y + 2.92, -10.7, .87, .06, 'y', 28)
    # ベンチ・植木・物干し
    box(M['red'], 14.6, 17.0, y + .42, y + .5, -1.85, -1.35, bevel=.02); [box(M['dark'], x, x + .08, y, y + .42, -1.8, -1.4) for x in (14.7, 16.82)]
    plant(13.8, -1.4, y); plant(17.6, -1.3, y, .9)
    for x in (7.8, 10.2): bar(M['steel'], (x, y, -2.2), (x, y + 1.8, -2.2), .035)
    bar(M['steel'], (7.8, y + 1.75, -2.2), (10.2, y + 1.75, -2.2), .02)
    for (x, c) in [(8.3, '#d8b23f'), (8.9, '#ece9e0'), (9.5, '#4f6f86')]: box(C(c, .9), x - .22, x + .22, y + 1.05, y + 1.72, -2.24, -2.16)
    # アンテナ
    bar(M['steel'], (21.2, y + .4, -11.5), (21.2, y + 3.6, -11.5), .03)
    for k in range(4): bar(M['steel'], (20.9, y + 2.6 + k * .25, -11.5), (21.5, y + 2.6 + k * .25, -11.5), .012)
    gacha(12.5, -7.4, y)

build1F(); stairs1(); build2F(); stairs2(); buildRoof()

# =====================================================================
#  まとめる：階ごと・材料ごとに 1 つのメッシュへ（軽くするため）。いちばん上の節は F1 F2 RF ST1 ST2
# =====================================================================
for name, c in COLS.items():
    objs = [o for o in c.objects if o.type == 'MESH']
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]; bpy.ops.object.join()
    j = bpy.context.active_object; j.name = name + '_mesh'
    e = bpy.data.objects.new(name, None); c.objects.link(e); j.parent = e
    print(name, len(j.data.vertices), 'verts', len(j.data.materials), 'mats')
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_apply=True, export_yup=True, export_image_format='AUTO')
bpy.ops.wm.save_as_mainfile(filepath=out.replace('.glb', '.blend'))
print('wrote', out)
