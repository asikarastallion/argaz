# Arıza enjeksiyonu

İki arıza, yalnızca iki: **GPS**'in bozulması ya da tamamen gitmesi, ve yer
istasyonuna giden **MAVLink bağlantısının** kesilmesi ya da kayıplı hâle
gelmesi.

Bunlar, bir prosedürün nominal bir uçuşun soramadığı soruyu sorabilmesi için
var — *bu araç bir şey ters gittiğinde ne yapar* — ve bu soruyu, nominal bir
uçuşun ürettiği kanıt zincirinin aynısıyla yanıtlamak için.

## Neden bu kadar az

Genel bir arıza DSL'i yazmak bir hafta sürer ve kimsenin bir aracın tepkisini
izlemediği senaryolar üretir. Bu ikisi şu üç özelliği taşıdıkları için seçildi:

- ArduPilot'un kendi SITL'inin zaten sağladığı ya da ArgazUI'nin gerçekten
  sahip olduğu bir mekanizma;
- varsayılan değil *ölçülen* bir gözlenebilir;
- gerçek uçuşta karşılaşılan bir arıza biçimi.

Rüzgâr, motor kaybı ve rastgele sensör bozulması bilerek **uygulanmadı**.
Birileri gerçekten koşmak istediği bir senaryo ve birilerinin savunabileceği bir
kriter ortaya çıktığında uygulanacaklar — listenin kısa görünmesi bir sebep
değil.

## Beş kural

Her biri, tersi tehlikeli olduğu için var.

### 1. Yalnızca simülasyon

Her mekanizma ya bir `SIM_*` parametresi yazar ya da ArgazUI'nin kendi soket
davranışını değiştirir. Buradan donanıma giden bir yol yoktur — ve buradaki
hiçbir şey simülatörde olmaya *bağlı* değildir; mekanizmalar simülatör dışında
zaten mevcut olmadığı için bu, bir bayraktan daha güçlü bir güvencedir.

### 2. Prosedürde beyan edilir

Arıza, koşan YAML'ın `failures:` girdisidir. Dolayısıyla `scenario.yaml` içinde
harfi harfine bulunur ve [ortam parmak izindeki](reproducibility.tr.md)
`procedure_hash`'in kapsadığı metnin içindedir. Bir koşu, arşivlenmiş belgenin
söz etmediği bir şey tarafından bozulmuş olamaz.

`fingerprint.json` beyanı ayrıca `scenario` altında listeler — okuyan için. O
bölüm betimleyicidir ve ikinci bir kimlik alanı **değildir**: `failures:` bloğu
zaten prosedür metninin parçasıdır ve aynı içerik üzerindeki ikinci bir özet
ancak birinciyle çelişebilirdi.

### 3. Kapalı düşer

Beyan edilen her arıza, **ilk adımdan önce** araç üzerinde yoklanır. Mekanizma
bu yazılımda yoksa — parametresi olmayan bir ArduPilot, var olmayan bir bozma
düğmesi — prosedür **durdurulur** ve araç yerden hiç kalkmaz. Koşu bir
`environment` arızası ve `fault-not-applied` koduyla kaydedilir.

Asla nominal olarak uçurulmaz. Arızası hiç gerçekleşmemiş bir nominal-dışı test,
yanlış adı taşıyan nominal bir testtir ve kimsenin denemediği bir davranış için
"geçti" raporlardı.

### 4. Temizlenir

Her enjektör değiştirdiğini bir `finally` içinden geri alır; prosedür düşse,
hata verse ya da iptal edilse de. Her geri almanın gerçekten başarılı olup
olmadığı varsayılmaz, kaydedilir; geri alınamayan bir arıza sınıflandırılmış bir
arızanın kendisidir (`fault-not-cleared`), çünkü simülatör hâlâ bozuktur ve o
noktadan sonra ölçülen hiçbir şey söylediği anlama gelmez.

Bağlantı arızasının enjektörünkinin ötesinde ikinci bir güvencesi vardır:
yürütücü onu dıştaki `finally`'sinden temizler ve `MavlinkLink.stop()` bir kez
daha temizler; böylece taşıyan oturumdan sağ çıkamaz.

### 5. Belirlenimci

Hiçbir yerde rastgelelik yok. Paket kaybı N'de birini **sayarak** düşürür,
olasılıkla değil; böylece aynı senaryonun iki koşusu bağlantıyı aynı yerlerden
bozar. `drop_one_in: 1` reddedilir — o tam bir kesintidir ve koşu kaydı ikisinden
hangisinin gerçekten yaşandığını söylemelidir.

