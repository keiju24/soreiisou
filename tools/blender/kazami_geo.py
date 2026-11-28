# 風見ニュータウン用の 形づくりの道具。
#   座標はゲームと同じ（x 東、y 上、z 南がプラス）。Blender には (x, −z, y) で置く。
#   色だけの面は 1枚の「パレット」テクスチャ（32px のマスに色をぬったもの）を使い、
#   建物 1つ ＝ 1つのメッシュ・少ないマテリアル（パレット・屋根・ガラス・看板）にして、描く回数をへらす。
import bpy, os, math, json, random
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))

def bl(p): return (p[0], -p[2], p[1])

# =====================================================================
#  パレット（色 → マスの まんなかの UV）
# =====================================================================
PAL_N, PAL_CELL = 16, 32
PAL = {}
def hexrgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def pal_uv(h):
    h = h.lower()
    if len(h) == 4: h = '#' + ''.join(c * 2 for c in h[1:])
    if h not in PAL:
        if len(PAL) >= PAL_N * PAL_N: raise RuntimeError('パレットがいっぱい')
        PAL[h] = len(PAL)
    i = PAL[h]; cx, cy = i % PAL_N, i // PAL_N
    return ((cx + .5) / PAL_N, 1 - (cy + .5) / PAL_N)
def palette_image():
    S = PAL_N * PAL_CELL; im = Image.new('RGB', (S, S), (255, 0, 255)); d = ImageDraw.Draw(im)
    for h, i in PAL.items():
        cx, cy = i % PAL_N, i // PAL_N
        d.rectangle([cx * PAL_CELL, cy * PAL_CELL, cx * PAL_CELL + PAL_CELL - 1, cy * PAL_CELL + PAL_CELL - 1], fill=hexrgb(h))
    return im

