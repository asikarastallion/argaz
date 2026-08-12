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
| `ardupilot.dirty_digest` | ArduPilot'ta farklı commit'lenmemiş değişiklikler |
| `gazebo.version` | farklı bir simülatör — fiziğin yarısı |
| `sitl_models.pin.identity` | farklı model varlıkları — farklı bir hava aracı |

Herhangi birindeki fark, açıkça geçersiz kılınmadıkça karşılaştırmayı
`incomparable` yapar. Taraflardan birinde *bilinmiyor* olması da öyle: bu,
koşuların farklı olduğu iddiası değildir; buradaki hiçbir şeyin aynı olduklarını
gösteremediğinin ifadesidir.

Son ikisi v1.6 düzeltme sürümünde eklendi. İkisi de zaten kaydediliyordu ama
karşılaştırılmıyordu; dolayısıyla bir Gazebo yükseltmesinin iki yakasındaki — ya
da iki farklı commit'lenmemiş ArduPilot değişikliği kümesiyle uçurulmuş —
koşular kendilerini aynı yapılandırma olarak bildiriyordu.

`argaz.dirty_digest` kaydedilir ama bilerek karşılaştırılmaz; gerekçesi
`argaz.commit`'inkiyle aynıdır: ArgazUI'nin kendi kaynağı araç değil, koşum
takımıdır ve birini diğeri olmadan karşılaştırmak kuralın yarısı olurdu.

### Her iki koşuda da bulunmayan bir bileşen bir fark değildir

Bilinmeyen bir kimlik alanı normalde fark olarak bildirilir: hiçbir şey iki
koşunun aynı olduğunu göstermez ve bir karşılaştırma tam olarak bunun üzerinden
sessizce yapılmamalıdır. Bileşen ortamda hiç yoksa bu okuma yanlıştır: katman
1'de tasarım gereği Gazebo yoktur, dolayısıyla iki koşu da aynı yapısal nedenle
`null` bildirir ve alan hiçbir şeyi ayırt etmez.

Bu yüzden `gazebo.version`, **her iki** tarafta da bilinmiyorsa muaftır —
yalnızca o durumda; tek tarafta bilinmemesi gerçek bir asimetridir ve
bildirilmeye devam eder. Muafiyet genel bir kural değil, adı konmuş bir kümedir
(`OPTIONAL_IDENTITY`): `ardupilot.firmware_commit` de bir katman 1
karşılaştırmasının iki tarafında birden null'dur ve bu her zaman
karşılaştırılamaz sayılmıştır, öyle de kalır.

## Sabitlenmiş model ortamı

`ardupilot`, ilk katman imajından beri her iki Dockerfile'da SHA ile
sabitlenmiştir ve gerekçesi orada yazılıdır: bir dala takılan bir imaj her
derlemede farklı bir otopilot uçururdu ve hiçbir iki CI sonucu
karşılaştırılamazdı. Katman 2'nin doğrulamak için var olduğu her hava aracının,
dünyanın, mesh'in ve parametre dosyasının kaynağı olan `SITL_Models` ise HEAD'den
klonlanıyordu; yani ortamın yarısı hâlâ hareket hâlindeydi.

Parmak izi v1.3'ten beri `sitl_models.commit` kaydeder; yani sapma *olaydan
sonra görünürdü*. Bu tekrarlanabilirlik değildir: okuyucuya baktığı deneyin
tekrarlanamayacağını söyler ve bunu, bilmesi gerektiğinden geç söyler.

### Beyan

```toml
[model_environment]
repository = "https://github.com/ArduPilot/SITL_Models.git"
revision   = "25bc38ed8c6c0345840159a8cbc0b02781d52f3c"
```

`ARGAZ_SITL_MODELS_REF` bunu geçersiz kılar ve diğer her ayarın kullandığı
öncelik zincirini izler. `docker/Dockerfile.tier2` tam olarak o SHA'yı çeker ve
derleme anında doğrular; test takımı da iki beyanın uyuştuğunu denetler — tek
bir olgunun iki beyanı zamanla ayrışır ve bu ayrışma sessiz olurdu.

