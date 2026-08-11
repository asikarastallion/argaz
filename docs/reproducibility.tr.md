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

Bu alanlar, iki koşunun sayıları üzerinden karşılaştırılıp
karşılaştırılamayacağına karar verir. Her biri, aracın ya da testin *ne
olduğunu* değiştiren şeylerdir — ne kadar iyi yaptığını değil:

| alan | değişmesi ne demek |
|---|---|
| `model.config_hash` | kayıt girdisi ya da bir parametre dosyası değişti — başka bir araç |
| `procedure_hash` | akış ya da bir kabul kriteri değişti — başka bir test |
| `ardupilot.commit` | farklı bir ArduPilot çalışma kopyası |
| `ardupilot.firmware_commit` | gerçekte farklı bir ikili dosya uçtu |
| `argaz.dirty_digest` | ArgazUI'de farklı commit'lenmemiş değişiklikler |
| `ardupilot.dirty_digest` | ArduPilot'ta farklı commit'lenmemiş değişiklikler |
| `gazebo.version` | farklı bir simülatör — fiziğin yarısı |

Herhangi birindeki fark, açıkça geçersiz kılınmadıkça karşılaştırmayı
`incomparable` yapar. Taraflardan birinde *bilinmiyor* olması da öyle: bu,
koşuların farklı olduğu iddiası değildir; buradaki hiçbir şeyin aynı olduklarını
gösteremediğinin ifadesidir.

Son üçü v1.6 düzeltme sürümünde eklendi. Üçü de zaten kaydediliyordu ama hiçbiri
karşılaştırılmıyordu; dolayısıyla bir Gazebo yükseltmesinin iki yakasındaki — ya
da iki farklı commit'lenmemiş değişiklik kümesiyle uçurulmuş — koşular kendilerini
aynı yapılandırma olarak bildiriyordu.

### `dirty` neden bir bayrak değil, bir özet

Bir commit, bir çalışma kopyasını tanımlamaz. `dirty: true`, ağaçta değişiklik
olduğunu söyler ama *hangisi* olduğunu söyleyemez; bu yüzden iki farklı yarım
kalmış çalışma durumundan uçurulmuş iki koşu aynı kimliğe sahipti — oysa TEK bir
kirli ağaçtan dakikalar arayla uçurulan iki koşu gayet karşılaştırılabilirdir ve
reddedilmemelidir. Bir mantıksal değer ikisini birden ifade edemez; commit'lenmemiş
işin içerik özeti edebilir. Temiz bir çalışma kopyası, `clean` yazar — bu bir
belirlemedir, belirlemenin yokluğu değil, dolayısıyla `null` değildir.

Özet, izlenen dosyaların farkını ve izlenmeyenlerin ADLARINI kapsar. İzlenmeyen
dosyaların içeriği bilerek hash'lenmez: bu koca bir derleme ağacı olabilir ve
okuma maliyeti, `model.config_hash`'in zaten kapsadığı bir durumu yakalamak için
her koşuya binerdi.

## Koşu başına iki geçiş

Bildirim iki kez alınır; `versions.txt`'in iki kez yazılmasıyla aynı sebeple:
firmware metni ancak dataflash logu ayrıştırıldıktan sonra vardır. İlk geçiş
DURDUR anında çalışır, böylece log üretmemiş bir oturum bile neyin üzerinde
koştuğunu söyler; ikinci geçiş, log okunduktan sonra onun yerine geçer.
