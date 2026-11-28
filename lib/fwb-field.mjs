// =====================================================================
//  風情ウォッチバスターズ：フィールド（大きなマップ）の しくみ
//  models/<名前>.glb と models/<名前>.col.json（"field": true）をいっしょに使う。
//   ・当たり判定：箱（box）・丸（circle）・線（seg＝はばのある線分）を 8m のマスに入れて 近くだけ しらべる
//   ・木・草・花・電柱など 同じメッシュの物は まとめて インスタンス描画（40m ごとに分けて、見えない所は描かない）
//   ・木と草は 風で ゆれる（インスタンスの行列を 毎フレーム 少し かたむける）
//   ・カメラとキャラのあいだの 建物・木・電柱は 半透明に
//   ・遠くの家は かんたんな形（*_LOD）に、遠くの草花は 描かない
//   ・水路の水が ながれる、桜の花びらが まう
//   ・ミニマップ（右上・M で 大きく）、出口（つぎのマップへ。まだの所は 通行止め）、昼・夕方・夜
// =====================================================================
import { Entity, Color, Vec2, Vec3, Quat, Mat4, BoundingBox, VertexBuffer, VertexFormat, MeshInstance, Mesh, PlaneGeometry, StandardMaterial,
  BLEND_NORMAL, BLEND_NONE, BUFFER_DYNAMIC, CULLFACE_NONE } from 'playcanvas';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// ---------------------------------------------------------------------
//  当たり判定（マスで しぼりこむ）
// ---------------------------------------------------------------------
export function makeCollider(COL, cell = 8) {
  const grid = new Map(), key = (i, j) => i * 100003 + j;
  const items = [];
  const add = (it, x0, z0, x1, z1) => {
    items.push(it);
    for (let i = Math.floor(x0 / cell); i <= Math.floor(x1 / cell); i++) for (let j = Math.floor(z0 / cell); j <= Math.floor(z1 / cell); j++) {
      const k = key(i, j); if (!grid.has(k)) grid.set(k, []); grid.get(k).push(it);
    }
  };
  for (const b of COL.box || []) add({ t: 0, d: b, h: b[4], note: b[5] }, b[0], b[2], b[1], b[3]);
  for (const c of COL.circle || []) add({ t: 1, d: c, h: c[3], note: c[4] }, c[0] - c[2], c[1] - c[2], c[0] + c[2], c[1] + c[2]);
  for (const s of COL.seg || []) add({ t: 2, d: s, h: s[5], note: s[6] }, Math.min(s[0], s[2]) - s[4], Math.min(s[1], s[3]) - s[4], Math.max(s[0], s[2]) + s[4], Math.max(s[1], s[3]) + s[4]);
  let stamp = 0;
  const near = (x0, z0, x1, z1) => {
    stamp++; const out = [];
    for (let i = Math.floor(x0 / cell); i <= Math.floor(x1 / cell); i++) for (let j = Math.floor(z0 / cell); j <= Math.floor(z1 / cell); j++) {
      const a = grid.get(key(i, j)); if (!a) continue;
      for (const it of a) if (it._s !== stamp) { it._s = stamp; out.push(it); }
    }
    return out;
  };
  let lastHit = '';
  // 丸いキャラ（半径 r）を おしだす。y が 物の高さより上なら（ジャンプで のった）とおす
  function collide(p, r = .35, useY = false) {
    lastHit = '';
    const cand = near(p.x - r - 1, p.z - r - 1, p.x + r + 1, p.z + r + 1);
    for (let it = 0; it < 3; it++) {
      for (const o of cand) {
        if (useY && p.y > o.h - .05) continue;
        const d = o.d;
        if (o.t === 0) {
          const [x0, x1, z0, z1] = d, cx = clamp(p.x, x0, x1), cz = clamp(p.z, z0, z1), dx = p.x - cx, dz = p.z - cz, dd = Math.hypot(dx, dz);
          if (dd >= r) continue; lastHit = o.note || 'かべ';
          if (dd > 1e-5) { p.x += dx / dd * (r - dd); p.z += dz / dd * (r - dd); }
          else { const pen = [p.x - x0, x1 - p.x, p.z - z0, z1 - p.z], m = Math.min(...pen), k = pen.indexOf(m); if (k === 0) p.x = x0 - r; else if (k === 1) p.x = x1 + r; else if (k === 2) p.z = z0 - r; else p.z = z1 + r; }
        } else if (o.t === 1) {
          const [x, z, cr] = d, dx = p.x - x, dz = p.z - z, dd = Math.hypot(dx, dz), m = cr + r;
          if (dd >= m) continue; lastHit = o.note || 'もの';
          if (dd > 1e-5) { p.x = x + dx / dd * m; p.z = z + dz / dd * m; } else p.x = x + m;
        } else {
          const [ax, az, bx, bz, sr] = d, ux = bx - ax, uz = bz - az, L = ux * ux + uz * uz || 1e-9, t = clamp(((p.x - ax) * ux + (p.z - az) * uz) / L, 0, 1);
          const cx = ax + ux * t, cz = az + uz * t, dx = p.x - cx, dz = p.z - cz, dd = Math.hypot(dx, dz), m = sr + r;
          if (dd >= m) continue; lastHit = o.note || 'さく';
          if (dd > 1e-5) { p.x = cx + dx / dd * m; p.z = cz + dz / dd * m; } else { const l = Math.sqrt(L); p.x = cx - uz / l * m; p.z = cz + ux / l * m; }
        }
      }
    }
  }
  // a → b の線が かべ（高さ .8 以上）に さえぎられるか
  function blocked(a, b) {
    const dx = b.x - a.x, dz = b.z - a.z;
    for (const o of near(Math.min(a.x, b.x) - 1, Math.min(a.z, b.z) - 1, Math.max(a.x, b.x) + 1, Math.max(a.z, b.z) + 1)) {
      if (o.h < .8) continue; const d = o.d;
      if (o.t === 0) {
        const [x0, x1, z0, z1] = d; let t0 = 0, t1 = 1, out = false;
        for (const [p, dd, lo, hi] of [[a.x, dx, x0, x1], [a.z, dz, z0, z1]]) {
          if (Math.abs(dd) < 1e-6) { if (p < lo || p > hi) { out = true; break; } continue; }
          let u = (lo - p) / dd, v = (hi - p) / dd; if (u > v) [u, v] = [v, u]; t0 = Math.max(t0, u); t1 = Math.min(t1, v); if (t0 > t1) { out = true; break; }
        }
        if (!out && t0 <= t1 && t0 < 1 && t1 > 0) return true;
      } else if (o.t === 1) {
        const [x, z, r] = d; if (r < .25) continue;
        const L = dx * dx + dz * dz || 1e-6, t = clamp(((x - a.x) * dx + (z - a.z) * dz) / L, 0, 1), cx = a.x + dx * t, cz = a.z + dz * t;
        if (Math.hypot(cx - x, cz - z) < r * .9 && t > .02 && t < .98) return true;
      } else {
        const [ax, az, bx, bz] = d, ex = bx - ax, ez = bz - az, den = dx * ez - dz * ex;
        if (Math.abs(den) < 1e-9) continue;
        const t = ((ax - a.x) * ez - (az - a.z) * ex) / den, u = ((ax - a.x) * dz - (az - a.z) * dx) / den;
        if (t > .02 && t < .98 && u >= 0 && u <= 1) return true;
      }
    }
    return false;
  }
  return { collide, blocked, near, get lastHit() { return lastHit; }, items };
}

