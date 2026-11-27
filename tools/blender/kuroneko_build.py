# =====================================================================
#  黒ねこ（デバッグ用キャラ）を Blender で組み立てて、アニメつきの glb に書き出す
#    pip の bpy：  python tools/blender/kuroneko_build.py models/kuroneko.glb
#    Blender 本体：blender -b -P tools/blender/kuroneko_build.py -- models/kuroneko.glb
#
#  寸法は 4 枚の設定画（正面・横・うしろ・ななめ）から測った値（頭の幅を 1.0 とした単位）
#    髪：中心 z1.09・幅 1.00・奥行き .88・高さ .94（てっぺん 1.56）。前髪のすそ z.88（ギザギザ）、横とうしろのすそ z.79
#    顔：前髪の下に見える肌。幅 .61、あご z.71、口は「ω」
#    耳：てっぺん z1.75、外がわ x±.46。外は黒、内がわ白
#    首輪：z.63〜.71 の白いわっか＋銀の鈴　胴：z.42〜.65 黒　腹巻き：z.29〜.42 白（たて線）
#    足：x±.16 の短い足（つま先が白）　腕：肩 (±.29, z.58) → 先 (±.39, z.45)、先が白
#    しっぽ：腰のうしろの下から横へ U の字に出て上へ（x±.69）。先に銀の火の玉（幅.31・z.56〜1.0、正面にうず）
#  ボーン：root / hips / spine / head / arm.L,R / leg.L,R / tail1.L,R / tail2.L,R
#  アニメ：idle / walk / run / jump / fall / attack / attack2
# =====================================================================
import bpy, bmesh, math, sys
from mathutils import Vector

argv = sys.argv
out = argv[argv.index('--') + 1] if '--' in argv else next((a for a in argv[1:] if a.endswith('.glb')), 'kuroneko.glb')
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene; scn.render.fps = 30
D = math.radians

# ---------------------------------------------------------------------
#  材質（妖怪ウォッチ風：つやのある黒、やわらかい肌、銀はメタリック）
# ---------------------------------------------------------------------
def mat(name, rgb, rough=.45, metal=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    return m
M_HAIR = mat('hair', (.010, .010, .013), .62)
M_BLACK = mat('black', (.014, .014, .018), .7)
M_SHINE = mat('hair_shine', (.075, .078, .09), .8)
M_SKIN = mat('skin', (.98, .78, .64), .8)
M_WHITE = mat('white', (.90, .90, .92), .7)
M_LINE = mat('band_line', (.62, .63, .66), .7)
M_EARIN = mat('ear_inner', (.86, .85, .88), .75)
M_SILVER = mat('silver', (.86, .87, .90), .5, .2)
M_SWIRL = mat('silver_swirl', (.50, .51, .55), .55, .3)
M_INK = mat('ink', (.08, .05, .05), .6)

PARTS = []      # (オブジェクト, ボーン名 または ('tail', 'L'/'R'))
def add(o, bone, m, smooth=True, subd=0):
    o.data.materials.append(m)
    if smooth:
        for p in o.data.polygons: p.use_smooth = True
    if subd:
        md = o.modifiers.new('subd', 'SUBSURF'); md.levels = md.render_levels = subd
    PARTS.append((o, bone)); return o
def new_obj(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scn.collection.objects.link(o); return o
def ellipsoid(name, c, r, bone, m, seg=40, ring=20):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=ring, radius=1, location=c)
    o = bpy.context.active_object; o.name = name; o.scale = r; return add(o, bone, m)
def capsule(name, a, b, r, bone, m):
    a, b = Vector(a), Vector(b); d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=r, depth=d.length, location=(a + b) / 2)
    o = bpy.context.active_object; o.name = name; o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = d.to_track_quat('Z', 'Y')
    add(o, bone, m)
    for p, nm in ((a, 'A'), (b, 'B')): ellipsoid(name + nm, p, (r, r, r), bone, m, 20, 10)
    return o
def tube(name, pts, radius, bone, m, radii=None):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts) - 1)
    for i, (bp, p) in enumerate(zip(sp.bezier_points, pts)):
        bp.co = p; bp.handle_left_type = bp.handle_right_type = 'AUTO'
        if radii: bp.radius = radii[i]
    cu.bevel_depth = radius; cu.bevel_resolution = 5; cu.resolution_u = 20; cu.use_fill_caps = True
    o = bpy.data.objects.new(name, cu); scn.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o; o.select_set(True); bpy.ops.object.convert(target='MESH'); o = bpy.context.active_object; o.select_set(False)
    return add(o, bone, m)

