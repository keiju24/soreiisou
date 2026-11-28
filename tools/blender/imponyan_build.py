# 新キャラ「インポニャン」：もらった動かないモデル（models/src/imponyan_static.glb）に骨を入れて、
# 戦闘用のアニメ一式（30fps・その場で動く）をつけた glb を書き出す。
#   使い方：python tools/blender/imponyan_build.py models/imponyan.glb   （pip の bpy でも、Blender の Python でもよい）
#
# ・見た目（形・色・頭身）はもらったモデルのまま。大きさだけ 1.3 倍（背の高さ 約 1.8）
# ・骨：hips（腰）→ chest（胴）→ neck（首）→ head（頭）→ ear.L/R（耳）、chest → bell（首元の鈴）
#       chest → shoulder.L/R（肩）→ elbow.L/R（ひじ）→ fist.L/R（こぶし）
#       hips → leg.L/R（もも）→ knee.L/R（ひざ）、hips → tail1/2/3.L・tail1/2/3.R（2本のしっぽ、3本ずつ）
#   .L はキャラの左（モデルの ＋x）、.R はキャラの右（−x）。前は −Y
# ・パーツの名前で骨をきめ、つなぎ（体と足がひとつ）・そで・しっぽは 場所で なめらかに まぜる
#   白い腹巻（z .213〜.336）は 体 にだけつけて、足をふっても裂けないようにする
# ・アニメ（名前）：idle walk run dash / atk1 atk2 atk3 / charge_start charge_loop charge_atk / power / fire_charge fire /
#   dodge_f dodge_b / special / dmg_light dmg_heavy knockback down getup dead / 前からの jump fall attack attack2
#   どれも その場で動く（前に進む・とぶ量は ゲームのほうで つける）
import bpy, sys, os, math
from mathutils import Vector, Matrix
D = math.radians
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
out = sys.argv[-1] if sys.argv[-1].endswith('.glb') else os.path.join(ROOT, 'models', 'imponyan.glb')
S = 1.3
FPS = 30

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene; scn.render.fps = FPS
bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, 'models', 'src', 'imponyan_static.glb'))
meshes = [o for o in bpy.data.objects if o.type == 'MESH']
for o in bpy.data.objects:
    if o.type != 'MESH': bpy.data.objects.remove(o)
for o in meshes:
    o.data.transform(o.matrix_world); o.matrix_world.identity(); o.data.transform(Matrix.Scale(S, 4))

# ---- 骨（もとのモデルの大きさで書いて S 倍）----
P = lambda x, y, z: Vector((x * S, y * S, z * S))
TAIL = [(.02, .152, .166), (.18, .237, .163), (.34, .268, .212), (.45, .305, .40)]      # しっぽの中心の線（左）
SH, EL, WR, FT = (.11, 0, .535), (.19, -.008, .44), (.262, -.012, .352), (.29, -.016, .30)
arm = bpy.data.armatures.new('imponyan_rig'); rig = bpy.data.objects.new('rig', arm); scn.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT')
def bone(n, h, t, parent=None, conn=False):
    b = arm.edit_bones.new(n); b.head = P(*h); b.tail = P(*t); b.roll = 0
    if parent: b.parent = arm.edit_bones[parent]; b.use_connect = conn
bone('hips', (0, 0, .2), (0, 0, .34))
bone('chest', (0, 0, .34), (0, 0, .55), 'hips', True)
bone('neck', (0, 0, .55), (0, 0, .62), 'chest', True)
bone('head', (0, 0, .62), (0, 0, 1.2), 'neck', True)
bone('bell', (0, -.135, .535), (0, -.15, .465), 'chest')
for s, sd in ((1, 'L'), (-1, 'R')):
    m = lambda p: (s * p[0], p[1], p[2])
    bone('ear.' + sd, m((.2, 0, 1.04)), m((.31, .005, 1.37)), 'head')
    bone('shoulder.' + sd, m(SH), m(EL), 'chest'); bone('elbow.' + sd, m(EL), m(WR), 'shoulder.' + sd, True); bone('fist.' + sd, m(WR), m(FT), 'elbow.' + sd, True)
    bone('leg.' + sd, m((.1, 0, .2)), m((.11, 0, .1)), 'hips'); bone('knee.' + sd, m((.11, 0, .1)), m((.12, -.01, .0)), 'leg.' + sd, True)
    for k in range(3): bone(f'tail{k + 1}.' + sd, m(TAIL[k]), m(TAIL[k + 1]), 'hips' if k == 0 else f'tail{k}.' + sd, k > 0)
