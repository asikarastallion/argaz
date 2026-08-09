# Doğrulama modeli

Bu sayfa, ArgazUI'de yeşil bir sonucun neyi iddia ettiğini anlatır — ve daha
uzun uzun, çünkü asıl önemli olan budur, **neyi iddia etmediğini**.

## Diğer her şeyin türediği tek kural

**Bir makine gözlemlemediyse hiçbir şey doğrulanmış sayılmaz.** Makul bir
çıkarım değil, "geçen hafta çalışıyordu" değil, ACK hiç değil. Katman 2'nin
hiç uçurmadığı bir model `untested`'dır ve `untested` şu demektir: *henüz bir
makine tarafından doğrulanmadı*. Bozuk demek değildir, çalışıyor da demek
değildir.

Bu proje, alternatifi denendiği için var. v1.0'ın README'sinde elle yazılmış
bir destek tablosu vardı; o tikleri üreten tek şey birinin inancıydı ve
içlerinden en az biri bir yıl boyunca yanlıştı — Plane kalkışı hiç
çalışmamıştı.

## Üç tür çıktı, ve birbirlerinin yerine geçmezler

| | üreten | koşuyu düşürebilir mi? | eşiğin kaynağı |
|---|---|---|---|
| **Kabul kriterleri** | prosedürün `expect:` bloğu | **evet** | prosedür, uçuş başına beyan eder |
| **Danışma uyarıları** | `flightlog.py`, dataflash logundan | hayır | ArduPilot'un kendi dokümantasyonu |
| **Metrikler** | `metrics.py`, aynı log ve koşu kaydından | hayır | hiçbiri — bir referansla karşılaştırılana kadar |

İlk ikisini birbirine karıştırmak iki sonuçtan birini verirdi: gürültülü bir
hava aracı çalışan bir kalkışı bozuk göstermek, ya da gerçek bir kabul
başarısızlığının sağlık uyarıları arasında kaybolması. Metrikler ikisinden de
başka bir sebeple ayrılır: tek başlarına hiçbir eşik taşımazlar, dolayısıyla
burada onlara eşik vermek, hiçbir prosedürde beyan edilmemiş sınırlarla ikinci
bir kabul sistemi kurmak olurdu. Bkz. [Metrikler](metrics.tr.md) ve
[Regresyon](regression.tr.md).

## Üç sonuç, ve üçüncüsü hava aracıyla ilgili değil

| sonuç | anlamı |
|---|---|
| `passed` | her adım çalıştı ve her kabul kriteri sağlandı |
| `failed` | bir adım ya da bir kriter sağlanmadı. Hava aracı hakkında gerçek bir sonuç. CI kırmızıya döner. |
| `error` | prosedür hiç değerlendirilemedi — bozuk bir adım, kopan bir bağlantı, koşturucudaki bir hata. **Hava aracı hakkında hiçbir şey söylemez.** |

Koşunun kendi durumu dördüncüyü ekler, `no-procedure`: model başlatılıp
durduruldu, hiçbir şey çalıştırılmadı, dolayısıyla hiçbir iddia ortaya
atılmadı. Bu, `untested` olarak raporlanır; asla geçti sayılmaz.

## İki katman, ve yalnızca biri bir modelin adını anabilir

**Katman 1**, Gazebo olmadan SITL'in kendi genel gövdelerini uçurur. Yetenek
sorgusunun aracı doğru okuduğunu, doğru prosedürün seçildiğini, beyan edilen
override'ların uygulanıp geri alındığını, kabul kriterlerinin ölçülmüş duruma
karşı değerlendirildiğini ve eksiksiz, ayrıştırılabilir bir koşu dizininin
çıktığını doğrular.

**Katman 1 hiçbir Gazebo modeli hakkında iddiada bulunmaz.** Yeşil bir katman-1
koşusu "Skywalker X8 çalışıyor" demek değildir; "plane prosedürü SITL'in plane
gövdesinde çalışıyor" demektir.

**Katman 2**, gerçek model kümesini Gazebo içinde uçurur. Sonuçları
[docs/status.md](status.md) içinde bir modelin karşısında görünebilecek tek
katman budur.

Atlanan bir test geçmiş sayılmaz. Eksik ikili dosya, eksik Gazebo, eksik model:
test gerekçesiyle birlikte atlanır ve model `untested` olarak kaydedilir.

## İddialar, satırlardan dardır

Durum tablosundaki `passed` bir satır şu demektir: "bu modelin uçurulduğu her
prosedür, beyan ettiği her kriteri sağladı". Bu, göründüğünden dardır ve
aradaki boşluk tam olarak hak edilmemiş iddianın yeniden bittiği yerdir.

Bu yüzden durum üreteci ayrıca **doğrulama iddiaları** üretir: her prosedür,
doğrulanmış her mod geçişi ve her kabul kriteri için bir satır; her birinin
sonucu ve onu kanıtlayan koşuyla birlikte. Bunları okuma kuralı bölümün kendi
başında yazılıdır — *orada listelenmeyen hiçbir şey doğrulanmamıştır*.

Özellikle, bu projedeki hiçbir model şu koşullarda uçurulmadı:

- yol noktalı bir görev boyunca,
- rüzgârda ya da başka bir bozucu etki altında,
- uçuş zarfının sınırlarında,
- enjekte edilmiş bir arıza ile,
- güvenilirlik hakkında bir şey söylemeye yetecek kadar tekrarla.

## Yeniden denemenin bir bedeli vardır

Test kümelerinin prosedür başına tam olarak bir yeniden deneme hakkı vardır;
çünkü SITL yüklü bir makinede gerçekten zamanlamaya duyarlıdır. Bu deneme asla
sessiz kalmaz: koşunun `flaky` listesine yazılır, her deneme `procedures`
içinde kalır ve durum tablosu koşuyu `passed` değil `flaky` olarak raporlar.
Bu görünür bedel olmasa, yeniden deneme kuralı hataları saklamanın bir yolundan
ibaret olurdu.

## Bunların her biri nerede yaşar

| | |
|---|---|
| Kabul kriterleri | `argazui/procedures/*.yaml`, `procrunner.py` değerlendirir |
| Tek bir koşunun sonucu | `runs/<id>/result.json` |
| Danışma uyarıları ve metrikler | `runs/<id>/report.json`, özeti `report.md` |
| Sonucu neyin ürettiği | `runs/<id>/fingerprint.json` |
| Referansla karşılaştırma | `runs/<id>/regression.json` |
| Model satırları ve iddialar | `docs/status.md`, `argazui status` üretir |
