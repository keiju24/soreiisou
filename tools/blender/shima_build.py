"""
風情ウォッチバスターズ「シマさん」の 3D モデルを作って models/shima.glb（と .blend）に書き出す。

  python tools/blender/shima_build.py models/shima.glb      （pip install bpy の bpy で動く）
  blender --background --python tools/blender/shima_build.py -- models/shima.glb

- 前は Blender の -Y（glTF の +Z）。高さ約 2.0。
- 骨：root / body / head / arm.L / arm.R / leg.L / leg.R / tail（ゲームは leg.* arm.* head tail の名前で骨を動かす）
- アニメ Idle / Walk も入れてある（ゲームでは使わず、ほかのビューアでの確認用）
- 輪郭線（反転シェル）は .blend だけ。glb には入れない
"""
import sys, os
_args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
GLB_PATH = os.path.abspath(_args[0] if _args else "models/shima.glb")

import bpy, bmesh, math, random
from mathutils import Vector, Matrix

random.seed(7)

# ------------------------------------------------------------------ reset
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.images,
             bpy.data.cameras, bpy.data.lights):
    for d in list(coll):
        coll.remove(d)

scene = bpy.context.scene
COL = bpy.data.collections.get("Character") or bpy.data.collections.new("Character")
if COL.name not in scene.collection.children:
    scene.collection.children.link(COL)


def link(obj):
    COL.objects.link(obj)
    return obj

# ------------------------------------------------------------------ materials
def mat(name, color, rough=0.65, emit=0.0, emit_color=None, spec=0.15):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = spec
    if emit > 0:
        p.inputs["Emission Color"].default_value = (*(emit_color or color), 1)
        p.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = (*color, 1)
    return m


M_SKIN = mat("Skin", (0.80, 0.46, 0.28))
M_HAIR = mat("Hair", (0.012, 0.016, 0.04), rough=0.45)
M_BODY = mat("Body_White", (0.90, 0.86, 0.78))
M_BELLY = mat("Belly_Blue", (0.42, 0.65, 0.85))
M_SWIRL_BLUE = mat("Swirl_DarkBlue", (0.20, 0.42, 0.68))
M_RED = mat("Swirl_Red", (0.62, 0.12, 0.10))
M_CHEEK = mat("Cheek_Swirl", (0.62, 0.25, 0.14))
M_TAIL = mat("Tail_Blue", (0.20, 0.38, 0.68))
M_CLOTH = mat("Cloth_Green_Plain", (0.30, 0.42, 0.12))
M_MOUTH = mat("Mouth", (0.18, 0.05, 0.04))
M_TEETH = mat("Teeth", (0.95, 0.95, 0.92))
M_BROW = mat("Brow", (0.05, 0.05, 0.10))
M_EYE = mat("Eye_Glow", (0.8, 0.95, 1.0), emit=4.0, emit_color=(0.6, 0.85, 1.0))
M_FLAME = mat("Flame_Blue", (0.25, 0.55, 1.0), emit=1.2, emit_color=(0.15, 0.50, 1.0))
M_FLAME_SW = mat("Flame_Swirl", (0.15, 0.40, 0.85), emit=0.6, emit_color=(0.05, 0.25, 0.8))

# outline material (inverted hull): black on front faces of flipped shell, transparent on back faces
M_OUT = bpy.data.materials.new("Outline")
M_OUT.use_nodes = True
nt = M_OUT.node_tree
nt.nodes.clear()
o_out = nt.nodes.new("ShaderNodeOutputMaterial")
mix = nt.nodes.new("ShaderNodeMixShader")
geo = nt.nodes.new("ShaderNodeNewGeometry")
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (0.01, 0.01, 0.015, 1)
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
lp = nt.nodes.new("ShaderNodeLightPath")
inv = nt.nodes.new("ShaderNodeMath"); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0
nt.links.new(geo.outputs["Backfacing"], inv.inputs[1])
mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'
nt.links.new(inv.outputs[0], mul.inputs[0])
nt.links.new(lp.outputs["Is Camera Ray"], mul.inputs[1])
nt.links.new(mul.outputs[0], mix.inputs[0])
nt.links.new(tr.outputs[0], mix.inputs[1])
nt.links.new(em.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], o_out.inputs["Surface"])
M_OUT.use_backface_culling = True
M_OUT.diffuse_color = (0, 0, 0, 1)