# ---------------------------------------------------------------------
#  頭：髪（おかっぱ）・顔・口・耳
# ---------------------------------------------------------------------
HC = Vector((0, 0, 1.09)); HR = Vector((.50, .44, .47))
def hair_point(th, ph, k=1.0):
    """th：前が 0 の方位、ph：てっぺんが 0 の角度。k：ふくらみ"""
    return Vector((HC.x + HR.x * k * math.sin(ph) * math.sin(th), HC.y - HR.y * k * math.sin(ph) * math.cos(th), HC.z + HR.z * k * math.cos(ph)))
def hairline(th):
    """前髪〜すその角度。前は目の下まで、横とうしろは首まで。前髪はギザギザ"""
    a = abs(((th + math.pi) % (2 * math.pi)) - math.pi)          # 0（前）〜 π（うしろ）
    base = D(116) + (D(131) - D(116)) * min(1, max(0, (a - D(30)) / D(55)))
    u = ((th + 7) / D(10)) % 1; tri = 1 - 2 * abs(u - .5) * 2      # -1〜1 の三角波（毛先がとがる）
    teeth = D(5.5) * tri if a < D(80) else D(2.5) * tri
    return base + teeth
def hair_k(th, ph):
    """髪のふくらみ：下にいくほど少しふくらむ（ボブ）＋ 毛の束のでこぼこ（下のほうほど強い）"""
    k = 1.0 + .035 * max(0, math.sin(min(1, ph / D(110)) * math.pi / 2)) ** 3
    return k + .012 * min(1, max(0, (ph - D(55)) / D(40))) * abs(math.sin(th * 13))
NT, NP = 120, 32
bm = bmesh.new(); grid = []
for i in range(NT):
    th = i / NT * 2 * math.pi; lim = hairline(th); col = []
    for j in range(NP + 1):
        ph = lim * j / NP
        k = hair_k(th, ph)
        if j >= NP - 2: k *= .985 - .02 * (j - (NP - 2))                            # すそは少し内がわへ
        col.append(bm.verts.new(hair_point(th, max(ph, 1e-4), k)))
    grid.append(col)
for i in range(NT):
    a, b = grid[i], grid[(i + 1) % NT]
    for j in range(NP): bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
bmesh.ops.remove_doubles(bm, verts=[c[0] for c in grid], dist=1e-3)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
hair = new_obj('hair', bm)
sol = hair.modifiers.new('thick', 'SOLIDIFY'); sol.thickness = .03; sol.offset = -1
add(hair, 'head', M_HAIR, subd=1)
# 髪のつや：前と横の上のほうに、細いたての光のすじ（妖怪ウォッチ風のギザギザのつや）
bm = bmesh.new()
for i in range(34):
    th = D(-112) + D(224) * (i + .5) / 34
    p0 = D(66) + D(4) * math.sin(i * 2.3); p1 = p0 + D(8 + 7 * abs(math.sin(i * 1.7)))   # すじの上と下
    w = D(2.2)
    vs = [bm.verts.new(hair_point(th + dt, ph, hair_k(th + dt, ph) + .007)) for dt, ph in ((-w, p0), (w, p0), (w * .25, p1), (-w * .25, p1))]
    bm.faces.new(vs)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
add(new_obj('hairShine', bm), 'head', M_SHINE)
# 顔（前髪の下に少しだけ見える）
FC, FR = (0, -.09, .93), (.31, .28, .23)
ellipsoid('face', FC, FR, 'head', M_SKIN)
def face_y(x, z): return FC[1] - FR[1] * math.sqrt(max(0, 1 - (x / FR[0]) ** 2 - ((z - FC[2]) / FR[2]) ** 2))
# 口「ω」
pts = [Vector((x, face_y(x, z) - .003, z)) for x, z in (((u - .5) * .11, .80 - .022 * abs(math.sin(u * 2 * math.pi))) for u in [i / 16 for i in range(17)])]
tube('mouth', pts, .0055, 'head', M_INK)
# 耳：ふくらんだ三角（外は黒、内がわ白）。輪を積み上げて作る
def ear_mesh(name, base, tip, rx, flat, bulge, bone, m):
    ax = (tip - base); L = ax.length; ax.normalize()
    side = Vector((1, 0, 0)) - ax * ax.x; side.normalize(); fwd = ax.cross(side)
    bm = bmesh.new(); rings = []; N = 28
    for k in range(13):
        h = k / 12; r = rx * (1 - h) ** .85 * (1 + bulge * math.sin(math.pi * h)) + .012 * h
        c = base + ax * (L * h)
        rings.append([bm.verts.new(c + side * (r * math.cos(a)) + fwd * (r * flat * math.sin(a))) for a in [n / N * 2 * math.pi for n in range(N)]])
    for k in range(12):
        for n in range(N): bm.faces.new((rings[k][n], rings[k][(n + 1) % N], rings[k + 1][(n + 1) % N], rings[k + 1][n]))
    capv = bm.verts.new(tip + ax * .012)
    for n in range(N): bm.faces.new((rings[-1][n], rings[-1][(n + 1) % N], capv))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return add(new_obj(name, bm), bone, m, subd=1)
