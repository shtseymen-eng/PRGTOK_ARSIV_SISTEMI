# ============================================================================
# PRGTOK ARSIV SISTEMI - motor.py
# Surum: 2.0.0  (sifirdan yeniden yazildi)
#
# DEGISIKLIKLER (v2.0.0):
#   - Program SADECE PDF dosyalarini tarar / siniflandirir / isimlendirir.
#   - PDF olmayan TUM dosyalar (jpg, png, docx, xlsx, vb.) tek bir
#     "FARKLI FORMAT DOSYALAR" klasorune tasinir; bu dosyalar OCR/metin
#     okuma surecine hic girmez (eskiden resimler icin OCR yapiliyordu,
#     bu kaldirildi - sadece PDF okunur).
#   - T9 alt turleri (T9_GECICI / T9_MUAYENE / T9_ANA) KALDIRILDI.
#     Hepsi tek "T9" kategorisinde birlesti.
#   - Islem kodu sistemi sadelesti:
#       "P"  = Program tarafindan otomatik tarandi/siniflandirildi
#       "E"  = Elle duzeltildi (kullanici dosya adini kendi yazdi)
#     Kod HER ZAMAN dosya adinin SONUNDA (uzantidan once) yer alir.
#   - "E" ile bitmis dosyalar: program bu dosyalarin ICERIGINI BIR DAHA
#     OKUMAZ. Sadece dosya adi icindeki tur anahtar kelimesine gore
#     dogru klasore tasir (kullanicinin yazdigi isim oldugu gibi kalir,
#     sadece konum kontrol edilir / duzeltilir).
#   - "P" ile bitmis dosyalar: zaten islenmis sayilir, sadece dogru
#     klasorde mi diye konum kontrolu yapilir (yeniden okunmaz).
#   - Kod tasimayan / ne P ne E olan PDF'ler: icerik okunur, turu
#     bulunur, yeniden adlandirilir (sonuna " P" eklenir) ve ilgili
#     klasore tasinir.
# ============================================================================

import json
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber

