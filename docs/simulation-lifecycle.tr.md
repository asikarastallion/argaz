# Simülasyon yaşam döngüsü

Bir hava aracına hüküm verilebilmesi için önce neyin ayağa kalkması gerekir,
hangi sırayla, ve her basamak kalkmadığında nasıl bir arıza üretir.

Bir koşu başarısız olduğunda ve simülatöre mi, otopilota mı yoksa araca mı
bakmanız gerektiğini henüz bilmiyorsanız okunacak sayfa budur.
[Süreç ve oturum yaşam döngüsü](lifecycle.tr.md) süreçlerin kendisini anlatır —
ne başlatılır, nasıl kapatılır. Bu sayfa onların geçtiği *durumlarla* ilgilidir.

## Merdiven

```
CREATED
   ↓
ENVIRONMENT_STARTING     simülatör süreci başlatıldı
   ↓
ENVIRONMENT_READY        bir dünya sunuyor — yalnızca çalışıyor değil
   ↓
VEHICLE_STARTING         otopilot süreci başlatıldı
   ↓
VEHICLE_READY            konuşuyor ve uçmaya elverişli olduğunu söylüyor
   ↓
PROCEDURE_RUNNING        yürütücü devraldı
   ↓
COMPLETED                araçla ilgili bir hükümle
```

arıza dalları:

```
ENVIRONMENT_FAILED       simülatör ayağa kalkmadı
VEHICLE_START_FAILED     simülatör kalktı, otopilot kalkmadı
VEHICLE_NOT_READY        otopilot çalışıyor ve kendini elverişsiz bildiriyor
PROCEDURE_FAILED         akış koştu ve varacağı yere varmadı
ACCEPTANCE_FAILED        araç çalışır durumdaydı ve yanlış olanı yaptı
```

## "Başladı" ile "hazır" neden iki ayrı basamak

Bir PID yalnızca `fork` çağrısının başarılı olduğunu kanıtlar, başka bir şey
değil.

Gazebo, `model://runway` adresini çözemeyip *Unable to find uri* yazdırarak
çıktığı birkaç saniye boyunca bir PID tutar. SITL, hiç yanıt vermeyecek bir
fizik arka ucunu sonsuza kadar beklerken bir PID tutar. v1.7'den önce tüm el
sıkışma `gz sim … &` ardından `sleep 6` idi: altı saniye hızlı bir makinede
fazla, soğuk bir önbellekte azdır — ve hiçbir durumda yavaş bir simülatörü ölü
bir simülatörden ayırmaz.

Bu yüzden her basamağa, bir saatle değil, bileşenin işini yapmasıyla ulaşılır:

| Basamak | Nasıl kanıtlanır |
|---|---|
| `ENVIRONMENT_READY` | `gz topic -l` çıktısında `/world/…` altında bir konu listelenir. Gazebo taşıma katmanı bunları ancak bir dünya yüklenip sunucu adım attığında duyurur. |
| `VEHICLE_STARTING` → çalışır durumda | SITL'in serial0 TCP portu bağlantı kabul eder. İkili dosya bu portu ancak ilklendirmeyi bitirip bir yer istasyonuna hazır olduğunda açar. |
| `VEHICLE_READY` | Bir heartbeat geldi **ve** `SYS_STATUS`, arm öncesi denetim bitini sağlıklı bildiriyor. |

Başlatma komutları bunlardan ilkini terminalde, görünür biçimde bekler:

```bash
gz sim -v4 -r -s alti_transition_runway.sdf &
for i in $(seq 1 30); do
  gz topic -l 2>/dev/null | grep -q "^/world/" && { echo "[argaz] gazebo is serving a world"; break; }
  sleep 2
done
```

Bu satır Python'a taşınmayıp kabuk satırı olarak kalır; diğer her başlatma
satırıyla aynı gerekçeyle: terminaldeki komutlar, sizin de yazabileceğiniz
komutlardır.

### Geri düşüş, gizlenmek yerine bildirilir

`gz sim` bulunan bir `PATH` üzerinde `gz topic` bulunmayabilir. Eksik bir tanı
aracı yüzünden ilerlemeyi reddeden bir başlatma, çalışan bir simülasyonu
başarısız sayardı; bu yüzden araç yine de başlatılır ve basamağa ulaşılmadığı
kaydedilir. Ardından hiç heartbeat gelmezse koşu şunu söyler: *Gazebo hiçbir
zaman sunulan bir dünya bildirmedi ve araçtan heartbeat gelmedi* — bu, *simülatör
kalktı ama araç görünmedi* cümlesinden farklıdır ve ikisi iki ayrı incelemedir.

## Her basamak başarısız olduğunda ne üretir

Her arıza dalı [yedi kategorili sınıflandırmaya](failure-classification.tr.md)
eşlenir. **Hiçbir kategori eklenmedi.** Amaç, arızanın gerçekleştiği katmanda
raporlanmasıdır; katmanlar için yeni bir sözlük oluşturmak değil.

