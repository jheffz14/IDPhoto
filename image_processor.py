"""
IDPhotoProcessor – face detection, cropping, layout generation.
Uses OpenCV for face detection and Pillow for image composition.
"""
import io
import os
import sys
import math
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

MM_PER_INCH = 25.4


def mm_to_px(mm: float, dpi: int) -> int:
    return max(1, round(mm / MM_PER_INCH * dpi))


def hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _get_cascade_path() -> str:
    """
    Resolve the Haar cascade XML path whether running:
      - normally (python app.py)
      - frozen by PyInstaller (IDPhotoApp.exe)
    PyInstaller extracts bundled data to sys._MEIPASS at runtime.
    """
    cascade_filename = "haarcascade_frontalface_alt2.xml"

    # 1. PyInstaller bundle: data is extracted to sys._MEIPASS
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
        candidate = base / "cv2" / "data" / cascade_filename
        if candidate.exists():
            return str(candidate)
        # Some PyInstaller builds flatten it differently
        for p in base.rglob(cascade_filename):
            return str(p)

    # 2. Normal run: use cv2.data.haarcascades
    candidate = Path(cv2.data.haarcascades) / cascade_filename
    if candidate.exists():
        return str(candidate)

    # 3. Last resort: search inside the cv2 package directory
    cv2_dir = Path(cv2.__file__).parent
    for p in cv2_dir.rglob(cascade_filename):
        return str(p)

    raise FileNotFoundError(
        f"Could not locate {cascade_filename}. "
        "Re-install opencv-python or check your cv2 installation."
    )