// ---------------------------------------------------------------------
//  フィールド本体
// ---------------------------------------------------------------------
export function setupField({ app, mapEntity, col, camera, sun, fill, getPlayer, onExit, ui = true }) {
  const device = app.graphicsDevice, F = { col, camera };
  const C = makeCollider(col); F.collide = C.collide; F.blocked = C.blocked; Object.defineProperty(F, 'lastHit', { get: () => C.lastHit });
  F.colNear = (p, r) => C.near(p.x - r, p.z - r, p.x + r, p.z + r);
  // 地面や道は 影を落とさない（受けるだけ）
  for (const n of ['Terrain', 'MainRoads', 'ResidentialRoads', 'Sidewalks', 'Waterways', 'SchoolGround', 'ResidentialAreas']) {
    const g = mapEntity.findByName(n); if (g) g.findComponents('render').forEach(r => { if (!/walls$/.test(r.entity.name)) r.castShadows = false; });
  }

  // ---- マテリアルの 手なおし ----
  const mats = new Map();
  mapEntity.findComponents('render').forEach(r => r.meshInstances.forEach(mi => { const m = mi.material; if (m && !mats.has(m.name + '#' + m.id)) mats.set(m.name + '#' + m.id, m); }));
  const M = { water: [], glass: [], lamp: [], neon: [], sign: [], clear: [] };
  for (const m of mats.values()) {
    const n = m.name || '';
    if (/^(decal_|pic_fencenet|pic_decal)/.test(n)) { m.blendType = BLEND_NONE; m.alphaTest = .5; m.depthWrite = true; m.cull = CULLFACE_NONE; }
    if (n === 'water') M.water.push(m);
    if (n === 'glass') M.glass.push(m);
    if (n === 'lamp') M.lamp.push(m);
    if (n === 'neon') M.neon.push(m);
    if (n === 'clear') { M.clear.push(m); m.depthWrite = false; }
    if (/^sign_/.test(n)) M.sign.push(m);
    // つやを おさえて アニメ調に
    if (n !== 'glass' && n !== 'water' && n !== 'clear') { if (m.glossInvert) m.gloss = Math.max(m.gloss, .85); else m.gloss = Math.min(m.gloss, .18); m.specularityFactor = .2; }
    if (n === 'water') { m.gloss = .75; m.specularityFactor = .6; }
    m.update();
  }

  // ---- インスタンス描画：同じメッシュが たくさんある物を まとめる ----
  const SWAY = { tree_round_a: 1.0, tree_round_b: 1.0, tree_cone: .7, tree_sakura: 1.1, bush: 2.0, grass_tuft: 7, flower_clump: 6 };
  const FADEABLE = /^(tree_|bush|pole$|pole_|curve_mirror)/;
  const FARHIDE = /^(grass_tuft|flower_)/;   // 遠くでは描かない
  const groups = new Map();
  mapEntity.forEach(e => {
    if (!e.render || !/\.\d{3,}$/.test(e.name)) return;
    const tpl = e.name.replace(/\.\d{3,}$/, '');
    for (const mi of e.render.meshInstances) {
      const k = tpl + '|' + mi.mesh.id + '|' + mi.material.id;
      if (!groups.has(k)) groups.set(k, { tpl, mesh: mi.mesh, material: mi.material, list: [] });
      groups.get(k).list.push(e);
    }
  });
  const chunks = [], CH = 64, tmpM = new Mat4(), tmpA = new BoundingBox();
  const pieces = [];         // 1本ずつ：{ chunk, i, pos, rot, scl, tpl, base(Float32Array 16) }
  for (const g of groups.values()) {
    if (g.list.length < 4) continue;
    const by = new Map();
    for (const e of g.list) {
      const p = e.getPosition(), k = Math.floor(p.x / CH) + ',' + Math.floor(p.z / CH);
      if (!by.has(k)) by.set(k, []); by.get(k).push(e);
    }
    for (const [k, list] of by) {
      const data = new Float32Array(list.length * 16), aabb = new BoundingBox(); let first = true;
      const ch = { tpl: g.tpl, data, base: new Float32Array(list.length * 16), n: list.length, dirty: false, sway: SWAY[g.tpl] || 0, farHide: FARHIDE.test(g.tpl), center: new Vec3(), hidden: new Uint8Array(list.length) };
      list.forEach((e, i) => {
        const w = e.getWorldTransform(); data.set(w.data, i * 16); ch.base.set(w.data, i * 16);
        tmpA.setFromTransformedAabb(g.mesh.aabb, w); if (first) { aabb.copy(tmpA); first = false; } else aabb.add(tmpA);
        if (FADEABLE.test(g.tpl)) pieces.push({ ch, i, tpl: g.tpl, mesh: g.mesh, material: g.material, pos: e.getPosition().clone(), rot: e.getRotation().clone(), scl: e.getLocalScale().clone(), r: Math.max(g.mesh.aabb.halfExtents.x, g.mesh.aabb.halfExtents.z) * e.getLocalScale().x, h: (g.mesh.aabb.center.y + g.mesh.aabb.halfExtents.y) * e.getLocalScale().y });
      });
      aabb.halfExtents.add(new Vec3(.5, .5, .5));
      const vb = new VertexBuffer(device, VertexFormat.getDefaultInstancingFormat(device), list.length, { usage: BUFFER_DYNAMIC, data });
      const mi = new MeshInstance(g.mesh, g.material); mi.setInstancing(vb); mi.setCustomAabb(aabb);
      const ent = new Entity('inst_' + g.tpl + '_' + k); ent.addComponent('render', { meshInstances: [mi], castShadows: !ch.farHide, receiveShadows: true });
      app.root.addChild(ent); ch.vb = vb; ch.ent = ent; ch.center.copy(aabb.center); ch.mi = mi;
      chunks.push(ch);
    }
    for (const e of g.list) e.destroy();
  }

  // ---- 遠くの家は かんたんな形 ----
  const lods = [];
  mapEntity.forEach(e => {
    if (!/_LOD$/.test(e.name) || !e.parent) return;
    const full = e.parent.children.find(c => c !== e && c.render); if (!full) return;
    const aabb = new BoundingBox(); let f = true; full.render.meshInstances.forEach(mi => { if (f) { aabb.copy(mi.aabb); f = false; } else aabb.add(mi.aabb); });
    lods.push({ lod: e, full, c: aabb.center.clone(), state: -1 }); e.enabled = false;
  });

  // ---- 半透明にする 建物（カメラとキャラのあいだ）----
  const occ = [];
  const OCC_GROUPS = ['Houses', 'KazamiElementarySchool', 'Gymnasium', 'HidamariNursery', 'MarufukuMart', 'AsakuraHouse', 'TsukimoriHouse', 'Hanabiyori', 'KomugiBakery', 'Uomaru', 'FutabaBank', 'TsubamePostOffice', 'ForestShop', 'OtherBuildings', 'SwimmingPool', 'StreetProps', 'MapExits', 'MitsubaPark'];
  for (const gn of OCC_GROUPS) {
    const g = mapEntity.findByName(gn); if (!g) continue;
    const add = (e) => {
      const mis = []; e.forEach(n => { if (n.render && n.enabled !== false && !/_LOD$/.test(n.name)) mis.push(...n.render.meshInstances); });
      if (!mis.length) return; const aabb = new BoundingBox(); aabb.copy(mis[0].aabb); for (const mi of mis) aabb.add(mi.aabb);
      if (aabb.halfExtents.y < .6) return;
      occ.push({ e, mis, aabb, faded: false, t: 0 });
    };
    for (const c of g.children) add(c);
  }
  const fadeCache = new Map();
  const fadeMat = (m) => {
    if (!fadeCache.has(m)) { const f = m.clone(); f.opacity = .28; f.blendType = BLEND_NORMAL; f.depthWrite = false; f.update(); fadeCache.set(m, f); }
    return fadeCache.get(m);
  };
  const setFade = (o, on) => {
    if (o.faded === on) return; o.faded = on;
    for (const mi of o.mis) { if (on) { mi.__m = mi.material; mi.material = fadeMat(mi.material); } else if (mi.__m) mi.material = mi.__m; }
  };
  // 木・電柱の 半透明：インスタンスから 一時的に はずして、すけた コピーを置く
  const fadePool = new Map();
  const poolGet = (pc) => {
    const key = pc.mesh.id + '|' + pc.material.id; if (!fadePool.has(key)) fadePool.set(key, []);
    const arr = fadePool.get(key); let it = arr.find(x => !x.used);
    if (!it) { const mi = new MeshInstance(pc.mesh, fadeMat(pc.material)); const e = new Entity(); e.addComponent('render', { meshInstances: [mi], castShadows: false }); app.root.addChild(e); it = { e, used: false }; arr.push(it); }
    it.used = true; it.e.enabled = true; return it;
  };
  const fadedPieces = new Set();
  const zero16 = new Float32Array(16);
  function pieceFade(pc, on) {
    if (!!pc.fade === on) return;
    if (on) { pc.ch.data.set(zero16, pc.i * 16); pc.ch.hidden[pc.i] = 1; pc.fade = poolGet(pc); pc.fade.e.setPosition(pc.pos); pc.fade.e.setRotation(pc.rot); pc.fade.e.setLocalScale(pc.scl); fadedPieces.add(pc); }
    else { pc.ch.data.set(pc.ch.base.subarray(pc.i * 16, pc.i * 16 + 16), pc.i * 16); pc.ch.hidden[pc.i] = 0; pc.fade.used = false; pc.fade.e.enabled = false; pc.fade = null; fadedPieces.delete(pc); }
    pc.ch.dirty = true;
  }

  // ---- 桜の花びら ----
  const sakura = pieces.filter(p => /^tree_sakura/.test(p.tpl));
  const PET = 140, petals = [];
  const petalMesh = Mesh.fromGeometry(device, new PlaneGeometry({ halfExtents: new Vec2(.06, .045) }));
  const petalMat = new StandardMaterial(); petalMat.diffuse = new Color(1, .78, .86); petalMat.emissive = new Color(.35, .2, .25); petalMat.cull = CULLFACE_NONE; petalMat.update();
  const petalData = new Float32Array(PET * 16);
  const petalVB = new VertexBuffer(device, VertexFormat.getDefaultInstancingFormat(device), PET, { usage: BUFFER_DYNAMIC, data: petalData });
  const petalMI = new MeshInstance(petalMesh, petalMat); petalMI.setInstancing(petalVB); petalMI.cull = false;
  const petalE = new Entity('petals'); petalE.addComponent('render', { meshInstances: [petalMI], castShadows: false }); app.root.addChild(petalE);
  for (let i = 0; i < PET; i++) petals.push({ life: 0 });

  // ---- 昼・夕方・夜 ----
  const TIMES = {
    day:     { sun: [1, .96, .9], si: 1.55, sa: [50, 30], amb: [.58, .6, .66], sky: [.62, .8, .95], fill: .45, glass: 0, lamp: 0, sign: 0 },
    evening: { sun: [1, .66, .42], si: 1.25, sa: [18, 60], amb: [.5, .42, .45], sky: [.96, .64, .5], fill: .3, glass: .25, lamp: .8, sign: .25 },
    night:   { sun: [.5, .6, .9], si: .35, sa: [55, -40], amb: [.2, .24, .38], sky: [.08, .1, .2], fill: .12, glass: .9, lamp: 2.2, sign: .8 },
  };
  let timeName = 'day';
  function setTime(n) {
    const T = TIMES[n]; if (!T) return; timeName = n;
    if (sun) { sun.light.color = new Color(...T.sun); sun.light.intensity = T.si; sun.setLocalEulerAngles(T.sa[0], T.sa[1], 0); }
    if (fill) fill.light.intensity = T.fill;
    app.scene.ambientLight = new Color(...T.amb);
    camera.camera.clearColor = new Color(...T.sky);
    for (const m of M.glass) { m.emissive = new Color(1, .82, .5); m.emissiveIntensity = T.glass; m.update(); }
    for (const m of M.lamp) { m.emissive = new Color(1, .9, .6); m.emissiveIntensity = T.lamp; m.update(); }
    for (const m of M.neon) { m.emissive = new Color(.9, .95, 1); m.emissiveIntensity = .3 + T.lamp * .6; m.update(); }
    for (const m of M.sign) { if (m.diffuseMap) { m.emissiveMap = m.diffuseMap; m.emissive = new Color(1, 1, 1); m.emissiveIntensity = T.sign; m.update(); } }
    if (ui) document.querySelectorAll('#fwbTime button').forEach(b => b.classList.toggle('on', b.dataset.t === n));
  }
  F.setTime = setTime; F.TIMES = TIMES; Object.defineProperty(F, 'time', { get: () => timeName });

  // ---- ミニマップ ----
  const mini = col.mini || {}, [ax0, az0, ax1, az1] = col.aabb || [-100, -130, 100, 130];
  const PX = 4, MW = Math.ceil((ax1 - ax0) * PX) + 8, MH = Math.ceil((az1 - az0) * PX) + 8;
  const off = document.createElement('canvas'); off.width = MW; off.height = MH;
  { const g = off.getContext('2d'), T = (x, z) => [(x - ax0) * PX + 4, (z - az0) * PX + 4];
    const poly = (list, color, stroke) => { for (const rings of list || []) { g.beginPath(); for (const r of rings) r.forEach((p, i) => { const [x, y] = T(p[0], p[1]); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.closePath(); g.fillStyle = color; g.fill('evenodd'); if (stroke) { g.strokeStyle = stroke; g.lineWidth = 1; g.stroke(); } } };
    g.clearRect(0, 0, MW, MH);
    if (mini.outline) poly([[mini.outline]], '#e9d2a8', '#7a6a4a');
    poly(mini.grass, '#a9da86'); poly(mini.dirt, '#ecc98e'); poly(mini.park, '#7cc45a'); poly(mini.side, '#e6c9a0'); poly(mini.paths, '#dca08c');
    poly(mini.roads, '#8e9198'); poly(mini.water, '#5cc0ea');
    for (const [x, z] of mini.trees || []) { const [px, py] = T(x, z); g.fillStyle = '#5a9e48'; g.beginPath(); g.arc(px, py, 1.6 * PX * .5, 0, Math.PI * 2); g.fill(); }
    for (const b of mini.buildings || []) { const [x0, y0] = T(b[0], b[1]), [x1, y1] = T(b[2], b[3]); g.fillStyle = b[4]; g.fillRect(x0, y0, x1 - x0, y1 - y0); g.strokeStyle = 'rgba(40,30,20,.55)'; g.lineWidth = 1; g.strokeRect(x0 + .5, y0 + .5, x1 - x0 - 1, y1 - y0 - 1); }
  }
  const ICON = { school: ['学', '#1f5fbf'], nursery: ['保', '#e07b1f'], hall: ['公', '#7a43b6'], mart: ['コ', '#3f9a2a'], park: ['園', '#3f9a2a'], flower: ['花', '#e0457b'],
    home: ['家', '#d7262a'], bakery: ['パ', '#e07b1f'], fish: ['魚', '#1f6fd0'], bank: ['銀', '#1f6fd0'], post: ['〒', '#d7262a'], forest: ['森', '#2f8a2a'] };
  let miniEl = null, bigEl = null, bigOn = false, toastEl = null, timeEl = null;
  if (ui) {
    const css = document.createElement('style');
    css.textContent = `#fwbMini{position:fixed;right:14px;top:14px;width:210px;height:210px;border-radius:50%;border:4px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.35);background:#cfe8b8;z-index:8;cursor:pointer}
#fwbMiniName{position:fixed;right:14px;top:232px;width:218px;text-align:center;font:15px 'FWB',sans-serif;color:#fff;-webkit-text-stroke:4px #234;paint-order:stroke fill;z-index:8;pointer-events:none}
#fwbBig{position:fixed;inset:0;display:none;z-index:40;background:rgba(10,20,40,.55);align-items:center;justify-content:center}#fwbBig.on{display:flex}
#fwbBig canvas{max-width:96vw;max-height:94vh;border-radius:14px;box-shadow:0 6px 30px rgba(0,0,0,.5);background:#fff}
#fwbToast{position:fixed;left:50%;top:30%;transform:translateX(-50%);padding:10px 26px;border-radius:12px;background:rgba(20,10,40,.78);color:#fff;font:22px 'FWB',sans-serif;opacity:0;transition:opacity .25s;pointer-events:none;z-index:9;text-align:center}#fwbToast.on{opacity:1}
#fwbToast small{display:block;font-size:14px;opacity:.8}
#fwbTime{position:fixed;right:14px;top:258px;width:218px;display:flex;gap:4px;justify-content:center;z-index:8}#fwbTime button{font:12px system-ui,sans-serif;padding:3px 9px;border-radius:8px;border:1px solid #3a3f48;background:rgba(18,20,24,.8);color:#fff;cursor:pointer}#fwbTime button.on{background:#3f5f2e;border-color:#9fe28c}`;
    document.head.appendChild(css);
    miniEl = document.createElement('canvas'); miniEl.id = 'fwbMini'; miniEl.width = miniEl.height = 420; document.body.appendChild(miniEl);
    const nm = document.createElement('div'); nm.id = 'fwbMiniName'; nm.textContent = col.name || ''; document.body.appendChild(nm);
    bigEl = document.createElement('div'); bigEl.id = 'fwbBig'; const bc = document.createElement('canvas'); bigEl.appendChild(bc); document.body.appendChild(bigEl);
    toastEl = document.createElement('div'); toastEl.id = 'fwbToast'; document.body.appendChild(toastEl);
    timeEl = document.createElement('div'); timeEl.id = 'fwbTime'; timeEl.innerHTML = '<button data-t="day">昼</button><button data-t="evening">夕方</button><button data-t="night">夜</button>'; document.body.appendChild(timeEl);
    timeEl.querySelectorAll('button').forEach(b => b.onclick = (e) => { setTime(b.dataset.t); e.target.blur(); });
    miniEl.onclick = () => toggleBig(); bigEl.onclick = () => toggleBig(false);
    addEventListener('keydown', (e) => { if (e.code === 'KeyM' && !e.repeat && e.target.tagName !== 'INPUT') toggleBig(); if (e.code === 'Escape' && bigOn) toggleBig(false); });
  }
  const arrow = (g, x, y, ang, s, color = '#ff3b6b') => {
    g.save(); g.translate(x, y); g.rotate(ang); g.beginPath(); g.moveTo(0, -s); g.lineTo(s * .75, s * .7); g.lineTo(0, s * .3); g.lineTo(-s * .75, s * .7); g.closePath();
    g.fillStyle = color; g.fill(); g.lineWidth = s * .22; g.strokeStyle = '#fff'; g.stroke(); g.restore();
  };
  function drawIcons(g, T, scale, labels) {
    for (const [k, x, z] of mini.icons || []) {
      const [px, py] = T(x, z), ic = ICON[k]; if (!ic) continue; const r = 9 * scale;
      g.beginPath(); g.arc(px, py, r, 0, Math.PI * 2); g.fillStyle = ic[1]; g.fill(); g.lineWidth = 2 * scale; g.strokeStyle = '#fff'; g.stroke();
      g.fillStyle = '#fff'; g.font = `${Math.round(11 * scale)}px FWB, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(ic[0], px, py + .5);
    }
    for (const ex of col.exits || []) {
      const [px, py] = T(ex.ax, ex.az); arrow(g, px + ex.dir[0] * 10 * scale, py + ex.dir[1] * 10 * scale, Math.atan2(ex.dir[0], -ex.dir[1]), 9 * scale, '#e8288a');
      if (labels) { g.font = `${Math.round(13 * scale)}px FWB, sans-serif`; g.textAlign = 'center'; g.lineWidth = 4 * scale; g.strokeStyle = '#fff'; const tx = px + ex.dir[0] * 34 * scale, ty = py + ex.dir[1] * 26 * scale; g.strokeText(ex.name, tx, ty); g.fillStyle = '#c8106a'; g.fillText(ex.name, tx, ty); }
    }
    if (labels) for (const [t, x, z, c] of mini.labels || []) {
      const [px, py] = T(x, z); g.font = `${Math.round(13 * scale)}px FWB, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
      const w = g.measureText(t).width + 14 * scale, h = 20 * scale; g.fillStyle = c; g.beginPath(); g.roundRect(px - w / 2, py - h / 2 - 16 * scale, w, h, h / 2); g.fill();
      g.lineWidth = 2 * scale; g.strokeStyle = '#fff'; g.stroke(); g.fillStyle = '#fff'; g.fillText(t, px, py - 16 * scale + .5);
    }
  }
  function drawMini(p, face) {
    if (!miniEl) return; const g = miniEl.getContext('2d'), S = miniEl.width, R = 64, sc = S / (R * 2) / PX;   // 半径 64m を表示
    g.save(); g.clearRect(0, 0, S, S); g.beginPath(); g.arc(S / 2, S / 2, S / 2, 0, Math.PI * 2); g.clip(); g.fillStyle = '#bfe0a8'; g.fillRect(0, 0, S, S);
    const ox = (p.x - ax0) * PX + 4, oy = (p.z - az0) * PX + 4;
    g.drawImage(off, ox - R * PX, oy - R * PX, R * 2 * PX, R * 2 * PX, 0, 0, S, S);
    const T = (x, z) => [((x - ax0) * PX + 4 - ox) * sc + S / 2, ((z - az0) * PX + 4 - oy) * sc + S / 2];
    drawIcons(g, T, 1.6, false);
    arrow(g, S / 2, S / 2, Math.PI - face, 15);
    g.restore();
  }
  function toggleBig(v) {
    if (!bigEl) return; bigOn = v === undefined ? !bigOn : v; bigEl.classList.toggle('on', bigOn);
    if (bigOn) {
      const c = bigEl.querySelector('canvas'), sc = 2; c.width = MW * sc / 1.4; c.height = MH * sc / 1.4; const k = c.width / MW, g = c.getContext('2d');
      g.fillStyle = '#ffffff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(off, 0, 0, c.width, c.height);
      const T = (x, z) => [((x - ax0) * PX + 4) * k, ((z - az0) * PX + 4) * k];
      drawIcons(g, T, 1.1, true);
      const P = getPlayer && getPlayer(); if (P) { const [px, py] = T(P.pos.x, P.pos.z); arrow(g, px, py, Math.PI - P.face, 14); }
      g.font = '26px FWB, sans-serif'; g.textAlign = 'left'; g.fillStyle = '#234'; g.fillText(col.name || '', 16, 34);
    }
  }
  F.toggleMap = toggleBig;

  // ---- 出口 ----
  let toastT = 0, lastExit = null;
  function toast(t, sub) { if (!toastEl) return; toastEl.innerHTML = t + (sub ? `<small>${sub}</small>` : ''); toastEl.classList.add('on'); toastT = 2.2; }
  F.toast = toast;

  // ---- 毎フレーム ----
  let time = 0, slow = 0, waterOff = 0;
  const camPos = new Vec3(), head = new Vec3(), dir = new Vec3();
  const rayAabb = (o, d, maxT, b) => {
    let t0 = 0, t1 = maxT; const mn = b.getMin(), mx = b.getMax();
    for (const ax of ['x', 'y', 'z']) {
      if (Math.abs(d[ax]) < 1e-7) { if (o[ax] < mn[ax] || o[ax] > mx[ax]) return false; continue; }
      let u = (mn[ax] - o[ax]) / d[ax], v = (mx[ax] - o[ax]) / d[ax]; if (u > v) [u, v] = [v, u]; t0 = Math.max(t0, u); t1 = Math.min(t1, v); if (t0 > t1) return false;
    }
    return true;
  };
  F.update = (dt) => {
    time += dt; slow += dt;
    const P = getPlayer && getPlayer(); if (!P) return;
    camPos.copy(camera.getPosition());
    // 水
    waterOff = (waterOff + dt * .04) % 1;
    for (const m of M.water) { m.diffuseMapOffset = new Vec2(waterOff * .3, waterOff); m.update(); }
    // 風（ふきかたが ゆっくり かわる）
    const gust = .6 + .4 * Math.sin(time * .37) * Math.sin(time * .11 + 1);
    for (const ch of chunks) {
      const d2 = (ch.center.x - camPos.x) ** 2 + (ch.center.z - camPos.z) ** 2;
      if (ch.farHide) { const show = d2 < 75 * 75; if (ch.ent.enabled !== show) ch.ent.enabled = show; }
      if (ch.sway && d2 < 90 * 90 && ch.ent.enabled) {
        const amp = ch.sway * Math.PI / 180 * gust, d = ch.data, b = ch.base;
        for (let i = 0; i < ch.n; i++) {
          if (ch.hidden[i]) continue; const o = i * 16, px = b[o + 12], pz = b[o + 14];
          const ph = px * .31 + pz * .17, ax = Math.sin(time * 1.7 + ph) * amp, az = Math.sin(time * 1.3 + ph * 1.3) * amp * .8;
          // かたむき R = Rz(az)·Rx(ax)（小さい角）を 3x3 に かける
          const ca = Math.cos(ax), sa = Math.sin(ax), cb = Math.cos(az), sb = Math.sin(az);
          const r00 = cb, r01 = -sb * ca, r02 = sb * sa, r10 = sb, r11 = cb * ca, r12 = -cb * sa, r20 = 0, r21 = sa, r22 = ca;
          for (let c = 0; c < 3; c++) {
            const x = b[o + c * 4], y = b[o + c * 4 + 1], z = b[o + c * 4 + 2];
            d[o + c * 4] = r00 * x + r01 * y + r02 * z; d[o + c * 4 + 1] = r10 * x + r11 * y + r12 * z; d[o + c * 4 + 2] = r20 * x + r21 * y + r22 * z;
          }
        }
        ch.dirty = true;
      }
      if (ch.dirty) { ch.vb.setData(ch.data); ch.dirty = false; }
    }
    // 半透明：カメラ → キャラの頭・足もと
    head.set(P.pos.x, P.pos.y + 1.0, P.pos.z);
    dir.sub2(head, camPos); const dist = dir.length(); dir.mulScalar(1 / Math.max(dist, 1e-4));
    const dirF = dir.clone(), feet = new Vec3(P.pos.x, P.pos.y + .3, P.pos.z), dir2 = new Vec3().sub2(feet, camPos), dist2 = dir2.length(); dir2.mulScalar(1 / Math.max(dist2, 1e-4));
    for (const o of occ) {
      const d2 = (o.aabb.center.x - P.pos.x) ** 2 + (o.aabb.center.z - P.pos.z) ** 2; if (d2 > 50 * 50) { if (o.faded) setFade(o, false); continue; }
      // キャラ自身が 中に いるような大きな箱（ひろい区画）は さける
      const inside = o.aabb.containsPoint(head);
      const hit = !inside && (rayAabb(camPos, dirF, dist - .6, o.aabb) || rayAabb(camPos, dir2, dist2 - .6, o.aabb));
      if (hit) { o.t = .25; setFade(o, true); } else if (o.faded) { o.t -= dt; if (o.t <= 0) setFade(o, false); }
    }
    for (const pc of pieces) {
      if (Math.abs(pc.pos.x - P.pos.x) > 26 || Math.abs(pc.pos.z - P.pos.z) > 26) { if (pc.fade) pieceFade(pc, false); continue; }
      // 線分（カメラ→頭）と 木の みき〜てっぺん の 近さ
      const cy = pc.pos.y + pc.h * .6, ox = pc.pos.x - camPos.x, oy = cy - camPos.y, oz = pc.pos.z - camPos.z;
      const t = clamp(ox * dirF.x + oy * dirF.y + oz * dirF.z, 0, dist);
      const qx = camPos.x + dirF.x * t - pc.pos.x, qy = camPos.y + dirF.y * t - cy, qz = camPos.z + dirF.z * t - pc.pos.z;
      const near = t < dist - .8 && Math.hypot(qx, qz) < pc.r * .95 + .3 && Math.abs(qy) < pc.h * .6 + .3;
      pieceFade(pc, near);
    }
    // 遠くの家は かんたんな形（0.25秒ごと）
    if (slow > .25) {
      slow = 0;
      for (const l of lods) { const far = (l.c.x - camPos.x) ** 2 + (l.c.z - camPos.z) ** 2 > 85 * 85 ? 1 : 0; if (far !== l.state) { l.state = far; l.lod.enabled = !!far; l.full.enabled = !far; } }
    }
    // 花びら：近くの桜から
    let k = 0;
    for (const pt of petals) {
      if (pt.life <= 0) {
        if (Math.random() < dt * 6 && sakura.length) {
          const near = sakura.filter(s => Math.abs(s.pos.x - P.pos.x) < 30 && Math.abs(s.pos.z - P.pos.z) < 30);
          if (near.length) { const s = near[(Math.random() * near.length) | 0]; const a = Math.random() * Math.PI * 2, r = Math.random() * 1.6 * s.scl.x;
            pt.x = s.pos.x + Math.cos(a) * r; pt.y = s.pos.y + (2.6 + Math.random() * 1.2) * s.scl.y; pt.z = s.pos.z + Math.sin(a) * r; pt.life = 5 + Math.random() * 4; pt.ph = Math.random() * 9; pt.vx = .5 + Math.random() * .6; pt.vz = .2 + Math.random() * .4; }
        }
        if (pt.life <= 0) { petalData.fill(0, k * 16, k * 16 + 16); k++; continue; }
      }
      pt.life -= dt; pt.ph += dt * 3;
      pt.x += (pt.vx * gust + Math.sin(pt.ph) * .3) * dt; pt.z += (pt.vz + Math.cos(pt.ph * .7) * .3) * dt; pt.y = Math.max(.02, pt.y - (.45 + Math.sin(pt.ph * 1.3) * .2) * dt);
      if (pt.y <= .02) pt.life = Math.min(pt.life, .8);
      const rx = pt.ph, rz = pt.ph * .7, s = pt.y <= .02 ? 1 : 1;
      tmpM.setFromEulerAngles(rx * 57.3, pt.ph * 30, rz * 57.3); tmpM.data[12] = pt.x; tmpM.data[13] = pt.y; tmpM.data[14] = pt.z;
      for (let j = 0; j < 12; j++) tmpM.data[j] *= s;
      petalData.set(tmpM.data, k * 16); k++;
    }
    petalVB.setData(petalData);
    // 出口
    let inExit = null;
    for (const ex of col.exits || []) if (Math.hypot(P.pos.x - ex.x, P.pos.z - ex.z) < ex.r) inExit = ex;
    if (inExit && inExit !== lastExit) {
      if (onExit) onExit(inExit);
      if (!inExit.ready) toast(`${inExit.name} へ`, 'この先は まだ 行けません（通行止め）');
    }
    lastExit = inExit;
    if (toastT > 0) { toastT -= dt; if (toastT <= 0 && toastEl) toastEl.classList.remove('on'); }
    drawMini(P.pos, P.face);
  };
  F.stats = () => ({ chunks: chunks.length, instances: chunks.reduce((a, c) => a + c.n, 0), lods: lods.length, occluders: occ.length, pieces: pieces.length });
  setTime('day');
  return F;
}