# bundle cloth: generated swirl texture + darker cell lines
def make_swirl_image(w=1024, h=512, cols=8, rows=4):
    import numpy as np
    img = np.zeros((h, w, 4), dtype=np.float32)
    base = np.array([0.30, 0.42, 0.12])
    line = np.array([0.72, 0.80, 0.42])
    edge = np.array([0.24, 0.35, 0.09])
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cw, ch = w / cols, h / rows
    row = np.floor(yy / ch)
    xs = xx / cw + 0.5 * (row % 2)
    cx = np.floor(xs)
    lx = (xs - cx) * 2 - 1
    ly = (yy / ch - row) * 2 - 1
    rng = np.random.default_rng(3)
    rot = rng.uniform(0, 2 * np.pi, size=(rows + 1, cols + 2))
    ang = rot[row.astype(int) % (rows + 1), cx.astype(int) % (cols + 2)]
    r = np.sqrt(lx ** 2 + ly ** 2)
    th = (np.arctan2(ly, lx) + ang) % (2 * np.pi)
    R, turns = 0.62, 2.2
    b = R / (turns * 2 * np.pi)
    k = (r / b - th) / (2 * np.pi)
    d = np.abs(k - np.round(k))
    spiral = (d < 0.16) & (r < R) & (r > 0.04)
    border = np.maximum(np.abs(lx), np.abs(ly)) > 0.95
    col = np.where(border[..., None], edge, base)
    col = np.where(spiral[..., None], line, col)
    img[..., :3] = col
    img[..., 3] = 1
    im = bpy.data.images.new("SwirlCloth", w, h)
    im.pixels.foreach_set(img.ravel())
    im.pack()
    return im


M_BUNDLE = bpy.data.materials.new("Cloth_Green_Swirl")
M_BUNDLE.use_nodes = True
p = M_BUNDLE.node_tree.nodes.get("Principled BSDF")
p.inputs["Roughness"].default_value = 0.8
if "Specular IOR Level" in p.inputs:
    p.inputs["Specular IOR Level"].default_value = 0.1
tex = M_BUNDLE.node_tree.nodes.new("ShaderNodeTexImage")
tex.image = make_swirl_image()
M_BUNDLE.node_tree.links.new(tex.outputs["Color"], p.inputs["Base Color"])
M_BUNDLE.diffuse_color = (0.30, 0.42, 0.12, 1)

# ------------------------------------------------------------------ mesh helpers
def finish_mesh(name, bm, m, loc=(0, 0, 0), smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = smooth
    me.materials.append(m)
    ob = link(bpy.data.objects.new(name, me))
    ob.location = loc
    return ob


def uv_sphere(name, loc, scale, m, segs=48, rings=24, deform=None):
    bm = bmesh.new()
    bm.loops.layers.uv.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0, calc_uvs=True)
    for v in bm.verts:
        v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2]))
        if deform:
            v.co = deform(v.co)
    return finish_mesh(name, bm, m, loc)


def cone_mesh(bm, base, direction, r, length, segs=8):
    d = Vector(direction).normalized()
    q = d.to_track_quat('Z', 'Y')
    mtx = Matrix.Translation(Vector(base) + d * (length / 2)) @ q.to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=0.0,
                          depth=length, matrix=mtx)


def add_outline(ob, t=0.009):
    ob.data.materials.append(M_OUT)
    md = ob.modifiers.new("Outline", 'SOLIDIFY')
    md.thickness = t
    md.offset = 1
    md.use_flip_normals = True
    md.use_rim = False
    md.material_offset = len(ob.data.materials) - 1


