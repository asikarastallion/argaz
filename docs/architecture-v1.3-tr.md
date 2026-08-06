# ArgazUI v1.3 — Çoklu Araç Simülasyonu Sistem Mimarisi

**Tema:** Tek bir Gazebo dünyasında, deklaratif olarak tanımlanmış, tekrarlanabilir ve
doğrulanabilir çoklu araç (fleet) simülasyonu.

**Değişmeyen ilke:** v1.2'nin tek-araç yolu bozulmadan kalır. Fleet motoru *ek* bir
yoldur, mevcut yolun yeniden yazımı değildir.

---

## 0. Neden bu "endüstriyel seviye" farkı yaratıyor

Çoğu açık kaynak çoklu-SITL örneği şudur: birkaç terminal aç, `-I 0`, `-I 1`, `-I 2`
yaz, elle uçur. Bu bir *demo*'dur. Endüstriyel olan tarafı şu beş şey belirler:

| Demo | Endüstriyel |
|---|---|
| Elle port seçimi | Deterministik + kiralanmış (leased) kaynak tahsisi, çakışma tespiti |
| Elle dünya dosyası düzenleme | Fleet spec → dünya + model dosyalarının üretilmesi |
| "Çalıştı galiba" | Filo seviyesinde kabul kriterleri + üretilen rapor |
| Ctrl+C ile kapatma | Sıralı teardown, yetim (orphan) süpürme, kaynak iadesi |
| Tek araç ACK'i | Araç başına ACK matrisi, kısmi başarısızlık politikası |

v1.1/v1.2'de zaten kurduğun **prosedür motoru**, **kabul kriterleri**, **runs/
artefaktları** ve **Tier-1/Tier-2 CI** disiplini var. v1.3 bunları araç başına
çoğaltmak yerine *filo seviyesine yükseltiyor*.

---

## 1. Katman haritası

```
┌────────────────────────────────────────────────────────────────────┐
│ L7  UI — Fleet sayfası (grid kartlar, hedef seçici, grup komutları) │
├────────────────────────────────────────────────────────────────────┤
│ L6  Artefakt & Rapor — runs/<run_id>/fleet.json + fleet_report.md   │
├────────────────────────────────────────────────────────────────────┤
│ L5  Gözlem & Güvenlik — RTF, ayrışma (separation), link sağlığı     │
├────────────────────────────────────────────────────────────────────┤
│ L4  Fleet MAVLink Router — araç başına link, state, grup komutları  │
├────────────────────────────────────────────────────────────────────┤
│ L3  Supervisor — süreç yaşam döngüsü, hazırlık kapıları, teardown   │
├────────────────────────────────────────────────────────────────────┤
│ L2  World Composer — SDF üretimi, spawn geometrisi, ENU→LLA         │
├────────────────────────────────────────────────────────────────────┤
│ L1  Resource Allocator — port blokları, sysid, çalışma dizinleri    │
├────────────────────────────────────────────────────────────────────┤
│ L0  Fleet Spec — deklaratif TOML + şema doğrulaması                 │
└────────────────────────────────────────────────────────────────────┘
```

L0–L2 **saf** (yan etkisiz, tamamen unit-test edilebilir). L3–L5 **süreç/ağ**.
Bu ayrım kasıtlı: CI'ın büyük kısmı simülasyon açmadan koşabilsin diye.

---

## 2. L0 — Fleet Spec (deklaratif sözleşme)

Filo, kodda değil dosyada tanımlanır: `argazui/config/fleets/<name>.toml`.
Bu, "tekrarlanabilirlik" iddiasının tek dayanağıdır.

```toml
[fleet]
name        = "quad_swarm_4"
description = "4x Iris, 10 m ızgara, eşzamanlı GUIDED kalkış"
world       = "iris_runway"        # SITL_Models veya argazui/worlds içindeki taban dünya
max_rtf_drop = 0.35                # RTF bu oranın altına düşerse koşu 'degraded'
min_separation_m = 5.0             # ihlal = kabul kriteri hatası
formation   = "grid"               # grid | line | circle | explicit

[fleet.origin]                     # dünya spherical_coordinates ile birebir aynı olmalı
lat = -35.363262
lon = 149.165237
alt = 584.0
heading = 0.0

[fleet.policy]
start        = "staggered"         # parallel | staggered | gated
start_delay_s = 3.0
on_vehicle_failure = "abort_fleet" # abort_fleet | continue_degraded | hold
group_command      = "parallel_ack"

[[vehicle]]
id    = "v1"
model = "iris"                     # models.json içindeki mevcut id
sysid = 1
spawn = { east_m = 0.0, north_m = 0.0, up_m = 0.2, yaw_deg = 0 }
role  = "leader"

[[vehicle]]
id    = "v2"
model = "iris"
sysid = 2
spawn = { east_m = 10.0, north_m = 0.0, up_m = 0.2, yaw_deg = 0 }
params = { BATT_CAPACITY = 5000 }  # araç-özel override, beyan edilmiş olur
```