| Durduğu yer | Kategori | Kod |
|---|---|---|
| `ENVIRONMENT_FAILED` | `environment` | `environment-not-ready` |
| `VEHICLE_START_FAILED` | `environment` | `vehicle-start-failed` |
| `VEHICLE_NOT_READY` | `vehicle_readiness` | `prearm-never-passed` |
| `PROCEDURE_FAILED` | `procedure` | `step-failed` |
| `ACCEPTANCE_FAILED` | `acceptance` | `criterion-failed` |

Yalnızca tek bir satır `acceptance`'tır; çünkü `acceptance`, aracın yanlış bir
şey yaptığı anlamına gelen tek kategori olarak
[belgelenmiştir](failure-classification.tr.md) — ve bir yaşam döngüsü basamağı
tanımı gereği aracın altındadır.

`VEHICLE_START_FAILED` bilinçli olarak `vehicle_readiness` değil `environment`
sayılır. SITL'in başlayamaması, simülatörün ayağa kalkmamasıdır.
`vehicle_readiness`, *çalışan* ve kendini elverişsiz bildiren bir araca ayrılmıştır;
bu, aracın yapılandırmasıyla ilgili bir olgudur — [status.md](status.md)
içindeki `swan_k1_hwing` canlı örnektir: hava hızı sensörü olmadığı için arm
öncesi denetimleri hiç geçmez.

## Nereden sürülür

Buradaki hiçbir şey bir orkestratör değildir. `simlifecycle.Lifecycle` bir kayıt
ve bir sınıflandırıcıdır: hiçbir şey başlatmaz, hiçbir şey çalıştırmaz ve
hiçbir sürece sahip olmaz.

* Süreçlerin sahibi hâlâ `TerminalSession`'dır.
* Hazır olma durumunun sahibi hâlâ `MavlinkLink`'tir.
* Tek yürütücü hâlâ `ProcedureRunner`'dır.

İki yer onu sürer, çünkü neyin başlatıldığını zaten bilen iki yer bunlardır:
tarayıcı yolu için `Manager`, tier 2 için `tests/gazebo.py`. İkisi de sonucu
`RunRecorder.record_lifecycle` üzerinden koşuya kaydeder.

Bir tier-1 koşusu hiç yaşam döngüsü kaydetmez. Doğrudan bir SITL ikili dosyası
başlatır; ayağa kaldırılacak Gazebo ve sahiplenilecek bir pty oturumu yoktur.
`lifecycle: null`, boş bir kayıt yerine dürüst yanıttır.

## Bir koşu neyi kaydeder

```json
"lifecycle": {
  "phase": "completed",
  "clock": "wall",
  "history": [
    {"phase": "created",               "since_start_s": 0.0,  "detail": ""},
    {"phase": "environment_starting",  "since_start_s": 0.1,  "detail": "6 launch line(s)"},
    {"phase": "environment_ready",     "since_start_s": 8.4,  "detail": "Gazebo is serving world(s): alti_transition_runway"},
    {"phase": "vehicle_starting",      "since_start_s": 8.4,  "detail": "waiting for MAVLink"},
    {"phase": "vehicle_ready",         "since_start_s": 31.2, "detail": "pre-arm checks pass"},
    {"phase": "procedure_running",     "since_start_s": 31.3, "detail": "vtol_takeoff"},
    {"phase": "completed",             "since_start_s": 96.0, "detail": "session stopped"}
  ],
  "timings_s": {"environment_ready": 8.4, "vehicle_ready": 31.2, "total": 96.0},
  "failure": null
}
```

### Süreler hakkında

Bunlar **duvar saati** ölçümleridir ve kayıtta böyle etiketlenir. Ana makinenin
bir ortamı ayağa kaldırmasının ne kadar sürdüğünü ölçerler; bu ana makineyle
ilgili bir olgudur — araçla değil ve bir [metrik](metrics.tr.md) değildir.
Bunlardan türetilen hiçbir şey bir hükme ulaşamaz.

Hiç ulaşılmayan bir basamak `0` değil `null` bildirir. "Hiç sürmedi" ile "hiç
olmadı" farklı olgulardır ve bu proje ikisinin aynı görünmesine izin vermez.

### Uçtaki bir duruma bir daha çıkılmaz

Bir yaşam döngüsü başarısız olduktan sonra, sonraki bir başarı onun üzerine
yazmaz. Arızanın var olduğu ama görünmediği bir geçmiş, hiç geçmiş olmamasından
kötüdür: hiçbir şeyin desteklemediği bir hüküm taşıyan koşunun altında temiz bir
açılış gösterirdi.

## Bir arızayı okumak

`result.json` dosyasını açın ve önce `lifecycle.failure` alanına bakın. `null`
değilse, koşu prosedürlerinin bir anlam ifade edeceği noktaya hiç ulaşmamıştır
ve `classify_run` — tek bir adıma bakmadan önce — uçuşu değil ortamı
raporlamış olacaktır.

`null` *ise* ortam ayağa kalkmış ve yürütücü sırasını almıştır. Hüküm
prosedürlerdedir ve bunun sayfası
[arıza incelemesidir](failure-investigation.tr.md).
