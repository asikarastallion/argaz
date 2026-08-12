# CI/CD

Üç iş akışı var ve aralarındaki sınır, bütün projenin dayandığı sınırın
aynısıdır: **bir model hakkında yalnızca katman 2 bir şey söyleyebilir.**

| iş akışı | ne zaman | neyi kanıtlar |
|---|---|---|
| `tier1.yml` | her push ve pull request | prosedür mantığı, HTTP/WebSocket katmanı, sayfa. Hiçbir model hakkında bir şey değil. |
| `tier2.yml` | her gece 03:00 UTC ve elle tetiklendiğinde | gerçek model kümesi, Gazebo içinde. [status.md](status.md) içindeki model satırlarının tek kaynağı. |
| `status.yml` | bir katman koştuktan sonra | `docs/status.md` dosyasını artefaktlardan yeniden üretir ve işler |

## İmajlar çekilir, hiç derlenmez

Her push'ta ArduPilot derlemek katman 1'i bütçesinin bir saat ötesine taşırdı.
Katman-2 imajı 10,3 GB (Gazebo Harmonic + ROS 2 Jazzy + ArduPilot + SITL_Models
+ ardupilot_gazebo) ve barındırılan bir runner'da geri kazanım adımından önce
yaklaşık 14 GB boş yer var — imajı çekmek sınıra yakın, orada derlemek daha da
yakın. Her iki imaj da ayrı bir `images` iş akışıyla derlenir.

Checkout, imajın içine gömülü kopyanın üzerine bağlanır; böylece test edilen
kod, koşuyu tetikleyen commit olur.

## Ne yüklenir ve neden başarısızlıkta bile

Her koşu bir dizin bırakır: dataflash logu, parametre dökümü, uçuş sonrası
rapor, ortam parmak izi ve `docs/status.md` dosyasının üretildiği `suite.json`.
İş geçse de kalsa da yüklenir, **çünkü başarısızlık da bir sonuçtur** — ve
çünkü birinin gerçekten okuması gereken koşu kırmızı olandır.

## docs/status.md üretilir ve döngü bilerek kırılmıştır

`status.yml` tabloyu yeniden üretir ve işler. İki koruma bunun sonsuz bir
döngüye dönüşmesini engeller:

- `tier1.yml`, yalnızca `docs/**` altına dokunan push'ları yok sayar;
- bot'un commit'i `[skip ci]` taşır, çünkü aynı commit `README.md` içindeki
  `STATUS-SUMMARY` bloğunu da yeniden yazar ve o dosya `docs/` altında
  **değildir**. README'yi elle düzenleyen bir insan testleri yine koşturmalıdır,
  bu yüzden muafiyet dosyaya değil o tek commit'e verilmiştir.

## Kapsam, durum tablosuyla birlikte üretilir

`python3 -m argazui status`, `docs/coverage.md` dosyasını `docs/status.md` ile
aynı koşu derlemesinden yazar. Koşular üzerinde iki ayrı geçiş iki farklı cevap
üretebilir; durum tablosundaki *Neler test edilmedi* özeti ile kapsam
raporundaki tam listelerin uyuşması gerekir — bu yüzden tek geçiş vardır.

`python3 -m argazui coverage` yalnızca kapsam belgesini yeniden üretir. Çıkış
kodu her zaman `0`'dır: kapsam bir ölçümdür, bir kapı değil. Kapsanmayan bir
prosedürü kırmızı bir derlemeye çevirmek, doğru olan şeyi — bir prosedürü
uçurulabilmeden önce beyan etmeyi — CI'ı bozan şey hâline getirirdi.

`python3 -m argazui trace runs/<id>` ise bir **kapıdır** ve zincirdeki bir bağ
çözülmediğinde 1 ile çıkar. Kimsenin denetlemediği bir izlenebilirlik şeması
sessizce çürür.

## Bayatlamış üretilmiş artefaktlar bir test hatasıdır