# =====================================================================
#  テクスチャ（手描き風：ゆるいムラ＋線）。どれも 上下左右に つながる
# =====================================================================
def tnoise(W, H, cells, seed):
    r = np.random.default_rng(seed); g = r.random((cells, cells)).astype(np.float32)
    g = np.pad(g, 2, mode='wrap')
    big = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((W * (cells + 4) // cells, H * (cells + 4) // cells), Image.BICUBIC), np.float32) / 255
    ox, oy = W * 2 // cells, H * 2 // cells
    return big[oy:oy + H, ox:ox + W]
def tint(base, n, amt):
    return Image.fromarray(np.clip(np.array(base, np.float32)[None, None] * (1 + (n[..., None] - .5) * amt), 0, 255).astype(np.uint8))
def soft_noise(W, H, seed, amt=.18):
    return tnoise(W, H, 8, seed) * .5 + tnoise(W, H, 32, seed + 1) * .3 + tnoise(W, H, 128, seed + 2) * .2

def tex_asphalt():
    W = H = 512; n = soft_noise(W, H, 11); im = tint((112, 116, 124), n, .22); d = ImageDraw.Draw(im); r = random.Random(1)
    for _ in range(2500):
        x, y = r.random() * W, r.random() * H; c = r.choice([(96, 99, 106), (134, 137, 144), (122, 125, 132)])
        d.point((x, y), fill=c)
    for _ in range(6):                                  # うすい ひび（つなぎめ）
        x, y = r.random() * W, r.random() * H; pts = [(x, y)]
        for k in range(5): x += r.uniform(-30, 30); y += r.uniform(-30, 30); pts.append((x, y))
        d.line(pts, fill=(100, 103, 110), width=1)
    return im
def tex_grass():
    W = H = 512; n = soft_noise(W, H, 21); im = tint((118, 178, 80), n, .3); d = ImageDraw.Draw(im); r = random.Random(2)
    for _ in range(3800):                               # 草の葉（短い線）
        x, y = r.random() * W, r.random() * H; L = r.uniform(3, 8); a = r.uniform(-.5, .5)
        c = r.choice([(96, 156, 64), (140, 196, 92), (108, 168, 70), (150, 204, 104)])
        for ox in (0, W, -W):
            for oy in (0, H, -H): d.line([(x + ox, y + oy), (x + ox + math.sin(a) * L, y + oy - math.cos(a) * L)], fill=c, width=2)
    return im
def tex_lot():                                          # 区画の中の 土まじりの舗装（うすい茶）
    W = H = 512; n = soft_noise(W, H, 31); im = tint((226, 196, 150), n, .14); d = ImageDraw.Draw(im); r = random.Random(3)
    for _ in range(1800):
        x, y = r.random() * W, r.random() * H; s = r.uniform(.6, 1.6); c = r.choice([(206, 176, 132), (236, 210, 168)])
        d.ellipse([x - s, y - s, x + s, y + s], fill=c)
    return im
def tex_paving():                                       # 歩道（うす茶の四角いタイル 30cm）
    W = H = 512; n = soft_noise(W, H, 41); im = tint((232, 206, 166), n, .12); d = ImageDraw.Draw(im); k = 8
    for i in range(k + 1):
        d.line([(i * W / k, 0), (i * W / k, H)], fill=(204, 176, 138), width=3); d.line([(0, i * H / k), (W, i * H / k)], fill=(204, 176, 138), width=3)
    return im
def tex_brick():                                        # れんが（ピンクがかった赤茶）
    W = H = 512; n = soft_noise(W, H, 51); im = tint((214, 140, 120), n, .12); d = ImageDraw.Draw(im); r = random.Random(5)
    bh = H / 16; bw = W / 8
    for j in range(16):
        off = (bw / 2) * (j % 2)
        for i in range(-1, 9):
            x0 = i * bw + off; c = r.choice([(212, 136, 118), (202, 126, 110), (222, 150, 128), (196, 120, 106)])
            d.rectangle([x0 + 2, j * bh + 2, x0 + bw - 2, j * bh + bh - 2], fill=c)
    return im
def tex_dirt():                                         # 校庭の土
    W = H = 512; n = soft_noise(W, H, 61); im = tint((222, 186, 128), n, .16); d = ImageDraw.Draw(im); r = random.Random(6)
    for _ in range(3000):
        x, y = r.random() * W, r.random() * H; s = r.uniform(.5, 1.4); c = r.choice([(196, 160, 108), (236, 204, 150), (182, 150, 104)])
        d.ellipse([x - s, y - s, x + s, y + s], fill=c)
    return im
def tex_concrete():
    W = H = 256; n = soft_noise(W, H, 71); return tint((196, 194, 188), n, .14)
def tex_water():                                        # 水面（波のすじ）。ゲームで UV を動かして流す
    W = H = 512; n = soft_noise(W, H, 81); im = tint((78, 176, 214), n, .22); d = ImageDraw.Draw(im); r = random.Random(8)
    for _ in range(70):
        x, y = r.random() * W, r.random() * H; L = r.uniform(20, 60)
        for ox in (0, W, -W):
            for oy in (0, H, -H):
                d.arc([x + ox - L, y + oy - 6, x + ox + L, y + oy + 6], 200, 340, fill=(190, 236, 250), width=2)
    return im.filter(ImageFilter.GaussianBlur(.6))
def tex_soil():                                         # ジオラマの側面の土
    W = H = 256; n = soft_noise(W, H, 91); im = tint((150, 108, 70), n, .25); d = ImageDraw.Draw(im)
    for y in (60, 140, 200): d.line([(0, y), (W, y + 6)], fill=(132, 92, 60), width=3)
    return im
def tex_glass():                                        # 窓ガラス（ななめの光）
    W, H = 64, 128; im = Image.new('RGB', (W, H)); d = ImageDraw.Draw(im)
    for y in range(H): t = y / H; d.line([(0, y), (W, y)], fill=(int(120 + 70 * (1 - t)), int(170 + 60 * (1 - t)), int(214 + 30 * (1 - t))))
    d.polygon([(10, H), (30, H), (W, 30), (W, 10)], fill=(214, 238, 250)); d.polygon([(36, H), (42, H), (W, 62), (W, 56)], fill=(200, 230, 246))
    return im
def tex_roof(col, kind='tile'):
    W = H = 256; base = hexrgb(col); n = soft_noise(W, H, hash(col) % 1000); im = tint(base, n, .1); d = ImageDraw.Draw(im)
    dark = tuple(int(c * .78) for c in base); light = tuple(min(255, int(c * 1.12)) for c in base)
    rows = 8
    for j in range(rows):
        y = j * H / rows
        d.line([(0, y + H / rows - 3), (W, y + H / rows - 3)], fill=dark, width=4)        # 段の かげ
        d.line([(0, y + 2), (W, y + 2)], fill=light, width=2)
        if kind == 'tile':                                                           # 瓦（たての切れ目）
            off = (W / 16) * (j % 2)
            for i in range(9): x = i * W / 8 + off; d.line([(x, y + 3), (x, y + H / rows - 4)], fill=dark, width=2)
    return im
def tex_ground_side():
    return tex_soil()

# =====================================================================
#  マテリアル
# =====================================================================
MATS = {}
def to_image(name, pil, alpha=False):
    pil = pil.convert('RGBA'); w, h = pil.size
    a = np.asarray(pil, dtype=np.float32)[::-1] / 255.0
    img = bpy.data.images.new(name, w, h, alpha=alpha)
    img.pixels.foreach_set(a.ravel()); img.file_format = 'PNG'; img.pack()
    return img
def make_mat(name, pil=None, rough=.85, alpha=False, emit=0.0, col=(1, 1, 1)):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*col, 1); b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = 0
    try: b.inputs['Specular IOR Level'].default_value = .2
    except Exception: pass
    if pil is not None:
        t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = to_image(name, pil, alpha)
        m.node_tree.links.new(t.outputs['Color'], b.inputs['Base Color'])
        if alpha:
            m.node_tree.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
            try: m.surface_render_method = 'BLENDED'
            except Exception: pass
    if emit:
        b.inputs['Emission Color'].default_value = (*col, 1); b.inputs['Emission Strength'].default_value = emit
    MATS[name] = m; return m

# テクスチャの 1枚が 何 m か（世界座標で UV をはる）
TILE = {'asphalt': 6.0, 'grass': 5.0, 'lot': 6.0, 'paving': 2.4, 'brick': 2.0, 'dirt': 8.0, 'concrete': 2.5, 'water': 4.0, 'soil': 3.0}
TEXFN = {'asphalt': tex_asphalt, 'grass': tex_grass, 'lot': tex_lot, 'paving': tex_paving, 'brick': tex_brick, 'dirt': tex_dirt,
         'concrete': tex_concrete, 'water': tex_water, 'soil': tex_soil, 'glass': tex_glass}
ROOFCOL = {'b': '#4a7fc4', 'k': '#3a4f78', 'g': '#647c90', 'G': '#4f9460', 'r': '#d8643c', 'R': '#9c5a3e', 'o': '#e8913c', 'y': '#dcb44c',
           'p': '#8a68b0', 's': '#7f868e'}
def material(key):
    """key：'pal' / 'asphalt' など / 'roof_b' / 'glass' / 'sign:…'（看板は sign() で先に作る）"""
    if key in MATS: return MATS[key]
    if key == 'pal': return make_mat('pal', Image.new('RGB', (8, 8)), .8)            # 中身は さいごに パレットで上書き
    if key.startswith('roof_'):
        c = key[5:]; return make_mat(key, tex_roof(ROOFCOL[c], 'tile' if c in 'Rrogk' else 'plain'), .75)
    if key in TEXFN: return make_mat(key, TEXFN[key](), .3 if key in ('glass', 'water') else .9)
    if key == 'lamp': return make_mat('lamp', None, .5, col=(1.0, .9, .62))                 # 夜に光る（ゲームで emissive）
    if key == 'clear':                                                                       # すけるガラス（店の中が見える）
        m = make_mat('clear', None, .05, col=(.75, .9, 1.0)); b = m.node_tree.nodes.get('Principled BSDF'); b.inputs['Alpha'].default_value = .28
        try: m.surface_render_method = 'BLENDED'
        except Exception: pass
        return m
    if key == 'neon': return make_mat('neon', None, .5, col=(.95, .98, 1.0))                # 看板の明かり・自販機
    raise KeyError(key)
def finish_palette():
    m = MATS.get('pal')
    if not m: return
    t = [n for n in m.node_tree.nodes if n.type == 'TEX_IMAGE'][0]
    t.image = to_image('palette', palette_image())

# =====================================================================
#  看板の絵（ラノベPOP v2）
# =====================================================================
_FONT = [None]
def font_path():
    if _FONT[0]: return _FONT[0]
    w = os.path.join(ROOT, 'fonts', 'LightNovelPOPv2.woff2')
    try:
        from fontTools.ttLib import TTFont
        p = os.path.join(bpy.app.tempdir or '/tmp', 'lnpop.otf'); f = TTFont(w); f.flavor = None; f.save(p); _FONT[0] = p; return p
    except Exception as e: print('font', e)
def F(sz):
    p = font_path(); return ImageFont.truetype(p, sz) if p else ImageFont.load_default()
def sign_img(text, w, h, bg, fg, border=None, sub=None, icon=None):
    W = 512 if w >= h else max(64, int(512 * w / h)); H = max(32, int(W * h / w))
    im = Image.new('RGB', (W, H), bg); d = ImageDraw.Draw(im)
    if border: d.rounded_rectangle([5, 5, W - 6, H - 6], radius=min(W, H) // 8, outline=border, width=max(4, H // 16))
    vertical = h > w * 1.6
    if vertical:
        sz = int(W * .7); f = F(sz)
        while sz * len(text) > H * .9 and sz > 10: sz -= 2; f = F(sz)
        for i, ch in enumerate(text): d.text((W / 2, H / 2 + (i - (len(text) - 1) / 2) * sz * 1.02), ch, font=f, fill=fg, anchor='mm')
        return im
    sz = int(H * (.5 if sub else .62)); f = F(sz)
    while d.textlength(text, font=f) > W * .86 and sz > 8: sz -= 2; f = F(sz)
    d.text((W / 2, H * (.4 if sub else .52)), text, font=f, fill=fg, anchor='mm')
    if sub:
        f2 = F(int(H * .2)); d.text((W / 2, H * .8), sub, font=f2, fill=fg, anchor='mm')
    return im
SIGNS = {}
def sign_mat(text, w, h, bg, fg, border=None, sub=None, emit=0.0):
    key = 'sign:%s:%s:%s' % (text, bg, sub)
    if key not in MATS:
        n = 'sign_%d' % len(SIGNS); SIGNS[key] = n
        m = make_mat(n, sign_img(text, w, h, bg, fg, border, sub), .7); MATS[key] = m
    return key
def pic_mat(name, pil, rough=.8, alpha=False):
    key = 'pic:' + name
    if key not in MATS: MATS[key] = make_mat('pic_' + name, pil, rough, alpha)
    return key

# =====================================================================
#  メッシュを組み立てる入れもの（建物 1つ・道 1本 など）
# =====================================================================
class MB:
    def __init__(self, name):
        self.name = name; self.v = []; self.faces = []        # faces: (idx list, uv list, matkey, smooth)
    def _add(self, pts):
        i = len(self.v); self.v.extend(pts); return list(range(i, i + len(pts)))
    def face(self, pts, col=None, tex=None, uvs=None, smooth=False, n=None):
        """pts：ゲーム座標の点。col（#色）か tex（テクスチャ名）。n をわたすと 向きをそろえる"""
        pts = [tuple(map(float, p)) for p in pts]
        if n is not None:
            a, b, c = Vector(pts[0]), Vector(pts[1]), Vector(pts[2]); nn = (b - a).cross(c - a)
            if nn.length < 1e-12 and len(pts) > 3: nn = (Vector(pts[2]) - a).cross(Vector(pts[3]) - a)
            if nn.dot(Vector(n)) < 0: pts = pts[::-1]; uvs = uvs[::-1] if uvs else None
        if col is not None:
            uv = pal_uv(col); uvs = [uv] * len(pts); key = 'pal'
        else:
            key = tex
            if uvs is None: uvs = self.world_uv(pts, tex)
        self.faces.append((self._add(pts), uvs, key, smooth))
    @staticmethod
    def world_uv(pts, tex):
        t = TILE.get(tex, 2.0)
        a, b, c = Vector(pts[0]), Vector(pts[1]), Vector(pts[2]); n = (b - a).cross(c - a)
        ax = max(range(3), key=lambda i: abs(n[i])) if n.length > 0 else 1
        if ax == 1: return [(p[0] / t, -p[2] / t) for p in pts]
        if ax == 0: return [(p[2] / t, p[1] / t) for p in pts]
        return [(p[0] / t, p[1] / t) for p in pts]
    def mesh(self, verts, faces, col=None, tex=None, smooth=True, uvs=None):
        """頂点を共有する形（球・円柱など）。faces は verts の番号"""
        base = len(self.v); self._add([tuple(map(float, p)) for p in verts])
        for k, f in enumerate(faces):
            idx = [base + i for i in f]
            if col is not None: uv = pal_uv(col); fu = [uv] * len(f); key = 'pal'
            else:
                key = tex; fu = [uvs[i] for i in f] if uvs else self.world_uv([verts[i] for i in f], tex)
            self.faces.append((idx, fu, key, smooth))
    def empty(self): return not self.faces
    def build(self, parent=None, coll=None):
        if not self.faces: return None
        # 使っている頂点だけを 0 から番号づけ
        me = bpy.data.meshes.new(self.name)
        keys = []; kidx = {}
        for f in self.faces:
            if f[2] not in kidx: kidx[f[2]] = len(keys); keys.append(f[2])
        me.from_pydata([bl(p) for p in self.v], [], [f[0] for f in self.faces])
        uvl = me.uv_layers.new(name='UVMap')
        uvs = []
        for f in self.faces: uvs.extend(f[1])
        uvl.data.foreach_set('uv', np.array(uvs, np.float32).ravel())
        me.polygons.foreach_set('material_index', [kidx[f[2]] for f in self.faces])
        me.polygons.foreach_set('use_smooth', [f[3] for f in self.faces])
        for k in keys: me.materials.append(material(k))
        me.update()
        o = bpy.data.objects.new(self.name, me)
        (coll or bpy.context.scene.collection).objects.link(o)
        if parent is not None: o.parent = parent
        return o

# =====================================================================
#  形
# =====================================================================
def box(mb, x0, x1, y0, y1, z0, z1, col=None, tex=None, sides='all', top=True, bottom=False):
    x0, x1 = min(x0, x1), max(x0, x1); y0, y1 = min(y0, y1), max(y0, y1); z0, z1 = min(z0, z1), max(z0, z1)
    F = {'+x': ([(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)], (1, 0, 0)),
         '-x': ([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0)),
         '+z': ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1)),
         '-z': ([(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)], (0, 0, -1))}
    for k, (p, n) in F.items():
        if sides == 'all' or k in sides: mb.face(p, col, tex, n=n)
    if top: mb.face([(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)], col, tex, n=(0, 1, 0))
    if bottom: mb.face([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], col, tex, n=(0, -1, 0))
