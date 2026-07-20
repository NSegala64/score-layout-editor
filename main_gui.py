import os
import copy
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz
from PIL import Image, ImageTk

from layout_engine import (
    DEFAULT_CONFIG, analyze_and_get_systems, build_layout, render_layout
)

class UnifiedLayoutEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sheet Music Layout Engine")
        self.geometry("1400x900")
        
        self.pdf_path = None
        self.doc = None
        self.layout = None
        self.cfg = dict(DEFAULT_CONFIG)
        
        # Isolated Navigation States
        self.tune_page_idx = 0
        self.edit_page_idx = 0
        
        self.dpi = 100
        self.scale = self.dpi / 72.0
        
        # Editor State
        self.drag_data = {"item_idx": None, "edge": None, "start_y": 0, "current_y": 0}
        self.hovered_idx = None
        self.undo_stack, self.redo_stack = [], []

        self._build_ui()
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.tab_tune = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_tune, text="1. Detect & Tune")
        self._build_tune_tab()

        self.tab_edit = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_edit, text="2. Visual Editor", state="disabled")
        self._build_edit_tab()

        self.tab_render = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_render, text="3. Export & Render", state="disabled")
        self._build_render_tab()

    def _on_tab_changed(self, event):
        idx = self.notebook.index(self.notebook.select())
        if idx == 2 and self.layout:
            self._refresh_render_preview()

    # ==========================================
    # TAB 1: DETECTION & TUNING
    # ==========================================
    def _build_tune_tab(self):
        ctrl_frame = ttk.Frame(self.tab_tune, width=300, relief=tk.SUNKEN, padding=10)
        ctrl_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        ttk.Button(ctrl_frame, text="Load PDF Score", command=self._load_pdf).pack(fill=tk.X, pady=5)
        self.lbl_pdf_info = ttk.Label(ctrl_frame, text="No file loaded")
        self.lbl_pdf_info.pack(fill=tk.X, pady=5)

        # Tune Navigation
        nav_frame = tk.Frame(ctrl_frame)
        nav_frame.pack(fill=tk.X, pady=5)
        tk.Button(nav_frame, text="< Prev", command=self._tune_prev_page).pack(side=tk.LEFT)
        self.lbl_tune_page = tk.Label(nav_frame, text="Page: - / -")
        self.lbl_tune_page.pack(side=tk.LEFT, expand=True)
        tk.Button(nav_frame, text="Next >", command=self._tune_next_page).pack(side=tk.RIGHT)

        ttk.Separator(ctrl_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        ttk.Label(ctrl_frame, text="Detection Parameters", font=("Arial", 10, "bold")).pack(anchor=tk.W)

        self.tune_sliders = {}
        self.tune_labels = {}
        params = [
            ("DARK_PIXEL_THRESHOLD", "Ink Threshold", 0, 255),
            ("MIN_SYSTEM_HEIGHT_PT", "Min Height (pt)", 5, 100),
            ("SIDE_MARGIN_PCT", "Side Margin %", 0.0, 0.15)
        ]

        for key, title, vmin, vmax in params:
            lbl = ttk.Label(ctrl_frame, text=f"{title}: {self.cfg[key]:.2f}")
            lbl.pack(anchor=tk.W, pady=(10, 0))
            var = tk.DoubleVar(value=self.cfg[key])
            slider = ttk.Scale(ctrl_frame, from_=vmin, to=vmax, variable=var, orient=tk.HORIZONTAL)
            slider.pack(fill=tk.X)
            
            def on_slide(e, k=key, v=var, l=lbl, t=title):
                l.config(text=f"{t}: {v.get():.2f}")
                
            def on_release(e, k=key, v=var):
                self.cfg[k] = v.get()
                self._refresh_tune_preview()
                
            slider.bind("<B1-Motion>", on_slide)
            slider.bind("<ButtonRelease-1>", on_release)
            self.tune_sliders[key] = var
            self.tune_labels[key] = lbl

        ttk.Separator(ctrl_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        self.btn_detect = tk.Button(ctrl_frame, text="Run Full Detection", bg="#0055ff", fg="white", command=self._run_full_detection, state=tk.DISABLED)
        self.btn_detect.pack(fill=tk.X, pady=10)

        self.tune_canvas = tk.Canvas(self.tab_tune, bg="gray")
        self.tune_canvas.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def _load_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path: return
        self.pdf_path = path
        self.doc = fitz.open(self.pdf_path)
        self.lbl_pdf_info.config(text=f"Pages: {len(self.doc)}\n{os.path.basename(path)}")
        self.btn_detect.config(state=tk.NORMAL)
        self.tune_page_idx = 0
        self._refresh_tune_preview()

    def _tune_prev_page(self):
        if self.doc and self.tune_page_idx > 0:
            self.tune_page_idx -= 1
            self._refresh_tune_preview()

    def _tune_next_page(self):
        if self.doc and self.tune_page_idx < len(self.doc) - 1:
            self.tune_page_idx += 1
            self._refresh_tune_preview()

    def _refresh_tune_preview(self):
        if not self.doc: return
        self.lbl_tune_page.config(text=f"Page: {self.tune_page_idx + 1} / {len(self.doc)}")
        
        page = self.doc[self.tune_page_idx]
        pix = page.get_pixmap(dpi=self.dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tune_tk_img = ImageTk.PhotoImage(img)
        
        self.tune_canvas.delete("all")
        self.tune_canvas.create_image(0, 0, anchor=tk.NW, image=self.tune_tk_img)
        self.tune_canvas.config(scrollregion=(0, 0, pix.width, pix.height))

        systems = analyze_and_get_systems(page, self.cfg)
        width_px = pix.width
        
        for sys in systems:
            y0, y1 = sys["top"] * self.scale, sys["bot"] * self.scale
            color = "#00ff00" if sys["is_content"] else "#ff0000"
            self.tune_canvas.create_rectangle(5, y0, width_px - 5, y1, outline=color, width=2)

    def _run_full_detection(self):
        self.config(cursor="watch")
        self.update()
        try:
            self.layout = build_layout(self.pdf_path, self.cfg)
            self.notebook.tab(1, state="normal")
            self.notebook.tab(2, state="normal")
            self.notebook.select(1)
            self.edit_page_idx = 0
            self._load_editor_page()
        except Exception as e:
            messagebox.showerror("Detection Error", str(e))
        finally:
            self.config(cursor="")

    # ==========================================
    # TAB 2: VISUAL EDITOR (No changes required)
    # ==========================================
    def _build_edit_tab(self):
        toolbar = tk.Frame(self.tab_edit)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        nav_frame = tk.Frame(toolbar)
        nav_frame.pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="< Prev", command=self._edit_prev_page).pack(side=tk.LEFT, pady=5)
        self.lbl_edit_page = tk.Label(nav_frame, text="Page: 0 / 0", width=12)
        self.lbl_edit_page.pack(side=tk.LEFT, pady=5)
        tk.Button(nav_frame, text="Next >", command=self._edit_next_page).pack(side=tk.LEFT, pady=5)
        
        hist_frame = tk.Frame(toolbar)
        hist_frame.pack(side=tk.LEFT, padx=20)
        tk.Button(hist_frame, text="Undo", command=self._undo).pack(side=tk.LEFT, padx=2)
        tk.Button(hist_frame, text="Redo", command=self._redo).pack(side=tk.LEFT, padx=2)
        
        instructions = "Drag empty: Add | Hover+Del: Delete | R-Click: Reset | Shift+R-Click: Label"
        tk.Label(toolbar, text=instructions).pack(side=tk.RIGHT, padx=10)

        self.edit_canvas = tk.Canvas(self.tab_edit, cursor="cross", bg="gray")
        self.edit_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.edit_canvas.bind("<ButtonPress-1>", self._on_press)
        self.edit_canvas.bind("<B1-Motion>", self._on_drag)
        self.edit_canvas.bind("<ButtonRelease-1>", self._on_release)
        self.edit_canvas.bind("<Button-3>", self._on_right_click)
        self.edit_canvas.bind("<Shift-Button-3>", self._on_shift_right_click)
        self.edit_canvas.bind("<Motion>", self._on_mouse_move)
        self.bind("<Delete>", self._on_delete_key)
        self.bind("<BackSpace>", self._on_delete_key)

    def _save_state(self):
        self.undo_stack.append({'idx': self.edit_page_idx, 'pages': copy.deepcopy(self.layout["pages"])})
        self.redo_stack.clear()

    def _undo(self, event=None):
        if not self.undo_stack: return
        self.redo_stack.append({'idx': self.edit_page_idx, 'pages': copy.deepcopy(self.layout["pages"])})
        state = self.undo_stack.pop()
        self.layout["pages"], self.edit_page_idx = state['pages'], state['idx']
        self._load_editor_page()

    def _redo(self, event=None):
        if not self.redo_stack: return
        self.undo_stack.append({'idx': self.edit_page_idx, 'pages': copy.deepcopy(self.layout["pages"])})
        state = self.redo_stack.pop()
        self.layout["pages"], self.edit_page_idx = state['pages'], state['idx']
        self._load_editor_page()

    def _load_editor_page(self):
        if not self.layout or not (0 <= self.edit_page_idx < len(self.layout["pages"])): return
        self.page_data = self.layout["pages"][self.edit_page_idx]
        self.lbl_edit_page.config(text=f"Page: {self.edit_page_idx + 1} / {len(self.layout['pages'])}")
        
        page = self.doc[self.edit_page_idx]
        pix = page.get_pixmap(dpi=self.dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tk_img = ImageTk.PhotoImage(img)
        
        self.edit_canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.edit_canvas.delete("all")
        self.edit_canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        self._draw_boxes()

    def _draw_boxes(self):
        self.edit_canvas.delete("box")
        width_px = self.page_data["width"] * self.scale
        
        for i, sys in enumerate(self.page_data.get("systems", [])):
            y0, y1 = sys["top"] * self.scale, sys["bot"] * self.scale
            color = "#ff00ff" if sys.get("is_reset") else ("#00ff00" if sys.get("is_content", True) else "#ffff00")
            width = 5 if self.hovered_idx == i else (3 if sys.get("is_reset") else 2)
            self.edit_canvas.create_rectangle(5, y0, width_px - 5, y1, outline=color, width=width, tags=("box", f"sys_{i}"))
            
        if self.drag_data.get("item_idx") == "new":
            y0, y1 = self.drag_data.get("start_y", 0), self.drag_data.get("current_y", 0)
            self.edit_canvas.create_rectangle(5, min(y0, y1), width_px - 5, max(y0, y1), outline="#00ffff", width=2, dash=(4, 4), tags="box")

    def _get_sys_at_y(self, y):
        for i, sys in enumerate(self.page_data.get("systems", [])):
            if sys["top"] * self.scale - 10 <= y <= sys["bot"] * self.scale + 10: return i
        return None

    def _on_mouse_move(self, event):
        if self.notebook.index(self.notebook.select()) != 1: return
        y = self.edit_canvas.canvasy(event.y)
        new_hover = self._get_sys_at_y(y)
        if new_hover != self.hovered_idx:
            self.hovered_idx = new_hover
            self._draw_boxes()

    def _on_delete_key(self, event):
        if self.notebook.index(self.notebook.select()) != 1: return
        if self.hovered_idx is not None:
            self._save_state()
            del self.page_data["systems"][self.hovered_idx]
            self.hovered_idx = None
            self._draw_boxes()

    def _on_press(self, event):
        y = self.edit_canvas.canvasy(event.y)
        idx = self._get_sys_at_y(y)
        self._save_state()
        if idx is not None:
            sys = self.page_data["systems"][idx]
            top_px, bot_px = sys["top"] * self.scale, sys["bot"] * self.scale
            self.drag_data = {"item_idx": idx, "edge": "top" if abs(y - top_px) < abs(y - bot_px) else "bot"}
        else:
            self.drag_data = {"item_idx": "new", "start_y": y, "current_y": y}

    def _on_drag(self, event):
        y = self.edit_canvas.canvasy(event.y)
        if self.drag_data.get("item_idx") == "new":
            self.drag_data["current_y"] = y
            self._draw_boxes()
        elif self.drag_data.get("item_idx") is not None:
            sys = self.page_data["systems"][self.drag_data["item_idx"]]
            if self.drag_data["edge"] == "top": sys["top"] = y / self.scale
            else: sys["bot"] = y / self.scale
            self._draw_boxes()

    def _on_release(self, event):
        if self.drag_data.get("item_idx") == "new":
            y0, y1 = self.drag_data["start_y"], self.drag_data["current_y"]
            if abs(y1 - y0) > 5:
                self.page_data.setdefault("systems", []).append({"top": min(y0, y1) / self.scale, "bot": max(y0, y1) / self.scale, "is_content": True, "is_reset": False})
                self.page_data["systems"].sort(key=lambda s: s["top"])
            self._draw_boxes()
        self.drag_data = {"item_idx": None, "edge": None, "start_y": 0, "current_y": 0}

    def _on_right_click(self, event):
        idx = self._get_sys_at_y(self.edit_canvas.canvasy(event.y))
        if idx is not None:
            self._save_state()
            self.page_data["systems"][idx]["is_reset"] = not self.page_data["systems"][idx].get("is_reset", False)
            self._draw_boxes()

    def _on_shift_right_click(self, event):
        idx = self._get_sys_at_y(self.edit_canvas.canvasy(event.y))
        if idx is not None:
            self._save_state()
            self.page_data["systems"][idx]["is_content"] = not self.page_data["systems"][idx].get("is_content", True)
            self._draw_boxes()

    def _edit_prev_page(self):
        if self.edit_page_idx > 0:
            self.edit_page_idx -= 1
            self._load_editor_page()

    def _edit_next_page(self):
        if self.edit_page_idx < len(self.layout["pages"]) - 1:
            self.edit_page_idx += 1
            self._load_editor_page()

    # ==========================================
    # TAB 3: RENDER & EXPORT (With Live Canvas)
    # ==========================================
    def _build_render_tab(self):
        ctrl_frame = ttk.Frame(self.tab_render, width=300, relief=tk.SUNKEN, padding=10)
        ctrl_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        ttk.Label(ctrl_frame, text="Render Formatting", font=("Arial", 12, "bold")).pack(anchor=tk.W, pady=(0, 20))
        
        self.render_vars = {}
        render_params = [
            ("min_gap", "Min Gap (pt)", 0, 100, 12.0),
            ("max_gap", "Max Gap (pt)", 10, 150, 60.0),
            ("margin_top", "Top Margin (pt)", 0, 150, 30.0),
            ("margin_bot", "Bottom Margin (pt)", 0, 150, 20.0),
            ("preview_opacity", "Preview Opacity", 0.0, 1.0, 0.65),
            ("target_aspect_ratio", "Aspect Ratio", 0.8, 2.0, 1.3333)
        ]
        
        for key, title, vmin, vmax, default in render_params:
            lbl = ttk.Label(ctrl_frame, text=f"{title}: {default:.2f}")
            lbl.pack(anchor=tk.W, pady=(10, 0))
            var = tk.DoubleVar(value=default)
            slider = ttk.Scale(ctrl_frame, from_=vmin, to=vmax, variable=var, orient=tk.HORIZONTAL)
            slider.pack(fill=tk.X)
            
            def on_slide(e, k=key, v=var, l=lbl, t=title):
                l.config(text=f"{t}: {v.get():.2f}")
                
            def on_release(e, k=key, v=var):
                self._refresh_render_preview()

            slider.bind("<B1-Motion>", on_slide)
            slider.bind("<ButtonRelease-1>", on_release)
            self.render_vars[key] = var

        tk.Button(ctrl_frame, text="Export PDF", bg="green", fg="white", font=("Arial", 12, "bold"), 
                  command=self._render_pdf).pack(fill=tk.X, pady=40)

        # Dynamic Single-Page Render Preview Canvas
        self.render_canvas = tk.Canvas(self.tab_render, bg="darkgray")
        self.render_canvas.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def _refresh_render_preview(self):
        """Packs and renders ONLY the first output page to a volatile in-memory PyMuPDF doc."""
        if not self.layout or not self.layout.get("pages"): return

        all_blocks = []
        for p in self.layout["pages"]:
            for s in p.get("systems", []):
                if s.get("is_content", True):
                    b = dict(s)
                    b["page_idx"] = p["index"]
                    b["page_width"] = p["width"]
                    all_blocks.append(b)
        
        if not all_blocks: return

        # Load dynamic parameters
        t_ar = self.render_vars["target_aspect_ratio"].get()
        m_top = self.render_vars["margin_top"].get()
        m_bot = self.render_vars["margin_bot"].get()
        min_gap = self.render_vars["min_gap"].get()
        max_gap = self.render_vars["max_gap"].get()
        opacity = self.render_vars["preview_opacity"].get()

        target_width = all_blocks[0]["page_width"]
        target_height = target_width / t_ar
        available_height = target_height - m_top - m_bot

        # Bin-packing simulation for the FIRST page only
        current_page_blocks = []
        current_sum_h = 0.0
        i = 0
        while i < len(all_blocks):
            block = all_blocks[i]
            block_h = block["bot"] - block["top"]
            if block.get("is_reset", False) and current_page_blocks: break
            
            num_future_gaps = len(current_page_blocks)
            required_space = current_sum_h + block_h + (num_future_gaps * min_gap)

            preview_h = 0.0
            if i + 1 < len(all_blocks) and not all_blocks[i+1].get("is_reset", False):
                preview_h = all_blocks[i+1]["bot"] - all_blocks[i+1]["top"]
                required_space += preview_h + min_gap

            if required_space <= available_height:
                current_page_blocks.append(block)
                current_sum_h += block_h
                i += 1
            else:
                if not current_page_blocks:
                    current_page_blocks.append(block)
                    current_sum_h += block_h
                break

        preview_block = None
        preview_h = 0.0
        if i < len(all_blocks) and not all_blocks[i].get("is_reset", False):
            preview_block = all_blocks[i]
            preview_h = preview_block["bot"] - preview_block["top"]
            
        num_gaps = len(current_page_blocks) - 1 + (1 if preview_block else 0)
        leftover_space = available_height - (current_sum_h + preview_h)
        actual_gap = max(min_gap, min(leftover_space / num_gaps, max_gap)) if num_gaps > 0 else 0.0

        # Create ephemeral page and composite directly from source Doc
        temp_doc = fitz.open()
        p = temp_doc.new_page(width=target_width, height=target_height)
        current_y = m_top

        for block in current_page_blocks:
            src_rect = fitz.Rect(0, block["top"], target_width, block["bot"])
            dest_rect = fitz.Rect(0, current_y, target_width, current_y + (block["bot"] - block["top"]))
            p.show_pdf_page(dest_rect, self.doc, block["page_idx"], clip=src_rect)
            current_y += (block["bot"] - block["top"]) + actual_gap

        if preview_block:
            src_rect = fitz.Rect(0, preview_block["top"], target_width, preview_block["bot"])
            dest_rect = fitz.Rect(0, current_y, target_width, current_y + preview_h)
            p.show_pdf_page(dest_rect, self.doc, preview_block["page_idx"], clip=src_rect)
            p.draw_rect(dest_rect, color=None, fill=(1, 1, 1), fill_opacity=opacity, overlay=True)

        pix = p.get_pixmap(dpi=self.dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.render_tk_img = ImageTk.PhotoImage(img)
        
        self.render_canvas.delete("all")
        self.render_canvas.create_image(0, 0, anchor=tk.NW, image=self.render_tk_img)
        self.render_canvas.config(scrollregion=(0, 0, pix.width, pix.height))

    def _render_pdf(self):
        if not self.layout: return
        out_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not out_path: return
        
        for k, v in self.render_vars.items():
            self.layout[k] = v.get()
            
        self.config(cursor="watch")
        self.update()
        try:
            render_layout(self.pdf_path, self.layout, out_path)
            messagebox.showinfo("Success", f"PDF successfully rendered to:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Render Error", str(e))
        finally:
            self.config(cursor="")

if __name__ == "__main__":
    app = UnifiedLayoutEditor()
    app.mainloop()