## Katalog

| `fault` | `target` | seçenekler | mekanizma |
|---|---|---|---|
| `gps_loss` | `gps1` | — | `SIM_GPS1_ENABLE = 0`; enjeksiyondan önce okunan değere geri alınır |
| `gps_degradation` | `gps1` | `satellites` (varsayılan 4), `fix_type` (0–6) | `SIM_GPS1_NUMSATS`, `SIM_GPS1_FIXTYPE`; ikisi de geri alınır |
| `mavlink_interrupt` | `gcs_link` | — | ArgazUI hiçbir şey göndermez ve aldığı her paketi okumadan atar |
| `mavlink_degradation` | `gcs_link` | `drop_one_in` (varsayılan 2, en az 2) | ArgazUI aldığı her N. mesajı atar |

Yalnızca **birincil** GPS sunuluyor. ArduPilot'un SITL'i ikinci bir alıcıyı
ancak `SIM_GPS2_ENABLE` ayarlıysa simüle eder; dolayısıyla sıradan bir modelde
"GPS 2'yi kapat" hiçbir şeyi bozmaz — ki bu, 3. kuralın önlemek için var olduğu
sessiz boş işlemin ta kendisidir.

ArduPilot, SITL birden çok simüle alıcı kazandığında bu parametreleri yeniden
adlandırdı: `SIM_GPS_DISABLE`, anlamı tersine çevrilerek `SIM_GPS1_ENABLE`
oldu. İkisi de yoklanır ve bağlı aracın yanıtladığı kullanılır; çünkü ArgazUI,
kendi denetlemediği bir checkout'un önyüzüdür.

### MAVLink arızası neden bir `SIM_` parametresi değil

ArduPilot'ta "yer istasyonu gitti" diye bir parametre yok ve olmamalı da: yer
istasyonu *bu programın kendisi*. Bu yüzden arıza, gerçekte yaşanacağı yerde
yaşıyor — bağlantıda — ve iki yönde de dürüst: ArgazUI o süre boyunca aracı
duymuyormuş gibi yapmıyor, gerçekten duymuyor.

ArgazUI'nin heartbeat'ini kesmek, koşulun yaklaşık değil **tam** bir modelidir.
ArduPilot'un GCS failsafe'i `sysid_mygcs_seen` üzerinden çalışır ve bu, tam
olarak üç işleyiciden çağrılır: `HEARTBEAT`, `RC_CHANNELS_OVERRIDE` ve
`MANUAL_CONTROL` (`ardupilot/libraries/GCS_MAVLink/GCS_Common.cpp`). ArgazUI
ilk ikisini gönderir, üçüncüsünü hiç göndermez ve arıza ikisini de keser.

## Bir arıza testinin ayrı tuttuğu dört şey

Koşunun kaydı bunları ayırır ve hiçbiri bir diğerinden türetilmez:

| | |
|---|---|
| **enjekte edilen koşul** | hangi parametrelere ne yazıldı ve önceki değerleri neydi |
| **aracın tepkisi** | arızanın aracın saatinde gerçekte ne kadar tutulduğu ve hangi kanıtın geldiği |
| **kriterler** | `expect:` (arıza uygulanırken) ve `recovery:` (geri alındıktan sonra) |
| **hüküm** | bu kriterlerin her birinin sağlanıp sağlanmadığı |

> **Başarıyla enjekte edilmiş bir arıza, geçiş değildir.**

Beyan ettiği `evidence:` hiç gelmemiş bir arıza, sağlanmış değil
**değerlendirilmedi** olarak raporlanır. Kanıt olmadan kriterler, hiçbir şeyin
yazmadığı bir duruma karşı değerlendirilirdi — kehribara gömülmüş bir araç, ki
her şeyi geçirir.

## Kriterler arıza sırasında ne zaman değerlendirilebilir, ne zaman değil

Bu, mekanizmanın bir kısıtı değil; arızaların *ne olduğudur*.

- **GPS kaybı** telemetriyi akar bırakır, dolayısıyla `expect:` kriterleri
  anlamlıdır: bozulmuş araç hakkında iddialardır ve düzeltmeden sonra
  ölçüldüklerinde aynı şeyi ifade etmezlerdi.
- **Tam bir MAVLink kesintisi** telemetriyi tanımı gereği durdurur. Bu yüzden
  `copter_link_loss.yaml` içindeki her kriter bir `recovery:` kriteridir. Yer
  istasyonu ne olduğunu ya sonradan öğrenir ya da hiç öğrenmez.