# OCR (resimden metin tanima) - sadece normal yontemle metin cikarilamayan
# (taranmis/resim tabanli) PDF'ler icin devreye girer. Kutuphaneler
# kurulu degilse OCR sessizce devre disi kalir, program calismayi
# surdurur (sadece OKUNAMAYAN PDF sayisi yuksek kalir).
try:
    from pdf2image import convert_from_path as _ocr_pdf_to_images
    import pytesseract as _ocr_engine
    OCR_KULLANILABILIR = True

    if os.name == "nt":
        import subprocess, sys as _sys

        # Windows'ta Tesseract ve Poppler cagrilirken siyah konsol
        # penceresi acilmasin: subprocess'e CREATE_NO_WINDOW bayragi ver.
        _CREATE_NO_WINDOW = 0x08000000

        # pdf2image icindeki Popen cagrisini gizli yap
        _orijinal_popen = subprocess.Popen
        def _gizli_popen(*args, **kwargs):
            if os.name == "nt":
                kwargs.setdefault("creationflags", 0)
                kwargs["creationflags"] |= _CREATE_NO_WINDOW
                kwargs.setdefault("startupinfo", subprocess.STARTUPINFO())
                kwargs["startupinfo"].dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"].wShowWindow = 0
            return _orijinal_popen(*args, **kwargs)
        subprocess.Popen = _gizli_popen

        # pytesseract icin de ayni ayar
        _ocr_engine.pytesseract.get_tesseract_version.__globals__.get(
            "subprocess", subprocess)  # noqa – sadece import tetikle

        # PyInstaller ile paketlendiginde Tesseract ve Poppler exe icine
        # gomulur; sys._MEIPASS bu gecici klasore isaret eder.
        _meipass = getattr(_sys, "_MEIPASS", None)

        _olasi_tesseract_yollari = []
        if _meipass:
            _olasi_tesseract_yollari.append(
                os.path.join(_meipass, "tesseract", "tesseract.exe"))
        _olasi_tesseract_yollari += [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for _yol in _olasi_tesseract_yollari:
            if os.path.exists(_yol):
                _ocr_engine.pytesseract.tesseract_cmd = _yol
                break
except Exception:
    OCR_KULLANILABILIR = False

SURUM = "2.4.0"

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

# Dosya adindan tur tespiti icin ters-arama tablosu (kisa etiket -> tur)
TUR_DISPLAY_REVERSE = {v: k for k, v in TUR_DISPLAY.items()}

PDF_EXT = {".pdf"}

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
    tarihler = tum_tarihleri_bul(metin)
    if not tarihler:
        return ""
    try:
        normal = [x for x in tarihler if re.match(r"\d{2}\.\d{2}\.\d{4}", x)]
        sirali = sorted(set(normal), key=lambda x: datetime.strptime(x, "%d.%m.%Y"))
        return sirali[-1] if sirali else tarihler[-1]
    except Exception:
        return tarihler[-1]


OCR_MAX_SAYFA = 3  # OCR sadece ilk N sayfayi tarar (hiz icin)
OCR_DPI = 200


def _poppler_bin_yolu_bul():
    """Windows'ta pdf2image'in ihtiyac duydugu Poppler (pdftoppm.exe)
    icin yaygin kurulum konumlarini tarar. Bulunursa bin klasor yolunu,
    bulunamazsa None doner (bu durumda PATH'e guvenilir)."""
    if os.name != "nt":
        return None

    def _klasorde_ara(kok):
        for alt in (kok, os.path.join(kok, "bin"), os.path.join(kok, "Library", "bin")):
            if os.path.exists(os.path.join(alt, "pdftoppm.exe")):
                return alt
        return None

    # PyInstaller ile paketlendiginde Poppler _MEIPASS/poppler/bin altinda olur
    import sys as _sys
    _meipass = getattr(_sys, "_MEIPASS", None)
    if _meipass:
        bulundu = _klasorde_ara(os.path.join(_meipass, "poppler"))
        if bulundu:
            return bulundu

    olasi_kokler = [
        r"C:\Program Files\poppler",
        r"C:\Program Files\poppler-windows",
        r"C:\poppler",
        r"C:\Users\{}\poppler".format(os.environ.get("USERNAME", "")),
        r"C:\Users\{}\Downloads\poppler".format(os.environ.get("USERNAME", "")),
    ]
    for kok in olasi_kokler:
        if not os.path.isdir(kok):
            continue
        bulundu = _klasorde_ara(kok)
        if bulundu:
            return bulundu
        try:
            for ad in os.listdir(kok):
                bulundu = _klasorde_ara(os.path.join(kok, ad))
                if bulundu:
                    return bulundu
        except OSError:
            pass

    taranacak_kokler = [r"C:\\", r"C:\Users\{}".format(os.environ.get("USERNAME", ""))]
    for taranacak in taranacak_kokler:
        try:
            for ad in os.listdir(taranacak):
                if ad.lower().startswith("poppler"):
                    bulundu = _klasorde_ara(os.path.join(taranacak, ad))
                    if bulundu:
                        return bulundu
        except OSError:
            pass

    return None


_POPPLER_BIN_YOLU = _poppler_bin_yolu_bul() if OCR_KULLANILABILIR else None


def pdf_text_oku(dosya_yolu, max_sayfa=None):
    """PDF'ten metin cikarir. max_sayfa verilirse sadece ilk N sayfa okunur.
    Normal yontemle (gomulu metin katmani) hic metin cikmazsa, OCR
    kutuphaneleri kuruluysa otomatik olarak OCR denenir (sadece ilk
    OCR_MAX_SAYFA sayfa, performans icin)."""
    metin = ""
    with pdfplumber.open(dosya_yolu) as pdf:
        sayfalar = pdf.pages if max_sayfa is None else pdf.pages[:max_sayfa]
        for sayfa in sayfalar:
            metin += "\n" + (sayfa.extract_text() or "")
    metin = metin.strip()

    if not metin and OCR_KULLANILABILIR:
        try:
            metin = pdf_text_oku_ocr(dosya_yolu)
        except Exception:
            pass

    return metin


def pdf_text_oku_ocr(dosya_yolu):
    """Taranmis/resim tabanli PDF'lerden OCR ile metin cikarir.
    Sadece pdf_text_oku() normal yontemle hic metin bulamadiginda
    cagrilir. Performans icin sadece ilk OCR_MAX_SAYFA sayfa islenir."""
    if not OCR_KULLANILABILIR:
        return ""
    sayfalar = _ocr_pdf_to_images(
        dosya_yolu, dpi=OCR_DPI, first_page=1, last_page=OCR_MAX_SAYFA,
        poppler_path=_POPPLER_BIN_YOLU,
    )
    metin = ""
    for sayfa_resmi in sayfalar:
        try:
            metin += "\n" + _ocr_engine.image_to_string(sayfa_resmi, lang="eng+tur")
        except Exception:
            # Turkce dil paketi kurulu degilse sadece ingilizce ile dene
            try:
                metin += "\n" + _ocr_engine.image_to_string(sayfa_resmi, lang="eng")
            except Exception:
                pass
    return metin.strip()


def plaka_bul(metin):
    m = TURK_PLAKA_RE.search(metin.upper())
    return temizle_ad(m.group(0).replace(" ", "")) if m else ""


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
    return adaylar[0] if adaylar else ""


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

    m = re.search(r"TO\s+([A-ZÇĞİÖŞÜ]{2,}\s+[A-ZÇĞİÖŞÜ]{2,}(?:\s+[A-ZÇĞİÖŞÜ]{2,})?)", buyuk)
    if m:
        isim = m.group(1).strip()
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
def belge_turu_bul(metin, dosya_adi="", ozel_kelimeler=None):
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

    # ── T9 (birlesik): gecici belge / muayene sertifikasi / ana onay belgesi ──
    if not _override_edilmis("T9"):
        if ("GEÇİCİ" in m or "GECICI" in m or
            "TEMPORARY" in m or "PROVISIONAL" in m or "INTERIM" in m or
            "23 İŞ GÜNÜ" in m or "23 IS GUNU" in m or "23 WORKING DAY" in m) and (
            "T9" in m or "ADR" in m or "UYGUNLUK" in m or "ONAY" in m):
            return "T9"

        if ("MUAYENE SERTIFIKASI" in m or "MUAYENE SERTİFİKASI" in m) and (
            sasi_bul(m) or "ŞASİ" in m or "SASI NO" in m or "VIN" in m
        ) and (
            kapasite_bul(m) or "KAPASİTE" in m or "KAPASITE" in m or "LİTRE" in m or "LITRE" in m
        ):
            return "T9"

        if ("BELİRLİ TEHLİKELİ MADDELER TAŞIYAN ARAÇLAR İÇİN ONAY SERTİFİKASI" in m or
            "BELIRLI TEHLIKELI MADDELER TASIYAN ARACLAR ICIN ONAY SERTIFIKASI" in m or
            "CERTIFICATE OF APPROVAL FOR VEHICLES CARRYING CERTAIN DANGEROUS GOODS" in m or
            "TAŞIT UYGUNLUK" in m or "TASIT UYGUNLUK" in m or "ADR UYGUNLUK" in m or
            "TANK BİLGİLERİ" in m or "TANK BILGILERI" in m or
            "TANK KODU" in m or "TASIMA BIRIM TIPI" in m or "TAŞIMA BIRIM TIPI" in m or
            bool(re.search(r"\bUN\s*\d{4}\b", m)) or
            # INSPECTION CERTIFICATE: arac/ADR onayi olanlar T9;
            # Tank basinc raporlari (BV, Lloyd's Register, IIC vb.) bu T9
            # kurali tarafindan yakalanmasin, TANK BASINC RAPORU kurali yakalasin.
            ("INSPECTION CERTIFICATE" in m and ("TANK" in m or "CONTAINER" in m or "ADR" in m)
             and not ("TANK CONTAINER" in m and ("PORTABLE TANK" in m or
                      "INITIAL INSPECTION CERTIFICATE" in m or
                      "PERIODIC INSPECTION REPORT" in m or
                      "LLOYD" in m or "BUREAU VERITAS" in m or
                      "NEW CONSTRUCTION" in m))) or
            ("T9" in m and ("ADR" in m or "ONAY SERTIFIKA" in m or "ONAY SERTİFİKA" in m or
                              "UYGUNLUK BELGE" in m or "APPROVAL" in m))):
            return "T9"

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
    """Dosya elle duzeltme kodu ile mi isaretli? (E veya eski PRGT)
    Bu dosyalarin ICERIGI BIR DAHA OKUNMAZ; sadece konumu kontrol edilir."""
    return _son_token(dosya_adi) in ({ELLE_DUZELT_KODU} | ESKI_ELLE_DUZELT_KODLARI)


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
    for klasor in BELGE_KLASORLERI.values():
        (arsiv / klasor).mkdir(exist_ok=True)
    for d in ("FARKLI FORMAT DOSYALAR", "OKUNAMAYAN PDF", "ISLEM RAPORLARI"):
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


def dosya_tasi(kaynak, hedef_klasor, yeni_ad=None):
    """Dosyayi hedef klasore tasir. Hedef yol zaten kaynagin kendisiyse hicbir
    sey yapilmaz (zaten dogru yerde/isimde)."""
    with _TASIMA_KILIDI:
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


def bilgi_cek(metin, dosya_adi="", ozel_kelimeler=None):
    tur = belge_turu_bul(metin, dosya_adi, ozel_kelimeler)
    dosya_bilgisi = bilgi_dosya_adindan(dosya_adi)
    return {
        "plaka": plaka_bul(metin) or dosya_bilgisi.get("plaka", ""),
        "tank_no": tank_no_bul(metin) or dosya_bilgisi.get("tank_no", ""),
        "sasi": sasi_bul(metin) or dosya_bilgisi.get("sasi", ""),
        "yabanci_plaka": yabanci_plaka_bul(metin) or dosya_bilgisi.get("yabanci_plaka", ""),
        "tarih": en_mantikli_tarih(metin, tur) or dosya_bilgisi.get("tarih", ""),
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

    if tur == "ISOPA":
        kimlik = bilgi.get("surucu") or temizle_ad(Path(eski_ad).stem, 40)
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
def dosya_isle(dosya_yolu, ana_klasor, ozel_kelimeler=None):
    """ozel_kelimeler verilmezse, ana_klasor icin kayitli kullanici tanimli
    anahtar kelimeler otomatik olarak diskten okunur (performans icin toplu
    islemlerde bu sozluk bir kere okunup tum dosyalara aynen gecirilir)."""
    if ozel_kelimeler is None:
        ozel_kelimeler = anahtar_kelimeleri_oku(ana_klasor)
    kaynak = Path(dosya_yolu)
    arsiv = klasorleri_hazirla(ana_klasor)
    eski_ad, uzanti = kaynak.name, kaynak.suffix.lower()

    sonuc = {
        "Eski Dosya Adı": eski_ad, "Yeni Dosya Adı": "", "Belge Türü": "", "Plaka": "", "Tank No": "",
        "Şasi No": "", "Yabancı Plaka": "", "Geçerlilik Tarihi": "", "Kapasite": "", "Tank Kodu": "",
        "Sürücü": "", "Bulunduğu Klasör": str(kaynak.parent), "Yeni Klasör": "", "İşlem Durumu": "",
        "Hata": "", "İşlem Tarihi": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
    }

    try:
        if kaynak.name.startswith("~$"):
            sonuc["İşlem Durumu"] = "GECICI DOSYA ATLANDI"
            return sonuc

        if "ISLEM RAPORLARI" in str(kaynak.parent):
            sonuc["İşlem Durumu"] = "RAPOR ATLANDI"
            return sonuc

        # ── PDF DEGIL: FARKLI_FORMAT_DOSYALAR'a tasi, hic okuma ────────────
        if uzanti not in PDF_EXT:
            hedef = ana_klasor_path(ana_klasor) / "FARKLI FORMAT DOSYALAR"
            yeni_yol = dosya_tasi(kaynak, hedef)
            sonuc.update({
                "Belge Türü": "FARKLI FORMAT DOSYALAR",
                "Yeni Dosya Adı": yeni_yol.name,
                "Yeni Klasör": str(yeni_yol.parent),
                "İşlem Durumu": "FARKLI FORMAT TASINDI",
            })
            return sonuc

        # ── E (elle duzeltilmis): ICERIK OKUNMAZ, sadece konum kontrolu ────
        if _elle_duzeltilmis_mi(kaynak.name):
            tur = belge_turu_dosya_adindan(kaynak.name) or "DIGER BELGELER"
            hedef_klasor = arsiv / BELGE_KLASORLERI.get(tur, "DIGER BELGELER")
            sonuc["Belge Türü"] = tur

            # Eski "PRGT" kodunu yeni "E" koduna cevir
            yeni_ad = kaynak.name if _son_token(kaynak.name) == ELLE_DUZELT_KODU else _kod_degistir(kaynak.name, ELLE_DUZELT_KODU)

            if kaynak.parent.resolve() != hedef_klasor.resolve() or yeni_ad != kaynak.name:
                yeni_yol = dosya_tasi(kaynak, hedef_klasor, yeni_ad)
                sonuc["Yeni Dosya Adı"] = yeni_yol.name
                sonuc["Yeni Klasör"] = str(yeni_yol.parent)
                sonuc["İşlem Durumu"] = "ELLEDUZ TASINDI"
            else:
                sonuc["Yeni Dosya Adı"] = kaynak.name
                sonuc["Yeni Klasör"] = str(kaynak.parent)
                sonuc["İşlem Durumu"] = "ELLEDUZ DOGRU YERDE"
            return sonuc

        # ── P (otomatik islenmis): ICERIK OKUNMAZ, sadece konum kontrolu ───
        if _islenmis_mi(kaynak.name):
            tur = belge_turu_dosya_adindan(kaynak.name)
            if not tur:
                sonuc["İşlem Durumu"] = "ATLANDI TUR BULUNAMADI"
                return sonuc

            hedef_klasor = arsiv / BELGE_KLASORLERI.get(tur, "DIGER BELGELER")
            sonuc["Belge Türü"] = tur

            # Eski "S"/"PRGTOK" kodunu yeni "P" koduna cevir
            yeni_ad = kaynak.name if _son_token(kaynak.name) == ISLEM_KODU else _kod_degistir(kaynak.name, ISLEM_KODU)

            if kaynak.parent.resolve() != hedef_klasor.resolve() or yeni_ad != kaynak.name:
                yeni_yol = dosya_tasi(kaynak, hedef_klasor, yeni_ad)
                sonuc["Yeni Dosya Adı"] = yeni_yol.name
                sonuc["Yeni Klasör"] = str(yeni_yol.parent)
                sonuc["İşlem Durumu"] = "YER DUZELTILDI"
            else:
                sonuc["Yeni Dosya Adı"] = kaynak.name
                sonuc["Yeni Klasör"] = str(kaynak.parent)
                sonuc["İşlem Durumu"] = "ATLANDI ZATEN ISLENMIS"
            return sonuc

        # ── KOD YOK: PDF icerigini oku, turu bul, yeniden adlandir ─────────
        try:
            metin = pdf_text_oku(str(kaynak), max_sayfa=6)
        except Exception as e:
            metin = ""
            sonuc["Hata"] = f"OKUMA_HATASI: {e}"

        tur = belge_turu_bul(metin, eski_ad, ozel_kelimeler)

        # Ilk sayfalarda yeterli bilgi yoksa PDF'in tamamini oku
        if tur == "DIGER BELGELER" and not yabanci_plaka_bul(metin):
            try:
                metin_tam = pdf_text_oku(str(kaynak))
                if len(metin_tam) > len(metin):
                    metin = metin_tam
                    tur = belge_turu_bul(metin, eski_ad, ozel_kelimeler)
            except Exception:
                pass

        bilgi = bilgi_cek(metin, eski_ad, ozel_kelimeler)

        # Metin hic okunamadiysa -> OKUNAMAYAN_PDF klasorune at (isim degismez)
        if not metin and tur == "DIGER BELGELER":
            hedef = ana_klasor_path(ana_klasor) / "OKUNAMAYAN PDF"
            yeni_yol = dosya_tasi(kaynak, hedef)
            sonuc.update({
                "Belge Türü": "OKUNAMAYAN PDF",
                "Yeni Dosya Adı": yeni_yol.name,
                "Yeni Klasör": str(yeni_yol.parent),
                "İşlem Durumu": "OKUNAMADI TASINDI",
            })
            return sonuc

        yeni_ad = yeni_dosya_adi_olustur(tur, bilgi, eski_ad, uzanti)
        yeni_yol = dosya_tasi(kaynak, arsiv / BELGE_KLASORLERI.get(tur, "DIGER BELGELER"), yeni_ad)

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
            "İşlem Durumu": "OKUNDU TASINDI",
        })
        return sonuc

    except Exception as e:
        sonuc["İşlem Durumu"] = "HATA"
        sonuc["Hata"] = str(e)
        return sonuc


