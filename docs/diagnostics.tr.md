# Tanılama (`doctor`)

```bash
python3 -m argazui doctor            # insan için
python3 -m argazui doctor --json     # makine için
python3 -m argazui doctor --tier tier1
```

Her **kritik** kontrol geçtiyse çıkış kodu `0`, aksi hâlde `1`.

## Yalnızca gözlemler

Doctor hiçbir zaman paket kurmaz, dizin oluşturmaz, simülatör başlatmaz.
Makinede ne olduğunu raporlar ve her başarısızlık ne yapılacağını söyleyen bir
`fix:` satırı taşır. Bir şeyleri onaran bir tanılama aracı, çıktısına artık
"elimdeki makine bu" diye güvenilemeyen bir tanılama aracıdır.

## Neleri kontrol eder

| kontrol | kritik | ne demektir |
|---|---|---|
| `ardupilot_root` | evet | yapılandırılmış ArduPilot checkout'u var |
| `sitl_copter` / `sitl_plane` | evet | SITL ikili dosyası var, çalıştırılabilir ve başlıyor |
| `env_script`, `quadplane_env_script` | evet | başlatmaların source ettiği kabuk ortamı |
| `python_fastapi` / `uvicorn` / `pymavlink` / `yaml` | evet | **bu yorumlayıcıda** import edilebiliyor |
| `runs_root` | hayır | koşu arşivi dizini yazılabilir |
| `port_http`, `port_mavlink`, `port_script_mavlink` | evet | 8770 / 14550 / 14551 bağlanmaya uygun |
| `ardu_ws_root`, `sitl_models_root`, `sitl_models_gazebo` | tam profil | ROS çalışma alanı ve Gazebo varlıkları |
| `gz`, `ros2`, `ros_distro` | tam profil | **yapılandırılmış ortam source edildikten sonra** koşulur, giriş kabuğunda değil |

### SITL ikili kontrolü neden sıfırdan farklı çıkışı hoş görür

SITL'in seçenek ayrıştırıcısı birkaç ArduPilot sürümünde `--help` için bilerek
`1` ile çıkar. Seçenek başlığının tamamını görmek, bu çalıştırılabilir dosyanın
bu makinede başladığını yine de kanıtlar; `0` şartı koşmak çalışan bir SITL'i
bozuk göstermek olurdu.

### Canlı grafik portu neden kontrol edilmez

`doctor`, 14550 ve 14551'in bağlanmaya *uygun* olduğunu kontrol eder. 14552'nin
ise tutuluyor olması beklenir — PlotJuggler tarafından — dolayısıyla oradaki bir
bağlanma kontrolü tam da özellik çalışırken FAIL raporlardı.

## İki profil ve başlatmanın neden tam profile bağlı olmadığı

`--tier tier1`; ArduPilot'u, SITL ikili dosyalarını, Python paketlerini ve
portları kapsar. `--tier full` bunlara Gazebo'yu, ROS 2'yi ve model varlıklarını
ekler.

**Başlangıçta yalnızca katman-1 kümesi ölümcüldür.** Tam profile bağlamak,
ArgazUI'nin Gazebo ve ROS 2 olmayan her makinede — katman-1 konteyner imajı
dahil — başlamayı reddetmesine yol açıyordu; orada her e2e testi, hiçbirinin
kullanmadığı varlıklar yüzünden ölüyordu. Kullanıcı açısından da yanlıştır:
`sitl_only` başlatma yöntemi Gazebo'yu hiç istemez ve eksik bir simülatör bazı
modellerin uçamamasının sebebidir, uygulamanın çalışamamasının değil.

Bu yüzden sunucu başlar, hangi modellerin başlatılamayacağını yazar ve tam
rapora işaret eder:

```
ArgazUI: starting without the full simulation stack. Models that
need it cannot be launched:
  - sitl_models_root: SITL_Models root not found: /opt/SITL_Models
  Run 'argazui doctor' for the complete report.
```

## CI içinde

`--json` şunu verir: `{"ok": bool, "tier": str, "config": {...}, "checks":
[...]}`. Buradaki `config`, çözümlenmiş yapılandırmadır — hangi dosya okundu,
oradan hangi kökler ve portlar çıktı. Bir makinenin neden yanlış yere baktığını
bulmanın en hızlı yolu o bloktur.
