# 新キャラ「インポニャン」：もらった動かないモデル（models/src/imponyan_static.glb）に骨を入れて、
# debug-kuroneko.html と同じ名前のアニメ 7 つ（idle walk run jump fall attack attack2）をつけた glb を書き出す。
#   使い方：python tools/blender/imponyan_build.py models/imponyan.glb   （pip の bpy でも、Blender の Python でもよい）
# ・見た目（形・色）はもらったモデルのまま。大きさだけ黒ねこにそろえて 1.3 倍（背の高さ 約 1.8）
# ・パーツの名前で骨をきめる：耳・髪・顔・口 → head、そで・手 → arm、しっぽ・炎・うずまき → tail、つま先 → leg
#   つなぎ（体と足がひとつのメッシュ）は、高さと左右で 体 と 足 に分けて、さかいめはなめらかにまぜる
# ・左右：「Left」はモデルの ＋x がわ。骨の名前も .L＝＋x、.R＝−x
import bpy, bmesh, sys, os, math
from mathutils import Vector
D = math.radians
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
out = sys.argv[-1] if sys.argv[-1].endswith('.glb') else os.path.join(ROOT, 'models', 'imponyan.glb')
S = 1.3

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, 'models', 'src', 'imponyan_static.glb'))
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for o in bpy.data.objects:
    if o.type != 'MESH': bpy.data.objects.remove(o)
# 位置・大きさを頂点に焼きこむ（1.3 倍）
for o in meshes:
    o.data.transform(o.matrix_world); o.matrix_world.identity()
    o.data.transform(__import__('mathutils').Matrix.Scale(S, 4))

# ---- 骨 ----
P = lambda x, y, z: Vector((x * S, y * S, z * S))
arm = bpy.data.armatures.new('imponyan_rig'); rig = bpy.data.objects.new('rig', arm); bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT')
def bone(n, h, t, parent=None):
    b = arm.edit_bones.new(n); b.head = h; b.tail = t; b.roll = 0
    if parent: b.parent = arm.edit_bones[parent]
bone('body', P(0, 0, .26), P(0, 0, .58))
bone('head', P(0, 0, .58), P(0, 0, 1.25), 'body')
for s, side in ((1, 'L'), (-1, 'R')):
    bone('arm.' + side, P(s * .10, 0, .54), P(s * .28, -.01, .33), 'body')
    bone('leg.' + side, P(s * .11, 0, .27), P(s * .12, 0, .02), 'body')
    bone('tail.' + side, P(s * .02, .14, .2), P(s * .45, .31, .45), 'body')
bpy.ops.object.mode_set(mode='OBJECT')

# ---- どのパーツをどの骨に ----
def owner(name):
    n = name.lower(); side = 'L' if n.startswith('left') else 'R' if n.startswith('right') else None
    if any(k in n for k in ('ear', 'bob', 'face', 'smile')): return 'head'
    if side and any(k in n for k in ('sleeve', 'mitten')): return 'arm.' + side
    if side and any(k in n for k in ('tail', 'flame', 'spiral')): return 'tail.' + side
    if side and 'toe' in n: return 'leg.' + side
    return 'body'
for o in meshes:
    nm = o.name
    if 'romper' in nm.lower():       # つなぎ：足は高さと左右で、上は体
        vb = o.vertex_groups.new(name='body'); vl = o.vertex_groups.new(name='leg.L'); vr = o.vertex_groups.new(name='leg.R')
        for v in o.data.vertices:
            z = v.co.z / S; k = min(1, max(0, (.30 - z) / .12)); k = k * k * (3 - 2 * k)   # z .30 → .18 で 体 → 足
            if k < 1: vb.add([v.index], 1 - k, 'REPLACE')
            if k > 0: (vl if v.co.x >= 0 else vr).add([v.index], k, 'REPLACE')
    else:
        o.vertex_groups.new(name=owner(nm)).add([v.index for v in o.data.vertices], 1.0, 'REPLACE')
    print(f'{nm:45s} -> {owner(nm) if "romper" not in nm.lower() else "body/leg"}')

# 1つのメッシュにまとめて、骨で動かす
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]; bpy.ops.object.join()
mesh = bpy.context.active_object; mesh.name = 'imponyan'; mesh.parent = rig
mesh.modifiers.new('rig', 'ARMATURE').object = rig

