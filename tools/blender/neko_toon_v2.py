# Blender 4.2+ / Eevee. Creates a separate collection; does not delete your objects.
import bpy, math
from math import sin, cos, pi, sqrt
from mathutils import Vector
C=bpy.data.collections.new('Neko Toon V2'); bpy.context.scene.collection.children.link(C)
parts=[]
def move(o):
    for c in list(o.users_collection): c.objects.unlink(o)
    C.objects.link(o); return o

def toon(name,colors):
    m=bpy.data.materials.new(name); m.diffuse_color=(*colors[1],1); m.use_nodes=True
    n=m.node_tree.nodes; n.clear(); l=m.node_tree.links
    d=n.new('ShaderNodeBsdfDiffuse'); d.inputs[0].default_value=(1,1,1,1)
    s=n.new('ShaderNodeShaderToRGB'); r=n.new('ShaderNodeValToRGB'); r.color_ramp.interpolation='CONSTANT'
    for e,p,c in zip(r.color_ramp.elements,[0,.36],colors): e.position=p; e.color=(*c,1)
    e=r.color_ramp.elements.new(.72); e.color=(*colors[2],1)
    em=n.new('ShaderNodeEmission'); out=n.new('ShaderNodeOutputMaterial')
    l.new(d.outputs[0],s.inputs[0]); l.new(s.outputs[0],r.inputs[0]); l.new(r.outputs[0],em.inputs[0]); l.new(em.outputs[0],out.inputs[0]); return m
black=toon('Fur',[(.012,.011,.016),(.043,.039,.05),(.09,.085,.105)])
hair=toon('Hair',[(.009,.008,.012),(.035,.032,.043),(.075,.07,.09)])
skin=toon('Face',[(.66,.32,.16),(.98,.63,.36),(1,.79,.55)])
white=toon('Ivory',[(.38,.36,.43),(.78,.77,.83),(.98,.97,1)])
silver=toon('Silver',[(.18,.18,.24),(.52,.53,.62),(.95,.96,1)])
gray=toon('Spiral',[(.15,.14,.20),(.35,.34,.42),(.51,.50,.59)])
ink=toon('Mouth',[(.008,.005,.008)]*3)
high=toon('Hair painted shine',[(.07,.065,.09),(.14,.13,.18),(.19,.18,.23)])
def mesh(name,v,f,m,bone='body',smooth=True):
    me=bpy.data.meshes.new(name); me.from_pydata(v,[],f); me.update(); o=bpy.data.objects.new(name,me); C.objects.link(o); me.materials.append(m)
    for p in me.polygons:p.use_smooth=smooth
    parts.append((o,bone)); return o

def rings(name,rows,m,bone='body',N=32):
    v=[(x+rx*cos(2*pi*j/N),y+ry*sin(2*pi*j/N),z) for x,y,z,rx,ry in rows for j in range(N)]
    f=[(i*N+j,i*N+(j+1)%N,(i+1)*N+(j+1)%N,(i+1)*N+j) for i in range(len(rows)-1) for j in range(N)]
    f += [tuple(reversed(range(N))),tuple((len(rows)-1)*N+j for j in range(N))]; return mesh(name,v,f,m,bone)
def ball(name,loc,scale,m,bone='body',rot=0):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=20,location=loc); o=move(bpy.context.object); o.name=name; o.scale=scale; o.rotation_euler.y=rot; o.data.materials.append(m)
    for p in o.data.polygons:p.use_smooth=True
    parts.append((o,bone)); return o

def tube(name,pts,r,m,bone='body',radii=None):
    c=bpy.data.curves.new(name,'CURVE'); c.dimensions='3D'; c.resolution_u=8; c.bevel_depth=r; c.bevel_resolution=2; c.use_fill_caps=True
    s=c.splines.new('BEZIER'); s.bezier_points.add(len(pts)-1)
    for i,(b,p) in enumerate(zip(s.bezier_points,pts)):
        b.co=p; b.handle_left_type=b.handle_right_type='AUTO'; b.radius=radii[i] if radii else 1
    o=bpy.data.objects.new(name,c); C.objects.link(o); c.materials.append(m); parts.append((o,bone)); return o