### Doğrulama kuralları (hepsi hata, uyarı değil)

1. `sysid` benzersiz, 1–255 aralığında, 0 yasak.
2. `model` `models.json`'da var ve Tier-1'de **geçiyor** olmalı
   (Swan-K1 gibi tutum kriterini geçemeyen modeller filoya alınamaz).
3. Filodaki tüm modeller aynı `launch_method` ailesinden olmalı —
   `ros2_launch` (Iris/RViz) ile `gz_plus_sitl_paramfile` aynı dünyada karıştırılamaz.
   Karışım denenirse net hata: hangi araç hangi yöntemi istiyor.
4. Herhangi iki spawn noktası arası mesafe ≥ `min_separation_m` (spawn anında çakışma
   fiziği patlatır).
5. Araç sayısı ≤ `argaz.toml`'daki `fleet.max_vehicles` (CPU çekirdek sayısından türetilmiş
   varsayılan, örn. `max(2, cores // 2)`).
6. `formation` verilmişse `spawn` alanları üretilir; ikisi birden verilirse hata.

Spec doğrulaması **CLI'dan da çağrılabilir**: `argaz fleet validate quad_swarm_4`.
Bu, simülasyon açmadan hata bulmayı sağlar ve CI'ın ilk kapısıdır.

---

## 3. L1 — Resource Allocator

ArduPilot SITL, `-I <instance>` ile portları 10'ar 10'ar kaydırır. v1.3 bunu
**varsaymamalı, doğrulamalı** — Claude Code'un ilk işi kendi ArduPilot sürümünde
gerçek port haritasını ölçüp `docs/fleet-ports.md`'ye yazmak.

Beklenen harita (instance = i):

| Kaynak | Port | Kim kullanıyor |
|---|---|---|
| SITL SERIAL0 (TCP) | `5760 + 10*i` | ArgazUI fleet router (**birincil bağlantı**) |
| SITL SERIAL1/2 (TCP) | `5762/5763 + 10*i` | opsiyonel harici GCS |
| FDM in (Gazebo→SITL) | `9002 + 10*i` | ardupilot_gazebo plugin `fdm_port_in` |
| FDM out | `9003 + 10*i` | SITL |
| MAVProxy out (opsiyonel) | `14550 + 10*i` | yalnız "attach console" edilen araç |
| PlotJuggler mirror | tek port (14552), araç-namespace'li JSON | v1.2'den gelen |

### Üç tasarım kararı

**(a) Fleet modunda araç başına MAVProxy YOK.** ArgazUI doğrudan `tcp:127.0.0.1:5760+10i`
adresine bağlanır. Gerekçe: N araç × (MAVProxy + map + console) hem RTF'i yer hem de
her araç için ayrı terminal gerektirir. Bunun yerine:

**(b) "Attach console" — tek interaktif MAVProxy.** Kullanıcı bir aracı seçip
konsol açtığında o araç için tek bir MAVProxy başlatılır (`--master tcp:...`),
kapatınca söner. "Hiçbir şey gizlenmiyor" ilkesi korunur, maliyet 1 sürece iner.

**(c) Port kiralama (lease).** Tahsis deterministiktir ama körlemesine değil:
her port için `bind()` denemesiyle boşluk doğrulanır, sonuç
`runs/<run_id>/ports.json`'a PID'lerle yazılır. Kirli kapanmadan kalan lease'ler
PID canlılığına bakılarak temizlenir. Aynı makinede iki ArgazUI koşusu birbirini
sessizce bozamaz.

Çalışma dizini izolasyonu v1.0'daki desenin devamı:
`argazui/run/fleet/<run_id>/<vehicle_id>/` — her aracın kendi `eeprom.bin`'i,
parametreleri ve logu.

---

## 4. L2 — World Composer (en teknik kısım)

