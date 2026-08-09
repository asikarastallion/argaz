# Yapılandırma ve tekrarlanabilirlik

Her koşu, kendisini neyin ürettiğini makine tarafından okunabilir bir bildirim
olarak kaydeder: `runs/<id>/fingerprint.json`. Aynı bildirim `result.json`
içine de gömülür ve `report.md` içinde **Environment** bölümü olarak
görüntülenir.

## Neden bir bildirim, neden sadece versions.txt değil

`versions.txt` "hangi yazılım?" sorusunu zaten yanıtlıyordu: insanın okuması
için düz bir metin listesi. Bakmaya yeter, karşılaştırmaya yetmez.

Aynı modelin iki koşusu bir ArduPilot commit'i, düzenlenmiş bir prosedür,
değişmiş bir parametre dosyası ya da farklı bir Gazebo yüzünden ayrışabilir.
Her koşu bunların hepsini bir programın hizalayabileceği biçimde belirtmedikçe,
aralarındaki karşılaştırma tablo kılığına girmiş bir tahmindir. Parmak izi,
[Regresyon](regression.tr.md) katmanının *"bu ikisi karşılaştırılabilir"*
diyebilmesini sağlar — varsaymak yerine.

## Alanlar

| alan | ne kaydeder |
|---|---|
| `argaz` | ArgazUI sürümü, depo commit'i, `git describe` ve ağaçta commit'lenmemiş değişiklik olup olmadığı |
| `ardupilot.commit` | yapılandırılmış ArduPilot checkout'unun HEAD'i |
| `ardupilot.firmware` | ikili dosyanın kendisi hakkında söylediği; logun `VER`/`MSG` kaydından |
| `ardupilot.firmware_commit` | o metnin içine gömülü commit hash'i |
| `ardupilot.firmware_matches_checkout` | `true`, `false` ya da karşılaştıracak bir şey yoksa `null` |
| `sitl_models` | SITL_Models checkout'unun HEAD'i — checkout olduğunda |
| `gazebo.version` | `gz sim --version` çıktısının ilk satırı |
| `ros.distro` | sunucunun gördüğü hâliyle `ROS_DISTRO` |
| `runtime` | Python, yorumlayıcı yolu, pymavlink, platform |
| `model.config_hash` | modelin kayıt defteri girdisinin **ve adını verdiği her parametre dosyasının** SHA-256'sı |
| `procedure_hash` | çalışan her prosedürün SHA-256'sı; koşunun birebir kaydettiği YAML üzerinden |
| `procedures[]` | prosedür başına: kimliği, beyan ettiği şema ve kendi hash'i |
| `config` | çözümlenmiş ArgazUI yapılandırması — kökler, portlar, yapılandırma dosyası |
| `unknown[]` | belirlenemeyen her alan, gerekçesiyle birlikte |

### `firmware_matches_checkout` üç cevap verir

`null`, gerçek bir üçüncü cevaptır; yumuşatılmış bir "hayır" değildir. Yalnızca
bir logdan üretilmiş, elinde checkout olmayan bir rapor, ikili dosyanın bir
kaynak ağacıyla eşleşip eşleşmediğini gerçekten söyleyemez — ve eşleşme iddia
etmemelidir. `false` olduğunda koşu bayat bir ikili dosyayla uçmuştur ve bu
çözülene kadar başka bir koşuyla karşılaştırılması anlamsızdır; uçuş raporu
bunu birinin fark etmesine bırakmak yerine danışma uyarısı olarak öne çıkarır.

## Bilinmiyor bir cevaptır ve gerekçesiyle gelir

Hiçbir alan makul görünen bir şeyle doldurulmaz. Kimliği belirlenemeyen bir
bileşen `null` olur ve gerekçe `unknown` içinde görünür:

```json
{"field": "sitl_models.commit", "reason": "/opt/SITL_Models is not a git checkout"}
{"field": "gazebo.version", "reason": "unavailable: [Errno 2] No such file or directory: 'gz'"}
```

Alanı sessizce atlayan bir parmak izi, bileşenin sorunsuz olduğu bir makinede
alınmış olanla birebir aynı görünürdü. Bildirimin bütün amacı, bu iki durumun
aynı görünmemesidir.

## Neden commit'lerin yanında içerik hash'leri de var

Commit'ler yalnızca commit sınırında hareket eder. En sık değişen iki girdi ise
değiştiklerinde hiçbir sürüm numarasını hareket ettirmez:

- **çalıştırılan prosedürler**, koşunun birebir kaydettiği YAML üzerinden
  hash'lenir — o sırada zaten düzenlenmiş olabilecek disk üzerindeki dosya
  üzerinden değil;
- **modelin parametre dosyaları**, çünkü değişen bir `.param` hiçbir yerde
  hiçbir commit'i değiştirmeden hava aracını değiştirir.

## Kimlik alanları

Bu alanlardan dördü, iki koşunun sayıları üzerinden karşılaştırılıp
karşılaştırılamayacağına karar verir. Her biri, aracın ya da testin *ne
olduğunu* değiştiren şeylerdir — ne kadar iyi yaptığını değil:

- `model.config_hash`
- `procedure_hash`
- `ardupilot.commit`
- `ardupilot.firmware_commit`

Herhangi birindeki fark, açıkça geçersiz kılınmadıkça karşılaştırmayı
`incomparable` yapar. Taraflardan birinde *bilinmiyor* olması da öyle: bu,
koşuların farklı olduğu iddiası değildir; buradaki hiçbir şeyin aynı olduklarını
gösteremediğinin ifadesidir.

## Koşu başına iki geçiş

Bildirim iki kez alınır; `versions.txt`'in iki kez yazılmasıyla aynı sebeple:
firmware metni ancak dataflash logu ayrıştırıldıktan sonra vardır. İlk geçiş
DURDUR anında çalışır, böylece log üretmemiş bir oturum bile neyin üzerinde
koştuğunu söyler; ikinci geçiş, log okunduktan sonra onun yerine geçer.