def apply_mods(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    ob.modifiers.clear()
    if ob.type == 'MESH':
        ob.data = me
    return me


def curve_to_mesh(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    new = link(bpy.data.objects.new(ob.name, me))
    new.matrix_world = ob.matrix_world
    cu = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    for poly in me.polygons:
        poly.use_smooth = True
    return new


def tube(name, pts, radius, m):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = radius
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for bp, pt in zip(sp.bezier_points, pts):
        bp.co = pt
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
    cu.materials.append(m)
    ob = link(bpy.data.objects.new(name, cu))
    return curve_to_mesh(ob)

# ------------------------------------------------------------------ decals (painted marks wrapped on surfaces)
def spiral_ribbon(turns=2.2, R=1.0, width=0.16, n=160):
    b = R / (turns * 2 * math.pi)
    pts = []
    t0, t1 = 0.9, turns * 2 * math.pi
    for i in range(n):
        th = t0 + (t1 - t0) * i / (n - 1)
        pts.append(Vector((b * th * math.cos(th), b * th * math.sin(th))))
    return ribbon(pts, lambda t: width)


def ribbon(pts, wfun):
    verts, faces = [], []
    n = len(pts)
    for i, pnt in enumerate(pts):
        a = pts[max(i - 1, 0)]
        c = pts[min(i + 1, n - 1)]
        tg = (c - a).normalized()
        nr = Vector((-tg.y, tg.x))
        w = wfun(i / (n - 1)) / 2
        verts += [pnt + nr * w, pnt - nr * w]
        if i:
            k = 2 * i
            faces.append((k - 2, k - 1, k + 1, k))
    return verts, faces


def star_fill(poly, rings=6):
    c = sum(poly, Vector((0, 0))) / len(poly)
    verts = [c]
    n = len(poly)
    for r in range(1, rings + 1):
        k = r / rings
        verts += [c + (p - c) * k for p in poly]
    faces = []
    for i in range(n):
        faces.append((0, 1 + i, 1 + (i + 1) % n))
    for r in range(1, rings):
        o0, o1 = 1 + (r - 1) * n, 1 + r * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((o0 + i, o1 + i, o1 + j, o0 + j))
    return verts, faces


def resample(poly, n=80):
    # smooth closed polygon via Catmull-Rom sampling
    out = []
    m = len(poly)
    for i in range(n):
        t = i / n * m
        k = int(t)
        f = t - k
        p0, p1, p2, p3 = (poly[(k + j) % m] for j in (-1, 0, 1, 2))
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f +
                          (-p0 + 3 * p1 - 3 * p2 + p3) * f ** 3))
    return out


def decal(name, vf, center, normal, target, m, scale=1.0, offset=0.004, roll=0.0, flip=False):
    verts2d, faces = vf
    me = bpy.data.meshes.new(name)
    sx = -1 if flip else 1
    cr, sr = math.cos(roll), math.sin(roll)
    v3 = []
    for v in verts2d:
        x, y = v.x * sx, v.y
        x, y = x * cr - y * sr, x * sr + y * cr
        v3.append((x * scale, 0.0, y * scale))
    if flip:
        faces = [tuple(reversed(f)) for f in faces]
    me.from_pydata(v3, [], faces)
    me.materials.append(m)
    ob = link(bpy.data.objects.new(name, me))
    n = Vector(normal).normalized()
    ob.rotation_euler = n.to_track_quat('-Y', 'Z').to_euler()
    ob.location = Vector(center) + n * 0.05
    sw = ob.modifiers.new("wrap", 'SHRINKWRAP')
    sw.target = target
    sw.wrap_method = 'NEAREST_SURFACEPOINT'
    sw.offset = offset
    apply_mods(ob)
    return ob

# ------------------------------------------------------------------ BODY
def body_deform(c):
    t = (0.40 - c.z) / 0.80          # 0 top -> 1 bottom
    f = 0.82 + 0.30 * t
    return Vector((c.x * f, c.y * f, c.z))

