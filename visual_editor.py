import json
import argparse
import tkinter as tk
from tkinter import messagebox, filedialog
import fitz
from PIL import Image, ImageTk
import copy
import os

SETTINGS_FILE = ".editor_settings.json"

class MusicLayoutEditor(tk.Tk):
    def __init__(self, pdf_path, layout_path):
        super().__init__()
        self.title("Sequential Flow Visual Editor")
        self.layout_path = layout_path
        self.doc = fitz.open(pdf_path)
        with open(layout_path, 'r') as f:
            self.layout = json.load(f)
        self.pages = self.layout["pages"]
        self.settings = self.load_settings()
        self.current_page_idx = self.settings.get(os.path.abspath(self.layout_path), 0)
        if not (0 <= self.current_page_idx < len(self.pages)): self.current_page_idx = 0
        
        self.dpi = 100
        self.scale = self.dpi / 72.0
        self.drag_data = {"item_idx": None, "edge": None, "y": 0, "start_y": 0, "current_y": 0}
        self.mouse_y = 0
        self.undo_stack, self.redo_stack = [], []
        self.setup_ui()
        self.load_page()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, 'r') as f: return json.load(f)
        except Exception: return {}

    def save_settings(self):
        self.settings[os.path.abspath(self.layout_path)] = self.current_page_idx
        try:
            with open(SETTINGS_FILE, 'w') as f: json.dump(self.settings, f)
        except Exception: pass

    def on_closing(self):
        self.save_settings()
        self.destroy()

    def setup_ui(self):
        toolbar = tk.Frame(self)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        nav_frame = tk.Frame(toolbar)
        nav_frame.pack(side=tk.LEFT, padx=5)
        tk.Button(nav_frame, text="< Prev", command=self.prev_page).pack(side=tk.LEFT, pady=5)
        self.page_label = tk.Label(nav_frame, text="Page: 0 / 0", width=12)
        self.page_label.pack(side=tk.LEFT, pady=5)
        tk.Button(nav_frame, text="Next >", command=self.next_page).pack(side=tk.LEFT, pady=5)
        
        hist_frame = tk.Frame(toolbar)
        hist_frame.pack(side=tk.LEFT, padx=20)
        tk.Button(hist_frame, text="Undo", command=self.undo).pack(side=tk.LEFT, padx=2)
        tk.Button(hist_frame, text="Redo", command=self.redo).pack(side=tk.LEFT, padx=2)
        
        file_frame = tk.Frame(toolbar)
        file_frame.pack(side=tk.RIGHT, padx=5)
        tk.Button(file_frame, text="Save", command=self.save_layout, bg="green", fg="white").pack(side=tk.RIGHT, padx=2)
        tk.Button(file_frame, text="Save As...", command=self.save_layout_as).pack(side=tk.RIGHT, padx=2)
        
        instructions = "Drag empty space: Add Box | Hover+Del: Delete Box | Right-Click: Toggle Reset | Shift+Right: Toggle Label"
        tk.Label(toolbar, text=instructions).pack(side=tk.RIGHT, padx=10)

        self.canvas = tk.Canvas(self, cursor="cross")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Shift-Button-3>", self.on_shift_right_click)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.bind("<Control-z>", self.undo)
        self.bind("<Control-y>", self.redo)
        self.bind("<Left>", self.prev_page)
        self.bind("<Right>", self.next_page)
        
        self.bind("<Delete>", self.on_delete_key)
        self.bind("<BackSpace>", self.on_delete_key)

    def save_state(self):
        self.undo_stack.append({'idx': self.current_page_idx, 'pages': copy.deepcopy(self.pages)})
        self.redo_stack.clear()

    def undo(self, event=None):
        if not self.undo_stack: return
        self.redo_stack.append({'idx': self.current_page_idx, 'pages': copy.deepcopy(self.pages)})
        state = self.undo_stack.pop()
        self.pages, self.current_page_idx = state['pages'], state['idx']
        self.load_page()

    def redo(self, event=None):
        if not self.redo_stack: return
        self.undo_stack.append({'idx': self.current_page_idx, 'pages': copy.deepcopy(self.pages)})
        state = self.redo_stack.pop()
        self.pages, self.current_page_idx = state['pages'], state['idx']
        self.load_page()

    def load_page(self):
        if not (0 <= self.current_page_idx < len(self.pages)): return
        self.page_data = self.pages[self.current_page_idx]
        self.page_label.config(text=f"Page: {self.current_page_idx + 1} / {len(self.pages)}")
        
        page = self.doc[self.current_page_idx]
        pix = page.get_pixmap(dpi=self.dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.config(scrollregion=(0, 0, pix.width, pix.height))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        self.draw_boxes()

    def draw_boxes(self):
        self.canvas.delete("box")
        width_px = self.page_data["width"] * self.scale
        
        for i, sys in enumerate(self.page_data.get("systems", [])):
            y0, y1 = sys["top"] * self.scale, sys["bot"] * self.scale
            color = "#ff00ff" if sys.get("is_reset") else ("#00ff00" if sys.get("is_content", True) else "#ffff00")
            width = 3 if sys.get("is_reset") else 2
            self.canvas.create_rectangle(5, y0, width_px - 5, y1, outline=color, width=width, tags=("box", f"sys_{i}"))
            
        if self.drag_data.get("item_idx") == "new":
            y0 = self.drag_data.get("start_y", 0)
            y1 = self.drag_data.get("current_y", 0)
            self.canvas.create_rectangle(5, min(y0, y1), width_px - 5, max(y0, y1), outline="#00ffff", width=2, dash=(4, 4), tags="box")

    def get_system_at_y(self, y):
        for i, sys in enumerate(self.page_data.get("systems", [])):
            if sys["top"] * self.scale - 10 <= y <= sys["bot"] * self.scale + 10:
                return i
        return None

    def on_mouse_move(self, event):
        self.mouse_y = self.canvas.canvasy(event.y)

    def on_delete_key(self, event):
        if hasattr(self, 'mouse_y'):
            idx = self.get_system_at_y(self.mouse_y)
            if idx is not None:
                self.save_state()
                del self.page_data["systems"][idx]
                self.draw_boxes()

    def on_press(self, event):
        y = self.canvas.canvasy(event.y)
        idx = self.get_system_at_y(y)
        if idx is not None:
            self.save_state()
            sys = self.page_data["systems"][idx]
            top_px, bot_px = sys["top"] * self.scale, sys["bot"] * self.scale
            self.drag_data = {"item_idx": idx, "edge": "top" if abs(y - top_px) < abs(y - bot_px) else "bot"}
        else:
            self.save_state()
            self.drag_data = {"item_idx": "new", "start_y": y, "current_y": y}

    def on_drag(self, event):
        y = self.canvas.canvasy(event.y)
        if self.drag_data.get("item_idx") == "new":
            self.drag_data["current_y"] = y
            self.draw_boxes()
        elif self.drag_data.get("item_idx") is not None:
            idx = self.drag_data["item_idx"]
            sys = self.page_data["systems"][idx]
            if self.drag_data["edge"] == "top": sys["top"] = y / self.scale
            else: sys["bot"] = y / self.scale
            self.draw_boxes()

    def on_release(self, event):
        if self.drag_data.get("item_idx") == "new":
            y0 = self.drag_data["start_y"]
            y1 = self.drag_data["current_y"]
            
            if abs(y1 - y0) > 5:  
                new_sys = {
                    "top": min(y0, y1) / self.scale,
                    "bot": max(y0, y1) / self.scale,
                    "is_content": True,
                    "is_reset": False
                }
                self.page_data.setdefault("systems", []).append(new_sys)
                self.page_data["systems"].sort(key=lambda s: s["top"])
                
            self.draw_boxes()
            
        self.drag_data = {"item_idx": None, "edge": None, "start_y": 0, "current_y": 0}

    def on_right_click(self, event):
        y = self.canvas.canvasy(event.y)
        idx = self.get_system_at_y(y)
        if idx is not None:
            self.save_state()
            sys = self.page_data["systems"][idx]
            sys["is_reset"] = not sys.get("is_reset", False)
            self.draw_boxes()

    def on_shift_right_click(self, event):
        y = self.canvas.canvasy(event.y)
        idx = self.get_system_at_y(y)
        if idx is not None:
            self.save_state()
            sys = self.page_data["systems"][idx]
            sys["is_content"] = not sys.get("is_content", True)
            self.draw_boxes()

    def prev_page(self, event=None):
        if self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.load_page()

    def next_page(self, event=None):
        if self.current_page_idx < len(self.pages) - 1:
            self.current_page_idx += 1
            self.load_page()

    def save_layout(self):
        # Explicitly reconnect the decoupled pointer back to the main layout dictionary
        self.layout["pages"] = self.pages
        try:
            with open(self.layout_path, 'w') as f:
                json.dump(self.layout, f, indent=2)
            messagebox.showinfo("Saved", f"Layout successfully saved to:\n{os.path.basename(self.layout_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def save_layout_as(self):
        self.layout["pages"] = self.pages
        new_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=os.path.basename(self.layout_path)
        )
        if new_path:
            self.layout_path = new_path
            self.save_layout()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("layout_path")
    app = MusicLayoutEditor(**vars(parser.parse_args()))
    app.mainloop()
