# PRGTOK Arşiv Sistemi - Sürüm Geçmişi

Bu dosya, programda yapılan HER revizyonu sürüm numarasıyla birlikte kayıt
altına alır. Yeni bir değişiklik yapıldığında:
  1. `motor.py` içindeki `SURUM = "x.y.z"` değeri güncellenir.
  2. Bu dosyaya yeni bir madde eklenir (en üste).

Sürümleme: `MAJOR.MINOR.PATCH`
  - MAJOR: Mimari / temel mantık değişikliği (örn. PDF-only'ye geçiş)
  - MINOR: Yeni özellik eklendi
  - PATCH: Hata düzeltmesi / küçük iyileştirme

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

----------------------------------------------------------------------

## v2.3.4 — Dört Sınıflandırma Hatası Düzeltildi (Gerçek Örneklerle Teşhis Edildi)

**Tarih:** 2026-06-17

**Neden:** Kullanıcı, OKUNAMAYAN PDF ve yanlış sınıflandırılan belgelerden
gerçek örnekler paylaştı (Körfez Krom Tanker sızdırmazlık raporu, plaka
41B 2271; American Bureau of Shipping tank konteyner raporu, AAMU
261275-9). İncelemede dört ayrı kök sebep bulundu ve düzeltildi.

**Düzeltme 1 — Türk plakası yanlışlıkla "yabancı plaka" sayılıyordu:**
- `yabanci_plaka_bul()` fonksiyonu, gerçek Türk plakası (`41B 2271`)
  metinden temizlendikten sonra, Türkçe resmi belge metinlerinde sık
  geçen "27.08.2014 tarih ve 28801 sayılı resmi gazete" gibi ifadeleri
  yanlışlıkla yabancı plaka adayı (`VE28801`) olarak yakalıyordu.
- Düzeltme: "... TARİH VE NNNNN" ve "VE NNNNN SAYILI" kalıpları artık
  aramadan önce temizleniyor; yasaklı kelime listesine VE, NO, SAYILI,
  GAZETE, MADDE, TARİH, BÖLÜM, TEBLİĞ, YÖNETMELİK, KANUN, RESMİ eklendi.

**Düzeltme 2 — SIZDIRMAZLIK kategorisi çok dar tanımlanmıştı:**
- Önceden sadece "SIZDIRMAZLIK RAPORU", "SIZDIRMAZLIK TEST RAPORU" gibi
  TAM ifadeler aranıyordu. Kullanıcının belirttiği gibi, başlığı farklı
  olsa da (örn. "KARA TANKERİ PERİYODİK KONTROL RAPORU") içeriğinde
  "sızdırmazlık" kelimesi geçen her belge bu kategoriye gitmeli.
- Düzeltme: kural sadece "SIZDIRMAZLIK" / "LEAKPROOFNESS" kelimesinin
  kendisini arayacak şekilde basitleştirildi.

**Düzeltme 3 — Tank/konteyner numarası "Old number" (eski/iptal
numara) ifadesinden yanlış okunuyordu:**
- Bazı belgelerde hem geçerli ("Owner No: AAMU 261275-9") hem de eski/
  iptal edilmiş ("Old number: WABU 561109-8") numara birlikte
  geçiyordu; eski yöntem metindeki İLK eşleşmeyi aldığı için çoğu zaman
  yanlış (eski) numarayı yakalıyordu.
- Düzeltme: `tank_no_bul()` artık önce "OLD NUMBER: ..." ifadesini
  metinden temizliyor, sonra "OWNER NO", "MARQUAGE/MARKING",
  "IMMATRICULATION/UNIT" gibi güvenilir etiketlerin yanındaki numarayı
  öncelikli olarak arıyor; bulamazsa genel aramaya dönüyor.

**Düzeltme 4 — "PORTABLE TANK INSTRUCTION" ifadesi T9 kategorisinde
yanlış pozitif yaratıyordu:**
- Bu ifade hem T9 belgelerinde hem normal Tank Basınç raporlarında
  (örn. "Portable Tank instruction: T7" alanı) ortak geçiyor; T9
  kuralının bir parçası olduğu için birçok gerçek Tank Basınç raporu
  yanlışlıkla T9'a sınıflandırılıyordu.
- Düzeltme: bu ifade T9 kuralından tamamen kaldırıldı.

**Test:** Kullanıcının gönderdiği iki gerçek PDF ile doğrulandı: Körfez
Krom Tanker belgesi artık doğru şekilde SIZDIRMAZLIK kategorisine ve
doğru plakayla (41B2271, yabancı değil) gidiyor; American Bureau of
Shipping belgesi artık T9 yerine doğru şekilde TANK BASINC RAPORU
kategorisine gidiyor. Ayrıca 9 ayrı regresyon testi (eski formatlar,
gerçek T9 belgeleri, UN kodu vb.) çalıştırılıp hiçbir mevcut davranışın
bozulmadığı doğrulandı.

**Not:** Birinci örnek belgenin OCR ile okunduğu metin oldukça bozuktu
("Owner No.: AAM" diye kesik kalmış); bu durumda tank numarası hâlâ boş
çıkabilir — bu OCR kalitesi sınırlamasıdır, regex/mantık hatası değildir.

**Dosyalar:**
- `motor.py` — `yabanci_plaka_bul()`, `tank_no_bul()`, ve T9/SIZDIRMAZLIK
  kuralları güncellendi.

----------------------------------------------------------------------

## v2.3.3 — Tank/Konteyner Numarası Tespiti Düzeltildi (Boşluk-Tire-Boşluk Formatı)

**Tarih:** 2026-06-17

**Neden:** Kullanıcı, bazı tank basınç raporlarında dosya adına yanlış
(veya hiç) tank/konteyner numarası yazıldığını bildirdi. Örnek belge
incelendi: gerçek numara `VTGU 184073 - 8` şeklinde, harf/rakam grubu
ile kontrol rakamı arasında BOŞLUK-TİRE-BOŞLUK kombinasyonu kullanılmış
(`184073 - 8`). Önceki regex deseni bu spesifik ayraç kombinasyonunu
tanımıyordu, sadece tire veya sadece boşluk varyasyonlarını
destekliyordu; bu yüzden numara hiç yakalanamıyor, dosya adına eski
rapor/sıra numarası (`00003REV` gibi) yazılıyordu.

**Değişiklikler:**
- `TANK_NO_RE` regex deseni güncellendi: artık 6 rakamlık grup ile son
  kontrol rakamı arasında şu ayraç kombinasyonlarının HEPSİ
  tanınıyor: hiç ayraç yok, sadece boşluk, sadece tire, boşluk+tire,
  tire+boşluk, VE boşluk+tire+boşluk (yeni eklenen, asıl sorunlu olan
  format). Tüm varyasyonlar normalize edilip aynı standart formata
  (`ABCD123456-7`) çevriliyor.
- Test edilerek doğrulandı: kullanıcının paylaştığı gerçek PDF'te
  (`VTGU 184073 - 8`) artık doğru şekilde `VTGU184073-8` olarak
  tespit ediliyor ve dosya adına doğru yazılıyor
  (`VTGU184073-8 02.01.2023 LIEU 24010LT TANK BASINC P.pdf`).
  Önceki tüm ayraç varyasyonları (tire, boşluk, boşluksuz) da hâlâ
  doğru çalışıyor — geriye dönük uyumluluk korundu.

**Not — devam eden araştırma:** Kullanıcı, bazı VTGU/Fransızca formatlı
tank basınç raporlarının bazen hiç tanınmayıp `OKUNAMAYAN PDF`
klasörüne düştüğünü de bildirdi. Bu, yukarıdaki numara tespiti
sorunundan FARKLI ve henüz teşhis edilememiş bir durum (muhtemelen
gerçekten taranmış/düşük kaliteli görüntü içeren dosyalarla ilgili).
Kullanıcıdan böyle bir örnek istendi; örnek sağlandığında ayrıca ele
alınacak.

**Önemli — mevcut dosyaların düzeltilmesi:** Bu düzeltme sadece BUNDAN
SONRA yapılacak taramalar için geçerlidir. Daha önce yanlış numarayla
zaten taşınmış/adlandırılmış dosyaların düzeltilmesi için, kullanıcı
"Tümünü Yeniden Tara" butonunu kullanmalıdır.

**Dosyalar:**
- `motor.py` — `TANK_NO_RE` regex deseni güncellendi.

----------------------------------------------------------------------

## v2.3.2 — Gerçek Kurulum Sihirbazı (Setup.exe) Eklendi

**Tarih:** 2026-06-17

**Neden:** Kullanıcı, tek bir `.exe` dosyasını zip'ten çıkarıp manuel
çalıştırmak yerine, "Next, Next, Install" tarzı gerçek bir kurulum
sihirbazı istedi; bu sihirbazın masaüstü ve başlat menüsü kısayolunu
otomatik oluşturmasını ve doğru ikonu kullanmasını istedi.

**Değişiklikler:**
- `installer/kurulum.iss` eklendi: Inno Setup için kurulum betiği.
  Kurulum sırasında kullanıcıya "Masaüstü simgesi oluştur" seçeneği
  sunulur (varsayılan olarak işaretli), program Başlat Menüsü'ne de
  eklenir, her ikisi de `assets/app_icon.ico` simgesini kullanır.
  Kurulum dili Türkçe olarak ayarlandı. Yönetici izni gerektirmeyecek
  şekilde (`PrivilegesRequired=lowest`) yapılandırıldı, kurumsal/
  kısıtlı bilgisayarlarda da çalışabilmesi için.
- `.github/workflows/build-windows.yml` güncellendi: PyInstaller ile
  `.exe` oluşturulduktan sonra, Inno Setup (Chocolatey üzerinden
  otomatik kurulan) ile bu `.exe`'yi gerçek bir kurulum dosyasına
  (`PRGTOK_Arsiv_Kurulum.exe`) paketliyor.
- Artık GitHub Actions her derlemede İKİ farklı çıktı (artifact)
  üretiyor: "PRGTOK_EXE" (eskisi gibi tek başına çalışan dosya, ileri
  düzey kullanım için) ve "PRGTOK_Kurulum_Sihirbazi" (yeni, normal
  kullanıcılar için önerilen, gerçek Setup.exe deneyimi sunan kurulum
  dosyası).

**Not — önceki "siyah konsol penceresi" şikayeti hakkında:**
Kullanıcı, indirilen `.exe`'yi zip içinden (WinRAR'ın geçici açma
klasöründen) doğrudan çift tıklayarak çalıştırdığında kısa süreli bir
konsol penceresi gördüğünü bildirdi. PyInstaller derlemesi zaten
`--windowed` modunda yapıldığı için (konsol penceresi açmaması
gerekir), bu sorunun zip'in geçici bir klasörden çalıştırılmasıyla
ilgili olduğu değerlendirildi. Gerçek bir kurulum sihirbazıyla
(Program Files altına düzgün kurulum) bu sorunun ortadan kalkması
bekleniyor; kullanıcıdan yeni kurulum sonrası bu davranışı tekrar
gözlemlemesi istenecek.

