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

## Regresyon kapısı eklemek

`argazui compare` tam olarak bunun için yazıldı: regresyon yoksa `0`,
kötüleşme varsa `1`, karşılaştırılamayan koşular için `2`. Bkz.
[Regresyon](regression.tr.md).

```yaml
- name: Referansla karşılaştır
  run: |
    python3 -m argazui compare "runs/$CURRENT" --baseline "runs/$BASELINE"
```

Referansı açıkça ver. Referanssız biçim aynı modelin en yeni önceki koşusunu
seçer; bu arayüz için bir kolaylıktır — bir hatta ise karşılaştırmanın neye
karşı yapıldığını o gün diskte ne varsa ona bağımlı kılardı.

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