body = uv_sphere("Body", (0, 0.02, 0.62), (0.30, 0.26, 0.40), M_BODY, deform=body_deform)

legs = []
for sx in (-1, 1):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.095, radius2=0.105, depth=0.34,
                          matrix=Matrix.Translation((0, 0, 0)))
    bmesh.ops.bevel(bm, geom=[e for e in bm.edges if e.verts[0].co.z < -0.1 and e.verts[1].co.z < -0.1
                              and abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-4],
                    offset=0.035, segments=3, affect='EDGES')
    leg = finish_mesh("Leg_" + ("L" if sx > 0 else "R"), bm, M_BODY, (sx * 0.14, 0.03, 0.17))
    legs.append(leg)

# tail fin
bm = bmesh.new()
cone_mesh(bm, (0, 0, 0), (0, 0.55, -0.75), 0.075, 0.24, segs=16)
for v in bm.verts:
    v.co.x *= 0.35
tail = finish_mesh("Tail", bm, M_TAIL, (0, 0.18, 0.20))

# ------------------------------------------------------------------ HEAD
HC = Vector((0, -0.01, 1.40))
HR = (0.33, 0.31, 0.50)

def head_deform(c):
    if c.z < 0:
        t = -c.z / HR[2]
        c = Vector((c.x * (1 - 0.30 * t * t), c.y * (1 - 0.10 * t * t), c.z))
    return c

head = uv_sphere("Head", HC, HR, M_SKIN, segs=64, rings=32, deform=head_deform)
nose = uv_sphere("Nose", (0, -0.325, 1.335), (0.04, 0.06, 0.07), M_SKIN, segs=24, rings=12)
ears = [uv_sphere("Ear_" + s, (sx * 0.325, 0.03, 1.39), (0.035, 0.065, 0.095), M_SKIN, segs=24, rings=12)
        for s, sx in (("L", 1), ("R", -1))]


def head_point(x, z, extra=0.0):
    """point + normal on (undeformed) head ellipsoid front at given x,z"""
    lx, lz = x / HR[0], (z - HC.z) / HR[2]
    ly = -math.sqrt(max(1e-4, 1 - lx * lx - lz * lz))
    p = Vector((x, HC.y + ly * HR[1], z))
    n = Vector((lx / HR[0], ly / HR[1], lz / HR[2])).normalized()
    return p, n

# eyes (glowing almonds)
almond = [Vector((u, 0.42 * (1 - u * u) * (1 if s > 0 else -0.8)))
          for s in (1, -1) for u in ([i / 10 for i in range(-10, 11)] if s > 0 else [i / 10 for i in range(9, -10, -1)])]
for sx in (1, -1):
    p, n = head_point(sx * 0.125, 1.475)
    decal("Eye_" + ("L" if sx > 0 else "R"), star_fill(almond, 4), p, n, head, M_EYE,
          scale=0.058, offset=0.0065, roll=sx * 0.12)

# blue flames above eyes
flame = resample([Vector(v) for v in [(0.00, -0.10), (0.30, 0.00), (0.38, 0.28), (0.22, 0.52), (0.30, 0.78),
                                      (0.18, 1.05), (0.06, 1.42), (0.05, 1.08), (-0.08, 0.82), (-0.10, 0.58),
                                      (-0.30, 0.38), (-0.32, 0.08)]], 90)
for sx in (1, -1):
    p, n = head_point(sx * 0.12, 1.52)
    decal("Flame_" + ("L" if sx > 0 else "R"), star_fill(flame, 6), p, n, head, M_FLAME,
          scale=0.15, offset=0.0045, flip=(sx < 0), roll=-sx * 0.15)
    p2, n2 = head_point(sx * 0.122, 1.535)
    decal("FlameSwirl_" + ("L" if sx > 0 else "R"), spiral_ribbon(1.8, 1.0, 0.2), p2, n2, head, M_FLAME_SW,
          scale=0.028, offset=0.006, flip=(sx < 0))