def obox(mb, cx, cz, hw, hd, y0, y1, ang, col=None, tex=None, top=True):
    """向きのある箱（ang：ラジアン。x 軸から z 軸へ）"""
    c, s = math.cos(ang), math.sin(ang)
    P = [(cx + dx * c - dz * s, cz + dx * s + dz * c) for dx, dz in [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]]
    prism(mb, P, y0, y1, col, tex, top=top)
def prism(mb, poly, y0, y1, col=None, tex=None, top=True, side_col=None, side_tex=None, bottom=False):
    """多角形（x, z）を y0〜y1 に のばす（凸でなくてもよい：上面は earcut）"""
    poly = ccw(poly)
    n = len(poly)
    for i in range(n):
        (ax, az), (bx, bz) = poly[i], poly[(i + 1) % n]
        if abs(ax - bx) + abs(az - bz) < 1e-6: continue
        nx, nz = bz - az, -(bx - ax)
        mb.face([(ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az)], side_col or col, side_tex or tex, n=(nx, 0, nz))
    if top: flat(mb, [poly], y1, col, tex)
    if bottom: flat(mb, [poly], y0, col, tex, up=False)
def ccw(poly):
    a = 0
    for i in range(len(poly)):
        x0, z0 = poly[i]; x1, z1 = poly[(i + 1) % len(poly)]; a += x0 * z1 - x1 * z0
    return list(poly) if a < 0 else list(poly)[::-1]      # z が南向きなので、上から見て反時計まわり＝ここでは a<0
