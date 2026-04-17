from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Surface:
    radius: Optional[float]
    thickness: float
    ior: float
    abbe: float
    semi_aperture: float
    coating: int = 0
    is_stop: bool = False


@dataclass
class Lens:
    name: str = ""
    focal_length: float = 0.0
    f_number: float = 0.0
    surfaces: List[Surface] = field(default_factory=list)


def _parse_radius(token: str):
    t = token.strip()
    low = t.lower()
    if low == "stop":
        return None, True
    if low in ("inf", "infinity"):
        return None, False
    value = float(t)
    if value == 0.0:
        return None, False
    return value, False


def parse_lens_file(path: str) -> Lens:
    import os
    import re

    lens = Lens(name=os.path.splitext(os.path.basename(path))[0])
    in_surfaces = False
    f_num_re = re.compile(r"\bf/(\d+(?:\.\d+)?)")

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            stripped = raw.strip()

            if not in_surfaces and lens.f_number == 0.0 and stripped.startswith("#"):
                m = f_num_re.search(stripped)
                if m:
                    try:
                        lens.f_number = float(m.group(1))
                    except ValueError:
                        pass

            line = raw.split("#", 1)[0].strip()
            if not line:
                continue

            if line.lower().startswith("surfaces:"):
                in_surfaces = True
                continue

            if not in_surfaces:
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip().lower()
                    value = value.strip()
                    if key == "name" and value:
                        lens.name = value
                    elif key in ("focal_length", "focal length"):
                        try:
                            lens.focal_length = float(value)
                        except ValueError:
                            pass
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            radius, is_stop = _parse_radius(parts[0])
            coating = int(float(parts[5])) if len(parts) > 5 else 0

            lens.surfaces.append(
                Surface(
                    radius=radius,
                    thickness=float(parts[1]),
                    ior=float(parts[2]),
                    abbe=float(parts[3]),
                    semi_aperture=float(parts[4]),
                    coating=coating,
                    is_stop=is_stop,
                )
            )

    return lens
