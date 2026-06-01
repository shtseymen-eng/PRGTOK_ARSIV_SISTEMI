# PRGTOK motor.py - ISOPA isim düzeltmeli güncel sürüm
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber

ISLEM_KODU = "PRGTOK"

BELGE_KLASORLERI = {
    "TANK_BASINC_RAPORU": "TANK_BASINC_RAPORU",
    "ISOPA": "ISOPA",
    "T9_MUAYENE_SERTIFIKASI": "T9_MUAYENE_SERTIFIKASI",
    "TRAFIK_SIGORTASI": "TRAFIK_SIGORTASI",
    "TEHLIKELI_MADDE_SIGORTASI": "TEHLIKELI_MADDE_SIGORTASI",
    "FENNI_MUAYENE": "FENNI_MUAYENE",
    "SIZDIRMAZLIK": "SIZDIRMAZLIK",
    "YUKSEKTE_CALISABILIR_SAGLIK_RAPORU": "YUKSEKTE_CALISABILIR_SAGLIK_RAPORU",
    "YABANCI_PLAKA": "YABANCI_PLAKA",
    "DIGER_BELGELER": "DIGER_BELGELER",
    "OKUNAMAYANLAR": "OKUNAMAYANLAR",
    "FARKLI_FORMAT_DOSYALAR": "FARKLI_FORMAT_DOSYALAR",
    "ISLEM_RAPORLARI": "ISLEM_RAPORLARI",
}

PDF_EXT = {".pdf"}

TURK_PLAKA_RE = re.compile(r"\b(0[1-9]|[1-7][0-9]|8[01])\s*[A-ZÇĞİÖŞÜ]{1,3}\s*\d{2,4}\b", re.I)
TANK_NO_RE = re.compile(r"\b[A-Z]{4}\s?\d{6}[-\s]?\d\b", re.I)
SASI_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
DATE_RE_LIST = [
    re.compile(r"\b(\d{2})[./-](\d{2})[./-](\d{4})\b"),
    re.compile(r"\b(\d{4})[./-](\d{2})[./-](\d{2})\b"),
]
EN_DATE_RE = re.compile(r"\b(\d{1,2})[-\s](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[-\s](\d{2,4})\b", re.I)
CAPACITY_RE = re.compile(r"\b(\d{2,3}[\.,]?\d{3}|\d{4,6})\s*(?:LT|LITRE|LITER|L)\b", re.I)
YABANCI_PLAKA_ADAY_RE = re.compile(r"\b[A-Z]{1,3}\s?\d{2,5}\s?[A-Z]{1,3}\b|\b[A-Z]{2}\s?\d{3,6}\b|\b\d{3,6}\s?[A-Z]{2,4}\b", re.I)


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
            return f"{gun}-{ay}-{yil}"
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
    return f"{gun.zfill(2)}-{aylar.get(ay.upper(), '00')}-{yil}"


def dnv_next_due_bul(metin):
    for pattern in [
        r"DATE\s+NEXT\s+INSPECTION\s+DUE\s*[:\-]?\s*(0?[1-9]|1[0-2])[/.-](\d{2})",
        r"NEXT\s+INSPECTION\s+DUE\s*[:\-]?\s*(0?[1-9]|1[0-2])[/.-](\d{2})",
    ]:
        m = re.search(pattern, metin.upper())
        if m:
            ay, yil = m.groups()
            return f"{ay.zfill(2)}-20{yil}"
    return ""


def tse_next_inspection_bul(metin):
    m = re.search(r"SONRAKI\s+MUAYENE.*?(\d{2})[/.-](20\d{2})", metin.upper(), re.S)
    if not m:
        m = re.search(r"NEXT\s+INSPECTION.*?(\d{2})[/.-](20\d{2})", metin.upper(), re.S)
    if m:
        ay, yil = m.groups()
        return f"{ay}-{yil}"
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
    if tur == "TANK_BASINC_RAPORU":
        x = dnv_next_due_bul(metin)
        if x:
            return x
    if tur == "T9_MUAYENE_SERTIFIKASI":
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
        normal = [x for x in tarihler if re.match(r"\d{2}-\d{2}-\d{4}", x)]
        sirali = sorted(set(normal), key=lambda x: datetime.strptime(x, "%d-%m-%Y"))
        return sirali[-1] if sirali else tarihler[-1]
    except Exception:
        return tarihler[-1]


