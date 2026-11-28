# 「Neko Toon V2」（neko_toon_v2.py：もらったスクリプト）をそのまま組み立てて、
# ゲーム／デバッグページ用に アニメつきの glb を書き出す。
#   使い方：python tools/blender/neko_toon_v2_build.py models/neko_toon_v2.glb   （pip の bpy でも、Blender の Python でもよい）
# やること
#   1. neko_toon_v2.py を実行（いちばん下の「Render setup」＝ライト・カメラ・Freestyle は書き出しに使わないので実行しない）
#   2. トゥーンのマテリアル（Shader to RGB）は glTF に入らないので、まんなかの色のふつうのマテリアルに置きかえる
#   3. 曲線（しっぽ・口・うずまき）をメッシュにし、妖怪ウォッチ風の黒いふち（裏返しの殻）をつける
#   4. debug-kuroneko.html と同じ名前のアニメ 7 つ（idle walk run jump fall attack attack2）をつける
#   5. 大きさを 0.5 倍（背の高さ 約 1.9）にして書き出す
import bpy, sys, os, math
D = math.radians
HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[-1] if sys.argv[-1].endswith('.glb') else os.path.join(HERE, '..', '..', 'models', 'neko_toon_v2.glb')

bpy.ops.wm.read_factory_settings(use_empty=True)
src = open(os.path.join(HERE, 'neko_toon_v2.py'), encoding='utf-8').read().split('# Render setup')[0]
exec(compile(src, 'neko_toon_v2.py', 'exec'), {'__name__': '__main__'})
rig = bpy.data.objects['Neko rig']

# ---- マテリアル：トゥーンの色ランプのまんなかの色を、ふつうの（glTF に入る）マテリアルにする ----
for m in list(bpy.data.materials):
    nt = m.node_tree
    ramp = next((n for n in nt.nodes if n.type == 'VALTORGB'), None) if nt else None
    if not ramp: continue
    els = ramp.color_ramp.elements
    col = tuple(els[1].color if len(els) > 1 else els[0].color)   # ノードを消す前にコピー
    nt.nodes.clear()
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); o = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(b.outputs[0], o.inputs[0])
    b.inputs['Base Color'].default_value = (col[0], col[1], col[2], 1)
    b.inputs['Roughness'].default_value = .85
    b.inputs['Metallic'].default_value = 0

# ---- 曲線 → メッシュ（骨への親子づけはそのまま） ----
for o in [o for o in bpy.data.objects if o.type == 'CURVE']:
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target='MESH')

# ---- 黒いふち（裏返した殻：外へ少しふくらませて、裏面だけ描く）。うすい物・平らな物にはつけない ----
M_OUT = bpy.data.materials.new('outline'); M_OUT.use_backface_culling = True
M_OUT.use_nodes = True
bn = M_OUT.node_tree.nodes.get('Principled BSDF'); bn.inputs['Base Color'].default_value = (0, 0, 0, 1); bn.inputs['Roughness'].default_value = 1
SKIP = ('Hair shine', 'Bell hole', 'Cat mouth', 'Flame spiral', 'Bell groove', 'Ear inset')
for o in bpy.data.objects:
    if o.type != 'MESH' or o.name.startswith(SKIP): continue
    o.data.materials.append(M_OUT)
    s = o.modifiers.new('outline', 'SOLIDIFY'); s.thickness = .022; s.offset = 1; s.use_flip_normals = True; s.use_rim = False
    s.material_offset = len(o.data.materials) - 1

# ---- アニメ ----
#  骨の向き（しらべた結果）：足・腕は X＋で後ろ、X−で前にふる。体（body）は X＋で前にかたむく、Y でひねる。
#  腕を横に上げる：arm.R（＋x がわ）は Z−、arm.L（−x がわ）は Z＋。しっぽは大きい骨なので小さめにゆらす。
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
def tails(sw, up=0): return {'tail.L': (up, 0, sw), 'tail.R': (up, 0, -sw)}
def arms(up): return {'arm.L': (0, 0, up), 'arm.R': (0, 0, -up)}     # 横に上げる
def cyc(n, f): return [(round(i * n / 4), f(i)) for i in range(5)]
action('idle', cyc(48, lambda i: dict(rot={'head': (0, 0, [0, 3, 0, -3, 0][i]), **arms([0, 4, 0, 4, 0][i]), **tails([0, 5, 0, -5, 0][i])},
                                      loc={'body': (0, [0, -.04, 0, -.04, 0][i], 0)})))
