import os
import re
import shutil
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None


APP_TITLE = "PRGTOK Manuel Düzeltme"

SUPPORTED_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png"]

DOCUMENT_TYPES = {
    "T9": "T9",
    "TANK BASINC RAPORU": "TANK BASINC RAPORU",
    "SIZDIRMAZLIK": "SIZDIRMAZLIK",
    "FENNI MUAYENE": "FENNI MUAYENE",
    "TRAFIK SIGORTASI": "TRAFIK SIGORTASI",
    "TEHLIKELI MADDE SIGORTASI": "TEHLIKELI MADDE SIGORTASI",
    "ISOPA": "ISOPA",
    "SRC5": "SRC5",
    "YUKSEKTE CALISABILIR SAGLIK RAPORU": "YUKSEKTE CALISABILIR SAGLIK RAPORU",
    "YABANCI PLAKA": "YABANCI PLAKA",
    "DIGER BELGELER": "DIGER BELGELER",
}

UNREAD_FOLDER_CANDIDATES = [
    "OKUNAMAYAN PDF",
    "OKUNAMAYANLAR",
    "OKUNAMAYAN",
    "OKUNAMAYAN DOSYALAR",
    "OKUNAMAYAN BELGELER",
]

SETTINGS_FILE = "settings_paned.json"

