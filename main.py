# ============================================================================
# PRGTOK ARSIV SISTEMI - main.py
# Surum: 2.1.0  (bkz. SURUM_GECMISI.md)
#
# v2.1.0 ARAYUZ DEGISIKLIKLERI:
#   - "Ayarlar" ve "Klasor Yapisi" menuleri kaldirildi.
#   - "Arama" artik alt sekme degil: sol menude tiklaninca UST tarafta
#     bir arama cubugu acilir/kapanir (toggle).
#   - Arama en az 3 harf yazilinca otomatik calisir, sonuclari listede
#     gosterir. Sonuc satirina CIFT TIKLAYINCA dosya isletim sisteminde
#     dogrudan acilir (Windows: os.startfile).
#   - Sonuc tablosunda "Dosya Konumu" ve "Son Islem Tarihi" sutunlari var.
#   - Tarama sirasinda ilerleme cubugu (yuzde + sayi, ör: 3/120) gosterilir.
#   - Sag ust kosede son tarama tarih/saati otomatik gosterilir.
#   - Tema acik/beyaz: ana arka plan beyaz, sol menu ve kart kutulari
#     yine koyu lacivert kaliyor (Poliport logosu ile uyum icin).
#   - Logo gorunur sekilde sol menude buyutuldu.
# ============================================================================

import os
import platform
import subprocess
import threading
from pathlib import Path
from tkinter import filedialog, ttk, messagebox, Toplevel

import customtkinter as ctk
from PIL import Image

