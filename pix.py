"""
Universal Image Viewer — Slideshow GUI
Supports: .jpg .jpeg .png .tiff .tif .bmp .gif .webp .ico .ppm .pgm
          .raw .cr2 .nef .arw .dng .orf .rw2 .raf .pef .srw
          ENVI hyperspectral cubes (.hdr + .bil / .bsq / .bip / .img / .dat / .raw)
          NumPy arrays (.npy) — 2-D greyscale, 3-D (H×W×C) RGB/RGBA,
                                or hyperspectral cubes (H×W×bands, bands>4)
Requires: pip install rawpy pillow numpy spectral
"""

import os
import sys
import math
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

try:
    import rawpy
    import numpy as np
    from PIL import Image, ImageTk
except ImportError:
    print("Installing required packages...")
    os.system(f"{sys.executable} -m pip install rawpy Pillow numpy")
    import rawpy
    import numpy as np
    from PIL import Image, ImageTk

try:
    import spectral
    import spectral.io.envi as envi
    SPECTRAL_AVAILABLE = True
except ImportError:
    os.system(f"{sys.executable} -m pip install spectral")
    try:
        import spectral
        import spectral.io.envi as envi
        SPECTRAL_AVAILABLE = True
    except ImportError:
        SPECTRAL_AVAILABLE = False


# ── Supported extensions ──────────────────────────────────────────────────────

PILLOW_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".bmp", ".gif", ".webp", ".ico", ".ppm", ".pgm", ".pbm",
}
CAMERA_RAW_EXTENSIONS = {
    ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf", ".pef", ".srw",
}
PLAIN_RAW_EXTENSIONS = {".raw"}
ENVI_HEADER_EXTENSIONS = {".hdr"}          # user opens the .hdr file
ENVI_DATA_EXTENSIONS   = {".bil", ".bsq", ".bip", ".img", ".dat"}
NPY_EXTENSIONS         = {".npy"}          # NumPy array files

ALL_EXTENSIONS = (PILLOW_EXTENSIONS | CAMERA_RAW_EXTENSIONS |
                  PLAIN_RAW_EXTENSIONS | ENVI_HEADER_EXTENSIONS |
                  NPY_EXTENSIONS)

# Stored plain-RAW settings so user only enters them once per session.
_plain_raw_settings: dict = {}


# ── Dimension guesser for plain .raw files ────────────────────────────────────

def _guess_dimensions(file_size: int) -> list[tuple]:
    guesses = []
    for bits in (8, 16):
        bytes_pp = bits // 8
        for channels in (1, 3):
            total_pixels = file_size // (bytes_pp * channels)
            if total_pixels < 1:
                continue
            for ratio in ((4, 3), (16, 9), (3, 2), (1, 1)):
                wr, hr = ratio
                w = math.sqrt(total_pixels * wr / hr)
                h = total_pixels / w
                w, h = int(round(w)), int(round(h))
                if w * h == total_pixels and w > 0 and h > 0:
                    guesses.append((w, h, channels, bits))
    return guesses


# ── Plain-RAW parameter dialog ────────────────────────────────────────────────

