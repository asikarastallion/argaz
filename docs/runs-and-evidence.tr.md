# Koşular ve kanıt

**Koşu**, tek bir modelin bir BAŞLAT … DURDUR döngüsüdür. Geriye
`runs/<UTC-zaman>_<model_id>/` dizinini bırakır; içinde sonradan ne olduğunu
açıklamak için gereken her şey vardır.

## Bir koşu dizininde ne var

| dosya | nedir |
|---|---|
| `scenario.yaml` | çalıştırılan prosedür dosyaları, **birebir** |
| `result.json` | adım adım geçti/kaldı, kabul kriterleri, metrikler, parmak izi |
| `console.log` | simülasyon terminalinde görünenler, ANSI temizlenmiş |
| `mavlink_events.jsonl` | mod/arm/ack/statustext ve 1 Hz durum örneği |
| `<NNNNNNNN>.BIN` | otopilotun kendi dataflash logu |
| `params_full.txt` | logdan alınmış bütün parametreler |
| `params_diff.txt` | **firmware** varsayılanından farklı olanlar |
| `report.md` / `report.json` | uçuş sonrası rapor |
| `fingerprint.json` | sonucu neyin ürettiği — bkz. [tekrarlanabilirlik](reproducibility.tr.md) |
| `evidence.json` | bu koşunun geriye **bırakması beklenen** şeyler ve ne bıraktığı — bkz. [kanıt listesi](evidence-manifest.tr.md) |
| `regression.json` / `.md` | koşu bir referansla karşılaştırıldıysa bulunur |
| `versions.txt` | ArduPilot SHA'sı, Gazebo, ArgazUI, yorumlayıcı |
| `plots/` | irtifa ve tutum takibi PNG'leri — matplotlib kuruluysa |

`result.json` içinde ayrıca adlandırmaya değer iki alan var; ikisi de v1.4 ile
geldi:

- **`failure`** — koşunun neden geçmediği; bir cümle olarak değil, yedi
  kategoriden biri olarak. Geçen bir koşuda `null`'dır ve bilerek asla
  `"category": "none"` değildir. Bkz.
  [Arıza sınıflandırması](failure-classification.tr.md).
- **`campaign`** — bu koşunun hangi tekrarlanabilirlik kampanyasının yinelemesi
  olduğu, ya da `null`. Bir dizin dosyasında değil koşunun içinde tutulur;
  böylece kampanya koşuları okunarak bulunur ve kopyalanmış bir koşu bile
  neye ait olduğunu söyler. Bkz. [Kampanyalar](campaigns.tr.md).
- **`test_id`** (v1.5) — koşunun *ne için* olduğu: bir pytest düğüm kimliği ya
  da elle başlatılmış bir uçuş için `manual`. `manual` gerçek bir cevaptır ve
  asıl önemli olanıdır: bu depodaki hiçbir testin o koşunun gösterdiğini iddia
  etmediğini söyler. Bkz. [İzlenebilirlik](traceability.tr.md).
- **`evidence`** (v1.5) — koşunun kendi kanıtı hakkındaki hüküm: gereken her
  artefaktın mevcut olup olmadığı ve değilse neyin eksik olduğu. Tam liste
  `evidence.json` içindedir.

v1.5'ten itibaren `procedures` içindeki her adım ve her kriter bir `step_id` ve
bir `criterion_id` taşır; böylece bir iddia, durum tablosundan onu destekleyen
dosyaya kadar izlenebilir.

Arıza enjekte etmiş bir koşu, prosedür başına bir **`faults`** listesi de
taşır; içinde birbirinden türetilmeyen dört ayrı şey vardır: mekanizmanın
uygulandığı hâli (hangi parametrelere ne yazıldı, önceki değerleri neydi),
tepki (gerçekte ne kadar, hangi saatte tutuldu ve hangi kanıt geldi),
kriterler ve hüküm. Hiçbiri diğerinden çıkarılmaz, çünkü *başarıyla enjekte
edilmiş bir arıza geçiş değildir*. Bkz.
[Arıza enjeksiyonu](fault-injection.tr.md).