for s in (-1, 1):
    base = Vector((s * .31, -.04, 1.40)); tip = Vector((s * .42, -.07, 1.77))
    ear_mesh('ear%+d' % s, base, tip, .2, .55, .12, 'head', M_BLACK)
    ear_mesh('earIn%+d' % s, base + Vector((s * .01, -.085, .06)), tip + Vector((0, -.045, -.07)), .135, .22, .08, 'head', M_EARIN)

# ---------------------------------------------------------------------
#  体：首輪・鈴・胴・腹巻き・腰・足・腕
# ---------------------------------------------------------------------
bpy.ops.mesh.primitive_torus_add(major_radius=.19, minor_radius=.055, location=(0, -.01, .675), major_segments=48, minor_segments=16)
o = bpy.context.active_object; o.name = 'collar'; o.scale = (1.12, 1.0, .72); add(o, 'spine', M_WHITE)
ellipsoid('bell', (0, -.235, .655), (.048, .045, .048), 'spine', M_SILVER, 24, 12)
capsule('bellSlit', (-.02, -.278, .645), (.02, -.278, .645), .007, 'spine', M_SWIRL)
ellipsoid('torso', (0, 0, .53), (.285, .225, .17), 'spine', M_BLACK)
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=1, depth=1, location=(0, 0, .355))
o = bpy.context.active_object; o.name = 'band'; o.scale = (.29, .235, .13)
bv = o.modifiers.new('round', 'BEVEL'); bv.width = .25; bv.segments = 4; add(o, 'hips', M_WHITE)
for i in range(16):
    a = i / 16 * 2 * math.pi
    capsule('bandLine%d' % i, (math.sin(a) * .294, -math.cos(a) * .239, .31), (math.sin(a) * .294, -math.cos(a) * .239, .40), .0045, 'hips', M_LINE)
ellipsoid('lower', (0, 0, .25), (.25, .21, .1), 'hips', M_BLACK)
for s, nm in ((-1, 'leg.R'), (1, 'leg.L')):
    capsule('leg' + nm, (s * .16, 0, .20), (s * .16, -.01, .07), .085, nm, M_BLACK)
    ellipsoid('foot' + nm, (s * .16, -.02, .045), (.09, .1, .055), nm, M_BLACK, 24, 12)
    ellipsoid('toe' + nm, (s * .16, -.1, .03), (.055, .03, .03), nm, M_WHITE, 20, 10)
for s, nm in ((-1, 'arm.R'), (1, 'arm.L')):
    capsule('arm' + nm, (s * .27, -.01, .58), (s * .375, -.02, .47), .055, nm, M_BLACK)
    ellipsoid('claw' + nm, (s * .395, -.025, .445), (.04, .035, .035), nm, M_WHITE, 20, 10)

# ---------------------------------------------------------------------
#  しっぽ：腰のうしろの下から横へ U の字に出て上へ。先に銀の火の玉
# ---------------------------------------------------------------------
TAIL_SPLIT = .52      # これより外がわは tail2 のボーン
for s, side in ((-1, 'R'), (1, 'L')):
    pts = [Vector((s * .03, .21, .24)), Vector((s * .30, .25, .18)), Vector((s * .54, .18, .23)), Vector((s * .66, .1, .36)), Vector((s * .69, .06, .48)), Vector((s * .665, .04, .58))]
    tube('tail' + side, pts, .03, ('tail', side), M_BLACK, radii=[1.1, 1, 1, .95, .92, .9])
    c = Vector((s * .655, .03, .69))
    ellipsoid('wisp' + side, c, (.155, .12, .14), 'tail2.' + side, M_SILVER)
    # 火の先：少し外がわへ曲がったとがり
    tip = [c + Vector((0, 0, .05)), c + Vector((s * .01, 0, .16)), c + Vector((s * .045, 0, .27)), c + Vector((s * .06, 0, .31))]
    tube('wispTip' + side, tip, .12, 'tail2.' + side, M_SILVER, radii=[1, .62, .22, .02])
    # 正面のうず
    sp = []
    for i in range(40):
        u = i / 39; r = .075 * (1 - u * .85); a = u * 2.2 * math.pi
        sp.append(c + Vector((r * math.cos(a) * s, -.118 + .01 * u, r * math.sin(a) - .005)))
    tube('swirl' + side, sp, .011, 'tail2.' + side, M_SWIRL)