# eyebrows (outer part, behind the flames)
brow_pts = [Vector((t, 0.25 * math.sin(t * math.pi))) for t in [i / 20 for i in range(21)]]
for sx in (1, -1):
    p, n = head_point(sx * 0.17, 1.575)
    decal("Brow_" + ("L" if sx > 0 else "R"), ribbon(brow_pts, lambda t: 0.10 + 0.12 * math.sin(t * math.pi)),
          p + Vector((sx * 0.03, 0, 0)), n, head, M_BROW, scale=0.11, offset=0.003, flip=(sx < 0), roll=-sx * 0.2)

# cheek swirls
for sx in (1, -1):
    p, n = head_point(sx * 0.21, 1.35)
    decal("CheekSwirl_" + ("L" if sx > 0 else "R"), spiral_ribbon(2.0, 1.0, 0.17), p, n, head, M_CHEEK,
          scale=0.042, offset=0.003, flip=(sx < 0))

# smile
arc = [Vector((u, 0.35 * u * u)) for u in [i / 30 - 1 for i in range(61)]]
p, n = head_point(0.0, 1.215)
decal("Mouth", ribbon(arc, lambda t: 0.06 + 0.22 * math.sin(t * math.pi) ** 1.5), p, n, head, M_MOUTH,
      scale=0.11, offset=0.003)
teeth_arc = [Vector((u * 0.72, 0.35 * (u * 0.72) ** 2 + 0.035)) for u in [i / 30 - 1 for i in range(61)]]
decal("Teeth", ribbon(teeth_arc, lambda t: 0.09 * math.sin(t * math.pi) ** 0.7), p, n, head, M_TEETH,
      scale=0.11, offset=0.0045)

# ------------------------------------------------------------------ HAIR
HHC = Vector((0, 0.02, 1.43))
HHR = (0.365, 0.345, 0.48)

def hair_keep(p):
    return (p.z > 1.68) or (p.y > 0.06 and p.z > 1.17) or (p.y > -0.10 and p.z > 1.47) or \
           (p.y > -0.20 and p.z > 1.60)

bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0)
for v in bm.verts:
    v.co = Vector((v.co.x * HHR[0], v.co.y * HHR[1], v.co.z * HHR[2]))
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not hair_keep(v.co + HHC)], context='VERTS')
bmesh.ops.translate(bm, verts=bm.verts, vec=HHC)

def ell(a, b, scale=1.0):
    s = Vector((math.sin(b) * math.cos(a), math.sin(b) * math.sin(a), math.cos(b)))
    p = HHC + Vector((HHR[0] * s.x, HHR[1] * s.y, HHR[2] * s.z)) * scale
    n = Vector((s.x / HHR[0], s.y / HHR[1], s.z / HHR[2])).normalized()
    return p, n

count = 0
for i in range(900):
    a = random.uniform(0, 2 * math.pi)
    b = math.acos(random.uniform(-0.75, 1.0))
    p, n = ell(a, b)
    if not hair_keep(p):
        continue
    down = max(0.0, 1.0 - (p.z - 1.2) / 0.6)
    d = (n + Vector((0, 0.35, -1.3)) * (0.6 + 0.9 * down) +
         Vector((random.uniform(-.25, .25), random.uniform(-.25, .25), random.uniform(-.2, .2)))).normalized()
    cone_mesh(bm, p - n * 0.05, d, random.uniform(0.05, 0.075), random.uniform(0.10, 0.17), segs=7)
    count += 1
    if count > 110:
        break
# spiky crown
for i in range(8):
    a = random.uniform(0, 2 * math.pi)
    b = random.uniform(0.05, 0.6)
    p, n = ell(a, b)
    d = (n + Vector((random.uniform(-.4, .4), 0.3, 0.2))).normalized()
    cone_mesh(bm, p - n * 0.04, d, random.uniform(0.05, 0.07), random.uniform(0.09, 0.14), segs=7)
