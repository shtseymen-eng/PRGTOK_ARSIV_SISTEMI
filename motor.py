# ============================================================================
# PRGTOK ARSIV SISTEMI - motor.py
# PDF, Word, Excel ve resim arsivleme motoru.

import json
import os
import re
import shutil
import threading
import subprocess
import sys
from io import BytesIO
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import fitz
from PIL import Image, ImageOps, ImageSequence
from docx import Document

SURUM = "2.7.0"
ESKI_DOSYALAR = "ESKI DOSYALAR"
TARIHI_GECMIS = "TARIHI GECMIS"


def _tesseract_yolu():
    paket = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    adaylar = [paket / "tesseract" / "tesseract.exe"]
    if os.name == "nt":
        adaylar.append(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe")
    return next((str(yol) for yol in adaylar if yol.is_file()), None) or shutil.which("tesseract")


# ----------------------------------------------------------------------------
# ISLEM KODLARI
# ----------------------------------------------------------------------------
ISLEM_KODU = "P"          # Program tarafindan otomatik tarandi
ELLE_DUZELT_KODU = "E"    # Elle duzeltildi - icerik tekrar okunmaz

# Eski surumden gelen kodlar icin geriye-donuk uyumluluk (otomatik cevrilir)
ESKI_ISLEM_KODLARI = {"S", "PRGTOK"}
ESKI_ELLE_DUZELT_KODLARI = {"PRGT"}

BILINEN_KODLAR = {ISLEM_KODU, ELLE_DUZELT_KODU} | ESKI_ISLEM_KODLARI | ESKI_ELLE_DUZELT_KODLARI

# ----------------------------------------------------------------------------
# BELGE KATEGORILERI (sadelestirilmis - T9 alt turleri birlesti)
# ----------------------------------------------------------------------------
BELGE_KLASORLERI = {
    "TANK BASINC RAPORU": "TANK BASINC RAPORU",
    "ISOPA": "ISOPA",
    "T9": "T9",
    "RUHSAT": "RUHSAT",
    "TASIT KARTI": "TASIT KARTI",
    "TASIT UYGUNLUK MUAYENE SERTIFIKASI": "TASIT UYGUNLUK MUAYENE SERTIFIKASI",
    "TASIT UYGUNLUK GECICI BELGE": "TASIT UYGUNLUK GECICI BELGE",
    "TRAFIK SIGORTASI": "TRAFIK SIGORTASI",
    "TEHLIKELI MADDE SIGORTASI": "TEHLIKELI MADDE SIGORTASI",
    "FENNI MUAYENE": "FENNI MUAYENE",
    "SIZDIRMAZLIK": "SIZDIRMAZLIK",
    "YUKSEKTE CALISABILIR SAGLIK RAPORU": "YUKSEKTE CALISABILIR SAGLIK RAPORU",
    "SRC5": "SRC5",
    "YABANCI PLAKA": "YABANCI PLAKA",
    "DIGER BELGELER": "DIGER BELGELER",
}

# Dosya adinda kullanilan kisa tur etiketleri
TUR_DISPLAY = {
    "TANK BASINC RAPORU": "TANK BASINC",
    "ISOPA": "ISOPA",
    "T9": "T9",
    "RUHSAT": "RUHSAT",
    "TASIT KARTI": "TASIT KARTI",
    "TASIT UYGUNLUK MUAYENE SERTIFIKASI": "TASIT UYGUNLUK MUAYENE SERTIFIKASI",
    "TASIT UYGUNLUK GECICI BELGE": "TASIT UYGUNLUK GECICI BELGE",
    "TRAFIK SIGORTASI": "TRAFIK SIGORTASI",
    "TEHLIKELI MADDE SIGORTASI": "TEHLIKELI MADDE SIGORTASI",
    "FENNI MUAYENE": "FENNI MUAYENE",
    "SIZDIRMAZLIK": "SIZDIRMAZLIK",
    "YUKSEKTE CALISABILIR SAGLIK RAPORU": "YC SAGLIK",
    "SRC5": "SRC5",
    "YABANCI PLAKA": "YABANCI PLAKA",
    "DIGER BELGELER": "DIGER",
}

# Eski T9 alt-tur adlarini yeni birlesik "T9" turune yonlendirmek icin
ESKI_T9_TURLERI = {"T9 GECICI", "T9 MUAYENE", "T9 ANA", "T9 MUAYENE SERTIFIKASI"}


# ----------------------------------------------------------------------------
# KULLANICI TARAFINDAN ELLE OLUSTURULMUS, PROGRAMIN HIC DOKUNMAMASI GEREKEN
# KLASORLER
#
# Kullanici, arsivleme mantigi programdan tamamen farkli olan kendi klasorlerini
# (ör. "Kontrol Formu", "Kontrol Formlari") ana klasorun altina acabilir. Bu
# klasorler asagidaki VARSAYILAN listeye + kullanicinin sonradan program
# icinden ekledigi ozel isimlere eklenir; tarama (klasor_tara /
# tum_dosyalari_yeniden_tara) bu klasorlerin ICINE HIC GIRMEZ: ne icindeki
# dosyalari baska yere tasir, ne de disaridan bu klasore dosya sokar.
# Karsilastirma buyuk/kucuk harf ve Turkce karakter farkina duyarsizdir
# (kullanici "Kontrol Formu", "KONTROL FORMU" ya da "kontrol formu" yazsa da
# ayni klasor olarak taninir).
#
# Kullanicinin kendi ekledigi ek isimler, her ana klasore ozel olarak
# "ISLEM RAPORLARI/KORUMALI KLASORLER.json" dosyasinda saklanir (bkz.
# korumali_klasorleri_oku / korumali_klasor_ekle / korumali_klasor_sil).
# Boylece yeni bir "dokunulmasin" klasoru icin kod degisikligi gerekmez;
# programdaki "Korumali Klasorler" ekranindan eklenip cikarilabilir.
# ----------------------------------------------------------------------------
VARSAYILAN_KULLANICI_KORUMALI_KLASORLER = {"KONTROL FORMU", "KONTROL FORMLARI", "FAALIYET BELGESI", "FAALIYET BELGELERI"}

# Geriye donuk uyumluluk: eski kod bu isimle referans veriyor olabilir.
KULLANICI_KORUMALI_KLASORLER = VARSAYILAN_KULLANICI_KORUMALI_KLASORLER


def _klasor_adi_normalize(text):
    """Klasor adlarini buyuk/kucuk harf ve Turkce karakter farkina duyarsiz
    sekilde karsilastirmak icin kullanilir (sadece karsilastirma amacli;
    diskteki gercek klasor adi degistirilmez)."""
    tr_map = str.maketrans("ığüşöçİĞÜŞÖÇ", "igusocIGUSOC")
    return str(text).translate(tr_map).upper().strip()


KORUMALI_KLASOR_DOSYA_ADI = "KORUMALI KLASORLER.json"


def _korumali_klasor_dosya_yolu(ana_klasor):
    return Path(ana_klasor) / "ISLEM RAPORLARI" / KORUMALI_KLASOR_DOSYA_ADI


def korumali_klasorleri_oku(ana_klasor):
    """Bu ana klasore ozel olarak kullanicinin programdan ekledigi, dokunulmasi
    yasak klasor isimlerini okur. Donus degeri: (normalize_edilmis_kume, ham_liste)
       - normalize_edilmis_kume: VARSAYILAN_KULLANICI_KORUMALI_KLASORLER + ozel
         isimlerin hepsinin normalize edilmis hali (tarama fonksiyonlarinda
         dogrudan karsilastirma icin kullanilir).
       - ham_liste: sadece kullanicinin kendi ekledigi isimler, oldugu gibi
         (arayuzde listelemek / silmek icin kullanilir). Dosya yoksa veya
         bozuksa bos liste doner, hata vermez."""
    ozel = []
    yol = _korumali_klasor_dosya_yolu(ana_klasor)
    if yol.exists():
        try:
            with open(yol, "r", encoding="utf-8") as f:
                veri = json.load(f)
            if isinstance(veri, list):
                ozel = [str(x).strip() for x in veri if str(x).strip()]
        except Exception:
            ozel = []
    tumu = set(VARSAYILAN_KULLANICI_KORUMALI_KLASORLER) | set(ozel)
    normalize_kume = {_klasor_adi_normalize(x) for x in tumu}
    return normalize_kume, ozel


def korumali_klasor_ekle(ana_klasor, isim):
    """Kullanicinin programdan verdigi yeni bir korumali klasor adini,
    o ana klasore ozel JSON dosyasina ekler (kalici)."""
    isim = str(isim).strip()
    if not isim:
        return
    _, ozel = korumali_klasorleri_oku(ana_klasor)
    if _klasor_adi_normalize(isim) not in {_klasor_adi_normalize(x) for x in ozel}:
        ozel.append(isim)
    yol = _korumali_klasor_dosya_yolu(ana_klasor)
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(ozel, f, ensure_ascii=False, indent=2)


def korumali_klasor_sil(ana_klasor, isim):
    """Kullanicinin kendi eklemis oldugu bir korumali klasor adini siler.
    Varsayilan (VARSAYILAN_KULLANICI_KORUMALI_KLASORLER) isimler bu fonksiyonla
    silinemez; onlar her zaman korumali kalir."""
    _, ozel = korumali_klasorleri_oku(ana_klasor)
    hedef = _klasor_adi_normalize(isim)
    ozel = [x for x in ozel if _klasor_adi_normalize(x) != hedef]
    yol = _korumali_klasor_dosya_yolu(ana_klasor)
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(ozel, f, ensure_ascii=False, indent=2)

# Dosya adindan tur tespiti icin ters-arama tablosu (kisa etiket -> tur)
TUR_DISPLAY_REVERSE = {v: k for k, v in TUR_DISPLAY.items()}

PDF_EXT = {".pdf"}
RESIM_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
EXCEL_EXT = {".xls", ".xlsx", ".xlsm"}
OKUNABILIR_EXT = PDF_EXT | RESIM_EXT | EXCEL_EXT | {".docx"}

# ----------------------------------------------------------------------------
# REGEX KALIPLARI
# ----------------------------------------------------------------------------
TURK_PLAKA_RE = re.compile(r"\b(0[1-9]|[1-7][0-9]|8[01])\s*[A-ZÇĞİÖŞÜ]{1,3}\s*\d{2,4}\b", re.I)
TANK_NO_RE = re.compile(r"\b[A-Z]{4}\s?\d{6}\s?-?\s?\d\b", re.I)
SASI_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
DATE_RE_LIST = [
    re.compile(r"\b(\d{2})[./-](\d{2})[./-](\d{4})\b"),
    re.compile(r"\b(\d{4})[./-](\d{2})[./-](\d{2})\b"),
]
EN_DATE_RE = re.compile(r"\b(\d{1,2})[-\s](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s](\d{2,4})\b", re.I)
CAPACITY_RE = re.compile(r"\b(\d{2,3}[\.,]?\d{3}|\d{4,6})\s*(?:LT|LITRE|LITER|L)\b", re.I)
YABANCI_PLAKA_ADAY_RE = re.compile(
    r"\b[A-Z]{1,3}\s?\d{2,5}\s?[A-Z]{1,3}\b|\b[A-Z]{2}\s?\d{3,6}\b|\b\d{3,6}\s?[A-Z]{2,4}\b", re.I
)


# ----------------------------------------------------------------------------
# YARDIMCI METIN FONKSIYONLARI
# ----------------------------------------------------------------------------
def temizle_ad(text, max_len=80):
    if not text:
        return "BILGIYOK"
    tr_map = str.maketrans("ÇĞİÖŞÜçğıöşü", "CGIOSUcgiosu")
    text = str(text).replace("\u00a0", " ").translate(tr_map).upper().strip()
    text = re.sub(r"[^A-Z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_len] if text else "BILGIYOK"


def anlamli_kimlik_mi(text):
    if not text:
        return False
    t = temizle_ad(text, 80)
    kotu = {"ON", "DELIVERED", "DELIVERED_ON", "CERTIFICATE", "DRIVER", "ISOPA", "BILGIYOK"}
    return t not in kotu and len(t) >= 5


def tarih_formatla(tarih):
    if not tarih:
        return ""
    for ix, rgx in enumerate(DATE_RE_LIST):
        m = rgx.search(tarih)
        if m:
            if ix == 0:
                gun, ay, yil = m.groups()
            else:
                yil, ay, gun = m.groups()
            return f"{gun}.{ay}.{yil}"
    return ""


def en_date_formatla(tarih):
    aylar = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
        "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    }
    m = EN_DATE_RE.search(tarih or "")
    if not m:
        return ""
    gun, ay, yil = m.groups()
    if len(yil) == 2:
        yil = "20" + yil
    return f"{gun.zfill(2)}.{aylar.get(ay.upper(), '00')}.{yil}"


def dnv_next_due_bul(metin):
    _AY_MAP = {
        "JANUARY":"01","FEBRUARY":"02","MARCH":"03","APRIL":"04",
        "MAY":"05","JUNE":"06","JULY":"07","AUGUST":"08",
        "SEPTEMBER":"09","OCTOBER":"10","NOVEMBER":"11","DECEMBER":"12",
        "JAN":"01","FEB":"02","MAR":"03","APR":"04","JUN":"06",
        "JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12",
    }
    buyuk = metin.upper()
    for pattern in [
        r"DATE\s+NEXT\s+INSPECTION\s+DUE\s*[:\-]?\s*(0?[1-9]|1[0-2])[/.-](\d{2})",
        r"NEXT\s+INSPECTION\s+DUE\s*[:\-]?\s*(0?[1-9]|1[0-2])[/.-](\d{2})",
    ]:
        m = re.search(pattern, buyuk)
        if m:
            ay, yil = m.groups()
            return f"{ay.zfill(2)}.20{yil}"
    # Lloyd's Register: "Next Inspection date May 2026"
    m = re.search(
        r"NEXT\s+INSPECTION\s+DATE\s+([A-Z]+)\s+(20\d{2})", buyuk)
    if m:
        ay_ad, yil = m.groups()
        ay = _AY_MAP.get(ay_ad)
        if ay:
            return f"{ay}.{yil}"
    # BV: "Date Prochain controle 07-2026"
    m = re.search(
        r"(?:DATE\s+PROCHAIN\s+CONTR[OÔ]LE|NEXT\s+INSPECTION\s+DATE)\s*(\d{2})[/-](20\d{2})",
        buyuk)
    if m:
        ay, yil = m.groups()
        return f"{ay}.{yil}"
    return ""


def tse_next_inspection_bul(metin):
    m = re.search(r"SONRAKI\s+MUAYENE.*?(\d{2})[/.-](20\d{2})", metin.upper(), re.S)
    if not m:
        m = re.search(r"NEXT\s+INSPECTION.*?(\d{2})[/.-](20\d{2})", metin.upper(), re.S)
    if m:
        ay, yil = m.groups()
        return f"{ay}.{yil}"
    return ""


def tum_tarihleri_bul(metin):
    bulunan = []
    for rgx in DATE_RE_LIST:
        for m in rgx.finditer(metin):
            bulunan.append(tarih_formatla(m.group(0)))
    for m in EN_DATE_RE.finditer(metin):
        bulunan.append(en_date_formatla(m.group(0)))
    return [x for x in bulunan if x]


def en_mantikli_tarih(metin, tur=""):
    if tur == "TANK BASINC RAPORU":
        x = dnv_next_due_bul(metin)
        if x:
            return x
    if tur == "T9":
        x = tse_next_inspection_bul(metin)
        if x:
            return x
    patterns = [
        r"SON\s+GEÇERLİLİK\s+TARİHİ\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"SON\s+GECERLILIK\s+TARIHI\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"VALID\s+UNTIL\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"BİTİŞ\s+TARİHİ\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"BITIS\s+TARIHI\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"EXPIRATION\s+DATE\s*[:\-]?\s*(\d{4}[./-]\d{2}[./-]\d{2})",
        r"MUAYENE\s+GEÇERLİLİK\s+TARİHİ\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"MUAYENE\s+GECERLILIK\s+TARIHI\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"BİR\s+SONRAKİ\s+KONTROL\s+TARİHİ\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
        r"BIR\s+SONRAKI\s+KONTROL\s+TARIHI\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})",
    ]
    for p in patterns:
        m = re.search(p, metin.upper(), re.S)
        if m:
            return tarih_formatla(m.group(1))
    return ""


def _resim_metni(resim, psm=3):
    exe = _tesseract_yolu()
    if not exe:
        raise RuntimeError("Tesseract OCR bulunamadı.")
    with BytesIO() as veri:
        resim.save(veri, format="PNG")
        png = veri.getvalue()

    ortam = dict(os.environ, OMP_THREAD_LIMIT="1")
    veri_klasoru = Path(exe).parent / "tessdata"
    if veri_klasoru.is_dir():
        ortam["TESSDATA_PREFIX"] = str(veri_klasoru)
    bayrak = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    for diller in ("tur+eng", "eng"):
        sonuc = subprocess.run(
            [exe, "stdin", "stdout", "-l", diller, "--psm", str(psm)],
            input=png, capture_output=True, timeout=45, creationflags=bayrak, env=ortam,
        )
        if sonuc.returncode == 0:
            metin = sonuc.stdout.decode("utf-8", errors="replace")
            if metin.strip() or diller == "eng":
                return metin
    raise RuntimeError(sonuc.stderr.decode("utf-8", errors="replace").strip())


def _kirmizi_serit(resim):
    """Sayfanin ortasindan gecen belirgin kirmizi seridi arar."""
    ornek = resim.convert("RGB").resize((96, 96))
    def kirmizi(x, y):
        r, g, b = ornek.getpixel((x, y))
        return r >= 115 and r > 1.35 * max(g, b)

    for adim in range(-12, 13):
        egim = adim / 12
        for orta in range(37, 60):
            uzunluk = sum(
                kirmizi(x, int(orta + egim * (x - 48)))
                for x in range(16, 80)
            )
            if uzunluk >= 44:
                return True
    return False


def _belge_oku(kaynak, ikinci=False):
    uzanti = kaynak.suffix.lower()
    parcalar = []
    serit = False
    if uzanti in PDF_EXT:
        ocr_hatasi = None
        with fitz.open(kaynak) as pdf:
            for sayfa in pdf:
                metin = sayfa.get_text(sort=True).strip()
                parcalar.append(metin)
                uygunluk = "UYGUNLUK BELGE" in _klasor_adi_normalize(" ".join(metin.split()))
                gorsel = bool(sayfa.get_image_info())
                if not (ikinci or not metin or gorsel or uygunluk):
                    continue
                pix = sayfa.get_pixmap(dpi=300 if ikinci else 180, colorspace=fitz.csRGB)
                with Image.frombytes("RGB", (pix.width, pix.height), pix.samples) as resim:
                    serit = serit or _kirmizi_serit(resim)
                    if not (ikinci or not metin or gorsel):
                        continue
                    try:
                        if ikinci:
                            with ImageOps.autocontrast(resim.convert("L")) as duz:
                                parcalar.append(_resim_metni(duz, psm=11))
                        else:
                            parcalar.append(_resim_metni(resim))
                    except (RuntimeError, OSError, subprocess.TimeoutExpired) as hata:
                        ocr_hatasi = hata
        if ocr_hatasi is not None and not any(parca.strip() for parca in parcalar):
            raise ocr_hatasi
    elif uzanti in RESIM_EXT:
        with Image.open(kaynak) as resim:
            for kare in ImageSequence.Iterator(resim):
                with ImageOps.exif_transpose(kare) as duz:
                    serit = serit or _kirmizi_serit(duz)
                    parcalar.append(_resim_metni(duz))
    elif uzanti == ".docx":
        belge = Document(kaynak)
        parcalar.extend(p.text for p in belge.paragraphs)
        for tablo in belge.tables:
            for satir in tablo.rows:
                parcalar.append(" ".join(hucre.text for hucre in satir.cells))
    elif uzanti in EXCEL_EXT:
        with pd.ExcelFile(kaynak) as kitap:
            for sayfa in kitap.sheet_names:
                tablo = kitap.parse(sayfa, header=None, dtype=str).fillna("")
                parcalar.extend(" ".join(satir) for satir in tablo.itertuples(index=False, name=None))
    return "\n".join(parcalar).strip(), serit


def plaka_bul(metin):
    plakalar = {temizle_ad(m.group().replace(" ", "")) for m in TURK_PLAKA_RE.finditer(metin.upper())}
    return next(iter(plakalar)) if len(plakalar) == 1 else ""


def tank_no_bul(metin):
    """Tank/konteyner numarasini bulur. Once guvenilir bir etiketin
    (Owner No / Marquage / Immatriculation / Owner's Serial number)
    yanindaki numarayi arar; bulamazsa genel aramaya doner. 'Old number'
    (eski/iptal numara) ifadesinin yanindaki numara HER ZAMAN atlanir,
    cunku bu artik gecerli olmayan bir numaradir."""
    buyuk = metin.upper()

    # "OLD NUMBER: XXXX-X" gibi ifadeleri once metinden cikar, boylece
    # ne etiketli arama ne de genel arama bu eski/iptal numarayi yakalamasin.
    buyuk_temiz = re.sub(r"OLD\s+NUMBER\s*[:\-]?\s*[A-Z]{2,4}\s?\d{4,6}\s?-?\s?\d?", " ", buyuk)

    # Guvenilir etiketlerin yanindaki numarayi tercih et.
    for etiket_pattern in (
        r"OWNER\s*N[O°]\.?\s*[:\-]?\s*",
        r"MARQUAGE\s*[/]?\s*MARKING\s*[:\-]?\s*",
        r"IMMATRICULATION\s*/?\s*UNIT\s*[:\-]?\s*",
        # Lloyd's Register: "Owner's Serial number" basliginin altindaki satir
        r"OWNER['\u2019]?S\s+SERIAL\s+NUMBER\s*\n\s*",
    ):
        etiket_m = re.search(etiket_pattern + r"([A-Z]{2,4}\s?\d{5,6}\s?-?\s?\d)", buyuk_temiz)
        if etiket_m:
            raw = etiket_m.group(1).replace(" ", "").upper()
            norm = re.sub(r"^([A-Z]{2,4})(\d{5,6})-?(\d)$", r"\1\2-\3", raw)
            return norm if norm else temizle_ad(raw)

    m = TANK_NO_RE.search(buyuk_temiz)
    if not m:
        return ""
    raw = m.group(0).replace(" ", "").upper()
    norm = re.sub(r"^([A-Z]{4})(\d{6})-?(\d)$", r"\1\2-\3", raw)
    return norm if norm else temizle_ad(raw)


def sasi_bul(metin):
    m = SASI_RE.search(metin.upper())
    return temizle_ad(m.group(0)) if m else ""


def kapasite_bul(metin):
    temiz = metin.upper().replace(".", "").replace(",", "")
    for pattern in [
        r"CAPACITY\s*\(L\)\s*[:\-]?\s*(\d{4,6})",
        r"KAPASITE\s*\(L\).*?TOPLAM\s*\(TOTAL\)\s*[:\-]?\s*(\d{4,6})",
        r"TOPLAM\s*\(TOTAL\)\s*[:\-]?\s*(\d{4,6})",
        r"TANK\s+HACMI\s*[:\-]?\s*(\d{4,6})\s*LT",
        # Lloyd's Register: "Capacity 25,940 litres" veya "26,000 Litres UN Portable Tank"
        r"CAPACITY\s+(\d{4,6})\s+LITRE",
        r"(\d{4,6})\s+LITRES?\s+UN\s+PORTABLE\s+TANK",
    ]:
        m = re.search(pattern, temiz, re.S)
        if m:
            return f"{m.group(1)}LT"
    m = CAPACITY_RE.search(temiz)
    if not m:
        return ""
    sayi = re.sub(r"\D", "", m.group(1))
    return f"{sayi}LT" if sayi else ""


def tank_kodu_bul(metin):
    for pattern in [
        r"TANK\s+KODU.*?(L[A-Z0-9]{3})",
        r"PORTABLE\s+TANK\s+INSTRUCTION.*?(L[A-Z0-9]{3})",
    ]:
        m = re.search(pattern, metin.upper(), re.S)
        if m:
            return temizle_ad(m.group(1))
    m = re.search(r"\bL[A-Z0-9]{3}\b", metin.upper())
    return temizle_ad(m.group(0)) if m else ""


def un_numaralari_bul(metin, max_adet=10):
    eslesler = re.findall(r"\bUN\s*N?O?\.?\s*(\d{4})\b", metin.upper())
    gorulen = set()
    benzersiz = []
    for un in eslesler:
        if un not in gorulen:
            gorulen.add(un)
            benzersiz.append(un)
        if len(benzersiz) >= max_adet:
            break
    return "-".join(benzersiz)


def yabanci_plaka_bul(metin):
    temiz = TURK_PLAKA_RE.sub(" ", metin.upper())
    # Turkce resmi belgelerde sik gecen "... tarih ve NNNNN sayili resmi
    # gazete/yonetmelik/teblig" gibi ifadeler "VE 28801" gibi sahte plaka
    # adaylarina yol aciyordu. Bu kaliplari plaka aramasindan once temizle.
    temiz = re.sub(r"\bVE\s+\d{3,6}\s+SAYILI\b", " ", temiz)
    temiz = re.sub(r"\bTARİH\s+VE\s+\d{3,6}\b", " ", temiz)
    temiz = re.sub(r"\bTARIH\s+VE\s+\d{3,6}\b", " ", temiz)
    yasak = ("POL", "TANK", "ADR", "PDF", "DNV", "CSC", "RID", "IMDG", "DATE", "TEST",
              "NEXT", "OWNER", "SHELL", "GROSS", "PRESSURE", "CAPACITY", "INSPECTION",
              "SERIAL", "TSE", "ISOPA", "DRIVER", "CERTIFICATE", "VE", "NO", "SAYILI",
              "GAZETE", "MADDE", "TARIH", "TARİH", "BOLUM", "BÖLÜM", "TEBLIG", "TEBLİĞ",
              "YONETMELIK", "YÖNETMELİK", "KANUN", "RESMI", "RESMİ")
    adaylar = []
    for m in YABANCI_PLAKA_ADAY_RE.finditer(temiz):
        aday = temizle_ad(m.group(0).replace(" ", ""))
        if 5 <= len(aday) <= 12 and not aday.startswith(yasak):
            adaylar.append(aday)
    return adaylar[0] if len(set(adaylar)) == 1 else ""


def surucu_adi_bul(metin, dosya_adi=""):
    metin_norm = (metin or "").replace("\u00a0", " ")
    buyuk = metin_norm.upper()

    m = re.search(
        r"ISOPA\s+DELIVERED\s+THIS\s+CERTIFICATE\s+TO\s+(.+?)(?:UNDER\s+THE\s+SUPERVISION|DELIVERED\s+ON|EXPIRATION\s+DATE|CERTIFICATE\s+UNIQUE\s+NUMBER|$)",
        buyuk, re.S
    )
    if m:
        isim = m.group(1)
        isim = re.sub(r"[^A-ZÇĞİÖŞÜ\s]", " ", isim)
        isim = re.sub(r"\s+", " ", isim).strip()
        if anlamli_kimlik_mi(isim):
            return temizle_ad(isim)

    m = re.search(r"(?:ADI\s*SOYADI|AD SOYAD|NAME\s*SURNAME)\s*[:\-]?\s*([A-ZÇĞİÖŞÜ ]{5,60})", buyuk)
    if m:
        isim = m.group(1).strip()
        if anlamli_kimlik_mi(isim):
            return temizle_ad(isim)

    stem = Path(dosya_adi).stem
    # Sondaki islem kodunu (P/E/eski S,PRGTOK,PRGT) kimlige dahil etmemek icin temizle
    son = _son_token(dosya_adi)
    if son in BILINEN_KODLAR:
        parcalar = stem.replace("-", " ").split(" ")
        stem = " ".join(parcalar[:-1])
    stem_clean = re.sub(r"[-_]", " ", stem).upper()
    if any(x in stem_clean for x in ["ISOPA", "YÇ", "YC", "YUKSEKTE"]):
        stem_clean = re.sub(r"\b(ISOPA|YÇ|YC|YUKSEKTE|CALISABILIR|ÇALISABILIR|ÇALIŞABİLİR|RAPORU)\b", " ", stem_clean)
        stem_clean = re.sub(r"\d{2,4}[./-]\d{1,2}[./-]\d{1,4}", " ", stem_clean)
        stem_clean = re.sub(r"\s+", " ", stem_clean).strip()
        if anlamli_kimlik_mi(stem_clean):
            return temizle_ad(stem_clean)

    return ""


def bilgi_dosya_adindan(dosya_adi):
    stem = Path(dosya_adi).stem
    # Sondaki islem kodunu (P/E/eski kodlar) analiz disinda tut
    son = _son_token(dosya_adi)
    if son in BILINEN_KODLAR:
        parcalar = stem.replace("-", " ").split(" ")
        stem = " ".join(parcalar[:-1])
    return {
        "plaka": plaka_bul(stem),
        "tank_no": tank_no_bul(stem),
        "sasi": sasi_bul(stem),
        "yabanci_plaka": yabanci_plaka_bul(stem),
        "tarih": en_mantikli_tarih(stem),
        "kapasite": kapasite_bul(stem),
        "tank_kodu": tank_kodu_bul(stem),
        "surucu": surucu_adi_bul("", dosya_adi),
    }


# ----------------------------------------------------------------------------
# BELGE TURU TESPITI (icerik bazli)
# ----------------------------------------------------------------------------
def belge_turu_bul(metin, dosya_adi="", ozel_kelimeler=None, kirmizi_serit=False):
    """Belge turunu tespit eder.

    ozel_kelimeler verilirse (klasore ozel ayar dosyasindan okunur):
      - Bir kategori icin kullanici en az 1 anahtar kelime tanimladiysa,
        o kategori icin asagidaki SABIT kurallar tamamen devre disi
        kalir; sadece kullanicinin yazdigi kelimeler kontrol edilir.
      - Kullanicinin kelime TANIMLAMADIGI kategoriler icin eski sabit
        kurallar oldugu gibi calismaya devam eder.
      - Birden fazla kullanici-tanimli kategori ayni metinde eslesirse,
        ozel_kelimeler sozlugundeki sira (yani kullanicinin ekleme
        sirasi) ile ilk eslesen kategori kullanilir.
    """
    m = (metin + "\n" + dosya_adi).upper()
    ad = dosya_adi.upper()
    ozel_kelimeler = ozel_kelimeler or {}

    def _override_edilmis(kategori):
        return bool(ozel_kelimeler.get(kategori))

    def _ozel_eslesiyor(kategori):
        for kelime in ozel_kelimeler.get(kategori, []):
            if kelime and kelime in m:
                return True
        return False

    # Once: kullanicinin OVERRIDE ETTIGI tum kategorileri kontrol et.
    # (Sozlukteki sira = kullanicinin ekleme sirasi; ilk eslesen kazanir.)
    for kategori in ozel_kelimeler.keys():
        if _override_edilmis(kategori) and _ozel_eslesiyor(kategori):
            return kategori

    if not _override_edilmis("YUKSEKTE CALISABILIR SAGLIK RAPORU") and (
        "YÇ" in ad or "YC" in ad or "YUKSEKTE" in m or "YÜKSEKTE" in m):
        return "YUKSEKTE CALISABILIR SAGLIK RAPORU"

    if not _override_edilmis("TEHLIKELI MADDE SIGORTASI") and (
        ("TEHLIKELI MADDE" in m or "TEHLİKELİ MADDE" in m or "TEHLIKELI ATIK" in m or "TEHLİKELİ ATIK" in m) and "ZORUNLU MALI SORUMLULUK" in m):
        return "TEHLIKELI MADDE SIGORTASI"

    baslik = _klasor_adi_normalize(" ".join(metin.split()))
    uygunluk = bool(re.search(r"\b(?:TASIT|ARAC|ADR)\s+UYGUNLUK\b", baslik))
    tur_kurallari = (
        ("TASIT UYGUNLUK GECICI BELGE", uygunluk and bool(re.search(
            r"\b(?:GECICI\s+(?:TASIT\s+UYGUNLUK\s+)?BELGE(?:SI)?|UYGUNLUK\s+GECICI)\b", baslik
        ))),
        ("TASIT UYGUNLUK MUAYENE SERTIFIKASI", uygunluk and "MUAYENE SERTIFIKASI" in baslik),
        ("TASIT KARTI", bool(re.search(r"\bTASIT KARTI\b", baslik))),
        ("RUHSAT", bool(re.search(
            r"\b(?:ARAC TESCIL BELGESI|MOTORLU ARAC TESCIL BELGESI|ARAC RUHSATI)\b", baslik
        ))),
        ("T9", (uygunluk and kirmizi_serit) or bool(re.search(
            r"BELIRLI TEHLIKELI MADDELER TASIYAN ARACLAR ICIN ONAY SERTIFIKASI"
            r"|CERTIFICATE OF APPROVAL FOR VEHICLES CARRYING CERTAIN DANGEROUS GOODS"
            r"|\bADR UYGUNLUK BELGESI\b|\bT9 (?:ONAY|UYGUNLUK)\b", baslik
        ))),
    )
    for tur, eslesme in tur_kurallari:
        if eslesme and not _override_edilmis(tur):
            return tur
    if uygunluk:
        return "DIGER BELGELER"

    if not _override_edilmis("SRC5") and (
        ("SRC-5" in m or "SRC 5" in m or "SRC5" in m or
        ("SRC" in m and ("TEHLIKELI MADDE TASIMACILIGI" in m or "TEHLİKELİ MADDE TAŞIMACILIĞI" in m or
                            "DANGEROUS GOODS DRIVER" in m or "ADR SURUCU" in m or "ADR SÜRÜCÜ" in m)))):
        return "SRC5"

    if not _override_edilmis("TANK BASINC RAPORU"):
        tank_ifadeleri = [
            "TANK CONTAINER PERIODIC INSPECTION REPORT", "PERIODIC INSPECTION REPORT",
            "DATE NEXT INSPECTION DUE", "NEXT INSPECTION DUE",
            "DNV SILVER", "SILVER/CIMS", "DNV GL",
            "OWNER'S SERIAL NUMBER", "OWNERS SERIAL NUMBER", "OWNER S SERIAL NUMBER",
            "OWNER'S SERIAL NO", "OWNERS SERIAL NO",
            "INITIAL HYDRO TEST", "LAST HYDRO TEST", "HYDROSTATIC TEST",
            "THIS INSPECTION", "INSPECTION DATES", "PERIODIC TEST",
            "NEXT PERIODIC TEST", "NEXT TEST DATE", "RETEST DATE",
            "MAX GROSS WEIGHT", "TARE WEIGHT",
            "CAPACITY (L)", "CAPACITY(L)",
            "TEST PRESSURE", "DESIGN PRESSURE", "WORKING PRESSURE",
            "M.A.W.P", "MAWP",
            "ISO TYPE", "PRESSURE RELIEF VALVES",
            "SHELL THICKNESS", "MINIMUM DESIGN METAL TEMPERATURE", "MDMT",
            "BUREAU VERITAS", "INTERTEK", "SGS INSPECTION", "COTAC",
            "RINA INSPECTION", "ABS INSPECTION", "TUV INSPECTION",
            "BASINÇ TEST RAPORU", "BASINC TEST RAPORU",
            "PERİYODİK MUAYENE RAPORU", "PERIYODIK MUAYENE RAPORU",
        ]
        if any(x in m for x in tank_ifadeleri):
            return "TANK BASINC RAPORU"

        if tank_no_bul(m) and ("PRESSURE" in m or "BASINC" in m or "BASINÇ" in m or
                                  "HYDRO" in m or "TANK CONTAINER" in m or "PERIODIC" in m):
            return "TANK BASINC RAPORU"

    if not _override_edilmis("ISOPA") and ("ISOPA" in m or "TDI" in m or "MDI" in m):
        return "ISOPA"

    if not _override_edilmis("TRAFIK SIGORTASI") and (
        "TRAFIK SIGORT" in m or "TRAFİK SİGORT" in m or "KARAYOLLARI MOTORLU" in m):
        return "TRAFIK SIGORTASI"

    if not _override_edilmis("FENNI MUAYENE") and (
        "FENNI MUAYENE" in m or "FENNİ MUAYENE" in m or "ARAÇ MUAYENE RAPORU" in m or "ARAC MUAYENE RAPORU" in m or "VEHICLE INSPECTION REPORT" in m):
        return "FENNI MUAYENE"

    if not _override_edilmis("SIZDIRMAZLIK") and (
        "SIZDIRMAZLIK" in m or "SIZDİRMAZLIK" in m or
        "LEAKPROOFNESS" in m or "LEAK PROOFNESS" in m or "LEAK-PROOFNESS" in m):
        return "SIZDIRMAZLIK"

    if not _override_edilmis("YABANCI PLAKA") and yabanci_plaka_bul(m):
        return "YABANCI PLAKA"

    return "DIGER BELGELER"


# ----------------------------------------------------------------------------
# DOSYA ADI ICINDEN ISLEM KODU / TUR TESPITI
# ----------------------------------------------------------------------------
def _son_token(dosya_adi):
    """Dosya adinin (uzantisiz) son bosluktan ayrilmis parcasini buyuk harfle
    dondurur. Islem kodu tespiti SADECE bu son parcaya bakilarak yapilir."""
    stem = Path(dosya_adi).stem.strip()
    if not stem:
        return ""
    parcalar = stem.replace("-", " ").split(" ")
    return parcalar[-1].upper().strip() if parcalar else ""


def _islenmis_mi(dosya_adi):
    """Dosya program tarafindan otomatik tarandi mi? (P veya eski S/PRGTOK)"""
    return _son_token(dosya_adi) in ({ISLEM_KODU} | ESKI_ISLEM_KODLARI)


def _elle_duzeltilmis_mi(dosya_adi):
    """E ve eski PRGT işaretlerini, eski çakışma ekleriyle birlikte tanır."""
    return bool(re.search(r"(?:^|[ _-])(?:E|PRGT)(?:_\d+)?$", Path(dosya_adi).stem.strip(), re.I))


def _kod_degistir(dosya_adi, yeni_kod):
    """Dosya adinin sonundaki islem kodunu yeni_kod ile degistirir.
    Son parca bilinen bir kod degilse, yeni_kod sona eklenir."""
    p = Path(dosya_adi)
    stem = p.stem.strip()
    parcalar = stem.split(" ")
    if parcalar and parcalar[-1].upper() in BILINEN_KODLAR:
        parcalar[-1] = yeni_kod
    else:
        parcalar.append(yeni_kod)
    return " ".join(x for x in parcalar if x) + p.suffix


def belge_turu_dosya_adindan(dosya_adi):
    """Dosya adi icindeki tur anahtar kelimesine bakarak kategori bulur.
    'E' (elle duzeltme) kodlu dosyalar icin kullanilir - icerik okunmadan
    sadece isimden tur cikarilir."""
    # NOT: Artik klasor/tur adlari boslukla yazildigi icin (alt cizgi degil),
    # dosya adindaki bosluklari koruyoruz; sadece eski (alt cizgili) dosya
    # adlarinin da hala taninmasi icin alt cizgili bir kopya da kontrol edilir.
    ad = dosya_adi.upper()
    ad_alt_cizgili = ad.replace(" ", "_")

    # Eski T9 alt-turleri -> birlesik T9 (alt cizgili eski isimlendirme de dahil)
    if any(eski in ad or eski.replace(" ", "_") in ad_alt_cizgili for eski in ESKI_T9_TURLERI):
        return "T9"

    for tur in BELGE_KLASORLERI.keys():
        if tur in ad or tur.replace(" ", "_") in ad_alt_cizgili:
            return tur

    for display_norm, tur in TUR_DISPLAY_REVERSE.items():
        if display_norm and len(display_norm) >= 2 and (display_norm in ad or display_norm in ad_alt_cizgili):
            return tur

    if YABANCI_PLAKA_ADAY_RE.search(ad) and not TURK_PLAKA_RE.search(ad):
        return "YABANCI PLAKA"

    return ""


# ----------------------------------------------------------------------------
# KLASOR HAZIRLAMA
# ----------------------------------------------------------------------------
def klasorleri_hazirla(ana_klasor):
    ana = Path(ana_klasor)
    # Alt klasorler dogrudan ana (secilen Taramalar) klasorune acilir,
    # araya "PREGATE ARSIV" eklenmez.
    arsiv = ana
    korumali, _ = korumali_klasorleri_oku(ana)
    if any(_klasor_adi_normalize(p) in korumali for p in ana.resolve().parts):
        raise ValueError("Korumalı klasör taranamaz.")
    for klasor in BELGE_KLASORLERI.values():
        if _klasor_adi_normalize(klasor) not in korumali:
            (arsiv / klasor).mkdir(exist_ok=True)
    for d in ("FARKLI FORMAT DOSYALAR", "OKUNAMAYAN PDF", "ISLEM RAPORLARI", ESKI_DOSYALAR, TARIHI_GECMIS):
        if _klasor_adi_normalize(d) not in korumali:
            (ana / d).mkdir(exist_ok=True)
    return arsiv


# ----------------------------------------------------------------------------
# KULLANICI TANIMLI ANAHTAR KELIMELER (klasore ozel, kalici JSON)
# ----------------------------------------------------------------------------
ANAHTAR_KELIME_DOSYA_ADI = "ANAHTAR KELIMELER.json"


def _anahtar_kelime_yolu(ana_klasor):
    return Path(ana_klasor) / "ISLEM RAPORLARI" / ANAHTAR_KELIME_DOSYA_ADI


def anahtar_kelimeleri_oku(ana_klasor):
    """Bu ana klasore ozel kullanici tanimli anahtar kelimeleri okur.
    Donus: {"TANK BASINC RAPORU": ["INSPECTION DATE", ...], ...}
    Kategori icin hic kelime tanimlanmamissa o kategori sozlukte yer almaz
    (bu durumda o kategori icin eski sabit kurallar gecerli kalir).
    Dosya yoksa veya bozuksa bos sozluk doner (hata vermez)."""
    yol = _anahtar_kelime_yolu(ana_klasor)
    if not yol.exists():
        return {}
    try:
        with open(yol, "r", encoding="utf-8") as f:
            veri = json.load(f)
        if not isinstance(veri, dict):
            return {}
        # Sadece gecerli kategori adlarini ve liste tipini kabul et
        temiz = {}
        for kategori, kelimeler in veri.items():
            if kategori in BELGE_KLASORLERI and isinstance(kelimeler, list):
                temiz[kategori] = [str(k).strip().upper() for k in kelimeler if str(k).strip()]
        return temiz
    except Exception:
        return {}


def anahtar_kelimeleri_kaydet(ana_klasor, kelime_haritasi):
    """Kullanicinin duzenledigi tum kategori->kelime listesini kaydeder.
    Bos liste olan kategoriler dosyadan tamamen cikarilir (yani o kategori
    tekrar eski sabit kurallara doner)."""
    yol = _anahtar_kelime_yolu(ana_klasor)
    yol.parent.mkdir(parents=True, exist_ok=True)
    temiz = {
        kategori: [str(k).strip().upper() for k in kelimeler if str(k).strip()]
        for kategori, kelimeler in kelime_haritasi.items()
        if kategori in BELGE_KLASORLERI and kelimeler
    }
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(temiz, f, ensure_ascii=False, indent=2)
    return temiz


def anahtar_kelime_ekle(ana_klasor, kategori, kelime):
    """Tek bir kategoriye tek bir anahtar kelime ekler (var olan listeye)."""
    if kategori not in BELGE_KLASORLERI:
        raise ValueError(f"Gecersiz kategori: {kategori}")
    kelime = str(kelime).strip().upper()
    if not kelime:
        return anahtar_kelimeleri_oku(ana_klasor)
    harita = anahtar_kelimeleri_oku(ana_klasor)
    mevcut = harita.get(kategori, [])
    if kelime not in mevcut:
        mevcut.append(kelime)
    harita[kategori] = mevcut
    return anahtar_kelimeleri_kaydet(ana_klasor, harita)


def anahtar_kelime_sil(ana_klasor, kategori, kelime):
    """Bir kategoriden tek bir anahtar kelimeyi siler."""
    kelime = str(kelime).strip().upper()
    harita = anahtar_kelimeleri_oku(ana_klasor)
    if kategori in harita and kelime in harita[kategori]:
        harita[kategori].remove(kelime)
        if not harita[kategori]:
            del harita[kategori]
    return anahtar_kelimeleri_kaydet(ana_klasor, harita)


# ----------------------------------------------------------------------------
# DOSYA TASIMA (thread-safe)
# ----------------------------------------------------------------------------
_TASIMA_KILIDI = threading.Lock()


def benzersiz_yol(hedef_yol):
    if not hedef_yol.exists():
        return hedef_yol
    stem, suffix, parent = hedef_yol.stem, hedef_yol.suffix, hedef_yol.parent
    i = 1
    while True:
        aday = parent / f"{stem}_{i}{suffix}"
        if not aday.exists():
            return aday
        i += 1


def dosya_tasi(kaynak, hedef_klasor, yeni_ad=None, korumali=None):
    """Dosyayi hedef klasore tasir. Hedef yol zaten kaynagin kendisiyse hicbir
    sey yapilmaz (zaten dogru yerde/isimde)."""
    korumali = korumali or VARSAYILAN_KULLANICI_KORUMALI_KLASORLER
    with _TASIMA_KILIDI:
        if any(_klasor_adi_normalize(part) in korumali
               for yol in (kaynak, hedef_klasor) for part in yol.resolve().parts):
            raise ValueError("Kontrol Formu klasöründe taşıma yapılamaz.")
        hedef_klasor.mkdir(parents=True, exist_ok=True)
        hedef_aday = hedef_klasor / (yeni_ad if yeni_ad else kaynak.name)
        if kaynak.resolve() == hedef_aday.resolve():
            return hedef_aday
        hedef = benzersiz_yol(hedef_aday)
        shutil.move(str(kaynak), str(hedef))
        return hedef


# ----------------------------------------------------------------------------
# YENI DOSYA ADI OLUSTURMA
# ----------------------------------------------------------------------------
def _fp(text, max_len=0):
    """Dosya adi parcasi: sadece A-Z 0-9 nokta izinli, digerleri bosluk."""
    if not text:
        return ""
    tr_map = str.maketrans("ÇĞİÖŞÜçğıöşü", "CGIOSUcgiosu")
    t = str(text).replace("\u00a0", " ").translate(tr_map).upper().strip()
    t = re.sub(r"[^A-Z0-9.]+", " ", t)
    t = re.sub(r" +", " ", t).strip()
    return t[:max_len] if max_len else t


def bilgi_cek(metin, dosya_adi="", ozel_kelimeler=None, tur=None, tarih_oku=True):
    tur = tur or belge_turu_bul(metin, dosya_adi, ozel_kelimeler)
    dosya_bilgisi = bilgi_dosya_adindan(dosya_adi)
    return {
        "plaka": plaka_bul(metin) or dosya_bilgisi.get("plaka", ""),
        "tank_no": tank_no_bul(metin) or dosya_bilgisi.get("tank_no", ""),
        "sasi": sasi_bul(metin) or dosya_bilgisi.get("sasi", ""),
        "yabanci_plaka": yabanci_plaka_bul(metin) or dosya_bilgisi.get("yabanci_plaka", ""),
        "tarih": (en_mantikli_tarih(metin, tur) or dosya_bilgisi.get("tarih", "")) if tarih_oku else "",
        "kapasite": kapasite_bul(metin) or dosya_bilgisi.get("kapasite", ""),
        "tank_kodu": tank_kodu_bul(metin) or dosya_bilgisi.get("tank_kodu", ""),
        "surucu": surucu_adi_bul(metin, dosya_adi) or dosya_bilgisi.get("surucu", ""),
        "un_numaralar": un_numaralari_bul(metin),
    }


def yeni_dosya_adi_olustur(tur, bilgi, eski_ad, uzanti):
    tank_no = bilgi.get("tank_no") or ""
    tarih = bilgi.get("tarih") or ""
    kapasite = bilgi.get("kapasite") or ""
    tank_kodu = bilgi.get("tank_kodu") or ""
    un_numaralar = bilgi.get("un_numaralar") or ""
    tur_ad = TUR_DISPLAY.get(tur, tur.replace("_", " "))

    if tur in {"ISOPA", "SRC5", "YUKSEKTE CALISABILIR SAGLIK RAPORU"}:
        kimlik = bilgi.get("surucu") or temizle_ad(Path(eski_ad).stem, 40)
    elif tur in {"T9", "TASIT UYGUNLUK GECICI BELGE", "TASIT UYGUNLUK MUAYENE SERTIFIKASI"}:
        kimlik = bilgi.get("plaka") or tank_no or bilgi.get("sasi") or temizle_ad(Path(eski_ad).stem, 40)
    else:
        kimlik = (
            tank_no or bilgi.get("plaka") or bilgi.get("sasi") or
            bilgi.get("yabanci_plaka") or bilgi.get("surucu") or temizle_ad(Path(eski_ad).stem, 40)
        )

    if not anlamli_kimlik_mi(kimlik):
        kimlik = temizle_ad(Path(eski_ad).stem, 40)

    kimlik_part = tank_no if (tank_no and kimlik == tank_no) else _fp(kimlik, 60)

    if tur == "YABANCI PLAKA":
        parcalar = [_fp(bilgi.get("yabanci_plaka") or kimlik_part)]
        if tarih:
            parcalar.append(tarih)
        parcalar.append(ISLEM_KODU)
        return " ".join(p for p in parcalar if p)[:160] + uzanti.lower()

    if tur == "TANK BASINC RAPORU":
        parcalar = [kimlik_part]
        if tarih:
            parcalar.append(tarih)
        if tank_kodu:
            parcalar.append(_fp(tank_kodu))
        if kapasite:
            parcalar.append(_fp(kapasite))
        parcalar += [tur_ad, ISLEM_KODU]
        return " ".join(p for p in parcalar if p)[:180] + uzanti.lower()

    if tur == "T9":
        parcalar = [kimlik_part]
        if tarih:
            parcalar.append(tarih)
        if kapasite:
            parcalar.append(_fp(kapasite))
        if tank_kodu:
            parcalar.append(_fp(tank_kodu))
        parcalar.append(tur_ad)
        if un_numaralar:
            parcalar.append(un_numaralar)
        parcalar.append(ISLEM_KODU)
        return " ".join(p for p in parcalar if p)[:180] + uzanti.lower()

    parcalar = [kimlik_part]
    if tarih:
        parcalar.append(tarih)
    if kapasite and tur == "SIZDIRMAZLIK":
        parcalar.append(_fp(kapasite))
    parcalar += [tur_ad, ISLEM_KODU]
    return " ".join(p for p in parcalar if p)[:180] + uzanti.lower()


# ----------------------------------------------------------------------------
# TEK DOSYA ISLEME (ana mantik)
# ----------------------------------------------------------------------------
def dosya_isle(dosya_yolu, ana_klasor, ozel_kelimeler=None, *, ikinci=False):
    """ozel_kelimeler verilmezse, ana_klasor icin kayitli kullanici tanimli
    anahtar kelimeler otomatik olarak diskten okunur (performans icin toplu
    islemlerde bu sozluk bir kere okunup tum dosyalara aynen gecirilir)."""
    if ozel_kelimeler is None:
        ozel_kelimeler = anahtar_kelimeleri_oku(ana_klasor)
    kaynak = Path(dosya_yolu)
    arsiv = Path(ana_klasor)
    eski_ad, uzanti = kaynak.name, kaynak.suffix.lower()

    sonuc = {
        "Eski Dosya Adı": eski_ad, "Yeni Dosya Adı": "", "Belge Türü": "", "Plaka": "", "Tank No": "",
        "Şasi No": "", "Yabancı Plaka": "", "Geçerlilik Tarihi": "", "Kapasite": "", "Tank Kodu": "",
        "Sürücü": "", "Bulunduğu Klasör": str(kaynak.parent), "Yeni Klasör": "", "İşlem Durumu": "",
        "Hata": "", "İşlem Tarihi": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
    }

    try:
        korumali, _ = korumali_klasorleri_oku(arsiv)
        if any(_klasor_adi_normalize(p) in korumali for p in kaynak.resolve().parts):
            sonuc["İşlem Durumu"] = "KORUMALI DOSYA ATLANDI"
            return sonuc

        if _elle_duzeltilmis_mi(eski_ad):
            sonuc.update({
                "Yeni Dosya Adı": eski_ad,
                "Yeni Klasör": str(kaynak.parent),
                "Belge Türü": BELGE_KLASORLERI.get(kaynak.parent.name)
                or belge_turu_dosya_adindan(eski_ad) or "",
                "İşlem Durumu": "ELLE DÜZELTİLDİ - ATLANDI",
            })
            return sonuc

        if kaynak.name.startswith("~$"):
            sonuc["İşlem Durumu"] = "GECICI DOSYA ATLANDI"
            return sonuc

        if "ISLEM RAPORLARI" in str(kaynak.parent):
            sonuc["İşlem Durumu"] = "RAPOR ATLANDI"
            return sonuc

        kok = arsiv if uzanti in PDF_EXT else arsiv / "FARKLI FORMAT DOSYALAR" / (uzanti[1:].upper() or "UZANTISIZ")
        if uzanti not in OKUNABILIR_EXT:
            yeni_yol = dosya_tasi(kaynak, kok / "DESTEKLENMEYEN", korumali=korumali)
            sonuc.update({
                "Belge Türü": "FARKLI FORMAT DOSYALAR",
                "Yeni Dosya Adı": yeni_yol.name,
                "Yeni Klasör": str(yeni_yol.parent),
                "İşlem Durumu": "DESTEKLENMEYEN FORMAT",
            })
            return sonuc

        try:
            metin, serit = _belge_oku(kaynak, ikinci=True) if ikinci else _belge_oku(kaynak)
        except Exception as hata:
            metin, serit = "", False
            sonuc["Hata"] = str(hata)
        tur = belge_turu_bul(metin, ozel_kelimeler=ozel_kelimeler, kirmizi_serit=serit)
        bilgi = bilgi_cek(metin, ozel_kelimeler=ozel_kelimeler, tur=tur, tarih_oku=uzanti in PDF_EXT)
        kimlik = (
            bilgi["surucu"] if tur in {"ISOPA", "SRC5", "YUKSEKTE CALISABILIR SAGLIK RAPORU"}
            else bilgi["plaka"] or bilgi["sasi"] if tur in {"RUHSAT", "TASIT KARTI"}
            else bilgi["yabanci_plaka"] if tur == "YABANCI PLAKA"
            else bilgi["tank_no"] or bilgi["plaka"] or bilgi["sasi"]
        )
        if not metin or tur == "DIGER BELGELER" or not kimlik:
            if uzanti in PDF_EXT and not ikinci:
                return None
            if uzanti in PDF_EXT or tur == "DIGER BELGELER":
                hedef = kok / ("OKUNAMAYAN PDF" if uzanti in PDF_EXT else "INCELENECEK")
            else:
                hedef = kok / BELGE_KLASORLERI[tur]
            yeni_yol = dosya_tasi(kaynak, hedef, korumali=korumali)
            sonuc.update({
                "Belge Türü": tur,
                "Yeni Dosya Adı": yeni_yol.name,
                "Yeni Klasör": str(yeni_yol.parent),
                "İşlem Durumu": "KONTROL GEREKLI",
            })
            return sonuc

        if tur in {"RUHSAT", "TASIT KARTI"}:
            bilgi["tank_no"] = ""
        if uzanti in PDF_EXT:
            sinir = _pdf_son_gun(metin, tur, bilgi["tarih"])
            sonuc["_tarih_siniri"] = sinir
            if sinir and sinir < date.today():
                kok = arsiv / TARIHI_GECMIS
        yeni_ad = yeni_dosya_adi_olustur(tur, bilgi, eski_ad, uzanti)
        yeni_yol = dosya_tasi(kaynak, kok / BELGE_KLASORLERI[tur], yeni_ad, korumali=korumali)

        sonuc.update({
            "Yeni Dosya Adı": yeni_yol.name,
            "Belge Türü": tur,
            "Plaka": bilgi.get("plaka", ""),
            "Tank No": bilgi.get("tank_no", ""),
            "Şasi No": bilgi.get("sasi", ""),
            "Yabancı Plaka": bilgi.get("yabanci_plaka", ""),
            "Geçerlilik Tarihi": bilgi.get("tarih", ""),
            "Kapasite": bilgi.get("kapasite", ""),
            "Tank Kodu": bilgi.get("tank_kodu", ""),
            "Sürücü": bilgi.get("surucu", ""),
            "Yeni Klasör": str(yeni_yol.parent),
            "İşlem Durumu": "TARİHİ GEÇMİŞ" if kok == arsiv / TARIHI_GECMIS else "OKUNDU TASINDI",
        })
        return sonuc

    except Exception as e:
        sonuc["İşlem Durumu"] = "HATA"
        sonuc["Hata"] = str(e)
        return sonuc


def _tarama_dosyalari(ana, atla):
    for root, dirs, files in os.walk(ana):
        kok = Path(root)
        dirs[:] = sorted(d for d in dirs if _klasor_adi_normalize(d) not in atla and not (kok / d).is_symlink())
        for ad in sorted(files):
            yol = kok / ad
            if not ad.startswith("~$") and not yol.is_symlink():
                yield yol


def _rapor_yaz(ana, sonuclar, baslik):
    df = pd.DataFrame(sonuclar).drop(columns="_tarih_siniri", errors="ignore")
    if not df.empty:
        rapor = ana / "ISLEM RAPORLARI" / f"{baslik} {datetime.now():%d-%m-%Y %H-%M-%S}.xlsx"
        df.to_excel(rapor, index=False)
        _index_guncelle(ana, df)
    return df


def _tarama_yurut(ana, dosyalar, rapor_adi, log_callback, progress_callback):
    ozel = anahtar_kelimeleri_oku(ana)
    sonuclar = {}
    korumali, _ = korumali_klasorleri_oku(ana)
    okunamayan = ana / "OKUNAMAYAN PDF"
    ikinci_tur = {
        yol for yol in _tarama_dosyalari(okunamayan, korumali)
        if yol.suffix.lower() in PDF_EXT and not _elle_duzeltilmis_mi(yol.name)
    } if okunamayan.name not in korumali and not okunamayan.is_symlink() else set()
    ikinci_tur.difference_update(dosyalar)
    toplam = len(dosyalar)

    def kaydet(sonuc):
        konum = Path(sonuc["Yeni Klasör"]) / sonuc["Yeni Dosya Adı"]
        if not sonuc["Yeni Dosya Adı"]:
            konum = Path(sonuc["Bulunduğu Klasör"]) / sonuc["Eski Dosya Adı"]
        sonuclar[konum] = sonuc
        if log_callback:
            log_callback(f"{sonuc['İşlem Durumu']}: {sonuc['Eski Dosya Adı']}")

    with ThreadPoolExecutor(max_workers=min(2, max(1, (os.cpu_count() or 1) - 1))) as havuz:
        bekleyen = {havuz.submit(dosya_isle, yol, ana, ozel): yol for yol in dosyalar}
        for sayi, islem in enumerate(as_completed(bekleyen), 1):
            sonuc = islem.result()
            if sonuc is None:
                ikinci_tur.add(bekleyen[islem])
            else:
                kaydet(sonuc)
            if progress_callback:
                progress_callback(sayi, toplam)
        if ikinci_tur and log_callback:
            log_callback(f"İkinci OCR taraması: {len(ikinci_tur)} PDF")
        bekleyen = [havuz.submit(dosya_isle, yol, ana, ozel, ikinci=True) for yol in sorted(ikinci_tur)]
        for sayi, islem in enumerate(as_completed(bekleyen), 1):
            kaydet(islem.result())
            if progress_callback:
                progress_callback(sayi, len(ikinci_tur))

    _pdf_arsivi_duzenle(ana, sonuclar, log_callback, progress_callback)
    _son_tarama_bilgisini_kaydet(ana, toplam)
    return _rapor_yaz(ana, sonuclar.values(), rapor_adi)


def klasor_tara(ana_klasor, log_callback=None, progress_callback=None):
    ana = klasorleri_hazirla(ana_klasor)
    korumali, _ = korumali_klasorleri_oku(ana)
    atla = korumali | set(BELGE_KLASORLERI.values()) | ESKI_T9_TURLERI | {
        "FARKLI FORMAT DOSYALAR", "OKUNAMAYAN PDF", "ISLEM RAPORLARI", ESKI_DOSYALAR, TARIHI_GECMIS,
    }
    return _tarama_yurut(ana, list(_tarama_dosyalari(ana, atla)), "ISLEM RAPORU", log_callback, progress_callback)


def _tarih_degeri(deger):
    try:
        return datetime.strptime(deger, "%d.%m.%Y").date()
    except (ValueError, TypeError):
        if isinstance(deger, str) and re.fullmatch(r"(?:0[1-9]|1[0-2])\.\d{4}", deger):
            ay, yil = map(int, deger.split("."))
            if yil:
                return date(yil, ay, monthrange(yil, ay)[1])
        return None


def _pdf_son_gun(metin, tur, gecerlilik=""):
    """Son geçerlilik" önceliklidir. Düzenleme tarihine bir takvim ayı eklenir."""
    duz = _klasor_adi_normalize(" ".join(metin.split()))
    acik_tarih = re.search(
        r"\b(?:GECERLILIK TARIHI|GECERLILIK BITIS TARIHI|VALID UNTIL|EXPIRY DATE|EXPIRATION DATE)"
        r"\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4}|\d{4}[./-]\d{2}[./-]\d{2})", duz
    )
    if acik_tarih:
        return _tarih_degeri(tarih_formatla(acik_tarih[1]))
    onay = gecerlilik or en_mantikli_tarih(metin, tur)
    if onay:
        return _tarih_degeri(onay)
    if re.search(r"\b(?:GECERLILIK TARIHI|BITIS TARIHI|VALID UNTIL|EXPIRY DATE|EXPIRATION DATE)\b", duz):
        return None
    duzenleme = re.search(
        r"\b(?:DUZENLEME TARIHI|BELGE DUZENLEME TARIHI|YAPILIS TARIHI|ISSUE DATE|DATE OF ISSUE)"
        r"\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4}|\d{4}[./-]\d{2}[./-]\d{2})", duz
    )
    gun = _tarih_degeri(tarih_formatla(duzenleme[1])) if duzenleme else None
    if gun:
        yil, ay = (gun.year + 1, 1) if gun.month == 12 else (gun.year, gun.month + 1)
        return date(yil, ay, min(gun.day, monthrange(yil, ay)[1]))
    return None


def _gecmis_adini_temizle(ad):
    return re.sub(r"^\d{3,} - ", "", ad)


def _pdf_kimligi(yol, tur, kayit):
    alanlar = (
        ("Sürücü",) if tur in {"ISOPA", "SRC5", "YUKSEKTE CALISABILIR SAGLIK RAPORU"}
        else ("Tank No",) if tur == "TANK BASINC RAPORU"
        else ("Yabancı Plaka",) if tur == "YABANCI PLAKA"
        else ("Plaka", "Tank No", "Şasi No")
    )
    for alan in alanlar:
        if kayit.get(alan):
            return _fp(kayit[alan]).replace(" ", "")
    # Yalnızca içeriğiyle sınıflandırılan araç PDF'lerinin başındaki kimliği kullan.
    ad = _gecmis_adini_temizle(yol.name)
    if not re.search(r"(?:^|[ _-])(?:P|S|PRGTOK)(?:_\d+)?\.pdf$", ad, re.I):
        return ""
    ad = re.split(r"\s+\d{2}\.\d{2}\.\d{4}\b", Path(ad).stem, maxsplit=1)[0]
    etiket = TUR_DISPLAY.get(tur, tur)
    ad = re.split(r"\s+" + re.escape(etiket) + r"\b", ad, maxsplit=1, flags=re.I)[0]
    ad = re.sub(r"\s+(?:P|S|PRGTOK)(?:_\d+)?$", "", ad, flags=re.I)
    if tur in {"ISOPA", "SRC5", "YUKSEKTE CALISABILIR SAGLIK RAPORU"}:
        return _fp(ad).replace(" ", "") if anlamli_kimlik_mi(ad) else ""
    aday = ad.split()[0] if ad.split() else ""
    kimlik = plaka_bul(aday) or tank_no_bul(aday) or sasi_bul(aday)
    if tur == "YABANCI PLAKA":
        kimlik = yabanci_plaka_bul(aday)
    return _fp(kimlik).replace(" ", "")


def _yukleme_anahtari(yol):
    bilgi = yol.stat()
    # Windows/macOS oluşturma zamanı. Oluşturma zamanı olmayan sistemlerde
    # taşıma sırasında değişmeyen dosya değiştirme zamanı kullanılır.
    return getattr(bilgi, "st_birthtime", bilgi.st_mtime), bilgi.st_mtime, yol.name.casefold()


def _pdf_arsivi_duzenle(ana, sonuclar, log_callback, progress_callback, *, yalniz_tarih=False):
    korumali, _ = korumali_klasorleri_oku(ana)
    atla = korumali | {"FARKLI FORMAT DOSYALAR", "ISLEM RAPORLARI", TARIHI_GECMIS}
    ozel = anahtar_kelimeleri_oku(ana)
    try:
        onceki = {
            Path(kayit["Yeni Klasör"]) / kayit["Yeni Dosya Adı"]: kayit
            for kayit in _mevcut_arsiv_kayitlari(ana).to_dict("records")
        }
    except (OSError, KeyError, ValueError):
        onceki = {}
    gruplar = {}
    bugun = date.today()
    pdfler = [yol for yol in _tarama_dosyalari(ana, atla)
              if yol.suffix.lower() in PDF_EXT and not _elle_duzeltilmis_mi(yol.name)]
    if log_callback:
        log_callback("PDF tarihleri kontrol ediliyor…")

    def tasi(yol, hedef, ad, tur, neden, tarih=""):
        kayit = sonuclar.get(yol, onceki.get(yol, {}))
        try:
            yeni = dosya_tasi(yol, hedef, ad, korumali=korumali)
        except (OSError, ValueError) as hata:
            sonuclar[yol] = {
                **kayit, "Eski Dosya Adı": kayit.get("Eski Dosya Adı", yol.name),
                "Bulunduğu Klasör": str(yol.parent), "Yeni Dosya Adı": yol.name,
                "Yeni Klasör": str(yol.parent), "Belge Türü": tur,
                "İşlem Durumu": "HATA", "Hata": str(hata),
            }
            return yol
        if yeni == yol and not yalniz_tarih:
            return yol
        sonuclar.pop(yol, None)
        sonuclar[yeni] = {
            **kayit, "Eski Dosya Adı": kayit.get("Eski Dosya Adı", yol.name),
            "Bulunduğu Klasör": kayit.get("Bulunduğu Klasör", str(yol.parent)),
            "Yeni Dosya Adı": yeni.name, "Yeni Klasör": str(yeni.parent),
            "Belge Türü": tur, "İşlem Durumu": neden,
            "Geçerlilik Tarihi": kayit.get("Geçerlilik Tarihi") or tarih,
            "İşlem Tarihi": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        }
        return yeni

    for sayi, yol in enumerate(pdfler, 1):
        if progress_callback:
            progress_callback(sayi, len(pdfler))
        kayit = sonuclar.get(yol, onceki.get(yol, {}))
        if yol.parent.name == "OKUNAMAYAN PDF" and not yalniz_tarih:
            continue
        tur = BELGE_KLASORLERI.get(yol.parent.name) or kayit.get("Belge Türü") or ""
        etiketli = bool(re.search(r"(?:^|[ _-])P(?:_\d+)?\.pdf$", yol.name, re.I))
        ad_tarih = re.search(r"(?<![\d.])((?:\d{2}\.)?\d{2}\.\d{4})(?![\d.])", yol.stem) if etiketli else None
        son_gun = kayit.get("_tarih_siniri")
        gercek_tarih = kayit.get("Geçerlilik Tarihi", "")
        if not son_gun and ad_tarih:
            gercek_tarih = ad_tarih[1]
            son_gun = _tarih_degeri(gercek_tarih)
        hata = ""
        if not son_gun and "_tarih_siniri" not in kayit:
            try:
                metin, serit = _belge_oku(yol)
                tur = tur or belge_turu_bul(metin, ozel_kelimeler=ozel, kirmizi_serit=serit)
                gercek_tarih = en_mantikli_tarih(metin, tur)
                son_gun = _pdf_son_gun(metin, tur, gercek_tarih)
            except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as e:
                hata = str(e)
        if son_gun and son_gun < bugun:
            tasi(yol, ana / TARIHI_GECMIS / (tur or "DIGER BELGELER"),
                 _gecmis_adini_temizle(yol.name), tur or "DIGER BELGELER", "TARİHİ GEÇMİŞ", gercek_tarih)
            continue
        if yalniz_tarih:
            sonuclar[yol] = {
                **kayit,
                "Eski Dosya Adı": yol.name, "Yeni Dosya Adı": yol.name,
                "Bulunduğu Klasör": str(yol.parent), "Yeni Klasör": str(yol.parent),
                "Belge Türü": tur, "Geçerlilik Tarihi": gercek_tarih,
                "İşlem Durumu": "OKUMA HATASI" if hata else ("TARİH KONTROL EDİLDİ" if son_gun else "TARİH BULUNAMADI"),
                "Hata": hata, "İşlem Tarihi": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
            }
            continue
        if not tur or tur == "DIGER BELGELER":
            continue
        in_history = ESKI_DOSYALAR in yol.relative_to(ana).parts
        if yol.parent != ana / tur and not in_history:
            continue
        kimlik = _pdf_kimligi(yol, tur, kayit)
        if kimlik:
            gruplar.setdefault((tur, kimlik), []).append((yol, in_history))

    for (tur, _), dosyalar in gruplar.items():
        yuklemeler = []
        for yol, arsivde in dosyalar:
            try:
                yuklemeler.append((_yukleme_anahtari(yol), yol, arsivde))
            except FileNotFoundError:
                continue
        sirali = [(yol, arsivde) for _, yol, arsivde in sorted(yuklemeler)]
        etkin = [yol for yol, arsivde in sirali if not arsivde]
        guncel = etkin[-1] if etkin else None
        plan = {}
        gecmis = (yol for yol, _ in sirali if yol != guncel)
        for sira, yol in enumerate(gecmis, 1):
            hedef = ana / ESKI_DOSYALAR / tur / f"{sira:03d} - {_gecmis_adini_temizle(yol.name)}"
            if yol != hedef:
                plan[yol] = hedef
        while plan:
            # Önce yeri boşaltılacak belgeleri taşı. Aynı adlı dosyalara
            # dosya taşıma işlevi güvenli bir çakışma eki ekler.
            yol = next((anahtar for anahtar, hedef in plan.items() if hedef not in plan), next(iter(plan)))
            hedef = plan.pop(yol)
            tasi(yol, hedef.parent, hedef.name, tur, "ESKİ SÜRÜM")


def tarih_kontrolu(ana_klasor, log_callback=None, progress_callback=None):
    ana = klasorleri_hazirla(ana_klasor)
    sonuclar = {}
    _pdf_arsivi_duzenle(ana, sonuclar, log_callback, progress_callback, yalniz_tarih=True)
    return _rapor_yaz(ana, sonuclar.values(), "TARIH KONTROLU")


def _index_guncelle(ana, yeni):
    yol = ana / "ISLEM RAPORLARI" / "ARSIV INDEX.xlsx"
    onceki = _mevcut_arsiv_kayitlari(ana)
    birlesik = pd.concat([onceki, yeni], ignore_index=True)
    birlesik = birlesik.drop_duplicates(["Yeni Klasör", "Yeni Dosya Adı"], keep="last")
    gecici = yol.with_name(".ARSIV INDEX.tmp.xlsx")
    birlesik.to_excel(gecici, index=False)
    gecici.replace(yol)


def _son_tarama_bilgisini_kaydet(ana_klasor, dosya_sayisi):
    """Son tarama tarih/saat bilgisini kucuk bir metin dosyasinda tutar.
    Arayuzde sag ust kosede 'Son tarama: ...' seklinde gosterilir."""
    ana = Path(ana_klasor)
    rapor_klasor = ana / "ISLEM RAPORLARI"
    rapor_klasor.mkdir(exist_ok=True)
    bilgi_yolu = rapor_klasor / "SON TARAMA.txt"
    try:
        with open(bilgi_yolu, "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%d.%m.%Y %H:%M:%S") + "\n")
            f.write(str(dosya_sayisi))
    except Exception:
        pass


def son_tarama_bilgisi_oku(ana_klasor):
    """Sag ust kosede gosterilecek 'Son tarama: 16.06.2026 09:04' bilgisini okur.
    Hic tarama yapilmadiysa None doner."""
    bilgi_yolu = Path(ana_klasor) / "ISLEM RAPORLARI" / "SON TARAMA.txt"
    if not bilgi_yolu.exists():
        return None
    try:
        with open(bilgi_yolu, "r", encoding="utf-8") as f:
            satirlar = f.read().splitlines()
        tarih_saat = satirlar[0] if satirlar else ""
        sayi = satirlar[1] if len(satirlar) > 1 else "0"
        return {"tarih_saat": tarih_saat, "dosya_sayisi": sayi}
    except Exception:
        return None


def zorla_yeniden_oku(ana_klasor, log_callback=None, progress_callback=None):
    ana = klasorleri_hazirla(ana_klasor)
    korumali, _ = korumali_klasorleri_oku(ana)
    okunamayan = ana / "OKUNAMAYAN PDF"
    dosyalar = [] if okunamayan.name in korumali or not okunamayan.is_dir() else [
        yol for yol in _tarama_dosyalari(okunamayan, korumali) if yol.suffix.lower() in PDF_EXT
    ]
    return _tarama_yurut(ana, dosyalar, "OKUNAMAYAN TEKRAR DENE", log_callback, progress_callback)


def tum_dosyalari_yeniden_tara(ana_klasor, log_callback=None, progress_callback=None):
    ana = klasorleri_hazirla(ana_klasor)
    korumali, _ = korumali_klasorleri_oku(ana)
    atla = korumali | {"ISLEM RAPORLARI", ESKI_DOSYALAR, TARIHI_GECMIS}
    dosyalar = [yol for yol in _tarama_dosyalari(ana, atla) if yol.suffix.lower() in OKUNABILIR_EXT]
    return _tarama_yurut(ana, dosyalar, "TUMUNU YENIDEN TARA", log_callback, progress_callback)


# ----------------------------------------------------------------------------
# OZET SAYILAR (dashboard kartlari icin)
# ----------------------------------------------------------------------------
def ozet_sayilar(ana_klasor):
    ana = Path(ana_klasor)
    # v2.4.0'dan itibaren alt klasorler dogrudan ana klasorun altinda
    # (araya "PREGATE ARSIV" girmiyor). Bu fonksiyon eski yapiyi arıyordu ve
    # bu yuzden dashboard'daki kategori sayaclari v2.4.0'dan beri hep 0/yanlis
    # gosteriyordu; duzeltildi.
    arsiv = ana
    ozet = {"TOPLAM": 0}

    for tur, klasor_adi in BELGE_KLASORLERI.items():
        klasor = arsiv / klasor_adi
        sayi = sum(p.is_file() and p.suffix.lower() in PDF_EXT for p in klasor.iterdir()) if klasor.exists() else 0
        ozet[tur] = ozet.get(tur, 0) + sayi
        ozet["TOPLAM"] += sayi

    korumali, _ = korumali_klasorleri_oku(ana)
    farkli_adet = 0
    for root, dirs, files in os.walk(ana / "FARKLI FORMAT DOSYALAR"):
        dirs[:] = [d for d in dirs if _klasor_adi_normalize(d) not in korumali]
        klasor = Path(root).name
        sayi = sum(not name.startswith("~$") for name in files)
        farkli_adet += sayi
        if klasor in BELGE_KLASORLERI:
            ozet[klasor] += sayi
            ozet["TOPLAM"] += sayi
    ozet["FARKLI FORMAT DOSYALAR"] = farkli_adet

    for tur in (ESKI_DOSYALAR, TARIHI_GECMIS):
        hedef = ana / tur
        ozet[tur] = sum(yol.suffix.lower() in PDF_EXT for yol in _tarama_dosyalari(hedef, korumali)) if tur not in korumali else 0

    okunamayan = ana / "OKUNAMAYAN PDF"
    ozet["OKUNAMAYAN PDF"] = sum(p.is_file() and p.suffix.lower() in PDF_EXT for p in okunamayan.iterdir()) if okunamayan.exists() else 0

    return ozet


# ----------------------------------------------------------------------------
# ARSIV INDEX
# ----------------------------------------------------------------------------
def _mevcut_arsiv_kayitlari(ana_klasor):
    index_yolu = Path(ana_klasor) / "ISLEM RAPORLARI" / "ARSIV INDEX.xlsx"
    if not index_yolu.exists():
        return pd.DataFrame()

    df = pd.read_excel(index_yolu).fillna("")

    def dosya_mevcut(row):
        klasor = str(row.get("Yeni Klasör", "")).strip()
        ad = str(row.get("Yeni Dosya Adı", "")).strip()
        return bool(klasor and ad) and (Path(klasor) / ad).is_file()

    if df.empty:
        return df
    return df.loc[df.apply(dosya_mevcut, axis=1)].drop(columns="Tam Yol", errors="ignore")