# ---------------------------------------------------------------------
#  ボーン
# ---------------------------------------------------------------------
ad = bpy.data.armatures.new('rig'); rig = bpy.data.objects.new('rig', ad); scn.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT'); E = ad.edit_bones
def bone(name, h, t, parent=None):
    b = E.new(name); b.head = h; b.tail = t
    if parent: b.parent = E[parent]
bone('root', (0, 0, 0), (0, 0, .15))
bone('hips', (0, 0, .20), (0, 0, .42), 'root')
bone('spine', (0, 0, .42), (0, 0, .72), 'hips')
bone('head', (0, 0, .72), (0, 0, 1.56), 'spine')
for s, side in ((-1, 'R'), (1, 'L')):
    bone('arm.' + side, (s * .27, 0, .58), (s * .39, 0, .45), 'spine')
    bone('leg.' + side, (s * .16, 0, .22), (s * .16, 0, .02), 'hips')
    bone('tail1.' + side, (s * .03, .21, .24), (s * TAIL_SPLIT, .2, .21), 'hips')
    bone('tail2.' + side, (s * TAIL_SPLIT, .2, .21), (s * .66, .03, 1.0), 'tail1.' + side)
bpy.ops.object.mode_set(mode='OBJECT')

# 部品ごとにボーンの重み（しっぽは根元側と先側で分ける）→ 1 つのメッシュにまとめる
for o, b in PARTS:
    bpy.context.view_layer.objects.active = o
    for md in list(o.modifiers): bpy.ops.object.modifier_apply(modifier=md.name)
    if isinstance(b, tuple):
        side = b[1]; g1 = o.vertex_groups.new(name='tail1.' + side); g2 = o.vertex_groups.new(name='tail2.' + side)
        for v in o.data.vertices:
            x = abs((o.matrix_world @ v.co).x); w = min(1, max(0, (x - (TAIL_SPLIT - .08)) / .16))
            if w < 1: g1.add([v.index], 1 - w, 'REPLACE')
            if w > 0: g2.add([v.index], w, 'REPLACE')
    else:
        o.vertex_groups.new(name=b).add([v.index for v in o.data.vertices], 1.0, 'REPLACE')
bpy.ops.object.select_all(action='DESELECT')
for o, _ in PARTS: o.select_set(True)
bpy.context.view_layer.objects.active = PARTS[0][0]
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.join()
mesh = bpy.context.active_object; mesh.name = 'kuroneko'; mesh.parent = rig
# 妖怪ウォッチ風の黒いふち（裏返した殻：外へ少しふくらませて、裏面だけ描く）
M_OUT = mat('outline', (0, 0, 0), 1.0); M_OUT.use_backface_culling = True
mesh.data.materials.append(M_OUT)
sol = mesh.modifiers.new('outline', 'SOLIDIFY'); sol.thickness = .011; sol.offset = 1; sol.use_flip_normals = True; sol.use_rim = False
sol.material_offset = len(mesh.data.materials) - 1
mesh.modifiers.new('rig', 'ARMATURE').object = rig

# ---------------------------------------------------------------------
#  アニメ（立った骨：X＝前後にかたむく、Y＝ひねり、Z＝横にかたむく）
# ---------------------------------------------------------------------
PB = rig.pose.bones
for p in PB: p.rotation_mode = 'XYZ'
def pose(frame, rot=None, loc=None):
    for p in PB: p.rotation_euler = (0, 0, 0); p.location = (0, 0, 0)
    for n, r in (rot or {}).items(): PB[n].rotation_euler = tuple(D(v) for v in r)
    for n, l in (loc or {}).items(): PB[n].location = l
    for p in PB: p.keyframe_insert('rotation_euler', frame=frame); p.keyframe_insert('location', frame=frame)
def action(name, keys):
    rig.animation_data_create(); act = bpy.data.actions.new(name); rig.animation_data.action = act
    for f, kw in keys: pose(f, **kw)
    act.use_fake_user = True
def tails(sw, up=0):
    return {'tail1.L': (up, 0, sw), 'tail1.R': (up, 0, -sw), 'tail2.L': (0, 0, sw * .8), 'tail2.R': (0, 0, -sw * .8)}