def flat(mb, rings, y, col=None, tex=None, up=True):
    """水平な面（rings[0] が外がわ、のこりは穴）。earcut で三角形に"""
    import mapbox_earcut as earcut
    pts = []; ends = []
    for r in rings:
        r = list(r)
        if len(r) > 1 and r[0] == r[-1]: r = r[:-1]
        pts.extend(r); ends.append(len(pts))
    if len(pts) < 3: return
    arr = np.array(pts, np.float64)
    tri = earcut.triangulate_float64(arr, np.array(ends, np.uint32))
    V = [(p[0], y, p[1]) for p in pts]
    F = [tuple(int(v) for v in tri[i:i + 3]) for i in range(0, len(tri), 3)]
    # 向きをそろえる（上向き）
    out = []
    for f in F:
        a, b, c = (Vector(V[i]) for i in f); nn = (b - a).cross(c - a)
        if (nn.y < 0) == up: f = f[::-1]
        out.append(f)
    if col is not None: mb.mesh(V, out, col=col, smooth=False)
    else:
        t = TILE.get(tex, 2.0); uvs = [(p[0] / t, -p[2] / t) for p in V]
        mb.mesh(V, out, tex=tex, smooth=False, uvs=uvs)
def cyl(mb, x, y0, z, r, h, col=None, tex=None, seg=10, r2=None, cap=True, smooth=True):
    r2 = r if r2 is None else r2; V = []; Fc = []
    for i in range(seg):
        a = i / seg * math.tau; V.append((x + math.cos(a) * r, y0, z + math.sin(a) * r)); V.append((x + math.cos(a) * r2, y0 + h, z + math.sin(a) * r2))
    for i in range(seg):
        j = (i + 1) % seg; Fc.append((2 * i, 2 * i + 1, 2 * j + 1, 2 * j))
    # 外向きに
    a, b, c = Vector(V[0]), Vector(V[1]), Vector(V[3]); nn = (b - a).cross(c - a)
    if nn.dot(Vector((V[0][0] - x, 0, V[0][2] - z))) < 0: Fc = [f[::-1] for f in Fc]
    mb.mesh(V, Fc, col, tex, smooth)
    if cap and r2 > 0: mb.face([(x + math.cos(i / seg * math.tau) * r2, y0 + h, z + math.sin(i / seg * math.tau) * r2) for i in range(seg)], col, tex, n=(0, 1, 0))
