import os
from pathlib import Path
from tkinter import filedialog, ttk, messagebox

import customtkinter as ctk
from PIL import Image

from motor import klasor_tara, arama_yap, ozet_sayilar, zorla_yeniden_oku

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_TITLE = "PRGTOK Arşiv Sistemi"


class PRGTOKApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1400x850")
        self.minsize(1180, 720)

        self.ana_klasor = ctk.StringVar(value="Henüz klasör seçilmedi")
        self.assets = Path(__file__).parent / "assets"

        self._build_ui()

    def _img(self, filename, size):
        path = self.assets / filename
        if path.exists():
            return ctk.CTkImage(Image.open(path), size=size)
        return None

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # SOL MENÜ
        self.sidebar = ctk.CTkFrame(self, width=245, corner_radius=0, fg_color="#071827")
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(20, weight=1)

        logo = self._img("logo.png", (210, 70))
        self.logo_button = ctk.CTkButton(
            self.sidebar,
            image=logo,
            text="" if logo else "Poliport",
            fg_color="transparent",
            hover_color="#0B2A44",
            command=self.anasayfa
        )
        self.logo_button.grid(row=0, column=0, padx=18, pady=(20, 4), sticky="ew")

        ctk.CTkLabel(
            self.sidebar,
            text="PRGTOK Arşiv Sistemi",
            font=("Arial", 16, "bold"),
            anchor="w"
        ).grid(row=1, column=0, padx=24, pady=(0, 18), sticky="ew")

        menu = [
            ("🏠  Anasayfa", self.anasayfa),
            ("📄  Tüm Belgeler", self.anasayfa),
            ("🔎  Arama", lambda: self.search_entry.focus()),
            ("📁  Klasör Yapısı", self.klasor_sec),
            ("📊  İşlem Raporları", self.rapor_bilgi),
            ("⚙️  Ayarlar", self.ayarlar_bilgi),
        ]

        for i, (txt, cmd) in enumerate(menu, start=2):
            ctk.CTkButton(
                self.sidebar,
                text=txt,
                anchor="w",
                height=42,
                command=cmd
            ).grid(row=i, column=0, padx=14, pady=4, sticky="ew")

        ctk.CTkLabel(
            self.sidebar,
            text="HIZLI İŞLEMLER",
            anchor="w",
            font=("Arial", 12, "bold"),
            text_color="#AFC3D5"
        ).grid(row=10, column=0, padx=24, pady=(28, 6), sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="📂  Klasör Seç",
            height=46,
            command=self.klasor_sec
        ).grid(row=11, column=0, padx=16, pady=5, sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="🚀  Klasörü Tara",
            height=46,
            fg_color="#0B7A32",
            hover_color="#0A632A",
            command=self.tara
        ).grid(row=12, column=0, padx=16, pady=5, sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="🔄  Yenile",
            height=42,
            fg_color="#27394A",
            command=self.ozet_yenile
        ).grid(row=13, column=0, padx=16, pady=5, sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="♻️  Zorla Yeniden Oku",
            height=46,
            fg_color="#6B2F00",
            hover_color="#8B3D00",
            command=self.zorla_oku
        ).grid(row=14, column=0, padx=16, pady=5, sticky="ew")

        self.signature = ctk.CTkFrame(self.sidebar, fg_color="#06111D")
        self.signature.grid(row=21, column=0, padx=12, pady=16, sticky="sew")

        ctk.CTkLabel(
            self.signature,
            text="S.SEYMEN",
            font=("Arial", 22, "bold"),
            text_color="#DCEBFF"
        ).pack(padx=10, pady=(18, 4))

        ctk.CTkLabel(
            self.signature,
            text="Versiyon: 1.0.2",
            text_color="#AFC3D5"
        ).pack(padx=10, pady=(0, 18))

        # ANA ALAN
        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color="#071320")
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(5, weight=1)

        header_img = self._img("header.jpg", (1150, 170)) or self._img("terminal.jpg", (1150, 170))
        self.header = ctk.CTkLabel(
            self.main,
            image=header_img,
            text="" if header_img else "PRGTOK Arşiv Sistemi",
            height=170
        )
        self.header.grid(row=0, column=0, sticky="ew")

        self.path_bar = ctk.CTkFrame(self.main, fg_color="#0B1E30")
        self.path_bar.grid(row=1, column=0, padx=18, pady=(12, 6), sticky="ew")
        self.path_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.path_bar,
            text="Seçili Klasör:",
            font=("Arial", 13, "bold")
        ).grid(row=0, column=0, padx=12, pady=9)

        ctk.CTkEntry(
            self.path_bar,
            textvariable=self.ana_klasor
        ).grid(row=0, column=1, padx=8, pady=9, sticky="ew")

        ctk.CTkButton(
            self.path_bar,
            text="Seç",
            width=90,
            command=self.klasor_sec
        ).grid(row=0, column=2, padx=8, pady=9)

        # ÜST ÖZET KARTLARI
        self.stats_frame = ctk.CTkFrame(self.main, fg_color="transparent")
        self.stats_frame.grid(row=2, column=0, padx=18, pady=6, sticky="ew")

        for i in range(5):
            self.stats_frame.grid_columnconfigure(i, weight=1)

        self.stat_labels = {}
        stat_names = [
            ("TOPLAM", "Toplam Belge"),
            ("TANK_BASINC_RAPORU", "Tank Basınç"),
            ("OKUNAMAYANLAR", "Okunamayan"),
            ("FARKLI_FORMAT_DOSYALAR", "Farklı Format"),
            ("YABANCI_PLAKA", "Yabancı Plaka"),
        ]

        for i, (key, label) in enumerate(stat_names):
            card = ctk.CTkFrame(self.stats_frame, fg_color="#10283D", corner_radius=14)
            card.grid(row=0, column=i, padx=7, sticky="ew")

            ctk.CTkLabel(card, text=label, font=("Arial", 13)).pack(pady=(12, 2))

            val = ctk.CTkLabel(card, text="0", font=("Arial", 28, "bold"))
            val.pack(pady=(0, 12))

            self.stat_labels[key] = val

        # KATEGORİLER
        self.cat_frame = ctk.CTkFrame(self.main, fg_color="#0B1E30", corner_radius=12)
        self.cat_frame.grid(row=3, column=0, padx=18, pady=8, sticky="ew")

        for i in range(4):
            self.cat_frame.grid_columnconfigure(i, weight=1)  # 13 kategori, 4 sütun (4 satır)

        categories = [
            "TANK_BASINC_RAPORU",
            "ISOPA",
            "T9_GECICI",
            "T9_MUAYENE",
            "T9_ANA",
            "TRAFIK_SIGORTASI",
            "TEHLIKELI_MADDE_SIGORTASI",
            "FENNI_MUAYENE",
            "SIZDIRMAZLIK",
            "YUKSEKTE_CALISABILIR_SAGLIK_RAPORU",
            "SRC5",
            "YABANCI_PLAKA",
            "DIGER_BELGELER",
            "OKUNAMAYANLAR",
            "FARKLI_FORMAT_DOSYALAR",
        ]

        self.cat_labels = {}

        for i, cat in enumerate(categories):
            r, c = divmod(i, 4)

            box = ctk.CTkFrame(self.cat_frame, fg_color="#10283D", corner_radius=10)
            box.grid(row=r, column=c, padx=8, pady=8, sticky="ew")

            ctk.CTkLabel(
                box,
                text=cat.replace("_", " "),
                font=("Arial", 12, "bold")
            ).pack(anchor="w", padx=12, pady=(10, 0))

            val = ctk.CTkLabel(box, text="0", font=("Arial", 20, "bold"))
            val.pack(anchor="w", padx=12, pady=(0, 10))

            self.cat_labels[cat] = val

        # ARAMA ALANI
        self.search_frame = ctk.CTkFrame(self.main, fg_color="#0B1E30", corner_radius=12)
        self.search_frame.grid(row=4, column=0, padx=18, pady=8, sticky="ew")
        self.search_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.search_frame,
            text="Hızlı Arama",
            font=("Arial", 14, "bold")
        ).grid(row=0, column=0, padx=14, pady=12)

        self.search_entry = ctk.CTkEntry(
            self.search_frame,
            placeholder_text="Plaka, Tank No, Şasi No, Sürücü adı veya firma adı giriniz..."
        )
        self.search_entry.grid(row=0, column=1, padx=8, pady=12, sticky="ew")
        self.search_entry.bind("<Return>", lambda e: self.ara())

        ctk.CTkButton(
            self.search_frame,
            text="Ara",
            width=120,
            command=self.ara
        ).grid(row=0, column=2, padx=12, pady=12)

        # TABLO
        self.table_frame = ctk.CTkFrame(self.main, fg_color="#0B1E30", corner_radius=12)
        self.table_frame.grid(row=5, column=0, padx=18, pady=(8, 12), sticky="nsew")
        self.table_frame.grid_rowconfigure(1, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

        self.result_title = ctk.CTkLabel(
            self.table_frame,
            text="Arama Sonuçları",
            font=("Arial", 15, "bold"),
            anchor="w"
        )
        self.result_title.grid(row=0, column=0, padx=14, pady=10, sticky="ew")

        columns = [
            "Yeni Dosya Adı",
            "Belge Türü",
            "Plaka",
            "Tank No",
            "Şasi No",
            "Yabancı Plaka",
            "Geçerlilik Tarihi",
            "Kapasite",
            "Tank Kodu",
            "Yeni Klasör",
            "Tam Yol",
            "İşlem Durumu",
        ]

        col_widths = {
            "Yeni Dosya Adı": 220,
            "Tam Yol": 340,
            "Yeni Klasör": 160,
        }

        self.tree = ttk.Treeview(self.table_frame, columns=columns, show="headings")

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths.get(col, 130), anchor="w")

        self.tree.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")

        self.status = ctk.CTkLabel(
            self.main,
            text="● Sistem hazır",
            anchor="w",
            text_color="#83E082"
        )
        self.status.grid(row=6, column=0, padx=18, pady=(0, 8), sticky="ew")

    def anasayfa(self):
        self.ozet_yenile()
        self.result_title.configure(text="Arama Sonuçları")
        self.status.configure(text="● Anasayfa")

    def klasor_sec(self):
        yol = filedialog.askdirectory(title="Taranacak ana klasörü seç")
        if yol:
            self.ana_klasor.set(yol)
            self.ozet_yenile()
            self.status.configure(text="● Klasör seçildi")

    def tara(self):
        yol = self.ana_klasor.get()

        if not os.path.isdir(yol):
            messagebox.showwarning("Klasör seç", "Önce taranacak ana klasörü seç.")
            return

        self.status.configure(text="● Tarama başladı...")
        self.update_idletasks()

        try:
            df = klasor_tara(
                yol,
                log_callback=lambda msg: self.status.configure(text="● " + str(msg)[:120])
            )

            self.status.configure(text=f"● Tarama tamamlandı. İşlenen kayıt: {len(df)}")
            self.ozet_yenile()
            self.tablo_doldur(df.tail(300))

        except Exception as e:
            messagebox.showerror("Hata", str(e))
            self.status.configure(text="● Hata oluştu")

    def ara(self):
        yol = self.ana_klasor.get()

        if not os.path.isdir(yol):
            messagebox.showwarning("Klasör seç", "Önce ana klasörü seç.")
            return

        q = self.search_entry.get().strip()
        df = arama_yap(yol, q)

        self.result_title.configure(text=f"Arama Sonuçları ({q}) - {len(df)} kayıt")
        self.tablo_doldur(df)

    def tablo_doldur(self, df):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if df is None or df.empty:
            return

        columns = list(self.tree["columns"])

        for _, row in df.iterrows():
            values = [str(row.get(col, "")) for col in columns]
            self.tree.insert("", "end", values=values)

    def ozet_yenile(self):
        yol = self.ana_klasor.get()

        if not os.path.isdir(yol):
            return

        ozet = ozet_sayilar(yol)

        for key, lbl in self.stat_labels.items():
            lbl.configure(text=str(ozet.get(key, 0)))

        for key, lbl in self.cat_labels.items():
            lbl.configure(text=str(ozet.get(key, 0)))

    def zorla_oku(self):
        yol = self.ana_klasor.get()
        if not os.path.isdir(yol):
            messagebox.showwarning("Klasör seç", "Önce ana klasörü seç.")
            return
        self.status.configure(text="● Zorla okuma başladı...")
        self.update_idletasks()
        try:
            df = zorla_yeniden_oku(
                yol,
                log_callback=lambda msg: self.status.configure(text="● " + str(msg)[:120])
            )
            self.status.configure(text=f"● Zorla okuma tamamlandı. İşlenen: {len(df)} dosya")
            self.ozet_yenile()
            if df is not None and not df.empty:
                self.tablo_doldur(df)
        except Exception as e:
            messagebox.showerror("Hata", str(e))
            self.status.configure(text="● Hata oluştu")

    def rapor_bilgi(self):
        messagebox.showinfo(
            "Raporlar",
            "Raporlar seçili klasör / ISLEM_RAPORLARI klasöründe oluşur."
        )

    def ayarlar_bilgi(self):
        messagebox.showinfo(
            "Ayarlar",
            "İşlem kodu: PRGTOK\n\nPRGTOK olan dosyalar tekrar okunmaz; yanlış klasördeyse doğru klasöre taşınır."
        )


if __name__ == "__main__":
    app = PRGTOKApp()
    app.mainloop()