def walk(i, a=30, b=30, bob=.07, lean=0, tl=6):
    s = [1, 0, -1, 0, 1][i]
    return dict(rot={'leg.L': (a * s, 0, 0), 'leg.R': (-a * s, 0, 0), 'arm.L': (-b * s, 0, 0), 'arm.R': (b * s, 0, 0),
                     'body': (lean, 5 * s, 0), 'head': (-lean * .6, -3 * s, 0), **tails(tl * s, -lean * .5)},
                loc={'body': (0, [0, 1, 0, 1, 0][i] * bob, 0)})
action('walk', cyc(24, lambda i: walk(i)))
action('run', cyc(16, lambda i: walk(i, 48, 55, .14, 12, 10)))
action('jump', [
    (0, dict(rot={'leg.L': (-30, 0, 0), 'leg.R': (-30, 0, 0), 'body': (12, 0, 0), **tails(0, 8)}, loc={'body': (0, -.16, 0)})),
    (4, dict(rot={'leg.L': (12, 0, 0), 'leg.R': (12, 0, 0), **arms(110), 'body': (-6, 0, 0), **tails(0, -10)})),
    (12, dict(rot={'leg.L': (-45, 0, 0), 'leg.R': (-45, 0, 0), **arms(75), 'body': (5, 0, 0), **tails(6, -4)})),
])
action('fall', [(0, dict(rot={'leg.L': (20, 0, 0), 'leg.R': (-10, 0, 0), **arms(130), **tails(-5, 10)})),
                (8, dict(rot={'leg.L': (-10, 0, 0), 'leg.R': (20, 0, 0), **arms(120), **tails(5, 10)})),
                (16, dict(rot={'leg.L': (20, 0, 0), 'leg.R': (-10, 0, 0), **arms(130), **tails(-5, 10)}))])
# 攻撃1：ためて、右手（＋x がわ）でねこパンチ。右の肩を前に出すように体をひねる（Y−）
action('attack', [
    (0, dict(rot={})),
    (4, dict(rot={'arm.R': (40, 0, 0), 'body': (0, 18, 0), 'leg.L': (-10, 0, 0), **tails(-8)})),
    (8, dict(rot={'arm.R': (-100, 0, 0), 'body': (8, -22, 0), 'leg.L': (-22, 0, 0), 'leg.R': (18, 0, 0), **tails(12)}, loc={'body': (0, 0, -.06)})),
    (14, dict(rot={'arm.R': (-70, 0, 0), 'body': (4, -12, 0), **tails(6)})),
    (20, dict(rot={})),
])
# 攻撃2：しっぽ回転（その場でくるっと1回転）
action('attack2', [
    (0, dict(rot={})),
    (3, dict(rot={'body': (8, 0, 0), **tails(-10, 6)}, loc={'body': (0, -.1, 0)})),
    (8, dict(rot={'body': (0, 180, 0), **arms(80), **tails(14, -8)}, loc={'body': (0, .12, 0)})),
    (13, dict(rot={'body': (0, 360, 0), **arms(80), **tails(14, -8)})),
    (20, dict(rot={})),
])
rig.animation_data.action = bpy.data.actions['idle']

# ---- 大きさをそろえて書き出す ----
rig.scale = (.5, .5, .5)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_animation_mode='ACTIONS', export_force_sampling=True,
                          export_apply=True, export_yup=True, export_skins=True, export_def_bones=False)
bpy.ops.wm.save_as_mainfile(filepath=out.replace('.glb', '.blend'))
print('wrote', out)