# Front = -Y. Body and head proportions based on the supplied turnaround.
rings('Torso',[(0,0,.32,.35,.29),(0,0,.48,.53,.39),(0,0,.75,.62,.44),(0,0,1.05,.61,.43),(0,0,1.35,.49,.36),(0,0,1.58,.29,.26),(0,0,1.64,.15,.15)],black)
for s,side in [(-1,'L'),(1,'R')]:
    ball('Leg '+side,(s*.30,0,.34),(.255,.29,.34),black,'leg.'+side,s*.13)
    ball('Toe '+side,(s*.32,-.16,.105),(.16,.14,.085),white,'leg.'+side)
    ball('Arm '+side,(s*.57,0,1.16),(.19,.22,.43),black,'arm.'+side,-s*.55)
    ball('Paw '+side,(s*.76,-.025,.86),(.125,.14,.11),white,'arm.'+side,-s*.55)
# Fitted ribbed band, continuous surface with shallow grooves.
N=96; rows=[(.60,.575,.415),(.64,.625,.455),(.76,.644,.47),(.93,.638,.465),(1.01,.62,.45),(1.04,.59,.43)]
v=[]
for z,rx,ry in rows:
    for j in range(N):
        a=2*pi*j/N; groove=.009*(.5+.5*cos(16*a))**8; v.append(((rx-groove)*cos(a),(ry-groove)*sin(a),z))
f=[(i*N+j,i*N+(j+1)%N,(i+1)*N+(j+1)%N,(i+1)*N+j) for i in range(len(rows)-1) for j in range(N)]
mesh('Ribbed belly band',v,f,white)
# Front-only bib follows chest; no white collar at the rear.
ball('Front bib',(0,-.305,1.49),(.35,.135,.22),white)
ball('Bell',(0,-.465,1.47),(.126,.105,.126),silver)
tube('Bell groove',[(-.085,-.546,1.44),(0,-.573,1.43),(.085,-.546,1.44)],.009,gray)
ball('Bell hole',(0,-.573,1.415),(.025,.008,.019),ink)
ball('Face',(0,-.075,2.34),(.98,.79,.86),skin,'head')
# One continuous hair shell with a jagged, eye-covering fringe boundary.
N=144; R=24; v=[]
def hairpoint(a,t,offset=0):
    front=max(0,-sin(a)); tooth=(.5+.5*cos(13*a+.4))**.72
    end=1.98+.47*(1-front**3)+.17*tooth
    p=.012+(end-.012)*t
    # shallow sculpted locks, not separate intersecting spheres
    rib=.025*sin(13*a+.5)*sin(pi*t)**2
    return ((1.045+rib+offset)*sin(p)*cos(a),.015+(.86+rib+offset)*sin(p)*sin(a),2.65+(.94+offset)*cos(p))
for i in range(R+1):
    for j in range(N):v.append(hairpoint(2*pi*j/N,i/R))
f=[(i*N+j,(i+1)*N+j,(i+1)*N+(j+1)%N,i*N+(j+1)%N) for i in range(R) for j in range(N)]
f.append(tuple(reversed(range(N)))); f.append(tuple(R*N+j for j in range(N)))
mesh('Continuous sculpted hair',v,f,hair,'head')
# Painted-style highlight patches follow the shell, front and back.
for center in [-2.6,-2.05,-1.5,-.95,-.4,.45,1.0,1.55,2.1,2.65]:
    coords=[(-.19,.49),(-.10,.36),(-.045,.45),(.025,.39),(.17,.48),(.07,.52),(.02,.48),(-.08,.56)]
    mesh('Hair shine',[hairpoint(center+a,t,.009) for a,t in coords],[tuple(range(len(coords)))],high,'head',False)
for s,side in [(-1,'L'),(1,'R')]:
    rings('Ear '+side,[(s*.61,.035,3.05,.34,.24),(s*.70,.035,3.26,.31,.22),(s*.82,.04,3.56,.23,.15),(s*.94,.05,3.83,.12,.075),(s*.98,.05,3.94,.025,.02)],black,'head',24)
    rings('Ear inset '+side,[(s*.66,-.16,3.24,.19,.065),(s*.75,-.145,3.44,.18,.055),(s*.87,-.075,3.69,.105,.035),(s*.95,.015,3.87,.018,.018)],white,'head',24)