### Problem
`ardupilot_gazebo` model SDF'lerinde `fdm_port_in` **model dosyasının içine gömülü**.
Aynı modeli 4 kez `<include>` etmek 4 aracın da 9002'ye bağlanmasına yol açar.

### Çözüm: run dizinine materyalize etme
1. Her araç için taban model dizini `runs/<run_id>/models/<vehicle_id>/` altına kopyalanır.
2. `model.sdf` içindeki `ArduPilotPlugin` parametreleri yamalanır:
   `fdm_port_in = 9002 + 10*i`, gerekiyorsa `fdm_addr`.
3. `GZ_SIM_RESOURCE_PATH`'in **başına** run dizini eklenir.
4. Üretilen `runs/<run_id>/world/fleet.sdf`, taban dünyayı temel alıp her araç için
   benzersiz `<name>` ve `<pose>` ile `<include>` ekler.

> Alternatif (`<include>` içinde plugin override, ya da `gz service /world/<w>/create`
> ile runtime spawn) daha zarif görünür ama SDFormat sürümüne göre sessizce
> çalışmayabilir. Claude Code'a talimat: **ikisini de dene, hangisinin gerçekten
> çalıştığını ölç, sonucu dokümante et.** Ölçmeden seçim yapılmaz.

### Spawn geometrisi ve ENU→LLA
Gazebo pozu görselde nereye konduğunu belirler; SITL'in kendi home'u
`--custom-location=lat,lon,alt,heading` ile ayrıca verilmelidir. İkisi tutmazsa
araç ekranda bir yerde, EKF'e göre başka bir yerde olur — çoklu araçta bu hatanın
belirtisi "ayrışma monitörü saçmalıyor" şeklinde gelir.

Düz-dünya dönüşümü (< 1 km için yeterli, ama **test edilmiş** olmalı):

```
lat = lat0 + (north_m / 111320.0)
lon = lon0 + (east_m  / (111320.0 * cos(radians(lat0))))
alt = alt0 + up_m
```

Golden-file testi: bilinen offsetler → bilinen lat/lon, ve ters dönüşümün
< 0.1 m hata ile kapanması.

### Formasyon üreticileri
- `grid`: `ceil(sqrt(N))` kenarlı ızgara, `spacing_m` aralıkla, merkezi origin.
- `line`: doğu ekseninde dizilim.
- `circle`: `radius_m` yarıçaplı çember, araçlar merkeze bakar.
- `explicit`: her aracın `spawn` bloğu zorunlu.

---

## 5. L3 — Supervisor (süreç yaşam döngüsü)

Aşamalı başlatma, her aşamada **hazırlık kapısı** var. Kapı geçilmeden sonraki
aşama başlamaz; timeout = koşu hatası, "umarım hazır olmuştur" yok.

```
[1] Ortam doğrulama        → doctor (v1.2) + fleet-özel kontroller
[2] Kaynak tahsisi         → ports.json yazıldı
[3] Dünya üretimi          → fleet.sdf + model dizinleri hazır
[4] gz sim (tek server)    → KAPI: /stats topic'inde ilerleyen sim time
[5] SITL x N               → politikaya göre parallel/staggered/gated
                             KAPI(araç): TCP link açıldı + HEARTBEAT geldi
[6] Pre-arm bekleme        → KAPI(araç): EKF hazır + prearm health biti
[7] FILO HAZIR             → UI yeşile döner, komutlar açılır
```

Teardown ters sırada: araçlar → gz server → port lease iadesi → yetim süpürme.
Süreç sonlandırma v1.0'daki desenle: `start_new_session=True`, `/proc` üzerinden
SID/PGID eşleşmesi, `os.killpg` ile SIGINT → SIGTERM → SIGKILL. **Asla isim
eşleştirme (`pkill -f`) yok.**

### Sağlık monitörü (koşu boyunca, 1 Hz)
- Süreç canlı mı (`waitpid` non-blocking)
- Son HEARTBEAT üzerinden geçen süre (> 5 s = link kaybı)
- RTF (`gz topic -e -t /stats` veya gz transport aboneliği)
- Lockstep stall tespiti: sim time ilerlemiyorsa **hangi aracın FDM'i cevap
  vermiyor** bilgisiyle birlikte raporla (çoklu araçta en sık ve en kafa karıştırıcı arıza budur)

### Hata politikaları
| Politika | Davranış |
|---|---|
| `abort_fleet` | Tüm araçlara LAND/RTL, sonra düzenli teardown, koşu FAILED |
| `continue_degraded` | Arızalı araç işaretlenir, filo devam eder, koşu DEGRADED |
| `hold` | Uçandalar LOITER'a alınır, kullanıcı karar verene kadar beklenir |