bpy.ops.object.mode_set(mode='OBJECT')

# ---- 重み ----
sm = lambda t: (lambda c: c * c * (3 - 2 * c))(min(1, max(0, t)))
def seg_param(p, a, b):
    ab = b - a; t = max(0, min(1, (p - a).dot(ab) / ab.length_squared)); return t, (a + ab * t - p).length
def owner(name):
    n = name.lower(); sd = 'L' if n.startswith('left') else 'R' if n.startswith('right') else None
    if 'ear' in n: return 'ear.' + sd
    if any(k in n for k in ('bob', 'face', 'smile')): return 'head'
    if 'bell' in n: return 'bell'
    if 'bib' in n: return 'chest'
    if sd and 'mitten' in n: return 'fist.' + sd
    if sd and 'sleeve' in n: return 'SLEEVE.' + sd
    if sd and 'tail' in n: return 'TAIL.' + sd
    if sd and any(k in n for k in ('flame', 'spiral')): return 'tail3.' + sd
    if sd and 'toe' in n: return 'knee.' + sd
    if 'romper' in n: return 'ROMPER'
    return 'chest'
for o in meshes:
    who = owner(o.name); G = {}
    def g(n):
        if n not in G: G[n] = o.vertex_groups.new(name=n)
        return G[n]
    for v in o.data.vertices:
        x, y, z = (c / S for c in v.co); w = {}
        if who == 'ROMPER':
            k = sm((.20 - z) / .09)                          # 足（腹巻より下）
            side = sm((x + .035) / .07)
            kn = sm((.115 - z) / .06)                        # ひざから下
            ch = sm((z - .33) / .1) * (1 - k)                # 胴
            w['chest'] = ch; w['hips'] = (1 - k) - ch
            for sd, f in (('L', side), ('R', 1 - side)):
                w['leg.' + sd] = k * f * (1 - kn); w['knee.' + sd] = k * f * kn
        elif who.startswith('SLEEVE'):
            sd = who[-1]; s = 1 if sd == 'L' else -1
            a, b = Vector((s * SH[0], SH[1], SH[2])), Vector((s * WR[0], WR[1], WR[2]))
            t, _ = seg_param(Vector((x, y, z)), a, b); e = sm((t - .4) / .25)
            w['shoulder.' + sd] = 1 - e; w['elbow.' + sd] = e
        elif who.startswith('TAIL'):
            sd = who[-1]; s = 1 if sd == 'L' else -1; p = Vector((x, y, z))
            pts = [Vector((s * q[0], q[1], q[2])) for q in TAIL]
            best = min(range(3), key=lambda i: seg_param(p, pts[i], pts[i + 1])[1]); t, _ = seg_param(p, pts[best], pts[best + 1])
            w[f'tail{best + 1}.' + sd] = 1.0
            if best > 0 and t < .2: f = .5 * (1 - t / .2); w[f'tail{best + 1}.' + sd] = 1 - f; w[f'tail{best}.' + sd] = f
            if best < 2 and t > .8: f = .5 * (t - .8) / .2; w[f'tail{best + 1}.' + sd] = w.get(f'tail{best + 1}.' + sd, 1) - f; w[f'tail{best + 2}.' + sd] = f
        else: w[who] = 1.0
        for n, val in w.items():
            if val > 1e-3: g(n).add([v.index], val, 'REPLACE')
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]; bpy.ops.object.join()
mesh = bpy.context.active_object; mesh.name = 'imponyan'; mesh.parent = rig
mesh.modifiers.new('rig', 'ARMATURE').object = rig