**Dosyalar:**
- `installer/kurulum.iss` — yeni eklendi.
- `.github/workflows/build-windows.yml` — Inno Setup adımları eklendi.

----------------------------------------------------------------------

## v2.3.1 — Kenar Çubuğu Küçültüldü (İmza Görünür Hale Geldi)

**Tarih:** 2026-06-16

**Neden:** v2.2.0'da eklenen "Anahtar Kelimeler" butonuyla kenar
çubuğundaki menü ve hızlı işlem butonları toplam alanı, küçük/standart
pencere boyutlarında "S.SEYMEN" imza alanının görünür kalmasına yetecek
kadar yer bırakmıyordu.

**Değişiklikler:**
- Logo boyutu 110x110'dan 84x84 piksele küçültüldü.
- Üst başlık ("PRGTOK Arşiv Sistemi") ve alt yazı ("Sadece PDF • vX.X.X")
  font boyutları ve aralarındaki boşluklar azaltıldı.
- 5 menü butonu (Anasayfa, Tüm Belgeler, Arama, İşlem Raporları,
  Anahtar Kelimeler) yüksekliği 42'den 34 piksele düşürüldü.
- 5 hızlı işlem butonu (Klasör Seç, Klasörü Tara, Yenile, Okunamayanları
  Tekrar Dene, Tümünü Yeniden Tara) yükseklikleri 46/42'den 36/32
  piksele düşürüldü, aralarındaki boşluklar azaltıldı.