from motor import (
    SURUM,
    klasor_tara,
    arama_yap,
    ozet_sayilar,
    zorla_yeniden_oku,
    tum_dosyalari_yeniden_tara,
    son_tarama_bilgisi_oku,
    BELGE_KLASORLERI,
    anahtar_kelimeleri_oku,
    anahtar_kelime_ekle,
    anahtar_kelime_sil,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_TITLE = f"PRGTOK Arşiv Sistemi v{SURUM}"

# Koyu lacivert tema (v2.0.0 ile aynı renk paleti - kullanıcı talebiyle geri alındı)
RENK_ANA_ARKA = "#071320"        # ana alan arka plani (koyu lacivert)
RENK_KART = "#10283D"            # ozet/kategori kartlari
RENK_PANEL = "#0B1E30"           # arama/tablo paneli
RENK_SIDEBAR = "#071827"         # sol menu arka plani
RENK_METIN_KOYU = "#DCEBFF"      # koyu zemin uzerindeki acik yazi rengi


def dosyayi_ac(tam_yol):
    try:
        if platform.system() == "Windows":
            os.startfile(tam_yol)  # noqa
        elif platform.system() == "Darwin":
            subprocess.run(["open", tam_yol], check=False)
        else:
            subprocess.run(["xdg-open", tam_yol], check=False)
    except Exception as e:
        messagebox.showerror("Açılamadı", f"Dosya açılamadı:\n{e}")


class PRGTOKApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1450x880")
        self.minsize(1180, 760)
        self.configure(fg_color=RENK_ANA_ARKA)

        self.ana_klasor = ctk.StringVar(value="Henüz klasör seçilmedi")
        self.assets = Path(__file__).parent / "assets"
        self.arama_acik = False
        self.son_arama_sorgusu = ""
        self._tam_yol_haritasi = {}

        self._ikon_ayarla()
        self._build_ui()
        self._son_tarama_etiketini_guncelle()

    def _img(self, filename, size):
        path = self.assets / filename
        if path.exists():
            return ctk.CTkImage(Image.open(path), size=size)
        return None

    def _ikon_ayarla(self):
        """Pencere/taskbar simgesini SYMN Arşiv ikonuna ayarlar.
        Windows'ta .ico kullanilir (iconbitmap); diger isletim
        sistemlerinde .ico desteklenmedigi icin .png ile iconphoto
        kullanilir, bulunamazsa sessizce atlanir (program calismayi
        durdurmaz)."""
        ico_yolu = self.assets / "app_icon.ico"
        png_yolu = self.assets / "app_icon.png"
        try:
            if platform.system() == "Windows" and ico_yolu.exists():
                self.iconbitmap(str(ico_yolu))
            elif png_yolu.exists():
                from tkinter import PhotoImage
                self._icon_photo = PhotoImage(file=str(png_yolu))
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass  # Ikon ayarlanamasa da program calismaya devam etsin

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=245, corner_radius=0, fg_color=RENK_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(20, weight=1)

        logo = self._img("logo.png", (84, 84))
        self.logo_button = ctk.CTkButton(
            self.sidebar, image=logo, text="" if logo else "Poliport",
            fg_color="transparent", hover_color="#0B2A44", command=self.anasayfa
        )
        self.logo_button.grid(row=0, column=0, padx=18, pady=(14, 2), sticky="ew")

        ctk.CTkLabel(
            self.sidebar, text="PRGTOK Arşiv Sistemi", font=("Arial", 14, "bold"), anchor="w"
        ).grid(row=1, column=0, padx=24, pady=(0, 1), sticky="ew")

        ctk.CTkLabel(
            self.sidebar, text=f"Sadece PDF • v{SURUM}", font=("Arial", 10), anchor="w",
            text_color="#7FA8C9"
        ).grid(row=2, column=0, padx=24, pady=(0, 10), sticky="ew")

        menu = [
            ("🏠 Anasayfa", self.anasayfa),
            ("📄 Tüm Belgeler", self.anasayfa),
            ("🔎 Arama", self.arama_toggle),
            ("📊 İşlem Raporları", self.rapor_bilgi),
            ("🔑 Anahtar Kelimeler", self.anahtar_kelimeler_penceresi_ac),
            ("✏️ Manuel Düzeltme", self.manuel_duzeltme_ac),
        ]
        for i, (txt, cmd) in enumerate(menu, start=3):
            ctk.CTkButton(
                self.sidebar, text=txt, anchor="w", height=34, font=("Arial", 12), command=cmd
            ).grid(row=i, column=0, padx=14, pady=3, sticky="ew")

        ctk.CTkLabel(
            self.sidebar, text="HIZLI İŞLEMLER", anchor="w", font=("Arial", 11, "bold"),
            text_color="#AFC3D5"
        ).grid(row=9, column=0, padx=24, pady=(16, 4), sticky="ew")

        ctk.CTkButton(
            self.sidebar, text="📂 Klasör Seç", height=36, font=("Arial", 12), command=self.klasor_sec
        ).grid(row=10, column=0, padx=16, pady=3, sticky="ew")

        self.btn_tara = ctk.CTkButton(
            self.sidebar, text="🚀 Klasörü Tara (PDF)", height=36, font=("Arial", 12),
            fg_color="#0B7A32", hover_color="#0A632A", command=self.tara
        )
        self.btn_tara.grid(row=11, column=0, padx=16, pady=3, sticky="ew")

        self.btn_yenile = ctk.CTkButton(
            self.sidebar, text="🔄 Yenile", height=32, font=("Arial", 12), fg_color="#27394A", command=self.ozet_yenile
        )
        self.btn_yenile.grid(row=12, column=0, padx=16, pady=3, sticky="ew")

        self.btn_zorla = ctk.CTkButton(
            self.sidebar, text="♻️ Okunamayanları Tekrar Dene", height=36, font=("Arial", 12),
            fg_color="#6B2F00", hover_color="#8B3D00", command=self.zorla_oku
        )
        self.btn_zorla.grid(row=13, column=0, padx=16, pady=3, sticky="ew")

        self.btn_tumunu = ctk.CTkButton(
            self.sidebar, text="🧠 Tümünü Yeniden Tara", height=36, font=("Arial", 12),
            fg_color="#5A1E8C", hover_color="#7327B0", command=self.tumunu_yeniden_tara
        )
        self.btn_tumunu.grid(row=14, column=0, padx=16, pady=3, sticky="ew")

        self.signature = ctk.CTkFrame(self.sidebar, fg_color="#06111D")
        self.signature.grid(row=21, column=0, padx=12, pady=(4, 8), sticky="sew")
        ctk.CTkLabel(
            self.signature, text="S.SEYMEN", font=("Arial", 13, "bold"), text_color="#DCEBFF"
        ).pack(padx=10, pady=(7, 1))
        ctk.CTkLabel(
            self.signature, text=f"Versiyon: {SURUM}", font=("Arial", 9), text_color="#AFC3D5"
        ).pack(padx=10, pady=(0, 7))

        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color=RENK_ANA_ARKA)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(7, weight=1)

        # Ust banner: gercek bir gorsel (liman/tesis fotografi) varsa orana
        # uygun, asiri ezilmeyecek bir yukseklikte (120px) gosterilir.
        # Resim yoksa kompakt koyu baslik seridi (60px) gosterilir, boylece
        # bos/beyaz alan kalmaz.
        header_img = self._img("header.jpg", (1190, 120)) or self._img("terminal.jpg", (1190, 120))
        if header_img:
            self.header = ctk.CTkLabel(self.main, image=header_img, text="", height=120)
        else:
            self.header = ctk.CTkLabel(
                self.main, text="PRGTOK Arşiv Sistemi", font=("Arial", 18, "bold"),
                height=60, fg_color=RENK_PANEL, text_color=RENK_METIN_KOYU
            )
        self.header.grid(row=0, column=0, sticky="ew")

        self.top_bar = ctk.CTkFrame(self.main, fg_color="transparent")
        self.top_bar.grid(row=1, column=0, padx=18, pady=(12, 0), sticky="ew")
        self.top_bar.grid_columnconfigure(0, weight=1)

        self.path_bar = ctk.CTkFrame(self.top_bar, fg_color=RENK_PANEL)
        self.path_bar.grid(row=0, column=0, sticky="ew")
        self.path_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.path_bar, text="Seçili Klasör:", font=("Arial", 13, "bold")).grid(
            row=0, column=0, padx=12, pady=9
        )
        ctk.CTkEntry(self.path_bar, textvariable=self.ana_klasor).grid(
            row=0, column=1, padx=8, pady=9, sticky="ew"
        )
        ctk.CTkButton(self.path_bar, text="Seç", width=90, command=self.klasor_sec).grid(
            row=0, column=2, padx=8, pady=9
        )

        self.son_tarama_label = ctk.CTkLabel(
            self.top_bar, text="Son tarama: —", font=("Arial", 12, "bold"),
            text_color="#83E0FF", anchor="e"
        )
        self.son_tarama_label.grid(row=0, column=1, padx=(12, 4), sticky="e")

        self.progress_frame = ctk.CTkFrame(self.main, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, padx=18, pady=(8, 0), sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_label = ctk.CTkLabel(
            self.progress_frame, text="", font=("Arial", 12, "bold"), text_color=RENK_METIN_KOYU
        )

        self.arama_frame = ctk.CTkFrame(self.main, fg_color=RENK_PANEL, corner_radius=12)
        self.arama_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.arama_frame, text="🔎 Arama", font=("Arial", 14, "bold")
        ).grid(row=0, column=0, padx=14, pady=12)
        self.search_entry = ctk.CTkEntry(
            self.arama_frame,
            placeholder_text="En az 3 harf yazın: Plaka, Tank No, Şasi No, Sürücü adı..."
        )
        self.search_entry.grid(row=0, column=1, padx=8, pady=12, sticky="ew")
        self.search_entry.bind("<KeyRelease>", self._arama_yazildi)
        self.search_entry.bind("<Return>", lambda e: self.ara())
        ctk.CTkButton(self.arama_frame, text="Kapat", width=90, fg_color="#5A1E1E",
                      hover_color="#7A2A2A", command=self.arama_toggle).grid(
            row=0, column=2, padx=12, pady=12
        )

        self.stats_frame = ctk.CTkFrame(self.main, fg_color="transparent")
        self.stats_frame.grid(row=4, column=0, padx=18, pady=6, sticky="ew")
        for i in range(5):
            self.stats_frame.grid_columnconfigure(i, weight=1)

        self.stat_labels = {}
        stat_names = [
            ("TOPLAM", "Toplam PDF"),
            ("TANK BASINC RAPORU", "Tank Basınç"),
            ("OKUNAMAYAN PDF", "Okunamayan PDF"),
            ("FARKLI FORMAT DOSYALAR", "Farklı Format"),
            ("YABANCI PLAKA", "Yabancı Plaka"),
        ]
        for i, (key, label) in enumerate(stat_names):
            card = ctk.CTkFrame(self.stats_frame, fg_color=RENK_KART, corner_radius=12)
            card.grid(row=0, column=i, padx=6, sticky="ew")
            ctk.CTkLabel(card, text=label, font=("Arial", 12)).pack(pady=(9, 1))
            val = ctk.CTkLabel(card, text="0", font=("Arial", 24, "bold"))
            val.pack(pady=(0, 9))
            self.stat_labels[key] = val

        self.cat_frame = ctk.CTkFrame(self.main, fg_color=RENK_PANEL, corner_radius=12)
        self.cat_frame.grid(row=5, column=0, padx=18, pady=8, sticky="ew")
        for i in range(4):
            self.cat_frame.grid_columnconfigure(i, weight=1)

        categories = [
            ("TANK BASINC RAPORU", "TANK BASINC RAPORU"),
            ("ISOPA", "ISOPA"),
            ("T9", "T9"),
            ("TRAFIK SIGORTASI", "TRAFIK SIGORTASI"),
            ("TEHLIKELI MADDE SIGORTASI", "TEHLIKELI MADDE SIGORTASI"),
            ("FENNI MUAYENE", "FENNI MUAYENE"),
            ("SIZDIRMAZLIK", "SIZDIRMAZLIK"),
            ("YUKSEKTE CALISABILIR SAGLIK RAPORU", "YUKSEKTE CALISABILIR SAGLIK RAPORU"),
            ("SRC5", "SRC5"),
            ("YABANCI PLAKA", "YABANCI PLAKA"),
            ("DIGER BELGELER", "DIGER BELGELER"),
            ("FARKLI FORMAT DOSYALAR", "FARKLI FORMAT DOSYALAR"),
            ("OKUNAMAYAN PDF", "OKUNAMAYAN PDF"),
        ]
        self.cat_labels = {}
        for i, (cat, label) in enumerate(categories):
            r, c = divmod(i, 4)
            box = ctk.CTkFrame(self.cat_frame, fg_color=RENK_KART, corner_radius=10)
            box.grid(row=r, column=c, padx=6, pady=6, sticky="ew")
            ctk.CTkLabel(box, text=label, font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
            val = ctk.CTkLabel(box, text="0", font=("Arial", 17, "bold"))
            val.pack(anchor="w", padx=10, pady=(0, 8))
            self.cat_labels[cat] = val

        self.table_frame = ctk.CTkFrame(self.main, fg_color=RENK_PANEL, corner_radius=12)
        self.table_frame.grid(row=7, column=0, padx=18, pady=(8, 12), sticky="nsew")
        self.table_frame.grid_rowconfigure(1, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

        self.result_title = ctk.CTkLabel(
            self.table_frame, text="Arama Sonuçları", font=("Arial", 15, "bold"), anchor="w"
        )
        self.result_title.grid(row=0, column=0, padx=14, pady=10, sticky="ew")

        columns = [
            "Yeni Dosya Adı", "Belge Türü", "Plaka", "Tank No", "Şasi No",
            "Yabancı Plaka", "Geçerlilik Tarihi", "Dosya Konumu", "Son İşlem Tarihi", "İşlem Durumu",
        ]
        col_widths = {"Yeni Dosya Adı": 220, "Dosya Konumu": 340, "Son İşlem Tarihi": 130}

        self.tree = ttk.Treeview(self.table_frame, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths.get(col, 120), anchor="w")
        self.tree.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.tree.bind("<Double-1>", self._tabloda_cift_tik)

        ctk.CTkLabel(
            self.table_frame, text="İpucu: bir satıra çift tıklayarak dosyayı doğrudan açabilirsiniz.",
            font=("Arial", 11), text_color="#7FA8C9"
        ).grid(row=2, column=0, padx=14, pady=(0, 8), sticky="w")

        self.status = ctk.CTkLabel(
            self.main, text="● Sistem hazır", anchor="w", text_color="#2E7D32"
        )
        self.status.grid(row=8, column=0, padx=18, pady=(0, 8), sticky="ew")

    def arama_toggle(self):
        if self.arama_acik:
            self.arama_frame.grid_forget()
            self.arama_acik = False
        else:
            self.arama_frame.grid(row=3, column=0, padx=18, pady=8, sticky="ew")
            self.arama_acik = True
            self.search_entry.focus()

    def _arama_yazildi(self, event=None):
        q = self.search_entry.get().strip()
        if len(q) < 3:
            if len(q) == 0:
                self.result_title.configure(text="Arama Sonuçları")
                self.tablo_doldur(None)
            return
        if q == self.son_arama_sorgusu:
            return
        self.son_arama_sorgusu = q
        self.ara()

    def anasayfa(self):
        self.ozet_yenile()
        self.result_title.configure(text="Arama Sonuçları")
        self.status.configure(text="● Anasayfa")

    def klasor_sec(self):
        yol = filedialog.askdirectory(title="Taranacak ana klasörü seç")
        if yol:
            self.ana_klasor.set(yol)
            self.ozet_yenile()
            self._son_tarama_etiketini_guncelle()
            self.status.configure(text="● Klasör seçildi")

    def _durum_guncelle(self, msg):
        self.status.configure(text="● " + str(msg)[:120])

    def _son_tarama_etiketini_guncelle(self):
        yol = self.ana_klasor.get()
        if not os.path.isdir(yol):
            self.son_tarama_label.configure(text="Son tarama: —")
            return
        bilgi = son_tarama_bilgisi_oku(yol)
        if not bilgi:
            self.son_tarama_label.configure(text="Son tarama: henüz yapılmadı")
        else:
            self.son_tarama_label.configure(
                text=f"Son tarama: {bilgi['tarih_saat']}  •  {bilgi['dosya_sayisi']} dosya"
            )

    def _set_tarama_butonlari(self, enabled):
        durum = "normal" if enabled else "disabled"
        for btn in (self.btn_tara, self.btn_zorla, self.btn_tumunu, self.btn_yenile):
            btn.configure(state=durum)

    def _arka_planda_calistir(self, is_yap, bitince):
        def calistir():
            try:
                sonuc = is_yap()
                self.after(0, lambda: bitince(sonuc, None))
            except Exception as e:
                self.after(0, lambda: bitince(None, e))
        threading.Thread(target=calistir, daemon=True).start()

    def _ilerleme_goster(self):
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.progress_label.grid(row=1, column=0, sticky="w")
        self.progress_label.configure(text="0 / 0  (%0)")

    def _ilerleme_gizle(self):
        self.progress_bar.grid_forget()
        self.progress_label.grid_forget()

    def _ilerleme_guncelle(self, n, toplam):
        def _uygula():
            oran = 0 if toplam <= 0 else n / toplam
            self.progress_bar.set(oran)
            yuzde = int(oran * 100)
            self.progress_label.configure(text=f"{n} / {toplam}  (%{yuzde})")
        self.after(0, _uygula)

    def tara(self):
        yol = self.ana_klasor.get()
        if not os.path.isdir(yol):
            messagebox.showwarning("Klasör seç", "Önce taranacak ana klasörü seç.")
            return
        self.status.configure(text="● Tarama başladı...")
        self._set_tarama_butonlari(False)
        self._ilerleme_goster()

        def is_yap():
            return klasor_tara(
                yol,
                log_callback=lambda msg: self.after(0, self._durum_guncelle, msg),
                progress_callback=self._ilerleme_guncelle,
            )

        def bitince(df, hata):
            self._set_tarama_butonlari(True)
            self._ilerleme_gizle()
            if hata is not None:
                messagebox.showerror("Hata", str(hata))
                self.status.configure(text="● Hata oluştu")
                return
            self.status.configure(text=f"● Tarama tamamlandı. İşlenen kayıt: {len(df)}")
            self.ozet_yenile()
            self._son_tarama_etiketini_guncelle()
            self.tablo_doldur(df.tail(300))

        self._arka_planda_calistir(is_yap, bitince)

    def ara(self):
        yol = self.ana_klasor.get()
        if not os.path.isdir(yol):
            messagebox.showwarning("Klasör seç", "Önce ana klasörü seç.")
            return
        q = self.search_entry.get().strip()
        if len(q) < 3:
            messagebox.showinfo("Arama", "Lütfen en az 3 harf girin.")
            return
        df = arama_yap(yol, q)
        self.result_title.configure(text=f"Arama Sonuçları ({q}) - {len(df)} kayıt")
        self.tablo_doldur(df)

    def tablo_doldur(self, df):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._tam_yol_haritasi.clear()

        if df is None or df.empty:
            return

        gosterim_kolonlari = list(self.tree["columns"])

        for _, row in df.iterrows():
            tam_yol = row.get("Tam Yol", "") or os.path.join(
                str(row.get("Yeni Klasör", "")), str(row.get("Yeni Dosya Adı", ""))
            )
            son_islem_tarihi = row.get("İşlem Tarihi", "")

            deger_haritasi = {
                "Yeni Dosya Adı": row.get("Yeni Dosya Adı", ""),
                "Belge Türü": row.get("Belge Türü", ""),
                "Plaka": row.get("Plaka", ""),
                "Tank No": row.get("Tank No", ""),
                "Şasi No": row.get("Şasi No", ""),
                "Yabancı Plaka": row.get("Yabancı Plaka", ""),
                "Geçerlilik Tarihi": row.get("Geçerlilik Tarihi", ""),
                "Dosya Konumu": row.get("Yeni Klasör", ""),
                "Son İşlem Tarihi": son_islem_tarihi,
                "İşlem Durumu": row.get("İşlem Durumu", ""),
            }
            values = [str(deger_haritasi.get(col, "")) for col in gosterim_kolonlari]
            item_id = self.tree.insert("", "end", values=values)
            self._tam_yol_haritasi[item_id] = str(tam_yol)

    def _tabloda_cift_tik(self, event):
        secili = self.tree.selection()
        if not secili:
            return
        item_id = secili[0]
        tam_yol = self._tam_yol_haritasi.get(item_id, "")
        if tam_yol and os.path.isfile(tam_yol):
            dosyayi_ac(tam_yol)
        else:
            messagebox.showwarning("Bulunamadı", "Dosya konumu bulunamadı veya dosya taşınmış olabilir.")

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
        self.status.configure(text="● Okunamayan PDF'ler tekrar deneniyor...")
        self._set_tarama_butonlari(False)
        self._ilerleme_goster()

        def is_yap():
            return zorla_yeniden_oku(
                yol,
                log_callback=lambda msg: self.after(0, self._durum_guncelle, msg),
                progress_callback=self._ilerleme_guncelle,
            )

        def bitince(df, hata):
            self._set_tarama_butonlari(True)
            self._ilerleme_gizle()
            if hata is not None:
                messagebox.showerror("Hata", str(hata))
                self.status.configure(text="● Hata oluştu")
                return
            self.status.configure(text=f"● İşlem tamamlandı. İşlenen: {len(df)} dosya")
            self.ozet_yenile()
            if df is not None and not df.empty:
                self.tablo_doldur(df)

        self._arka_planda_calistir(is_yap, bitince)

    def tumunu_yeniden_tara(self):
        yol = self.ana_klasor.get()
        if not os.path.isdir(yol):
            messagebox.showwarning("Klasör seç", "Önce ana klasörü seç.")
            return
        onay = messagebox.askyesno(
            "Tümünü Yeniden Tara",
            "Bu işlem TÜM PDF dosyalarını (P veya E kodlu olsa da) içerikten "
            "yeniden okuyup yeniden sınıflandırır ve eski T9 alt klasörlerini "
            "tek 'T9' klasöründe birleştirir.\n\n"
            "FARKLI FORMAT DOSYALAR klasörüne dokunulmaz.\n\n"
            "Bu, normal taramadan ÇOK DAHA UZUN sürebilir. Devam edilsin mi?"
        )
        if not onay:
            return
        self.status.configure(text="● Tümünü yeniden tarama başladı... (bu uzun sürebilir)")
        self._set_tarama_butonlari(False)
        self._ilerleme_goster()

        def is_yap():
            return tum_dosyalari_yeniden_tara(
                yol,
                log_callback=lambda msg: self.after(0, self._durum_guncelle, msg),
                progress_callback=self._ilerleme_guncelle,
            )

        def bitince(df, hata):
            self._set_tarama_butonlari(True)
            self._ilerleme_gizle()
            if hata is not None:
                messagebox.showerror("Hata", str(hata))
                self.status.configure(text="● Hata oluştu")
                return
            self.status.configure(text=f"● Tümünü yeniden tarama tamamlandı. İşlenen: {len(df)} dosya")
            self.ozet_yenile()
            self._son_tarama_etiketini_guncelle()
            if df is not None and not df.empty:
                self.tablo_doldur(df.tail(300))

        self._arka_planda_calistir(is_yap, bitince)

    def rapor_bilgi(self):
        messagebox.showinfo(
            "Raporlar",
            "Raporlar seçili klasör / ISLEM RAPORLARI klasöründe oluşur.\n\n"
            "Her rapor dosyasının adında o taramanın yapıldığı gün ve saat "
            "yer alır (örn. ISLEM RAPORU 16-06-2026 09-04-12.xlsx)."
        )

    # ------------------------------------------------------------------
    # MANUEL DUZELTME MODULU
    # ------------------------------------------------------------------
    def manuel_duzeltme_ac(self):
        """main_paned.py'deki Manuel Düzeltme aracını yeni bir pencere
        olarak açar. Ana klasör seçiliyse otomatik olarak o klasörü
        Manuel Düzeltme aracına da iletir."""
        try:
            import importlib.util
            import sys

            # main_paned.py'nin yolunu bul (ana programla aynı klasörde)
            paned_yolu = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "main_paned.py"
            )
            if not os.path.exists(paned_yolu):
                messagebox.showerror(
                    "Modül Bulunamadı",
                    "main_paned.py dosyası bulunamadı.\n"
                    "Lütfen main_paned.py'nin main.py ile aynı klasörde "
                    "olduğundan emin olun."
                )
                return

            # main_paned modülünü dinamik olarak yükle
            spec = importlib.util.spec_from_file_location(
                "main_paned", paned_yolu)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Yeni Toplevel pencere oluştur
            pencere = Toplevel(self)
            pencere.title("PRGTOK Manuel Düzeltme")
            pencere.geometry("1500x850")
            pencere.minsize(1250, 720)

            # Uygulamayı bu pencereye başlat
            uygulama = mod.ManualCorrectionApp(pencere)

            # Ana klasör seçiliyse otomatik ilet
            ana_klasor = self.ana_klasor.get()
            if ana_klasor and os.path.isdir(ana_klasor):
                pencere.after(200, lambda: uygulama.set_root_folder(
                    __import__("pathlib").Path(ana_klasor)
                ))

        except ImportError as e:
            messagebox.showerror(
                "Eksik Paket",
                f"Manuel Düzeltme modülü açılırken bir paket bulunamadı:\n{e}\n\n"
                "Gerekli paketleri kurmak için:\n"
                "py -m pip install pymupdf pillow"
            )
        except Exception as e:
            messagebox.showerror(
                "Hata",
                f"Manuel Düzeltme penceresi açılamadı:\n{e}"
            )

    # ------------------------------------------------------------------
    # ANAHTAR KELIME YONETIMI
    # ------------------------------------------------------------------
    def anahtar_kelimeler_penceresi_ac(self):
        yol = self.ana_klasor.get()
        if not os.path.isdir(yol):
            messagebox.showwarning("Klasör seç", "Önce ana klasörü seç. Anahtar kelimeler seçili klasöre özeldir.")
            return

        pencere = Toplevel(self)
        pencere.title("Anahtar Kelimeler")
        pencere.geometry("760x620")
        pencere.configure(bg=RENK_ANA_ARKA)
        pencere.transient(self)

        ctk.CTkLabel(
            pencere, text="Anahtar Kelimeler", font=("Arial", 18, "bold")
        ).pack(padx=16, pady=(16, 4), anchor="w")
        ctk.CTkLabel(
            pencere,
            text=(
                "Bir kategoriye kelime eklerseniz, o kategori için programın "
                "kendi otomatik kuralları artık kullanılmaz; sadece buraya "
                "eklediğiniz kelimeler aranır. Bu klasöre özeldir ve klasör "
                "değiştirirseniz farklı kelimeler kullanabilirsiniz."
            ),
            font=("Arial", 11), text_color="#7FA8C9", wraplength=700, justify="left"
        ).pack(padx=16, pady=(0, 12), anchor="w")

        scroll = ctk.CTkScrollableFrame(pencere, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        scroll.grid_columnconfigure(0, weight=1)

        self._ak_pencere = pencere
        self._ak_scroll = scroll
        self._ak_klasor = yol
        self._anahtar_kelimeler_listesini_ciz()

        ctk.CTkButton(
            pencere, text="Kapat", command=pencere.destroy, fg_color="#5A1E1E", hover_color="#7A2A2A"
        ).pack(padx=16, pady=(0, 16), anchor="e")

    def _anahtar_kelimeler_listesini_ciz(self):
        """Anahtar kelime penceresinin icerigini (her kategori + kelimeleri)
        sifirdan yeniden cizer. Ekleme/silme sonrasi tekrar cagrilir."""
        for w in self._ak_scroll.winfo_children():
            w.destroy()

        kayitli = anahtar_kelimeleri_oku(self._ak_klasor)

        for i, kategori in enumerate(BELGE_KLASORLERI.keys()):
            kutu = ctk.CTkFrame(self._ak_scroll, fg_color=RENK_KART, corner_radius=10)
            kutu.grid(row=i, column=0, padx=4, pady=6, sticky="ew")
            kutu.grid_columnconfigure(0, weight=1)

            override_mi = kategori in kayitli and len(kayitli[kategori]) > 0
            baslik_renk = "#FFC857" if override_mi else "#DCEBFF"
            baslik_metin = kategori + ("  •  özel kelimelerle çalışıyor" if override_mi else "  •  otomatik kurallarla çalışıyor")
            ctk.CTkLabel(kutu, text=baslik_metin, font=("Arial", 13, "bold"), text_color=baslik_renk).grid(
                row=0, column=0, columnspan=3, padx=12, pady=(10, 4), sticky="w"
            )

            kelimeler = kayitli.get(kategori, [])
            if kelimeler:
                for j, kelime in enumerate(kelimeler):
                    ctk.CTkLabel(kutu, text=f"• {kelime}", font=("Arial", 12)).grid(
                        row=1 + j, column=0, padx=(20, 6), pady=2, sticky="w"
                    )
                    ctk.CTkButton(
                        kutu, text="Sil", width=56, height=24, fg_color="#5A1E1E", hover_color="#7A2A2A",
                        command=lambda kat=kategori, kel=kelime: self._anahtar_kelime_sil_ve_yenile(kat, kel)
                    ).grid(row=1 + j, column=1, padx=(0, 12), pady=2, sticky="e")
                son_satir = 1 + len(kelimeler)
            else:
                ctk.CTkLabel(kutu, text="(henüz özel kelime eklenmedi)", font=("Arial", 11), text_color="#7FA8C9").grid(
                    row=1, column=0, padx=20, pady=2, sticky="w"
                )
                son_satir = 2

            giris = ctk.CTkEntry(kutu, placeholder_text="Yeni anahtar kelime yazın...")
            giris.grid(row=son_satir, column=0, padx=(20, 6), pady=(6, 10), sticky="ew")
            giris.bind("<Return>", lambda e, kat=kategori, ent=giris: self._anahtar_kelime_ekle_ve_yenile(kat, ent))
            ctk.CTkButton(
                kutu, text="Ekle", width=56, height=28,
                command=lambda kat=kategori, ent=giris: self._anahtar_kelime_ekle_ve_yenile(kat, ent)
            ).grid(row=son_satir, column=1, padx=(0, 12), pady=(6, 10), sticky="e")

    def _anahtar_kelime_ekle_ve_yenile(self, kategori, giris_widget):
        kelime = giris_widget.get().strip()
        if not kelime:
            return
        anahtar_kelime_ekle(self._ak_klasor, kategori, kelime)
        self._anahtar_kelimeler_listesini_ciz()

    def _anahtar_kelime_sil_ve_yenile(self, kategori, kelime):
        anahtar_kelime_sil(self._ak_klasor, kategori, kelime)
        self._anahtar_kelimeler_listesini_ciz()


if __name__ == "__main__":
    app = PRGTOKApp()
    app.mainloop()