class IDPhotoProcessor:
    def __init__(self, config: dict):
        self.config = config
        self.dpi = config["app"].get("output_dpi", 300)

        cascade_path = _get_cascade_path()
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        if self.face_cascade.empty():
            raise RuntimeError(
                f"Failed to load face cascade from: {cascade_path}\n"
                "The file exists but OpenCV could not read it. "
                "Try reinstalling opencv-python."
            )

    # ── Public entry point ───────────────────────────────────────────────

    def process(self, input_path: str, output_path: str, package: dict,
                replace_background: bool = False, bg_color: str = "#ffffff"):
        """Full pipeline: detect face → crop → layout → save."""
        img = Image.open(input_path).convert("RGBA")
        img = self._auto_orient(img)

        face_img = self._smart_crop(img)

        if replace_background:
            face_img = self._replace_background(face_img, bg_color)
        else:
            face_img = face_img.convert("RGB")

        sheet = self._build_layout(face_img, package)
        sheet.save(output_path, "PNG", dpi=(self.dpi, self.dpi))

    # ── Face detection & crop ────────────────────────────────────────────

    def _smart_crop(self, img: Image.Image) -> Image.Image:
        """Detect face, return a head-centered crop with headroom."""
        cv_img = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.05, minNeighbors=4,
            minSize=(60, 60), flags=cv2.CASCADE_SCALE_IMAGE
        )

        w, h = img.size

        if len(faces) == 0:
            crop_h = int(h * 0.8)
            crop_w = min(w, crop_h)
            x0 = (w - crop_w) // 2
            y0 = 0
            return img.crop((x0, y0, x0 + crop_w, y0 + crop_h))

        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, fy, fw, fh = faces[0]

        target_face_ratio = 0.65
        desired_ph = fh / target_face_ratio
        desired_pw = desired_ph

        cx = fx + fw // 2
        headroom = fh * 0.35
        top = max(0, fy - headroom)
        left = max(0, cx - desired_pw // 2)

        crop_w = int(min(desired_pw, w))
        crop_h = int(min(desired_ph, h - top))
        left = int(max(0, min(left, w - crop_w)))
        top = int(top)

        cropped = img.crop((left, top, left + crop_w, top + crop_h))
        return cropped

    # ── Background replacement ───────────────────────────────────────────

    def _replace_background(self, img: Image.Image, bg_color: str) -> Image.Image:
        try:
            return self._grabcut_background(img, bg_color)
        except Exception:
            bg = Image.new("RGB", img.size, hex_to_rgb(bg_color))
            if img.mode == "RGBA":
                bg.paste(img, mask=img.split()[3])
            else:
                bg.paste(img)
            return bg

    def _grabcut_background(self, img: Image.Image, bg_color: str) -> Image.Image:
        rgb = img.convert("RGB")
        cv_img = cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)
        h, w = cv_img.shape[:2]

        mask = np.zeros((h, w), np.uint8)
        bg_model = np.zeros((1, 65), np.float64)
        fg_model = np.zeros((1, 65), np.float64)

        margin = max(5, int(min(w, h) * 0.05))
        rect = (margin, margin, w - 2 * margin, h - 2 * margin)

        cv2.grabCut(cv_img, mask, rect, bg_model, fg_model, 5,
                    cv2.GC_INIT_WITH_RECT)

        mask2 = np.where((mask == 2) | (mask == 0), 0, 255).astype("uint8")
        mask2 = cv2.GaussianBlur(mask2, (5, 5), 0)
        _, mask2 = cv2.threshold(mask2, 127, 255, cv2.THRESH_BINARY)

        alpha = Image.fromarray(mask2)
        result = Image.new("RGBA", rgb.size)
        result.paste(rgb, mask=alpha)

        bg = Image.new("RGBA", rgb.size, (*hex_to_rgb(bg_color), 255))
        bg.paste(result, mask=result.split()[3])
        return bg.convert("RGB")

    # ── Layout engine ────────────────────────────────────────────────────

    def _build_layout(self, face_img: Image.Image, package: dict) -> Image.Image:
        paper_id = package.get("paper_size", "a4")
        paper_info = self.config["paper_sizes"].get(paper_id, self.config["paper_sizes"]["a4"])
        orientation = package.get("orientation", "portrait")
        margin_mm = float(package.get("margin_mm", 5))
        spacing_mm = float(package.get("spacing_mm", 3))
        show_cuts = package.get("show_cut_lines", True)
        sheet_bg = package.get("background_color", "#ffffff")

        pw_mm = paper_info["width_mm"]
        ph_mm = paper_info["height_mm"]
        if orientation == "landscape":
            pw_mm, ph_mm = ph_mm, pw_mm

        sheet_w = mm_to_px(pw_mm, self.dpi)
        sheet_h = mm_to_px(ph_mm, self.dpi)
        margin_px = mm_to_px(margin_mm, self.dpi)
        spacing_px = mm_to_px(spacing_mm, self.dpi)

        sheet = Image.new("RGB", (sheet_w, sheet_h), hex_to_rgb(sheet_bg))
        draw = ImageDraw.Draw(sheet)

        items = package.get("items", [])
        photos_to_place = []
        for item in items:
            size_id = item["photo_size_id"]
            qty = item["quantity"]
            size_cfg = self.config["photo_sizes"].get(size_id, {})
            if not size_cfg:
                continue
            w_px = mm_to_px(size_cfg["width_mm"], self.dpi)
            h_px = mm_to_px(size_cfg["height_mm"], self.dpi)
            bg = size_cfg.get("background_color", "#ffffff")
            thumb = self._fit_photo(face_img, w_px, h_px, bg)
            for _ in range(qty):
                photos_to_place.append((thumb, w_px, h_px, size_id))

        cx = margin_px
        cy = margin_px
        row_h = 0
        cut_rects = []

        for thumb, w_px, h_px, size_id in photos_to_place:
            if cx + w_px > sheet_w - margin_px and cx > margin_px:
                cy += row_h + spacing_px
                cx = margin_px
                row_h = 0

            if cy + h_px > sheet_h - margin_px:
                break

            sheet.paste(thumb, (cx, cy))
            cut_rects.append((cx, cy, cx + w_px, cy + h_px))
            cx += w_px + spacing_px
            row_h = max(row_h, h_px)

        if show_cuts:
            self._draw_cut_lines(draw, cut_rects, sheet_w, sheet_h)

        return sheet

    def _fit_photo(self, src: Image.Image, w_px: int, h_px: int, bg_hex: str) -> Image.Image:
        bg_rgb = hex_to_rgb(bg_hex)
        canvas = Image.new("RGB", (w_px, h_px), bg_rgb)

        src_ratio = src.width / src.height
        tgt_ratio = w_px / h_px

        if src_ratio > tgt_ratio:
            new_w = w_px
            new_h = int(w_px / src_ratio)
        else:
            new_h = h_px
            new_w = int(h_px * src_ratio)

        resized = src.resize((new_w, new_h), Image.LANCZOS)
        x_off = (w_px - new_w) // 2
        y_off = (h_px - new_h) // 2
        canvas.paste(resized, (x_off, y_off))
        return canvas

    def _draw_cut_lines(self, draw: ImageDraw.ImageDraw, rects, sw, sh):
        dash_len = mm_to_px(3, self.dpi)
        color = "#aaaaaa"
        lw = max(1, mm_to_px(0.2, self.dpi))

        for x0, y0, x1, y1 in rects:
            ext = mm_to_px(2, self.dpi)
            offs = [(x0, y0, -1, -1), (x1, y0, 1, -1),
                    (x0, y1, -1, 1), (x1, y1, 1, 1)]
            for cx, cy, dx, dy in offs:
                draw.line([(cx + dx * ext, cy), (cx, cy)], fill=color, width=lw)
                draw.line([(cx, cy + dy * ext), (cx, cy)], fill=color, width=lw)

    # ── Format conversion ────────────────────────────────────────────────

    def convert_to_jpeg(self, png_path: str) -> io.BytesIO:
        img = Image.open(png_path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=95, dpi=(self.dpi, self.dpi))
        buf.seek(0)
        return buf

    def convert_to_pdf(self, png_path: str) -> io.BytesIO:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as rl_canvas

        img = Image.open(png_path)
        w_px, h_px = img.size
        w_pt = (w_px / self.dpi) * 72
        h_pt = (h_px / self.dpi) * 72

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(w_pt, h_pt))
        img_buf = io.BytesIO()
        img.save(img_buf, "PNG")
        img_buf.seek(0)
        c.drawImage(ImageReader(img_buf), 0, 0, width=w_pt, height=h_pt)
        c.save()
        buf.seek(0)
        return buf

    @staticmethod
    def _auto_orient(img: Image.Image) -> Image.Image:
        try:
            from PIL import ExifTags
            exif = img._getexif()
            if exif:
                for tag, val in exif.items():
                    if ExifTags.TAGS.get(tag) == "Orientation":
                        ops = {3: 180, 6: 270, 8: 90}
                        if val in ops:
                            img = img.rotate(ops[val], expand=True)
        except Exception:
            pass
        return img
