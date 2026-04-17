import math
from typing import List, Tuple

from .parser import Lens, Surface


AIR_TOL = 1e-3


def surface_vertices(lens: Lens) -> List[float]:
    z = 0.0
    out = []
    for s in lens.surfaces:
        out.append(z)
        z += s.thickness
    return out


def surface_profile(surface: Surface, z_vertex: float, steps: int = 48) -> List[Tuple[float, float]]:
    h = surface.semi_aperture
    r = surface.radius

    if r is None:
        return [(z_vertex, -h), (z_vertex, h)]

    h_eff = min(h, abs(r) * 0.99999)
    sign = math.copysign(1.0, r)
    points = []
    for i in range(steps + 1):
        y = -h_eff + (2.0 * h_eff) * (i / steps)
        disc = max(r * r - y * y, 0.0)
        z = z_vertex + r - sign * math.sqrt(disc)
        points.append((z, y))

    if h > h_eff:
        points[0] = (points[0][0], -h)
        points[-1] = (points[-1][0], h)

    return points


def glass_spans(lens: Lens) -> List[Tuple[int, int]]:
    spans = []
    surfaces = lens.surfaces
    for i in range(len(surfaces) - 1):
        if abs(surfaces[i].ior - 1.0) > AIR_TOL and not surfaces[i].is_stop and not surfaces[i + 1].is_stop:
            spans.append((i, i + 1))
    return spans


def bounding_box(lens: Lens) -> Tuple[float, float, float]:
    vertices = surface_vertices(lens)
    min_z = math.inf
    max_z = -math.inf
    max_h = 0.0
    for i, s in enumerate(lens.surfaces):
        for z, y in surface_profile(s, vertices[i], steps=16):
            if z < min_z:
                min_z = z
            if z > max_z:
                max_z = z
            if abs(y) > max_h:
                max_h = abs(y)
    if not math.isfinite(min_z):
        return 0.0, 1.0, 1.0
    return min_z, max_z, max_h
