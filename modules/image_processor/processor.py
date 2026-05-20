from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

from services.file_service import build_timestamped_filename, suffix_lower


SUPPORTED_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}
SUPPORTED_OUTPUT_FORMATS = ("JPG", "PNG", "WEBP")


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or "transparency" in image.info


def _resize_with_padding(image: Image.Image, target_width: int, target_height: int, preserve_alpha: bool) -> Image.Image:
    fitted = ImageOps.contain(image, (target_width, target_height), method=Image.Resampling.LANCZOS)
    x_offset = (target_width - fitted.width) // 2
    y_offset = (target_height - fitted.height) // 2

    if preserve_alpha:
        base = Image.new("RGBA", (target_width, target_height), (255, 255, 255, 0))
        overlay = fitted.convert("RGBA") if fitted.mode != "RGBA" else fitted
        base.paste(overlay, (x_offset, y_offset), overlay)
        return base

    base = Image.new("RGB", (target_width, target_height), (255, 255, 255))
    overlay = fitted.convert("RGB") if fitted.mode != "RGB" else fitted
    base.paste(overlay, (x_offset, y_offset))
    return base


def process_image(
    file_bytes: bytes,
    source_name: str,
    target_width: int,
    target_height: int,
    output_format: str,
    quality: int,
) -> tuple[bytes, str, dict[str, object]]:
    if target_width < 1 or target_height < 1:
        raise ValueError("目标宽高必须大于 0。")

    output_format = output_format.upper()
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise ValueError("不支持的输出格式。")

    with Image.open(BytesIO(file_bytes)) as image:
        image = ImageOps.exif_transpose(image)
        original_size = image.size
        original_mode = image.mode
        preserve_alpha = output_format in {"PNG", "WEBP"} and _has_alpha(image)
        resized = _resize_with_padding(image, target_width, target_height, preserve_alpha)

        buffer = BytesIO()
        save_kwargs: dict[str, object]
        output_suffix: str

        if output_format == "JPG":
            save_kwargs = {
                "format": "JPEG",
                "quality": int(quality),
                "optimize": True,
                "progressive": True,
            }
            save_image = resized.convert("RGB") if resized.mode != "RGB" else resized
            output_suffix = ".jpg"
        elif output_format == "PNG":
            compress_level = int(round((100 - int(quality)) / 100 * 9))
            save_kwargs = {
                "format": "PNG",
                "optimize": True,
                "compress_level": compress_level,
            }
            save_image = resized
            output_suffix = ".png"
        else:
            save_kwargs = {
                "format": "WEBP",
                "quality": int(quality),
                "method": 6,
            }
            save_image = resized
            output_suffix = ".webp"

        save_image.save(buffer, **save_kwargs)
        buffer.seek(0)
        metadata = {
            "original_size": original_size,
            "processed_size": (target_width, target_height),
            "original_mode": original_mode,
            "output_format": output_format,
            "quality": int(quality),
            "source_suffix": suffix_lower(source_name),
        }
        return (
            buffer.getvalue(),
            build_timestamped_filename(source_name, output_suffix, prefix="image_processed"),
            metadata,
        )