# bangs over the forehead, swept to character's left
for i in range(16):
    x = random.uniform(-0.27, 0.30)
    lx = x / HHR[0]
    z = 1.77 + random.uniform(-0.01, 0.03) - 0.08 * lx * lx
    lz = (z - HHC.z) / HHR[2]
    y = HHC.y - HHR[1] * math.sqrt(max(0.01, 1 - lx * lx - lz * lz))
    d = Vector((0.35 + random.uniform(-0.15, 0.15), -0.35, -1.0)).normalized()
    cone_mesh(bm, Vector((x, y + 0.03, z)), d, random.uniform(0.045, 0.065), random.uniform(0.07, 0.11), segs=7)
# side burns / back fringe at nape
for sx in (1, -1):
    for k in range(3):
        cone_mesh(bm, Vector((sx * (0.30 - k * 0.02), -0.02 + k * 0.05, 1.53 - k * 0.03)),
                  Vector((sx * 0.25, 0.05, -1)), 0.05, 0.13, segs=7)
hair = finish_mesh("Hair", bm, M_HAIR, smooth=False)

# ------------------------------------------------------------------ BELLY + body marks
p_belly = Vector((0, -0.30, 0.55))
ellipse = [Vector((math.cos(t) * 1.0, math.sin(t) * 0.82)) for t in [i / 64 * 2 * math.pi for i in range(64)]]
decal("BellyPatch", star_fill(ellipse, 8), p_belly, (0, -1, 0), body, M_BELLY, scale=0.17, offset=0.003)
decal("BellySwirl", spiral_ribbon(2.2, 1.0, 0.16), p_belly + Vector((0, 0, 0.0)), (0, -1, 0), body,
      M_SWIRL_BLUE, scale=0.10, offset=0.005)
for sx in (1, -1):
    c = Vector((sx * 0.30, -0.06, 0.44))
    decal("HipSwirl_" + ("L" if sx > 0 else "R"), spiral_ribbon(2.2, 1.0, 0.18), c, (sx, -0.35, 0), body, M_RED,
          scale=0.075, offset=0.003, flip=(sx < 0))

# ------------------------------------------------------------------ BUNDLE (furoshiki) + arms
bundle = uv_sphere("Bundle", (0, 0.30, 0.80), (0.36, 0.21, 0.35), M_BUNDLE,
                   deform=lambda c: Vector((c.x, c.y + (0.05 if c.y < 0 else 0) * 0, c.z)))
bundle.rotation_euler = (math.radians(-8), 0, 0)

straps = []
for sx in (1, -1):
    straps.append(tube("Strap_" + ("L" if sx > 0 else "R"),
                       [(sx * 0.16, 0.22, 1.05), (sx * 0.20, 0.0, 1.05), (sx * 0.14, -0.22, 0.98),
                        (sx * 0.03, -0.30, 0.93)], 0.035, M_CLOTH))
knot = uv_sphere("Knot", (0, -0.31, 0.93), (0.05, 0.04, 0.045), M_CLOTH, segs=24, rings=12)
bm = bmesh.new()
for sx in (1, -1):
    cone_mesh(bm, (sx * 0.02, -0.31, 0.95), (sx * 0.9, -0.25, 0.55), 0.045, 0.13, segs=12)
for v in bm.verts:
    pass
flaps = finish_mesh("KnotFlaps", bm, M_CLOTH)

arms, hands = [], []
for sx in (1, -1):
    s = "L" if sx > 0 else "R"
    arms.append(tube("Arm_" + s, [(sx * 0.25, 0.02, 0.93), (sx * 0.22, -0.16, 0.86), (sx * 0.08, -0.29, 0.88)],
                     0.055, M_BODY))
    hands.append(uv_sphere("Hand_" + s, (sx * 0.055, -0.31, 0.90), (0.055, 0.05, 0.062), M_BODY, segs=24, rings=12))

# ------------------------------------------------------------------ outlines
for ob in [body, head, nose, hair, tail, bundle, knot, flaps] + legs + ears + straps + arms + hands:
    add_outline(ob, 0.006 if ob.name.startswith(("Nose", "Ear", "Knot", "Hand")) else 0.009)