def klasorleri_hazirla(ana_klasor):
    arsiv = Path(ana_klasor) / "PREGATE_ARSIV"
    arsiv.mkdir(exist_ok=True)
    for klasor in BELGE_KLASORLERI.values():
        (arsiv / klasor).mkdir(exist_ok=True)
    return arsiv


def pdf_text_oku(dosya_yolu):
    metin = ""
    with pdfplumber.open(dosya_yolu) as pdf:
        for sayfa in pdf.pages:
            metin += "\n" + (sayfa.extract_text() or "")
    return metin.strip()


def plaka_bul(metin):
    m = TURK_PLAKA_RE.search(metin.upper())
    return temizle_ad(m.group(0).replace(" ", "")) if m else ""


def tank_no_bul(metin):
    m = TANK_NO_RE.search(metin.upper())
    return temizle_ad(m.group(0).replace(" ", "").replace("--", "-")) if m else ""


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


def yabanci_plaka_bul(metin):
    temiz = TURK_PLAKA_RE.sub(" ", metin.upper())
    yasak = ("POL", "TANK", "ADR", "PDF", "DNV", "CSC", "RID", "IMDG", "DATE", "TEST",
             "NEXT", "OWNER", "SHELL", "GROSS", "PRESSURE", "CAPACITY", "INSPECTION",
             "SERIAL", "TSE", "ISOPA", "DRIVER", "CERTIFICATE")
    adaylar = []
    for m in YABANCI_PLAKA_ADAY_RE.finditer(temiz):
        aday = temizle_ad(m.group(0).replace(" ", ""))
        if 5 <= len(aday) <= 12 and not aday.startswith(yasak):
            adaylar.append(aday)
    return adaylar[0] if adaylar else ""


def surucu_adi_bul(metin, dosya_adi=""):
    metin_norm = (metin or "").replace("\u00a0", " ")
    buyuk = metin_norm.upper()

    # ISOPA özel okuma: isim, "certificate to" ile "under the supervision" arasında kalır.
    m = re.search(
        r"ISOPA\s+DELIVERED\s+THIS\s+CERTIFICATE\s+TO\s+(.+?)(?:UNDER\s+THE\s+SUPERVISION|DELIVERED\s+ON|EXPIRATION\s+DATE|CERTIFICATE\s+UNIQUE\s+NUMBER|$)",
        buyuk,
        re.S
    )
    if m:
        isim = m.group(1)
        isim = re.sub(r"[^A-ZÇĞİÖŞÜ\s]", " ", isim)
        isim = re.sub(r"\s+", " ", isim).strip()
        if anlamli_kimlik_mi(isim):
            return temizle_ad(isim)

    # Alternatif ISOPA: TO sonrası tek satır isim yakala.
    m = re.search(r"TO\s+([A-ZÇĞİÖŞÜ]{2,}\s+[A-ZÇĞİÖŞÜ]{2,}(?:\s+[A-ZÇĞİÖŞÜ]{2,})?)", buyuk)
    if m:
        isim = m.group(1).strip()
        if anlamli_kimlik_mi(isim):
            return temizle_ad(isim)

    # Sağlık raporu / genel sürücü adı
    m = re.search(r"(?:ADI\s*SOYADI|AD SOYAD|NAME\s*SURNAME)\s*[:\-]?\s*([A-ZÇĞİÖŞÜ ]{5,60})", buyuk)
    if m:
        isim = m.group(1).strip()
        if anlamli_kimlik_mi(isim):
            return temizle_ad(isim)

    # Dosya adından fallback: Nihat YILMAZ- ISOPA.pdf gibi
    stem = Path(dosya_adi).stem
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


