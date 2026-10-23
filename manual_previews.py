"""Decode user pictures into a small, metadata-free PNG; originals are read-only."""
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from i18n import t

SIZE = (684, 384)
FORMATS = ('PNG', 'JPEG', 'WEBP', 'BMP')


def prepare_preview(source, output):
    source = Path(source)
    if source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(t('图片超过 64 MiB，请先缩小图片'))
    try:
        opened = Image.open(source, formats=FORMATS)
    except UnidentifiedImageError as exc:
        raise ValueError(t('无法读取图片，请选择有效的 PNG、JPEG、WebP 或 BMP 文件')) from exc
    with opened as image:
        if image.width * image.height > 40_000_000:
            raise ValueError(t('图片超过 4000 万像素，请先缩小图片'))
        image.seek(0)
        image = ImageOps.exif_transpose(image).convert('RGBA')
        fitted = ImageOps.contain(image, SIZE, Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', SIZE, '#131925')
        canvas.paste(fitted, ((SIZE[0]-fitted.width)//2, (SIZE[1]-fitted.height)//2), fitted)
        canvas.save(output, format='PNG')