**`revision` tam bir commit SHA'sı ya da değişmez bir etiket olmalıdır.**
`HEAD`, `main`, `master`, `latest` ve `current` doğrudan reddedilir; çünkü
bugün orada ne varsa onu adlandırırlar ve bir sabitlemenin anlamına
gelemeyeceği tek şey budur. Bunlardan birini adlandıran bir beyan, bir
sabitleme değil, bir yapılandırma hatasıdır.

### Altı durum

| durum | anlamı | kullanılabilir | tekrarlanabilir |
|---|---|:-:|:-:|
| `pinned` | beyan edildi, çözüldü ve aynılar | evet | **evet** |
| `unpinned` | beyan yok; koşu bu yokluğu kaydeder | evet | hayır |
| `modified` | beyan edilen revizyon, üzerinde işlenmemiş değişikliklerle | evet | hayır |
| `mismatch` | beyan edildi ve çözüldü, ve farklılar | **hayır** | hayır |
| `unresolved` | beyan edildi, ve checkout ne olduğunu söyleyemiyor | **hayır** | hayır |
| `invalid` | beyan, hareket eden bir şeyi adlandırıyor | **hayır** | hayır |

İki eşik var, çünkü iki soru var. *Beyana uyuluyor mu?* ile *bu ortam
tekrarlanabilir mi?* aynı soru değildir ve ikisini birleştirmek denetimi ya
işe yaramaz ya da kullanılamaz kılar.

`unpinned` kullanılabilirdir; çünkü beyansız çalışan bir geliştirici hiçbir şeyi
ihlal etmemiştir — koşu, olmayan bir sabitlemeyi uydurmak yerine yokluğu
kaydeder. `modified` ise `dirty`'nin neden özete dönüştüğüyle aynı gerekçeyle
kullanılabilirdir: beyan edilen revizyon *elde edilmiştir*, üzerindeki
değişiklikler kimliğe karıştırılır; yani aynı değişikliklere sahip iki koşu hâlâ
aynı deneydir. Değişiklik içeren her çalışma ağacını reddetmek, mekanizmayı tam
da en çok istendiği işin sırasında kullanılamaz kılardı.

`python3 -m argazui doctor --release` yalnızca `pinned` kabul eder ve
`tier2.yml` bunu tek bir model başlatılmadan önce koşturur.

### Arıza bir ortam arızasıdır

Elde edilemeyen bir revizyon **HEAD'e geri düşmez**. Koşu, hiçbir şey uçmadan
önce, ortam katmanında bir yapılandırma sorunu olarak başarısız olur — böylece
hiçbir model bunun yüzünden `failed` diye kaydedilmez ve hiçbir hava aracı bir
checkout yüzünden suçlanmaz. Bkz.
[Simülasyon yaşam döngüsü](simulation-lifecycle.tr.md).

Hiçbir şey fetch, checkout ya da pull yapmaz. `modelenv.reconcile_command()`,
bir kişinin koşacağı `git checkout` komutunu yazdırır; onu asla çalıştırmaz. Bir
denetimin geçmesi için kendi girdilerini yeniden düzenleyen bir araç, o
denetimi ortadan kaldırmıştır.

### Bir koşu neyi kaydeder

İkinci bir depoda değil, mevcut parmak izinin içinde:

```json
"sitl_models": {
  "commit": "25bc38ed8c6c0345840159a8cbc0b02781d52f3c",
  "pin": {
    "repository":      "https://github.com/ArduPilot/SITL_Models.git",
    "revision":        "25bc38ed8c6c0345840159a8cbc0b02781d52f3c",
    "revision_kind":   "commit",
    "resolved_commit": "25bc38ed8c6c0345840159a8cbc0b02781d52f3c",
    "identity":        "sha256:f12cd220cd53e7587ba770a49da0774e",
    "state": "pinned", "ok": true, "reproducible": true, "reason": ""
  }
}
```

Karşılaştırma `commit` yerine `identity` kullanır; çünkü kimlik, çalışma ağacı
özetini de içerir — `dirty` yerine `dirty_digest`'i kimlik alanı yapan gerekçe
aynısıdır.

### Beyan edilmiş bir override, hava aracının parçasıdır

**Kural: üçüncü taraf checkout'u, upstream'in yayımladığı hâliyle kalır; projeye
özgü hava aracı yapılandırması ise Argaz'ın beyan edilmiş override katmanına
aittir.** Argaz'ın ihtiyaç duyduğu ama upstream'in atamadığı bir değeri beyan
etmek Argaz'ın işidir; upstream'in dosyasını düzenlemek değil. Checkout içinde
yapılan bir düzenleme, hiçbir hash'i değiştirmeden uçanı değiştirir ve yalnızca
onu yapan makinede vardır.