# =====================================================================
#  アニメ
#  骨の向き：hips・chest・neck・head は X＋で前にかたむく、Y＋で 左（＋x）の肩がうしろへ（＝右の肩が前へ）、Z＋で 右へかたむく
#  肩・ひじ：X−で前へ（ひじは前に曲がる）、X＋でうしろ。肩を横に上げる：L は Z−、R は Z＋
#  もも：X−で前、X＋でうしろ。ひざ：X＋で うしろに曲がる。耳：X＋でうしろへたおれる
#  hips の位置：(横, 上, 前)。どれも その場で（前に進む量はゲームで）
# =====================================================================
PB = rig.pose.bones
for p in PB: p.rotation_mode = 'XYZ'
def pose(frame, rot=None, loc=None):
    for p in PB: p.rotation_euler = (0, 0, 0); p.location = (0, 0, 0)
    for n, r in (rot or {}).items(): PB[n].rotation_euler = tuple(D(v) for v in r)
    for n, l in (loc or {}).items(): PB[n].location = tuple(v * S for v in l)
    for p in PB: p.keyframe_insert('rotation_euler', frame=frame); p.keyframe_insert('location', frame=frame)
def action(name, keys, interp='BEZIER'):
    rig.animation_data_create(); act = bpy.data.actions.new(name); rig.animation_data.action = act
    for f, r, l in keys: pose(f, r, l)
    act.use_fake_user = True
def mir(d):   # 左右をいれかえる
    o = {}
    for n, (x, y, z) in d.items():
        if n.endswith('.L'): n2 = n[:-2] + '.R'
        elif n.endswith('.R'): n2 = n[:-2] + '.L'
        else: n2 = n
        side = n.endswith(('.L', '.R'))
        o[n2] = (x, -y if not side else -y, -z)
    return o
def add(*ds):
    o = {}
    for d in ds:
        for n, v in d.items(): o[n] = tuple(a + b for a, b in zip(o.get(n, (0, 0, 0)), v))
    return o
def tails(sw=0, up=0, lag=0):     # しっぽ：sw 横ゆれ・up 上げる（3本の骨で だんだん大きく）
    o = {}
    for k in range(3):
        a = (k + 1) / 2
        o[f'tail{k + 1}.L'] = (up * a * .6, 0, sw * a); o[f'tail{k + 1}.R'] = (up * a * .6, 0, sw * a)
    return o
def ears(back=0, flop=0): return {'ear.L': (back, 0, -flop), 'ear.R': (back, 0, flop)}
def arms_out(a): return {'shoulder.L': (0, 0, -a), 'shoulder.R': (0, 0, a)}
GUARD = add(arms_out(12), {'elbow.L': (-18, 0, 0), 'elbow.R': (-18, 0, 0), 'leg.L': (0, 0, -3), 'leg.R': (0, 0, 3)})
def K(f, r=None, l=None): return (f, r or {}, l or {})

# ---- 待機（2秒・60f）：呼吸・重心の左右・耳ぴくっ・しっぽゆらゆら ----
action('idle', [
    K(0, add(GUARD, tails(10)), {'hips': (0, 0, 0)}),
    K(15, add(GUARD, {'chest': (2, 0, -2), 'hips': (0, 0, -2), 'head': (-2, 0, 2)}, tails(0, 6)), {'hips': (-.006, -.008, 0)}),
    K(30, add(GUARD, tails(-10)), {'hips': (0, 0, 0)}),
    K(40, add(GUARD, {'chest': (2, 0, 2), 'hips': (0, 0, 2)}, ears(14, 6), tails(0, 6)), {'hips': (.006, -.008, 0)}),
    K(44, add(GUARD, {'chest': (2, 0, 2), 'hips': (0, 0, 2)}, ears(0), tails(-4, 6)), {'hips': (.006, -.006, 0)}),
    K(60, add(GUARD, tails(10)), {'hips': (0, 0, 0)}),
])
# ---- 歩く（0.6秒・18f）：短い足で ちょこちょこ ----
def walk(f, a, arm, bob, lean=0, knee=35, elb=-25, tw=6, tl=10, n=18):
    s = [1, 0, -1, 0, 1]
    ks = []
    for i in range(5):
        c = s[i]; fr = round(i * n / 4)
        lift = [0, 1, 0, 1, 0][i]
        r = {'leg.L': (-a * c, 0, -2), 'leg.R': (a * c, 0, 2), 'shoulder.L': (arm * c, 0, -10), 'shoulder.R': (-arm * c, 0, 10),
             'elbow.L': (elb, 0, 0), 'elbow.R': (elb, 0, 0), 'chest': (lean, tw * c, 0), 'hips': (lean * .4, -tw * .5 * c, 0), 'head': (-lean * .5, -tw * .5 * c, 0)}
        if lift:   # 足を前へもどしている ほうの ひざを曲げる
            r['knee.R' if i == 1 else 'knee.L'] = (knee, 0, 0)
        r.update(tails(tl * [0, -1, 0, 1, 0][i], lean * .8))
        r.update(ears(lean * .8 + 4 * lift))
        ks.append(K(fr, r, {'hips': (0, bob * lift, 0)}))
    return ks
