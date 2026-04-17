# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FlareSim is a CUDA-accelerated Nuke plugin that ray-traces physically-correct lens flares from real `.lens` prescription files. The user-facing behaviour, lens file format, and all UI knobs are fully documented in [README.md](README.md) — read it before answering questions about behaviour, parameters, or output channels.

## Build

Targets Nuke 13–17 on Windows and Linux. Each Nuke version needs its own binary because the NDK ABI changes between versions.

| Task | Command |
|------|---------|
| Build all versions (Windows) | `./build_all.ps1` |
| Build one version (Windows) | `./build_all.ps1 -Versions 16` |
| Build all versions (Linux, host toolchain) | `./build_all.sh` |
| Build all versions (Linux, ASWF Docker — portable) | `./docker_build_all.sh` |
| Package release zips | `./package_release.ps1 -Version X.Y.Z` / `./package_release.sh --version X.Y.Z` |
| Single CMake configure | `cmake -S . -B build -DNDK_ROOT=<nuke>/include -DNUKE_LIB_DIR=<nuke>` |

Output lands in `dist/nuke<N>/FlareSim.{dll,so}`. Release zips land in `release_packages/`.

There are **no automated tests**. Validation is manual: load the plugin in Nuke, apply it to an image, and inspect the `flare.rgb` / `source.rgb` / `haze.rgb` / `starburst.rgb` channels.

### Load-bearing build constraints (do not change without understanding why)

- **MSVC runtime must be `/MD` (`MultiThreadedDLL`)** — Nuke links `/MD`; mixing with `/MT` causes heap corruption. Set in [CMakeLists.txt](CMakeLists.txt).
- **Nuke 13 requires the old libstdc++ ABI** — `_GLIBCXX_USE_CXX11_ABI=0`. Nuke 14+ uses the new ABI (`=1`). Wrong ABI compiles and links but crashes at runtime. Handled per-version in [build_all.sh](build_all.sh) and [docker_build_all.sh](docker_build_all.sh).
- **Nuke 17 requires C++20**; Nuke 13–16 use C++17. Driven by VFX Reference Platform year.
- **CUDA runtime linkage**: static on Linux (no cudart dependency for end users), shared on Windows (avoids CRT conflicts with Nuke's `/MD`).
- **`sm_120` (Blackwell) requires CUDA 12.8+**, which only the Rocky 8-based ASWF images ship. CentOS 7 / Nuke 14 is capped at CUDA 12.4 → no Blackwell. See [docker/Dockerfile](docker/Dockerfile).
- **Output binary name must be exactly `FlareSim`** with no `lib` prefix — Nuke looks up plugin classes by filename.

## Architecture

Two independent layers that communicate via a knob (`lens_file`) on the `FlareSim` node:

### Native plugin ([src/](src/))

Classic Nuke `Iop` with one unusual design decision: **all simulation work happens inside `engine()`, not `_validate()`**. See [src/FlareSim.cpp](src/FlareSim.cpp) top-of-file comment.

- `_validate()` only configures channels/format and sets a `needs_compute_` flag. It cannot touch input pixels because Nuke's background playback cacher calls `_validate()` before the upstream graph has rendered.
- `engine()` takes a mutex on the first scanline request, runs source detection + CUDA kernel + post-process into full-frame buffers, then serves all subsequent scanlines from those buffers. This is why the UI appears to freeze briefly then paint the whole frame at once (also documented in README "Render behaviour").

Pipeline (all in [src/ghost_cuda.cu](src/ghost_cuda.cu) and [src/trace.cpp](src/trace.cpp)):

1. [src/lens.cpp](src/lens.cpp) — load `.lens` prescription → `LensSystem`.
2. [src/ghost.cpp](src/ghost.cpp) — enumerate C(N,2) ghost bounce pairs, pre-filter by Fresnel-reflectance probe ray, estimate per-pair area-boost.
3. Source detection — scan input image, threshold by luma, cap by `Max Sources`, emit `BrightPixel[]`.
4. [src/ghost_cuda.cu](src/ghost_cuda.cu) — for each (source, pair, wavelength, pupil sample) quadruple, trace ray through lens (refract at each surface, reflect at the two chosen surfaces), splat result onto sensor buffer. Pupil sampling = grid / stratified / Halton. Aperture mask = N-polygon or disc.
5. [src/starburst.cpp](src/starburst.cpp) — FFT the aperture mask, square magnitude → diffraction spikes.
6. Host-side post (box blur for ghost softening; wide blur for haze) in [src/FlareSim.cpp](src/FlareSim.cpp).

Output is written to named channel sets (`flare.*`, `source.*`, `haze.*`, `starburst.*`) regardless of Output Mode; Output Mode only controls what ends up in the main `rgba`.

### Python UI panels

Two `nukescripts.panels` panels registered from [menu.py](menu.py):

- [FlareSim_LensBrowser.py](FlareSim_LensBrowser.py) — knob-based panel. Lists `.lens` files in a folder, loads the chosen path onto the selected `FlareSim` node's `lens_file` knob.
- [FlareSim_LensSection.py](FlareSim_LensSection.py) + [lens_section/](lens_section/) — PySide2/6 widget that renders a 2D cross-section of the currently loaded lens (element polygons from surface arcs, stop tick marks). Follows the selected `FlareSim` node via a 500 ms `QTimer` poll of `lens_file`. See [PLAN_CROSS_SECTION_VIEWER.md](PLAN_CROSS_SECTION_VIEWER.md) for the design rationale.

The lens-section package is runnable **outside Nuke** for rendering iteration:

```
python -m lens_section lenses/lens_files/<file>.lens
```

Requires a system PySide2 or PySide6. The parser and geometry modules are pure Python with no Nuke/Qt imports, so they can be used in tests or scripts.

### PySide2 / PySide6 compatibility

Nuke 13–15 ship PySide2; Nuke 16+ may ship PySide6. The viewer uses a try/except import shim — when editing [lens_section/viewer.py](lens_section/viewer.py), keep it working with both.

## Lens files

- **Format** documented in [README.md](README.md) §"Lens files".
- **Library**: ~1300 `.lens` files in [lenses/lens_files/](lenses/lens_files/) covering Nikkor, Canon, Zeiss/ARRI cinema, Cooke, mirror lenses, zooms.
- **Converters**: [lenses/convert_p2p.py](lenses/convert_p2p.py) (PhotonsToPhotos Optical Bench), [lenses/convert_ob.py](lenses/convert_ob.py). Run standalone; not imported by the plugin.
- **Special tokens in the radius column**: `stop` (aperture stop), `INF` / `0` (flat surface).

## Installation quirks worth knowing

End users sometimes put `nuke.pluginAddPath()` in `menu.py` instead of `init.py` — this fails silently because `menu.py` runs after Nuke has finished its `menu.py` scan. Always `init.py`. See [INSTALL.md](INSTALL.md) troubleshooting.
