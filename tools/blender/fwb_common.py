# 風情ウォッチバスターズのマップづくり（Blender）で使う 共通の道具。
#   座標はゲームと同じ（x 右、y 上、z 手前がプラス・奥がマイナス）で書き、Blender には (x, −z, y) で置く。
#   テクスチャは numpy / Pillow で作って glb の中に入れる。看板の文字は ラノベPOP v2（fonts/）。
import bpy, bmesh, os, math, json
import numpy as np
from mathutils import Vector, Matrix
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    COLS.clear(); MATS.clear(); SIGNS.clear(); TEX.clear(); COL['box'].clear(); COL['circle'].clear()

# ---- 文字 ----
_FONT = [None]
def font_path():
    if _FONT[0]: return _FONT[0]
    w = os.path.join(ROOT, 'fonts', 'LightNovelPOPv2.woff2')
    if os.path.exists(w):
        try:
            from fontTools.ttLib import TTFont
            p = os.path.join(bpy.app.tempdir or '/tmp', 'lnpop.otf'); f = TTFont(w); f.flavor = None; f.save(p); _FONT[0] = p; return p
        except Exception as e: print('font', e)
    for p in ['/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf', '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf']:
        if os.path.exists(p): _FONT[0] = p; return p
def F(sz):
    p = font_path(); return ImageFont.truetype(p, sz) if p else ImageFont.load_default()

# ---- 画像 ----
def to_image(name, pil, jpeg=False):
    pil = pil.convert('RGBA'); w, h = pil.size
    a = np.asarray(pil, dtype=np.float32)[::-1] / 255.0
    img = bpy.data.images.new(name, w, h, alpha=not jpeg)
    img.pixels.foreach_set(a.ravel()); img.file_format = 'JPEG' if jpeg else 'PNG'; img.pack()
    return img
def noise(w, h, scale, seed):
    r = np.random.default_rng(seed); g = r.random((h // scale + 2, w // scale + 2)).astype(np.float32)
    return np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), dtype=np.float32) / 255.0
def tint(base, n, amt):
    return Image.fromarray(np.clip(np.array(base, np.float32)[None, None] * (1 + (n[..., None] - .5) * amt), 0, 255).astype(np.uint8))
def sign_img(text, w, h, bg, fg, border=None, size=None, sub=None):
    im = Image.new('RGB', (w, h), bg); d = ImageDraw.Draw(im)
    if border: d.rectangle([6, 6, w - 7, h - 7], outline=border, width=max(4, h // 20))
    sz = size or int(h * .58); f = F(sz)
    while d.textlength(text, font=f) > w * .88 and sz > 10: sz -= 2; f = F(sz)
    d.text((w / 2, h / 2 if not sub else h * .4), text, font=f, fill=fg, anchor='mm')
    if sub: d.text((w / 2, h * .78), sub, font=F(int(h * .2)), fill=fg, anchor='mm')
    return im

# ---- マテリアル ----
MATS, TEX = {}, {}
def mat(name, col=(.8, .8, .8), rough=.7, metal=0.0, img=None, emit=0.0):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*col, 1)
    b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    if img is not None:
        t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = img
        m.node_tree.links.new(t.outputs['Color'], b.inputs['Base Color'])
        if emit: m.node_tree.links.new(t.outputs['Color'], b.inputs['Emission Color'])
    elif emit: b.inputs['Emission Color'].default_value = (*col, 1)
    if emit: b.inputs['Emission Strength'].default_value = emit
    MATS[name] = m; return m
def hexc(h):
    h = h.lstrip('#'); return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4))
def C(h, rough=.7, metal=0.0, emit=0.0): return mat('c' + h + f'{rough}{metal}{emit}', hexc(h), rough, metal, emit=emit)
def glass(name, h, alpha):
    m = mat(name, hexc(h), .05)
    m.node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value = alpha
    try: m.surface_render_method = 'BLENDED'
    except Exception: pass
    return m
