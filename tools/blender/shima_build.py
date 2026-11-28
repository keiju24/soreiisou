# 新キャラ「シマさん」：もらった動かないモデル（models/src/shima_static.glb：色なし・30万頂点のひとかたまり）に骨を入れて、
# debug-kuroneko.html と同じ名前のアニメ 7 つ（idle walk run jump fall attack attack2）をつけた glb を書き出す。
#   使い方：python tools/blender/shima_build.py models/shima.glb   （pip の bpy でも、Blender の Python でもよい）
# ・形はもらったモデルのまま。ブラウザで軽く動くように、頂点を 約2割 に減らす（見た目はほぼ同じ）
# ・大きさは インポニャンとそろえて 1.05 倍（背の高さ 約 1.8）。前は −Y
# ・手は胸の前で風呂敷の結び目をにぎった形で体とつながっているので、腕の骨はなし（腕は体といっしょに動く）
# ・ひとかたまりのメッシュなので、場所で骨をきめる（さかいめは なめらかにまぜる）
#     頭：z .82 → .92 で 体 → 頭　　足：z .26 → .16 で 体 → 足（左右は x、またの真ん中は 体 のまま）
#     しっぽ：背中がわ（y > .14）の低いところ（z .24 → .19 で 体 → しっぽ）
import bpy, sys, os, math
from mathutils import Vector, Matrix
D = math.radians
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
out = sys.argv[-1] if sys.argv[-1].endswith('.glb') else os.path.join(ROOT, 'models', 'shima.glb')
S = 1.05
DECIMATE = .2

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, 'models', 'src', 'shima_static.glb'))
mesh = [o for o in bpy.data.objects if o.type == 'MESH'][0]
for o in list(bpy.data.objects):
    if o is not mesh: bpy.data.objects.remove(o)
mesh.data.transform(mesh.matrix_world); mesh.matrix_world.identity(); mesh.data.transform(Matrix.Scale(S, 4))
mesh.name = 'shima'
# 頂点をへらす
bpy.context.view_layer.objects.active = mesh; mesh.select_set(True)
dm = mesh.modifiers.new('dec', 'DECIMATE'); dm.ratio = DECIMATE
bpy.ops.object.modifier_apply(modifier='dec')
for p in mesh.data.polygons: p.use_smooth = True
# 色：もらったモデルは色なし（灰色）。てかりだけおさえる
for m in mesh.data.materials:
    if m and m.node_tree:
        b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if b: b.inputs['Roughness'].default_value = .8; b.inputs['Metallic'].default_value = 0

# ---- 骨 ----
P = lambda x, y, z: Vector((x * S, y * S, z * S))
arm = bpy.data.armatures.new('shima_rig'); rig = bpy.data.objects.new('rig', arm); bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT')
def bone(n, h, t, parent=None):
    b = arm.edit_bones.new(n); b.head = h; b.tail = t; b.roll = 0
    if parent: b.parent = arm.edit_bones[parent]
bone('body', P(0, 0, .24), P(0, 0, .86))
bone('head', P(0, 0, .86), P(0, 0, 1.6), 'body')
for s, side in ((1, 'L'), (-1, 'R')):
    bone('leg.' + side, P(s * .2, 0, .25), P(s * .26, -.02, .02), 'body')
bone('tail', P(0, .16, .22), P(0, .36, .14), 'body')
bpy.ops.object.mode_set(mode='OBJECT')

# ---- 場所で骨をきめる ----
sm = lambda t: (lambda c: c * c * (3 - 2 * c))(min(1, max(0, t)))
G = {n: mesh.vertex_groups.new(name=n) for n in ('body', 'head', 'leg.L', 'leg.R', 'tail')}
for v in mesh.data.vertices:
    x, y, z = (c / S for c in v.co)
    w = {}
    h = sm((z - .82) / .10)                                   # 頭
    leg = sm((.26 - z) / .10) * sm((abs(x) - .05) / .06)       # 足（またの真ん中は 体）
    tl = sm((.24 - z) / .05) * sm((y - .14) / .05) * (1 - sm((abs(x) - .1) / .04))   # しっぽ
    leg *= (1 - tl)
    w['head'] = h; w['leg.L' if x >= 0 else 'leg.R'] = leg; w['tail'] = tl
    w['body'] = max(0, 1 - h - leg - tl)
    for n, k in w.items():
        if k > 1e-3: G[n].add([v.index], k, 'REPLACE')
