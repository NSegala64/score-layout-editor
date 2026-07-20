"""
Manual-correction workflow for the page-turn preview generator.

    python cli.py detect input.pdf layout.json [--overlays overlays/]
    ... open layout.json in the editor UI and/or look at overlays/*.png ...
    python cli.py render input.pdf layout.json output.pdf

WHAT'S IN layout.json
----------------------
One entry per page. All coordinates are PDF points (the same units you'd see
in any PDF editor), measured from the top of the page.

Top-level parameters like "min_gap", "max_gap", and "preview_opacity" apply globally. 

"systems" is the list of slices kept from THIS page, top to bottom:
{
  "pages": [
    {
      "index": 0,
      "width": 612.0,
      "height": 792.0,
      "systems": [
        {"top": 101.5, "bot": 236.2, "is_content": true, "is_reset": false},
        ...
      ]
    }
  ]
}

To fix a page via JSON:
  - Wrong system split in two / merged wrong: edit the top/bot numbers.
  - A block shouldn't be there at all: delete the entry.
  - Previews are calculated dynamically. To force a page break before a system,
    set "is_reset" to true on that system.

READING THE OVERLAYS
----------------------
Each overlays/page_XX.png shows the rendered page with:
  - green boxes around blocks detected as real systems
  - red boxes around blocks flagged as non-content
"""
import argparse
import json
import fitz
from PIL import Image, ImageDraw

from layout_engine import (
    load_config, build_layout, render_layout,
    save_layout, load_layout, erase_catalog_text,
)

GREEN = (0, 150, 0)
RED = (200, 0, 0)

def _print_refine_report(report):
    print("\n=== SYSTEM DETECTION REPORT ===")
    print(f"Total systems processed: {report['checked']}")
    print(f"Median height: {report['median']:.1f} pt (MAD: {report['mad']:.1f} pt)")
    if report['outliers']:
        print(f"\n[!] Flagged {len(report['outliers'])} anomalous bounding box(es):")
        for ref, z in report['outliers']:
            direction = "TALLER" if z > 0 else "SHORTER"
            print(f"  -> Page {ref['page'] + 1}, Top Y: {ref['top']:.1f} | Height: {ref['height']:.1f} pt | ({direction} than usual)")
    else:
        print("[+] All detected bounding boxes are within expected dimensions.")
    print("===============================\n")

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
    
    dpi = layout.get("DPI", 100)
    pages_by_index = {p["index"]: p for p in layout["pages"]}

    for idx, page_entry in pages_by_index.items():
        page = normalized_doc[idx]
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("RGB")
        draw = ImageDraw.Draw(img)
        scale = dpi / 72.0 

        for s in page_entry["systems"]:
            color = GREEN if s.get("is_content", True) else RED
            y0, y1 = s["top"] * scale, s["bot"] * scale
            draw.rectangle([2, y0, pix.width - 2, y1], outline=color, width=2)
            draw.text((4, max(0, y0 - 11)), f"top {s['top']:.1f}", fill=color)
            draw.text((4, min(pix.height - 11, y1 + 1)), f"bot {s['bot']:.1f}", fill=color)

        img.save(f"{out_dir}/page_{idx:03d}.png")

def main():
    parser = argparse.ArgumentParser(description="Manual-correction workflow for layout engine")
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