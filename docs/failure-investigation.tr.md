# Arıza inceleme

Bir koşu kırmızıya döndü. Bu sayfa, oradan onu açıklayan dosyaya giden yoldur.

## Mesajla değil, kategoriyle başla

`runs/<koşu-id>/result.json` dosyasını aç ve tek bir alanı oku:

```json
"failure": {
  "category": "vehicle_readiness",
  "code": "arm-refused",
  "detail": "Arm the motors: ARM: REJECTED (MAV_RESULT_FAILED) — autopilot: PreArm: AHRS: waiting for home",
  "source": "steps[1]",
  "procedure": "copter_takeoff"
}
```

Aynı alan [`docs/status.md`](status.md) içindeki **Why** sütununda, Uçuş
Koşuları panelinde hükmün yanındaki rozette ve `report.md` dosyasının başında
bulunur. Bunun yedi incelemeden hangisi olduğunu söyler — her kategorinin ne
anlama geldiği için bkz. [Arıza sınıflandırması](failure-classification.tr.md).

`"failure": null` koşunun geçtiği anlamına gelir. "none" diye bir kategori yok.

## Sonra kategoriyi izle

### `environment` — simülasyon doğru duruma hiç gelmedi

```bash
head -40 runs/<koşu-id>/console.log     # başlatma komutları dosyanın başında
python3 -m argazui doctor               # her ön koşul, her arıza için bir çözüm
```

Koşunun `console.log` dosyasındaki başlatma komutları, yazılan satırların ta
kendisidir. Bir terminale yapıştır: orada ters giden ne varsa burada da aynı
şekilde ters gider ve genellikle eksik bir dünya dosyası, eksik bir parametre
dosyası ya da source edilmemiş bir ortam betiğidir.

Kod `fault-not-applied` ise simülatör beyan edilmiş bir arızayı reddetmiştir —
bkz. [Arıza enjeksiyonu](fault-injection.tr.md). ArgazUI nominal olarak uçurmak
yerine durdu; bu amaçlanan davranıştır, ikinci bir hata değil.

Kod `override-not-applied` ise araç, prosedürün `overrides:` içinde beyan ettiği
bir parametreyi reddetmiştir. Araç, prosedürün gerektirdiği yapılandırmaya hiç
girmedi; o noktadan sonrası anlamsızdır.

### `vehicle_readiness` — araç hazır hâle gelmedi

Otopilot nedenini söyledi. Arızanın `detail` alanında, tamamı da şuralarda:

```bash
grep -i "prearm\|arm:" runs/<koşu-id>/console.log
python3 - <<'PY'
import json, pathlib
for line in pathlib.Path("runs/<koşu-id>/mavlink_events.jsonl").read_text().splitlines():
    event = json.loads(line)
    if event.get("kind") == "statustext":
        print(event["t"], event["text"])
PY
```

ArgazUI üç belirli geçici reddi zaten 35 sn'ye kadar yeniden dener (bkz.
README'deki *Automatic ARM recovery*). Bir `vehicle_readiness` arızası, reddin
bunlardan biri olmadığı ya da geçmediği anlamına gelir.

### `procedure` — bir adım istediğini yapamadı

`source` adımı adlandırır. Önce `result.json` içinde oku, sonra prosedürün
kendisini — ki harfi harfine arşivlenmiştir, yani dosyanın bugün söylediğini
değil koşan sürümü okursun:

```bash
python3 -c "import json;d=json.load(open('runs/<koşu-id>/result.json'));\
print(*(f\"{s['status']:8s} {s['label']}: {s['text']}\" for s in d['procedures'][0]['result']['steps']),sep='\n')"
less runs/<koşu-id>/scenario.yaml
```

Bir `wait_for` üzerindeki `step-timeout` genellikle aracın işi hiç yapmaması
değil yavaş yapması demektir — `report.md` içindeki mod zaman çizelgesi ve
irtifa grafiği hangisi olduğunu gösterir.

### `acceptance` — uçuş koştu ve bir kriter sağlanmadı

Araç hakkında hüküm veren tek kategori budur.

Her kriter yalnızca düştüğünü değil, **gerçekte ne ölçüldüğünü** kaydeder:

```bash
python3 -c "import json;d=json.load(open('runs/<koşu-id>/result.json'));\
print(*(f\"{'OK ' if e['passed'] else 'FAIL'} [{e['kind']}] {e['label']}: {e['text']}\" for e in d['procedures'][0]['result']['expect']),sep='\n')"
```