`docs/status.md` ve `docs/coverage.md` makine çıktısıdır ve depoya işlenir;
dolayısıyla kaynak kodun olamayacağı bir biçimde yanlış olabilirler: kod ilerler,
belge ilerlemez. v1.6, ikisi de hâlâ v1.5'i anlatırken yayımlandı — en görünür
biçimde, `coverage.py` beş boyut beyan ederken `coverage.md` dört boyut
taşıyordu; yani yayımlanan rapor okuyucuya, projenin artık ölçmediği bir şeyi
ölçtüğünü söylüyordu.

Yeniden üretilen çıktıyla bayt karşılaştırması bu denetim olamaz. Her iki belge
de diskteki koşulardan hesaplanır ve bu, bir geliştiricinin makinesiyle bir CI
runner'ı arasında zaten tasarım gereği farklıdır. Belirlenimli olan şey
YAPILARIDIR ve bayatlayan da tam olarak oydu:

* kodun beyan ettiği her kapsam boyutunun `coverage.md` içinde bir bölümü olmalı
  ve `coverage.md`, kodun düşürdüğü hiçbir boyutu adlandırmamalı;
* `status.md`, bu üreticinin yazdığı başlıkları taşımalı;
* README'nin `STATUS-SUMMARY` bloğu, `status.md` ile aynı üretim zamanını
  bildirmeli — böylece bir commit birini işleyip diğerini bırakamaz.

Bunlar `tests/test_identity_and_artefacts.py` içindedir, `tier1` olarak
işaretlidir ve dolayısıyla hâlihazırda var olan işte, her push'ta koşarlar. Yeni
bir iş akışı ya da yeni bir CI adımı yoktur.

## Regresyon kapısı

v1.7'ye kadar bu bölüm, okuyucunun *ekleyebileceği* bir parçacığı anlatıyordu.
Hiçbir şey `argazui compare` çağırmıyordu; yani eşiğini aşarak kötüleşen bir
metriğin hiçbir otomatik tüketicisi yoktu — yalnızca kod olarak var olan bir
regresyon sistemi henüz bir sürüm kapısı değildir.

Artık `tier2.yml`, modeller uçtuktan sonra onu koşturuyor:

```yaml
- name: Regresyon kapısı
  if: always()
  run: python3 -m argazui gate --runs runs --baselines runs/baselines
```

İşin uçurduğu her modelin en yeni koşusunu, `runs/baselines/<model_id>/`
altındaki işlenmiş referansla karşılaştırır ve tek bir hüküm döndürür.

### Beş sonuç ve neden beş

| sonuç | anlamı | çıkış | sürümü engeller mi |
|---|---|---:|---|
| `PASS` | karşılaştırılan her metrik eşiğini korudu | 0 | hayır |
| `FAIL` | bir metrik eşiğini aşarak kötüleşti | 1 | **evet** |
| `ERROR` | karşılaştırma yapılamadı | 2 | hayır — ama işi başarısız kılar |
| `SKIPPED` | karşılaştırılacak koşu yoktu | 0 | hayır |
| `NOT_APPLICABLE` | bu modelin henüz işlenmiş bir referansı yok | 0 | hayır |

`FAIL` ve `ERROR` ikisi de işi başarısız kılar ve bilerek farklı haberlerdir.
Okunamayan bir koşu ya da parmak izleri örtüşmeyen iki koşu bir **altyapı**
sonucudur: `evidence` sınıflandırmasını korur ve hiçbir şey onu araçla ilgili
bir hüküm olarak okumaz. İkisini birleştirmek, yanlış belirtilmiş bir referans
yolunun kötüleşmiş bir araç olarak raporlanmasına giden yoldur.

`SKIPPED`, `PASS` değildir. Hiçbir şey uçurmamış bir iş hiçbir şey doğrulamamıştır
ve buna yeşil demek, bu dosyanın `if-no-files-found` notunun zaten uyardığı
sessiz kanıt buharlaşmasıdır.