mesh.parent = rig
mesh.modifiers.new('rig', 'ARMATURE').object = rig

# ---- アニメ ----
#  骨の向き：足は X＋で後ろ、X−で前。体（body）は X＋で前にかたむく、Y でひねる、Z で横にかたむく
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
def cyc(n, f): return [(round(i * n / 4), f(i)) for i in range(5)]
action('idle', cyc(48, lambda i: dict(rot={'head': (0, [0, 4, 0, -4, 0][i], [0, 2, 0, -2, 0][i]), 'tail': (0, 0, [0, 12, 0, -12, 0][i])},
                                      loc={'body': (0, [0, -.012, 0, -.012, 0][i], 0)})))
def walk(i, a=26, bob=.025, lean=0, sway=4):
    s = [1, 0, -1, 0, 1][i]
    return dict(rot={'leg.L': (a * s, 0, 0), 'leg.R': (-a * s, 0, 0), 'body': (lean, 6 * s, -sway * s), 'head': (-lean * .6, -4 * s, sway * .6 * s),
                     'tail': (0, 0, 15 * s)},
                loc={'body': (0, [0, 1, 0, 1, 0][i] * bob, 0)})
action('walk', cyc(24, lambda i: walk(i)))                       # ちょこちょこ、左右にゆれて歩く
action('run', cyc(16, lambda i: walk(i, 40, .05, 12, 6)))
action('jump', [
    (0, dict(rot={'leg.L': (-28, 0, 0), 'leg.R': (-28, 0, 0), 'body': (14, 0, 0), 'head': (-8, 0, 0)}, loc={'body': (0, -.05, 0)})),
    (4, dict(rot={'leg.L': (14, 0, 0), 'leg.R': (14, 0, 0), 'body': (-8, 0, 0), 'head': (-6, 0, 0), 'tail': (-20, 0, 0)})),
    (12, dict(rot={'leg.L': (-40, 0, 0), 'leg.R': (-40, 0, 0), 'body': (6, 0, 0)})),
])
action('fall', [(0, dict(rot={'leg.L': (18, 0, 0), 'leg.R': (-10, 0, 0), 'head': (-10, 0, 0), 'tail': (-25, 0, 10)})),
                (8, dict(rot={'leg.L': (-10, 0, 0), 'leg.R': (18, 0, 0), 'head': (-10, 0, 0), 'tail': (-25, 0, -10)})),
                (16, dict(rot={'leg.L': (18, 0, 0), 'leg.R': (-10, 0, 0), 'head': (-10, 0, 0), 'tail': (-25, 0, 10)}))])
# 攻撃1：手がふさがっているので、ずつき（のけぞってためて、前にどーん）
action('attack', [
    (0, dict(rot={})),
    (5, dict(rot={'body': (-14, 0, 0), 'head': (-12, 0, 0), 'leg.L': (-8, 0, 0), 'tail': (0, 0, -15)}, loc={'body': (0, 0, .03)})),
    (9, dict(rot={'body': (26, 0, 0), 'head': (16, 0, 0), 'leg.L': (-24, 0, 0), 'leg.R': (16, 0, 0), 'tail': (-15, 0, 15)}, loc={'body': (0, 0, -.06)})),
    (14, dict(rot={'body': (14, 0, 0), 'head': (8, 0, 0)})),
    (20, dict(rot={})),
])
# 攻撃2：風呂敷ごと くるっと1回転
action('attack2', [
    (0, dict(rot={})),
    (3, dict(rot={'body': (8, 0, 0)}, loc={'body': (0, -.03, 0)})),
    (8, dict(rot={'body': (0, 180, 0), 'tail': (-20, 0, 20)}, loc={'body': (0, .05, 0)})),
    (13, dict(rot={'body': (0, 360, 0), 'tail': (-20, 0, 20)})),
    (20, dict(rot={})),
])
rig.animation_data.action = bpy.data.actions['idle']

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_animation_mode='ACTIONS', export_force_sampling=True,
                          export_apply=True, export_yup=True, export_skins=True, export_def_bones=False)
bpy.ops.wm.save_as_mainfile(filepath=out.replace('.glb', '.blend'))
print('wrote', out)