def belge_turu_bul(metin, dosya_adi=""):
    m = (metin + "\n" + dosya_adi).upper()
    ad = dosya_adi.upper()

    if "YÇ" in ad or "YC" in ad or "YUKSEKTE" in m or "YÜKSEKTE" in m:
        return "YUKSEKTE_CALISABILIR_SAGLIK_RAPORU"

    if ("TEHLIKELI MADDE" in m or "TEHLİKELİ MADDE" in m or "TEHLIKELI ATIK" in m or "TEHLİKELİ ATIK" in m) and "ZORUNLU MALI SORUMLULUK" in m:
        return "TEHLIKELI_MADDE_SIGORTASI"

    if ("MUAYENE SERTIFIKASI" in m or "MUAYENE SERTİFİKASI" in m or "INSPECTION CERTIFICATE" in m) and (
        "TANK BILGILERI" in m or "TANK BİLGİLERİ" in m or "TANK KODU" in m or
        "PORTABLE TANK INSTRUCTION" in m or "TASIMA BIRIM TIPI" in m or "TAŞIMA BIRIM TIPI" in m
    ):
        return "T9_MUAYENE_SERTIFIKASI"

    if ("BELİRLİ TEHLİKELİ MADDELER TAŞIYAN ARAÇLAR İÇİN ONAY SERTİFİKASI" in m or
        "BELIRLI TEHLIKELI MADDELER TASIYAN ARACLAR ICIN ONAY SERTIFIKASI" in m or
        "CERTIFICATE OF APPROVAL FOR VEHICLES CARRYING CERTAIN DANGEROUS GOODS" in m or
        "T9" in m or "TAŞIT UYGUNLUK" in m or "TASIT UYGUNLUK" in m or "ADR UYGUNLUK" in m):
        return "T9_MUAYENE_SERTIFIKASI"

    tank_ifadeleri = [
        "TANK CONTAINER PERIODIC INSPECTION REPORT", "PERIODIC INSPECTION REPORT", "DNV SILVER",
        "SILVER/CIMS", "DATE NEXT INSPECTION DUE", "NEXT INSPECTION DUE", "OWNER'S SERIAL NUMBER",
        "OWNERS SERIAL NUMBER", "OWNER S SERIAL NUMBER", "INITIAL HYDRO TEST", "LAST HYDRO TEST",
        "THIS INSPECTION", "INSPECTION DATES", "MAX GROSS WEIGHT", "TARE WEIGHT", "CAPACITY (L)",
        "TEST PRESSURE", "M.A.W.P", "MAWP", "ISO TYPE", "PRESSURE RELIEF VALVES",
    ]
    if any(x in m for x in tank_ifadeleri):
        return "TANK_BASINC_RAPORU"

    if tank_no_bul(m) and ("PRESSURE" in m or "BASINC" in m or "BASINÇ" in m or "HYDRO" in m or "TANK CONTAINER" in m):
        return "TANK_BASINC_RAPORU"

    if "ISOPA" in m or "TDI" in m or "MDI" in m:
        return "ISOPA"

    if "TRAFIK SIGORT" in m or "TRAFİK SİGORT" in m or "KARAYOLLARI MOTORLU" in m:
        return "TRAFIK_SIGORTASI"

    if "FENNI MUAYENE" in m or "FENNİ MUAYENE" in m or "ARAÇ MUAYENE RAPORU" in m or "ARAC MUAYENE RAPORU" in m or "VEHICLE INSPECTION REPORT" in m:
        return "FENNI_MUAYENE"

    if ("SIZDIRMAZLIK RAPORU" in m or "SIZDIRMAZLIK TEST RAPORU" in m or "KARA TANKERI SIZDIRMAZLIK TEST RAPORU" in m or
        "LEAKPROOFNESS TEST REPORT" in m or "LEAK PROOFNESS TEST REPORT" in m or "LEAKPROOFNESS CERTIFICATE" in m):
        return "SIZDIRMAZLIK"

    if yabanci_plaka_bul(m):
        return "YABANCI_PLAKA"

    return "DIGER_BELGELER"


def belge_turu_dosya_adindan(dosya_adi):
    ad = dosya_adi.upper()
    for tur in BELGE_KLASORLERI.keys():
        if tur != "ISLEM_RAPORLARI" and tur in ad:
            return tur
    if ISLEM_KODU in ad and YABANCI_PLAKA_ADAY_RE.search(ad) and not TURK_PLAKA_RE.search(ad):
        return "YABANCI_PLAKA"
    return ""


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
    hedef_klasor.mkdir(parents=True, exist_ok=True)
    hedef = benzersiz_yol(hedef_klasor / (yeni_ad if yeni_ad else kaynak.name))
    if kaynak.resolve() == hedef.resolve():
        return hedef
    shutil.move(str(kaynak), str(hedef))
    return hedef