## Nasıl çalıştırılır

Senaryolar kendi panellerinde görünür, adlarıyla başlatılır ve hiçbir zaman bir
hızlı komut butonuna bağlanmaz — bir arıza, bir yetenek eşleşmesi uygun bulduğu
için başlamamalıdır. v1.4 ile iki tanesi geliyor:

| | |
|---|---|
| `copter_gps_loss` | GUIDED'da askıya tırmanır, GPS'i 12 sn kapatır |
| `copter_link_loss` | GUIDED'da askıya tırmanır, bağlantıyı 10 sn susturur |

Şema, [`argazui/procedures/SCHEMA.md`](../argazui/procedures/SCHEMA.md)
dosyasında *Scenarios and fault injection* başlığı altında belgelenmiştir.

## Senaryoların bilerek iddia etmedikleri

`copter_gps_loss` belirli bir failsafe modu **istemez**. `FS_EKF_ACTION` bir
parametredir, bir model onun herhangi bir değerini taşıyabilir ve `LAND`
dayatan bir kriter, aracı değil bu deponun varsayımını test ederdi. İstediği
şey, parametre ne derse desin doğru olan kısımdır: GPS'ini kaybeden havadaki bir
araç disarm etmemeli ve takla atmamalıdır. Seçtiği mod, bir insanın okuması için
koşunun mod zaman çizelgesine kanıt olarak kaydedilir.

Arıza enjeksiyonu ArgazUI v1.4 ile eklendi.

## Dört mekanizmanın dördü de artık uygulanıyor

Dördünden ikisi — `gps_degradation` ve `mavlink_degradation` — v1.4'ten beri
arkalarında birim testleriyle `faults.KINDS` içindeydi ve hiçbir senaryo
ikisinden birini adlandırmıyordu. Hiçbir şey onları bir araca yöneltemiyordu;
yani uçuş kanıtı olmayan kod yollarıydılar:
[mekanizma matrisinde](coverage-model.tr.md) `DEFINED` — "kapsanmamış"tan daha
zayıf bir durum.

v1.7, onları erişilebilir kılan iki beyanı ekler. **Hiçbir mekanizma
eklenmedi** — `faults.py` değişmemiştir.

| senaryo | mekanizma | neyi sorar |
|---|---|---|
| `copter_gps_degradation` | `gps_degradation` | hâlâ bildiren ve kötü bildiren bir alıcı: dört uydu ve 2B fix |
| `copter_link_degradation` | `mavlink_degradation` | sessiz değil kayıplı bir bağlantı: alınan her dört mesajdan biri atılır |

`tests/test_tier1_degradation_faults.py` ikisini de gerçek bir SITL üzerinde
uçurur ve yedi özelliği sırayla dayatır — arıza başlar, koşul gözlemlenebilir,
beklenen tepki gerçekleşir, bir kriter onu değerlendirir, kanıt üretilir, hüküm
kriterlerden çıkar ve temizlik ortamı geri yükler.

### Bozulma neden kayıptan farklı bir soru

`copter_gps_loss` alıcıyı kapatır ve ArduCopter'in yanıtı EKF failsafe'idir: bir
koşunun izleyebileceği bir mod değişimi. Bozulma daha zor ve daha yaygın olan
durumdur — alıcı hâlâ oradadır ve kötü bildirmektedir; mesajda *bana güvenme*
diyen hiçbir şey yoktur. Bu yüzden kriterler bir failsafe talep etmez;
kestirici ne karar verirse versin geçerli olanı talep eder: havadaki bir çok
rotorlu araç armlı kalır ve doğru tarafı yukarı durur.

`copter_link_loss` bağlantıyı tamamen susturur ve kriterlerinin her biri bir
`recovery:` kriteri olmak zorundadır — karartma sırasında telemetri yoktur, yani
o sırada hüküm verilecek bir şey de yoktur.
`copter_link_degradation` ise **kataloğdaki, penceresi kendi içinden hüküm
verilebilen tek arızadır**: alınan her dört mesajdan üçü hâlâ gelir, yani `for`
ve `never` çalışacak örneklere sahiptir. Bunu bir varsayım değil bir ölçüm yapan
şey kanıt korumasıdır — düşme oranı akışı gerçekten sustursaydı, o kriterler
hiçbir şeyin yazmadığı bir duruma dayanarak geçmek yerine *hüküm verilmedi*
bildirirdi.