class PlainRawDialog(tk.Toplevel):
    def __init__(self, parent, filepath: str, file_size: int):
        super().__init__(parent)
        self.title("Plain RAW — image parameters")
        self.configure(bg=parent.BG)
        self.resizable(False, False)
        self.result = None

        bg, fg, surf, accent = parent.BG, parent.FG, parent.SURFACE, parent.ACCENT
        pad = dict(padx=12, pady=6)

        tk.Label(self, text="Plain RAW file detected",
                 font=("Courier New", 13, "bold"), bg=bg, fg=accent
                 ).grid(row=0, column=0, columnspan=2, pady=(14, 2))
        tk.Label(self, text=f"{Path(filepath).name}  ({file_size:,} bytes)",
                 font=("Courier New", 8), bg=bg, fg=parent.FG_DIM
                 ).grid(row=1, column=0, columnspan=2)

        guesses = _guess_dimensions(file_size)
        if guesses:
            tk.Label(self, text="Possible dimensions (click to fill):",
                     font=("Courier New", 9), bg=bg, fg=fg
                     ).grid(row=2, column=0, columnspan=2, pady=(10, 2))
            gf = tk.Frame(self, bg=bg)
            gf.grid(row=3, column=0, columnspan=2, pady=(0, 8))
            for i, (w, h, ch, bits) in enumerate(guesses[:6]):
                tk.Button(gf, text=f"{w}×{h}  ch={ch}  {bits}bit",
                          font=("Courier New", 8), bg=surf, fg=fg,
                          relief="flat", cursor="hand2",
                          activebackground=accent, activeforeground=bg,
                          command=lambda w=w, h=h, ch=ch, b=bits: self._fill(w, h, ch, b)
                          ).grid(row=i // 3, column=i % 3, padx=4, pady=2, sticky="ew")

        ff = tk.Frame(self, bg=bg)
        ff.grid(row=4, column=0, columnspan=2, **pad)

        def field(label, row, default=""):
            tk.Label(ff, text=label, font=("Courier New", 10),
                     bg=bg, fg=fg, width=10, anchor="e").grid(row=row, column=0, **pad)
            var = tk.StringVar(value=str(default))
            tk.Entry(ff, textvariable=var, font=("Courier New", 10),
                     bg=surf, fg=fg, insertbackground=accent,
                     relief="flat", width=10).grid(row=row, column=1, **pad)
            return var

        self._w    = field("Width",     0)
        self._h    = field("Height",    1)
        self._chan  = field("Channels",  2, 3)
        self._bits  = field("Bit depth", 3, 8)

        bs = dict(bg=surf, fg=fg, relief="flat", font=("Courier New", 10),
                  cursor="hand2", activebackground=accent, activeforeground=bg,
                  padx=14, pady=6, bd=0)
        bf = tk.Frame(self, bg=bg)
        bf.grid(row=5, column=0, columnspan=2, pady=12)
        tk.Button(bf, text="OK",     command=self._ok,     **bs).pack(side="left", padx=6)
        tk.Button(bf, text="Cancel", command=self.destroy, **bs).pack(side="left", padx=6)

        self.grab_set()
        self.wait_window()

    def _fill(self, w, h, ch, bits):
        self._w.set(str(w)); self._h.set(str(h))
        self._chan.set(str(ch)); self._bits.set(str(bits))

    def _ok(self):
        try:
            w, h = int(self._w.get()), int(self._h.get())
            ch, bits = int(self._chan.get()), int(self._bits.get())
            assert w > 0 and h > 0 and ch in (1, 3, 4) and bits in (8, 16)
            self.result = (w, h, ch, bits)
            self.destroy()
        except Exception:
            messagebox.showerror("Invalid input",
                                 "Channels: 1 (grey), 3 (RGB), 4 (RGBA)\nBit depth: 8 or 16")


# ── Image loading ─────────────────────────────────────────────────────────────

def _load_plain_raw(filepath: str, w: int, h: int, ch: int, bits: int) -> Image.Image:
    dtype = np.uint8 if bits == 8 else np.uint16
    data  = np.fromfile(filepath, dtype=dtype)
    expected = w * h * ch
    if data.size < expected:
        raise ValueError(f"File too small: got {data.size} values, need {expected}")
    data = data[:expected].reshape((h, w, ch) if ch > 1 else (h, w))
    if bits == 16:
        data = (data >> 8).astype(np.uint8)
    if ch == 1:
        return Image.fromarray(data, "L").convert("RGB")
    if ch == 4:
        return Image.fromarray(data, "RGBA").convert("RGB")
    return Image.fromarray(data, "RGB")


def _norm_band(arr: np.ndarray) -> np.ndarray:
    """Normalise a 2-D float array to uint8, ignoring NaN/Inf."""
    arr = arr.astype(np.float32)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = arr.min(), arr.max()
    if hi > lo:
        arr = (arr - lo) / (hi - lo) * 255.0
    return arr.astype(np.uint8)


# ── NPY / NumPy array support ─────────────────────────────────────────────────

def _npy_kind(arr: np.ndarray) -> str:
    """
    Classify an NPY array shape:
      'grey'   — 2-D (H, W)
      'rgb'    — 3-D (H, W, 3)
      'rgba'   — 3-D (H, W, 4)
      'hyper'  — 3-D (H, W, bands) where bands > 4
    Raises ValueError for anything else.
    """
    if arr.ndim == 2:
        return "grey"
    if arr.ndim == 3:
        bands = arr.shape[2]
        if bands == 1:
            return "grey"
        if bands == 3:
            return "rgb"
        if bands == 4:
            return "rgba"
        return "hyper"
    raise ValueError(
        f"Cannot display NPY array with shape {arr.shape}. "
        "Expected 2-D (H,W) or 3-D (H,W,C)."
    )


def get_npy_info(filepath: str) -> dict:
    """Return metadata dict for an NPY file without loading the full array."""
    arr = np.load(filepath, mmap_mode="r")
    kind = _npy_kind(arr)
    nbands = arr.shape[2] if arr.ndim == 3 else 1
    return {
        "rows":   arr.shape[0],
        "cols":   arr.shape[1],
        "bands":  nbands,
        "kind":   kind,
        "dtype":  str(arr.dtype),
        "shape":  arr.shape,
    }


def load_npy_preview(filepath: str,
                     r_idx: int, g_idx: int, b_idx: int) -> Image.Image:
    """Load a hyperspectral NPY cube and return an RGB false-colour PIL image."""
    arr = np.load(filepath, mmap_mode="r")
    nbands = arr.shape[2]
    r_idx = max(0, min(r_idx, nbands - 1))
    g_idx = max(0, min(g_idx, nbands - 1))
    b_idx = max(0, min(b_idx, nbands - 1))
    rgb = np.stack([
        _norm_band(arr[:, :, r_idx].astype(np.float32)),
        _norm_band(arr[:, :, g_idx].astype(np.float32)),
        _norm_band(arr[:, :, b_idx].astype(np.float32)),
    ], axis=2)
    return Image.fromarray(rgb, "RGB")


def load_npy_band(filepath: str, band_idx: int) -> Image.Image:
    """Return a single band from a hyperspectral NPY cube as a greyscale PIL image."""
    arr = np.load(filepath, mmap_mode="r")
    nbands = arr.shape[2]
    band_idx = max(0, min(band_idx, nbands - 1))
    band_arr = _norm_band(arr[:, :, band_idx].astype(np.float32))
    return Image.fromarray(band_arr, "L").convert("RGB")


def load_npy_image(filepath: str) -> Image.Image:
    """
    Load any NPY file and return a displayable PIL RGB image.
    For hyperspectral cubes (bands > 4) returns a false-colour composite using
    bands at 75 %, 50 %, 25 % of the band count as R, G, B.
    """
    arr = np.load(filepath)
    kind = _npy_kind(arr)

    if kind == "grey":
        data = arr[:, :, 0] if arr.ndim == 3 else arr
        return Image.fromarray(_norm_band(data.astype(np.float32)), "L").convert("RGB")

    if kind == "rgb":
        rgb = np.stack([_norm_band(arr[:, :, c].astype(np.float32))
                        for c in range(3)], axis=2)
        return Image.fromarray(rgb, "RGB")

    if kind == "rgba":
        rgba = np.stack([_norm_band(arr[:, :, c].astype(np.float32))
                         for c in range(4)], axis=2)
        pil = Image.fromarray(rgba, "RGBA")
        bg  = Image.new("RGB", pil.size, (20, 20, 20))
        bg.paste(pil, mask=pil.split()[3])
        return bg

    # hyper
    nbands = arr.shape[2]
    r, g, b = _estimate_rgb_bands(nbands, None)
    return load_npy_preview(filepath, r, g, b)


def _estimate_rgb_bands(nbands: int, wavelengths: list | None) -> tuple[int, int, int]:
    """
    Estimate the best R, G, B band indices for a natural-looking false-colour composite.

    If wavelength metadata is available the function finds the bands closest to
    canonical visible wavelengths (640 nm R, 550 nm G, 470 nm B).  This gives a
    perceptually correct colour rendering for sensors that cover the visible range.

    When no wavelength info exists (NPY cubes, ENVI without metadata) it falls back
    to a geometric heuristic that spreads R/G/B across the upper, middle and lower
    thirds of the band stack — better than 75/50/25 for sensors whose bands are not
    evenly spaced in wavelength.
    """
    if wavelengths and len(wavelengths) >= 3:
        wl = wavelengths
        def nearest(target):
            return min(range(len(wl)), key=lambda i: abs(wl[i] - target))
        # Try canonical visible wavelengths first
        r = nearest(640.0)
        g = nearest(550.0)
        b = nearest(470.0)
        # If all three collapse to the same band (sensor outside visible range),
        # fall back to geometric spread
        if len({r, g, b}) == 3:
            return r, g, b

    # Geometric fallback — spread evenly across the band range
    r = min(int(nbands * 0.75), nbands - 1)
    g = min(int(nbands * 0.50), nbands - 1)
    b = min(int(nbands * 0.25), nbands - 1)
    return r, g, b


def _find_envi_data_file_in_folder(hdr_path: str) -> str | None:
    """
    For folder loading only — find the paired ENVI data file next to the HDR
    by matching stem and known data extensions (case-insensitive).
    """
    hdr = Path(hdr_path)
    stem_lower = hdr.stem.lower()
    folder = hdr.parent
    for f in folder.iterdir():
        if (f.suffix.lower() in (".bil", ".bsq", ".bip", ".img", ".dat", ".raw")
                and f.stem.lower() == stem_lower):
            return str(f)
    return None


def load_envi_preview(hdr_path: str, data_file: str,
                      r_idx: int, g_idx: int, b_idx: int) -> Image.Image:
    """Load an ENVI cube and return an RGB preview PIL image."""
    if not SPECTRAL_AVAILABLE:
        raise RuntimeError("The 'spectral' package is not installed.\n"
                           "Run:  pip install spectral")
    img = envi.open(hdr_path, image=data_file)
    nbands = img.shape[2]

    def read_band(idx: int) -> np.ndarray:
        idx = max(0, min(idx, nbands - 1))
        return img.read_band(idx).astype(np.float32)

    rgb = np.stack([_norm_band(read_band(r_idx)),
                    _norm_band(read_band(g_idx)),
                    _norm_band(read_band(b_idx))], axis=2)
    return Image.fromarray(rgb, "RGB")


def get_envi_info(hdr_path: str, data_file: str) -> dict:
    """Return metadata dict from an ENVI header + data file pair."""
    if not SPECTRAL_AVAILABLE:
        return {}
    img = envi.open(hdr_path, image=data_file)
    rows, cols, nbands = img.shape
    meta = img.metadata
    wavelengths = None
    wl_unit = ""
    if "wavelength" in meta:
        try:
            wavelengths = [float(w) for w in meta["wavelength"]]
            wl_unit = meta.get("wavelength units", "")
        except Exception:
            pass
    return {
        "rows": rows, "cols": cols, "bands": nbands,
        "interleave": meta.get("interleave", "?").upper(),
        "dtype": str(img.dtype),
        "wavelengths": wavelengths,
        "wl_unit": wl_unit,
        "description": meta.get("description", ""),
        "data_file": data_file,
    }


def _save_hq_pil(pil: Image.Image, parent, stem: str, title: str = "Save high-quality image"):
    """
    Prompt for a save path and write a PIL image at full resolution.
    Offers 16-bit TIFF as the preferred lossless format; also PNG / JPEG.
    """
    out = filedialog.asksaveasfilename(
        parent=parent,
        title=title,
        initialfile=f"{stem}_hq.tif",
        defaultextension=".tif",
        filetypes=[
            ("16-bit TIFF (lossless)", "*.tif *.tiff"),
            ("PNG  (lossless 8-bit)",  "*.png"),
            ("JPEG (lossy)",           "*.jpg *.jpeg"),
            ("All files",              "*.*"),
        ],
    )
    if not out:
        return
    ext = Path(out).suffix.lower()
    try:
        if ext in (".tif", ".tiff"):
            # Save as 16-bit greyscale or RGB TIFF
            arr = np.array(pil.convert("RGB"))
            arr16 = (arr.astype(np.uint16) * 257)   # 8-bit → 16-bit (0-255 → 0-65535)
            img16 = Image.fromarray(arr16, mode="RGB")  # Pillow RGB 16-bit
            img16.save(out, format="TIFF", compression="tiff_lzw")
        elif ext in (".jpg", ".jpeg"):
            pil.convert("RGB").save(out, format="JPEG", quality=97, subsampling=0)
        else:
            pil.save(out)
        messagebox.showinfo("Saved", f"Saved to:\n{out}", parent=parent)
    except Exception as exc:
        messagebox.showerror("Save failed", str(exc), parent=parent)


def _build_hq_npy_band(filepath: str, band_idx: int) -> Image.Image:
    """
    Return a full-resolution 16-bit-range greyscale PIL image for a single NPY band.
    The raw float values are linearly scaled to 0-65535 and stored in a 16-bit
    greyscale TIFF-compatible PIL image (mode 'I' / int32 with 16-bit range).
    For display / save we keep it as uint16 in mode 'I;16'.
    """
    arr = np.load(filepath, mmap_mode="r")
    nbands = arr.shape[2]
    band_idx = max(0, min(band_idx, nbands - 1))
    raw = arr[:, :, band_idx].astype(np.float32)
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = raw.min(), raw.max()
    if hi > lo:
        scaled = ((raw - lo) / (hi - lo) * 65535.0).astype(np.uint16)
    else:
        scaled = np.zeros(raw.shape, dtype=np.uint16)
    # PIL can save uint16 greyscale as 16-bit TIFF via mode 'I;16'
    return Image.fromarray(scaled, mode="I;16")


def _build_hq_npy_rgb(filepath: str, r_idx: int, g_idx: int, b_idx: int) -> Image.Image:
    """
    Return a full-resolution RGB PIL image from three NPY bands.
    Each band is independently normalised to 0-255 (uint8) — same as the viewer
    preview but without any downscaling, so it is truly the full-resolution composite.
    """
    arr = np.load(filepath, mmap_mode="r")
    nbands = arr.shape[2]
    r_idx = max(0, min(r_idx, nbands - 1))
    g_idx = max(0, min(g_idx, nbands - 1))
    b_idx = max(0, min(b_idx, nbands - 1))
    rgb = np.stack([
        _norm_band(arr[:, :, r_idx].astype(np.float32)),
        _norm_band(arr[:, :, g_idx].astype(np.float32)),
        _norm_band(arr[:, :, b_idx].astype(np.float32)),
    ], axis=2)
    return Image.fromarray(rgb, "RGB")


def _build_hq_envi_band(hdr_path: str, data_file: str, band_idx: int) -> Image.Image:
    """Return a full-resolution 16-bit greyscale PIL image for one ENVI band."""
    img = envi.open(hdr_path, image=data_file)
    nbands = img.shape[2]
    band_idx = max(0, min(band_idx, nbands - 1))
    raw = img.read_band(band_idx).astype(np.float32)
    raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = raw.min(), raw.max()
    if hi > lo:
        scaled = ((raw - lo) / (hi - lo) * 65535.0).astype(np.uint16)
    else:
        scaled = np.zeros(raw.shape, dtype=np.uint16)
    return Image.fromarray(scaled, mode="I;16")


def _build_hq_envi_rgb(hdr_path: str, data_file: str,
                        r_idx: int, g_idx: int, b_idx: int) -> Image.Image:
    """Return a full-resolution RGB PIL image from three ENVI bands."""
    img = envi.open(hdr_path, image=data_file)
    nbands = img.shape[2]
    def rb(i):
        i = max(0, min(i, nbands - 1))
        return _norm_band(img.read_band(i).astype(np.float32))
    rgb = np.stack([rb(r_idx), rb(g_idx), rb(b_idx)], axis=2)
    return Image.fromarray(rgb, "RGB")


def load_image(filepath: str, parent_widget=None,
               envi_bands: tuple = None,
               envi_data_file: str = None) -> Image.Image:
    ext = Path(filepath).suffix.lower()

    # Standard formats via Pillow
    if ext in PILLOW_EXTENSIONS:
        img = Image.open(filepath)

        # Multi-page (animated GIF, multi-frame TIFF) — just use first frame
        try:
            img.seek(0)
        except EOFError:
            pass

        # ── Normalise bit depth so the image isn't white / black ──────────
        mode = img.mode

        # 16-bit greyscale or RGB
        if mode == "I;16" or mode == "I":
            arr = np.array(img, dtype=np.float32)
            lo, hi = arr.min(), arr.max()
            if hi > lo:
                arr = (arr - lo) / (hi - lo) * 255
            img = Image.fromarray(arr.astype(np.uint8), "L")

        elif mode == "F":   # 32-bit float
            arr = np.array(img, dtype=np.float32)
            lo, hi = arr.min(), arr.max()
            if hi > lo:
                arr = (arr - lo) / (hi - lo) * 255
            img = Image.fromarray(arr.astype(np.uint8), "L")

        elif mode == "I;16B":
            arr = np.frombuffer(img.tobytes(), dtype=np.dtype(">u2")).reshape(img.size[1], img.size[0])
            arr = arr.astype(np.float32)
            lo, hi = arr.min(), arr.max()
            if hi > lo:
                arr = (arr - lo) / (hi - lo) * 255
            img = Image.fromarray(arr.astype(np.uint8), "L")

        elif mode == "RGB;16":
            arr = np.array(img.convert("RGB"), dtype=np.float32)
            lo, hi = arr.min(), arr.max()
            if hi > lo:
                arr = (arr - lo) / (hi - lo) * 255
            img = Image.fromarray(arr.astype(np.uint8), "RGB")

        # Numpy-based normalisation for any remaining high-bit modes
        elif img.mode not in ("RGB", "L", "RGBA", "LA", "P", "1"):
            try:
                arr = np.array(img).astype(np.float32)
                lo, hi = arr.min(), arr.max()
                if hi > lo:
                    arr = (arr - lo) / (hi - lo) * 255
                img = Image.fromarray(arr.astype(np.uint8))
            except Exception:
                pass

        # Flatten transparency / palette for display
        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (20, 20, 20))
            src = img.convert("RGBA")
            bg.paste(src, mask=src.split()[3])
            return bg
        if img.mode == "P":
            return img.convert("RGB")

        return img.convert("RGB")

    # Camera RAW via rawpy
    if ext in CAMERA_RAW_EXTENSIONS:
        with rawpy.imread(filepath) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
        return Image.fromarray(rgb)

    # .raw — try rawpy, then Pillow, then plain pixel fallback
    if ext in PLAIN_RAW_EXTENSIONS:
        try:
            with rawpy.imread(filepath) as raw:
                rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False, output_bps=8)
            return Image.fromarray(rgb)
        except Exception:
            pass
        try:
            return Image.open(filepath).convert("RGB")
        except Exception:
            pass

        # Ask user for dimensions
        global _plain_raw_settings
        file_size = os.path.getsize(filepath)
        if _plain_raw_settings.get("file_size") == file_size:
            w, h, ch, bits = (_plain_raw_settings["width"], _plain_raw_settings["height"],
                               _plain_raw_settings["channels"], _plain_raw_settings["bits"])
        else:
            if parent_widget is None:
                raise RuntimeError("Cannot determine dimensions — no parent widget.")
            dlg = PlainRawDialog(parent_widget, filepath, file_size)
            if dlg.result is None:
                raise RuntimeError("Cancelled.")
            w, h, ch, bits = dlg.result
            _plain_raw_settings = dict(file_size=file_size, width=w, height=h,
                                        channels=ch, bits=bits)
        return _load_plain_raw(filepath, w, h, ch, bits)

    # ENVI hyperspectral — open the .hdr file
    if ext in ENVI_HEADER_EXTENSIONS:
        info = get_envi_info(filepath, envi_data_file)
        nbands = info.get("bands", 1)
        if envi_bands is not None:
            r, g, b = envi_bands
        else:
            r, g, b = _estimate_rgb_bands(nbands, info.get("wavelengths"))
        return load_envi_preview(filepath, envi_data_file, r, g, b)

    # NumPy .npy files
    if ext in NPY_EXTENSIONS:
        return load_npy_image(filepath)

    raise ValueError(f"Unsupported extension: {ext}")