def ana_klasor_path(ana_klasor):
    return Path(ana_klasor)


# ----------------------------------------------------------------------------
# TARAMA (klasor agaci uzerinde calisir)
# ----------------------------------------------------------------------------
def klasor_tara(ana_klasor, log_callback=None, progress_callback=None):
    """progress_callback(islenen, toplam) seklinde cagrilir; arayuzde
    ilerleme cubugu / 'X/Y dosya islendi' bilgisini gostermek icin kullanilir."""
    arsiv = klasorleri_hazirla(ana_klasor)
    sonuclar = []
    ana = Path(ana_klasor)

    # Tarama sirasinda atlanan ozel klasorler
    ATLA_KLASORLER = {"OKUNAMAYAN PDF", "ISLEM RAPORLARI"}

    dosya_listesi = []
    for root, dirs, files in os.walk(ana):
        root_path = Path(root)
        if any(p in ATLA_KLASORLER for p in root_path.parts):
            dirs[:] = []
            continue
        for file in files:
            yol = root_path / file
            if yol.name.startswith("~$"):
                continue
            dosya_listesi.append(yol)

    toplam = len(dosya_listesi)
    islenen_sayac = {"n": 0}
    sayac_kilidi = threading.Lock()
    ozel_kelimeler = anahtar_kelimeleri_oku(ana_klasor)

    def _ilerleme_bildir():
        with sayac_kilidi:
            islenen_sayac["n"] += 1
            n = islenen_sayac["n"]
        if progress_callback:
            progress_callback(n, toplam)

    if toplam > 1:
        max_worker = min(4, max(1, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=max_worker) as ex:
            future_map = {ex.submit(dosya_isle, str(yol), ana_klasor, ozel_kelimeler): yol for yol in dosya_listesi}
            for fut in as_completed(future_map):
                sonuc = fut.result()
                sonuclar.append(sonuc)
                _ilerleme_bildir()
                if log_callback:
                    log_callback(f"{sonuc['İşlem Durumu']}: {sonuc['Eski Dosya Adı']} -> {sonuc.get('Yeni Dosya Adı', '')}")
    else:
        for yol in dosya_listesi:
            sonuc = dosya_isle(str(yol), ana_klasor, ozel_kelimeler)
            sonuclar.append(sonuc)
            _ilerleme_bildir()
            if log_callback:
                log_callback(f"{sonuc['İşlem Durumu']}: {sonuc['Eski Dosya Adı']} -> {sonuc.get('Yeni Dosya Adı', '')}")

    df = pd.DataFrame(sonuclar)
    rapor_klasor = ana / "ISLEM RAPORLARI"
    rapor_klasor.mkdir(exist_ok=True)
    # Rapor adi: gun ve saat bilgisiyle (ornek: ISLEM_RAPORU_16-06-2026_09-04-12.xlsx)
    rapor_adi = f"ISLEM RAPORU {datetime.now().strftime('%d-%m-%Y %H-%M-%S')}.xlsx"
    if not df.empty:
        df.to_excel(rapor_klasor / rapor_adi, index=False)
        df.to_excel(rapor_klasor / "ARSIV INDEX.xlsx", index=False)
    _son_tarama_bilgisini_kaydet(ana_klasor, toplam)
    return df


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
    """OKUNAMAYAN_PDF klasorundeki dosyalari (P/E kodlari silinerek) tekrar
    icerikten okumaya zorlar. FARKLI_FORMAT_DOSYALAR'a dokunmaz (PDF degil)."""
    ana = Path(ana_klasor)
    okunamayan = ana / "OKUNAMAYAN PDF"
    sonuclar = []
    ozel_kelimeler = anahtar_kelimeleri_oku(ana_klasor)

    dosya_listesi = []
    if okunamayan.exists():
        dosya_listesi = [d for d in okunamayan.iterdir() if d.is_file() and d.suffix.lower() in PDF_EXT]

    toplam = len(dosya_listesi)
    for i, dosya in enumerate(dosya_listesi, start=1):
        sonuc = dosya_isle(str(dosya), ana_klasor, ozel_kelimeler)
        sonuclar.append(sonuc)
        if log_callback:
            log_callback(f"{sonuc['İşlem Durumu']}: {sonuc['Eski Dosya Adı']} -> {sonuc.get('Yeni Dosya Adı', '')}")
        if progress_callback:
            progress_callback(i, toplam)

    df = pd.DataFrame(sonuclar)
    if not df.empty:
        rapor_klasor = ana / "ISLEM RAPORLARI"
        rapor_klasor.mkdir(exist_ok=True)
        rapor_adi = f"OKUNAMAYAN TEKRAR DENE {datetime.now().strftime('%d-%m-%Y %H-%M-%S')}.xlsx"
        df.to_excel(rapor_klasor / rapor_adi, index=False)
    return df


def tum_dosyalari_yeniden_tara(ana_klasor, log_callback=None, progress_callback=None):
    """TUM PDF dosyalarini (P/E kodu olsa da) iceriklerinden yeniden okur ve
    yeniden siniflandirir. Eski T9 alt klasorlerini birlesik T9'a tasir."""
    ana = Path(ana_klasor)
    arsiv = klasorleri_hazirla(ana_klasor)
    sonuclar = []
    ozel_kelimeler = anahtar_kelimeleri_oku(ana_klasor)

    ATLA_KLASORLER = {"FARKLI FORMAT DOSYALAR", "ISLEM RAPORLARI"}

    dosya_listesi = []
    for root, dirs, files in os.walk(ana):
        root_path = Path(root)
        if any(p in ATLA_KLASORLER for p in root_path.parts):
            dirs[:] = []
            continue
        for file in files:
            yol = root_path / file
            if yol.name.startswith("~$"):
                continue
            if yol.suffix.lower() in PDF_EXT:
                dosya_listesi.append(yol)

    def yeniden_isle(dosya_yolu):
        """Kod kontrolu yapmadan, dogrudan icerikten okuyup yeniden adlandirir."""
        kaynak = Path(dosya_yolu)
        eski_ad, uzanti = kaynak.name, kaynak.suffix.lower()
        sonuc = {
            "Eski Dosya Adı": eski_ad, "Yeni Dosya Adı": "", "Belge Türü": "", "Plaka": "", "Tank No": "",
            "Şasi No": "", "Yabancı Plaka": "", "Geçerlilik Tarihi": "", "Kapasite": "", "Tank Kodu": "",
            "Sürücü": "", "Bulunduğu Klasör": str(kaynak.parent), "Yeni Klasör": "", "İşlem Durumu": "",
            "Hata": "", "İşlem Tarihi": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        }
        try:
            # E kodluysa icerik yine de zorla okunur (bu fonksiyonun amaci budur)
            try:
                metin = pdf_text_oku(str(kaynak))
            except Exception as e:
                metin = ""
                sonuc["Hata"] = f"OKUMA_HATASI: {e}"

            tur = belge_turu_bul(metin, eski_ad, ozel_kelimeler)
            bilgi = bilgi_cek(metin, eski_ad, ozel_kelimeler)

            if not metin and tur == "DIGER BELGELER":
                hedef = ana / "OKUNAMAYAN PDF"
                yeni_yol = dosya_tasi(kaynak, hedef)
                sonuc.update({
                    "Belge Türü": "OKUNAMAYAN PDF",
                    "Yeni Dosya Adı": yeni_yol.name,
                    "Yeni Klasör": str(yeni_yol.parent),
                    "İşlem Durumu": "OKUNAMADI TASINDI",
                })
                return sonuc

            # Onceden E ile isaretliyse, yeniden taramada da E olarak kalsin
            korunacak_kod = ELLE_DUZELT_KODU if _elle_duzeltilmis_mi(eski_ad) else ISLEM_KODU
            yeni_ad = yeni_dosya_adi_olustur(tur, bilgi, eski_ad, uzanti)
            if korunacak_kod == ELLE_DUZELT_KODU:
                yeni_ad = _kod_degistir(yeni_ad, ELLE_DUZELT_KODU)

            yeni_yol = dosya_tasi(kaynak, arsiv / BELGE_KLASORLERI.get(tur, "DIGER BELGELER"), yeni_ad)
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
                "İşlem Durumu": "YENIDEN TARANDI",
            })
            return sonuc
        except Exception as e:
            sonuc["İşlem Durumu"] = "HATA"
            sonuc["Hata"] = str(e)
            return sonuc

    toplam = len(dosya_listesi)
    islenen_sayac = {"n": 0}
    sayac_kilidi = threading.Lock()

    def _ilerleme_bildir():
        with sayac_kilidi:
            islenen_sayac["n"] += 1
            n = islenen_sayac["n"]
        if progress_callback:
            progress_callback(n, toplam)

    if toplam > 1:
        max_worker = min(4, max(1, os.cpu_count() or 1))
        with ThreadPoolExecutor(max_workers=max_worker) as ex:
            future_map = {ex.submit(yeniden_isle, yol): yol for yol in dosya_listesi}
            for fut in as_completed(future_map):
                sonuc = fut.result()
                sonuclar.append(sonuc)
                _ilerleme_bildir()
                if log_callback:
                    log_callback(f"{sonuc['İşlem Durumu']}: {sonuc['Eski Dosya Adı']} -> {sonuc.get('Yeni Dosya Adı', '')}")
    else:
        for yol in dosya_listesi:
            sonuc = yeniden_isle(yol)
            sonuclar.append(sonuc)
            _ilerleme_bildir()
            if log_callback:
                log_callback(f"{sonuc['İşlem Durumu']}: {sonuc['Eski Dosya Adı']} -> {sonuc.get('Yeni Dosya Adı', '')}")

    # Eski T9 alt klasorleri bossa sil
    for eski_ad in ESKI_T9_TURLERI:
        eski_klasor = arsiv / eski_ad
        if eski_klasor.exists() and eski_klasor.is_dir():
            try:
                if not any(eski_klasor.iterdir()):
                    eski_klasor.rmdir()
            except OSError:
                pass

    df = pd.DataFrame(sonuclar)
    if not df.empty:
        rapor_klasor = ana / "ISLEM RAPORLARI"
        rapor_klasor.mkdir(exist_ok=True)
        rapor_adi = f"TUMUNU YENIDEN TARA {datetime.now().strftime('%d-%m-%Y %H-%M-%S')}.xlsx"
        df.to_excel(rapor_klasor / rapor_adi, index=False)
        df.to_excel(rapor_klasor / "ARSIV INDEX.xlsx", index=False)
    _son_tarama_bilgisini_kaydet(ana_klasor, toplam)
    return df