def tmat(name, fn, rough=.8, jpeg=False):
    if name not in TEX: TEX[name] = mat(name, img=to_image(name, fn(), jpeg), rough=rough)
    return TEX[name]

# ---- 形 ----
def P(x, y, z): return Vector((x, -z, y))
COLS = {}
CUR = ['MAP']
def coll(name):
    if name not in COLS:
        c = bpy.data.collections.new(name); bpy.context.scene.collection.children.link(c); COLS[name] = c
    return COLS[name]
def link(o): coll(CUR[0]).objects.link(o); return o
def uv_box(bm, tile):
    uv = bm.loops.layers.uv.get('UVMap') or bm.loops.layers.uv.new('UVMap')
    for f in bm.faces:
        n = f.normal; ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            co = l.vert.co; u, v = [(co.y, co.z), (co.x, co.z), (co.x, co.y)][ax]
            l[uv].uv = (u / tile, v / tile)
def _mesh(bm, m, name, smooth, tile=1.0, uv=True):
    if uv: uv_box(bm, tile)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(m)
    for p in me.polygons: p.use_smooth = smooth
    return link(bpy.data.objects.new(name, me))
def box(m, x0, x1, y0, y1, z0, z1, bevel=0.0, tile=1.0, name='box'):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    a, b = P(min(x0, x1), min(y0, y1), max(z0, z1)), P(max(x0, x1), max(y0, y1), min(z0, z1))
    for v in bm.verts: v.co = Vector((a.x + (v.co.x + .5) * (b.x - a.x), a.y + (v.co.y + .5) * (b.y - a.y), a.z + (v.co.z + .5) * (b.z - a.z)))
    if bevel > 0: bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect='EDGES', profile=.5)
    bm.normal_update(); return _mesh(bm, m, name, False, tile)
def cyl(m, x, y, z, r, h, axis='y', seg=20, cap=True, r2=None, name='cyl'):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=cap, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=h)
    rot = {'y': Matrix.Identity(4), 'x': Matrix.Rotation(math.pi / 2, 4, 'Y'), 'z': Matrix.Rotation(math.pi / 2, 4, 'X')}[axis]
    bmesh.ops.transform(bm, matrix=Matrix.Translation(P(x, y, z)) @ rot, verts=bm.verts)
    return _mesh(bm, m, name, True)
def bar(m, a, b, r, seg=10, name='bar'):
    A, B = P(*a), P(*b); d = B - A
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=d.length)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((A + B) / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4(), verts=bm.verts)
    return _mesh(bm, m, name, True)
def ball(m, x, y, z, rx, ry, rz, seg=16, name='ball'):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=1)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(P(x, y, z)) @ Matrix.Diagonal((rx, rz, ry, 1)), verts=bm.verts)
    return _mesh(bm, m, name, True)
def quad(m, pts, uvs=((0, 0), (1, 0), (1, 1), (0, 1)), name='quad'):
    me = bpy.data.meshes.new(name); me.from_pydata([P(*p) for p in pts], [], [tuple(range(len(pts)))]); me.update()
    uv = me.uv_layers.new(name='UVMap')
    for i, t in enumerate(uvs): uv.data[i].uv = t
    me.materials.append(m); return link(bpy.data.objects.new(name, me))
def plane(m, cx, cy, cz, w, h, face, name='plane'):
    hw, hh = w / 2, h / 2
    q = {'+z': [(cx - hw, cy - hh, cz), (cx + hw, cy - hh, cz), (cx + hw, cy + hh, cz), (cx - hw, cy + hh, cz)],
         '-z': [(cx + hw, cy - hh, cz), (cx - hw, cy - hh, cz), (cx - hw, cy + hh, cz), (cx + hw, cy + hh, cz)],
         '+x': [(cx, cy - hh, cz - hw), (cx, cy - hh, cz + hw), (cx, cy + hh, cz + hw), (cx, cy + hh, cz - hw)],
         '-x': [(cx, cy - hh, cz + hw), (cx, cy - hh, cz - hw), (cx, cy + hh, cz - hw), (cx, cy + hh, cz + hw)],
         '+y': [(cx - hw, cy, cz + hh), (cx + hw, cy, cz + hh), (cx + hw, cy, cz - hh), (cx - hw, cy, cz - hh)]}[face]
    return quad(m, q, name=name)