Ardından `runs/<koşu-id>/report.md` ve grafikleri; bunlar telemetriden değil,
otopilotun kendi dataflash logundan tam hızda üretilir.

Kod `criterion-not-judged` ise kriter, dayandığı telemetri hiç gelmediği için
değerlendirilmemiştir. Bu, aracın yanlış davranmasından farklı bir sorundur ve
genellikle istenmemiş bir akışa ya da düşmüş bir bağlantıya işaret eder — aynı
belgedeki `stability.samples` alanına bak.

### `evidence` — uçtu ve kanıt eksik

```bash
python3 -c "import json;print(json.load(open('runs/<koşu-id>/result.json'))['artefacts'])"
```

`dataflash_absent_reason` neden log olmadığını yazar. En yaygın sebep hiç arıza
değildir: ArduPilot `LOG_DISARMED=0` ile gelir, yani aracın hiç arm etmediği bir
oturum log yazmaz ve kaybolan bir şey yoktur.

`dataflash-truncated`, SITL'in dosyayı kapatmadan öldürüldüğü anlamına gelir.
DURDUR tam da bunun olmaması için önce SIGINT gönderir; yine de olduysa süreç
grubunu başka bir şey öldürmüştür.

`runs-not-comparable` bir uçuştan değil bir regresyon karşılaştırmasından gelir
— bkz. [Regresyon](regression.tr.md) ve `regression.json` içindeki, değişen
alanı adlandıran `configuration_drift` listesi.

### `regression` — hiçbir şey düşmedi ve bir şey kötüleşti

```bash
less runs/<koşu-id>/regression.md
```

Referansı, her metriği, farkı, eşiği ve hükmü adlandırır. Metriğin ne olduğunu
hatırla: kendi eşiği olmayan bir ölçüm ([Metrikler](metrics.tr.md)). Buradaki
bir regresyon bir kriterin düştüğü anlamına gelmez — aracın aynı işi referansa
göre ölçülebilir biçimde daha kötü yaptığı anlamına gelir.

### `infrastructure` — ArgazUI ya da bağlantı bozuldu

Araç hakkında bir hüküm değildir ve asla öyleymiş gibi raporlanmamalıdır. `text`
alanı istisnayı taşır; gerisi tarayıcı konsolunda ve ArgazUI'nin başlatıldığı
terminaldedir.

## Tek bir arıza mı, bir örüntü mü?

Tek bir kırmızı koşu, "bu bozuk" ile "bu bazen düşüyor"u ayırt etmez. Tekrar
tekrar uçur:

```bash
# arayüzden: Tekrarlanabilirlik kampanyası -> prosedürü seç -> KAMPANYAYI BAŞLAT
python3 -m argazui campaign <kampanya-id>
```

Kampanya belgesi geçiş oranını, her metriğin dağılımını ve
`failure_categories`'i — koşular boyunca her türden kaç tane olduğunu —
raporlar. Beşte üç `environment` arızası, beşte üç `acceptance` arızasından
farklı bir tanıdır ve bu sayımlar hangisi olduğunu anlamanın en hızlı yoludur.

Bkz. [Tekrarlanabilirlik kampanyaları](campaigns.tr.md).

## Bu derleme mi, yoksa hep böyle miydi?

```bash
python3 -m argazui compare runs/<güncel> --baseline runs/<bilinen-iyi-koşu>
```

Karşılaştırma; model, prosedür, ArduPilot commit'i ya da uçan yazılım değiştiyse
açıkça söylenmedikçe çalışmayı reddeder — ki bu bazen cevabın kendisidir. Bkz.
[Regresyon](regression.tr.md) ve [Tekrarlanabilirlik](reproducibility.tr.md).

## Yapılmaması gerekenler

- **Bir koşuyu yeşile döndürmek için kriteri gevşetme.** Kendi testi geçsin diye
  aracı ya da sınırları ayarlayan bir test aracı hiçbir şey kanıtlamaz. Bir
  prosedürün yaptığı her parametre değişikliği gerekçesiyle beyan edilmek
  zorundadır ve bu kural tam olarak bu ayartma için vardır.
- **Bir atlamayı geçiş sayma.** Atlanan bir test modeli `untested` olarak
  kaydeder; bu, hiçbir şeyin kanıtlanmadığı anlamına gelir — bir şeyin yanlış
  olmadığı değil.
- **Bir danışma uyarısını sebep sanma.** Danışma uyarıları dataflash logundan
  çıkan sağlık bulgularıdır ve bir hükmü asla değiştirmez. Gürültülü bir hava
  aracı, bir kriterin düşme sebebi değildir.
