"""
ImageGenerator — uses SDXL-Turbo on Apple MPS to generate
unique background images for each song.

Model: stabilityai/sdxl-turbo
Device: MPS (Apple Silicon)
Steps: 4 (Turbo optimized)
Output: 1024x576 → resized to 1920x1080 via Pillow
"""

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Lazy imports — torch + diffusers only loaded when this class is instantiated
_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    import torch
    from diffusers import AutoPipelineForText2Image

    logger.info("Loading SDXL-Turbo model on MPS...")
    pipe = AutoPipelineForText2Image.from_pretrained(
        "stabilityai/sdxl-turbo",
        torch_dtype=torch.float16,
        variant="fp16",
    )
    pipe = pipe.to("mps")
    _pipeline = pipe
    logger.info("SDXL-Turbo loaded.")
    return _pipeline


class ImageGenerator:
    TARGET_WIDTH = 1920
    TARGET_HEIGHT = 1080
    # SDXL-Turbo native output (16:9 safe ratio at low res)
    GEN_WIDTH = 1024
    GEN_HEIGHT = 576

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
        import torch

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        pipe = _get_pipeline()

        logger.info("Generating image: %s...", image_prompt[:80])

        with torch.inference_mode():
            result = pipe(
                prompt=image_prompt,
                negative_prompt=negative_prompt or "text, watermark, signature, blurry, deformed",
                num_inference_steps=4,
                guidance_scale=0.0,  # Turbo mode: guidance disabled
                width=gen_width or self.GEN_WIDTH,
                height=gen_height or self.GEN_HEIGHT,
            )

        img: Image.Image = result.images[0]

        # Upscale with LANCZOS for best quality.
        img = img.resize(
            (target_width or self.TARGET_WIDTH, target_height or self.TARGET_HEIGHT),
            Image.LANCZOS,
        )
        img.save(str(output_path), format="PNG")

        logger.info("Image saved to %s", output_path)
        return output_path