# ----------------------------------------------------------------------------
# OZET SAYILAR (dashboard kartlari icin)
# ----------------------------------------------------------------------------
def ozet_sayilar(ana_klasor):
    ana = Path(ana_klasor)
    arsiv = ana / "PREGATE ARSIV"
    ozet = {"TOPLAM": 0}

    for tur, klasor_adi in BELGE_KLASORLERI.items():
        klasor = arsiv / klasor_adi
        sayi = len(list(klasor.glob("*.pdf"))) if klasor.exists() else 0
        ozet[tur] = ozet.get(tur, 0) + sayi
        ozet["TOPLAM"] += sayi

    farkli_format = ana / "FARKLI FORMAT DOSYALAR"
    ozet["FARKLI FORMAT DOSYALAR"] = len(list(farkli_format.iterdir())) if farkli_format.exists() else 0

    okunamayan = ana / "OKUNAMAYAN PDF"
    ozet["OKUNAMAYAN PDF"] = len(list(okunamayan.glob("*.pdf"))) if okunamayan.exists() else 0

    return ozet


# ----------------------------------------------------------------------------
# ARAMA
# ----------------------------------------------------------------------------
def arama_yap(ana_klasor, sorgu):
    index_yolu = Path(ana_klasor) / "ISLEM RAPORLARI" / "ARSIV INDEX.xlsx"
    if not index_yolu.exists():
        return pd.DataFrame()

    df = pd.read_excel(index_yolu).fillna("")

    def _tam_yol(row):
        klasor = str(row.get("Yeni Klasör", "")).strip()
        ad = str(row.get("Yeni Dosya Adı", "")).strip()
        return os.path.join(klasor, ad) if klasor and ad else ""

    df["Tam Yol"] = df.apply(_tam_yol, axis=1)

    if not sorgu:
        return df

    q = temizle_ad(sorgu).replace("_", "")

    def satirda_var(row):
        alan = " ".join(str(x) for x in row.values).upper()
        alan_temiz = temizle_ad(alan).replace("_", "")
        return q in alan_temiz

    return df[df.apply(satirda_var, axis=1)]
