"""Read-only, positional-weld topology checks for Blender source and GLB imports.

Welding is for inspection only: never merge source vertices or flat normals.
Self intersections are not tested. Open component intent is validated separately.
"""
from collections import defaultdict
import math


def inspect_mesh(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    positions = [tuple(vertex.co) for vertex in mesh.vertices]
    weld, ids = {}, []
    for point in positions:
        key = tuple(round(value, 6) for value in point)
        ids.append(weld.setdefault(key, len(weld)))
    edges = defaultdict(list)
    adjacency = [set() for _ in mesh.polygons]
    for face in mesh.polygons:
        vertices = [ids[index] for index in face.vertices]
        for a, b in zip(vertices, vertices[1:] + vertices[:1]):
            edges[tuple(sorted((a, b)))].append((face.index, a, b))
    for uses in edges.values():
        for face, _, _ in uses:
            adjacency[face].update(other for other, _, _ in uses if other != face)
    unseen, components = set(range(len(mesh.polygons))), []
    while unseen:
        pending, faces = [min(unseen)], set()
        while pending:
            face = pending.pop()
            if face in faces:
                continue
            faces.add(face)
            pending.extend(adjacency[face] - faces)
        unseen.difference_update(faces)
        component_edges = [uses for uses in edges.values() if uses[0][0] in faces]
        closed = all(len(uses) == 2 for uses in component_edges)
        consistent = all(len(uses) != 2 or uses[0][1:] == uses[1][1:][::-1] for uses in component_edges)
        volume = sum(mesh.vertices[t.vertices[0]].co.dot(
            mesh.vertices[t.vertices[1]].co.cross(mesh.vertices[t.vertices[2]].co)) / 6
            for t in mesh.loop_triangles if t.polygon_index in faces)
        components.append({'faces': len(faces), 'closed': closed, 'consistent_winding': consistent,
                           'signed_volume': volume})
    degenerate = sum((mesh.vertices[t.vertices[1]].co - mesh.vertices[t.vertices[0]].co).cross(
        mesh.vertices[t.vertices[2]].co - mesh.vertices[t.vertices[0]].co).length < 1e-12
        for t in mesh.loop_triangles)
    normals = [face.normal for face in mesh.polygons] + [vertex.normal for vertex in mesh.vertices]
    return {'vertices': len(mesh.vertices), 'welded_positions': len(weld), 'faces': len(mesh.polygons),
            'triangles': len(mesh.loop_triangles), 'boundary_edges': sum(len(uses) == 1 for uses in edges.values()),
            'non_manifold_shared_edges': sum(len(uses) > 2 for uses in edges.values()),
            'inconsistent_edges': sum(len(uses) == 2 and uses[0][1:] != uses[1][1:][::-1] for uses in edges.values()),
            'degenerate_triangles': degenerate,
            'invalid_normals': sum(not all(math.isfinite(value) for value in normal) or abs(normal.length - 1) > 1e-4 for normal in normals),
            'components': components}


def inspect_objects(objects):
    return {obj.name: inspect_mesh(obj) for obj in sorted(objects, key=lambda obj: obj.name) if obj.type == 'MESH'}


def validate_hardened(topology):
    assert set(topology) == {'HullWood', 'PlayerColor', 'CanvasIvory'}
    for name, info in topology.items():
        for field in ['non_manifold_shared_edges', 'inconsistent_edges', 'degenerate_triangles', 'invalid_normals']:
            assert info[field] == 0, (name, field, info[field])
        # HullWood contains a deliberately thin inset top-facing deck overlay.
        assert info['boundary_edges'] == (7 if name == 'HullWood' else 0), (name, info['boundary_edges'])
        for component in info['components']:
            if component['closed']:
                assert component['consistent_winding'] and component['signed_volume'] > 1e-10, (name, component)
