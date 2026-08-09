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

| anahtar | birim | kapsam | türetildiği kaynak |
|---|---|---|---|
| `time_to_target_alt` | sn | prosedür | `POS.RelHomeAlt`, prosedürün istediği irtifaya karşı; arm anından itibaren |
| `tracking_error_roll_max` | ° | koşu | `ATT.DesRoll - ATT.Roll` |
| `tracking_error_pitch_max` | ° | koşu | `ATT.DesPitch - ATT.Pitch` |
| `tracking_error_roll_rms` | ° | koşu | aynı fark, karekök ortalama |
| `tracking_error_pitch_rms` | ° | koşu | aynı fark, karekök ortalama |
| `peak_angular_rate` | °/sn | koşu | `IMU.GyrX/GyrY/GyrZ`, herhangi bir eksendeki en büyük genlik |
| `time_outside_attitude_envelope` | sn | koşu | `ATT.Roll`/`ATT.Pitch`, prosedürün beyan ettiği zarfa karşı |
| `mode_transition_latency_max` | sn | prosedür | her `set_mode` adımının kayıtlı süresi; adım, heartbeat yeni modu **numara üzerinden** doğrulayınca biter |

Bunların hepsi düşükken daha iyidir, ama yön her metrik için varsayılmaz,
açıkça kaydedilir: "küçük olan iyidir"i koda gömen bir karşılaştırıcı,
"korunan irtifa" gibi bir metrik eklendiği ilk anda ters sonuç raporlar.

### Neden bu kadar küçük bir küme

Buradaki her satır, bir uçuşa gerçekten sorulan bir soruyu yanıtlar ve
türetildiği sinyalin adını verir. Hesaplanabilecek her şeyi hesaplayan bir
modül, anlamı belirtilmemiş bir sayı duvarı üretirdi ve ilk regresyon
karşılaştırması, kimsenin izlemeyi seçmediği büyüklüklerin gürültüsünde
boğulurdu.

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
