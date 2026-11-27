"""風情ウォッチバスターズ：本部・公園のテクスチャをつくる（numpy + Pillow）
   python tools/textures/make_textures.py  →  textures/<名前>.jpg と <名前>_n.jpg（法線マップ）
   すべて上下左右につないでも継ぎ目が出ない（壁だけは横方向のみ）。色はゲームの元の色に合わせている。"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import os, math
OUT = os.path.join(os.path.dirname(__file__), '..', '..', 'textures')
os.makedirs(OUT, exist_ok=True)

def hexrgb(h): h = h.lstrip('#'); return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255
def fbm(h, w, beta, seed, aniso=(1, 1)):
    """周期的なノイズ（FFT で 1/f^beta のフィルタ）→ 0..1。つなぎ目が出ない"""
    rng = np.random.default_rng(seed)
    F = np.fft.fft2(rng.standard_normal((h, w)))
    fy = np.fft.fftfreq(h)[:, None] * aniso[0]; fx = np.fft.fftfreq(w)[None, :] * aniso[1]
    r = np.sqrt(fx ** 2 + fy ** 2); r[0, 0] = 1
    n = np.real(np.fft.ifft2(F / r ** beta)); n -= n.min(); n /= n.max() + 1e-9
    return n
def tint(base, *mods):
    img = np.ones(base.shape[:2] + (3,)) * base if base.ndim == 1 else base
    return img
def lay(img, mask, col, a=1.0):
    col = hexrgb(col) if isinstance(col, str) else col
    m = np.clip(mask * a, 0, 1)[..., None]
    return img * (1 - m) + col * m
def save(name, img, height=None, strength=2.0, wrapy=True):
    img = np.clip(img, 0, 1)
    Image.fromarray((img * 255).astype(np.uint8)).save(os.path.join(OUT, name + '.jpg'), quality=86, optimize=True)
    if height is not None:
        hgt = height.astype(float)
        pad = 'wrap'
        dx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) * strength
        dy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) * strength
        if not wrapy: dy[0] = dy[-1] = 0
        n = np.dstack([-dx, dy, np.ones_like(hgt)])
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        Image.fromarray(((n * .5 + .5) * 255).astype(np.uint8)).save(os.path.join(OUT, name + '_n.jpg'), quality=90)
    print('made', name, img.shape[1], 'x', img.shape[0])
def wrapdraw(size, draw_fn):
    """つなぎ目をまたいでも切れないように、9枚分の位置に同じ絵を描いて真ん中を使う"""
    W, H = size
    big = Image.new('L', (W * 3, H * 3), 0); d = ImageDraw.Draw(big)
    draw_fn(d, W, H)
    big = big.crop((W, H, W * 2, H * 2))
    return np.asarray(big, float) / 255
def tiled(draw_one, W, H):
    def f(d, W_, H_):
        for oy in (0, H_, 2 * H_):
            for ox in (0, W_, 2 * W_): draw_one(d, ox, oy)
    return wrapdraw((W, H), f)
def cracks(W, H, n, seed, width=1):
    rng = np.random.default_rng(seed); segs = []
    for _ in range(n):
        x, y = rng.uniform(0, W), rng.uniform(0, H); a = rng.uniform(0, 2 * math.pi); pts = [(x, y)]
        for _ in range(rng.integers(8, 22)):
            a += rng.normal(0, .5); L = rng.uniform(6, 18); x += math.cos(a) * L; y += math.sin(a) * L; pts.append((x, y))
        segs.append(pts)
    return tiled(lambda d, ox, oy: [d.line([(p[0] + ox, p[1] + oy) for p in s], fill=255, width=width) for s in segs], W, H)

# ---------------- concrete（1F の床）----------------
def concrete():
    N = 1024; base = hexrgb('#9d9b92')
    big = fbm(N, N, 1.6, 1); mid = fbm(N, N, 1.0, 2); fine = fbm(N, N, .4, 3)
    img = np.ones((N, N, 3)) * base
    img *= (0.9 + big[..., None] * .16) * (0.96 + mid[..., None] * .08) * (0.95 + fine[..., None] * .1)
    stain = np.clip((fbm(N, N, 2.2, 4) - .62) * 4, 0, 1); img = lay(img, stain, '#6f6c62', .35)
    rng = np.random.default_rng(5); sp = np.zeros((N, N)); idx = rng.integers(0, N, (3500, 2)); sp[idx[:, 0], idx[:, 1]] = 1
    sp = np.asarray(Image.fromarray((sp * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)), float) / 255
    img = lay(img, sp * (rng.random((N, N)) > .5), '#5d5b54', .5); img = lay(img, sp * (rng.random((N, N)) > .7), '#cfccc2', .4)
    cr = cracks(N, N, 5, 6); img = lay(img, cr, '#4e4c46', .55)
    joint = np.zeros((N, N)); joint[:3, :] = joint[-3:, :] = 1; joint[:, :3] = joint[:, -3:] = 1
    img = lay(img, joint, '#55534c', .7)
    save('concrete', img, height=fine * .6 + mid * .4 - cr * .8 - joint * .9, strength=3)

# ---------------- tile（市松のタイル）----------------
def tile():
    N = 512; h = N // 2; rng = np.random.default_rng(10)
    img = np.zeros((N, N, 3)); hgt = np.zeros((N, N))
    for ty in range(2):
        for tx in range(2):
            col = hexrgb('#b3ab92' if (tx + ty) % 2 == 0 else '#c2bba4') * rng.uniform(.96, 1.04)
            img[ty * h:(ty + 1) * h, tx * h:(tx + 1) * h] = col
    n = fbm(N, N, 1.2, 11); img *= (0.94 + n[..., None] * .12)
    g = np.zeros((N, N)); w = 5
    for k in (0, h): g[k:k + w // 2 + 1, :] = 1; g[:, k:k + w // 2 + 1] = 1; g[(k - w // 2) % N:(k) if k else N, :] = 1; g[:, (k - w // 2) % N:(k) if k else N] = 1
    g[-w // 2:, :] = 1; g[:, -w // 2:] = 1
    img = lay(img, g, '#7d7764', 1)
    chip = np.clip((fbm(N, N, 1.8, 12) - .8) * 8, 0, 1) * np.clip(1 - g, 0, 1); img = lay(img, chip, '#9a937c', .5)
    save('tile', img, height=n * .3 - g * 1.0, strength=4)

# ---------------- wood（2F の床：8枚の板）----------------
def wood():
    N = 1024; P = N // 8; rng = np.random.default_rng(20)
    grain = fbm(N, N, 1.4, 21, aniso=(9, .6)); fine = fbm(N, N, .7, 22, aniso=(6, .5))
    cols = ['#8e6a45', '#9b744b', '#85613e', '#a07a50']
    img = np.zeros((N, N, 3)); hgt = np.zeros((N, N))
    for i in range(8):
        c = hexrgb(cols[i % 4]) * rng.uniform(.95, 1.05); sl = slice(i * P, (i + 1) * P)
        g = grain[sl] ; rings = (np.sin(g * 40 + i) * .5 + .5)
        img[sl] = c * (0.82 + g[..., None] * .22) * (0.94 + rings[..., None] * .08) * (0.96 + fine[sl][..., None] * .08)
        # 板のつぎ目（たて）と、くぎ
        cut = int(rng.uniform(0, N)); img[sl, cut:cut + 3] *= .45; hgt[sl, cut:cut + 3] = -1
        for x in (cut + 14, (cut - 16) % N):
            for y in (i * P + 18, (i + 1) * P - 20):
                yy, xx = np.ogrid[-4:5, -4:5]; m = (yy ** 2 + xx ** 2) <= 12
                img[(y - 4):(y + 5), (x - 4) % N:(x - 4) % N + 9][m[:, :min(9, N - (x - 4) % N)]] *= .5 if (x - 4) % N + 9 <= N else 1
        # ふし
        kx, ky = int(rng.uniform(0, N)), int(rng.uniform(i * P + 20, (i + 1) * P - 20))
        yy, xx = np.ogrid[0:N, 0:N]; d = np.sqrt(((xx - kx + N / 2) % N - N / 2) ** 2 / 3 + (yy - ky) ** 2)
        k = np.clip(1 - d / 14, 0, 1) * (np.arange(N)[:, None] // P == i); img = lay(img, k, '#4e3720', .7)
    seam = np.zeros((N, N)); 
    for i in range(8): seam[i * P:i * P + 3] = 1
    img = lay(img, seam, '#2b1c0e', .75)
    save('wood', img, height=grain * .4 + fine * .2 - seam * 1.2 + hgt * .8, strength=3)

# ---------------- wall / wall2（下に腰板。横だけつながる）----------------
def wall(name, top, band, low):
    N = 1024; img = np.ones((N, N, 3)) * hexrgb(top); y = np.arange(N)[:, None] / N
    n1 = fbm(N, N, 1.5, 30); n2 = fbm(N, N, .5, 31); streak = fbm(N, N, 1.2, 32, aniso=(.15, 4))
    img *= (0.94 + n1[..., None] * .1) * (0.97 + n2[..., None] * .06)
    img = lay(img, np.clip((streak - .55) * 3, 0, 1) * (y < .7), '#a69b80', .25)
    lowm = (y >= .72).astype(float) * np.ones((1, N)); bandm = ((y >= .7) & (y < .73)).astype(float) * np.ones((1, N))
    img = lay(img, lowm, low); img[(y >= .72)[:, 0]] *= (0.9 + fbm(N, N, 1.0, 33)[(y >= .72)[:, 0]][..., None] * .16)
    scuff = np.clip((fbm(N, N, .9, 34) - .7) * 5, 0, 1) * (y > .8); img = lay(img, scuff, '#2b2d27', .25)
    img = lay(img, bandm, band)
    grime = np.clip((y - .55) * 1.6, 0, 1) * (0.6 + fbm(N, N, 1.6, 35) * .6); img *= (1 - grime[..., None] * .12)
    hgt = n2 * .3 + n1 * .2 + bandm * 1.2 + lowm * .4
    save(name, img, height=hgt, strength=2.5, wrapy=False)

# ---------------- hazard（黄色と黒のしま。はげかけ）----------------
def hazard():
    W, H = 512, 128; P = 64
    xs, ys = np.meshgrid(np.arange(W), np.arange(H))
    stripe = (((xs + (H - ys)) % P) < P / 2).astype(float)
    img = np.ones((H, W, 3)) * hexrgb('#cfae45'); img = lay(img, stripe, '#1d1b19')
    wear = np.clip((fbm(H, W, 1.3, 40) - .62) * 5, 0, 1); img = lay(img, wear, '#8f8c83', .7)
    n = fbm(H, W, .6, 41); img *= (0.92 + n[..., None] * .14)
    save('hazard', img, height=n * .3 - wear * .5, strength=2)

# ---------------- roof（屋上の防水シート）----------------
def roof():
    N = 512; img = np.ones((N, N, 3)) * hexrgb('#a3a596')
    n = fbm(N, N, 1.4, 50); f = fbm(N, N, .5, 51); img *= (0.9 + n[..., None] * .14) * (0.96 + f[..., None] * .08)
    pud = np.clip((fbm(N, N, 2.4, 52) - .65) * 4, 0, 1); img = lay(img, pud, '#7d806f', .45)
    seam = np.zeros((N, N)); seam[:4] = seam[-4:] = seam[:, :4] = seam[:, -4:] = 1; img = lay(img, seam, '#6b6d60', .8)
    hi = np.zeros((N, N)); hi[6:9, 6:-6] = hi[6:-6, 6:9] = 1; img = lay(img, hi, '#d8dacb', .25)
    save('roof', img, height=f * .4 + n * .2 + seam * .8, strength=2.5)

# ---------------- shutter（車庫のシャッター）----------------
def shutter():
    N = 512; P = 32; img = np.ones((N, N, 3)) * hexrgb('#8c9187'); y = np.arange(N)[:, None] % P
    prof = np.where(y < 5, .25, np.where(y > P - 7, -.6, np.sin((y - 5) / (P - 12) * math.pi) * .2))
    img *= (1 + prof[..., None] * .3)
    n = fbm(N, N, 1.0, 60, aniso=(.3, 2)); img *= (0.94 + n[..., None] * .1)
    rust = np.clip((fbm(N, N, 1.1, 61, aniso=(.12, 3)) - .66) * 4, 0, 1); img = lay(img, rust, '#8a5a3a', .35)
    save('shutter', img, height=prof * np.ones((1, N)) + n * .1, strength=4)

# ---------------- grass（公園のしばふ）----------------
def grass():
    N = 1024; rng = np.random.default_rng(70); base = hexrgb('#86a052')
    img = np.ones((N, N, 3)) * base
    p = fbm(N, N, 1.7, 71); img *= (0.86 + p[..., None] * .24)
    img = lay(img, np.clip((fbm(N, N, 1.9, 72) - .6) * 3, 0, 1), '#a7b35c', .35)
    blades = []
    for _ in range(9000):
        x, y = rng.uniform(0, N), rng.uniform(0, N); L = rng.uniform(5, 13); a = rng.normal(-math.pi / 2, .35)
        blades.append((x, y, x + math.cos(a) * L, y + math.sin(a) * L, rng.random()))
    dark = tiled(lambda d, ox, oy: [d.line([(b[0] + ox, b[1] + oy), (b[2] + ox, b[3] + oy)], fill=255, width=2) for b in blades if b[4] < .5], N, N)
    light = tiled(lambda d, ox, oy: [d.line([(b[0] + ox, b[1] + oy), (b[2] + ox, b[3] + oy)], fill=255, width=2) for b in blades if b[4] >= .5], N, N)
    img = lay(img, dark, '#4f6e2a', .45); img = lay(img, light, '#c4d27e', .35)
    flowers = tiled(lambda d, ox, oy: [d.ellipse([b[0] + ox - 2, b[1] + oy - 2, b[0] + ox + 2, b[1] + oy + 2], fill=255) for b in blades[:60]], N, N)
    img = lay(img, flowers, '#f4f1e2', .8)
    save('grass', img, height=p * .3 + light * .5 - dark * .3, strength=2)

# ---------------- dirt（公園の土の道）----------------
def dirt():
    N = 512; rng = np.random.default_rng(80); img = np.ones((N, N, 3)) * hexrgb('#c9ad7c')
    n = fbm(N, N, 1.3, 81); f = fbm(N, N, .4, 82); img *= (0.88 + n[..., None] * .2) * (0.95 + f[..., None] * .1)
    pts = [(rng.uniform(0, N), rng.uniform(0, N), rng.uniform(1.5, 4.5), rng.random()) for _ in range(700)]
    peb = tiled(lambda d, ox, oy: [d.ellipse([p[0] + ox - p[2], p[1] + oy - p[2] * .8, p[0] + ox + p[2], p[1] + oy + p[2] * .8], fill=255) for p in pts], N, N)
    img = lay(img, peb, '#8f7550', .55)
    hi = tiled(lambda d, ox, oy: [d.ellipse([p[0] + ox - p[2] * .5, p[1] + oy - p[2] * .6, p[0] + ox + p[2] * .2, p[1] + oy - p[2] * .1], fill=255) for p in pts if p[3] > .4], N, N)
    img = lay(img, hi, '#e9dcbc', .5)
    save('dirt', img, height=n * .3 + f * .3 + peb * .8, strength=2.5)

# ---------------- stone（広場の石だたみ：レンガ積み）----------------
def stone():
    N = 512; B = 128; rng = np.random.default_rng(90); img = np.zeros((N, N, 3)); hgt = np.zeros((N, N))
    yy, xx = np.mgrid[0:N, 0:N]
    for r in range(N // B):
        off = (r % 2) * B // 2
        for c in range(-1, N // B + 1):
            x0 = c * B + off; tone = rng.uniform(.9, 1.08); col = hexrgb('#bdb7a8') * tone * np.array([1, rng.uniform(.98, 1.02), rng.uniform(.96, 1.03)])
            m = (yy >= r * B) & (yy < (r + 1) * B) & (((xx - x0) % N) < B) & (((xx - x0) % N) >= 0)
            img[m] = col
            lx = ((xx - x0) % N); ly = yy - r * B
            bev = np.clip(np.minimum.reduce([lx, B - 1 - lx, ly, B - 1 - ly]) / 10, 0, 1)
            hgt[m] = bev[m]
    n = fbm(N, N, 1.1, 91); f = fbm(N, N, .4, 92); img *= (0.9 + n[..., None] * .14) * (0.95 + f[..., None] * .1)
    grout = (hgt < .25).astype(float); img = lay(img, grout, '#6b6455', .85)
    img *= (0.85 + hgt[..., None] * .15)
    save('stone', img, height=hgt + f * .2, strength=3)

# ---------------- sand（砂場）----------------
def sand():
    N = 512; img = np.ones((N, N, 3)) * hexrgb('#e2cf98')
    n = fbm(N, N, 1.2, 100); f = fbm(N, N, .1, 101); rip = (np.sin(fbm(N, N, 1.6, 102, aniso=(1.5, .5)) * 60) * .5 + .5)
    img *= (0.92 + n[..., None] * .1) * (0.93 + f[..., None] * .14) * (0.96 + rip[..., None] * .06)
    save('sand', img, height=f * .5 + rip * .4, strength=2)

for fn in (concrete, tile, wood, hazard, roof, shutter, grass, dirt, stone, sand): fn()
wall('wall', '#d9cfb3', '#3b3f35', '#6f7a5e'); wall('wall2', '#c9c4ad', '#2e3a44', '#4f6f86')