def cyc(n, f): return [(round(i * n / 4), f(i)) for i in range(5)]
action('idle', cyc(48, lambda i: dict(rot={'head': (0, [0, 5, 0, -5, 0][i], [0, 2, 0, -2, 0][i]), 'arm.L': (0, 0, [0, 4, 0, 4, 0][i]), 'arm.R': (0, 0, -[0, 4, 0, 4, 0][i]), **tails([0, 7, 0, -7, 0][i])},
                                      loc={'hips': (0, [0, -.018, 0, -.018, 0][i], 0)})))
def walk(i, a=30, b=30, bob=.035, lean=0, tl=10):
    s = [1, 0, -1, 0, 1][i]
    return dict(rot={'leg.L': (a * s, 0, 0), 'leg.R': (-a * s, 0, 0), 'arm.L': (-b * s, 0, 0), 'arm.R': (b * s, 0, 0),
                     'spine': (lean, 5 * s, 0), 'head': (-lean * .6, -3 * s, 0), **tails(tl * s, -lean)},
                loc={'hips': (0, [0, 1, 0, 1, 0][i] * bob, 0)})
action('walk', cyc(24, lambda i: walk(i)))
action('run', cyc(16, lambda i: walk(i, 50, 55, .07, 16, 18)))
action('jump', [
    (0, dict(rot={'leg.L': (-35, 0, 0), 'leg.R': (-35, 0, 0), 'spine': (14, 0, 0), 'head': (-6, 0, 0), **tails(0, 20)}, loc={'hips': (0, -.08, 0)})),
    (4, dict(rot={'leg.L': (12, 0, 0), 'leg.R': (12, 0, 0), 'arm.L': (0, 0, -110), 'arm.R': (0, 0, 110), 'spine': (-8, 0, 0), **tails(0, -28)})),
    (12, dict(rot={'leg.L': (-50, 0, 0), 'leg.R': (-50, 0, 0), 'arm.L': (0, 0, -75), 'arm.R': (0, 0, 75), 'spine': (6, 0, 0), **tails(14, -10)})),
])
action('fall', [(0, dict(rot={'leg.L': (22, 0, 0), 'leg.R': (-12, 0, 0), 'arm.L': (0, 0, -140), 'arm.R': (0, 0, 140), **tails(-10, 26)})),
                (8, dict(rot={'leg.L': (-12, 0, 0), 'leg.R': (22, 0, 0), 'arm.L': (0, 0, -130), 'arm.R': (0, 0, 130), **tails(10, 26)})),
                (16, dict(rot={'leg.L': (22, 0, 0), 'leg.R': (-12, 0, 0), 'arm.L': (0, 0, -140), 'arm.R': (0, 0, 140), **tails(-10, 26)}))])
# 攻撃1：ためて、右手のねこパンチ
action('attack', [
    (0, dict(rot={})),
    (4, dict(rot={'arm.R': (45, 0, 0), 'spine': (0, -22, 0), 'head': (0, 8, 0), 'leg.L': (-10, 0, 0), **tails(-14)})),
    (8, dict(rot={'arm.R': (-105, 0, 0), 'spine': (-8, 24, 0), 'head': (0, -8, 0), 'leg.L': (-25, 0, 0), 'leg.R': (20, 0, 0), **tails(22)}, loc={'hips': (0, -.03, 0)})),
    (14, dict(rot={'arm.R': (-75, 0, 0), 'spine': (-4, 12, 0), **tails(12)})),
    (20, dict(rot={})),
])
# 攻撃2：その場で一回転して、2 本のしっぽでなぎ払う
action('attack2', [
    (0, dict(rot={})),
    (3, dict(rot={'spine': (10, 0, 0), **tails(-25, 12)}, loc={'hips': (0, -.05, 0)})),
    (8, dict(rot={'root': (0, 180, 0), 'arm.L': (0, 0, -80), 'arm.R': (0, 0, 80), **tails(35, -38)}, loc={'hips': (0, .06, 0)})),
    (13, dict(rot={'root': (0, 360, 0), 'arm.L': (0, 0, -80), 'arm.R': (0, 0, 80), **tails(35, -38)})),
    (20, dict(rot={})),
])
rig.animation_data.action = bpy.data.actions['idle']

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_animation_mode='ACTIONS', export_force_sampling=True,
                          export_apply=True, export_yup=True, export_skins=True, export_def_bones=False)
bpy.ops.wm.save_as_mainfile(filepath=out.replace('.glb', '.blend'))
print('wrote', out)