action('walk', walk(0, 26, 28, .022))
action('run', walk(0, 44, 55, .05, lean=14, knee=70, elb=-70, tw=10, tl=16, n=15))        # 0.5秒
action('dash', walk(0, 55, 40, .045, lean=26, knee=85, elb=-85, tw=8, tl=8, n=12))         # 0.4秒
# ---- 三段こうげき ----
GUARD_L = {'shoulder.L': (-40, 0, -8), 'elbow.L': (-95, 0, 0)}         # 左手はあごの前でかまえる
GUARD_R = {'shoulder.R': (-40, 0, 8), 'elbow.R': (-95, 0, 0)}
def punchR(tw=26, lean=8, ext=-88):
    tw *= .4   # 短い腕なので ひねりは小さく（こぶしが まっすぐ前へ出るように）
    # 肩の骨は 外下を向いているので、前へまっすぐ出すには「前 −60°＋外 56°」（しらべた値。ext が大きいほど 少し高く）
    return {'shoulder.R': (-62 + (ext + 88) * .5, 0, 54), 'elbow.R': (-6, 0, 0), 'fist.R': (0, 0, 0), 'chest': (lean, tw, 0), 'hips': (2, tw * .4, 0), 'head': (-4, -tw * .5, 0)}
action('atk1', [
    K(0, add(GUARD, tails(0))),
    K(3, add(GUARD_L, {'shoulder.R': (35, 0, 10), 'elbow.R': (-105, 0, 0), 'chest': (-2, -16, 0), 'hips': (0, -6, 0), 'leg.L': (-8, 0, -3)}, tails(-10))),
    K(6, add(GUARD_L, punchR(), {'leg.L': (-18, 0, -3), 'leg.R': (14, 0, 3)}, tails(14))),
    K(10, add(GUARD_L, punchR(24, 6, -84), {'leg.L': (-16, 0, -3), 'leg.R': (12, 0, 3)}, tails(10))),
    K(18, add(GUARD, tails(0))),
])
def punchL(tw=-26, lean=8, ext=-88):
    tw *= .4
    return {'shoulder.L': (-62 + (ext + 88) * .5, 0, -54), 'elbow.L': (-6, 0, 0), 'chest': (lean, tw, 0), 'hips': (2, tw * .4, 0), 'head': (-4, -tw * .5, 0)}