- "S.SEYMEN" imza kutusu da biraz küçültüldü (font 16→13).
- Sonuç: standart pencere boyutunda bile artık "S.SEYMEN" ve
  "Versiyon: 2.3.1" yazısı kenar çubuğunun en altında net görünüyor,
  hiçbir buton kesilmiyor veya görünmez kalmıyor (ekran görüntüsüyle
  doğrulandı).

**Dosyalar:**
- `main.py` — kenar çubuğu (sidebar) bölümündeki tüm boyutlar/aralıklar
  küçültüldü.

----------------------------------------------------------------------

## v2.3.0 — OCR Desteği Eklendi (Taranmış/Resim Tabanlı PDF'ler)

**Tarih:** 2026-06-16

**Neden:** Gerçek kullanımda, 13.231 dosyalık bir klasörde 2363 dosya
(yaklaşık %18) `OKUNAMAYAN PDF` klasörüne düşüyordu. Sebebi: bu PDF'ler
taranmış (fotokopi/tarayıcı çıktısı) belgeler olduğu için içlerinde
gömülü metin katmanı yok — sadece sayfa görüntüsü var. `pdfplumber`
sadece gömülü metni okuyabildiği için bu dosyalardan hiç metin
çıkaramıyordu. Kullanıcı onayıyla OCR (resimden metin tanıma) eklendi.

**Değişiklikler:**
- `pdf_text_oku()` fonksiyonu artık şu şekilde çalışıyor: önce normal
  yöntemle (hızlı, gömülü metin katmanı) metin çıkarmayı dener; metin
  TAMAMEN boş gelirse, otomatik olarak OCR'a düşer.
- OCR sadece normal yöntemin tamamen başarısız olduğu dosyalarda
  çalışır (performans için) ve sadece ilk 3 sayfayı işler (belge türü
  bilgisi genelde ilk sayfada olduğu için).
- OCR motoru: Tesseract (İngilizce + Türkçe dil paketleriyle), PDF
  sayfalarını görüntüye çevirmek için Poppler kullanılıyor
  (`pytesseract` + `pdf2image` Python paketleri üzerinden).
- **Windows'ta otomatik konum bulma**: Program, Tesseract'ı
  `C:\Program Files\Tesseract-OCR\tesseract.exe` gibi yaygın kurulum
  konumlarında otomatik arar; Poppler için de `C:\Program Files\poppler`,
  `C:\poppler` gibi yaygın konumları tarar. Bulunursa kullanıcının
  PATH ayarı yapmasına gerek kalmaz.
- **OCR kütüphaneleri kurulu değilse program çökmez**: `OCR_KULLANILABILIR`
  bayrağı `False` olur ve program eskisi gibi (sadece normal yöntemle)
  çalışmaya devam eder; sadece taranmış PDF'ler yine OKUNAMAYAN'a gider.
- Test edilerek doğrulandı: resim tabanlı (taranmış) bir test PDF'i
  OCR sayesinde doğru kategoriye (ISOPA) yönlendirildi; gerçekten boş
  bir PDF hâlâ doğru şekilde OKUNAMAYAN PDF'e gitti (isim değişmedi).
  Karma bir test setinde (3 normal + 2 taranmış + 1 boş PDF) paralel
  tarama 0.9 saniyede sorunsuz tamamlandı.

**ÖNEMLİ — Kullanıcı tarafında ek kurulum gerekiyor:**
OCR'ın Windows'ta çalışması için, Python paketlerine (`pip install -r
requirements.txt` ile otomatik kurulan `pytesseract` ve `pdf2image`)
ek olarak, iki harici programın bilgisayara kurulması gerekiyor:
1. **Tesseract OCR** — `https://github.com/UB-Mannheim/tesseract/wiki`
   adresinden `.exe` kurulum dosyası indirilip kurulmalı. Kurulum
   ekranında "Additional language data" kısmından **Turkish** dil
   paketi de işaretlenmeli.
