import json
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

DEFAULT_CONFIG = {
    "TEXT_TO_REMOVE": ["K.S.S.59", "K.S.S. 59"],
    "DPI": 100,
    "DARK_PIXEL_THRESHOLD": 220,
    "SIDE_MARGIN_PCT": 0.005, 
    "MIN_SYSTEM_HEIGHT_PT": 20.0,
    "MIN_GAP": 12.0,  
    "MAX_GAP": 60.0,  
    "PREVIEW_OPACITY": 0.65, 
    "TARGET_ASPECT_RATIO": 1.3333, 
    "MARGIN_TOP": 30.0,
    "MARGIN_BOT": 20.0,
    "PAGE_NUM_MARGIN_PCT": 0.06 
}

def load_config(config_path=None, overrides=None):
    """Loads default configuration, updating with any JSON file or dictionary overrides."""
    cfg = dict(DEFAULT_CONFIG)
    if config_path:
        with open(config_path) as f:
            cfg.update(json.load(f))
    if overrides:
        cfg.update(overrides)
    return cfg

def _tighten_bounds(dark_counts, top, bot):
    """Trims empty rows from the top and bottom of a bounding box."""
    while top < bot and dark_counts[top] == 0:
        top += 1
    while bot > top and dark_counts[bot - 1] == 0:
        bot -= 1
    return top, bot

def erase_page_numbers(dark, cfg):
    """Clears dark pixels in the top and bottom margins to ignore page numbers during analysis."""
    height, width = dark.shape
    margin = int(height * cfg["PAGE_NUM_MARGIN_PCT"])
    row_ink_widths = dark.sum(axis=1)

    for y in range(margin):
        if 0 < row_ink_widths[y] < width * 0.15: 
            dark[y, :] = False
    for y in range(height - margin, height):
        if 0 < row_ink_widths[y] < width * 0.15:
            dark[y, :] = False
    return dark