tube('Cat mouth',[(-.12,-.741,1.94),(-.065,-.756,1.925),(0,-.766,1.953),(.065,-.756,1.925),(.12,-.741,1.94)],.012,ink,'head')
# Two independent tails start close together at the rear pelvis, BELOW the band.
for s,side in [(-1,'L'),(1,'R')]:
    b='tail.'+side; x=s*1.49; y=.42
    tube('Tail '+side,[(s*.10,.32,.48),(s*.28,.49,.49),(s*.68,.56,.53),(s*1.14,.52,.69),(s*1.43,.44,1.03),(x,y,1.36)],.115,black,b,[1.12,1.1,1,.95,.88,.8])
    rings('Flame '+side,[(x,y,1.29,.09,.08),(x,y,1.39,.20,.15),(x,y,1.57,.27,.20),(x,y,1.74,.24,.18),(x-s*.055,y,1.91,.15,.12),(x-s*.12,y,2.08,.065,.05),(x-s*.08,y,2.20,.009,.009)],white,b,32)
    for sign in [-1,1]:
        pts=[]
        for j in range(33):
            t=j/32; a=2*pi*1.12*t; r=.018+.14*t; dx=r*cos(a); dz=r*sin(a); depth=.202*sqrt(max(.1,1-(dx/.27)**2-(dz/.24)**2)); pts.append((x+dx,y+sign*(depth+.009),1.57+dz))
        tube('Flame spiral '+side,pts,.022,gray,b,[.45+.55*j/32 for j in range(33)])
# Simple pose rig. Rigid bone parenting keeps the stylized pieces editable.
a=bpy.data.armatures.new('Neko rig'); rig=bpy.data.objects.new('Neko rig',a); C.objects.link(rig); bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True); bpy.context.view_layer.objects.active=rig; bpy.ops.object.mode_set(mode='EDIT')
def bone(n,h,t,parent=None):
    b=a.edit_bones.new(n); b.head=h; b.tail=t
    if parent:b.parent=a.edit_bones[parent]
bone('body',(0,0,.45),(0,0,1.5)); bone('head',(0,0,1.5),(0,0,3),'body')
for s,side in [(-1,'L'),(1,'R')]:
    bone('arm.'+side,(s*.42,0,1.48),(s*.76,0,.86),'body'); bone('leg.'+side,(s*.30,0,.55),(s*.32,0,.10),'body'); bone('tail.'+side,(s*.10,.32,.48),(s*1.49,.42,1.36),'body')
bpy.ops.object.mode_set(mode='OBJECT'); rig.show_in_front=True
for o,b in parts:
    world=o.matrix_world.copy(); o.parent=rig; o.parent_type='BONE'; o.parent_bone=b; o.matrix_world=world
# Render setup: Eevee shader-to-RGB + Freestyle silhouette.
scene=bpy.context.scene; scene.render.engine='BLENDER_EEVEE_NEXT'; scene.render.use_freestyle=True
ls=bpy.context.view_layer.freestyle_settings.linesets[0]; ls.linestyle.thickness=1.35; ls.linestyle.color=(.015,.012,.02)
ls.select_silhouette=True; ls.select_border=True; ls.select_crease=False; ls.select_edge_mark=False
scene.world=bpy.data.worlds.new('Toon studio'); scene.world.use_nodes=True; scene.world.node_tree.nodes.get('Background').inputs[0].default_value=(.78,.78,.78,1); scene.world.node_tree.nodes.get('Background').inputs[1].default_value=.35
scene.view_settings.view_transform='Standard'
def aim(o,p):o.rotation_euler=(Vector(p)-o.location).to_track_quat('-Z','Y').to_euler()
for loc,power,size in [((-4,-5,7),850,4),((4,-2,4),240,5),((0,4,6),450,4)]:
    bpy.ops.object.light_add(type='AREA',location=loc); o=move(bpy.context.object); o.data.energy=power; o.data.shape='DISK'; o.data.size=size; aim(o,(0,0,2))
bpy.ops.object.camera_add(location=(0,-12,2.0)); cam=move(bpy.context.object); aim(cam,(0,0,2)); cam.data.type='ORTHO'; cam.data.ortho_scale=4.65; scene.camera=cam
scene.render.resolution_x=1000; scene.render.resolution_y=1000; scene.render.resolution_percentage=100
bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True); bpy.context.view_layer.objects.active=rig
print('Neko Toon V2 created. F12 to render. Pose Mode to pose.')