SIGNS = {}
def sign(text, cx, cy, cz, w, h, face, bg='#cfae45', fg='#1d1b19', border='#1d1b19', sub=None, frame=True):
    key = (text, bg, fg, border, sub)
    if key not in SIGNS:
        W = 512 if w >= h else int(512 * w / h); H = int(W * h / w)
        SIGNS[key] = mat('sign%d' % len(SIGNS), img=to_image('sign%d' % len(SIGNS), sign_img(text, W, H, bg, fg, border, sub=sub)), rough=.7)
    o = {'+z': (0, 0, .006), '-z': (0, 0, -.006), '+x': (.006, 0, 0), '-x': (-.006, 0, 0), '+y': (0, .006, 0)}[face]
    if frame and face in ('+z', '-z'): box(C('#1d1b19'), cx - w / 2 - .04, cx + w / 2 + .04, cy - h / 2 - .04, cy + h / 2 + .04, cz - .03 * (1 if face == '+z' else -1) - .02, cz - .03 * (1 if face == '+z' else -1) + .02)
    if frame and face in ('+x', '-x'): box(C('#1d1b19'), cx - .03 * (1 if face == '+x' else -1) - .02, cx - .03 * (1 if face == '+x' else -1) + .02, cy - h / 2 - .04, cy + h / 2 + .04, cz - w / 2 - .04, cz + w / 2 + .04)
    return plane(SIGNS[key], cx + o[0], cy + o[1], cz + o[2], w, h, face, 'sign')
def picture(fn, key, cx, cy, cz, w, h, face, emit=0.0, rough=.8):
    if key not in SIGNS: SIGNS[key] = mat('pic_' + key, img=to_image('pic_' + key, fn()), rough=rough, emit=emit)
    o = {'+z': (0, 0, .006), '-z': (0, 0, -.006), '+x': (.006, 0, 0), '-x': (-.006, 0, 0), '+y': (0, .006, 0)}[face]
    return plane(SIGNS[key], cx + o[0], cy + o[1], cz + o[2], w, h, face, 'pic')

# ---- 当たり判定（ゲームの座標で。箱は x・z の範囲、丸は中心と半径） ----
COL = {'box': [], 'circle': []}
def colbox(x0, x1, z0, z1, h=3.0, note=''): COL['box'].append([round(min(x0, x1), 3), round(max(x0, x1), 3), round(min(z0, z1), 3), round(max(z0, z1), 3), round(h, 2), note])
def colcircle(x, z, r, h=3.0, note=''): COL['circle'].append([round(x, 3), round(z, 3), round(r, 3), round(h, 2), note])

# ---- 書き出し：コレクションごとに 1 つのメッシュにまとめ、いちばん上の節の名前にする ----
def export(out, extra=None):
    for name, c in COLS.items():
        objs = [o for o in c.objects if o.type == 'MESH']
        if not objs: continue
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs: o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]; bpy.ops.object.join()
        j = bpy.context.active_object; j.name = name + '_mesh'
        e = bpy.data.objects.new(name, None); c.objects.link(e); j.parent = e
        print(name, len(j.data.vertices), 'verts', len(j.data.materials), 'mats')
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_apply=True, export_yup=True, export_image_format='AUTO')
    bpy.ops.wm.save_as_mainfile(filepath=out.replace('.glb', '.blend'))
    data = dict(COL); data.update(extra or {})
    with open(out.replace('.glb', '.col.json'), 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False)
    print('wrote', out, len(COL['box']), 'boxes', len(COL['circle']), 'circles')