### Kapı neden bir katman-2 adımı

Bir karşılaştırma uçuş ister ve modeller katman 2'de uçar. Her itmede koşabilen
şey, karşılaştırmanın hava aracı **gerektirmeyen** her yanıdır: uyumluluk
kuralları, fark aritmetiği ve tabanları, beş sonuç ve bir altyapı hatasının
kötüleşmiş bir araç olarak raporlanmaması. Bunlar saf testlerdir, yaklaşık bir
saniye sürerler ve `tier1.yml` onları *Deterministik regresyon doğrulaması*
adımında adlarıyla koşturur; böylece sonuçları altı yüzlük bir toplamın içinde
kaybolmak yerine görünür olur.

```
PR / her itme            birim + entegrasyon + deterministik regresyon
gecelik / sürüm          yukarıdakiler, artı modeller, artı kapı
```

### Referanslar

Bir referans, kendine ait bir biçim değil, `runs/baselines/` altına işlenmiş
sıradan bir koşu dizinidir — bkz. [README dosyası](../runs/baselines/README.md).
Kapıya referans kökünü açıkça ver. `argazui compare`'in referanssız biçimi aynı
modelin en yeni önceki koşusunu seçer; bu arayüz için bir kolaylıktır — bir
hatta ise karşılaştırmanın neye karşı yapıldığını o gün diskte ne varsa ona
bağımlı kılardı.

**Yedi modelin işlenmiş bir referansı var**; hepsi, `doctor --release`
denetimini geçen bir makinede birlikte uçuruldu. İşe olağan yoldan ulaşırlar:
`runs/baselines/` checkout içindedir, `actions/checkout` onu getirir ve adım
zaten `$PWD/runs` dizinini bağlar — böylece kapı, konteynerin az önce yazdığı
güncel koşuları ve işlenmiş referansları tek bir kökte görür. Bir referans
dizini güncel koşu sanılmaz; kapı, üst dizini `baselines/` olan her şeyi atlar.

Referansı olmayan dört model `NOT_APPLICABLE` bildirir ve bu hiçbir şeyi
başarısız kılmaz.

## Model ortamı, hiçbir şey uçmadan önce doğrulanır

`tier2.yml`, tek bir model başlatmadan önce
`python3 -m argazui doctor --release` koşturur. `--release`, iki model-ortamı
eşiğinden katı olanını uygular: varlıklar, yalnızca tartışmasız değil, üzerinde
hiçbir işlenmemiş değişiklik bulunmayan tek ve değişmez bir revizyon olmalıdır.
Bkz. [Tekrarlanabilirlik](reproducibility.tr.md).

`argaz.toml`'un beyan ettiğinden farklı bir `SITL_Models` uçuran bir gecelik iş,
kimsenin tekrarlayamayacağı model satırları yayımlardı ve hata görünmez olurdu,
çünkü her satır yine yeşil kalırdı. Bu yüzden iş başarısız olur — ve bir
**yapılandırma** sorunu olarak, hiçbir model başlatılmadan önce; böylece hiçbir
model bunun yüzünden `failed` diye kaydedilmez.

## Katman 2 barındırılan runner'da koşamıyorsa

Kendi makinene yönlendir; başka hiçbir şey değişmez.

1. Settings → Actions → Runners → New self-hosted runner
2. `tier2.yml` içinde `runs-on: ubuntu-latest` yerine `runs-on: self-hosted`
3. Makinede Docker ve ~30 GB boş alan gerekir. Ekran gerekmez — ArgazUI ekran
   bulamadığında Gazebo'yu yalnızca sunucu kipinde başlatır.

Koşamayan bir katman 2 `untested` olarak raporlanır. Hiçbir şey uçurmadan yeşil
raporlayan bir katman 2 ise hiç katman 2 olmamasından kötü olurdu.

## Katmanları yerelde koşturmak

Bkz. [Geliştirme/test](testing.tr.md).