def bar(mb, a, b, r, col, seg=6):
    A, B = Vector(a), Vector(b); d = B - A; L = d.length
    if L < 1e-6: return
    q = d.normalized(); up = Vector((0, 1, 0)) if abs(q.y) < .9 else Vector((1, 0, 0))
    u = q.cross(up).normalized(); v = q.cross(u).normalized()
    V = []
    for i in range(seg):
        t = i / seg * math.tau; o = u * math.cos(t) * r + v * math.sin(t) * r
        V.append(tuple(A + o)); V.append(tuple(B + o))
    Fc = [(2 * i, 2 * ((i + 1) % seg), 2 * ((i + 1) % seg) + 1, 2 * i + 1) for i in range(seg)]
    a0, b0, c0 = Vector(V[0]), Vector(V[2]), Vector(V[3]); nn = (b0 - a0).cross(c0 - a0)
    if nn.dot(Vector(V[0]) - A) < 0: Fc = [f[::-1] for f in Fc]
    mb.mesh(V, Fc, col, None, True)
def ball(mb, x, y, z, rx, ry, rz, col=None, seg=10, rings=6, smooth=True, jitter=0.0, rnd=None):
    V = [(x, y + ry, z)]
    for j in range(1, rings):
        t = j / rings * math.pi
        for i in range(seg):
            a = i / seg * math.tau; k = 1 + (rnd.uniform(-jitter, jitter) if rnd and jitter else 0)
            V.append((x + math.sin(t) * math.cos(a) * rx * k, y + math.cos(t) * ry * k, z + math.sin(t) * math.sin(a) * rz * k))
    V.append((x, y - ry, z)); bot = len(V) - 1
    Fc = []
    for i in range(seg): Fc.append((0, 1 + (i + 1) % seg, 1 + i))
    for j in range(rings - 2):
        for i in range(seg):
            a = 1 + j * seg + i; b = 1 + j * seg + (i + 1) % seg
            Fc.append((a, b, b + seg, a + seg))
    for i in range(seg): Fc.append((bot, 1 + (rings - 2) * seg + i, 1 + (rings - 2) * seg + (i + 1) % seg))
    # 外向き
    f = Fc[0]; a, b, c = (Vector(V[i]) for i in f); nn = (b - a).cross(c - a)
    if nn.y < 0: Fc = [ff[::-1] for ff in Fc]
    mb.mesh(V, Fc, col, None, smooth)