2. **Poppler** — `https://github.com/oschwartz10612/poppler-windows/releases`
   adresinden son sürüm zip indirilip bir klasöre çıkarılmalı (örnek:
   `C:\poppler`).
Bu iki program kurulmazsa OCR devre dışı kalır ama program normal
çalışmaya devam eder (sadece taranmış PDF'ler okunamaz).

**Dosyalar:**
- `motor.py` — `pdf_text_oku()`, yeni `pdf_text_oku_ocr()`,
  `_poppler_bin_yolu_bul()` fonksiyonları eklendi.
- `requirements.txt` — `pytesseract`, `pdf2image` eklendi.

----------------------------------------------------------------------

## v2.2.0 — Anahtar Kelime Yönetimi (Klasöre Özel, Override Edilebilir Kurallar)

**Tarih:** 2026-06-16

**Neden:** Kullanıcı, belge türü tespitinin sadece koddaki sabit
kurallarla sınırlı kalmaması, kendisinin de her kategori için anahtar
kelime tanımlayabilmesi istedi (örnek verilen senaryo: "INSPECTION
DATE" gibi bir kelimeyi bir kategoriye eklediğinde, o kelimeyi içeren
belgelerin o kategoriye gitmesi).

**Değişiklikler:**

*Anahtar kelime sistemi (motor.py):*
- Her ana klasörün kendine özel `ISLEM RAPORLARI/ANAHTAR KELIMELER.json`
  dosyasında kategori → kelime listesi kalıcı olarak saklanıyor.
  Anahtar kelimeler klasöre özeldir; farklı bir klasör taradığınızda
  farklı kelime listeleri kullanabilirsiniz.
- `anahtar_kelimeleri_oku()`, `anahtar_kelimeleri_kaydet()`,
  `anahtar_kelime_ekle()`, `anahtar_kelime_sil()` fonksiyonları eklendi.
- **Override mantığı**: Bir kategoriye en az 1 kullanıcı kelimesi
  eklendiğinde, o kategori için programın TÜM sabit/otomatik tespit
  kuralları devre dışı kalır; sadece kullanıcının yazdığı kelimeler
  aranır. Kategoriden tüm kelimeler silinirse, o kategori otomatik
  olarak eski sabit kurallarına geri döner. Test edilerek doğrulandı:
  ISOPA kategorisine alakasız bir kelime eklenince, içinde "ISOPA"
  geçen bir belge artık ISOPA kategorisine gitmiyor (override çalışıyor);
  kelime silinince eski davranış geri geliyor.
- `belge_turu_bul()` fonksiyonu `ozel_kelimeler` parametresi alacak
  şekilde yeniden yazıldı; her sabit kural bloğu artık önce "bu
  kategori override edilmiş mi?" kontrolünden geçiyor.
- `dosya_isle()`, `klasor_tara()`, `zorla_yeniden_oku()`,
  `tum_dosyalari_yeniden_tara()` fonksiyonları güncellendi: anahtar
  kelimeler performans için tarama başında bir kez diskten okunup tüm
  dosyalara aynı şekilde uygulanıyor (her dosya için tekrar tekrar
  JSON okumuyor).
- Bu değişiklik **sadece "kod yok / içerik okunarak sınıflandırılan"
  dosyalar** için geçerli; "P" veya "E" kodlu dosyalar zaten içerik
  okumadığı için (dosya adından tür çıkarıyor) bu değişiklikten
  etkilenmiyor — bu kasıtlı bir tasarım kararı.

*Anahtar Kelimeler penceresi (main.py):*
- Sol menüye "🔑 Anahtar Kelimeler" butonu eklendi.
- Tıklandığında, tüm 11 belge kategorisini ve her birinin altında
  kayıtlı kullanıcı kelimelerini gösteren bir pencere açılıyor.
- Her kategori kutusunda: kategori adı (ve "özel kelimelerle çalışıyor"
  / "otomatik kurallarla çalışıyor" durumu turuncu/mavi renkle
  ayırt edilir), mevcut kelimelerin listesi (her birinin yanında
  "Sil" butonu), ve yeni kelime eklemek için bir giriş kutusu + "Ekle"
  butonu (Enter tuşu da çalışır).
- Pencere klasör seçilmeden açılamaz (anahtar kelimeler klasöre özel
  olduğu için önce hangi klasörle çalışıldığı bilinmesi gerekiyor).

*P/E kod davranışı (gözden geçirildi, DEĞİŞMEDİ):*
- Kullanıcı onayıyla doğrulandı: P kodu (otomatik tarandı işareti) ve
  E kodu (elle düzeltildi işareti) eskisi gibi dosya adının sonuna
  eklenmeye devam ediyor. **Tek istisna zaten mevcuttu ve hâlâ
  geçerli**: `OKUNAMAYAN PDF` klasörüne giden (hiç metin çıkarılamayan)
  dosyalara hiçbir kod eklenmiyor ve bu klasör her taramada otomatik
  olarak yeniden denenmeye devam ediyor.

**Dosyalar:**
- `motor.py` — anahtar kelime depolama fonksiyonları, `belge_turu_bul()`
  override mantığı, ilgili tüm çağrı noktaları güncellendi.
- `main.py` — "Anahtar Kelimeler" menü butonu ve yönetim penceresi
  eklendi.

----------------------------------------------------------------------

## v2.1.5 — Tüm Alt Çizgiler Kaldırıldı (Kapsamlı Temizlik)

**Tarih:** 2026-06-16

**Neden:** Kullanıcı, v2.1.4'te sadece klasör adlarında yapılan alt
çizgi temizliğinin yetersiz olduğunu belirtti ve kod içindeki dahili
tür kimlikleri (`BELGE_KLASORLERI` sözlüğünün anahtarları) dahil HER
YERDEKİ alt çizginin kaldırılmasını istedi.

**Değişiklikler:**
- `BELGE_KLASORLERI` sözlüğünün **anahtarları** da artık boşluklu:
  `"TANK BASINC RAPORU"`, `"TRAFIK SIGORTASI"`,
  `"TEHLIKELI MADDE SIGORTASI"`, `"FENNI MUAYENE"`,
  `"YUKSEKTE CALISABILIR SAGLIK RAPORU"`, `"YABANCI PLAKA"`,
  `"DIGER BELGELER"` (önceki sürümde sadece değerler değişmişti).
- Özel klasör adları boşluklu: `PREGATE ARSIV`, `FARKLI FORMAT DOSYALAR`,
  `OKUNAMAYAN PDF`, `ISLEM RAPORLARI`.
- Eski T9 alt-tür isimleri de boşluklu: `T9 GECICI`, `T9 MUAYENE`,
  `T9 ANA`, `T9 MUAYENE SERTIFIKASI`.
- Rapor/dosya adı sabitleri boşluklu: `ARSIV INDEX.xlsx`,
  `SON TARAMA.txt`, `ISLEM RAPORU ...xlsx`,
  `OKUNAMAYAN TEKRAR DENE ...xlsx`, `TUMUNU YENIDEN TARA ...xlsx`
  (tarih/saat damgası içindeki ayraçlar da `_` yerine boşluk oldu).
- Excel raporlarındaki **İşlem Durumu** sütun değerleri boşluklu:
  `OKUNDU TASINDI`, `ELLEDUZ TASINDI`, `ELLEDUZ DOGRU YERDE`,
  `YER DUZELTILDI`, `ATLANDI ZATEN ISLENMIS`, `ATLANDI TUR BULUNAMADI`,
  `FARKLI FORMAT TASINDI`, `OKUNAMADI TASINDI`, `GECICI DOSYA ATLANDI`,
  `RAPOR ATLANDI`, `YENIDEN TARANDI`.
- `main.py` içindeki `stat_labels` ve `cat_labels` sözlük anahtarları
  da (`motor.ozet_sayilar()` ile eşleşmesi için) boşluklu hale
  güncellendi; aksi halde özet kartlarındaki sayılar artık "0" görünür
  ve hiç güncellenmezdi.
- `main.py` içindeki bilgi kutusu (Ayarlar/Raporlar açıklaması)
  metinlerindeki klasör adı referansları da boşluklu güncellendi.
- **Geriye dönük uyumluluk korundu**: `belge_turu_dosya_adindan()`
  fonksiyonu artık hem boşluklu hem alt çizgili (eski) dosya adlarını
  tanıyor; örneğin daha önce `TANK_BASINC_RAPORU E.pdf` şeklinde elle
  düzeltilmiş bir dosya hâlâ doğru klasöre yönlendiriliyor, test
  edilerek doğrulandı.
- **`temizle_ad()` fonksiyonunun iç çalışma mantığına ve
  `DELIVERED_ON` gibi tamamen teknik/iç karşılaştırma sabitlerine
  dokunulmadı** — bunlar hiçbir zaman kullanıcıya gösterilen dosya adı,
  klasör adı veya ekran metni olmuyor; bilinçli olarak kapsam dışı
  bırakıldı.

**Test:** Kod taşımayan PDF, ISOPA içerikli PDF, eski alt çizgili "E"
kodlu dosya adı, yeni boşluklu "E" kodlu dosya adı ve farklı format
(jpg) dosyası ile uçtan uca tarama testi yapıldı; tüm klasörler, dosya
adları ve özet sayıları doğru ve alt çizgisiz olarak doğrulandı.

**Dosyalar:**
- `motor.py` — `BELGE_KLASORLERI`, `TUR_DISPLAY_REVERSE`,
  `belge_turu_dosya_adindan()`, tüm İşlem Durumu sabitleri ve rapor
  dosya adları güncellendi.
- `main.py` — `stat_names`, `categories` listelerindeki anahtarlar ve
  bilgi kutusu metinleri güncellendi.

----------------------------------------------------------------------

## v2.1.4 — Klasör Adlarında Alt Çizgi Kaldırıldı (Boşluklu İsimlendirme)

**Tarih:** 2026-06-16

**Neden:** Kullanıcı talebi: diskte oluşan klasör adlarında (örn.
`TANK_BASINC_RAPORU`) alt çizgi yerine boşluk kullanılması istendi,
daha okunaklı olması için (örn. `TANK BASINC RAPORU`).

**Değişiklikler:**
- `BELGE_KLASORLERI` sözlüğünün **değerleri** (yani diskte gerçekten
  oluşturulan klasör adları) artık boşluklu: `TANK BASINC RAPORU`,
  `TRAFIK SIGORTASI`, `TEHLIKELI MADDE SIGORTASI`, `FENNI MUAYENE`,
  `YUKSEKTE CALISABILIR SAGLIK RAPORU`, `YABANCI PLAKA`,
  `DIGER BELGELER`. (`ISOPA`, `T9`, `SIZDIRMAZLIK`, `SRC5` zaten tek
  kelime olduğu için değişmedi.)
- Sözlüğün **anahtarları** (kod içinde dahili tür kimliği olarak
  kullanılan `"TANK_BASINC_RAPORU"` gibi sabitler) bilerek
  DEĞİŞTİRİLMEDİ — bunlar yüzlerce karşılaştırmada kullanılıyor ve
  kullanıcıya hiçbir zaman gösterilmiyor; değiştirmek gereksiz risk
  taşırdı. Kullanıcının göreceği her yer (klasör adları, dosya adları,
  özet kartı başlıkları) zaten boşluklu görünüyor ve değişmiyor.
- `dosya_isle()` içindeki `BELGE_KLASORLERI.get(tur, "DIGER_BELGELER")`
  varsayılan değerleri de `"DIGER BELGELER"` olarak güncellendi
  (tutarlılık için, dört yerde).
- Dosya adı içindeki kısa tür etiketleri (`TUR_DISPLAY`) zaten önceki
  sürümlerde boşluklu idi (örn. `TANK BASINC`, `TRAFIK SIGORTASI`),
  bu sürümde değişiklik gerekmedi.
- **P / E işlem kodu mantığı gözden geçirildi, değişiklik yapılmadı**:
  okunamayan PDF'ler (`OKUNAMAYAN_PDF` klasörüne taşınanlar) hâlâ kod
  almıyor ve her taramada/her "Okunamayanları Tekrar Dene" işleminde
  yeniden okunmaya çalışılıyor — bu, kullanıcının onayladığı mevcut
  davranış. "P" (otomatik tarandı) ve "E" (elle düzeltildi) kodlu
  dosyaların içeriği hâlâ bir daha okunmuyor, sadece isimden tür
  çıkarılıp doğru klasöre taşınıyor.

**Dosyalar:**
- `motor.py` — `BELGE_KLASORLERI` değerleri ve varsayılan değerler
  güncellendi.

----------------------------------------------------------------------

## v2.1.3 — Üst Banner Görseli, İmza Düzeltmesi, Kart Boyutları

**Tarih:** 2026-06-16

**Neden:** Kullanıcı geri bildirimi: üstteki boş alana liman/tesis
fotoğrafı eklenmesi istendi; sol alttaki "S.SEYMEN" imzası ekranda
kesiliyordu (görünmüyordu); özet ve kategori kartları 3-4 mm kadar
küçültülmesi istendi.

**Değişiklikler:**
- `assets/header.jpg` eklendi: kullanıcının sağladığı liman/tank sahası
  fotoğrafı, üstteki bozuk/renkli kenar şeridi kırpılarak temizlendi.
- Üst banner artık bu görseli orana uygun şekilde 120 piksel
  yükseklikte gösteriyor (önceki sürümde görsel olmadığı için kompakt
  60 piksellik koyu başlık şeridi gösteriliyordu; artık gerçek görsel
  varsa daha ferah bir banner kullanılıyor).
- **"S.SEYMEN" imza alanı küçültüldü ve düzeltildi**: font boyutu
  22'den 16'ya, "Versiyon" yazısı da küçültüldü; alttaki boşluklar
  azaltıldı. Önceki sürümde küçük pencere yüksekliklerinde bu alan
  ekranın altına taşıp görünmez oluyordu.
- Pencerenin minimum yüksekliği 720'den 760 piksele çıkarıldı; sidebar
  içeriğinin (4 menü + 4 hızlı işlem butonu + imza) taşma riski azaltıldı.
- **Üst özet kartları (Toplam PDF, Tank Basınç, vb.) küçültüldü**:
  köşe yuvarlaklığı 14→12, iç boşluk (padding) ~3px azaltıldı, sayı
  fontu 28→24, başlık fontu 13→12.
- **Kategori kartları (Tank Basınç Raporu, ISOPA, T9, vb.) küçültüldü**:
  iç/dış boşluklar 8px'den 6px'e indirildi, başlık fontu 12→11, sayı
  fontu 20→17.

**Dosyalar:**
- `main.py` — Header görsel mantığı, imza alanı, kart boyutları
  güncellendi.
- `assets/header.jpg` — yeni eklendi (liman/tank sahası fotoğrafı).

----------------------------------------------------------------------

## v2.1.2 — Görsel Düzeltmeler (Koyu Tema Geri Alındı, Logo/Header Düzeltildi)

**Tarih:** 2026-06-16

**Neden:** v2.1.0'da denenen açık/beyaz tema gerçek kullanımda
okunabilirliği düşürdü ("anlaşılmıyor" geri bildirimi alındı); ayrıca
logo gereğinden büyük görünüyordu ve üst kısımda `header.jpg` dosyası
proje içinde bulunmadığı için büyük, boş, dikkat dağıtıcı bir alan
oluşuyordu.

**Değişiklikler:**
- **Tema tamamen koyu lacivert temaya geri döndürüldü** (v2.0.0 ile
  aynı palet): `ctk.set_appearance_mode("dark")`, ana arka plan
  `#071320`, kartlar `#10283D`, paneller `#0B1E30`, kenar çubuğu
  `#071827`. Önceki sürümün açık/beyaz teması kaldırıldı.
- **Logo küçültüldü**: 190x190 pikselden 110x110 piksele indirildi;
  artık sol menüde dengeli bir boyutta görünüyor, aşırı yer kaplamıyor.
- **Üst banner (header) düzeltildi**: Önceden `assets/header.jpg` veya
  `assets/terminal.jpg` dosyası yoksa, 170 piksel yüksekliğinde boş/
  beyaz bir alan kalıyordu. Artık resim dosyası yoksa otomatik olarak
  60 piksel yükseklikte, koyu zeminli, "PRGTOK Arşiv Sistemi" başlık
  yazısı içeren kompakt bir şerit gösteriliyor. Resim dosyası eklenirse
  o da artık daha küçük (60 piksel) yükseklikte gösterilecek.
- "Son tarama: ..." etiketinin rengi koyu zemine uygun açık camgöbeği
  tonuna (`#83E0FF`) çevrildi; önceki renk koyu temada okunmuyordu.

**Dosyalar:**
- `main.py` — Tema renkleri, logo boyutu, header mantığı güncellendi.

----------------------------------------------------------------------

## v2.1.1 — Program İkonu (SYMN Arşiv)

**Tarih:** 2026-06-16

**Neden:** Kullanıcı, program penceresi/görev çubuğu ve .exe dosyası için
özel bir simge (SYMN Arşiv logosu) eklenmesini istedi.

**Değişiklikler:**
- `assets/app_icon.ico` eklendi (16, 24, 32, 48, 64, 128, 256 piksel
  boyutlarını içeren çok boyutlu Windows ikon dosyası).
- `assets/app_icon.png` eklendi (Linux/Mac üzerinde pencere ikonu için
  yedek, Windows dışı sistemlerde kullanılır).
- `main.py` içine `_ikon_ayarla()` metodu eklendi: program açılır
  açılmaz pencere/görev çubuğu simgesini bu ikona ayarlar. Windows'ta
  `.ico`, diğer sistemlerde `.png` kullanılır. İkon dosyası bulunamazsa
  veya bir hata olursa program çalışmaya devam eder (sessizce atlanır).
- `.github/workflows/build-windows.yml` içindeki PyInstaller komutuna
  `--icon "assets/app_icon.ico"` parametresi eklendi; böylece üretilen
  `.exe` dosyasının Dosya Gezgini'nde görünen simgesi de SYMN Arşiv
  logosu olacak.

**Dosyalar:**
- `main.py` — `_ikon_ayarla()` eklendi, `__init__` sırası düzeltildi.
- `assets/app_icon.ico`, `assets/app_icon.png` — yeni eklendi.
- `.github/workflows/build-windows.yml` — `--icon` parametresi eklendi.

----------------------------------------------------------------------

## v2.1.0 — Arayüz Revizyonu (Arama, İlerleme Çubuğu, Açık Tema)

**Tarih:** 2026-06-16

**Neden:** Kullanıcı geri bildirimine göre arayüzde sadeleştirme ve
kullanılabilirlik iyileştirmeleri istendi.

**Değişiklikler:**
- **"Ayarlar"** ve **"Klasör Yapısı"** menüleri kaldırıldı (kullanıcı bu
  menülerin gereksiz/işlevsiz olduğunu belirtti).
- **Arama artık ayrı bir sekme değil.** Sol menüdeki "🔎 Arama" butonuna
  tıklandığında üst tarafta bir arama çubuğu açılır/kapanır (toggle).
  Tekrar tıklanınca veya "Kapat" butonuna basılınca gizlenir.
- Arama kutusuna **en az 3 harf** yazılınca otomatik olarak arama
  yapılır (Enter'a basmaya gerek yok, ama Enter ile de tetiklenebilir).
- Arama/listeleme tablosunda artık **"Dosya Konumu"** ve
  **"Son İşlem Tarihi"** sütunları var.
- Sonuç tablosunda bir satıra **çift tıklandığında dosya doğrudan
  işletim sisteminde varsayılan programıyla açılır** (Windows'ta
  `os.startfile`, diğer sistemlerde `open`/`xdg-open`).
- **İlerleme çubuğu** eklendi: "Klasörü Tara", "Tümünü Yeniden Tara" ve
  "Okunamayanları Tekrar Dene" işlemleri sırasında ekranda hem yüzde
  hem sayı olarak ilerleme gösterilir (örnek: `3 / 120  (%2)`).
- Sağ üst köşede **son tarama tarih ve saati** otomatik olarak
  gösterilir (örnek: `Son tarama: 16.06.2026 09:04:12 • 187 dosya`).
  Bu bilgi `ISLEM_RAPORLARI/SON_TARAMA.txt` dosyasında saklanır.
- İşlem rapor dosyalarının adları artık gün-ay-yıl_saat-dakika-saniye
  formatında kaydediliyor (örnek: `ISLEM_RAPORU_16-06-2026_09-04-12.xlsx`),
  böylece hangi taramanın hangi gün/saat yapıldığı dosya adından
  doğrudan görülebiliyor.
- Her dosyanın **son işlem tarihi** (en son ne zaman tarandığı/taşındığı)
  arama sonuçlarında gösteriliyor; bu zaten `dosya_isle()` içinde
  tutulan "İşlem Tarihi" alanından geliyor.
- Tema **açık/beyaz** yapıldı: ana içerik alanının arka planı beyaza
  (`#F4F6F9`) çevrildi. Sol menü ve kart/panel kutuları okunabilirlik
  ve marka tutarlılığı için koyu lacivert tonlarında bırakıldı
  (kullanıcı talebiyle: "kutular yine koyu kalsın").
- **Logo büyütüldü ve daha görünür hale getirildi** (sol menüde
  190x190 piksel boyutunda gösteriliyor; önceki sürümde 210x70 dikdörtgen
  boyuttaydı ve kare logo bu orana sıkıştığı için net görünmüyordu).
- Kategori kartı ızgarası (TANK BASINÇ, ISOPA, T9, TRAFİK SİGORTASI vb.)
  4 sütun x 4 satır olacak şekilde grid ağırlıkları yeniden düzenlendi;
  önceki sürümde bazı kartların görünmeme şikayeti bu düzenlemeyle
  giderildi.

**Dosyalar:**
- `main.py` — Arayüz, yukarıdaki tüm maddeler için yeniden düzenlendi.
- `motor.py` — `klasor_tara`, `zorla_yeniden_oku`, `tum_dosyalari_yeniden_tara`
  fonksiyonlarına `progress_callback` parametresi eklendi; rapor dosya
  adları gün/saat formatına çevrildi; `son_tarama_bilgisi_oku()` ve
  `_son_tarama_bilgisini_kaydet()` fonksiyonları eklendi.
- `assets/logo.png` — Poliport logosu eklendi.

----------------------------------------------------------------------

## v2.0.0 — Sıfırdan Yeniden Yazım (PDF-Only Mimari)

**Tarih:** 2026-06-16

**Neden:** Eski program (v1.0.2) çalışmıyordu; isim okuma/yazmada hatalar
vardı. Program PDF-dışı dosyalarda OCR yaparken kilitleniyor/karmaşıklaşıyordu.
Bu sürümde program **sıfırdan** baştan tasarlandı.

**Değişiklikler:**
- Program artık **SADECE PDF dosyalarını** tarar, okur ve sınıflandırır.
- PDF olmayan tüm dosyalar (jpg, png, docx, xlsx, vb.) OCR/metin
  okumadan doğrudan **`FARKLI_FORMAT_DOSYALAR`** klasörüne taşınır.
  Bu dosyalar elle ayrıca düzenlenmelidir (ayrı bir program/akış önerilir).
- `pytesseract` / OCR bağımlılığı tamamen kaldırıldı (artık gerekmiyor).
- İşlem kodu sistemi sadeleştirildi:
  - **P** = Program tarafından otomatik tarandı/sınıflandırıldı
  - **E** = Elle düzeltildi (kullanıcı dosya adını kendisi yazdı)
  - Kod her zaman dosya adının **sonunda**, uzantıdan önce yer alır.
    Örnek: `34 ABC 123 12.06.2026 TANK BASINC P.pdf`
- **P kodlu dosyalar:** İçerik bir daha okunmaz. Sadece dosya adındaki
  tür anahtar kelimesine göre doğru klasörde olup olmadığı kontrol
  edilir; yanlış yerdeyse doğru klasöre taşınır.
- **E kodlu dosyalar:** İçerik HİÇ okunmaz (kullanıcı elle düzeltmiş
  kabul edilir). Sadece dosya adı içindeki tür kelimesine göre doğru
  klasöre taşınır. İsim aynen korunur.
- Kod taşımayan (ne P ne E) PDF'ler: içerik okunur, türü tespit edilir,
  yeniden adlandırılır (sonuna " P" eklenir) ve ilgili klasöre taşınır.
- **T9 alt kategorileri kaldırıldı.** Eskiden T9_GECICI / T9_MUAYENE /
  T9_ANA / T9_MUAYENE_SERTIFIKASI olarak ayrılan belgeler artık tek bir
  **T9** kategorisinde birleşti.
- Diğer kategoriler (TANK_BASINC_RAPORU, ISOPA, TRAFIK_SIGORTASI,
  TEHLIKELI_MADDE_SIGORTASI, FENNI_MUAYENE, SIZDIRMAZLIK,
  YUKSEKTE_CALISABILIR_SAGLIK_RAPORU, SRC5, YABANCI_PLAKA,
  DIGER_BELGELER) aynı kaldı.
- Okunamayan PDF'ler artık `OKUNAMAYAN_PDF` klasöründe tutulur (eski
  adı: `OKUNAMAYANLAR`); "Okunamayanları Tekrar Dene" butonuyla
  yeniden denenebilir.
- "Zorla Yeniden Oku" butonu "Okunamayanları Tekrar Dene" olarak
  yeniden adlandırıldı ve artık sadece `OKUNAMAYAN_PDF` klasöründeki
  PDF'leri işler.
- "Tümünü Yeniden Tara" tüm PDF'leri (P/E kodu olsa da) içerikten
  zorla yeniden okur; E kodlu dosyalarda kod E olarak korunur, diğerlerinde
  P olarak yazılır.
- Eski sürümden gelen kodlar geriye dönük tanınır ve otomatik çevrilir:
  - `S` / `PRGTOK` → `P`
  - `PRGT` → `E`
  - Eski `T9_GECICI`, `T9_MUAYENE`, `T9_ANA`, `T9_MUAYENE_SERTIFIKASI`
    klasör/isim etiketleri → `T9`
- Arayüzde sürüm numarası başlıkta, kenar çubuğunda ve "Ayarlar"
  penceresinde gösteriliyor.

**Dosyalar:**
- `main.py` — Arayüz (GUI), sıfırdan yazıldı.
- `motor.py` — Tarama/sınıflandırma motoru, sıfırdan yazıldı (sadece PDF).
- `requirements.txt` — `pytesseract` kaldırıldı.

----------------------------------------------------------------------

## v1.0.2 ve öncesi (eski sistem — artık kullanılmıyor)

Eski sistemde PDF ve resim dosyaları (OCR ile) birlikte taranıyordu;
işlem kodları `PRGTOK` (otomatik) / `PRGT` (elle düzeltme) idi ve T9
belgeleri 4 alt kategoriye ayrılıyordu. Bu sürüm GitHub Actions ile inşa
edilmiş ama kullanıcı tarafında çalışmıyordu; bu nedenle v2.0.0'da
mimari sıfırdan değiştirildi.