# Ana programla uyumlu koyu lacivert renk paleti
COLORS = {
    "bg":           "#071320",   # Ana arka plan (RENK_ANA_ARKA)
    "panel":        "#0B1E30",   # Panel arka planı (RENK_PANEL)
    "sidebar":      "#071827",   # Kenar çubuğu (RENK_SIDEBAR)
    "card":         "#10283D",   # Kart/çerçeve arka planı (RENK_KART)
    "text":         "#DCEBFF",   # Ana metin rengi
    "muted":        "#7FA8C9",   # Soluk/ikincil metin
    "accent":       "#1A6FBF",   # Vurgu/buton rengi (mavi)
    "accent_hover": "#2185D8",   # Hover rengi
    "success":      "#0B7A32",   # Yeşil (tara butonu rengi)
    "warning":      "#83E0FF",   # Camgöbeği (son tarama etiketi gibi)
    "danger":       "#5A1E1E",   # Kırmızı/koyu (sil/atla)
    "listbg":       "#0D2236",   # Dosya listesi arka planı
    "listfg":       "#DCEBFF",   # Dosya listesi metin rengi
    "entry_bg":     "#0D2236",   # Giriş kutusu arka planı
    "entry_fg":     "#DCEBFF",   # Giriş kutusu metin rengi
    "canvas_bg":    "#071320",   # Önizleme canvas arka planı
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_settings():
    path = app_dir() / SETTINGS_FILE
    if not path.exists():
        return {"root_folder": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"root_folder": ""}


def save_settings(data):
    path = app_dir() / SETTINGS_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_text(text: str) -> str:
    tr_map = str.maketrans("ığüşöçİĞÜŞÖÇ", "igusocIGUSOC")
    text = text.translate(tr_map)
    text = text.upper()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def find_unread_folder(root_folder: Path) -> Path:
    if not root_folder.exists():
        return root_folder / "OKUNAMAYAN PDF"

    candidates = [normalize_text(x) for x in UNREAD_FOLDER_CANDIDATES]

    for child in root_folder.iterdir():
        if child.is_dir() and normalize_text(child.name) in candidates:
            return child

    for child in root_folder.iterdir():
        if child.is_dir() and "OKUNAMAYAN" in normalize_text(child.name):
            return child

    unread = root_folder / "OKUNAMAYAN PDF"
    unread.mkdir(parents=True, exist_ok=True)
    return unread


def sanitize_filename(name: str) -> str:
    name = name.strip()
    tr_map = str.maketrans("ığüşöçİĞÜŞÖÇ", "igusocIGUSOC")
    name = name.translate(tr_map)
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("._ ")


def ensure_e_suffix(stem: str) -> str:
    stem = stem.strip()
    stem = re.sub(r"(_PRGTOK|_P|_E)$", "", stem, flags=re.IGNORECASE)
    return f"{stem} E"


def unique_path(target: Path) -> Path:
    if not target.exists():
        return target

    parent = target.parent
    stem = target.stem
    suffix = target.suffix
    counter = 1

    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


class ManualCorrectionApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1500x850")
        self.root.minsize(1250, 720)
        self.root.configure(bg=COLORS["bg"])

        # Uygulama ikonu
        self._ikon_ayarla()

        self.settings = load_settings()
        root_value = self.settings.get("root_folder", "")
        self.root_folder = Path(root_value).expanduser() if root_value else None
        self.unread_folder = None
        self.files = []
        self.filtered_files = []
        self.index = 0

        self.current_image_ref = None
        self.base_preview_image = None
        self.zoom_level = 1.0
        self.current_file_path = None
        self._logo_ref = None  # Logo için referans

        self.setup_style()
        self.create_widgets()
        self.bind_shortcuts()

        if self.root_folder and self.root_folder.exists():
            self.set_root_folder(self.root_folder)
        else:
            self.ask_root_folder()

    def _ikon_ayarla(self):
        """Program ikonunu assets klasöründen yükler."""
        try:
            icon_path = app_dir() / "assets" / "app_icon.ico"
            if icon_path.exists() and sys.platform.startswith("win"):
                self.root.iconbitmap(str(icon_path))
            else:
                png_path = app_dir() / "assets" / "app_icon.png"
                if png_path.exists() and Image is not None:
                    img = Image.open(str(png_path))
                    photo = ImageTk.PhotoImage(img)
                    self.root.iconphoto(True, photo)
        except Exception:
            pass

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg      = COLORS["bg"]
        panel   = COLORS["panel"]
        card    = COLORS["card"]
        text    = COLORS["text"]
        muted   = COLORS["muted"]
        accent  = COLORS["accent"]
        ahover  = COLORS["accent_hover"]
        entry   = COLORS["entry_bg"]
        efg     = COLORS["entry_fg"]
        warn    = COLORS["warning"]

        style.configure(".",
            background=bg, foreground=text,
            fieldbackground=entry, font=("Segoe UI", 10))

        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("Card.TFrame", background=card)
        style.configure("Sidebar.TFrame", background=COLORS["sidebar"])

        style.configure("TLabel",        background=bg,    foreground=text)
        style.configure("Panel.TLabel",  background=panel, foreground=text)
        style.configure("Card.TLabel",   background=card,  foreground=text)
        style.configure("Muted.TLabel",  background=panel, foreground=muted)
        style.configure("SidebarMuted.TLabel", background=COLORS["sidebar"], foreground=muted)

        style.configure("Title.TLabel",
            background=panel, foreground=text,
            font=("Segoe UI", 15, "bold"))
        style.configure("AppTitle.TLabel",
            background=COLORS["sidebar"], foreground=text,
            font=("Segoe UI", 13, "bold"))
        style.configure("AppSub.TLabel",
            background=COLORS["sidebar"], foreground=muted,
            font=("Segoe UI", 9))
        style.configure("Progress.TLabel",
            background=panel, foreground=warn,
            font=("Segoe UI", 12, "bold"))

        # Butonlar
        style.configure("TButton",
            background=accent, foreground="white",
            padding=8, borderwidth=0, relief="flat",
            font=("Segoe UI", 10))
        style.map("TButton",
            background=[("active", ahover), ("pressed", ahover)])

        style.configure("Success.TButton",
            background=COLORS["success"], foreground="white",
            padding=8, borderwidth=0, relief="flat",
            font=("Segoe UI", 10, "bold"))
        style.map("Success.TButton",
            background=[("active", "#0A9A3E"), ("pressed", "#086B2A")])

        style.configure("Danger.TButton",
            background=COLORS["danger"], foreground="white",
            padding=8, borderwidth=0, relief="flat",
            font=("Segoe UI", 10))
        style.map("Danger.TButton",
            background=[("active", "#7A2A2A"), ("pressed", "#5A1E1E")])

        # Giriş/Combobox
        style.configure("TEntry",
            fieldbackground=entry, foreground=efg,
            padding=5, insertcolor=text)
        style.configure("TCombobox",
            fieldbackground=entry, foreground=efg,
            padding=5, selectbackground=accent, selectforeground="white")
        style.map("TCombobox",
            fieldbackground=[("readonly", entry)],
            foreground=[("readonly", efg)])

        # Scrollbar
        style.configure("TScrollbar",
            background=card, troughcolor=bg,
            arrowcolor=muted, borderwidth=0)

        # LabelFrame
        style.configure("TLabelframe",
            background=panel, foreground=text, bordercolor=card)
        style.configure("TLabelframe.Label",
            background=panel, foreground=muted,
            font=("Segoe UI", 9, "bold"))

    def create_widgets(self):
        # ── Üst başlık çubuğu ─────────────────────────────────────────
        self.top_frame = ttk.Frame(self.root, style="Panel.TFrame", padding=(12, 8))
        self.top_frame.pack(fill="x", padx=0, pady=0)

        # Logo
        logo_path = app_dir() / "assets" / "logo.png"
        if logo_path.exists() and Image is not None:
            try:
                img = Image.open(str(logo_path)).convert("RGBA")
                img.thumbnail((48, 48), Image.LANCZOS)
                self._logo_ref = ImageTk.PhotoImage(img)
                logo_lbl = ttk.Label(
                    self.top_frame, image=self._logo_ref,
                    background=COLORS["panel"]
                )
                logo_lbl.pack(side="left", padx=(4, 10))
            except Exception:
                pass

        # Başlık metni
        title_block = ttk.Frame(self.top_frame, style="Panel.TFrame")
        title_block.pack(side="left")
        ttk.Label(title_block, text="PRGTOK Manuel Düzeltme",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_block, text="PREGATE Arşiv Sistemi — Okunamayan Belge Düzenleme Aracı",
                  style="Muted.TLabel").pack(anchor="w")

        # Klasör etiketi
        self.folder_label = ttk.Label(
            self.top_frame, text="Klasör seçilmedi",
            style="Muted.TLabel"
        )
        self.folder_label.pack(side="left", padx=20, fill="x", expand=True)

        # Sağdaki butonlar
        ttk.Button(self.top_frame, text="🔄 Yenile",
                   command=self.refresh_files).pack(side="right", padx=4)
        ttk.Button(self.top_frame, text="📂 Ana Klasör Seç",
                   command=self.ask_root_folder).pack(side="right", padx=4)

        # İnce ayırıcı çizgi
        sep = tk.Frame(self.root, bg=COLORS["card"], height=2)
        sep.pack(fill="x")

        # ── Sürüklenebilir ana alan ────────────────────────────────────
        self.paned = tk.PanedWindow(
            self.root,
            orient=tk.HORIZONTAL,
            bg=COLORS["bg"],
            sashwidth=6,
            sashrelief=tk.FLAT,
            bd=0
        )
        self.paned.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Sol: Dosya listesi ─────────────────────────────────────────
        self.list_frame = tk.Frame(self.paned, bg=COLORS["sidebar"])
        self.paned.add(self.list_frame, minsize=260, width=360)

        list_header = tk.Frame(self.list_frame, bg=COLORS["sidebar"])
        list_header.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(list_header, text="📄 Dosya Listesi",
                 bg=COLORS["sidebar"], fg=COLORS["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        search_frame = tk.Frame(self.list_frame, bg=COLORS["sidebar"])
        search_frame.pack(fill="x", padx=12, pady=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.apply_filter())
        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
            insertbackground=COLORS["text"],
            relief="flat", font=("Segoe UI", 10),
            bd=6
        )
        self.search_entry.pack(fill="x")

        self.file_count_label = tk.Label(
            self.list_frame, text="0 dosya",
            bg=COLORS["sidebar"], fg=COLORS["muted"],
            font=("Segoe UI", 9)
        )
        self.file_count_label.pack(anchor="w", padx=12, pady=(0, 4))

        self.file_list_container = tk.Frame(self.list_frame, bg=COLORS["sidebar"])
        self.file_list_container.pack(fill="both", expand=True, padx=12)

        self.file_listbox = tk.Listbox(
            self.file_list_container,
            bg=COLORS["listbg"],
            fg=COLORS["listfg"],
            selectbackground=COLORS["accent"],
            selectforeground="white",
            font=("Segoe UI", 9),
            activestyle="none",
            exportselection=False,
            borderwidth=0,
            relief="flat",
            highlightthickness=1,
            highlightcolor=COLORS["card"],
            highlightbackground=COLORS["card"]
        )
        self.file_listbox.grid(row=0, column=0, sticky="nsew")

        self.file_list_vscroll = ttk.Scrollbar(
            self.file_list_container, orient="vertical",
            command=self.file_listbox.yview)
        self.file_list_vscroll.grid(row=0, column=1, sticky="ns")

        self.file_list_hscroll = ttk.Scrollbar(
            self.file_list_container, orient="horizontal",
            command=self.file_listbox.xview)
        self.file_list_hscroll.grid(row=1, column=0, sticky="ew")

        self.file_listbox.configure(
            yscrollcommand=self.file_list_vscroll.set,
            xscrollcommand=self.file_list_hscroll.set
        )
        self.file_list_container.rowconfigure(0, weight=1)
        self.file_list_container.columnconfigure(0, weight=1)

        self.file_listbox.bind("<<ListboxSelect>>", self.on_list_select)
        self.file_listbox.bind("<Double-Button-1>", self.on_list_select)

        tk.Label(
            self.list_frame,
            text="Tıkla → Atla  •  Arama: plaka/tarih/tank",
            bg=COLORS["sidebar"], fg=COLORS["muted"],
            font=("Segoe UI", 8), justify="left"
        ).pack(anchor="w", padx=12, pady=(6, 10))

        # ── Orta: PDF önizleme ─────────────────────────────────────────
        preview_outer = tk.Frame(self.paned, bg=COLORS["panel"])
        self.paned.add(preview_outer, minsize=420, width=720)

        preview_header = tk.Frame(preview_outer, bg=COLORS["card"])
        preview_header.pack(fill="x")
        tk.Label(
            preview_header,
            text="  Belge Önizleme   ·   🖱 Tekerlek: Yakınlaştır   ·   Sol Tık Basılı: Kaydır",
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Segoe UI", 9), pady=6
        ).pack(side="left")

        self.canvas_frame = tk.Frame(preview_outer, bg=COLORS["bg"])
        self.canvas_frame.pack(fill="both", expand=True)

        self.preview_canvas = tk.Canvas(
            self.canvas_frame,
            bg=COLORS["canvas_bg"],
            highlightthickness=0,
            xscrollincrement=20,
            yscrollincrement=20
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")

        self.v_scroll = ttk.Scrollbar(
            self.canvas_frame, orient="vertical",
            command=self.preview_canvas.yview)
        self.v_scroll.grid(row=0, column=1, sticky="ns")

        self.h_scroll = ttk.Scrollbar(
            self.canvas_frame, orient="horizontal",
            command=self.preview_canvas.xview)
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        self.preview_canvas.configure(
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set)
        self.canvas_frame.rowconfigure(0, weight=1)
        self.canvas_frame.columnconfigure(0, weight=1)

        self.preview_canvas.bind("<MouseWheel>", self.on_mousewheel_zoom)
        self.preview_canvas.bind("<Button-4>",   self.on_mousewheel_zoom)
        self.preview_canvas.bind("<Button-5>",   self.on_mousewheel_zoom)
        self.preview_canvas.bind("<ButtonPress-1>", self.start_pan)
        self.preview_canvas.bind("<B1-Motion>",     self.do_pan)

        # ── Sağ: Form alanı ───────────────────────────────────────────
        self.form_frame = tk.Frame(self.paned, bg=COLORS["panel"])
        self.paned.add(self.form_frame, minsize=330, width=400)

        def section(parent, title):
            """Başlıklı bölüm ayırıcısı."""
            tk.Frame(parent, bg=COLORS["card"], height=1).pack(
                fill="x", padx=14, pady=(14, 0))
            tk.Label(parent, text=title,
                     bg=COLORS["panel"], fg=COLORS["muted"],
                     font=("Segoe UI", 8, "bold")).pack(
                anchor="w", padx=14, pady=(4, 0))

        def lbl(parent, text):
            tk.Label(parent, text=text,
                     bg=COLORS["panel"], fg=COLORS["muted"],
                     font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(8, 1))

        def entry_widget(parent, var, readonly=False):
            state = "readonly" if readonly else "normal"
            e = ttk.Entry(parent, textvariable=var, state=state)
            e.pack(fill="x", padx=14, pady=(0, 2))
            return e

        # İlerleme
        self.progress_label = tk.Label(
            self.form_frame,
            text="Belge: 0 / 0",
            bg=COLORS["panel"], fg=COLORS["warning"],
            font=("Segoe UI", 14, "bold")
        )
        self.progress_label.pack(anchor="w", padx=14, pady=(14, 0))

        self.unread_label = tk.Label(
            self.form_frame, text="-",
            bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 8), wraplength=360, justify="left"
        )
        self.unread_label.pack(anchor="w", padx=14, pady=(2, 0))

        # Dosya adları
        section(self.form_frame, "DOSYA BİLGİSİ")
        lbl(self.form_frame, "Eski Dosya Adı:")
        self.old_name_var = tk.StringVar()
        self.old_name_entry = entry_widget(self.form_frame, self.old_name_var, readonly=True)

        lbl(self.form_frame, "Yeni Dosya Adı:")
        self.new_name_var = tk.StringVar()
        self.new_name_entry = entry_widget(self.form_frame, self.new_name_var)

        # Belge türü
        section(self.form_frame, "SINIFLANDIRMA")
        lbl(self.form_frame, "Belge Türü:")
        self.doc_type_var = tk.StringVar()
        self.doc_type_combo = ttk.Combobox(
            self.form_frame,
            textvariable=self.doc_type_var,
            values=list(DOCUMENT_TYPES.keys()),
            state="readonly"
        )
        self.doc_type_combo.pack(fill="x", padx=14, pady=(0, 4))

        # Zoom
        section(self.form_frame, "ÖNİZLEME")
        self.zoom_label = tk.Label(
            self.form_frame, text="Zoom: 100%",
            bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 9)
        )
        self.zoom_label.pack(anchor="w", padx=14, pady=(6, 4))

        zoom_row = tk.Frame(self.form_frame, bg=COLORS["panel"])
        zoom_row.pack(fill="x", padx=14, pady=(0, 2))
        ttk.Button(zoom_row, text="🔍 Yakınlaştır +",
                   command=lambda: self.change_zoom(1.15)).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(zoom_row, text="🔎 Uzaklaştır −",
                   command=lambda: self.change_zoom(1 / 1.15)).pack(
            side="left", fill="x", expand=True, padx=(3, 0))
        ttk.Button(self.form_frame, text="⛶ Sayfaya Sığdır",
                   command=self.fit_to_canvas).pack(
            fill="x", padx=14, pady=(2, 0))

        # İşlem butonları
        section(self.form_frame, "İŞLEMLER")

        self.save_btn = ttk.Button(
            self.form_frame,
            text="✅  Kaydet ve Sonraki   (Enter)",
            style="Success.TButton",
            command=self.save_and_next
        )
        self.save_btn.pack(fill="x", padx=14, pady=(8, 3))

        btn_row = tk.Frame(self.form_frame, bg=COLORS["panel"])
        btn_row.pack(fill="x", padx=14, pady=3)
        ttk.Button(btn_row, text="◀  Geri  (Ctrl+Sol)",
                   style="Danger.TButton",
                   command=self.prev_file).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        ttk.Button(btn_row, text="Atla  (Ctrl+Sağ)  ▶",
                   command=self.next_file).pack(
            side="left", fill="x", expand=True, padx=(3, 0))

        ttk.Button(
            self.form_frame, text="↗  PDF'yi Dışarıda Aç",
            command=self.open_current_external
        ).pack(fill="x", padx=14, pady=(8, 2))

        # Durum
        self.status_label = tk.Label(
            self.form_frame, text="",
            bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Segoe UI", 9), wraplength=360, justify="left"
        )
        self.status_label.pack(anchor="w", padx=14, pady=(10, 0))

        # Kısayol yardımı
        section(self.form_frame, "KISAYOLLAR")
        kisayollar = (
            "Enter          Kaydet ve Sonraki\n"
            "F2              Yeni dosya adı\n"
            "F3              Belge türü\n"
            "Ctrl + →     Sonraki\n"
            "Ctrl + ←     Önceki\n"
            "Ctrl + F       Arama\n"
            "Ctrl + +/−   Zoom"
        )
        tk.Label(
            self.form_frame, text=kisayollar,
            bg=COLORS["panel"], fg=COLORS["muted"],
            font=("Courier New", 8), justify="left"
        ).pack(anchor="w", padx=14, pady=(6, 14))

    # ──────────────────────────────────────────────────────────────────
    # Aşağıdaki tüm metotlar orijinal main_paned.py ile BİREBİR AYNI
    # (yazılımsal mantığa dokunulmadı)
    # ──────────────────────────────────────────────────────────────────

    def bind_shortcuts(self):
        self.root.bind("<Return>",        lambda e: self.save_and_next())
        self.root.bind("<Control-Right>", lambda e: self.next_file())
        self.root.bind("<Control-Left>",  lambda e: self.prev_file())
        self.root.bind("<F2>",            lambda e: self.focus_new_name())
        self.root.bind("<F3>",            lambda e: self.focus_doc_type())
        self.root.bind("<Control-f>",     lambda e: self.focus_search())
        self.root.bind("<Control-F>",     lambda e: self.focus_search())
        self.root.bind("<Control-plus>",  lambda e: self.change_zoom(1.15))
        self.root.bind("<Control-minus>", lambda e: self.change_zoom(1 / 1.15))

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)

    def focus_new_name(self):
        self.new_name_entry.focus_set()
        self.new_name_entry.selection_range(0, tk.END)

    def focus_doc_type(self):
        self.doc_type_combo.focus_set()
        self.doc_type_combo.event_generate("<Button-1>")

    def ask_root_folder(self):
        folder = filedialog.askdirectory(
            title="PRGTOK ana klasörünü veya OKUNAMAYAN PDF klasörünü seç")
        if folder:
            self.set_root_folder(Path(folder))

    def set_root_folder(self, folder: Path):
        normalized = normalize_text(folder.name)

        if "OKUNAMAYAN" in normalized:
            self.unread_folder = folder
            self.root_folder = folder.parent
        else:
            self.root_folder = folder
            self.unread_folder = find_unread_folder(folder)

        self.settings["root_folder"] = str(self.root_folder)
        save_settings(self.settings)

        self.folder_label.config(text=f"Ana klasör: {self.root_folder}")
        self.unread_label.config(text=str(self.unread_folder))

        self.refresh_files()

    def refresh_files(self):
        if not self.root_folder:
            return

        if self.unread_folder is None or not self.unread_folder.exists():
            self.unread_folder = find_unread_folder(self.root_folder)

        self.unread_label.config(text=str(self.unread_folder))

        self.files = sorted([
            p for p in self.unread_folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ])

        self.apply_filter(reset_index=True)

    def apply_filter(self, reset_index=False):
        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""

        if query:
            self.filtered_files = [p for p in self.files if query in p.name.lower()]
        else:
            self.filtered_files = list(self.files)

        self.rebuild_file_listbox()

        if reset_index:
            self.index = 0

        if self.filtered_files:
            if self.index >= len(self.filtered_files):
                self.index = len(self.filtered_files) - 1
            if self.index < 0:
                self.index = 0
            self.load_current()
        else:
            self.index = 0
            self.load_current()

    def rebuild_file_listbox(self):
        if not hasattr(self, "file_listbox"):
            return

        self.file_listbox.delete(0, tk.END)

        for i, path in enumerate(self.filtered_files, start=1):
            self.file_listbox.insert(tk.END, f"{i:04d}  {path.name}")

        if hasattr(self, "file_count_label"):
            self.file_count_label.config(
                text=f"{len(self.filtered_files)} / {len(self.files)} dosya")

    def select_current_in_listbox(self):
        if not hasattr(self, "file_listbox") or not self.filtered_files:
            return

        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(self.index)
        self.file_listbox.activate(self.index)
        self.file_listbox.see(self.index)

    def on_list_select(self, event=None):
        if not self.filtered_files:
            return

        selection = self.file_listbox.curselection()
        if not selection:
            return

        self.index = int(selection[0])
        self.load_current()

    def get_current_files(self):
        return self.filtered_files

    def load_current(self):
        self.preview_canvas.delete("all")
        self.current_image_ref = None
        self.base_preview_image = None
        self.current_file_path = None
        self.zoom_level = 1.0
        self.update_zoom_label()

        current_files = self.get_current_files()
        total = len(current_files)

        if total == 0:
            self.progress_label.config(text="Belge: 0 / 0")
            self.old_name_var.set("")
            self.new_name_var.set("")
            self.doc_type_var.set("")
            self.status_label.config(
                text="Listede PDF/JPG/PNG yok veya arama sonucu boş.")
            self.preview_canvas.create_text(
                420, 300,
                text="Dosya bulunamadı.\nArama kutusunu temizle veya klasörü kontrol et.",
                font=("Segoe UI", 18),
                fill=COLORS["muted"]
            )
            return

        self.index = max(0, min(self.index, total - 1))
        file_path = current_files[self.index]
        self.current_file_path = file_path

        self.progress_label.config(
            text=f"Belge: {self.index + 1} / {total}   ·   Kalan: {total - self.index - 1}")
        self.old_name_var.set(file_path.name)

        clean_initial = re.sub(r"(_PRGTOK|_P|_E)$", "", file_path.stem, flags=re.IGNORECASE)
        self.new_name_var.set(clean_initial)
        self.doc_type_var.set("")

        self.status_label.config(text=f"Açılan: {file_path.name}")
        self.load_base_image(file_path)
        self.fit_to_canvas()
        self.select_current_in_listbox()
        self.focus_new_name()

    def load_base_image(self, file_path: Path):
        self.preview_canvas.delete("all")
        self.current_image_ref = None
        self.base_preview_image = None

        if Image is None or ImageTk is None:
            self.preview_canvas.create_text(
                420, 300,
                text="Pillow kurulu değil.\npip install pillow",
                font=("Segoe UI", 14),
                fill=COLORS["muted"]
            )
            return

        try:
            if file_path.suffix.lower() == ".pdf":
                if fitz is None:
                    self.preview_canvas.create_text(
                        420, 300,
                        text="PDF önizleme için PyMuPDF gerekli:\npip install pymupdf",
                        font=("Segoe UI", 14),
                        fill=COLORS["muted"]
                    )
                    return

                doc = fitz.open(str(file_path))
                page = doc.load_page(0)
                mat = fitz.Matrix(3.0, 3.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                doc.close()
            else:
                img = Image.open(file_path).convert("RGB")

            self.base_preview_image = img

        except Exception as e:
            self.preview_canvas.create_text(
                420, 300,
                text=f"Önizleme hatası:\n{e}",
                font=("Segoe UI", 14),
                fill="#B91C1C"
            )

    def fit_to_canvas(self):
        if self.base_preview_image is None:
            return

        self.preview_canvas.update_idletasks()
        canvas_w = max(self.preview_canvas.winfo_width(), 650)
        canvas_h = max(self.preview_canvas.winfo_height(), 620)

        img_w, img_h = self.base_preview_image.size
        if img_w <= 0 or img_h <= 0:
            return

        scale_w = (canvas_w - 30) / img_w
        scale_h = (canvas_h - 30) / img_h
        self.zoom_level = max(0.15, min(scale_w, scale_h))
        self.render_preview()

    def render_preview(self):
        if self.base_preview_image is None:
            return

        self.preview_canvas.delete("all")

        img_w, img_h = self.base_preview_image.size
        new_w = max(50, int(img_w * self.zoom_level))
        new_h = max(50, int(img_h * self.zoom_level))

        resized = self.base_preview_image.resize((new_w, new_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        self.current_image_ref = photo

        canvas_w = max(self.preview_canvas.winfo_width(), 650)
        canvas_h = max(self.preview_canvas.winfo_height(), 620)

        x = max(10, (canvas_w - new_w) // 2)
        y = max(10, (canvas_h - new_h) // 2)

        self.preview_canvas.create_image(x, y, image=photo, anchor="nw")
        self.preview_canvas.configure(
            scrollregion=(0, 0,
                          max(new_w + 20, canvas_w),
                          max(new_h + 20, canvas_h)))
        self.update_zoom_label()

    def update_zoom_label(self):
        if hasattr(self, "zoom_label"):
            self.zoom_label.config(text=f"Zoom: {int(self.zoom_level * 100)}%")

    def change_zoom(self, factor):
        if self.base_preview_image is None:
            return
        self.zoom_level = max(0.10, min(5.0, self.zoom_level * factor))
        self.render_preview()

    def on_mousewheel_zoom(self, event):
        if self.base_preview_image is None:
            return

        if hasattr(event, "delta"):
            if event.delta > 0:
                self.change_zoom(1.12)
            else:
                self.change_zoom(1 / 1.12)
        else:
            if event.num == 4:
                self.change_zoom(1.12)
            elif event.num == 5:
                self.change_zoom(1 / 1.12)

    def start_pan(self, event):
        self.preview_canvas.scan_mark(event.x, event.y)

    def do_pan(self, event):
        self.preview_canvas.scan_dragto(event.x, event.y, gain=1)

    def target_folder_for_doc_type(self, doc_type: str) -> Path:
        folder_name = DOCUMENT_TYPES.get(doc_type, "DIGER BELGELER")
        target = self.root_folder / "PREGATE ARSIV" / folder_name
        target.mkdir(parents=True, exist_ok=True)
        return target

    def save_and_next(self):
        current_files = self.get_current_files()

        if not current_files:
            return

        doc_type = self.doc_type_var.get().strip()
        if not doc_type:
            messagebox.showwarning("Eksik Bilgi",
                                   "Belge türü seçilmeden kaydedilemez.")
            return

        file_path = current_files[self.index]
        edited_name = self.new_name_var.get().strip()

        if not edited_name:
            messagebox.showwarning("Eksik Bilgi",
                                   "Yeni dosya adı boş olamaz.")
            return

        clean_stem = sanitize_filename(edited_name)
        clean_stem = ensure_e_suffix(clean_stem)

        target_folder = self.target_folder_for_doc_type(doc_type)
        target_path = unique_path(
            target_folder / f"{clean_stem}{file_path.suffix.lower()}")

        try:
            shutil.move(str(file_path), str(target_path))
            self.status_label.config(
                text=f"✅  Taşındı: {target_path.name}")

            self.files = [p for p in self.files if p != file_path]
            self.filtered_files = [p for p in self.filtered_files if p != file_path]

            if self.index >= len(self.filtered_files):
                self.index = max(0, len(self.filtered_files) - 1)

            self.rebuild_file_listbox()
            self.load_current()

        except Exception as e:
            messagebox.showerror("Taşıma Hatası", str(e))

    def next_file(self):
        current_files = self.get_current_files()

        if not current_files:
            return

        if self.index < len(current_files) - 1:
            self.index += 1
            self.load_current()
        else:
            self.status_label.config(text="Son dosyadasın.")

    def prev_file(self):
        current_files = self.get_current_files()

        if not current_files:
            return

        if self.index > 0:
            self.index -= 1
            self.load_current()
        else:
            self.status_label.config(text="İlk dosyadasın.")

    def open_current_external(self):
        current_files = self.get_current_files()

        if not current_files:
            return

        file_path = current_files[self.index]

        try:
            if sys.platform.startswith("win"):
                os.startfile(file_path)
            elif sys.platform == "darwin":
                os.system(f'open "{file_path}"')
            else:
                os.system(f'xdg-open "{file_path}"')
        except Exception as e:
            messagebox.showerror("Açma Hatası", str(e))


def main():
    root = tk.Tk()
    ManualCorrectionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