def yeni_dosya_adi_olustur(tur, bilgi, eski_ad, uzanti):
    if tur == "ISOPA":
        kimlik = bilgi.get("surucu") or temizle_ad(Path(eski_ad).stem, 40)
    else:
        kimlik = (
            bilgi.get("tank_no") or bilgi.get("plaka") or bilgi.get("sasi") or
            bilgi.get("yabanci_plaka") or bilgi.get("surucu") or temizle_ad(Path(eski_ad).stem, 40)
        )

    if not anlamli_kimlik_mi(kimlik):
        kimlik = temizle_ad(Path(eski_ad).stem, 40)

    tarih = bilgi.get("tarih") or ""
    kapasite = bilgi.get("kapasite") or ""
    tank_kodu = bilgi.get("tank_kodu") or ""

    if tur == "YABANCI_PLAKA":
        parcalar = [bilgi.get("yabanci_plaka") or kimlik]
        if tarih:
            parcalar.append(tarih)
        parcalar.append(ISLEM_KODU)
        return temizle_ad("_".join(parcalar), 160) + uzanti.lower()

    parcalar = [kimlik]
    if tarih:
        parcalar.append(tarih)
    if kapasite and tur in ["TANK_BASINC_RAPORU", "T9_MUAYENE_SERTIFIKASI", "SIZDIRMAZLIK"]:
        parcalar.append(kapasite)
    if tank_kodu and tur == "T9_MUAYENE_SERTIFIKASI":
        parcalar.append(tank_kodu)
    parcalar.append(tur)
    parcalar.append(ISLEM_KODU)
    return temizle_ad("_".join(parcalar), 180) + uzanti.lower()


def bilgi_cek(metin, dosya_adi=""):
    tur = belge_turu_bul(metin, dosya_adi)
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
    }


def hatali_isopa_prgtok_mu(dosya_adi):
    ad = dosya_adi.upper()
    return ISLEM_KODU in ad and "_ISOPA_" in ad and (
        ad.startswith("ON_") or ad.startswith("DELIVERED_") or ad.startswith("BILGIYOK_") or ad.startswith("CERTIFICATE_")
    )