def analyze_and_get_systems(page, cfg):
    """
    Analyzes a PDF page to detect horizontal systems of music.
    Returns a list of dictionaries containing top/bot bounding coordinates.
    """
    pix = page.get_pixmap(dpi=cfg["DPI"])
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    arr = np.array(img)

    side_px = int(arr.shape[1] * cfg["SIDE_MARGIN_PCT"])
    cropped = arr[:, side_px:-side_px] if side_px > 0 else arr
    dark = cropped < cfg["DARK_PIXEL_THRESHOLD"]
    dark = erase_page_numbers(dark, cfg)
    
    dark_counts = dark.sum(axis=1)
    height, width = dark.shape
    
    # Smooth horizontal ink profiles to find continuous content blocks
    window_size = int(cfg["DPI"] * 0.3) 
    kernel = np.ones(window_size) / window_size
    smoothed = np.convolve(dark_counts, kernel, mode='same')

    in_zone = smoothed > 2.0
    padded = np.pad(in_zone, (1, 1), mode='constant')
    diff = np.diff(padded.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    rough_zones = list(zip(starts, ends))

    scale = page.rect.height / pix.height
    margin_width = int(width * 0.15) 
    all_brackets = []

    for z_top, z_bot in rough_zones:
        if z_bot - z_top < cfg["DPI"] * 0.2:
            continue 

        left_strip = dark[z_top:z_bot, :margin_width]
        col_sums = left_strip.sum(axis=0)

        if len(col_sums) == 0 or col_sums.max() < cfg["DPI"] * 0.2:
            all_brackets.append(_tighten_bounds(dark_counts, z_top, z_bot))
            continue

        # Look for vertical bracket lines to precisely segment systems
        best_col = np.argmax(col_sums)
        col_pixels = left_strip[:, best_col]
        padded_col = np.pad(col_pixels, (1, 1), mode='constant')
        col_diff = np.diff(padded_col.astype(int))
        b_starts = np.where(col_diff == 1)[0]
        b_ends = np.where(col_diff == -1)[0]

        min_bracket_height = int(cfg["DPI"] * 0.4) 
        found = False

        for s, e in zip(b_starts, b_ends):
            if e - s >= min_bracket_height:
                all_brackets.append((z_top + s, z_top + e))
                found = True

        if not found:
            all_brackets.append(_tighten_bounds(dark_counts, z_top, z_bot))

    all_brackets.sort(key=lambda x: x[0])
    systems = []
    
    for i, (b_s, b_e) in enumerate(all_brackets):
        prev_e = all_brackets[i-1][1] if i > 0 else b_s
        max_up = int(b_s - (b_s - prev_e) * 0.6) if i > 0 else 0
        
        next_s = all_brackets[i+1][0] if i < len(all_brackets) - 1 else b_e
        max_down = int(b_e + (next_s - b_e) * 0.6) if i < len(all_brackets) - 1 else height - 1

        sys_top, sys_bot = b_s, b_e
        while sys_top > max_up and dark_counts[sys_top - 1] > 0: sys_top -= 1
        while sys_bot < max_down and dark_counts[sys_bot + 1] > 0: sys_bot += 1
        
        top_pt, bot_pt = sys_top * scale, sys_bot * scale

        if (bot_pt - top_pt) >= cfg.get("MIN_SYSTEM_HEIGHT_PT", 20.0):
            systems.append({"top": top_pt, "bot": bot_pt, "is_content": True, "is_reset": False})

    if not systems:
        systems.append({"top": 0, "bot": page.rect.height, "is_content": False, "is_reset": False})
    return systems

def erase_catalog_text(raw_doc, cfg):
    """Draws white rectangles over specified text targets to redact them prior to processing."""
    normalized_doc = fitz.open()
    for page in raw_doc:
        norm_page = normalized_doc.new_page(width=page.rect.width, height=page.rect.height)
        norm_page.show_pdf_page(norm_page.rect, raw_doc, page.number)
        for target in cfg["TEXT_TO_REMOVE"]:
            for rect in norm_page.search_for(target):
                norm_page.draw_rect(rect + (-3, -3, 3, 3), color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
    return normalized_doc

def build_layout(input_path, cfg, report_callback=None):
    """
    Parses an entire document and constructs the JSON layout state.
    Triggers report_callback with outlier metrics if provided.
    """
    raw_doc = fitz.open(input_path)
    normalized_doc = erase_catalog_text(raw_doc, cfg)
    
    pages = []
    all_heights, system_refs = [], []
    
    for idx in range(len(normalized_doc)):
        current_page = normalized_doc[idx]
        cur_systems = analyze_and_get_systems(current_page, cfg)
        for s in cur_systems:
            if s["is_content"]:
                h = s["bot"] - s["top"]
                all_heights.append(h)
                system_refs.append({"page": idx, "top": s["top"], "height": h})

        pages.append({
            "index": idx,
            "width": current_page.rect.width,
            "height": current_page.rect.height,
            "systems": cur_systems
        })

    if report_callback and all_heights:
        med = np.median(all_heights)
        mad = np.median(np.abs(all_heights - med))
        outliers = []
        for ref in system_refs:
            z = (ref["height"] - med) / mad if mad > 0 else 0
            if abs(z) > 2.5:
                outliers.append((ref, z))
        
        report_callback({
            "checked": len(all_heights),
            "median": med,
            "mad": mad,
            "outliers": outliers
        })

    return {
        "text_to_remove": cfg["TEXT_TO_REMOVE"],
        "target_aspect_ratio": cfg["TARGET_ASPECT_RATIO"],
        "min_gap": cfg["MIN_GAP"],
        "max_gap": cfg["MAX_GAP"],
        "margin_top": cfg["MARGIN_TOP"],
        "margin_bot": cfg["MARGIN_BOT"],
        "preview_opacity": cfg["PREVIEW_OPACITY"],
        "pages": pages,
    }

def save_layout(layout, path):
    with open(path, "w") as f: json.dump(layout, f, indent=2)

def load_layout(path):
    with open(path) as f: return json.load(f)

def render_layout(input_path, layout, output_path):
    """Reassembles the PDF based on the defined layout blocks, calculating preview logic dynamically."""
    raw_doc = fitz.open(input_path)
    normalized_doc = erase_catalog_text(raw_doc, {"TEXT_TO_REMOVE": layout["text_to_remove"]})
    final_doc = fitz.open()

    all_blocks = []
    for p in layout["pages"]:
        for s in p["systems"]:
            block = dict(s)
            block["page_idx"] = p["index"]
            block["page_width"] = p["width"]
            all_blocks.append(block)

    if not all_blocks: return

    target_width = all_blocks[0]["page_width"]
    target_height = target_width / layout.get("target_aspect_ratio", 1.3333)
    margin_top = layout.get("margin_top", 30.0)
    margin_bot = layout.get("margin_bot", 20.0)
    available_height = target_height - margin_top - margin_bot

    i = 0
    # Consolidate loop structure to cleanly pack one output page per iteration
    while i < len(all_blocks):
        current_page_blocks = []
        current_sum_h = 0.0
        
        while i < len(all_blocks):
            block = all_blocks[i]
            block_h = block["bot"] - block["top"]
            
            if block.get("is_reset", False) and current_page_blocks:
                break
                
            num_future_gaps = len(current_page_blocks)
            required_space = current_sum_h + block_h + (num_future_gaps * layout.get("min_gap", 12.0))

            # Factor in the required space for the next block to act as a preview
            preview_h = 0.0
            if i + 1 < len(all_blocks) and not all_blocks[i+1].get("is_reset", False):
                preview_h = all_blocks[i+1]["bot"] - all_blocks[i+1]["top"]
                required_space += preview_h + layout.get("min_gap", 12.0)

            if required_space <= available_height:
                current_page_blocks.append(block)
                current_sum_h += block_h
                i += 1
            else:
                if not current_page_blocks:
                    current_page_blocks.append(block)
                    current_sum_h += block_h
                    i += 1
                break

        # Calculate final spacing distribution
        preview_block = None
        preview_h = 0.0
        if i < len(all_blocks) and not all_blocks[i].get("is_reset", False):
            preview_block = all_blocks[i]
            preview_h = preview_block["bot"] - preview_block["top"]
            
        num_gaps = len(current_page_blocks) - 1 + (1 if preview_block else 0)
        leftover_space = available_height - (current_sum_h + preview_h)
        
        actual_gap = 0.0
        if num_gaps > 0:
            actual_gap = max(layout.get("min_gap", 12.0), min(leftover_space / num_gaps, layout.get("max_gap", 60.0)))

        # Render page
        p = final_doc.new_page(width=target_width, height=target_height)
        current_y = margin_top

        for block in current_page_blocks:
            src_rect = fitz.Rect(0, block["top"], target_width, block["bot"])
            dest_rect = fitz.Rect(0, current_y, target_width, current_y + (block["bot"] - block["top"]))
            p.show_pdf_page(dest_rect, normalized_doc, block["page_idx"], clip=src_rect)
            current_y += (block["bot"] - block["top"]) + actual_gap

        if preview_block:
            src_rect = fitz.Rect(0, preview_block["top"], target_width, preview_block["bot"])
            dest_rect = fitz.Rect(0, current_y, target_width, current_y + preview_h)
            p.show_pdf_page(dest_rect, normalized_doc, preview_block["page_idx"], clip=src_rect)
            p.draw_rect(dest_rect, color=None, fill=(1, 1, 1), fill_opacity=layout.get("preview_opacity", 0.65), overlay=True)

    final_doc.save(output_path, garbage=3, deflate=True)