action('atk2', [
    K(0, add(GUARD_L, punchR(18, 4, -60), tails(8))),
    K(3, add(GUARD_R, {'shoulder.L': (30, 0, -10), 'elbow.L': (-105, 0, 0), 'chest': (-2, 18, 0), 'hips': (0, 6, 0), 'leg.R': (-8, 0, 3)}, tails(10))),
    K(6, add(GUARD_R, punchL(-30, 9, -92), {'leg.R': (-18, 0, 3), 'leg.L': (14, 0, -3)}, tails(-16))),
    K(10, add(GUARD_R, punchL(-27, 7, -86), {'leg.R': (-16, 0, 3), 'leg.L': (12, 0, -3)}, tails(-11))),
    K(18, add(GUARD, tails(0))),
])
action('atk3', [
    K(0, add(GUARD_R, punchL(-20, 4, -60), tails(-6))),
    K(9, add(GUARD_L, {'shoulder.R': (55, 0, 14), 'elbow.R': (-120, 0, 0), 'chest': (-10, -34, 0), 'hips': (-6, -14, 0), 'head': (6, 14, 0),
                       'leg.L': (-10, 0, -6), 'knee.L': (20, 0, 0), 'leg.R': (12, 0, 6), 'knee.R': (25, 0, 0)}, ears(18), tails(-18, 8)), {'hips': (0, -.03, -.03)}),
    K(12, add(GUARD_L, punchR(30, 14, -80), {'leg.L': (-34, 0, -4), 'leg.R': (30, 0, 4), 'knee.R': (10, 0, 0)}, tails(10, -6))),
    K(14, add(GUARD_L, punchR(44, 18, -96), {'leg.L': (-38, 0, -4), 'leg.R': (34, 0, 4), 'knee.R': (12, 0, 0)}, ears(-6), tails(22, -10)), {'hips': (0, -.02, .03)}),
    K(20, add(GUARD_L, punchR(42, 16, -94), {'leg.L': (-36, 0, -4), 'leg.R': (32, 0, 4)}, tails(18, -6)), {'hips': (0, -.02, .03)}),
    K(30, add(GUARD, tails(0))),
])
# ---- チャージこうげき ----
CH = add(GUARD_L, {'shoulder.R': (58, 0, 16), 'elbow.R': (-125, 0, 0), 'chest': (10, -22, 0), 'hips': (4, -8, 0), 'head': (-6, 10, 0),
                   'leg.L': (-22, 0, -10), 'knee.L': (34, 0, 0), 'leg.R': (14, 0, 10), 'knee.R': (30, 0, 0)}, ears(10))
action('charge_start', [K(0, add(GUARD, tails(0))), K(9, add(CH, tails(-8, 6)), {'hips': (0, -.045, 0)})])
action('charge_loop', [K(0, add(CH, tails(-8, 6)), {'hips': (0, -.045, 0)}), K(4, add(CH, {'chest': (1, 1, 1)}, tails(-6, 8)), {'hips': (.004, -.048, 0)}),
                       K(8, add(CH, {'chest': (-1, -1, -1)}, tails(-10, 4)), {'hips': (-.004, -.044, 0)}), K(15, add(CH, tails(-8, 6)), {'hips': (0, -.045, 0)})])
