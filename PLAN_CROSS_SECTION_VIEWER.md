# Plan — Lens Cross-Section Viewer for FlareSim

## Goal

Add a Nuke panel that draws a 2D cross-section of the currently loaded lens —
the same style of schematic shown on PhotonsToPhotos' *Optical Bench*
(https://photonstophotos.net/GeneralTopics/Lenses/OpticalBench/OpticalBench.htm).

Source data: the existing `.lens` prescription files in `lenses/lens_files/`.
No scraping, no external dependencies beyond what Nuke already ships.

## What exists today (context)

- `FlareSim_LensBrowser.py` — a `nukescripts.PythonPanel` with Nuke knobs
  (folder picker, filter, list, *Load onto selected FlareSim*). Loading writes
  the file path into the `lens_file` knob of the selected `FlareSim` node.
- `menu.py` — registers the `FlareSim` node + calls `FlareSim_LensBrowser.register()`.
- `lenses/lens_files/*.lens` — tabular prescriptions
  (`radius thickness ior abbe semi_ap coating`, with `stop` / `0` special values).

The existing browser panel uses Nuke's knob-based panel API, which has no
custom-draw surface. The cross-section therefore has to live in a **PySide2
widget** registered via `nukescripts.panels.registerWidgetAsPanel`.

## Approach

**Separate panel, v1.** Ship a new "FlareSim Lens Cross-Section" panel alongside
the existing Lens Browser rather than rewriting the browser as Qt. Rationale:

- Zero changes to the existing browser — lower risk, smaller PR.
- Can be dropped next to the browser in a pane and behaves like its own tool.
- Easy to remove/disable if it causes problems.

If we later decide we want a single "Optical Bench-style" combined UI (list on
the left, schematic on the right), that's a v2 refactor.

The new panel watches the selected `FlareSim` node's `lens_file` knob and
redraws on change. It also supports loading an arbitrary `.lens` file directly,
for browsing without a node.

## Architecture

```
flaresim_nuke/
├── FlareSim_LensBrowser.py          (existing, untouched)
├── FlareSim_LensSection.py          (NEW — Nuke registration shim)
├── lens_section/                    (NEW — implementation package)
│   ├── __init__.py
│   ├── parser.py                    # .lens → Lens/Surface dataclasses
│   ├── geometry.py                  # vertices, surface arcs, element polygons
│   ├── viewer.py                    # PySide2 QWidget (paintEvent)
│   └── nuke_bridge.py               # FlareSim-node sync, standalone runner
└── menu.py                          (MODIFIED — one import + register call)
```

Why split implementation into a `lens_section/` package instead of one file:

- `parser.py` is independently testable without Nuke or Qt.
- `geometry.py` is pure math, no GUI — also testable in isolation.
- Keeps the paintEvent file small and focused on rendering.

## Data model

```python
@dataclass
class Surface:
    radius: Optional[float]     # None = flat (INF or 0); signed mm otherwise
    thickness: float            # mm to next surface
    ior: float                  # 1.0 = air
    abbe: float
    semi_aperture: float        # mm
    coating: int
    is_stop: bool               # True only for the `stop` row

@dataclass
class Lens:
    name: str
    focal_length: float
    surfaces: list[Surface]
```

Parser handles:
- `#` comments, blank lines
- Header keys (`name:`, `focal_length:`) before the `surfaces:` line
- Tokens `stop`, `INF`, `0` in the radius column (all map to `radius=None`, but
  `is_stop` only for `stop`)
- Comment lines like `# ... f/2.8` to recover f-number for display (optional)

## Geometry

**Surface vertex positions.** Walk the surface list, cumulative-summing
`thickness`. `z[0] = 0`, `z[i+1] = z[i] + surfaces[i].thickness`.

**Surface profile.** For surface `i` with radius `r` and semi-aperture `h`,
clamped height `h_eff = min(h, |r|·0.9999)` to avoid sqrt-of-negative at the
pole. Sample `y ∈ [-h_eff, +h_eff]`, compute

```
z(y) = z_i + r − sign(r)·sqrt(r² − y²)
```

Flat surfaces (`r is None`) → vertical segment from `(z_i, -h)` to `(z_i, +h)`.

**Glass elements.** For each `i` where `surfaces[i].ior != 1.0`, a glass region
occupies the space between surface `i` (front) and surface `i+1` (back).
Cemented doublets appear as two adjacent non-air regions sharing a surface —
drawn as two polygons with the shared surface automatically acting as the
cement line. The `stop` surface is skipped as a front/back of any element.

**Element polygon.** Front arc bottom→top, straight edge to back-arc top, back
arc top→bottom, close to front-arc bottom. When front and back semi-apertures
differ, those top/bottom straight edges are non-degenerate and render as the
element's outer rim — same as Optical Bench.

**Aperture stop marker.** Two short vertical ticks above/below the axis at
`z = z_stop`, from `±h` to `±1.3·h`.

## Rendering (PySide2)

- `LensCrossSection(QWidget)`:
  - `set_lens(Lens)` stores the model and calls `update()`.
  - `paintEvent`:
    1. Compute bounding box across all surface sample points.
    2. Fit-to-view transform (preserve aspect, symmetric around the optical
       axis, ~20 px margin).
    3. Draw optical axis (dashed grey).
    4. For each glass element, build `QPainterPath` from tessellated arcs
       (~40 steps/arc), fill with semi-transparent blue, stroke dark grey.
    5. Draw aperture stop ticks.
    6. Top-left label: `"<name>   f=<focal_length>mm"`.
  - Antialiased; redraws on resize (Qt handles this automatically via `update()`).

- `LensSectionPanel(QWidget)`:
  - Path row (line edit + Browse button) for ad-hoc loading.
  - "Follow selected FlareSim node" checkbox (default on).
  - `LensCrossSection` fills the rest.

## Nuke integration

- `FlareSim_LensSection.py` mirrors `FlareSim_LensBrowser.py`:
  ```python
  def register():
      nukescripts.panels.registerWidgetAsPanel(
          'lens_section.viewer.LensSectionPanel',
          'FlareSim Lens Cross-Section',
          'uk.co.flaresim.lenssection',
      )
      nuke.menu('Pane').addCommand('FlareSim Lens Cross-Section', ...)
  ```
- `menu.py` gets one new `try/except import + register()` block — same shape
  as the existing browser registration.

**Node sync.** When "Follow selected FlareSim" is on, the panel polls on a
`QTimer` (500 ms) for the selected node's `lens_file` value. This is simpler
and more robust than hooking `onKnobChanged` callbacks globally. The poll
cost is negligible (string compare).

## Standalone dev loop

`lens_section/nuke_bridge.py` exposes a `__main__` that creates a
`QApplication` and shows a `LensSectionPanel` directly — so we can iterate on
rendering without restarting Nuke:

```
python -m lens_section lenses/lens_files/AF_Nikkor_85mm_F1.4D_IF.lens
```

Requires `PySide2` in the local env. Nuke's bundled PySide2 isn't on the system
path, so this uses whatever PySide2 is installed outside Nuke (pip install if
needed). Purely a dev convenience — not shipped to end users.

## Compatibility

- **PySide2 vs PySide6.** Nuke 13–15 ship PySide2; Nuke 16+ may ship PySide6.
  Use a compat shim at the top of `viewer.py`:
  ```python
  try:
      from PySide2 import QtCore, QtGui, QtWidgets
  except ImportError:
      from PySide6 import QtCore, QtGui, QtWidgets
  ```
- **Python 3 only.** All target Nuke versions (13+) are Python 3, matching
  the existing codebase.

## Out of scope for v1

Deliberately deferred to keep v1 small:

- Ray-path overlay (entrance-pupil rays traced through the lens).
- Highlighting the two surfaces selected in the FlareSim "Pairs" tab.
- Focus / zoom group animation (would require a grouped lens format).
- Interactive measurement (click two surfaces, show distance).
- Dark-mode palette / styling to match Nuke's theme — v1 uses a neutral
  light palette.

## Step-by-step build order

1. **Parser** (`lens_section/parser.py`) — hand-test with 3–4 `.lens` files
   (doublegauss, 85mm Nikkor, a zoom). No Qt required.
2. **Geometry** (`lens_section/geometry.py`) — unit test on the parsed lenses;
   verify element count matches visual inspection of a known design.
3. **Renderer + standalone runner** (`viewer.py` + `__main__.py`) — iterate
   outside Nuke until the doublegauss looks right.
4. **Nuke panel shim** (`FlareSim_LensSection.py`) + `menu.py` hook — launch
   Nuke, verify panel opens from the Pane menu.
5. **Node sync** — QTimer poll of selected `FlareSim.lens_file`.
6. **Manual QA** — sweep through ~10 lenses including a zoom, a cemented
   triplet, a mirror lens (check no-crash), and an f/0.95 design (large
   semi-apertures).

## Risks / open questions

- **Semi-aperture values larger than |radius|** appear in some files in
  `lens_files/` (e.g., the AF Nikkor 85/1.4 header values look unusual). The
  clamping logic above prevents crashes but the rendered arc may not match the
  actual clear aperture. Worth spot-checking a few designs against Optical
  Bench to confirm the prescriptions line up.
- **QTimer polling granularity.** 500 ms feels snappy; can drop to 250 ms if
  sluggish. Knob-changed callbacks would be zero-latency but are more invasive
  to install/uninstall cleanly — revisit only if polling proves inadequate.
- **Mirror lenses.** Reflective surfaces aren't distinguished in the current
  `.lens` format (no column for it). They'll render as if they were refracting
  glass. Acceptable for v1 since FlareSim itself treats surfaces purely as
  refractive except at the ghost-pair bounces.