---

## 6. L4 — Fleet MAVLink Router

```
                       ┌──────────────┐
 SITL#1 tcp:5760 ──────┤              ├──> Vehicle State #1 ──┐
 SITL#2 tcp:5770 ──────┤ Fleet Router ├──> Vehicle State #2 ──┼──> UI (WebSocket)
 SITL#3 tcp:5780 ──────┤  (asyncio)   ├──> Vehicle State #3 ──┼──> PlotJuggler (/v1/.., /v2/..)
                       └──────┬───────┘                       └──> Artefakt yazıcı
                              │
                       Grup komut yürütücü
```

Araç başına bir asyncio task; her task kendi bağlantısını okur, `VehicleState`
günceller (mod, armed, prearm, GPS fix, EKF flags, batarya, konum, tutum, link
kalitesi) ve olayları tek bir olay hattına yazar.

### Grup komut semantiği
Bir grup komutu **her zaman** araç başına sonuç döndürür — "komut gönderildi"
diye bir başarı yoktur.

```json
{
  "command": "TAKEOFF",
  "target": ["v1","v2","v3"],
  "policy": "gated",
  "results": [
    {"vehicle":"v1","ack":"ACCEPTED","t_ms":142},
    {"vehicle":"v2","ack":"ACCEPTED","t_ms":168},
    {"vehicle":"v3","ack":"FAILED","reason":"PreArm: Need 3D Fix","t_ms":151}
  ],
  "verdict": "PARTIAL"
}
```

Politikalar:
- `parallel_ack` — hepsine aynı anda, ACK'ler paralel toplanır (mod değişimi için).
- `staggered` — araç başına `start_delay_s` gecikme (kalkışta RTF sıçramasını ve
  pervane etkileşimini önler).
- `gated` — araç *i+1* ancak *i* kapı koşulunu sağlayınca (örn. `alt > 3 m`) başlar.
  En güvenlisi, en yavaşı.

`sysid=0` broadcast **kullanılmaz**: ACK gelmez, doğrulanamaz, endüstriyel değildir.

### Hedef seçici
Her komutun hedefi açıkça belirtilir: `all` | `selected` | `["v1","v3"]` | `role:leader`.
UI'da "hangi araca gitti" belirsizliği kalmaz.

---

## 7. L5 — Gözlem ve Güvenlik

| Monitör | Kaynak | Eşik | Sonuç |
|---|---|---|---|
| Ayrışma (separation) | GLOBAL_POSITION_INT çiftleri, 2 Hz | `warn` / `violation` | violation = kabul hatası |
| RTF | gz `/stats` | `max_rtf_drop` | altına düşerse DEGRADED |
| Link | HEARTBEAT aralığı | 5 s | araç LOST |
| Tutum | ATTITUDE (v1.1 kriterleri) | araç başına | takla/kontrolsüzlük yakalanır |
| Yükseklik ayrımı | dikey mesafe | opsiyonel katman planı | uyarı |

Ayrışma monitörü v1.3'ün "aslında bir şey ölçüyoruz" kanıtıdır: 4 araç havada,
en küçük ikili mesafe zaman serisi kaydedilir ve raporda grafiklenir.

---

## 8. L6 — Artefaktlar ve Rapor

```
runs/<run_id>/
├── fleet.json              # spec snapshot + çözülmüş portlar + sürüm damgaları
├── timeline.jsonl          # tüm olaylar, monotonik zaman damgalı
├── separation.csv          # t, pair, distance_m
├── rtf.csv                 # t, rtf, sim_time
├── world/fleet.sdf         # üretilen dünya (tekrar üretilebilirlik kanıtı)
├── vehicles/
│   ├── v1/{params.txt, console.log, logs/*.BIN, acceptance.json}
│   ├── v2/...
│   └── v3/...
└── fleet_report.md         # insan okunur özet
```

`fleet_report.md` içeriği: filo künyesi, zaman çizelgesi, araç başına kabul
verdikti, ACK matrisi, minimum ayrışma, RTF istatistikleri, DEGRADED/FAILED
nedenleri. **README'de bir modelin "✅" alması ancak bu raporun ürettiği kanıtla
mümkün** — v1.1'de koyduğun kural filoya da uygulanır.