Bir kampanya kendi dizinini yazar:
`runs/campaigns/<kampanya-id>/campaign.json` ve `.md`. Bu, N sıradan koşunun
üzerinde bir toplamdır ve onlardan yeniden hesaplanamayacak hiçbir bilgi
eklemez.

## YAML neden birebir saklanır

Tek kaynak kuralının denetlenebilir hâli budur. `scenario.yaml`, KALKIŞ
butonunun ve regresyon testinin çalıştırdığı dosyanın bayt bayt aynısıdır;
böylece bir koşu, prosedürün hangi sürümünün geçerli olduğunu tahmin etmeye
gerek kalmadan tekrarlanabilir. Parmak izindeki `procedure_hash` da bundan
hesaplanır — o sırada düzenlenmiş olabilecek disk üzerindeki dosyadan değil.

## Neden `argazui/run/<model_id>/` değil

O dizin hâlâ var ve hâlâ SITL'in çalışma dizini — eeprom ve logları ArduPilot
ağacının dışında tutan şey o. Ama aynı modelin bir sonraki başlatılışında
*yeniden kullanılır*, dolayısıyla içindeki hiçbir şey kalıcı değildir. Oturum
durduğunda artefaktlar oradan zaman damgalı koşu dizinine kopyalanır.

## Yakalama akış hâlindedir

`console.log` ve `mavlink_events.jsonl`, koşu sürerken yazılır; sona kadar
tamponlanmaz. ArgazUI uçuşun ortasında öldürülürse dizin yine de o ana kadarki
her şeyi tutar — ki en çok istendiği an tam olarak odur.

## Dataflash logu varsayılmaz, denetlenir

Rapor, ArgazUI'nin sonlandırdığı bir sürecin yazdığı bir logdan üretilir. DURDUR
önce SIGINT gönderir, tam olarak otopilot logunu kapatabilsin diye — ama daha
uzun süreye ihtiyaç duysaydı yazmanın ortasında öldürülür ve rapor sessizce
yarım bir uçuşu kapsardı. Önemli olan kelime *sessizce*. Bu yüzden arşivlenen
her log denetlenir: baştan sona ayrıştırılabilmeli ve son kaydı zaman damgası
taşımalıdır. Yarım bir log yine saklanır ve yine analiz edilir; ama yarım olduğu
raporlanır.

## Eksik log yalnızca "eksik" diye geçilmez, açıklanır

Olağan sebep bir arıza bile değildir: ArduPilot `LOG_DISARMED=0` ile gelir,
dolayısıyla aracın hiç arm olmadığı bir oturum log üretmez. Bu, beklenip
kaybedilmiş bir logdan farklıdır ve
`artefacts.dataflash_absent_reason` hangisi olduğunu söyler.

## Parametre override'ları raporun başındadır

Bir koşu hava aracını yeniden yapılandırdıysa, rapor bunu her ölçümden **önce**
gösterir; çünkü aşağıdaki her sayı stok bir araçta değil, o durumdaki bir araçta
ölçülmüştür. Bir prosedür yalnızca `overrides:` bloğunda gerekçesiyle beyan
ettiği bir parametreyi değiştirebilir ve beyan edilen değerler prosedür nasıl
biterse bitsin geri alınır. Her geri almanın gerçekten başarılı olup olmadığı
kaydedilir: başarısız bir geri alma, aracın o anki durumu hakkında bir olgudur.

## Arayüz olmadan bir koşuyu okumak

```bash
python3 -m argazui runs                       # panelin gösterdiği listenin aynısı
python3 -m argazui report <koşu-dizini>       # uçuş sonrası raporu yeniden üret
python3 -m argazui report <log.BIN>           # çıplak bir logu analiz et
python3 -m argazui compare <koşu> --baseline <koşu>
MAVExplorer.py runs/<id>/<NNNNNNNN>.BIN       # log, ArduPilot'un kendi aracında
```

`runs/` bilerek depoya işlenmez: ArgazUI kullanmanın *çıktısıdır*. CI onu bunun
yerine derleme artefaktı olarak yükler.
