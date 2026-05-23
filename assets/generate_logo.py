"""Generate the app logo as PNG + Windows ICO.

The logo is a stylized chat-bubble (representing a Claude conversation) with
a download arrow inside (representing the export). It is drawn from scratch
with Pillow so we don't ship any third-party brand assets — re-run this
script if you ever want to tweak the colors or shape.

Two variants are produced so the chat-bubble silhouette stays readable in
both light and dark UI themes:
  * ``logo_light.png`` — chat bubble in white on a warm-orange tile.
  * ``logo_dark.png``  — chat bubble in warm-orange on a dark tile, so the
                          bubble silhouette pops against dark window chrome.

``logo.png`` is kept as a backwards-compatible alias for ``logo_light.png``.

Outputs (next to this script):
    logo.png        512x512 master (light variant, for README + fallback)
    logo_light.png  512x512 (used in light mode)
    logo_dark.png   512x512 (used in dark mode)
    logo_64.png     64x64 light variant (header thumbnail)
    logo.ico        Multi-resolution Windows icon (16, 32, 48, 64, 128, 256)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class Palette:
    """Color palette for one rendering of the logo."""
    tile_fill: tuple[int, int, int, int]
    tile_outline: tuple[int, int, int, int]
    bubble_fill: tuple[int, int, int, int]
    bubble_outline: tuple[int, int, int, int] | None
    arrow_fill: tuple[int, int, int, int]


# Light mode: white bubble on warm-orange tile (the classic).
LIGHT = Palette(
    tile_fill=(193, 95, 60, 255),       # #C15F3C
    tile_outline=(140, 60, 30, 255),    # #8C3C1E
    bubble_fill=(255, 255, 255, 255),
    bubble_outline=None,
    arrow_fill=(193, 95, 60, 255),
)

# Dark mode: a vivid orange bubble on a neutral mid-gray tile, with a
# bright outline around the bubble so it pops crisply against dark window
# chrome instead of looking dim.
DARK = Palette(
    tile_fill=(58, 58, 66, 255),        # #3A3A42 — clearly distinct from CTk dark bg
    tile_outline=(150, 150, 160, 255),  # #9696A0 — visible tile edge
    bubble_fill=(255, 140, 90, 255),    # #FF8C5A — saturated, bright orange
    bubble_outline=(255, 230, 200, 255),# #FFE6C8 — warm-white outline for contrast
    arrow_fill=(255, 255, 255, 255),    # arrow + tray are white in dark mode
)


_HERE = Path(__file__).resolve().parent


def draw_logo(palette: Palette, size: int = 512) -> Image.Image:
    """Render the logo into a fresh RGBA image of the given size + palette.

    The geometry is identical across palettes — only fills/outlines change —
    so the icon is recognisably the *same* mark in light and dark modes.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Rounded-square background tile
    pad = round(size * 0.04)
    radius = round(size * 0.22)
    draw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=radius,
        fill=palette.tile_fill,
    )

    # 2. Chat bubble (rounded rect + tail at bottom-left).
    #    Smaller than v1.0.0 so the speech-bubble silhouette reads cleanly
    #    against the tile in either mode.
    bubble_left = round(size * 0.22)
    bubble_right = size - bubble_left
    bubble_top = round(size * 0.18)
    bubble_bottom = round(size * 0.66)
    bubble_radius = round(size * 0.10)
    outline_w = max(3, size // 70) if palette.bubble_outline else 0
    draw.rounded_rectangle(
        (bubble_left, bubble_top, bubble_right, bubble_bottom),
        radius=bubble_radius,
        fill=palette.bubble_fill,
        outline=palette.bubble_outline,
        width=outline_w,
    )

    # Tail — bigger and more pronounced so the bubble shape is unmistakable.
    tail_top_y = bubble_bottom - max(2, size // 80)   # nestle the seam
    tail_inner_x = round(size * 0.42)
    tail_outer_x = round(size * 0.28)
    tail_apex_x = round(size * 0.30)
    tail_apex_y = round(size * 0.80)
    tail_points = [
        (tail_outer_x, tail_top_y),
        (tail_inner_x, tail_top_y),
        (tail_apex_x, tail_apex_y),
    ]
    draw.polygon(tail_points, fill=palette.bubble_fill)
    if palette.bubble_outline:
        # Trace the two outer edges of the tail so it has a matching border.
        draw.line(
            [tail_points[0], tail_points[2]],
            fill=palette.bubble_outline,
            width=outline_w,
        )
        draw.line(
            [tail_points[1], tail_points[2]],
            fill=palette.bubble_outline,
            width=outline_w,
        )

    # 3. Download arrow centred in the upper portion of the bubble.
    cx = size // 2
    shaft_top = round(size * 0.24)
    shaft_bottom = round(size * 0.46)
    shaft_half_w = round(size * 0.05)
    draw.rectangle(
        (cx - shaft_half_w, shaft_top, cx + shaft_half_w, shaft_bottom),
        fill=palette.arrow_fill,
    )
    # Arrowhead — chevron pointing down
    head_left = cx - round(size * 0.14)
    head_right = cx + round(size * 0.14)
    head_top = round(size * 0.41)
    head_tip_y = round(size * 0.58)
    draw.polygon(
        [(head_left, head_top), (head_right, head_top), (cx, head_tip_y)],
        fill=palette.arrow_fill,
    )

    # 4. "Tray" line at the bottom of the bubble — completes the download icon
    tray_inset = round(size * 0.04)
    tray_thickness = round(size * 0.03)
    tray_y = bubble_bottom - tray_thickness - round(size * 0.025)
    draw.rounded_rectangle(
        (
            bubble_left + tray_inset,
            tray_y,
            bubble_right - tray_inset,
            tray_y + tray_thickness,
        ),
        radius=tray_thickness // 2,
        fill=palette.arrow_fill,
    )

    # 5. Subtle inner outline for depth on the background tile
    draw.rounded_rectangle(
        (pad + 2, pad + 2, size - pad - 2, size - pad - 2),
        radius=radius - 2,
        outline=palette.tile_outline,
        width=max(1, size // 256),
    )

    return img


def main() -> None:
    light = draw_logo(LIGHT, 512)
    dark = draw_logo(DARK, 512)

    light.save(_HERE / "logo_light.png", format="PNG")
    dark.save(_HERE / "logo_dark.png", format="PNG")

    # Backwards-compat alias used by README + as a generic fallback.
    light.save(_HERE / "logo.png", format="PNG")

    # 64×64 header thumbnail (light variant) — kept for any callers still
    # asking for it explicitly.
    light.resize((64, 64), Image.LANCZOS).save(_HERE / "logo_64.png", format="PNG")

    # Multi-res Windows icon (uses the light variant — Windows title-bar
    # rendering doesn't switch with the in-app dark mode toggle).
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    light.save(_HERE / "logo.ico", format="ICO", sizes=ico_sizes)

    print("Wrote logo_light.png (512x512)")
    print("Wrote logo_dark.png  (512x512)")
    print("Wrote logo.png       (alias of light variant)")
    print("Wrote logo_64.png    (64x64 light)")
    print(f"Wrote logo.ico       (multi-res up to {ico_sizes[-1][0]}x{ico_sizes[-1][1]})")


if __name__ == "__main__":
    main()
