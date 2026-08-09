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
| `regression.json` / `.md` | koşu bir referansla karşılaştırıldıysa bulunur |
| `versions.txt` | ArduPilot SHA'sı, Gazebo, ArgazUI, yorumlayıcı |
| `plots/` | irtifa ve tutum takibi PNG'leri — matplotlib kuruluysa |

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