# parent all to a root empty
root = link(bpy.data.objects.new("Character_Root", None))
for ob in COL.objects:
    if ob is not root:
        ob.parent = root

# ------------------------------------------------------------------ scene: lights, world, camera
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (1, 1, 1, 1)
bg.inputs[1].default_value = 0.75

sun_d = bpy.data.lights.new("Key", 'SUN')
sun_d.energy = 2.2
sun_d.angle = math.radians(20)
sun = bpy.data.objects.new("Key", sun_d)
scene.collection.objects.link(sun)
sun.rotation_euler = (math.radians(50), 0, math.radians(-25))

cam_d = bpy.data.cameras.new("Camera")
cam_d.type = 'ORTHO'
cam_d.ortho_scale = 2.25
cam = bpy.data.objects.new("Camera", cam_d)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (0, -6, 1.0)
cam.rotation_euler = (math.radians(90), 0, 0)

scene.view_settings.view_transform = 'Standard'
for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        scene.render.engine = eng
        break
    except TypeError:
        pass
scene.render.resolution_x = 1200
scene.render.resolution_y = 1200

# ================================================================ rig + export
scene = bpy.context.scene
scene.render.fps = 30
root_empty = bpy.data.objects["Character_Root"]

# ---------------------------------------------------------------- armature
arm_data = bpy.data.armatures.new("Rig")
rig = bpy.data.objects.new("Rig", arm_data)
COL.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
eb = arm_data.edit_bones

def bone(name, head, tail, parent=None):
    b = eb.new(name)
    b.head, b.tail = head, tail
    b.roll = 0
    if parent:
        b.parent = eb[parent]
    return b

bone("root", (0, 0, 0), (0, 0.3, 0))
bone("body", (0, 0.02, 0.30), (0, 0.02, 0.98), "root")
bone("head", (0, 0, 0.98), (0, 0, 1.90), "body")
bone("arm.L", (0.24, 0.0, 0.94), (0.06, -0.30, 0.90), "body")
bone("arm.R", (-0.24, 0.0, 0.94), (-0.06, -0.30, 0.90), "body")
bone("leg.L", (0.14, 0.03, 0.34), (0.14, 0.03, 0.02), "root")
bone("leg.R", (-0.14, 0.03, 0.34), (-0.14, 0.03, 0.02), "root")
bone("tail", (0, 0.18, 0.26), (0, 0.32, 0.06), "body")
for b in eb:
    b.use_deform = b.name != "root"
bpy.ops.object.mode_set(mode='OBJECT')

# ---------------------------------------------------------------- bind meshes (rigid skinning) and join into one mesh
def bone_for(name):
    if name.startswith(("Head", "Hair", "Nose", "Ear_", "Eye_", "Flame", "Brow_", "CheekSwirl", "Mouth", "Teeth")):
        return "head"
    for s in ("L", "R"):
        if name in ("Arm_" + s, "Hand_" + s):
            return "arm." + s
        if name == "Leg_" + s:
            return "leg." + s
    if name == "Tail":
        return "tail"
    return "body"

meshes = [o for o in COL.objects if o.type == 'MESH']
for ob in meshes:
    # drop the Blender-only outline shell; one outline is re-added on the joined mesh
    for md in list(ob.modifiers):
        ob.modifiers.remove(md)
    if "Outline" in ob.data.materials:
        ob.data.materials.pop(index=list(ob.data.materials).index(M_OUT))
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw
    ob.data.transform(mw)
    ob.matrix_world.identity()
    vg = ob.vertex_groups.new(name=bone_for(ob.name))
    vg.add(list(range(len(ob.data.vertices))), 1.0, 'REPLACE')

active = bpy.data.objects["Body"]
with bpy.context.temp_override(active_object=active, object=active, selected_objects=meshes,
                               selected_editable_objects=meshes):
    bpy.ops.object.join()
