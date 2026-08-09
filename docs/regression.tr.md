# Regresyon

Bir koşu, kabul kriterlerinin sağlanıp sağlanmadığını söyler. Bu, tek bir uçuş
hakkında, birinin beyan ettiği sınırlara karşı verilmiş bir hükümdür ve bir
simülasyon projesinin aylar içinde gerçekten başına gelen şeyi göremez: **her
kriter hâlâ geçiyordur ve hava aracı sessizce daha kötü uçuyordur.** Takip
hatası tırmanır, tırmanış dört saniye uzar, eskiden 100 ms'de doğrulanan bir mod
değişimi iki saniye sürer.

Hiçbir şey düşmez ve bir şeyler yanlıştır. Bir koşunun
[metriklerini](metrics.tr.md) adı konmuş bir referansla karşılaştırmak, bunu
görünür kılmanın yoludur.

## Nasıl çalıştırılır

```bash
# açık referans — CI'ın yapması gereken budur
python3 -m argazui compare runs/20260809T101500Z_iris \
        --baseline runs/20260801T090000Z_iris

# kolaylık: aynı modelin en yeni önceki koşusu
python3 -m argazui compare runs/20260809T101500Z_iris

# firmware ya da prosedür değişmiş olsa da karşılaştır
python3 -m argazui compare <güncel> --baseline <referans> --ignore-config-drift
```

`regression.json` ve `regression.md` dosyalarını güncel koşunun dizinine yazar.
Arayüz aynı işlemi `GET /api/runs/<id>/compare` üzerinden sunar.

## Çıkış kodları

| kod | anlamı |
|---|---|
| `0` | hiçbir metrik eşiğini aşacak kadar kötüleşmedi |
| `1` | en az biri kötüleşti — **regresyon sinyali budur** |
| `2` | koşular karşılaştırılamadı ya da okunamadı |

`2`, `1`'den bilerek ayrıdır. "Bu koşular hizalanmıyor", "bu derleme kötüleşti"
ile aynı haber değildir; ikisini aynı sayan bir hat, er ya da geç yanlış
belirtilmiş bir referansı regresyon olarak raporlar.

## İki koşu, var oldukları için karşılaştırılabilir olmaz

Katı olması gereken kısım budur ve [ortam parmak
izinin](reproducibility.tr.md) varlık sebebi de budur. Farklı bir model, farklı
bir prosedür, farklı bir ArduPilot ya da düzenlenmiş bir parametre dosyası
üzerinden yapılan bir karşılaştırma hiçbir şeyin ölçümü değildir — birbiriyle
ilgisiz iki sayının çıkarılmasıdır.

**Kesin olarak karşılaştırılamaz** — geçersiz kılacak bir bayrak yoktur:

- farklı model,
- farklı prosedür kümesi,
- taraflardan birinde hiç metrik olmaması (v1.3 öncesi bir koşu ya da uçuş
  raporu hiç üretilmemiş bir koşu — `argazui report <koşu>` bunu düzeltir).

**Yapılandırma kayması** — alan alan raporlanır ve varsayılan olarak
`incomparable` yapar:

- prosedür içerik hash'i değişti,
- model yapılandırması ya da parametre dosyalarından biri değişti,
- ArduPilot checkout'u ya da firmware ikili dosyası değişti,
- bunlardan biri taraflardan birinde bilinmiyor.

`--ignore-config-drift` yine de karşılaştırır ve neyin değiştiğini yine yazar;
çünkü "firmware'i değiştirdim, bunun sayılara ne yaptığını görmek istiyorum"
gerçek bir sorudur. Sadece yüksek sesle sorulması gerekir.

Hiçbir şey sessizce karşılaştırılmaz.

## Hükümler

Metrik başına: `improved`, `degraded`, `unchanged`, `incomparable`.
Genel: `passed`, `regressed`, `incomparable`.

Bir metrik, **bağıl toleransından** *ya da* **mutlak tabanından** daha az
hareket ettiyse `unchanged` olur.

### Neden yüzdenin yanında bir taban da var

0,02° olan bir RMS takip hatasının 0,04° olması %100 artıştır ve hiçbir şey
ifade etmez: iki sayı da gürültüdür. Yalnızca bağıl değişime bakmak, mühendislik
anlamında birbirinin aynısı olan büyüklükler yüzünden CI'ı kırmızıya boğardı.
Taban, kabaca her ölçümün anlam kazandığı çözünürlüktür.

Tam olarak sıfır olan bir referansın yüzdesi zaten yoktur ve o durumda tek
sınama tabandır — ki taban tam olarak bu durum için eklenmiştir.

## Eşikler

Varsayılanlar: %10 bağıl, artı metrik başına bir taban. %10 bir doğa yasası
değildir; aynı gövdenin tekrarlanan katman-1 kalkışlarında ölçülmüş olarak,
SITL'in kendi koşudan koşuya saçılımının baskın hâle geldiği noktadır.

| metrik | taban |
|---|---|
| `time_to_target_alt` | 0,5 sn |
| `tracking_error_roll_max` / `_pitch_max` | 1,0° |
| `tracking_error_roll_rms` / `_pitch_rms` | 0,1° |
| `peak_angular_rate` | 2,0 °/sn |
| `time_outside_attitude_envelope` | 0,2 sn |
| `mode_transition_latency_max` | 0,1 sn |

`argaz.toml` içinden değiştirilir:

```toml
[regression]
default_tolerance = 0.10

[regression.tolerance]
peak_angular_rate = 0.25

[regression.floor]
time_to_target_alt = 1.0
```

## Veritabanı yok

Referans bir koşu dizinidir. Karşılaştırmalar `result.json` okur ve güncel
koşunun yanına `regression.json` yazar. Depolama tasarımının tamamı budur ve
bilerek öyledir: bir karşılaştırmanın kanıtı, bir uçuşun kanıtıyla aynı
araçlarla okunabilmelidir.

## Regresyon ne değildir

Metrikler ölçümdür, kabul kriteri değil. Buradaki bir regresyon, bir kriterin
düştüğü anlamına gelmez. Aracın aynı işi, referansa göre ölçülebilir biçimde
daha kötü yaptığı anlamına gelir — bakmak için bir sebeptir, bazen de referansı
ilerletmek için.