### Filo seviyesi kabul kriterleri
1. Her araç hedef irtifaya T saniye içinde ulaştı.
2. Koşu boyunca minimum ikili mesafe ≥ `min_separation_m`.
3. Hiçbir araç beklenmeyen moda düşmedi (araç başına tutum kriterleri dahil).
4. RTF eşiğin altına inmedi.
5. Her araç bir `.BIN` üretti ve log indirilebildi.
6. Teardown sonrası yetim süreç yok, port lease'leri iade edildi.

---

## 9. L7 — UI

Yeni bir **Fleet** sekmesi; tek-araç sayfası aynen kalır.

- **Fleet seçici** — mevcut spec'ler, `validate` sonucu rozet olarak.
- **Araç grid'i** — kart başına: id, sysid, model, mod, armed, irtifa, batarya,
  EKF/prearm, link yaşı, seçim kutusu.
- **Hedef çubuğu** — `All / Selected / v1…vN`, seçili hedef sayısı görünür.
- **Grup komut çubuğu** — ARM, TAKEOFF, MODE, RTL, LAND + politika seçici.
- **ACK matrisi** — son komutun araç × sonuç tablosu, hata sebepleriyle.
- **Ayrışma paneli** — anlık min mesafe + küçük zaman serisi.
- **RTF göstergesi** — renk kodlu.
- **Terminaller** — N terminal *yok*: (1) launch transcript (çalışan komutların
  birebir kaydı), (2) seçili aracın "attach console"u, (3) mevcut serbest shell.

---

## 10. Test ve CI stratejisi

| Katman | Kapsam | Nerede koşar |
|---|---|---|
| Tier-1 (saf) | spec doğrulama, allocator, ENU→LLA, formasyon, SDF golden files, grup komut durum makinesi, teardown mantığı | Her PR, saniyeler |
| Tier-2 (SITL-only) | Gazebo'suz `--model quad` ile 2–3 araç: link, heartbeat, ARM, mod, teardown, artefakt üretimi | Her PR, dakikalar |
| Tier-3 (Gazebo) | 3 araç gerçek dünya, kalkış → ayrışma → iniş, RTF ve tutum kriterleri | Nightly / manuel |

**Tier-2'nin Gazebo'suz olması kritik:** ArduPilot'un yerleşik fizik modeliyle
çoklu SITL, GitHub Actions runner'ında koşabilir. Fleet mantığının %80'i
(portlar, router, grup komutlar, artefaktlar) Gazebo'ya bakmaz — bunu CI'da
gerçekten test ediyor olmak v1.3'ün en güçlü iddiası olur.

Her yeni testin **önce kırmızı sonra yeşil** olduğu kanıtlanır (v1.1'de koyduğun kural).

---

## 11. Fazlar ve kapılar

| Faz | İçerik | Kapı |
|---|---|---|
| 0 | Baseline: v1.2 testleri yeşil, tek-araç davranışı snapshot'lanır | Mevcut 31+ test geçiyor |
| 1 | L0 + L1: spec, doğrulama, allocator, CLI `fleet validate` | Tier-1 testleri yeşil |
| 2 | L2: world composer, spawn matematiği, model materyalizasyonu | Golden dosyalar + 1 elle gz doğrulaması |
| 3 | L3: supervisor, SITL-only 2 araç | Tier-2: 2 araç kalkıp iniyor, yetim yok |
| 4 | L4: router, state, grup komutlar, ACK matrisi | ACK matrisi kısmi hatayı doğru raporluyor |
| 5 | L5 + Gazebo: 3 araç gerçek uçuş, RTF + ayrışma | Gerçek koşu kaydı üretildi |
| 6 | L6: artefaktlar, fleet_report, kabul kriterleri | Rapor bir başarısızlığı da doğru raporluyor |
| 7 | L7: UI | Elle uçuş testi |
| 8 | Docs, README, status.md, CI, v1.3.0 yayını | Temiz clone'dan kurulup çalışıyor |

---

## 12. Kapsam dışı (v1.3)

- HITL / gerçek donanım köprüsü (Parça C, ayrı sürüm)
- Sürü zekâsı / formasyon uçuşu algoritmaları (leader-follower kontrol yasası)
- Çoklu araç için otomatik çakışma önleme (sadece **tespit** var, kaçınma yok)
- Uzaktan erişim / kimlik doğrulama
- Rover/boat modelleri
- Karışık launch-method filoları

Bunları README'de "not implemented" olarak açıkça listele — v1.1'de kurduğun
dürüstlük çizgisi v1.3'te de sürsün.
