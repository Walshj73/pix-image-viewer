# Changelog — pix Image Viewer

All notable changes to this project are documented in this file.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-04-29

### Added — NPY / NumPy Hyperspectral Support

- **`.npy` file format support** — pix can now open NumPy array files directly.  
  Arrays are classified automatically by shape:
  - `(H, W)` → greyscale image
  - `(H, W, 3)` → RGB image
  - `(H, W, 4)` → RGBA image (composited onto dark background)
  - `(H, W, bands)` where bands > 4 → hyperspectral cube

- **NPY hyperspectral panel** — when a hyperspectral `.npy` cube is loaded, a dedicated band-picker panel appears (mirrors the existing ENVI panel) with:
  - R / G / B band spinboxes for false-colour compositing
  - APPLY button
  - "Single band (grey)" checkbox
  - Metadata label showing spatial dimensions, band count, and dtype

- **Slider band scrubbing for NPY cubes** — the bottom slider and ◀ ▶ arrow keys scrub through individual bands when a hyperspectral NPY file is active.

- **NPY filter button** — a new `NPY` button in the format filter strip lets you isolate `.npy` files in a mixed folder.

- **NumPy Array file type** added to the Open Files dialog filter list.

- **`get_npy_info()`** — reads array metadata (`rows`, `cols`, `bands`, `kind`, `dtype`, `shape`) via `mmap_mode="r"` without loading the full array into RAM.

- **`load_npy_preview()`** — builds a false-colour RGB composite from three chosen band indices.

- **`load_npy_band()`** — returns a single greyscale band slice as a PIL image.

- **`load_npy_image()`** — top-level dispatcher: handles all four NPY kinds and feeds into the existing `load_image()` routing pipeline.

---

### Added — Wavelength-Aware False-RGB Estimation

- **`_estimate_rgb_bands(nbands, wavelengths)`** — new module-level helper that replaces the old naive `75% / 50% / 25%` band heuristic for both ENVI and NPY cubes.

  | Input | Behaviour |
  |---|---|
  | ENVI file with `wavelength` metadata | Finds bands closest to **640 nm (R)**, **550 nm (G)**, **470 nm (B)** — perceptually correct natural colour for VNIR sensors |
  | ENVI without metadata, or SWIR/TIR sensor (all three targets collapse to same band) | Falls back to geometric spread across the band range |
  | NPY cube (no wavelength metadata) | Geometric spread fallback |

- ENVI `_setup_envi_panel()` and `load_image()` now both call `_estimate_rgb_bands()` so the initial composite and spinbox defaults are consistent.

- NPY `_setup_npy_panel()` also uses `_estimate_rgb_bands()`.

---

### Added — High-Quality Export

Four new HQ export functions (module-level, re-read from disk, no downscaling):

| Function | Output |
|---|---|
| `_build_hq_npy_band()` | 16-bit greyscale PIL image from a single NPY band |
| `_build_hq_npy_rgb()` | Full-resolution RGB composite from three NPY bands |
| `_build_hq_envi_band()` | 16-bit greyscale PIL image from a single ENVI band |
| `_build_hq_envi_rgb()` | Full-resolution RGB composite from three ENVI bands |

Helper `_save_hq_pil()` handles the save dialog and format routing:
- **16-bit TIFF** (LZW compressed) — default, full bit-depth, lossless
- **PNG** (8-bit lossless)
- **JPEG** (quality 97, lossless subsampling)

Two new buttons appear on both the ENVI and NPY hyperspectral panels:

- **💾 HQ Slice** — saves the currently displayed band as a 16-bit grayscale TIFF at native resolution. Falls back to 8-bit PNG if selected.
- **💾 HQ RGB** — saves the current false-colour composite (using the active R/G/B spinbox values) as a 16-bit RGB TIFF at native resolution.

Output filenames include the source stem and band indices for traceability, e.g. `datacube_rgb_B24-15-7_hq.tif`.

---

### Changed

- **ENVI false-RGB default** — initial band selection on load now uses `_estimate_rgb_bands()` instead of `75% / 50% / 25%`. For sensors with wavelength metadata covering the visible range this produces a natural-colour composite; for others the result is identical to before.

- **NPY false-RGB default** — same change; geometric spread is now calculated via the shared helper.

- **`ALL_EXTENSIONS`** — `.npy` added to the master set used by folder scanning and file dialogs.

- **`_is_rgb_image()`** — extended to return `True` for simple (grey / rgb / rgba) `.npy` files so that colour-transform tools (NEG, HSV, LAB, ADJUST) are available for them. Returns `False` for hyperspectral cubes.

- **`_show_image()`** — extended with a full `elif is_npy` branch that loads metadata, conditionally shows the NPY panel, configures the slider as a band scrubber (hyperspectral) or file scrubber (simple), and populates the info labels.

- **`_prev()` / `_next()` / `_on_slider()`** — all three now dispatch to `_npy_go_band()` when a hyperspectral NPY file is active.

- **`_redraw()`** — uses `_npy_slice_pil` as the display source when in NPY band-scrub mode.

- **Size label** — shows band count and dtype for NPY hyperspectral files (matches existing ENVI behaviour).

---

### Fixed

- ENVI `_setup_envi_panel()` previously had a logic gap where a sensor with fewer than 3 bands would set R = G = B = 0 but still pass `(r, g, b)` as a tuple. The new `_estimate_rgb_bands()` helper handles the degenerate single-band case cleanly.

---