# ── Main viewer application ───────────────────────────────────────────────────

class ImageViewer(tk.Tk):
    ACCENT  = "#E8FF47"
    BG      = "#0D0D0D"
    SURFACE = "#1A1A1A"
    BORDER  = "#2E2E2E"
    FG      = "#F0F0F0"
    FG_DIM  = "#666666"

    # Group extensions for the file-type filter badge
    FORMAT_GROUPS = {
        "STD":  PILLOW_EXTENSIONS,
        "CAM":  CAMERA_RAW_EXTENSIONS,
        "RAW":  PLAIN_RAW_EXTENSIONS,
        "NPY":  NPY_EXTENSIONS,
    }

    def __init__(self):
        super().__init__()
        self.title("Image Viewer")
        self.configure(bg=self.BG)
        self.minsize(900, 620)
        self.geometry("1200x820")

        self.files: list[str] = []
        self._all_files: list[str] = []
        self.index: int = 0
        self._pil_cache:   dict[int, Image.Image]      = {}
        self._photo_cache: dict[int, ImageTk.PhotoImage] = {}

        # Zoom & pan state
        self._zoom: float = 1.0
        self._zoom_min: float = 0.05
        self._zoom_max: float = 20.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_start: tuple = (0, 0)
        self._drag_pan_start: tuple = (0, 0)

        # Tool mode: "pan" or "lasso"
        self._tool: str = "pan"

        # ENVI hyperspectral state
        self._envi_info:       dict  = {}
        self._envi_bands:      tuple = None
        self._envi_data_files: dict  = {}   # hdr_path -> data_file_path
        self._envi_band_idx:   int   = 0    # current band slice shown by slider
        self._envi_slice_pil            = None  # PIL image of current band slice

        # NPY hyperspectral state
        self._npy_info:      dict  = {}
        self._npy_bands:     tuple = None   # (r, g, b) indices for false-colour
        self._npy_band_idx:  int   = 0      # current band slice for slider
        self._npy_slice_pil          = None # PIL image of current NPY band slice

        # Lasso state
        self._lasso_points: list[tuple[int, int]] = []   # canvas coords
        self._lasso_item   = None                         # canvas polygon id

        # Active filter: None = all, else a frozenset of extensions
        self._filter: frozenset | None = None

        self._build_ui()
        self._bind_keys()
        self._show_welcome()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ──
        top = tk.Frame(self, bg=self.BG, pady=8)
        top.pack(fill="x", padx=16)

        tk.Label(top, text="IMAGE", font=("Courier New", 22, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(side="left")
        tk.Label(top, text=" VIEWER", font=("Courier New", 22, "bold"),
                 bg=self.BG, fg=self.FG).pack(side="left")

        btn = dict(bg=self.SURFACE, fg=self.FG, relief="flat",
                   font=("Courier New", 10), cursor="hand2",
                   activebackground=self.ACCENT, activeforeground=self.BG,
                   padx=14, pady=6, bd=0)

        tk.Button(top, text="OPEN FOLDER", command=self._open_folder, **btn).pack(side="right", padx=4)
        tk.Button(top, text="OPEN FILES",  command=self._open_files,  **btn).pack(side="right", padx=4)
        tk.Button(top, text="✕  EXIT", command=self.quit,
                  bg=self.SURFACE, fg="#FF5555", relief="flat",
                  font=("Courier New", 10), cursor="hand2",
                  activebackground="#FF5555", activeforeground=self.BG,
                  padx=14, pady=6, bd=0).pack(side="right", padx=(0, 4))

        # Tool toggle
        self.btn_lasso = tk.Button(top, text="⬡  LASSO", command=self._toggle_lasso,
                                   bg=self.SURFACE, fg=self.FG, relief="flat",
                                   font=("Courier New", 10), cursor="hand2",
                                   activebackground=self.ACCENT, activeforeground=self.BG,
                                   padx=14, pady=6, bd=0)
        self.btn_lasso.pack(side="right", padx=4)

        # ── Colour transform buttons ──────────────────────────────────────────────
        tk.Button(top, text="NEG",    command=self._transform_negative,  **btn).pack(side="right", padx=4)
        tk.Button(top, text="HSV",    command=self._transform_hsv,       **btn).pack(side="right", padx=4)
        tk.Button(top, text="LAB",    command=self._transform_lab,        **btn).pack(side="right", padx=4)
        tk.Button(top, text="ADJUST", command=self._open_adjust_window,  **btn).pack(side="right", padx=4)

        # ── Filter strip ──
        fbar = tk.Frame(self, bg=self.SURFACE, pady=6)
        fbar.pack(fill="x", padx=0)

        tk.Label(fbar, text="SHOW:", font=("Courier New", 8),
                 bg=self.SURFACE, fg=self.FG_DIM).pack(side="left", padx=(14, 6))

        self._filter_btns: dict[str, tk.Button] = {}
        filter_options = {
            "ALL":   None,
            "JPG":   frozenset({".jpg", ".jpeg"}),
            "PNG":   frozenset({".png"}),
            "TIFF":  frozenset({".tiff", ".tif"}),
            "CAM RAW": frozenset(CAMERA_RAW_EXTENSIONS),
            ".RAW":  frozenset(PLAIN_RAW_EXTENSIONS),
            "ENVI":  frozenset(ENVI_HEADER_EXTENSIONS),
            "NPY":   frozenset(NPY_EXTENSIONS),
            "OTHER": frozenset(PILLOW_EXTENSIONS - {".jpg", ".jpeg", ".png", ".tiff", ".tif"}),
        }
        self._filter_map = filter_options

        for label, exts in filter_options.items():
            b = tk.Button(fbar, text=label, font=("Courier New", 8),
                          bg=self.SURFACE, fg=self.FG_DIM, relief="flat",
                          cursor="hand2", padx=10, pady=3, bd=0,
                          activebackground=self.ACCENT, activeforeground=self.BG,
                          command=lambda l=label: self._apply_filter(l))
            b.pack(side="left", padx=2)
            self._filter_btns[label] = b

        self._apply_filter("ALL", init=True)

        # ── Divider ──
        tk.Frame(self, bg=self.BORDER, height=1).pack(fill="x")

        # ── Canvas ──
        self.canvas = tk.Canvas(self, bg=self.BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>",       self._on_resize)
        self.canvas.bind("<MouseWheel>",      self._on_mousewheel)
        self.canvas.bind("<Button-4>",        self._on_mousewheel)
        self.canvas.bind("<Button-5>",        self._on_mousewheel)
        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        # ── ENVI band-picker panel (hidden unless an HDR is loaded) ──
        self._envi_panel = tk.Frame(self, bg=self.SURFACE, pady=6)
        # Not packed yet — shown/hidden dynamically

        ep = self._envi_panel
        tk.Label(ep, text="HYPERSPECTRAL", font=("Courier New", 8, "bold"),
                 bg=self.SURFACE, fg=self.ACCENT).pack(side="left", padx=(12, 10))

        self._envi_meta_lbl = tk.Label(ep, text="", font=("Courier New", 8),
                                        bg=self.SURFACE, fg=self.FG_DIM)
        self._envi_meta_lbl.pack(side="left", padx=(0, 14))

        for ch, color in (("R", "#FF6B6B"), ("G", "#6BFF8E"), ("B", "#6BB5FF")):
            tk.Label(ep, text=ch, font=("Courier New", 9, "bold"),
                     bg=self.SURFACE, fg=color).pack(side="left", padx=(6, 2))
            var = tk.IntVar(value=0)
            setattr(self, f"_envi_{ch.lower()}_var", var)
            sp = tk.Spinbox(ep, textvariable=var, from_=0, to=999, width=5,
                            font=("Courier New", 9), bg=self.BG, fg=self.FG,
                            buttonbackground=self.SURFACE, relief="flat",
                            insertbackground=self.ACCENT,
                            command=self._envi_band_changed)
            sp.bind("<Return>", lambda _: self._envi_band_changed())
            sp.pack(side="left", padx=(0, 4))

        tk.Button(ep, text="APPLY", command=self._envi_band_changed,
                  bg=self.SURFACE, fg=self.ACCENT, relief="flat",
                  font=("Courier New", 8, "bold"), cursor="hand2",
                  activebackground=self.ACCENT, activeforeground=self.BG,
                  padx=10, pady=3, bd=0).pack(side="left", padx=6)

        # Greyscale single-band mode
        self._envi_grey_var = tk.BooleanVar(value=False)
        tk.Checkbutton(ep, text="Single band (grey)", variable=self._envi_grey_var,
                       command=self._envi_band_changed,
                       bg=self.SURFACE, fg=self.FG_DIM,
                       selectcolor=self.BG, activebackground=self.SURFACE,
                       font=("Courier New", 8)).pack(side="left", padx=8)

        # Wavelength hint label
        self._envi_wl_lbl = tk.Label(ep, text="", font=("Courier New", 8),
                                      bg=self.SURFACE, fg=self.FG_DIM)
        self._envi_wl_lbl.pack(side="left", padx=6)

        # HQ export buttons
        tk.Button(ep, text="💾 HQ Slice",
                  command=self._envi_save_hq_slice,
                  bg=self.SURFACE, fg=self.ACCENT, relief="flat",
                  font=("Courier New", 8, "bold"), cursor="hand2",
                  activebackground=self.ACCENT, activeforeground=self.BG,
                  padx=10, pady=3, bd=0).pack(side="left", padx=4)
        tk.Button(ep, text="💾 HQ RGB",
                  command=self._envi_save_hq_rgb,
                  bg=self.SURFACE, fg=self.ACCENT, relief="flat",
                  font=("Courier New", 8, "bold"), cursor="hand2",
                  activebackground=self.ACCENT, activeforeground=self.BG,
                  padx=10, pady=3, bd=0).pack(side="left", padx=(0, 6))

        # ── NPY band-picker panel (hidden unless a hyperspectral NPY is loaded) ──
        self._npy_panel = tk.Frame(self, bg=self.SURFACE, pady=6)
        # Not packed yet — shown/hidden dynamically

        np_panel = self._npy_panel
        tk.Label(np_panel, text="NPY HYPERSPECTRAL", font=("Courier New", 8, "bold"),
                 bg=self.SURFACE, fg=self.ACCENT).pack(side="left", padx=(12, 10))

        self._npy_meta_lbl = tk.Label(np_panel, text="", font=("Courier New", 8),
                                       bg=self.SURFACE, fg=self.FG_DIM)
        self._npy_meta_lbl.pack(side="left", padx=(0, 14))

        for ch, color in (("R", "#FF6B6B"), ("G", "#6BFF8E"), ("B", "#6BB5FF")):
            tk.Label(np_panel, text=ch, font=("Courier New", 9, "bold"),
                     bg=self.SURFACE, fg=color).pack(side="left", padx=(6, 2))
            var = tk.IntVar(value=0)
            setattr(self, f"_npy_{ch.lower()}_var", var)
            sp = tk.Spinbox(np_panel, textvariable=var, from_=0, to=9999, width=5,
                            font=("Courier New", 9), bg=self.BG, fg=self.FG,
                            buttonbackground=self.SURFACE, relief="flat",
                            insertbackground=self.ACCENT,
                            command=self._npy_band_changed)
            sp.bind("<Return>", lambda _: self._npy_band_changed())
            sp.pack(side="left", padx=(0, 4))

        tk.Button(np_panel, text="APPLY", command=self._npy_band_changed,
                  bg=self.SURFACE, fg=self.ACCENT, relief="flat",
                  font=("Courier New", 8, "bold"), cursor="hand2",
                  activebackground=self.ACCENT, activeforeground=self.BG,
                  padx=10, pady=3, bd=0).pack(side="left", padx=6)

        # Greyscale single-band mode for NPY
        self._npy_grey_var = tk.BooleanVar(value=False)
        tk.Checkbutton(np_panel, text="Single band (grey)", variable=self._npy_grey_var,
                       command=self._npy_band_changed,
                       bg=self.SURFACE, fg=self.FG_DIM,
                       selectcolor=self.BG, activebackground=self.SURFACE,
                       font=("Courier New", 8)).pack(side="left", padx=8)

        # HQ export buttons
        tk.Button(np_panel, text="💾 HQ Slice",
                  command=self._npy_save_hq_slice,
                  bg=self.SURFACE, fg=self.ACCENT, relief="flat",
                  font=("Courier New", 8, "bold"), cursor="hand2",
                  activebackground=self.ACCENT, activeforeground=self.BG,
                  padx=10, pady=3, bd=0).pack(side="left", padx=4)
        tk.Button(np_panel, text="💾 HQ RGB",
                  command=self._npy_save_hq_rgb,
                  bg=self.SURFACE, fg=self.ACCENT, relief="flat",
                  font=("Courier New", 8, "bold"), cursor="hand2",
                  activebackground=self.ACCENT, activeforeground=self.BG,
                  padx=10, pady=3, bd=0).pack(side="left", padx=(0, 6))

        # ── Bottom bar ──
        bottom = tk.Frame(self, bg=self.SURFACE, pady=10)
        bottom.pack(fill="x", side="bottom")

        nav = dict(bg=self.SURFACE, fg=self.FG, relief="flat",
                   font=("Courier New", 14, "bold"), cursor="hand2",
                   activebackground=self.ACCENT, activeforeground=self.BG,
                   width=3, bd=0)

        tk.Button(bottom, text="◀", command=self._prev, **nav).pack(side="left", padx=(16, 6))
        tk.Button(bottom, text="▶", command=self._next, **nav).pack(side="left", padx=(0, 16))

        # Zoom controls
        zoom_style = dict(bg=self.SURFACE, fg=self.FG, relief="flat",
                          font=("Courier New", 12, "bold"), cursor="hand2",
                          activebackground=self.ACCENT, activeforeground=self.BG,
                          width=3, bd=0, pady=0)
        tk.Button(bottom, text="−", command=self._zoom_out,   **zoom_style).pack(side="left", padx=(0, 2))
        tk.Button(bottom, text="+", command=self._zoom_in,    **zoom_style).pack(side="left", padx=(0, 4))
        tk.Button(bottom, text="⊡", command=self._zoom_reset, **zoom_style).pack(side="left", padx=(0, 12))
        self.lbl_zoom = tk.Label(bottom, text="100%", font=("Courier New", 9),
                                  bg=self.SURFACE, fg=self.FG_DIM, width=6)
        self.lbl_zoom.pack(side="left")

        sf = tk.Frame(bottom, bg=self.SURFACE)
        sf.pack(side="left", fill="x", expand=True, padx=8)
        self.slider_var = tk.IntVar(value=0)
        self.slider = tk.Scale(sf, variable=self.slider_var, from_=0, to=0,
                               orient="horizontal", command=self._on_slider,
                               bg=self.SURFACE, fg=self.FG, troughcolor=self.BORDER,
                               highlightthickness=0, sliderrelief="flat",
                               activebackground=self.ACCENT, showvalue=False,
                               font=("Courier New", 8), length=400, bd=0)
        self.slider.pack(fill="x", expand=True)

        info = tk.Frame(bottom, bg=self.SURFACE)
        info.pack(side="right", padx=16)
        self.lbl_count = tk.Label(info, text="0 / 0", font=("Courier New", 11, "bold"),
                                   bg=self.SURFACE, fg=self.ACCENT)
        self.lbl_count.pack(anchor="e")
        self.lbl_name = tk.Label(info, text="—", font=("Courier New", 9),
                                  bg=self.SURFACE, fg=self.FG_DIM)
        self.lbl_name.pack(anchor="e")
        self.lbl_size = tk.Label(info, text="", font=("Courier New", 8),
                                  bg=self.SURFACE, fg=self.FG_DIM)
        self.lbl_size.pack(anchor="e")

    def _bind_keys(self):
        self.bind("<Left>",  lambda _: self._prev())
        self.bind("<Right>", lambda _: self._next())
        self.bind("<Home>",  lambda _: self._go(0))
        self.bind("<End>",   lambda _: self._go(len(self.files) - 1))
        self.bind("<plus>",   lambda _: self._zoom_in())
        self.bind("<equal>",  lambda _: self._zoom_in())
        self.bind("<minus>",  lambda _: self._zoom_out())
        self.bind("<0>",      lambda _: self._zoom_reset())
        self.bind("<Escape>", lambda _: self._lasso_clear())

    # ── Filter ────────────────────────────────────────────────────────────────

    def _apply_filter(self, label: str, init=False):
        self._active_filter_label = label
        exts = self._filter_map[label]

        for lbl, btn in self._filter_btns.items():
            if lbl == label:
                btn.config(bg=self.ACCENT, fg=self.BG)
            else:
                btn.config(bg=self.SURFACE, fg=self.FG_DIM)

        if init:
            return

        if not self._all_files:
            return

        if exts is None:
            self.files = list(self._all_files)
        else:
            self.files = [f for f in self._all_files
                          if Path(f).suffix.lower() in exts]

        self.index = 0
        self._pil_cache.clear()
        self._photo_cache.clear()
        self.slider.config(to=max(0, len(self.files) - 1))
        self.slider_var.set(0)

        if self.files:
            self._show_image()
        else:
            self._show_empty(f"No {label} files in current selection.")

    # ── Welcome / empty ───────────────────────────────────────────────────────

    def _show_welcome(self):
        self.canvas.delete("all")
        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 500
        self.canvas.create_text(cw // 2, ch // 2 - 20,
                                text="[ Open a folder or select image files ]",
                                font=("Courier New", 14), fill=self.FG_DIM)
        self.canvas.create_text(cw // 2, ch // 2 + 14,
                                text="JPG · PNG · TIFF · BMP · WEBP · GIF · CR2 · NEF · ARW · DNG · RAW …",
                                font=("Courier New", 9), fill=self.BORDER)

    def _show_empty(self, msg: str):
        self.canvas.delete("all")
        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 500
        self.canvas.create_text(cw // 2, ch // 2, text=msg,
                                font=("Courier New", 12), fill=self.FG_DIM)

    # ── File loading ──────────────────────────────────────────────────────────

    def _open_folder(self):
        folder = filedialog.askdirectory(title="Select image folder")
        if not folder:
            return
        found = sorted(
            str(p) for p in Path(folder).iterdir()
            if p.suffix.lower() in ALL_EXTENSIONS
        )
        # For ENVI HDRs in a folder, auto-pair with same-stem data file
        paired = {}   # hdr_path -> data_file_path
        filtered = []
        for f in found:
            if Path(f).suffix.lower() in ENVI_HEADER_EXTENSIONS:
                data = _find_envi_data_file_in_folder(f)
                if data:
                    paired[f] = data
                    filtered.append(f)
                # skip HDRs with no paired data file silently
            else:
                filtered.append(f)
        self._envi_data_files = paired
        self._load_file_list(filtered)

    def _open_files(self):
        ext_str = " ".join(f"*{e}" for e in sorted(ALL_EXTENSIONS))
        paths = filedialog.askopenfilenames(
            title="Select image files",
            filetypes=[
                ("All supported images", ext_str),
                ("Standard images",      "*.jpg *.jpeg *.png *.tiff *.tif *.bmp *.gif *.webp"),
                ("Camera RAW",           "*.cr2 *.nef *.arw *.dng *.orf *.rw2 *.raf *.pef *.srw"),
                ("Plain RAW",            "*.raw"),
                ("ENVI Hyperspectral",   "*.hdr"),
                ("NumPy Array",          "*.npy"),
                ("All files",            "*.*"),
            ]
        )
        if not paths:
            return

        # For each HDR in the selection, ask for its data file explicitly
        paired = {}
        final_paths = []
        for p in paths:
            if Path(p).suffix.lower() in ENVI_HEADER_EXTENSIONS:
                messagebox.showinfo(
                    "ENVI — Step 1 of 2",
                    f"HDR selected:\n{Path(p).name}\n\n"
                    f"Now select the matching data file (.bil / .bsq / .bip / .img / .dat).")
                data = filedialog.askopenfilename(
                    title=f"Select data file for  {Path(p).name}",
                    initialdir=str(Path(p).parent),
                    filetypes=[
                        ("ENVI data files", "*.bil *.bsq *.bip *.img *.dat *.raw"),
                        ("All files",       "*.*"),
                    ]
                )
                if not data:
                    continue   # user cancelled — skip this HDR
                paired[p] = data
                final_paths.append(p)
            else:
                final_paths.append(p)

        if not final_paths:
            return
        self._envi_data_files = paired
        self._load_file_list(final_paths)

    def _load_file_list(self, paths: list[str]):
        if not paths:
            messagebox.showinfo("No files", "No supported image files found.")
            return
        self._all_files = paths
        self.files = list(paths)
        self.index = 0
        self._pil_cache.clear()
        self._photo_cache.clear()
        self._envi_slice_pil = None
        self.slider.config(to=max(0, len(self.files) - 1))
        self.slider_var.set(0)
        # Reset filter to ALL
        self._apply_filter("ALL", init=True)
        self._active_filter_label = "ALL"
        for lbl, btn in self._filter_btns.items():
            btn.config(bg=(self.ACCENT if lbl == "ALL" else self.SURFACE),
                       fg=(self.BG     if lbl == "ALL" else self.FG_DIM))
        self._show_image()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _is_envi_active(self) -> bool:
        """True when the current file is an ENVI cube (slider = band scrubber)."""
        if not self.files:
            return False
        return Path(self.files[self.index]).suffix.lower() in ENVI_HEADER_EXTENSIONS

    def _is_npy_hyper_active(self) -> bool:
        """True when the current file is a hyperspectral NPY cube."""
        if not self.files:
            return False
        if Path(self.files[self.index]).suffix.lower() not in NPY_EXTENSIONS:
            return False
        return self._npy_info.get("kind") == "hyper"

    def _prev(self):
        if self._is_envi_active():
            self._envi_go_band(self._envi_band_idx - 1)
        elif self._is_npy_hyper_active():
            self._npy_go_band(self._npy_band_idx - 1)
        elif self.files:
            self._go(self.index - 1)

    def _next(self):
        if self._is_envi_active():
            self._envi_go_band(self._envi_band_idx + 1)
        elif self._is_npy_hyper_active():
            self._npy_go_band(self._npy_band_idx + 1)
        elif self.files:
            self._go(self.index + 1)

    def _go(self, idx: int):
        if not self.files:
            return
        self.index = idx % len(self.files)
        self.slider_var.set(self.index)
        self._show_image()

    def _on_slider(self, val):
        idx = int(float(val))
        if self._is_envi_active():
            if idx != self._envi_band_idx:
                self._envi_go_band(idx, from_slider=True)
        elif self._is_npy_hyper_active():
            if idx != self._npy_band_idx:
                self._npy_go_band(idx, from_slider=True)
        elif self.files and idx != self.index:
            self.index = idx
            self._show_image()

    # ── ENVI band scrubbing ───────────────────────────────────────────────────

    def _envi_go_band(self, band_idx: int, from_slider: bool = False):
        """Render a single greyscale band slice and update the slider."""
        info   = self._envi_info
        nbands = info.get("bands", 1)
        band_idx = max(0, min(band_idx, nbands - 1))
        self._envi_band_idx = band_idx

        if not from_slider:
            self.slider_var.set(band_idx)

        # Update wavelength label
        wls = info.get("wavelengths")
        raw_unit = info.get("wl_unit", "").strip().lower()
        unit = "nm" if (wls and max(wls) > 100 and raw_unit in ("", "unknown")) else raw_unit
        if wls and band_idx < len(wls):
            wl_str = f"Band {band_idx}  ·  λ {wls[band_idx]:.1f} {unit}"
        else:
            wl_str = f"Band {band_idx}"
        self.lbl_count.config(text=f"{band_idx + 1} / {nbands}")
        self.lbl_name.config(text=wl_str)
        self.title(f"Image Viewer — {Path(self.files[self.index]).name}  [{wl_str}]")

        # Render the band slice (not cached — read fresh each time for memory efficiency)
        path      = self.files[self.index]
        data_file = info.get("data_file")
        try:
            img      = envi.open(path, image=data_file)
            band_arr = _norm_band(img.read_band(band_idx).astype(np.float32))
            pil      = Image.fromarray(band_arr, "L").convert("RGB")
        except Exception as exc:
            messagebox.showerror("ENVI error", str(exc))
            return

        # Store as current display (don't pollute the main PIL cache)
        self._envi_slice_pil = pil
        self._redraw()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _show_image(self):
        """Load image into cache, update labels, then draw with current zoom."""
        if not self.files:
            return
        path = self.files[self.index]
        name = Path(path).name
        ext  = Path(path).suffix.lower()
        self.lbl_count.config(text=f"{self.index + 1} / {len(self.files)}")
        self.lbl_name.config(text=name)
        self.title(f"Image Viewer — {name}")

        # Reset zoom & pan when switching images
        self._zoom  = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.lbl_zoom.config(text="100%")

        # Show/hide ENVI panel
        is_envi = ext in ENVI_HEADER_EXTENSIONS
        is_npy  = ext in NPY_EXTENSIONS
        if is_envi:
            self._envi_panel.pack(fill="x", before=self.canvas)
            self._npy_panel.pack_forget()
            envi_data = self._envi_data_files.get(path)
            if not envi_data:
                self.canvas.delete("all")
                self.canvas.create_text(
                    max(self.canvas.winfo_width(), 100) // 2,
                    max(self.canvas.winfo_height(), 100) // 2,
                    text="⚠  No data file paired with this HDR.",
                    font=("Courier New", 11), fill="#FF5555")
                return
            self._envi_info     = get_envi_info(path, envi_data)
            self._envi_band_idx = 0
            self._envi_slice_pil = None
            # Reconfigure slider to scrub bands
            nbands = self._envi_info.get("bands", 1)
            self.slider.config(to=max(0, nbands - 1))
            self.slider_var.set(0)
            self.lbl_count.config(text=f"1 / {nbands}")
            self._setup_envi_panel(path)
        elif is_npy:
            self._envi_panel.pack_forget()
            self._envi_info      = {}
            self._envi_bands     = None
            self._envi_slice_pil = None
            # Load NPY metadata
            try:
                self._npy_info = get_npy_info(path)
            except Exception as exc:
                self._npy_panel.pack_forget()
                self.canvas.delete("all")
                cw = max(self.canvas.winfo_width(), 100)
                ch = max(self.canvas.winfo_height(), 100)
                self.canvas.create_text(cw // 2, ch // 2,
                                        text=f"⚠  Cannot read NPY file\n{exc}",
                                        font=("Courier New", 11), fill="#FF5555",
                                        justify="center")
                return
            if self._npy_info.get("kind") == "hyper":
                # Hyperspectral — show band panel and configure slider
                self._npy_panel.pack(fill="x", before=self.canvas)
                self._npy_band_idx  = 0
                self._npy_slice_pil = None
                self._npy_bands     = None
                nbands = self._npy_info.get("bands", 1)
                self.slider.config(to=max(0, nbands - 1))
                self.slider_var.set(0)
                self.lbl_count.config(text=f"1 / {nbands}")
                self._setup_npy_panel(path)
            else:
                # Simple 2-D or RGB NPY — hide panel, slider stays on files
                self._npy_panel.pack_forget()
                self._npy_info      = {}
                self._npy_bands     = None
                self._npy_slice_pil = None
                self.slider.config(to=max(0, len(self.files) - 1))
                self.slider_var.set(self.index)
        else:
            self._envi_panel.pack_forget()
            self._npy_panel.pack_forget()
            self._envi_info      = {}
            self._envi_bands     = None
            self._envi_slice_pil = None
            self._npy_info       = {}
            self._npy_bands      = None
            self._npy_slice_pil  = None
            # Restore slider to file range
            self.slider.config(to=max(0, len(self.files) - 1))
            self.slider_var.set(self.index)

        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        self.canvas.delete("all")
        self.canvas.create_text(cw // 2, ch // 2,
                                text=f"Loading  {name} …",
                                font=("Courier New", 12), fill=self.FG_DIM)
        self.update_idletasks()

        # Load into PIL cache if needed
        if self.index not in self._pil_cache:
            try:
                self._pil_cache[self.index] = load_image(
                    path, parent_widget=self,
                    envi_bands=self._envi_bands,
                    envi_data_file=self._envi_data_files.get(path))
            except Exception as exc:
                self.canvas.delete("all")
                self.canvas.create_text(cw // 2, ch // 2,
                                        text=f"⚠  Could not open file\n{exc}",
                                        font=("Courier New", 11), fill="#FF5555",
                                        justify="center")
                self.lbl_size.config(text="")
                return

        pil = self._pil_cache[self.index]
        file_bytes = os.path.getsize(path)
        size_kb    = file_bytes / 1024
        size_str   = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
        extra = ""
        if is_envi:
            info = self._envi_info
            extra = f"  ·  {info.get('bands','?')} bands  [{info.get('interleave','?')}]"
        elif is_npy and self._npy_info:
            info = self._npy_info
            extra = f"  ·  {info.get('bands','?')} bands  [{info.get('dtype','?')}]"
        self.lbl_size.config(text=f"{pil.width}×{pil.height}  ·  {size_str}{extra}")

        self._redraw()

    # ── ENVI panel helpers ────────────────────────────────────────────────────

    def _setup_envi_panel(self, hdr_path: str):
        """Populate spinboxes and metadata label from loaded ENVI info."""
        info = self._envi_info
        nbands = info.get("bands", 1)

        # Set spinbox max
        for ch in ("r", "g", "b"):
            sp_var = getattr(self, f"_envi_{ch}_var")
            # clamp existing value
            sp_var.set(min(sp_var.get(), nbands - 1))

        # Default RGB using wavelength-aware estimation
        if self._envi_bands is None:
            r, g, b = _estimate_rgb_bands(nbands, info.get("wavelengths"))
            self._envi_r_var.set(r)
            self._envi_g_var.set(g)
            self._envi_b_var.set(b)
            self._envi_bands = (r, g, b)

        # Metadata summary
        wls = info.get("wavelengths")
        raw_unit = info.get("wl_unit", "").strip().lower()
        unit = "nm" if (wls and max(wls) > 100 and raw_unit in ("", "unknown")) else raw_unit
        meta_str = (f"{info.get('rows','?')} × {info.get('cols','?')} × "
                    f"{nbands} bands  |  {info.get('interleave','?')}  |  "
                    f"{info.get('dtype','?')}")
        if wls:
            meta_str += f"  |  λ {wls[0]:.1f}–{wls[-1]:.1f} {unit}"
        self._envi_meta_lbl.config(text=meta_str)
        self._update_wl_hint()

    def _update_wl_hint(self):
        """Show wavelength values next to the current band indices."""
        wls = self._envi_info.get("wavelengths")
        raw_unit = self._envi_info.get("wl_unit", "").strip().lower()
        # If unit is blank or "unknown", infer from wavelength range
        if wls and raw_unit in ("", "unknown"):
            unit = "nm" if max(wls) > 100 else "μm"
        else:
            unit = raw_unit or ""
        if not wls:
            self._envi_wl_lbl.config(text="")
            return
        nbands = len(wls)
        parts = []
        for ch in ("r", "g", "b"):
            idx = getattr(self, f"_envi_{ch}_var").get()
            if 0 <= idx < nbands:
                parts.append(f"{ch.upper()}={wls[idx]:.1f}")
        self._envi_wl_lbl.config(text="  ".join(parts) + (f" {unit}" if parts else ""))

    def _envi_band_changed(self):
        """Called when user changes band spinboxes or grey checkbox."""
        if not self.files:
            return
        path = self.files[self.index]
        if Path(path).suffix.lower() not in ENVI_HEADER_EXTENSIONS:
            return

        info    = self._envi_info
        nbands  = info.get("bands", 1)
        grey    = self._envi_grey_var.get()

        r = max(0, min(self._envi_r_var.get(), nbands - 1))
        g = max(0, min(self._envi_g_var.get(), nbands - 1))
        b = max(0, min(self._envi_b_var.get(), nbands - 1))

        self._update_wl_hint()

        # Rebuild preview
        data_file = self._envi_info.get("data_file")
        try:
            if grey:
                img = envi.open(path, image=data_file)
                band_arr = _norm_band(img.read_band(r).astype(np.float32))
                pil = Image.fromarray(band_arr, "L").convert("RGB")
            else:
                pil = load_envi_preview(path, data_file, r, g, b)
            self._envi_bands = (r, g, b)
            self._pil_cache[self.index] = pil
            self._redraw()
        except Exception as exc:
            messagebox.showerror("ENVI error", str(exc))

    # ── NPY band scrubbing ────────────────────────────────────────────────────

    def _npy_go_band(self, band_idx: int, from_slider: bool = False):
        """Render a single greyscale band slice from a hyperspectral NPY cube."""
        info   = self._npy_info
        nbands = info.get("bands", 1)
        band_idx = max(0, min(band_idx, nbands - 1))
        self._npy_band_idx = band_idx

        if not from_slider:
            self.slider_var.set(band_idx)

        self.lbl_count.config(text=f"{band_idx + 1} / {nbands}")
        self.lbl_name.config(text=f"Band {band_idx}")
        path = self.files[self.index]
        self.title(f"Image Viewer — {Path(path).name}  [Band {band_idx}]")

        try:
            pil = load_npy_band(path, band_idx)
        except Exception as exc:
            messagebox.showerror("NPY error", str(exc))
            return

        self._npy_slice_pil = pil
        self._redraw()

    def _npy_band_changed(self):
        """Called when user changes the NPY RGB spinboxes or grey checkbox."""
        if not self.files:
            return
        path = self.files[self.index]
        if Path(path).suffix.lower() not in NPY_EXTENSIONS:
            return

        info   = self._npy_info
        nbands = info.get("bands", 1)
        grey   = self._npy_grey_var.get()

        r = max(0, min(self._npy_r_var.get(), nbands - 1))
        g = max(0, min(self._npy_g_var.get(), nbands - 1))
        b = max(0, min(self._npy_b_var.get(), nbands - 1))

        try:
            if grey:
                pil = load_npy_band(path, r)
            else:
                pil = load_npy_preview(path, r, g, b)
            self._npy_bands = (r, g, b)
            self._pil_cache[self.index] = pil
            self._redraw()
        except Exception as exc:
            messagebox.showerror("NPY error", str(exc))

    def _setup_npy_panel(self, filepath: str):
        """Populate the NPY panel spinboxes and metadata label."""
        info   = self._npy_info
        nbands = info.get("bands", 1)
        shape  = info.get("shape", ())

        # Default false-colour band selection (geometric — no wavelength metadata)
        if self._npy_bands is None:
            r, g, b = _estimate_rgb_bands(nbands, None)
            self._npy_r_var.set(r)
            self._npy_g_var.set(g)
            self._npy_b_var.set(b)
            self._npy_bands = (r, g, b)
        else:
            for ch, idx in zip(("r", "g", "b"), self._npy_bands):
                getattr(self, f"_npy_{ch}_var").set(min(idx, nbands - 1))

        meta_str = (f"{info.get('rows','?')} × {info.get('cols','?')} × "
                    f"{nbands} bands  |  {info.get('dtype','?')}")
        self._npy_meta_lbl.config(text=meta_str)

    # ── High-quality export ───────────────────────────────────────────────────

    def _npy_save_hq_slice(self):
        """Save the currently displayed NPY band as a 16-bit TIFF at full resolution."""
        if not self._is_npy_hyper_active():
            return
        path  = self.files[self.index]
        stem  = Path(path).stem
        band  = self._npy_band_idx
        try:
            pil16 = _build_hq_npy_band(path, band)
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))
            return
        out = filedialog.asksaveasfilename(
            parent=self,
            title=f"Save HQ band {band}",
            initialfile=f"{stem}_band{band:04d}_hq.tif",
            defaultextension=".tif",
            filetypes=[
                ("16-bit TIFF (lossless)", "*.tif *.tiff"),
                ("PNG  (8-bit)",           "*.png"),
                ("All files",              "*.*"),
            ],
        )
        if not out:
            return
        try:
            ext = Path(out).suffix.lower()
            if ext in (".tif", ".tiff"):
                pil16.save(out, format="TIFF", compression="tiff_lzw")
            else:
                # Convert 16-bit grey → 8-bit for PNG
                arr = np.array(pil16, dtype=np.uint16)
                pil8 = Image.fromarray((arr >> 8).astype(np.uint8), "L")
                pil8.save(out)
            messagebox.showinfo("Saved", f"Saved band {band} to:\n{out}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def _npy_save_hq_rgb(self):
        """Save the current NPY false-colour RGB composite at full resolution."""
        if not self._is_npy_hyper_active():
            return
        path = self.files[self.index]
        stem = Path(path).stem
        r, g, b = self._npy_bands or _estimate_rgb_bands(
            self._npy_info.get("bands", 1), None)
        try:
            pil = _build_hq_npy_rgb(path, r, g, b)
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))
            return
        _save_hq_pil(pil, self, f"{stem}_rgb_B{r}-{g}-{b}")

    def _envi_save_hq_slice(self):
        """Save the currently displayed ENVI band as a 16-bit TIFF at full resolution."""
        if not self._is_envi_active():
            return
        path      = self.files[self.index]
        data_file = self._envi_info.get("data_file")
        stem      = Path(path).stem
        band      = self._envi_band_idx
        try:
            pil16 = _build_hq_envi_band(path, data_file, band)
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))
            return
        out = filedialog.asksaveasfilename(
            parent=self,
            title=f"Save HQ band {band}",
            initialfile=f"{stem}_band{band:04d}_hq.tif",
            defaultextension=".tif",
            filetypes=[
                ("16-bit TIFF (lossless)", "*.tif *.tiff"),
                ("PNG  (8-bit)",           "*.png"),
                ("All files",              "*.*"),
            ],
        )
        if not out:
            return
        try:
            ext = Path(out).suffix.lower()
            if ext in (".tif", ".tiff"):
                pil16.save(out, format="TIFF", compression="tiff_lzw")
            else:
                arr = np.array(pil16, dtype=np.uint16)
                pil8 = Image.fromarray((arr >> 8).astype(np.uint8), "L")
                pil8.save(out)
            messagebox.showinfo("Saved", f"Saved band {band} to:\n{out}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def _envi_save_hq_rgb(self):
        """Save the current ENVI false-colour RGB composite at full resolution."""
        if not self._is_envi_active():
            return
        path      = self.files[self.index]
        data_file = self._envi_info.get("data_file")
        stem      = Path(path).stem
        r = self._envi_r_var.get()
        g = self._envi_g_var.get()
        b = self._envi_b_var.get()
        try:
            pil = _build_hq_envi_rgb(path, data_file, r, g, b)
        except Exception as exc:
            messagebox.showerror("Export error", str(exc))
            return
        _save_hq_pil(pil, self, f"{stem}_rgb_B{r}-{g}-{b}")

    @staticmethod
    def _fit_size(iw: int, ih: int, max_w: int, max_h: int) -> tuple[int, int]:
        """Return (w, h) scaled to fit within max_w × max_h, preserving aspect ratio."""
        scale = min(max_w / iw, max_h / ih, 1.0)
        return int(iw * scale), int(ih * scale)

    def _on_resize(self, _event):
        if self.files:
            self._redraw()

    # ── Zoom & pan ────────────────────────────────────────────────────────────

    def _zoom_in(self):
        self._set_zoom(self._zoom * 1.25)

    def _zoom_out(self):
        self._set_zoom(self._zoom / 1.25)

    def _zoom_reset(self):
        self._zoom  = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._redraw()

    def _set_zoom(self, new_zoom: float):
        self._zoom = max(self._zoom_min, min(self._zoom_max, new_zoom))
        self._redraw()

    def _on_mousewheel(self, event):
        # Determine scroll direction across platforms
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        else:
            delta = event.delta  # Windows: ±120 multiples

        factor = 1.1 if delta > 0 else (1 / 1.1)
        # Zoom toward the cursor position
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        cx, cy = cw / 2, ch / 2
        mx, my = event.x - cx, event.y - cy
        # Shift pan so the pixel under the cursor stays fixed
        self._pan_x = mx + (self._pan_x - mx) * factor
        self._pan_y = my + (self._pan_y - my) * factor
        self._set_zoom(self._zoom * factor)

    def _on_drag_start(self, event):
        self._drag_start      = (event.x, event.y)
        self._drag_pan_start  = (self._pan_x, self._pan_y)
        self.canvas.config(cursor="fleur")

    def _on_drag_move(self, event):
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._pan_x = self._drag_pan_start[0] + dx
        self._pan_y = self._drag_pan_start[1] + dy
        self._redraw()

    # ── Tool mode dispatcher ──────────────────────────────────────────────────

    def _on_press(self, event):
        if self._tool == "lasso":
            self._lasso_start(event)
        else:
            self._on_drag_start(event)

    def _on_motion(self, event):
        if self._tool == "lasso":
            self._lasso_extend(event)
        else:
            self._on_drag_move(event)

    def _on_release(self, event):
        if self._tool == "lasso":
            self._lasso_close(event)
        else:
            self.canvas.config(cursor="")

    # ── Lasso tool ────────────────────────────────────────────────────────────

    def _toggle_lasso(self):
        if self._tool == "lasso":
            self._tool = "pan"
            self.btn_lasso.config(bg=self.SURFACE, fg=self.FG)
            self.canvas.config(cursor="")
            self._lasso_clear()
        else:
            self._tool = "lasso"
            self.btn_lasso.config(bg=self.ACCENT, fg=self.BG)
            self.canvas.config(cursor="crosshair")

    def _lasso_start(self, event):
        self._lasso_clear()
        self._lasso_points = [(event.x, event.y)]

    def _lasso_extend(self, event):
        pt = (event.x, event.y)
        self._lasso_points.append(pt)
        # Redraw overlay without full image re-render for speed
        self._draw_lasso_overlay()

    def _lasso_close(self, event):
        if len(self._lasso_points) < 3:
            return
        self._lasso_points.append(self._lasso_points[0])   # close loop visually
        self._draw_lasso_overlay(closed=True)
        # Show action popup near the centroid
        xs = [p[0] for p in self._lasso_points]
        ys = [p[1] for p in self._lasso_points]
        cx = int(sum(xs) / len(xs))
        cy = int(sum(ys) / len(ys))
        self._show_lasso_menu(cx, cy)

    def _draw_lasso_overlay(self, closed=False):
        """Redraw image then paint lasso polygon on top."""
        self._redraw()
        pts = self._lasso_points
        if len(pts) < 2:
            return
        flat = [c for pt in pts for c in pt]
        if closed:
            self._lasso_item = self.canvas.create_polygon(
                flat, outline=self.ACCENT, fill=self.ACCENT,
                stipple="gray25", width=2)
        else:
            self.canvas.create_line(flat, fill=self.ACCENT, width=2,
                                    smooth=True, tags="lasso_line")

    def _lasso_clear(self):
        self._lasso_points = []
        self._lasso_item   = None
        self.canvas.delete("lasso_line")
        self._redraw()

    def _show_lasso_menu(self, cx: int, cy: int):
        """Tiny floating menu with crop/save/copy actions."""
        menu = tk.Toplevel(self)
        menu.overrideredirect(True)
        menu.configure(bg=self.BORDER)

        # Position near centroid but keep on screen
        wx = self.winfo_rootx() + cx + 12
        wy = self.winfo_rooty() + cy + 12
        menu.geometry(f"+{wx}+{wy}")

        btn = dict(bg=self.SURFACE, fg=self.FG, relief="flat",
                   font=("Courier New", 9), cursor="hand2",
                   activebackground=self.ACCENT, activeforeground=self.BG,
                   padx=12, pady=5, bd=0, anchor="w", width=16)

        def action(fn):
            menu.destroy()
            fn()

        tk.Button(menu, text="💾  Save crop…",
                  command=lambda: action(self._lasso_save),  **btn).pack(fill="x", pady=(1,0))
        tk.Button(menu, text="📋  Copy to clipboard",
                  command=lambda: action(self._lasso_copy),  **btn).pack(fill="x")
        cancel_btn = {**btn, "fg": "#FF5555"}
        tk.Button(menu, text="✕  Cancel",
                  command=lambda: action(self._lasso_clear),
                  **cancel_btn).pack(fill="x", pady=(0,1))

        # Dismiss if user clicks anywhere else
        menu.bind("<FocusOut>", lambda _: menu.destroy() if menu.winfo_exists() else None)
        menu.focus_force()

    def _canvas_to_image_coords(self, pts: list[tuple]) -> list[tuple]:
        """Convert canvas pixel coords → original image pixel coords."""
        pil = self._pil_cache.get(self.index)
        if pil is None:
            return pts
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        base_w, base_h = self._fit_size(pil.width, pil.height, cw, ch)
        disp_w = base_w * self._zoom
        disp_h = base_h * self._zoom
        img_x0 = cw / 2 + self._pan_x - disp_w / 2
        img_y0 = ch / 2 + self._pan_y - disp_h / 2
        sx = pil.width  / disp_w
        sy = pil.height / disp_h
        return [((p[0] - img_x0) * sx, (p[1] - img_y0) * sy) for p in pts]

    def _lasso_crop(self) -> Image.Image | None:
        """Return a cropped image of the lasso bounding box with the selection masked."""
        from PIL import ImageDraw
        pil = self._pil_cache.get(self.index)
        if pil is None or len(self._lasso_points) < 3:
            return None

        img_pts = self._canvas_to_image_coords(self._lasso_points)
        img_pts_int = [(int(x), int(y)) for x, y in img_pts]

        # Bounding box (clamped)
        xs = [p[0] for p in img_pts_int]
        ys = [p[1] for p in img_pts_int]
        x0, y0 = max(0, min(xs)), max(0, min(ys))
        x1, y1 = min(pil.width, max(xs)), min(pil.height, max(ys))
        if x1 <= x0 or y1 <= y0:
            return None

        # Mask
        mask = Image.new("L", pil.size, 0)
        ImageDraw.Draw(mask).polygon(img_pts_int, fill=255)
        rgba = pil.convert("RGBA")
        rgba.putalpha(mask)
        cropped = rgba.crop((x0, y0, x1, y1))
        return cropped

    def _lasso_save(self):
        cropped = self._lasso_crop()
        if cropped is None:
            messagebox.showwarning("Lasso", "No valid selection to save.")
            return
        src = Path(self.files[self.index])
        default = src.stem + "_crop.png"
        out = filedialog.asksaveasfilename(
            title="Save crop", initialfile=default,
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("All files", "*.*")]
        )
        if out:
            ext = Path(out).suffix.lower()
            if ext in (".jpg", ".jpeg"):
                cropped.convert("RGB").save(out, quality=95)
            else:
                cropped.save(out)
            messagebox.showinfo("Saved", f"Crop saved to:\n{out}")
        self._lasso_clear()

    def _lasso_copy(self):
        """Copy the cropped selection to the system clipboard as a PNG."""
        import io, subprocess, platform
        cropped = self._lasso_crop()
        if cropped is None:
            messagebox.showwarning("Lasso", "No valid selection to copy.")
            return
        system = platform.system()
        try:
            buf = io.BytesIO()
            if system == "Windows":
                import win32clipboard, win32con
                from PIL import ImageWin  # noqa
                cropped_rgb = cropped.convert("RGB")
                output = io.BytesIO()
                cropped_rgb.save(output, "BMP")
                data = output.getvalue()[14:]   # strip BMP file header
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_DIB, data)
                win32clipboard.CloseClipboard()
            elif system == "Darwin":
                cropped.save(buf, format="PNG")
                proc = subprocess.Popen(["osascript", "-e",
                    'set the clipboard to (read (POSIX file "/dev/stdin") as TIFF)'],
                    stdin=subprocess.PIPE)
                proc.communicate(buf.getvalue())
            else:  # Linux / X11
                cropped.save(buf, format="PNG")
                subprocess.run(["xclip", "-selection", "clipboard",
                                 "-t", "image/png"],
                               input=buf.getvalue(), check=True)
            messagebox.showinfo("Copied", "Selection copied to clipboard.")
        except Exception as exc:
            messagebox.showerror("Copy failed",
                                 f"Could not copy to clipboard:\n{exc}\n\n"
                                 "Try 'Save crop…' instead.")
        self._lasso_clear()

    # ── Colour-space transforms ───────────────────────────────────────────────

    def _is_rgb_image(self) -> bool:
        """Return True only for standard Pillow-loaded images (not ENVI/NPY hyper slices)."""
        if not self.files:
            return False
        ext = Path(self.files[self.index]).suffix.lower()
        if ext in PILLOW_EXTENSIONS | CAMERA_RAW_EXTENSIONS | PLAIN_RAW_EXTENSIONS:
            return True
        # Allow simple (grey / rgb / rgba) NPY files, but not hyperspectral cubes
        if ext in NPY_EXTENSIONS:
            return self._npy_info.get("kind", "hyper") != "hyper"
        return False

    def _transform_negative(self):
        """Display the photographic negative of the current image."""
        if not self._is_rgb_image():
            messagebox.showwarning("Not supported",
                "Negative is only available for standard RGB images (PNG, JPG, etc.).")
            return
        pil = self._pil_cache.get(self.index)
        if pil is None:
            return
        import numpy as np
        arr = np.array(pil.convert("RGB"), dtype=np.uint8)
        neg = 255 - arr
        self._show_transformed(Image.fromarray(neg, "RGB"), "NEGATIVE")

    def _transform_hsv(self):
        """Split image into H, S, V greyscale channels and show them side by side."""
        if not self._is_rgb_image():
            messagebox.showwarning("Not supported",
                "HSV conversion is only available for standard RGB images.")
            return
        pil = self._pil_cache.get(self.index)
        if pil is None:
            return
        arr = np.array(pil.convert("RGB"), dtype=np.float32) / 255.0
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        cmax  = np.max(arr, axis=2)
        cmin  = np.min(arr, axis=2)
        delta = cmax - cmin

        # Value
        V = cmax

        # Saturation — guard against divide-by-zero where cmax == 0
        with np.errstate(invalid="ignore", divide="ignore"):
            S = np.where(cmax > 0, delta / cmax, 0.0)

        # Hue (0–360 → 0–255)
        H = np.zeros_like(cmax)
        m  = delta > 0
        mr = m & (cmax == r)
        mg = m & (cmax == g)
        mb = m & (cmax == b)
        with np.errstate(invalid="ignore", divide="ignore"):
            H[mr] = (60.0 * ((g[mr] - b[mr]) / delta[mr])) % 360.0
            H[mg] = (60.0 * ((b[mg] - r[mg]) / delta[mg]) + 120.0) % 360.0
            H[mb] = (60.0 * ((r[mb] - g[mb]) / delta[mb]) + 240.0) % 360.0
        H = (H / 360.0 * 255.0).astype(np.uint8)
        S = (np.clip(S, 0.0, 1.0) * 255.0).astype(np.uint8)
        V = (np.clip(V, 0.0, 1.0) * 255.0).astype(np.uint8)

        channels = [
            ("H  (Hue)",        Image.fromarray(H, "L")),
            ("S  (Saturation)", Image.fromarray(S, "L")),
            ("V  (Value)",      Image.fromarray(V, "L")),
        ]
        self._show_channels("HSV", channels)

    def _transform_lab(self):
        """Split image into L*, a*, b* greyscale channels and show them side by side."""
        if not self._is_rgb_image():
            messagebox.showwarning("Not supported",
                "LAB conversion is only available for standard RGB images.")
            return
        pil = self._pil_cache.get(self.index)
        if pil is None:
            return
        arr = np.array(pil.convert("RGB"), dtype=np.float32) / 255.0
        # Linearise sRGB
        mask = arr > 0.04045
        arr[mask]  = ((arr[mask] + 0.055) / 1.055) ** 2.4
        arr[~mask] = arr[~mask] / 12.92
        # sRGB → XYZ (D65)
        M = np.array([[0.4124564, 0.3575761, 0.1804375],
                      [0.2126729, 0.7151522, 0.0721750],
                      [0.0193339, 0.1191920, 0.9503041]])
        xyz = arr @ M.T
        xyz /= np.array([0.95047, 1.00000, 1.08883])
        # XYZ → L*a*b*
        eps, kap = 0.008856, 903.3
        with np.errstate(invalid="ignore"):
            fx = np.where(xyz > eps, xyz ** (1.0 / 3.0), (kap * xyz + 16.0) / 116.0)
        L_ch = 116.0 * fx[..., 1] - 16.0          # 0–100
        a_ch = 500.0 * (fx[..., 0] - fx[..., 1])  # ~-128 to +127
        b_ch = 200.0 * (fx[..., 1] - fx[..., 2])  # ~-128 to +127

        def stretch(ch):
            lo, hi = ch.min(), ch.max()
            if hi > lo:
                ch = (ch - lo) / (hi - lo) * 255.0
            else:
                ch = np.zeros_like(ch)
            return ch.astype(np.uint8)

        channels = [
            ("L*  (Lightness)",   Image.fromarray(stretch(L_ch), "L")),
            ("a*  (Green→Red)",   Image.fromarray(stretch(a_ch), "L")),
            ("b*  (Blue→Yellow)", Image.fromarray(stretch(b_ch), "L")),
        ]
        self._show_channels("LAB", channels)

    def _show_transformed(self, img: "Image.Image", label: str):
        """Single-image popup (used by NEG and any other single-result transforms)."""
        win = tk.Toplevel(self)
        win.title(f"{label} — {Path(self.files[self.index]).name}")
        win.configure(bg=self.BG)
        max_w, max_h = 900, 700
        w, h = img.size
        scale = min(max_w / w, max_h / h, 1.0)
        disp  = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        photo = ImageTk.PhotoImage(disp)
        lbl = tk.Label(win, image=photo, bg=self.BG)
        lbl.image = photo
        lbl.pack(padx=12, pady=12)
        btn_style = dict(bg=self.SURFACE, fg=self.FG, relief="flat",
                         font=("Courier New", 10), cursor="hand2",
                         activebackground=self.ACCENT, activeforeground=self.BG,
                         padx=14, pady=6, bd=0)
        bar = tk.Frame(win, bg=self.BG)
        bar.pack(pady=(0, 10))
        def save_it():
            src = Path(self.files[self.index])
            out = filedialog.asksaveasfilename(
                title=f"Save {label}", initialfile=f"{src.stem}_{label.lower()}.png",
                defaultextension=".png",
                filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("All files", "*.*")])
            if out:
                (img.convert("RGB") if Path(out).suffix.lower() in (".jpg", ".jpeg") else img).save(out)
                messagebox.showinfo("Saved", f"Saved to:\n{out}")
        tk.Button(bar, text="💾  Save…", command=save_it, **btn_style).pack(side="left", padx=6)
        tk.Button(bar, text="✕  Close", command=win.destroy,
                  bg=self.SURFACE, fg="#FF5555", relief="flat",
                  font=("Courier New", 10), cursor="hand2",
                  activebackground="#FF5555", activeforeground=self.BG,
                  padx=14, pady=6, bd=0).pack(side="left", padx=6)

    def _show_channels(self, label: str, channels: list):
        """
        Popup showing 3 greyscale channel images side by side.
        channels: list of (name, PIL.Image in mode "L") tuples.
        """
        win = tk.Toplevel(self)
        src_name = Path(self.files[self.index]).name
        win.title(f"{label} Channels — {src_name}")
        win.configure(bg=self.BG)
        win.resizable(True, True)

        tk.Label(win, text=f"{label}  CHANNEL  SPLIT",
                 font=("Courier New", 13, "bold"), bg=self.BG, fg=self.ACCENT).pack(pady=(14, 2))
        tk.Label(win, text=src_name, font=("Courier New", 8),
                 bg=self.BG, fg=self.FG_DIM).pack(pady=(0, 10))

        img_frame = tk.Frame(win, bg=self.BG)
        img_frame.pack(padx=16, pady=4)

        thumb_max  = 360
        photo_refs = []

        def make_thumb(img):
            w, h  = img.size
            scale = min(thumb_max / w, thumb_max / h, 1.0)
            disp  = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            ph    = ImageTk.PhotoImage(disp)
            photo_refs.append(ph)
            return ph

        def save_one(ch_img, ch_name):
            stem = Path(self.files[self.index]).stem
            safe = ch_name.split()[0].replace("*", "").lower()
            out  = filedialog.asksaveasfilename(
                title=f"Save {ch_name}",
                initialfile=f"{stem}_{label.lower()}_{safe}.png",
                defaultextension=".png",
                filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("All files", "*.*")])
            if out:
                ext = Path(out).suffix.lower()
                (ch_img.convert("RGB") if ext in (".jpg", ".jpeg") else ch_img).save(out)
                messagebox.showinfo("Saved", f"Saved:\n{out}")

        def save_all():
            folder = filedialog.askdirectory(title="Choose folder to save all channels")
            if not folder:
                return
            stem  = Path(self.files[self.index]).stem
            saved = []
            for ch_name, ch_img in channels:
                safe = ch_name.split()[0].replace("*", "").lower()
                out  = str(Path(folder) / f"{stem}_{label.lower()}_{safe}.png")
                ch_img.save(out)
                saved.append(out)
            messagebox.showinfo("Saved All", "Saved:\n" + "\n".join(saved))

        btn_s = dict(bg=self.SURFACE, fg=self.FG, relief="flat",
                     font=("Courier New", 9), cursor="hand2",
                     activebackground=self.ACCENT, activeforeground=self.BG,
                     padx=10, pady=5, bd=0)

        for ch_name, ch_img in channels:
            col = tk.Frame(img_frame, bg=self.BG)
            col.pack(side="left", padx=10)
            tk.Label(col, text=ch_name, font=("Courier New", 10, "bold"),
                     bg=self.BG, fg=self.ACCENT).pack(pady=(0, 4))
            tk.Label(col, image=make_thumb(ch_img), bg=self.BORDER,
                     relief="flat", borderwidth=1).pack()
            tk.Button(col, text="💾  Save",
                      command=lambda i=ch_img, n=ch_name: save_one(i, n),
                      **btn_s).pack(pady=(8, 0))

        bar = tk.Frame(win, bg=self.BG)
        bar.pack(pady=14)
        tk.Button(bar, text="💾  Save All", command=save_all,
                  bg=self.ACCENT, fg=self.BG, relief="flat",
                  font=("Courier New", 10, "bold"), cursor="hand2",
                  activebackground=self.FG, activeforeground=self.BG,
                  padx=16, pady=7, bd=0).pack(side="left", padx=8)
        tk.Button(bar, text="✕  Close", command=win.destroy,
                  bg=self.SURFACE, fg="#FF5555", relief="flat",
                  font=("Courier New", 10), cursor="hand2",
                  activebackground="#FF5555", activeforeground=self.BG,
                  padx=16, pady=7, bd=0).pack(side="left", padx=8)

        win._photo_refs = photo_refs

    # ── Brightness / Contrast / Saturation adjustment window ──────────────────

    def _open_adjust_window(self):
        """Live adjustment popup: Brightness, Contrast, Saturation sliders."""
        if not self._is_rgb_image():
            messagebox.showwarning("Not supported",
                "Adjustments are only available for standard RGB images.")
            return
        pil = self._pil_cache.get(self.index)
        if pil is None:
            return

        from PIL import ImageEnhance

        win = tk.Toplevel(self)
        src_name = Path(self.files[self.index]).name
        win.title(f"Adjust — {src_name}")
        win.configure(bg=self.BG)
        win.resizable(False, False)

        # ── Preview ──
        PREV_MAX = 520
        orig = pil.convert("RGB")
        ow, oh = orig.size
        prev_scale = min(PREV_MAX / ow, PREV_MAX / oh, 1.0)
        prev_w = max(1, int(ow * prev_scale))
        prev_h = max(1, int(oh * prev_scale))
        orig_small = orig.resize((prev_w, prev_h), Image.LANCZOS)  # base for re-apply

        preview_lbl = tk.Label(win, bg=self.BG)
        preview_lbl.pack(padx=16, pady=(14, 6))
        _prev_photo = [None]   # mutable container to avoid GC

        def refresh_preview(*_):
            br  = brightness_var.get() / 100.0   # 1.0 = neutral
            con = contrast_var.get()   / 100.0
            sat = saturation_var.get() / 100.0
            img = orig_small.copy()
            img = ImageEnhance.Brightness(img).enhance(br)
            img = ImageEnhance.Contrast(img).enhance(con)
            img = ImageEnhance.Color(img).enhance(sat)
            ph  = ImageTk.PhotoImage(img)
            _prev_photo[0] = ph
            preview_lbl.config(image=ph)

        # ── Slider panel ──
        panel = tk.Frame(win, bg=self.SURFACE, padx=20, pady=14)
        panel.pack(fill="x", padx=16, pady=(0, 6))

        slider_cfg = dict(
            orient="horizontal", length=380,
            bg=self.SURFACE, fg=self.FG, troughcolor=self.BORDER,
            highlightthickness=0, sliderrelief="flat",
            activebackground=self.ACCENT, showvalue=False, bd=0,
        )
        label_cfg  = dict(bg=self.SURFACE, fg=self.FG, font=("Courier New", 10), width=14, anchor="w")
        val_cfg    = dict(bg=self.SURFACE, fg=self.ACCENT, font=("Courier New", 10, "bold"), width=5)

        def make_slider(row, name, var, lo, hi, neutral):
            tk.Label(panel, text=name, **label_cfg).grid(row=row, column=0, pady=6, sticky="w")
            val_lbl = tk.Label(panel, text=f"{neutral:+.0f}%", **val_cfg)
            val_lbl.grid(row=row, column=2, padx=(10, 0))
            def on_change(*_):
                pct = var.get() - neutral
                val_lbl.config(text=f"{pct:+.0f}%")
                refresh_preview()
            sl = tk.Scale(panel, variable=var, from_=lo, to=hi,
                          command=on_change, **slider_cfg)
            sl.grid(row=row, column=1, padx=(10, 0))
            # Double-click to reset
            sl.bind("<Double-Button-1>", lambda _e, v=var, n=neutral: (v.set(n), refresh_preview()))
            return sl

        # Variables — all centred on 100 (= "no change")
        brightness_var  = tk.IntVar(value=100)
        contrast_var    = tk.IntVar(value=100)
        saturation_var  = tk.IntVar(value=100)

        make_slider(0, "☀  Brightness",  brightness_var,   10, 300, 100)
        make_slider(1, "◑  Contrast",    contrast_var,     10, 300, 100)
        make_slider(2, "◈  Saturation",  saturation_var,   0,  300, 100)

        tk.Label(panel, text="(double-click any slider to reset)",
                 font=("Courier New", 7), bg=self.SURFACE,
                 fg=self.FG_DIM).grid(row=3, column=0, columnspan=3, pady=(4, 0), sticky="w")

        # ── Buttons ──
        bar = tk.Frame(win, bg=self.BG)
        bar.pack(pady=12)

        btn_s = dict(relief="flat", font=("Courier New", 10), cursor="hand2",
                     padx=16, pady=7, bd=0)

        def reset_all():
            brightness_var.set(100)
            contrast_var.set(100)
            saturation_var.set(100)
            refresh_preview()

        def apply_to_full():
            """Render the adjustments at full resolution and save to file."""
            br  = brightness_var.get() / 100.0
            con = contrast_var.get()   / 100.0
            sat = saturation_var.get() / 100.0
            img = orig.copy()
            img = ImageEnhance.Brightness(img).enhance(br)
            img = ImageEnhance.Contrast(img).enhance(con)
            img = ImageEnhance.Color(img).enhance(sat)
            stem = Path(self.files[self.index]).stem
            out  = filedialog.asksaveasfilename(
                title="Save adjusted image",
                initialfile=f"{stem}_adjusted.png",
                defaultextension=".png",
                filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("All files", "*.*")])
            if out:
                ext = Path(out).suffix.lower()
                (img.convert("RGB") if ext in (".jpg", ".jpeg") else img).save(out)
                messagebox.showinfo("Saved", f"Saved to:\n{out}")

        tk.Button(bar, text="↺  Reset",   command=reset_all,
                  bg=self.SURFACE, fg=self.FG, **btn_s).pack(side="left", padx=6)
        tk.Button(bar, text="💾  Save…",  command=apply_to_full,
                  bg=self.ACCENT,  fg=self.BG, **btn_s).pack(side="left", padx=6)
        tk.Button(bar, text="✕  Close",   command=win.destroy,
                  bg=self.SURFACE, fg="#FF5555", **btn_s).pack(side="left", padx=6)

        # Draw initial preview
        refresh_preview()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _redraw(self):
        """Re-render current image respecting zoom & pan."""
        if not self.files:
            return
        cw = max(self.canvas.winfo_width(),  100)
        ch = max(self.canvas.winfo_height(), 100)

        # In ENVI band-scrub mode use the slice;
        # in NPY hyper band-scrub mode use the NPY slice;
        # otherwise use the RGB composite cache
        if self._is_envi_active() and self._envi_slice_pil is not None:
            pil = self._envi_slice_pil
        elif self._is_npy_hyper_active() and self._npy_slice_pil is not None:
            pil = self._npy_slice_pil
        else:
            pil = self._pil_cache.get(self.index)
        if pil is None:
            return

        # Compute target size
        base_w, base_h = self._fit_size(pil.width, pil.height, cw, ch)
        tw = max(1, int(base_w * self._zoom))
        th = max(1, int(base_h * self._zoom))

        zoomed = pil.resize((tw, th), Image.LANCZOS)
        photo  = ImageTk.PhotoImage(zoomed)

        self.canvas.delete("all")
        x = cw // 2 + int(self._pan_x)
        y = ch // 2 + int(self._pan_y)
        self.canvas.create_image(x, y, anchor="center", image=photo)
        self._displayed = photo   # prevent GC

        pct = int(self._zoom * 100)
        self.lbl_zoom.config(text=f"{pct}%")
        self.canvas.config(cursor="fleur" if self._zoom > 1.0 else "")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ImageViewer()
    app.mainloop()