def dosya_isle(dosya_yolu, ana_klasor):
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
            sonuc["İşlem Durumu"] = "GECICI_DOSYA_ATLANDI"
            return sonuc

        if "ISLEM_RAPORLARI" in str(kaynak.parent):
            sonuc["İşlem Durumu"] = "RAPOR_ATLANDI"
            return sonuc

        # PRGTOK dosyaları normalde okunmaz.
        # Ama ON_..._ISOPA_PRGTOK gibi hatalı eski ISOPA isimlerini yeniden okuyup düzeltir.
        if ISLEM_KODU in kaynak.name.upper() and not hatali_isopa_prgtok_mu(kaynak.name):
            tur = belge_turu_dosya_adindan(kaynak.name)
            if not tur:
                sonuc["İşlem Durumu"] = "ATLANDI_PRGTOK_TUR_BULUNAMADI"
                return sonuc

            hedef_klasor = arsiv / BELGE_KLASORLERI.get(tur, "DIGER_BELGELER")
            sonuc["Belge Türü"] = tur

            if kaynak.parent.resolve() != hedef_klasor.resolve():
                yeni_yol = dosya_tasi(kaynak, hedef_klasor)
                sonuc["Yeni Dosya Adı"] = yeni_yol.name
                sonuc["Yeni Klasör"] = str(yeni_yol.parent)
                sonuc["İşlem Durumu"] = "YER_DUZELTILDI_PRGTOK"
            else:
                sonuc["Yeni Dosya Adı"] = kaynak.name
                sonuc["Yeni Klasör"] = str(kaynak.parent)
                sonuc["İşlem Durumu"] = "ATLANDI_PRGTOK"
            return sonuc

        if uzanti not in PDF_EXT:
            yeni_yol = dosya_tasi(kaynak, arsiv / "FARKLI_FORMAT_DOSYALAR")
            sonuc.update({
                "Belge Türü": "FARKLI_FORMAT_DOSYALAR",
                "Yeni Dosya Adı": yeni_yol.name,
                "Yeni Klasör": str(yeni_yol.parent),
                "İşlem Durumu": "FARKLI_FORMAT_TASINDI"
            })
            return sonuc

        try:
            metin = pdf_text_oku(str(kaynak))
        except Exception as e:
            metin = ""
            sonuc["Hata"] = f"PDF_OKUMA_HATASI: {e}"

        tur = belge_turu_bul(metin, eski_ad)
        bilgi = bilgi_cek(metin, eski_ad)

        # Metin az diye hemen okunamadı deme. Önce tür ve dosya adından bilgi bulmaya çalış.
        if not metin and tur == "DIGER_BELGELER":
            yeni_ad = temizle_ad(f"OKUNAMADI_{kaynak.stem}_{ISLEM_KODU}", 160) + uzanti
            yeni_yol = dosya_tasi(kaynak, arsiv / "OKUNAMAYANLAR", yeni_ad)
            sonuc.update({
                "Belge Türü": "OKUNAMAYANLAR",
                "Yeni Dosya Adı": yeni_yol.name,
                "Yeni Klasör": str(yeni_yol.parent),
                "İşlem Durumu": "OKUNAMADI_TASINDI"
            })
            return sonuc

        yeni_ad = yeni_dosya_adi_olustur(tur, bilgi, eski_ad, uzanti)
        yeni_yol = dosya_tasi(kaynak, arsiv / BELGE_KLASORLERI.get(tur, "DIGER_BELGELER"), yeni_ad)

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
            "İşlem Durumu": "OKUNDU_TASINDI",
        })
        return sonuc

    except Exception as e:
        sonuc["İşlem Durumu"] = "HATA"
        sonuc["Hata"] = str(e)
        return sonuc


def klasor_tara(ana_klasor, log_callback=None):
    arsiv = klasorleri_hazirla(ana_klasor)
    sonuclar = []
    ana = Path(ana_klasor)

    for root, dirs, files in os.walk(ana):
        root_path = Path(root)
        if "ISLEM_RAPORLARI" in root_path.parts:
            continue

        for file in files:
            yol = root_path / file
            if yol.name.startswith("~$"):
                continue

            sonuc = dosya_isle(str(yol), ana_klasor)
            sonuclar.append(sonuc)

            if log_callback:
                log_callback(f"{sonuc['İşlem Durumu']}: {sonuc['Eski Dosya Adı']} -> {sonuc.get('Yeni Dosya Adı', '')}")

    df = pd.DataFrame(sonuclar)
    rapor_adi = f"ISLEM_RAPORU_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(arsiv / "ISLEM_RAPORLARI" / rapor_adi, index=False)
    df.to_excel(arsiv / "ISLEM_RAPORLARI" / "ARSIV_INDEX.xlsx", index=False)
    return df


def arama_yap(ana_klasor, sorgu):
    index_yolu = Path(ana_klasor) / "PREGATE_ARSIV" / "ISLEM_RAPORLARI" / "ARSIV_INDEX.xlsx"
    if not index_yolu.exists():
        return pd.DataFrame()

    df = pd.read_excel(index_yolu).fillna("")
    if not sorgu:
        return df

    q = temizle_ad(sorgu).replace("_", "")

    def satirda_var(row):
        alan = " ".join(str(x) for x in row.values).upper()
        alan_temiz = temizle_ad(alan).replace("_", "")
        return q in alan_temiz

    return df[df.apply(satirda_var, axis=1)]


def ozet_sayilar(ana_klasor):
    arsiv = Path(ana_klasor) / "PREGATE_ARSIV"
    sonuc = {}

    for tur, klasor in BELGE_KLASORLERI.items():
        if tur == "ISLEM_RAPORLARI":
            continue
        p = arsiv / klasor
        sonuc[tur] = len([x for x in p.glob("*.*") if x.is_file()]) if p.exists() else 0

    sonuc["TOPLAM"] = sum(v for k, v in sonuc.items() if k != "ISLEM_RAPORLARI")
    return sonuc
