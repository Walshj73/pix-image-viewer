# PIX — Desktop Image Viewer

> A lightweight desktop image viewer built for research workflows. Handles standard images, camera RAW files, and ENVI hyperspectral cubes — all in one dark-themed GUI.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)

---

## Features

- **Broad format support** — JPEG, PNG, TIFF, BMP, GIF, WebP, PPM/PGM/PBM, and more
- **Camera RAW** — CR2, NEF, ARW, DNG, ORF, RW2, RAF, PEF, SRW via `rawpy`
- **Plain `.raw` files** — auto-detects dimensions or lets you specify width, height, channels, and bit depth manually
- **ENVI hyperspectral cubes** — open `.hdr` files paired with `.bil`, `.bsq`, `.bip`, `.img`, or `.dat` data files; navigate per-band with R/G/B spinboxes or scrub through all bands with a slider; single-band greyscale mode included
- **Lasso crop tool** — draw a freehand selection, then save it as PNG/JPEG or copy it to the clipboard
- **Zoom & pan** — scroll wheel to zoom (5% – 2000%), click-drag to pan; reset with one button
- **Slideshow navigation** — open a folder or a multi-file selection and step through with arrow keys or on-screen controls
- **File-type filter strip** — quickly narrow the active file list to JPG, PNG, TIFF, CAM RAW, .RAW, ENVI, or Other
- **16-bit / float image normalisation** — all high-bit-depth modes are automatically scaled to 8-bit for display
- **Dark theme** — high-contrast `#0D0D0D` background with `#E8FF47` accent, Courier New UI font

---

## Screenshots

*Coming soon — feel free to open a PR with screenshots!*

---

## Requirements

- Python 3.10 or newer
- `Pillow`
- `rawpy`
- `numpy`
- `spectral` *(for ENVI hyperspectral support)*

PIX will attempt to install missing packages automatically on first run. To install manually:

```bash
pip install pillow rawpy numpy spectral
```

For clipboard support on **Linux**, `xclip` must be available:

```bash
sudo apt install xclip
```

---

## Usage

```bash
python pix.py
```

Then use **OPEN FOLDER** to load an entire directory, or **OPEN FILES** to pick individual images.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `←` / `→` | Previous / next image |
| `+` / `-` | Zoom in / out |
| `0` | Reset zoom |
| `Scroll wheel` | Zoom at cursor |

### ENVI hyperspectral cubes

1. Open the `.hdr` header file — PIX will automatically locate the paired data file.
2. The **HYPERSPECTRAL** panel appears at the bottom of the window.
3. Set **R**, **G**, **B** band indices and press **APPLY** for a false-colour composite, or tick **Single band (grey)** to view one band at a time.
4. Use the bottom slider to scrub through all bands sequentially.
5. Wavelength metadata (if present in the header) is shown next to the band controls.

### Lasso crop

1. Click **⬡ LASSO** in the toolbar to activate the tool.
2. Click and drag to draw a freehand polygon around the region of interest.
3. Release the mouse to close the selection — a floating menu appears with:
   - **💾 Save crop…** — save as PNG or JPEG
   - **📋 Copy to clipboard** — copy the masked region as a PNG
   - **✕ Cancel** — clear the selection

### Plain `.raw` files

If `rawpy` and Pillow cannot decode a `.raw` file automatically, a dialog will prompt you to enter the image dimensions, number of channels (1 / 3 / 4), and bit depth (8 or 16). PIX suggests likely dimension combinations based on the file size. Settings are remembered for the rest of the session.

---

## Project Structure

```
pix.py          # Single-file application — everything lives here
```

---

## Dependencies & licences

| Package | Licence |
|---------|---------|
| [Pillow](https://python-pillow.org/) | HPND |
| [rawpy](https://github.com/letmaik/rawpy) | MIT |
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [spectral](https://www.spectralpython.net/) | MIT |

---

## Contributing

This is a personal project, but issues and pull requests are welcome. If you find a format that doesn't load correctly, please open an issue and include a minimal reproduction (file type, size, and any error output).

---

## Licence

MIT — do whatever you like with it.
