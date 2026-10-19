"""Original ship pilot, built/exported by Blender CLI in a fresh factory scene.

No external assets, random geometry, textures or gameplay data. Blender Z is up;
glTF export maps it to Three Y. X remains the original edge's length axis.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

import bpy


class MeshParts:
    def __init__(self):
        self.vertices, self.faces = [], []

    def part(self, vertices, faces):
        offset = len(self.vertices)
        self.vertices.extend(vertices)
        self.faces.extend(tuple(offset + index for index in face) for face in faces)

    def box(self, center, size):
        x, y, z = center
        a, b, c = (v / 2 for v in size)
        self.part([(x+dx*a, y+dy*b, z+dz*c) for dx, dy, dz in
            [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]],
            [(3,2,1,0),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)])

    def rings(self, rings, cap_bottom=True, cap_top=True):
        n = len(rings[0])
        vertices = [vertex for ring in rings for vertex in ring]
        faces = [(j*n+i, j*n+(i+1)%n, (j+1)*n+(i+1)%n, (j+1)*n+i)
            for j in range(len(rings)-1) for i in range(n)]
        if cap_bottom:
            faces.append(tuple(reversed(range(n))))
        if cap_top:
            faces.append(tuple((len(rings)-1)*n+i for i in range(n)))
        self.part(vertices, faces)


def material(name, hex_color, roughness):
    values = [int(hex_color[i:i+2], 16)/255 for i in (0, 2, 4)]
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*linear, 1)
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = 0
    mat.diffuse_color = (*linear, 1)
    return mat


def build():
    # Only the new --factory-startup CLI process is touched; never the user's GUI scene.
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1
    bpy.context.preferences.filepaths.save_version = 0
    root = bpy.data.objects.new('ShipPilot', None)
    bpy.context.scene.collection.objects.link(root)
    wood, owner, canvas = MeshParts(), MeshParts(), MeshParts()
    outline = [(-.40,-.09),(-.25,-.14),(.22,-.12),(.40,0),(.22,.12),(-.25,.14),(-.40,.09)]

    def ring(sx, sy, z):
        return [(x*sx, y*sy, z) for x, y in outline]

    # Shallow faceted hull, inset deck, and continuous colored gunwale.
    wood.rings([ring(.76,.56,0), ring(.96,.83,.035), ring(1,1,.125)])
    wood.part(ring(.91,.75,.126), [tuple(range(len(outline)))])
    owner.rings([ring(1,1,.105), ring(1,1,.144)], cap_bottom=False, cap_top=False)
    outer, inner = ring(1,1,.144), ring(.91,.75,.144)
    n = len(outline)
    owner.part(outer+inner, [(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)])
    owner.box((-.245,0,.141),(.035,.19,.025))
    owner.box((.15,0,.141),(.028,.16,.025))
    wood.box((-.08,0,.151),(.052,.045,.038))

    # Eight-sided mast and one restrained boom; no decorative ropes/rigging.
    pole = [[(-.08+math.cos(i*math.tau/8)*.013, math.sin(i*math.tau/8)*.013, z)
        for i in range(8)] for z in (.15,.53)]
    wood.rings(pole)
    wood.box((.075,-.014,.218),(.35,.018,.018))

    # Solid, lightly billowed sail: same neutral canvas from either camera side.
    rows = [(.227,-.078,.25),(.36,-.078,.23),(.505,-.078,.13)]
    front = []
    for row, (z,left,right) in enumerate(rows):
        for col in range(3):
            t = col/2
            front.append((left+(right-left)*t, -.012-.048*math.sin(t*math.pi)*math.sin((row+1)*math.pi/4), z))
    back = [(x,y+.008,z) for x,y,z in front]
    faces=[]
    for row in range(2):
        for col in range(2):
            a=row*3+col
            faces.extend([(a,a+1,a+4,a+3),(a+12,a+13,a+10,a+9)])
    boundary=[0,1,2,5,8,7,6,3]
    faces.extend((a,b,b+9,a+9) for a,b in zip(boundary,boundary[1:]+boundary[:1]))
    canvas.part(front+back,faces)
    # Ownership remains legible from the top even when the hull is foreshortened.
    owner.part([(-.08,-.008,.535),(.055,-.008,.518),(-.08,-.008,.488),
                (-.08,.002,.535),(.055,.002,.518),(-.08,.002,.488)],
        [(0,1,2),(5,4,3),(0,3,4,1),(1,4,5,2),(2,5,3,0)])

    materials = [('HullWood',wood,'805331',.80),('PlayerColor',owner,'cc4c48',.76),
                  ('CanvasIvory',canvas,'f4e7ca',.88)]
    objects=[]
    for name, parts, color, roughness in materials:
        mesh=bpy.data.meshes.new(name)
        mesh.from_pydata(parts.vertices,[],parts.faces)
        mesh.update()
        mesh.calc_loop_triangles()
        obj=bpy.data.objects.new(name,mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.parent=root
        mesh.materials.append(material(name,color,roughness))
        objects.append(obj)
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active=root
    bpy.context.view_layer.update()
    return objects


def main(args):
    output=Path(args.output_root).resolve()
    source=output/'docs/design/references/blender/ship_pilot.blend'
    glb=output/'web/public/models/pieces/ship-pilot.glb'
    metadata=output/'docs/design/references/blender/ship-pilot.json'
    for path in (source,glb,metadata):
        path.parent.mkdir(parents=True,exist_ok=True)
    objects=build()
    triangles=sum(len(obj.data.loop_triangles) for obj in objects)
    assert len(objects)==3 and triangles <= 500
    bpy.ops.wm.save_as_mainfile(filepath=str(source),check_existing=False)
    bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,
        export_yup=True,export_normals=True,export_materials='EXPORT',export_animations=False,
        export_cameras=False,export_lights=False,export_extras=False,export_apply=False)
    points=[(v.co.x,v.co.z,-v.co.y) for obj in objects for v in obj.data.vertices]
    result={'success':True,'blender_version':bpy.app.version_string,'asset':'ship-pilot',
        'source':'tools/blender/export_ship_pilot.py','mesh_count':len(objects),
        'materials':[obj.data.materials[0].name for obj in objects],
        'triangles':triangles,'vertices':sum(len(obj.data.vertices) for obj in objects),
        'three_bounds':{'min':[min(p[i] for p in points) for i in range(3)],
                        'max':[max(p[i] for p in points) for i in range(3)]},
        'coordinate_contract':'glTF Y-up; local X length; pivot (0,0,0); runtime X scale=ship.length*.88',
        'textures':0,'animations':0,'glb_bytes':glb.stat().st_size,
        'glb_sha256':hashlib.sha256(glb.read_bytes()).hexdigest()}
    assert result['glb_bytes'] < 80000
    # Reload the exported bytes in this disposable CLI process, never the GUI scene.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    imported=[obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    assert len(imported)==3 and {mat.name for obj in imported for mat in obj.data.materials}==set(result['materials'])
    for obj in imported:
        obj.data.calc_loop_triangles()
    assert sum(len(obj.data.loop_triangles) for obj in imported)==triangles
    assert not any(obj.type in ('CAMERA','LIGHT') for obj in bpy.context.scene.objects)
    restored=[obj.matrix_world @ vertex.co for obj in imported for vertex in obj.data.vertices]
    restored_three=[(v.x,v.z,-v.y) for v in restored]
    for i in range(3):
        assert abs(min(p[i] for p in restored_three)-result['three_bounds']['min'][i])<1e-5
        assert abs(max(p[i] for p in restored_three)-result['three_bounds']['max'][i])<1e-5
    result['glb_reload_verified']=True
    metadata.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-root',default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--status-file',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    try:
        result=main(args)
    except Exception:
        result={'success':False,'error':traceback.format_exc()}
        raise
    finally:
        Path(args.status_file).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
