# models/hq.glb（本部）の形から、家具や壁の当たり判定（箱）を作って models/hq.col.json に書く。
#   各階の「床から 0.36m〜1.6m の高さ」に形があるところを 0.2m のマスでぬりつぶし、となりあうマスを箱にまとめる。
#   使い方：python tools/hq_colliders.py   （numpy だけ使う。本部を作り直したら これも実行する）
import json, struct, os, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FH = 4.6; CELL = .2; X0, X1, Z0, Z1 = -.6, 22.6, -12.6, .6
LEVELS = {'F1': 0.0, 'F2': FH, 'RF': FH * 2}
b = open(os.path.join(ROOT, 'models', 'hq.glb'), 'rb').read()
n = struct.unpack('<I', b[12:16])[0]; J = json.loads(b[20:20 + n]); off = 20 + n; bl = struct.unpack('<I', b[off:off + 4])[0]; BIN = b[off + 8:off + 8 + bl]
def acc(i):
    a = J['accessors'][i]; v = J['bufferViews'][a['bufferView']]; o = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}[a['componentType']]; k = {'SCALAR': 1, 'VEC3': 3, 'VEC2': 2, 'VEC4': 4}[a['type']]
    st = v.get('byteStride'); cnt = a['count']
    if st and st != np.dtype(dt).itemsize * k:
        raw = np.frombuffer(BIN, np.uint8, cnt * st, o).reshape(cnt, st)[:, :np.dtype(dt).itemsize * k].copy(); return raw.view(dt).reshape(cnt, k)
    return np.frombuffer(BIN, dt, cnt * k, o).reshape(cnt, k) if k > 1 else np.frombuffer(BIN, dt, cnt, o)
out = []
nx, nz = int((X1 - X0) / CELL), int((Z1 - Z0) / CELL)
for top in J['scenes'][0]['nodes']:
    nd = J['nodes'][top]
    if nd['name'] not in LEVELS: continue
    y0 = LEVELS[nd['name']]; grid = np.zeros((nz, nx), bool)
    for c in nd.get('children', []):
        m = J['meshes'][J['nodes'][c]['mesh']]
        for p in m['primitives']:
            P = acc(p['attributes']['POSITION']).astype(np.float64); I = acc(p['indices']).reshape(-1, 3)
            A, B, C = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
            # 三角形の上に 点を ばらまいて しらべる（大きい三角形ほど たくさん）
            area = np.linalg.norm(np.cross(B - A, C - A), axis=1) / 2
            for t in range(len(A)):
                k = int(min(4000, max(3, area[t] / (CELL * CELL * .25))))
                r = np.random.default_rng(t).random((k, 2)); s = r.sum(1) > 1; r[s] = 1 - r[s]
                pts = A[t] + r[:, :1] * (B[t] - A[t]) + r[:, 1:] * (C[t] - A[t])
                pts = np.vstack([pts, A[t], B[t], C[t]])
                ok = (pts[:, 1] > y0 + .36) & (pts[:, 1] < y0 + 1.6)
                q = pts[ok]
                if not len(q): continue
                ix = ((q[:, 0] - X0) / CELL).astype(int); iz = ((q[:, 2] - Z0) / CELL).astype(int)
                v = (ix >= 0) & (ix < nx) & (iz >= 0) & (iz < nz); grid[iz[v], ix[v]] = True
    # 横に つながるマスを まとめ、同じ はばのものを 縦に まとめる
    runs = {}
    for j in range(nz):
        i = 0
        while i < nx:
            if grid[j, i]:
                k = i
                while k < nx and grid[j, k]: k += 1
                runs.setdefault((i, k), []).append(j); i = k
            else: i += 1
    for (i, k), js in runs.items():
        js.sort(); s = js[0]; prev = s
        for jj in js[1:] + [None]:
            if jj is not None and jj == prev + 1: prev = jj; continue
            out.append([round(X0 + i * CELL, 2), round(X0 + k * CELL, 2), round(y0 + .36, 2), round(y0 + 1.6, 2), round(Z0 + s * CELL, 2), round(Z0 + (prev + 1) * CELL, 2)])
            if jj is not None: s = prev = jj
    np.save('/tmp/hqgrid_%s.npy' % nd['name'], grid) if os.environ.get('HQDEBUG') else None
json.dump({'box': out, 'note': 'x0, x1, y0, y1, z0, z1（hq.glb から tools/hq_colliders.py で作った）'}, open(os.path.join(ROOT, 'models', 'hq.col.json'), 'w'), separators=(',', ':'))
print(len(out), 'boxes')