# ---- アニメ ----
#  骨の向き：足・腕は X＋で後ろ、X−で前。体（body）は X＋で前にかたむく、Y でひねる。
#  腕を横に上げる：arm.L（＋x）は Z−、arm.R（−x）は Z＋
PB = rig.pose.bones
for p in PB: p.rotation_mode = 'XYZ'
def pose(frame, rot=None, loc=None):
    for p in PB: p.rotation_euler = (0, 0, 0); p.location = (0, 0, 0)
    for n, r in (rot or {}).items(): PB[n].rotation_euler = tuple(D(v) for v in r)
    for n, l in (loc or {}).items(): PB[n].location = tuple(v * S for v in l)
    for p in PB: p.keyframe_insert('rotation_euler', frame=frame); p.keyframe_insert('location', frame=frame)
def action(name, keys):
    rig.animation_data_create(); act = bpy.data.actions.new(name); rig.animation_data.action = act
    for f, kw in keys: pose(f, **kw)
    act.use_fake_user = True
def tails(sw, up=0): return {'tail.L': (up, 0, -sw), 'tail.R': (up, 0, sw)}
def arms(up): return {'arm.L': (0, 0, -up), 'arm.R': (0, 0, up)}
def cyc(n, f): return [(round(i * n / 4), f(i)) for i in range(5)]
action('idle', cyc(48, lambda i: dict(rot={'head': (0, 0, [0, 3, 0, -3, 0][i]), **arms([0, 4, 0, 4, 0][i]), **tails([0, 8, 0, -8, 0][i])},
                                      loc={'body': (0, [0, -.012, 0, -.012, 0][i], 0)})))
def walk(i, a=30, b=30, bob=.025, lean=0, tl=10):
    s = [1, 0, -1, 0, 1][i]
    return dict(rot={'leg.L': (a * s, 0, 0), 'leg.R': (-a * s, 0, 0), 'arm.L': (-b * s, 0, 0), 'arm.R': (b * s, 0, 0),
                     'body': (lean, 5 * s, 0), 'head': (-lean * .6, -3 * s, 0), **tails(tl * s, -lean * .5)},
                loc={'body': (0, [0, 1, 0, 1, 0][i] * bob, 0)})
action('walk', cyc(24, lambda i: walk(i)))
action('run', cyc(16, lambda i: walk(i, 45, 55, .05, 12, 16)))
action('jump', [
    (0, dict(rot={'leg.L': (-30, 0, 0), 'leg.R': (-30, 0, 0), 'body': (12, 0, 0), **tails(0, 10)}, loc={'body': (0, -.05, 0)})),
    (4, dict(rot={'leg.L': (12, 0, 0), 'leg.R': (12, 0, 0), **arms(110), 'body': (-6, 0, 0), **tails(0, -14)})),
    (12, dict(rot={'leg.L': (-45, 0, 0), 'leg.R': (-45, 0, 0), **arms(75), 'body': (5, 0, 0), **tails(8, -6)})),
])
action('fall', [(0, dict(rot={'leg.L': (20, 0, 0), 'leg.R': (-10, 0, 0), **arms(130), **tails(-6, 14)})),
                (8, dict(rot={'leg.L': (-10, 0, 0), 'leg.R': (20, 0, 0), **arms(120), **tails(6, 14)})),
                (16, dict(rot={'leg.L': (20, 0, 0), 'leg.R': (-10, 0, 0), **arms(130), **tails(-6, 14)}))])
# 攻撃1：ためて、＋x がわの手でねこパンチ（その肩を前に出すように体をひねる）
action('attack', [
    (0, dict(rot={})),
    (4, dict(rot={'arm.L': (40, 0, 0), 'body': (0, 18, 0), 'leg.R': (-10, 0, 0), **tails(-10)})),
    (8, dict(rot={'arm.L': (-100, 0, 0), 'body': (8, -22, 0), 'leg.R': (-22, 0, 0), 'leg.L': (18, 0, 0), **tails(14)}, loc={'body': (0, 0, -.02)})),
    (14, dict(rot={'arm.L': (-70, 0, 0), 'body': (4, -12, 0), **tails(8)})),
    (20, dict(rot={})),
])
# 攻撃2：しっぽ回転（その場でくるっと1回転）
action('attack2', [
    (0, dict(rot={})),
    (3, dict(rot={'body': (8, 0, 0), **tails(-12, 8)}, loc={'body': (0, -.03, 0)})),
    (8, dict(rot={'body': (0, 180, 0), **arms(80), **tails(18, -10)}, loc={'body': (0, .04, 0)})),
    (13, dict(rot={'body': (0, 360, 0), **arms(80), **tails(18, -10)})),
    (20, dict(rot={})),
])
rig.animation_data.action = bpy.data.actions['idle']

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_animation_mode='ACTIONS', export_force_sampling=True,
                          export_apply=True, export_yup=True, export_skins=True, export_def_bones=False)
bpy.ops.wm.save_as_mainfile(filepath=out.replace('.glb', '.blend'))
print('wrote', out)