action('charge_atk', [
    K(0, add(CH, tails(-8, 6)), {'hips': (0, -.045, 0)}),
    K(3, add(GUARD_L, punchR(40, 16, -96), {'leg.L': (-36, 0, -6), 'leg.R': (32, 0, 6), 'knee.R': (10, 0, 0)}, ears(-6), tails(22, -8)), {'hips': (0, -.02, .02)}),
    K(9, add(GUARD_L, punchR(38, 15, -94), {'leg.L': (-34, 0, -6), 'leg.R': (30, 0, 6)}, tails(16, -6)), {'hips': (0, -.02, .02)}),
    K(24, add(GUARD, tails(0))),
])
# ---- 気合いの一発（1.2秒・36f。0.5秒で当たる）----
action('power', [
    K(0, add(GUARD, tails(0))),
    K(11, add(GUARD_L, {'shoulder.R': (70, 0, 42), 'elbow.R': (-80, 0, 0), 'chest': (-12, -42, 4), 'hips': (-6, -16, 0), 'head': (8, 18, 0),
                        'leg.L': (-14, 0, -10), 'leg.R': (18, 0, 10), 'knee.R': (22, 0, 0)}, ears(20), tails(-20, 10)), {'hips': (0, -.03, -.04)}),
    K(15, add(GUARD_L, punchR(48, 20, -100), {'leg.L': (-42, 0, -6), 'leg.R': (36, 0, 6), 'knee.R': (14, 0, 0)}, ears(-8), tails(24, -10)), {'hips': (0, -.03, .04)}),
    K(24, add(GUARD_L, punchR(44, 18, -96), {'leg.L': (-40, 0, -6), 'leg.R': (34, 0, 6)}, tails(18, -6)), {'hips': (0, -.03, .04)}),
    K(36, add(GUARD, tails(0))),
])
# ---- 火花の術 ----
FC = {'shoulder.L': (-58, 0, 16), 'shoulder.R': (-58, 0, -16), 'elbow.L': (-62, 0, 0), 'elbow.R': (-62, 0, 0), 'chest': (6, 0, 0), 'leg.L': (-10, 0, -6), 'leg.R': (10, 0, 6), 'knee.R': (12, 0, 0)}
action('fire_charge', [K(0, add(FC, tails(0, 6))), K(7, add(FC, {'chest': (8, 0, 0)}, tails(4, 8)), {'hips': (0, -.01, 0)}), K(15, add(FC, tails(0, 6)))])
action('fire', [
    K(0, add(FC, tails(0, 6))),
    K(3, add(FC, {'chest': (-4, 0, 0), 'shoulder.L': (-40, 0, 16), 'shoulder.R': (-40, 0, -16)}, tails(0, 10))),
    K(6, {'shoulder.L': (-88, 0, 10), 'shoulder.R': (-88, 0, -10), 'elbow.L': (-4, 0, 0), 'elbow.R': (-4, 0, 0), 'chest': (12, 0, 0), 'head': (-6, 0, 0),
          'leg.L': (-22, 0, -6), 'leg.R': (18, 0, 6), **ears(-6), **tails(0, -8)}),
    K(10, {'shoulder.L': (-84, 0, 10), 'shoulder.R': (-84, 0, -10), 'elbow.L': (-6, 0, 0), 'elbow.R': (-6, 0, 0), 'chest': (10, 0, 0), 'leg.L': (-20, 0, -6), 'leg.R': (16, 0, 6), **tails(0, -6)}),
    K(21, add(GUARD, tails(0))),
])
# ---- 回避（0.5秒・15f）：前へ／うしろへ ----
action('dodge_f', [
    K(0, add(GUARD, tails(0))),
    K(2, add(GUARD, {'leg.L': (-20, 0, -4), 'knee.L': (40, 0, 0), 'leg.R': (-20, 0, 4), 'knee.R': (40, 0, 0), 'chest': (16, 0, 0)}, tails(0, 6)), {'hips': (0, -.05, 0)}),
    K(5, {'chest': (24, 0, 0), 'hips': (10, 0, 0), 'head': (-14, 0, 0), 'shoulder.L': (48, 0, -18), 'shoulder.R': (48, 0, 18), 'elbow.L': (-30, 0, 0), 'elbow.R': (-30, 0, 0),
          'leg.L': (-46, 0, -4), 'knee.L': (70, 0, 0), 'leg.R': (-30, 0, 4), 'knee.R': (60, 0, 0), **ears(34), **tails(0, -16)}, {'hips': (0, .06, 0)}),
    K(10, add(GUARD, {'chest': (14, 0, 0), 'leg.L': (-16, 0, -4), 'knee.L': (30, 0, 0), 'leg.R': (-16, 0, 4), 'knee.R': (30, 0, 0)}, ears(12), tails(0, -8)), {'hips': (0, -.04, 0)}),
    K(15, add(GUARD, tails(0))),
])
action('dodge_b', [
    K(0, add(GUARD, tails(0))),
    K(2, add(GUARD, {'leg.L': (-16, 0, -4), 'knee.L': (34, 0, 0), 'leg.R': (-16, 0, 4), 'knee.R': (34, 0, 0), 'chest': (8, 0, 0)}), {'hips': (0, -.05, 0)}),
    K(5, {'chest': (-16, 0, 0), 'hips': (-8, 0, 0), 'head': (10, 0, 0), 'shoulder.L': (-50, 0, -20), 'shoulder.R': (-50, 0, 20), 'elbow.L': (-40, 0, 0), 'elbow.R': (-40, 0, 0),
          'leg.L': (-40, 0, -4), 'knee.L': (30, 0, 0), 'leg.R': (-34, 0, 4), 'knee.R': (26, 0, 0), **ears(-20), **tails(0, 18)}, {'hips': (0, .06, 0)}),
    K(10, add(GUARD, {'chest': (8, 0, 0), 'leg.L': (-12, 0, -4), 'knee.L': (28, 0, 0), 'leg.R': (-12, 0, 4), 'knee.R': (28, 0, 0)}, tails(0, 6)), {'hips': (0, -.04, 0)}),
    K(15, add(GUARD, tails(0))),
])
# ---- 必殺技（3秒・90f）：かまえ 0.5秒 → 0.6秒から 0.2秒ごとに左右こうたい → 2.4秒に 最後の大きい一発 ----
SP_STANCE = {'shoulder.L': (-62, 0, -6), 'shoulder.R': (-62, 0, 6), 'elbow.L': (-112, 0, 0), 'elbow.R': (-112, 0, 0), 'chest': (12, 0, 0), 'hips': (5, 0, 0),
             'leg.L': (-18, 0, -10), 'knee.L': (22, 0, 0), 'leg.R': (14, 0, 10), 'knee.R': (22, 0, 0)}
