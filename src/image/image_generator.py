"""
ImageGenerator — generates atmospheric background images for Anatolian Nights.

Model selection (config-driven):
  flux-schnell  → black-forest-labs/FLUX.1-schnell via diffusers (best quality)
  sdxl-turbo    → stabilityai/sdxl-turbo via diffusers (fallback)
  placeholder   → dark atmospheric PIL gradient (no AI model required)

Device: MPS (Apple Silicon) when available, CPU fallback.
Output: generated size → resized to 1920x1080 via Pillow.
"""

import logging
import random
from pathlib import Path

from PIL import Image

from src.config.settings import settings

logger = logging.getLogger(__name__)

_pipeline_cache: dict[str, object] = {}


def _get_pipeline(model_key: str):
    if model_key in _pipeline_cache:
        return _pipeline_cache[model_key]

    import torch
    from diffusers import AutoPipelineForText2Image

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float16 if device == "mps" else torch.float32

    if model_key == "flux-schnell":
        model_id = "black-forest-labs/FLUX.1-schnell"
        logger.info("Loading FLUX.1-schnell on %s...", device)
        pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=dtype)
    else:  # sdxl-turbo
        model_id = "stabilityai/sdxl-turbo"
        logger.info("Loading SDXL-Turbo on %s...", device)
        pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=dtype, variant="fp16" if dtype == torch.float16 else None)

    pipe = pipe.to(device)
    _pipeline_cache[model_key] = pipe
    logger.info("%s loaded.", model_key)
    return pipe


def _atmospheric_placeholder(width: int, height: int, seed: int | None = None) -> Image.Image:
    """
    Dark atmospheric gradient with subtle noise — deep blue-black Anatolian night palette.
    Used when no AI model is available.
    """
    import struct

    rng = random.Random(seed)
    img = Image.new("RGB", (width, height))
    pixels = img.load()

    # Deep blue-black gradient: top = very dark navy, bottom = near-black
    top_color = (8, 12, 28)    # deep navy
    mid_color = (4, 8, 18)     # darker mid
    bottom_color = (2, 4, 10)  # near-black bottom

    for y in range(height):
        t = y / height
        if t < 0.5:
            t2 = t * 2
            r = int(top_color[0] + (mid_color[0] - top_color[0]) * t2)
            g = int(top_color[1] + (mid_color[1] - top_color[1]) * t2)
            b = int(top_color[2] + (mid_color[2] - top_color[2]) * t2)
        else:
            t2 = (t - 0.5) * 2
            r = int(mid_color[0] + (bottom_color[0] - mid_color[0]) * t2)
            g = int(mid_color[1] + (bottom_color[1] - mid_color[1]) * t2)
            b = int(mid_color[2] + (bottom_color[2] - mid_color[2]) * t2)
        for x in range(width):
            noise = rng.randint(-6, 6)
            pixels[x, y] = (
                max(0, min(255, r + noise)),
                max(0, min(255, g + noise)),
                max(0, min(255, b + noise)),
            )

    return img


class ImageGenerator:
    TARGET_WIDTH = 1920
    TARGET_HEIGHT = 1080

    def generate(
        self,
        image_prompt: str,
        negative_prompt: str,
        output_path: Path,
        target_width: int | None = None,
        target_height: int | None = None,
        gen_width: int | None = None,
        gen_height: int | None = None,
    ) -> Path:
        """
        Generate image from prompt and save to output_path as PNG.
        Returns output_path.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        w = target_width or self.TARGET_WIDTH
        h = target_height or self.TARGET_HEIGHT

        model_key = getattr(getattr(settings, "image", None), "model", "placeholder") or "placeholder"

        if model_key == "placeholder":
            logger.info("Using atmospheric placeholder image (no AI model configured).")
            img = _atmospheric_placeholder(w, h)
            img.save(str(output_path), format="PNG")
            logger.info("Placeholder image saved to %s", output_path)
            return output_path

        # AI model path — lazy import torch/diffusers
        try:
            import torch

            pipe = _get_pipeline(model_key)

            if model_key == "flux-schnell":
                gw = gen_width or 1360
                gh = gen_height or 768
                num_steps = 4
                guidance = 0.0
            else:  # sdxl-turbo
                gw = gen_width or 1024
                gh = gen_height or 576
                num_steps = 4
                guidance = 0.0

            logger.info("Generating image with %s: %s...", model_key, image_prompt[:80])
            with torch.inference_mode():
                result = pipe(
                    prompt=image_prompt,
                    negative_prompt=negative_prompt or "text, watermark, people, faces, blurry",
                    num_inference_steps=num_steps,
                    guidance_scale=guidance,
                    width=gw,
                    height=gh,
                )
            img: Image.Image = result.images[0]
        except Exception as exc:
            logger.warning("AI image generation failed (%s), using placeholder: %s", model_key, exc)
            img = _atmospheric_placeholder(w, h)

        img = img.resize((w, h), Image.LANCZOS)
        img.save(str(output_path), format="PNG")
        logger.info("Image saved to %s", output_path)
        return output_path