char = active
char.name = "Character"
char.data.name = "CharacterMesh"
bpy.data.objects.remove(root_empty, do_unlink=True)

char.parent = rig
md = char.modifiers.new("Armature", 'ARMATURE')
md.object = rig
char.data.materials.append(M_OUT)
ol = char.modifiers.new("Outline", 'SOLIDIFY')
ol.thickness, ol.offset, ol.use_flip_normals, ol.use_rim = 0.008, 1, True, False
ol.material_offset = len(char.data.materials) - 1

# ---------------------------------------------------------------- animations
pb = rig.pose.bones
for p in pb:
    p.rotation_mode = 'XYZ'

def key(action_name, frames, fn):
    rig.animation_data_create()
    act = bpy.data.actions.new(action_name)
    act.use_fake_user = True
    rig.animation_data.action = act
    for f in frames:
        for p in pb:
            p.location = (0, 0, 0)
            p.rotation_euler = (0, 0, 0)
        fn(f)
        for p in pb:
            p.keyframe_insert("location", frame=f)
            p.keyframe_insert("rotation_euler", frame=f)
    # cyclic & linear-ish
    track = rig.animation_data.nla_tracks.new()
    track.name = action_name
    strip = track.strips.new(action_name, 1, act)
    strip.name = action_name
    track.mute = True
    rig.animation_data.action = None
    return act

R = math.radians
IDLE_N = 60
def idle(f):
    t = (f - 1) / IDLE_N * 2 * math.pi
    pb["body"].location.y = 0.012 * (1 - math.cos(2 * t)) / 2 * -1   # local Y = up along bone
    pb["body"].location.y = 0.012 * math.sin(t)
    pb["head"].rotation_euler = (R(2) * math.sin(t + 0.6), 0, R(4) * math.sin(t * 0.5 + 0.3) * 0 + R(3) * math.sin(t))
    pb["arm.L"].rotation_euler.x = R(3) * math.sin(t)
    pb["arm.R"].rotation_euler.x = R(3) * math.sin(t)
    pb["tail"].rotation_euler.z = R(15) * math.sin(t)

WALK_N = 30
def walk(f):
    t = (f - 1) / WALK_N * 2 * math.pi
    s = math.sin(t)
    pb["leg.L"].rotation_euler.x = R(28) * s
    pb["leg.R"].rotation_euler.x = -R(28) * s
    pb["body"].location.y = 0.025 * abs(math.cos(t))
    pb["body"].rotation_euler.y = R(5) * s           # twist around up axis
    pb["body"].rotation_euler.z = R(3) * s           # side sway
    pb["head"].rotation_euler.z = -R(3) * s
    pb["head"].rotation_euler.x = R(2) * math.cos(2 * t)
    pb["arm.L"].rotation_euler.x = R(4) * s
    pb["arm.R"].rotation_euler.x = -R(4) * s
    pb["tail"].rotation_euler.z = R(25) * math.sin(t * 2)

act_idle = key("Idle", range(1, IDLE_N + 2, 2), idle)
act_walk = key("Walk", range(1, WALK_N + 2, 2), walk)
for act in (act_idle, act_walk):
    for fc in getattr(act, "fcurves", []) or []:
        fc.modifiers.new('CYCLES')

# default: Idle active
rig.animation_data.action = act_idle
scene.frame_start, scene.frame_end = 1, IDLE_N

# ---------------------------------------------------------------- export
os.makedirs(os.path.dirname(GLB_PATH) or '.', exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(GLB_PATH)[0] + ".blend", compress=True)

ol.show_viewport = ol.show_render = False
for o in bpy.data.objects:
    o.select_set(o in (rig, char))
bpy.ops.export_scene.gltf(filepath=GLB_PATH, export_format='GLB',
                          use_selection=True, export_apply=False, export_animations=True,
                          export_animation_mode='ACTIONS', export_skins=True, export_yup=True,
                          export_image_format='AUTO', export_anim_slide_to_zero=True)
ol.show_viewport = ol.show_render = True
print("EXPORT_OK")