def cone(mb, x, y0, z, r, h, col, seg=10):
    V = [(x + math.cos(i / seg * math.tau) * r, y0, z + math.sin(i / seg * math.tau) * r) for i in range(seg)] + [(x, y0 + h, z)]
    Fc = [(i, seg, (i + 1) % seg) for i in range(seg)]
    a, b, c = (Vector(V[i]) for i in Fc[0]); nn = (b - a).cross(c - a)
    if nn.dot(Vector((V[0][0] - x, 0, V[0][2] - z))) < 0: Fc = [f[::-1] for f in Fc]
    mb.mesh(V, Fc, col, None, True)
    mb.face(V[:seg], col, n=(0, -1, 0))
def quad_uv(mb, pts, key, uvs=((0, 0), (1, 0), (1, 1), (0, 1))):
    """看板・ガラスなど テクスチャ1枚を はる四角形（pts は 表から見て 左下・右下・右上・左上）"""
    mb.face(pts, None, key, uvs=list(uvs))
def wall_quad(mb, a, b, y0, y1, col=None, tex=None, both=False):
    """a→b（x, z）の たての かべ。右がわ（a→b を前に見て）を おもてに"""
    (ax, az), (bx, bz) = a, b; nx, nz = bz - az, -(bx - ax)
    mb.face([(ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az)], col, tex, n=(nx, 0, nz))
    if both: mb.face([(ax, y0, az), (bx, y0, bz), (bx, y1, bz), (ax, y1, az)], col, tex, n=(-nx, 0, -nz))
