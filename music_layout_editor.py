"""
Manual-correction workflow for the page-turn preview generator.

    python music_layout_editor.py detect input.pdf layout.json [--overlays overlays/]
    ... open layout.json in a text editor and/or look at overlays/*.png ...
    ... fix whatever numbers are wrong ...
    python music_layout_editor.py render input.pdf layout.json output.pdf

WHAT'S IN layout.json
----------------------
One entry per page. All coordinates are PDF points (the same units you'd see
in any PDF editor), measured from the top of the page:

{
  "pages": [
    {
      "index": 0,
      "width": 612.0,
      "height": 792.0,
      "is_last_page": false,
      "systems": [
        {"top": 101.5, "bot": 236.2, "is_content": true},
        ...
      ],
      "preview_clip": {"top": 131.8, "bot": 216.0}
    },
    ...
  ]
}

"systems" is the list of slices kept from THIS page, top to bottom, each
repacked with a fixed gap between them ("compact_gap" at the top level of
the file). To fix a page:
  - Wrong system split in two / merged wrong: edit the top/bot numbers.
  - A block shouldn't be there at all (e.g. a stray mark got detected as
    its own system): delete that entry from the list.
  - Missing a system: add a new {"top":.., "bot":.., "is_content":true}
    entry in the right position.

"preview_clip" is the (top, bot) region taken from the NEXT page and shown
as the shaded preview strip at the bottom of THIS page. If the preview shows
the wrong thing or is cut off, edit these two numbers directly -- use the
overlay image for page N+1 to read off where the real first system actually
starts and ends. Set to null to remove the preview strip from that page
entirely.

Top-level "compact_gap", "preview_padding", "opacity", and "layout_mode"
apply to every page; you can also override any of these per-page by adding
the same keys inside an individual page entry.

READING THE OVERLAYS
----------------------
Each overlays/page_XX.png shows the rendered page with:
  - green boxes around blocks detected as real systems
  - red boxes around blocks detected as labels (titles, page numbers) --
    these are excluded from preview selection automatically
  - a blue box showing the region of THIS page that got used as the
    preview strip for the PREVIOUS page (if any)
Each box is labeled with its top/bot in PDF points, so you can copy the
numbers straight into layout.json.
"""
import argparse
import json

import fitz
from PIL import Image, ImageDraw

from layout_engine import (
    DEFAULT_CONFIG, load_config, build_layout, render_layout,
    save_layout, load_layout, erase_catalog_text,
)

GREEN = (0, 150, 0)
RED = (200, 0, 0)
BLUE = (0, 90, 220)


def _print_refine_report(report):
    if report["checked"] == 0:
        return
    print(f"[*] Auto-refine: {report['checked']} page(s) had an outlier-height system, retrying with nearby parameters...")
    for f in report["fixed"]:
        print(f"    page {f['page']}: fit improved (worst z {f['worst_z_before']:.2f} -> {f['worst_z_after']:.2f}) "
              f"using {f['variant']}")
    if report["unresolved"]:
        print(f"    still flagged after retry (needs manual fix):")
        for u in report["unresolved"]:
            print(f"      page {u['page']}: worst z={u['worst_z']:.2f}")


def cmd_detect(args):
    cfg = load_config(args.config)
    layout = build_layout(args.input_pdf, cfg, report_callback=_print_refine_report)
    save_layout(layout, args.layout_json)
    print(f"[+] Layout written to {args.layout_json} ({len(layout['pages'])} pages)")

    if args.overlays:
        render_overlays(args.input_pdf, layout, args.overlays)
        print(f"[+] Overlay images written to {args.overlays}/")


def cmd_render(args):
    layout = load_layout(args.layout_json)
    render_layout(args.input_pdf, layout, args.output_pdf)
    print(f"[+] Complete. Score written to: {args.output_pdf}")


def render_overlays(input_path, layout, out_dir):
    import os
    os.makedirs(out_dir, exist_ok=True)

    raw_doc = fitz.open(input_path)
    cfg_like = {"TEXT_TO_REMOVE": layout["text_to_remove"]}
    normalized_doc = erase_catalog_text(raw_doc, cfg_like)

    dpi = 100
    pages_by_index = {p["index"]: p for p in layout["pages"]}

    for idx, page_entry in pages_by_index.items():
        page = normalized_doc[idx]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGB")
        draw = ImageDraw.Draw(img)
        scale = dpi / 72.0  # PDF points -> pixels at this DPI

        for s in page_entry["systems"]:
            color = GREEN if s.get("is_content", True) else RED
            y0, y1 = s["top"] * scale, s["bot"] * scale
            draw.rectangle([2, y0, pix.width - 2, y1], outline=color, width=2)
            draw.text((4, max(0, y0 - 11)), f"top {s['top']:.1f}", fill=color)
            draw.text((4, min(pix.height - 11, y1 + 1)), f"bot {s['bot']:.1f}", fill=color)

        prev_page_entry = pages_by_index.get(idx - 1)
        if prev_page_entry and prev_page_entry.get("preview_clip"):
            pc = prev_page_entry["preview_clip"]
            y0, y1 = pc["top"] * scale, pc["bot"] * scale
            draw.rectangle([2, y0, pix.width - 2, y1], outline=BLUE, width=3)
            draw.text((pix.width - 160, max(0, y0 - 11)),
                      f"preview for pg {idx}: top {pc['top']:.1f}", fill=BLUE)
            draw.text((pix.width - 160, min(pix.height - 11, y1 + 1)),
                      f"bot {pc['bot']:.1f}", fill=BLUE)

        img.save(f"{out_dir}/page_{idx:03d}.png")


def main():
    parser = argparse.ArgumentParser(description="Manual-correction workflow for music_secure")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_detect = sub.add_parser("detect", help="Run detection, write an editable layout.json")
    p_detect.add_argument("input_pdf")
    p_detect.add_argument("layout_json")
    p_detect.add_argument("--config", help="JSON file overriding DEFAULT_CONFIG values")
    p_detect.add_argument("--overlays", help="Directory to write annotated preview PNGs into")
    p_detect.set_defaults(func=cmd_detect)

    p_render = sub.add_parser("render", help="Render the final PDF from a layout.json")
    p_render.add_argument("input_pdf")
    p_render.add_argument("layout_json")
    p_render.add_argument("output_pdf")
    p_render.set_defaults(func=cmd_render)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