keys = [K(0, add(GUARD, tails(0))), K(15, add(SP_STANCE, ears(10), tails(0, 10)), {'hips': (0, -.035, 0)})]
for i, f in enumerate(range(18, 72, 6)):              # 9発（左右こうたい）
    right = i % 2 == 0
    ext = {'shoulder.R' if right else 'shoulder.L': (-64, 0, 54 if right else -54), 'elbow.R' if right else 'elbow.L': (-8, 0, 0)}
    ret = {'shoulder.L' if right else 'shoulder.R': (-50, 0, -6 if right else 6), 'elbow.L' if right else 'elbow.R': (-125, 0, 0)}
    tw = 8 if right else -8
    keys.append(K(f - 3, add(SP_STANCE, {'chest': (0, -tw * .3, 0)}, tails(-tw * .3, 8)), {'hips': (0, -.035, 0)}))
    keys.append(K(f, add({**SP_STANCE, **ext, **ret}, {'chest': (2, tw, 0), 'hips': (0, tw * .35, 0), 'head': (0, -tw * .4, 0)}, tails(tw * .6, 6)), {'hips': ((.012 if right else -.012), -.035, .01)}))
keys += [K(69, add(GUARD_L, {'shoulder.R': (55, 0, 20), 'elbow.R': (-115, 0, 0), 'chest': (-6, -30, 0), 'hips': (-4, -12, 0)}, ears(18), tails(-18, 10)), {'hips': (0, -.04, -.02)}),
         K(72, add(GUARD_L, punchR(46, 20, -100), {'leg.L': (-40, 0, -6), 'leg.R': (34, 0, 6), 'knee.R': (12, 0, 0)}, ears(-8), tails(24, -10)), {'hips': (0, -.03, .04)}),
         K(80, add(GUARD_L, punchR(44, 18, -96), {'leg.L': (-38, 0, -6), 'leg.R': (32, 0, 6)}, tails(18, -6)), {'hips': (0, -.03, .04)}),
         K(90, add(GUARD, tails(0)))]
action('special', keys)
# ---- やられ ----
action('dmg_light', [K(0, add(GUARD)), K(2, add(GUARD, {'chest': (-12, 0, 0), 'head': (-12, 0, 0), 'hips': (-4, 0, 0)}, arms_out(26), ears(-18), tails(0, 14))), K(8, add(GUARD))])
action('dmg_heavy', [
    K(0, add(GUARD)),
    K(3, add({'chest': (-24, 8, 0), 'head': (-18, -6, 0), 'hips': (-8, 0, 0), 'leg.L': (16, 0, -6), 'leg.R': (-20, 0, 6), 'knee.L': (20, 0, 0)}, arms_out(40), ears(-26, 10), tails(0, 20)), {'hips': (0, -.02, -.04)}),
    K(9, add({'chest': (-10, -6, 4), 'head': (-6, 6, 0), 'leg.L': (10, 0, -6), 'leg.R': (-12, 0, 6)}, arms_out(22), ears(-10), tails(6, 8)), {'hips': (0, -.02, -.02)}),
    K(18, add(GUARD)),
])
LIE = {'hips': (-80, 0, 0), 'head': (-6, 0, 10), 'leg.L': (-30, 0, -14), 'leg.R': (-24, 0, 14), 'knee.L': (20, 0, 0), 'knee.R': (16, 0, 0), **arms_out(70),
       'elbow.L': (-10, 0, 0), 'elbow.R': (-10, 0, 0), **ears(30, 10), **tails(0, 30)}
