"""
ThumbnailRenderer — cinematic folk-music cover thumbnails.
"""

import logging
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

logger = logging.getLogger(__name__)


class ThumbnailRenderer:
    WIDTH = 1280
    HEIGHT = 720
    GOLD = (224, 184, 86, 255)
    IVORY = (232, 226, 210, 255)

    def render(
        self,
        background_path: Path,
        title: str,
        city_name: str,
        output_path: Path,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Rendering thumbnail: %s", output_path)
        img = self._cover(Image.open(background_path).convert("RGB"), self.WIDTH, self.HEIGHT)
        img = ImageEnhance.Color(img).enhance(0.88)
        img = ImageEnhance.Contrast(img).enhance(1.18)
        img = ImageEnhance.Brightness(img).enhance(0.86)

        canvas = img.convert("RGBA")
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        self._cinematic_grade(overlay, left_strength=210, bottom_strength=120)
        draw = ImageDraw.Draw(overlay)

        title_lines = self._title_lines(title or city_name, max_chars=13, max_lines=2)
        title_font = self._fit_font(title_lines, max_width=690, start_size=136, min_size=82)
        x = 62
        line_gap = 18
        y = 334 if len(title_lines) == 1 else 246
        for line in title_lines:
            self._draw_distressed_text(draw, (x, y), line, title_font, self.IVORY, stroke=3)
            bbox = draw.textbbox((x, y), line, font=title_font, stroke_width=3)
            y = bbox[3] + line_gap

        region = f"{self._tr_upper(city_name)} YÖRESİ"
        region_font = self._font(34, kind="wide")
        draw.text((x + 3, y + 24), region, fill=self.GOLD, font=region_font, spacing=2)
        self._draw_ornament(draw, x + 7, y + 80, width=275)

        Image.alpha_composite(canvas, overlay).convert("RGB").save(output_path, "PNG")
        return output_path

    @classmethod
    def _cover(cls, img: Image.Image, width: int, height: int) -> Image.Image:
        img_ratio = img.width / img.height
        target_ratio = width / height
        if img_ratio > target_ratio:
            new_height = height
            new_width = int(new_height * img_ratio)
        else:
            new_width = width
            new_height = int(new_width / img_ratio)
        resized = img.resize((new_width, new_height), Image.LANCZOS)
        left = (new_width - width) // 2
        top = (new_height - height) // 2
        return resized.crop((left, top, left + width, top + height))

    @staticmethod
    def _cinematic_grade(overlay: Image.Image, left_strength: int, bottom_strength: int) -> None:
        width, height = overlay.size
        px = overlay.load()
        for y in range(height):
            bottom = max(0, y - int(height * 0.58)) / max(1, int(height * 0.42))
            for x in range(width):
                left = max(0, 1 - x / (width * 0.62))
                edge = max(0, abs(x - width / 2) / (width / 2) - 0.55) * 1.8
                alpha = int(min(235, left * left_strength + bottom * bottom_strength + edge * 90))
                if alpha:
                    px[x, y] = (0, 0, 0, alpha)

    @classmethod
    def _draw_distressed_text(
        cls,
        draw: ImageDraw.ImageDraw,
        pos: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: tuple[int, int, int, int],
        stroke: int,
    ) -> None:
        x, y = pos
        shadow = (0, 0, 0, 190)
        draw.text((x + 4, y + 5), text, fill=shadow, font=font, stroke_width=stroke + 1, stroke_fill=shadow)
        draw.text((x, y), text, fill=fill, font=font, stroke_width=stroke, stroke_fill=(35, 32, 28, 230))

        bbox = draw.textbbox((x, y), text, font=font, stroke_width=stroke)
        clip = Image.new("RGBA", (bbox[2] - bbox[0] + 12, bbox[3] - bbox[1] + 12), (0, 0, 0, 0))
        cdraw = ImageDraw.Draw(clip)
        cdraw.text((6 - bbox[0] + x, 6 - bbox[1] + y), text, fill=(255, 255, 255, 34), font=font)
        mask = Image.effect_noise(clip.size, 70).convert("L").point(lambda p: 255 if p > 152 else 0)
        texture = Image.new("RGBA", clip.size, (0, 0, 0, 34))
        draw.bitmap((bbox[0] - 6, bbox[1] - 6), Image.composite(texture, Image.new("RGBA", clip.size), mask))

    @classmethod
    def _draw_ornament(cls, draw: ImageDraw.ImageDraw, x: int, y: int, width: int) -> None:
        color = cls.GOLD
        mid = x + width // 2
        draw.line((x, y, mid - 32, y), fill=color, width=2)
        draw.line((mid + 32, y, x + width, y), fill=color, width=2)
        draw.ellipse((mid - 7, y - 7, mid + 7, y + 7), outline=color, width=2)
        draw.line((mid - 22, y - 10, mid - 10, y), fill=color, width=2)
        draw.line((mid - 22, y + 10, mid - 10, y), fill=color, width=2)
        draw.line((mid + 10, y, mid + 22, y - 10), fill=color, width=2)
        draw.line((mid + 10, y, mid + 22, y + 10), fill=color, width=2)

    @staticmethod
    def _title_lines(title: str, max_chars: int, max_lines: int) -> list[str]:
        words = ThumbnailRenderer._tr_upper(title.strip()).split()[:4]
        return textwrap.wrap(" ".join(words), width=max_chars)[:max_lines] or ["TURKU"]

    @classmethod
    def _fit_font(
        cls,
        lines: list[str],
        max_width: int,
        start_size: int,
        min_size: int,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        probe = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        draw = ImageDraw.Draw(probe)
        for size in range(start_size, min_size - 1, -3):
            font = cls._font(size, kind="condensed")
            widest = max(draw.textbbox((0, 0), line, font=font, stroke_width=3)[2] for line in lines)
            if widest <= max_width:
                return font
        return cls._font(min_size, kind="condensed")

    @staticmethod
    def _font(size: int, kind: str = "condensed") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = {
            "condensed": (
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
            ),
            "wide": (
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
            ),
        }
        for path in candidates.get(kind, candidates["condensed"]):
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _tr_upper(text: str) -> str:
        return text.translate(str.maketrans({"i": "İ", "ı": "I"})).upper()
