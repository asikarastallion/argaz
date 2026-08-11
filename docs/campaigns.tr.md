# Tekrarlanabilirlik kampanyaları

Bir kampanya, **aynı prosedürü, aynı model üzerinde, aynı yapılandırmayla N
kez** uçurur ve tek bir hüküm yerine dağılımı raporlar.

## Tek koşu neden bir cevap değildir

Bu projedeki diğer bütün katmanlar tek bir uçuşa hüküm verir: kriterler
sağlandı ya da sağlanmadı, metrikler şu sayılardı, referansla karşılaştırma şunu
söyledi. Bunların tamamı *bir* kalkış için doğrudur; oysa bir simülasyonun
arızaları çoğu zaman böyle davranmaz. Beş denemenin dördünde çalışan bir
prosedür, ne çalışan bir prosedürdür ne de bozuk biri — ve ne yeşil bir koşu ne
de kırmızı biri hangisi olduğunu söyler.

Bu projenin üzerine yeniden kurulduğu vaka tam olarak bunu gösteriyor.
`tailsitter_takeoff` üç kez geçti: 24,9 m, 23,6 m ve 18,3 m. Her koşu kendi
kriterlerini sağladı. *Dağılım*, tırmanışını kontrol edemeyen bir aracın
imzasıdır — ve tek bir koşu bunu asla gösteremezdi.

## Kampanya, yapı olarak nedir

N adet sıradan koşu dizinine damgalanmış bir kampanya kimliği.

Yeni bir saklama biçimi yok, veritabanı yok. Her yineleme, tek bir uçuşun
ürettiği kanıtın aynısını üretir — kendi `result.json`'ı, kendi dataflash logu,
kendi parmak izi, kendi raporu — ve kampanya belgesi bunların üzerinde her
sorulduğunda yeniden hesaplanan bir toplamdır.

Bu bilinçli bir tercih: koşulardan yeniden hesaplanamayan bir kampanya özeti,
altında hiçbir kanıt olmayan dördüncü bir iddia türü olurdu.

```
runs/
├── 20260810T124500Z_iris/        result.json  ->  "campaign": {"id": ..., "index": 1, "of": 5}
├── 20260810T125130Z_iris/        result.json  ->  "campaign": {"id": ..., "index": 2, "of": 5}
├── …
└── campaigns/
    └── 20260810T124500Z_iris.copter_takeoff/
        ├── campaign.json
        └── campaign.md
```

## Nasıl çalıştırılır

Arayüzden — senaryo panelinin altındaki **Tekrarlanabilirlik kampanyası**: bir
prosedür seç, bir sayı seç, KAMPANYAYI BAŞLAT'a bas. Kampanya çalıştığı sürece
BAŞLAT ve DURDUR'u devralır; çünkü "her koşu kendi bağımsız kanıtını alır"
demek, yineleme başına gerçek bir başlatma ve gerçek bir kapatma demektir —
prosedürün tek bir oturumda beş kez gönderilmesi değil.

Kabuktan, zaten uçurulmuş olanı toplamak için:

```bash
python3 -m argazui campaign                       # diskteki kampanyaları listele
python3 -m argazui campaign <kampanya-id>         # belgeyi yeniden hesapla ve yaz
python3 -m argazui campaign <kampanya-id> --json  # aynısı, makine okuyabilir
```

Çıkış kodları — bu komut CI için tasarlandı:

| kod | anlamı |
|---|---|
| `0` | kampanya toplandı ve her koşu temiz geçti |
| `1` | kampanya var; koşulardan biri veya birkaçı kaldı, kararsızdı ya da yarım |
| `2` | böyle bir kampanya yok |

`2`, `1`'den ayrı tutuluyor; `argazui compare` neden ayrı tutuyorsa o yüzden:
"böyle bir kampanya yok" ile "araç başarısız oldu" farklı haberlerdir.

## Belge neyi raporlar

| | |
|---|---|
| geçen / kalan / kararsız / yarım sayıları | yineleme başına bir tane |
| temiz geçiş oranı | **yalnızca temiz geçişler** — aşağıya bakın |
| metrik başına ortalama, standart sapma, en az, en çok | her birinin yanında örneklem büyüklüğüyle |
| kategoriye göre arızalar | [arıza sınıflandırması](failure-classification.tr.md) kullanılarak |
| tutarlılık denetimi | her yineleme gerçekten aynı şeyi mi uçurdu? |
| koşu başına hüküm | her koşunun kendi dizinine bağlantıyla |

### Yeniden deneme asla geçişe dönüşmez

Yalnızca yeniden denemede geçen bir koşu `flaky`'dir — [`docs/status.md`](status.md)
dosyasında olduğu gibi. Geçiş oranına dahil edilmez. Yeniden denemeleri sessizce
içine alan bir geçiş oranı, aracı değil test düzeneğinin sabrını ölçerdi.