LIE_LOC = {'hips': (0, .146, 0)}      # いちばん低い所が ちょうど地面（しらべた値）
action('knockback', [
    K(0, add(GUARD)),
    K(4, add({'hips': (-30, 0, 0), 'chest': (-20, 0, 0), 'head': (-16, 0, 0), 'leg.L': (-30, 0, -8), 'leg.R': (-26, 0, 8)}, arms_out(60), ears(-30, 10), tails(0, 26)), {'hips': (0, .25, 0)}),
    K(12, add({'hips': (-70, 0, 0), 'chest': (-10, 0, 0), 'leg.L': (-50, 0, -10), 'leg.R': (-44, 0, 10), 'knee.L': (30, 0, 0)}, arms_out(80), ears(30, 10), tails(0, 30)), {'hips': (0, .1, 0)}),
    K(18, LIE, {'hips': (0, .17, 0)}), K(21, add(LIE, {'hips': (6, 0, 0)}), {'hips': (0, .16, 0)}), K(24, LIE, LIE_LOC),
])
action('down', [K(0, LIE, LIE_LOC), K(15, add(LIE, {'chest': (2, 0, 0)}), {'hips': (0, .148, 0)}), K(30, LIE, LIE_LOC)])
action('getup', [
    K(0, LIE, LIE_LOC),
    K(8, {'hips': (-40, 0, 0), 'chest': (30, 0, 0), 'head': (10, 0, 0), 'leg.L': (-70, 0, -14), 'leg.R': (-70, 0, 14), 'knee.L': (80, 0, 0), 'knee.R': (80, 0, 0), **arms_out(40), **ears(10)}, {'hips': (0, .02, 0)}),
    K(15, add(GUARD, {'chest': (20, 0, 0), 'leg.L': (-40, 0, -6), 'knee.L': (60, 0, 0), 'leg.R': (-30, 0, 6), 'knee.R': (50, 0, 0)}), {'hips': (0, -.07, 0)}),
    K(21, add(GUARD)),
])
DEAD = {**LIE, **ears(40, 20), **tails(0, 36), 'head': (-4, 0, 22)}
action('dead', [K(0, DEAD, LIE_LOC), K(30, DEAD, LIE_LOC)])
# ---- 前からある名前（ほかのページ用）：jump fall attack attack2 ----
action('jump', [
    K(0, add(GUARD, {'leg.L': (-30, 0, 0), 'knee.L': (40, 0, 0), 'leg.R': (-30, 0, 0), 'knee.R': (40, 0, 0), 'chest': (12, 0, 0)}, tails(0, 10)), {'hips': (0, -.05, 0)}),
    K(4, add({'leg.L': (12, 0, 0), 'leg.R': (12, 0, 0), 'chest': (-6, 0, 0)}, arms_out(110), ears(-10), tails(0, -14))),
    K(12, add({'leg.L': (-45, 0, 0), 'knee.L': (50, 0, 0), 'leg.R': (-45, 0, 0), 'knee.R': (50, 0, 0)}, arms_out(75), tails(8, -6))),
])
action('fall', [K(0, add({'leg.L': (20, 0, 0), 'leg.R': (-10, 0, 0)}, arms_out(130), ears(-14), tails(-6, 14))),
                K(8, add({'leg.L': (-10, 0, 0), 'leg.R': (20, 0, 0)}, arms_out(120), ears(-10), tails(6, 14))),
                K(16, add({'leg.L': (20, 0, 0), 'leg.R': (-10, 0, 0)}, arms_out(130), ears(-14), tails(-6, 14)))])
src = bpy.data.actions['atk1']; c = src.copy(); c.name = 'attack'; c.use_fake_user = True    # ねこパンチ＝三段こうげきの1段目
action('attack2', [
    K(0, add(GUARD)), K(3, add(GUARD, {'chest': (8, 0, 0)}, tails(-12, 8)), {'hips': (0, -.03, 0)}),
    K(8, add({'hips': (0, 180, 0)}, arms_out(80), tails(18, -10)), {'hips': (0, .04, 0)}),
    K(13, add({'hips': (0, 360, 0)}, arms_out(80), tails(18, -10))), K(20, add(GUARD)),
])
rig.animation_data.action = bpy.data.actions['idle']

bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', export_animation_mode='ACTIONS', export_force_sampling=True, export_frame_step=1,
                          export_apply=True, export_yup=True, export_skins=True, export_def_bones=False)
bpy.ops.wm.save_as_mainfile(filepath=out.replace('.glb', '.blend'))
print('wrote', out, sorted(a.name for a in bpy.data.actions))
