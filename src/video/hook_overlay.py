"""
HookOverlayRenderer — cinematic folk-title overlays for long videos and Shorts.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class HookOverlayRenderer:
    GOLD = (224, 184, 86, 255)
    IVORY = (232, 226, 210, 255)

    def render_long(self, city_name: str, title: str, output_path: Path) -> Path:
        return self._render(
            city_name=city_name,
            title=title,
            output_path=output_path,
            size=(1920, 1080),
            origin=(90, 360),
            max_width=820,
            title_size=150,
            region_size=46,
            wrap_width=13,
            dark_left=160,
            dark_bottom=150,
        )

    def render_short(self, city_name: str, title: str, output_path: Path) -> Path:
        return self._render(
            city_name=city_name,
            title=title,
            output_path=output_path,
            size=(1080, 1920),
            origin=(76, 930),
            max_width=760,
            title_size=152,
            region_size=44,
            wrap_width=10,
            dark_left=190,
            dark_bottom=170,
        )

    def _render(
        self,
        city_name: str,
        title: str,
        output_path: Path,
        size: tuple[int, int],
        origin: tuple[int, int],
        max_width: int,
        title_size: int,
        region_size: int,
        wrap_width: int,
        dark_left: int,
        dark_bottom: int,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        image = Image.new("RGBA", size, (0, 0, 0, 0))
        self._shade(image, dark_left, dark_bottom)
        draw = ImageDraw.Draw(image)

        lines = self._title_lines(title or city_name, wrap_width, max_lines=3)
        font = self._fit_font(lines, max_width=max_width, start_size=title_size, min_size=58)
        x, y = origin
        line_gap = 18 if size[0] <= 1080 else 22
        y = self._fit_vertical_position(
            draw=draw,
            x=x,
            y=y,
            lines=lines,
            font=font,
            line_gap=line_gap,
            canvas_height=size[1],
            bottom_padding=170 if size[0] <= 1080 else 260,
        )
        for line in lines:
            self._draw_title(draw, (x, y), line, font)
            bbox = draw.textbbox((x, y), line, font=font, stroke_width=3)
            y = bbox[3] + line_gap

        region = f"{self._tr_upper(city_name)} YÖRESİ"
        region_font = self._font(region_size, "wide")
        draw.text((x + 4, y + 28), region, fill=self.GOLD, font=region_font)
        self._draw_ornament(draw, x + 6, y + 88, width=260 if size[0] <= 1080 else 310)

        image.save(output_path, "PNG")
        return output_path

    @staticmethod
    def _fit_vertical_position(
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        lines: list[str],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        line_gap: int,
        canvas_height: int,
        bottom_padding: int,
    ) -> int:
        probe_y = y
        for line in lines:
            bbox = draw.textbbox((x, probe_y), line, font=font, stroke_width=3)
            probe_y = bbox[3] + line_gap
        block_bottom = probe_y + 112
        max_bottom = canvas_height - bottom_padding
        if block_bottom <= max_bottom:
            return y
        return max(48, y - (block_bottom - max_bottom))

    @staticmethod
    def _shade(image: Image.Image, left_strength: int, bottom_strength: int) -> None:
        width, height = image.size
        px = image.load()
        for y in range(height):
            bottom = max(0, y - int(height * 0.48)) / max(1, int(height * 0.52))
            for x in range(width):
                left = max(0, 1 - x / (width * 0.72))
                alpha = int(min(230, left * left_strength + bottom * bottom_strength))
                if alpha:
                    px[x, y] = (0, 0, 0, alpha)

    @classmethod
    def _draw_title(
        cls,
        draw: ImageDraw.ImageDraw,
        pos: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        x, y = pos
        draw.text((x + 5, y + 6), text, fill=(0, 0, 0, 190), font=font, stroke_width=4, stroke_fill=(0, 0, 0, 190))
        draw.text((x, y), text, fill=cls.IVORY, font=font, stroke_width=3, stroke_fill=(45, 41, 34, 230))

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
    def _title_lines(title: str, width: int, max_lines: int) -> list[str]:
        words = HookOverlayRenderer._tr_upper(title.strip()).split()[:4]
        return textwrap.wrap(" ".join(words), width=width)[:max_lines] or ["TURKU"]

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
            font = cls._font(size, "condensed")
            widest = max(draw.textbbox((0, 0), line, font=font, stroke_width=3)[2] for line in lines)
            if widest <= max_width:
                return font
        return cls._font(min_size, "condensed")

    @staticmethod
    def _font(size: int, kind: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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
        for path in candidates[kind]:
            if Path(path).exists():
                return ImageFont.truetype(path, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _tr_upper(text: str) -> str:
        return text.translate(str.maketrans({"i": "İ", "ı": "I"})).upper()
