# Metrikler

Metrik, uçuşun zaten ürettiği kanıttan türetilmiş bir sayıdır. Kabul kriteri
**değildir** ve bir koşuyu düşüremez.

Bu ayrım, danışma uyarılarının hâlihazırda sahip olduğu ayrımın aynısıdır:

| | karar veren | koşuyu düşürebilir mi? | eşiğin kaynağı |
|---|---|---|---|
| kabul kriterleri | prosedürün `expect:` bloğu | **evet** | prosedür |
| danışma uyarıları | `flightlog.py` | hayır | ArduPilot dokümantasyonu |
| metrikler | `metrics.py` | hayır | hiçbiri — karşılaştırılana kadar |

Bir metrik eşiğe ancak bir referansla karşılaştırıldığında kavuşur; bkz.
[Regresyon](regression.tr.md). Burada eşik vermek, hiçbir prosedürde beyan
edilmemiş sınırlarla ikinci bir kabul sistemi kurmak olurdu.

## Katalog

| anahtar | birim | saat | pencere | kapsam | türetildiği kaynak |
|---|---|---|---|---|---|
| `time_to_target_alt` | sn | araç | armlı | prosedür | `POS.RelHomeAlt`, prosedürün istediği irtifaya karşı; arm anından itibaren |
| `tracking_error_roll_max` | ° | araç | log | koşu | `ATT.DesRoll - ATT.Roll` |
| `tracking_error_pitch_max` | ° | araç | log | koşu | `ATT.DesPitch - ATT.Pitch` |
| `tracking_error_roll_rms` | ° | araç | log | koşu | aynı fark, karekök ortalama kare |
| `tracking_error_pitch_rms` | ° | araç | log | koşu | aynı fark, karekök ortalama kare |
| `peak_angular_rate` | °/sn | araç | log | koşu | `IMU.GyrX/GyrY/GyrZ`, herhangi bir eksendeki en büyük genlik |
| `time_outside_attitude_envelope` | sn | araç | armlı | koşu | `ATT.Roll`/`ATT.Pitch`, prosedürün beyan ettiği zarfa karşı; logun armlı aralık(lar)ı üzerinden |
| `mode_transition_latency_max` | sn | araç | prosedür | prosedür | her `set_mode` adımının **aracın kendi saatindeki** süresi; heartbeat yeni modu numarayla doğruladığında biter |

Bunların hepsi düşükken daha iyidir, ama yön her metrik için varsayılmaz,
açıkça kaydedilir: "küçük olan iyidir"i koda gömen bir karşılaştırıcı,
"korunan irtifa" gibi bir metrik eklendiği ilk anda ters sonuç raporlar.

### Neden bu kadar küçük bir küme

Buradaki her satır, bir uçuşa gerçekten sorulan bir soruyu yanıtlar ve
türetildiği sinyalin adını verir. Hesaplanabilecek her şeyi hesaplayan bir
modül, anlamı belirtilmemiş bir sayı duvarı üretirdi ve ilk regresyon
karşılaştırması, kimsenin izlemeyi seçmediği büyüklüklerin gürültüsünde
boğulurdu.

## Saat ve pencere

İki saniye değeri, ancak aynı saatte ve uçuşun aynı bölümü üzerinden alınmışsa
aynı büyüklüktür. İkisi de metrik başına belirtilir ve `result.json` içinde
değerle birlikte taşınır; böylece sonradan yazılan bir karşılaştırmanın bunları
bugünkü koda sorması gerekmez.

| saat | |
|---|---|
| `vehicle` | aracın kendi saati — dataflash `TimeUS` ya da canlı `ATTITUDE.time_boot_ms`. Yayımlanan her metrik bu saattedir. |
| `wall` | bu sürecin saati. Yalnızca ölçüm sırasında aracın saati ilerlemiyorsa, dürüst bir geri düşüş olarak kaydedilir. |

SITL hız çarpanı altında bir duvar saati saniyesi bir uçuş saniyesi değildir;
ikisi hız çarpanı kadar ayrışır. `mode_transition_latency_max`, v1.6 düzeltme
sürümüne kadar ana makinenin saatindeydi — logdan değil, kaydedilmiş bir
adımdan türetilen tek metrik — dolayısıyla farklı hız çarpanlarıyla uçurulmuş
iki koşuyu karşılaştırmak, sebebi yalnızca bir komut satırı seçeneği olan bir
regresyon bildiriyordu.

| pencere | |
|---|---|
| `procedure` | bir prosedürün ilk adımından son kriterine kadar |
| `armed` | dataflash logunun kaydettiği armlı aralık(lar) — uçuşun kendisi |
| `log` | logdaki her kayıt; yerde geçen süre dahil |

`time_outside_attitude_envelope` ile `attitude_stable` kabul kriteri bir adı ve
bir bant kümesini paylaşır ama **pencereyi paylaşmaz**: kriter kendi
prosedürüyle, metrik ise logun armlı aralık(lar)ıyla sınırlıdır. Düzeltme
sürümünden önce metrik tüm logu kapsıyordu; bu yüzden [55,115]° yunuslama bandı
olan bir tailsitter, pistte hareketsiz durduğu her saniye "zarfın dışında"
sayılıyordu — ve ikisi aynı uçuş için 0,0 sn ile 40 sn diyebiliyor, farklı
sorulara yanıt verdiklerini hiçbir şey söylemiyordu. Artık birlikte
okunabilecek kadar yakınlar ve kalan farkı `window` alanı belirtir.

`argazui compare`, bu iki alandan birinde anlaşmayan iki metriği birbirinden
çıkarmayı reddeder ve hangisi olduğunu söyler.

## Kimlik

Bir metrik, `key` değeri ile `procedure` değerinin bileşimiyle tanımlanır.

- **Koşu kapsamlı** metrikler, oturumun tamamını kapsayan dataflash logundan
  gelir ve prosedür taşımaz.
- **Prosedür kapsamlı** metrikler ait oldukları prosedürün adını taşır. "Hedef
  irtifaya ulaşma süresi", kimin hedefi olduğu söylenmeden bir şey ifade etmez.

## Logun bildiği ve bilmediği

Dataflash logu aracın ne yaptığını bilir. Araca ne yapması *söylendiğini*
bilmez. Hedef irtifalar, beyan edilen tutum zarfı ve ölçülmüş mod değişim
süreleri koşunun kendi `result.json` dosyasından gelir; `flightlog.py` ile
prosedür sistemi arasındaki tek bağ budur.

## Yokluk sıfır değildir

Türetilemeyen bir metrik dışarıda bırakılmaz; `value: null` ve belirtilmiş bir
gerekçeyle yazılır — "bu koşudaki hiçbir prosedür hedef irtifa beyan etmedi",
"log IMU kaydı taşımıyor". Okuyucu için eksik bir satırla yapılamamış bir ölçüm
birbirinin aynısı görünür ve bunlardan yalnızca biri bir olgudur.

## Nerede görünürler

| | |
|---|---|
| `runs/<id>/report.json` | tam liste, hesaplandığı serilerle birlikte |
| `runs/<id>/report.md` | **Metrics** başlığı altında bir tablo |
| `runs/<id>/result.json` | aynı liste; karşılaştırma koşu başına tek belge okusun diye kopyalanır |
| `runs/<id>/regression.json` | referans ile güncel, metrik başına bir hükümle |

Metrikler ArgazUI v1.3 ile eklendi. Daha önce kaydedilmiş bir koşuda yoktur;
`argazui report <koşu>` bunları zaten arşivlenmiş logdan yeniden üretir.