### Söylemeyi reddettiği şey

Beş koşu, beş koşudur. Belge sayıları, bir oranı ve metrik başına dört özet
istatistiği raporlar — ve her birinin yanında örneklem büyüklüğünü yazar.
**Hiçbir güven aralığı, p-değeri ya da güvenilirlik değeri** hesaplamaz; çünkü
n=5'te bunların hiçbiri anlam taşımaz ve hepsi taşıyormuş gibi okunur.

Standart sapma yalnızca **üç ölçülmüş değerden itibaren** raporlanır. Altında
hücre `—` okur; bu, *söylemeye yetecek kadar koşu yok* demektir — *değişim yok*
demek değildir. İki sayının da standart sapması vardır ve hiçbir şey anlatmaz.

### Tutarlılık denetimi

Bir kampanyanın bütün iddiası "aynı şey, N kez"dir ve bu iddia denetlenebilir:
her koşu bir [ortam parmak izi](reproducibility.tr.md) taşır. Belge bunları
karşılaştırır; model yapılandırması, prosedür metni, ArduPilot commit'i ya da
uçan yazılım yinelemeler arasında değiştiyse bunu metrik bölümünün başında
söyler — çünkü ortada yapılan bir düzenlemeden kaynaklanan dağılım, araçtan
kaynaklanan bir dağılım değildir.

## Her yinelemenin başladığı ilk durum

Bir kampanyanın iddiası şudur: *aynı araç, aynı prosedür, aynı yapılandırma, N
kez*. Bu üçünden ikisi ortam parmak izinden denetlenebilir. Üçüncüsü
denetlenemiyordu ve boşluk, simüle aracın kendi hafızasıydı.

SITL'in çalışma dizini `argazui/run/<model_id>/`'dir ve aynı modelin bir
sonraki açılışında yeniden kullanılır — `eeprom.bin` ve `logs/` dosyalarını
ArduPilot ağacının dışında tutan şey budur. Ama bu aynı zamanda her yinelemenin,
bir öncekinin bıraktığı tüm parametrelerle açılması demekti. Modelin
`--add-param-file` dosyası her açılışta yeniden uygulanır, dolayısıyla o
dosyanın adlandırdığı her şey geri gelir; gelmeyen şey, bir prosedürün
değiştirip geri koyamadığı bir parametredir — ki koşucu bunu varsaymak yerine
kaydeder.

Bu nedenle her açılışta `sim_vehicle.py -w` verilir; araç yalnızca beyan
edilmiş parametre dosyalarından başlar. Gerçekten önceki koşunun durumuna
ihtiyaç duyan bir model bunu açıkça bildirir:

```json
{"id": "my_model", "persist_eeprom": true}
```

Her koşu ne yaptığını kendisi yazar; niyet edilenden değil, gerçekten yazılan
komutlardan geri okunarak:

```json
"initial_state": {
  "eeprom_wiped": true,
  "launch_commands": ["source ...", "gz sim ...", "sim_vehicle.py ... -w ..."]
}
```

`eeprom_wiped: null`, ArgazUI'nin SITL komut satırını hiç oluşturmadığı anlamına
gelir — bir `ros2_launch` modeli — ki bu "silinmedi"den farklı bir cevaptır.

## Kampanyanın yapmadıkları

- Hiçbir şeye karar vermez. Geniş bir dağılım hiçbir şeyi düşürmez; metrikler
  ölçümdür, kabul kriteri değil ([Metrikler](metrics.tr.md)).
- Bir referansla karşılaştırmaz. O iş [regresyon
  karşılaştırmasıdır](regression.tr.md) ve N koşuya sorulan tek bir soru değil,
  iki koşuya sorulan farklı bir sorudur.
- Birden fazla model ya da birden fazla prosedür uçurmaz. İki farklı şey
  üzerindeki bir kampanyanın anlamlı bir dağılımı olmaz.

## Kod nerede

| | |
|---|---|
| `argazui/campaign.py` | kimlik, yürütücü, istatistikler, biçimlendirme |
| `argazui/app.py` | sunucunun başlatıcısı; sıradan BAŞLAT/DURDUR yolunu sürer |
| `argazui/runs.py` | `result.json` içindeki `campaign` damgası |

Yürütücü, bir başlatıcıya sahip olmak yerine bir *başlatıcı fonksiyonu* alır;
çünkü bir aracı havaya kaldırmak sunucuda, katman 1'de ve katman 2'de gerçekten
farklıdır. Üçünde de aynı olan — yineleme başına bir koşu dizini, aynı
`ProcedureRunner`, aynı damga, sonda tek bir toplama — sınıfın aynı tutmak için
var olduğu şeydir.

Kampanyalar ArgazUI v1.4 ile eklendi.