`models.json` içindeki `sitl_param_overrides`, her başlatmada ikinci bir
`--add-param-file` olarak yazılır ve modelin kendi dosyasından sonra
uygulandığı için üstün gelir. Yalnızca açılışta etkili olabilen ve üstkaynak
dosyanın yanlış verdiği ya da hiç vermediği parametreler için vardır —
`swan_k1_hwing`, dosyası `AHRS_EKF_TYPE=3` isteyip EK3'ü kapalı bıraktığı için
`EK3_ENABLE=1` gerektirir.

`alti_transition_quad` ikinci durumdur. Üstkaynaktaki
`Gazebo/config/alti_transition_quad.param` 33 adet `Q_*` parametresi taşır ve
QuadPlane alt sistemini açan ana anahtar olan `Q_ENABLE`'ı atlar — o
checkout'taki diğer her quadplane onu açıkça verir (`skycat_tvbs`,
`skywalker_x8_quad`, `swan_k1_hwing` hepsi `Q_ENABLE 1`; `wsc_aircraft` ise
uçak olduğu için `Q_ENABLE 0`). O olmadan ArduPlane 33 parametrenin hepsini
yok sayar ve araç, bir VTOL adı altında sabit kanat olarak uçar.

Bir süre bu depo onu **üçüncü taraf checkout'a işlenmemiş bir değişiklik**
olarak taşıdı; bu, mümkün olan en kötü yerdir: uçanı değiştiriyordu,
`model.config_hash` için görünmezdi ve model ortamını kalıcı olarak `modified`
yapıyordu. Artık sürümlenen, gözden geçirilebilen ve özetlenen `models.json`
içinde beyan ediliyor.

`sitl_param_overrides`'ın `MODEL_RECORD_KEYS` içinde olmasının nedeni budur.
Uygulanıyor ama arşivlenmiyordu; dolayısıyla `model.config_hash` içinde de
değildi: farklı override'larla uçurulan iki koşu — bir quadplane ve aynı
dosyanın override'sız tarif ettiği sabit kanat — tek bir yapılandırma olarak
karşılaştırılıyordu. Arşivlemek iki yarımı birden düzeltir, çünkü özet tam
olarak arşivlenen şey üzerinden alınır. Koşunun saklamadığı bir alan onu
tanımlamamalı, hava aracını değiştiren bir alan ise saklanmalıdır.

## Süreç ve port yalıtımı

Bir portu paylaşan iki koşu bir deneyi paylaşmıyordu. Çöken bir sunucu
`gz sim`, SITL ve MAVProxy süreçlerini 14550'i tutar hâlde bırakırdı; sonraki
BAŞLAT ise onların yanında `udpin:14550` portuna bağlanır ve *önceki* aracın
telemetrisini alabilirdi — kanıtı, içindeki hiç kimsenin başlatmadığı bir
araçtan gelen bir koşu.

Artık her koşu, hiçbir şey başlatmadan önce bir sınır beyan eder ve durduktan
sonra onu yeniden denetler:

```json
"isolation": {
  "session_id": 481923,
  "ports": {"mavlink": 14550, "script_mavlink": 14551, "plotjuggler": 14552},
  "conflicts_at_start": [],
  "released": true,
  "survivors": []
}
```

Sahiplik çekirdek tarafından kurulur — oturum kimliği, süreç grubu kimliği ve
bir portu tutan soket inode'u — asla bir süreç adıyla değil. Bu koşunun
başlatmadığı bir tutucu **raporlanır ve asla sinyallenmez**: başka bir
terminalde kendi SITL'ini 14550'de koşturan bir geliştirici, ölü bir süreç
değil, açık bir mesaj alır. `pkill -f` hâlâ hiç kullanılmaz ve sahiplik
katmanının herhangi bir şeye sinyal gönderecek hiçbir yolu yoktur.

`released: true`, temizliğin işlediği iddiasıdır ve varsayılmak yerine
denetlenir — `/proc`'a göre süreçler gitmiştir ve gerçek bir bind'a göre
portlar boştur.

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
