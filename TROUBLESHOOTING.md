# ARGAZ — Sorun Giderme Rehberi
ArduPilot SITL + ROS 2 Jazzy + Gazebo Harmonic (Ubuntu 24.04)

Proje kökü: `/home/asikarastallion/Documents/argaz`

---

## 0. Genel kural: takıldığında ilk yapman gereken

```bash
source ~/.bashrc
echo $GZ_VERSION        # "harmonic" yazmalı
echo $ROS_DISTRO        # "jazzy" yazmalı
which gz                # /usr/bin/gz gibi bir yol dönmeli
```

Bu üçü boşsa `env.sh` doğru yüklenmemiş demektir — önce onu çöz, gerisine bakma.

---

## 1. `apt` paket çakışmaları

**Belirti:** `apt install` sırasında "conflicting packages", "held broken packages", ya da `libgz-sim*` paketlerinin farklı sürümleri arasında çakışma.

**Sebep:** Aynı anda hem ROS deposundan (`ros-jazzy-ros-gz`) hem de bağımsız `gz-harmonic` metapaketini kurmaya çalışmak, ya da farklı Gazebo sürümlerini (Fortress + Harmonic gibi) aynı anda kurmak.

**Çözüm:**
```bash
apt list --installed | grep -i gz-
apt list --installed | grep -i gazebo
```
Çıktıda birden fazla Gazebo ana sürümüne ait paket görürsen (örn. hem `libgz-sim7*` hem `libgz-sim8*`), fazlalığı kaldır:
```bash
sudo apt remove --purge 'libgz-sim7*'
sudo apt autoremove
```
Sadece Harmonic ailesi (`gz-sim8`, `gz-*8` gibi) kalmalı.

---

## 2. `gz sim` GUI açılmıyor / siyah ekran / OGRE2 hatası

**Belirti:** `gz sim -v4 -r shapes.sdf` çalıştırdığında terminalde `Unable to create the rendering window`, `OGRE EXCEPTION`, ya da pencere hiç açılmıyor.

**Sebep:** Genelde GPU sürücüsü eksik/yanlış, ya da sanal makine (VirtualBox/VMware) kullanıyorsun. **VirtualBox ve VMware, Gazebo'nun ogre2 render motoru için gereken GPU pass-through'u düzgün desteklemiyor** — bu resmi olarak desteklenmiyor.

**Çözüm sırası:**
1. Fiziksel makinede (VM değil) çalıştığından emin ol.
2. GPU sürücünü kontrol et:
   ```bash
   sudo apt install mesa-utils
   glxinfo | grep "OpenGL renderer"
   ```
   Çıktıda `llvmpipe` yazıyorsa donanım hızlandırma çalışmıyor demektir (yazılım render — çok yavaş olur). NVIDIA kartın varsa:
   ```bash
   sudo ubuntu-drivers autoinstall
   sudo reboot
   ```
3. Vulkan eksikse:
   ```bash
   sudo apt install mesa-vulkan-drivers vulkan-tools
   vulkaninfo | head
   ```
4. Son çare, yazılım render ile test (sadece doğrulama amaçlı, performans kötü olur):
   ```bash
   LIBGL_ALWAYS_SOFTWARE=1 gz sim -v4 -r shapes.sdf
   ```

---

## 3. `rosdep install` paket bulamıyor (`Cannot locate rosdep definition`)

**Belirti:** `rosdep install --from-paths src --ignore-src -y` çalıştırdığında `gz-*` veya `ardupilot_gazebo` gibi anahtarlar için "Cannot locate rosdep definition" hatası.

**Sebep:** osrf-rosdep gz listesi eklenmemiş veya `rosdep update` yapılmamış.

**Çözüm:**
```bash
sudo wget https://raw.githubusercontent.com/osrf/osrf-rosdep/master/gz/00-gazebo.list -O /etc/ros/rosdep/sources.list.d/00-gazebo.list
rosdep update
cd /home/asikarastallion/Documents/argaz/ardu_ws
rosdep install --from-paths src --ignore-src -y
```

---

## 4. `colcon build` hataları

**Belirti:** `colcon build --packages-up-to ardupilot_gz_bringup` bir paketin ortasında kırmızı hata ile duruyor.

**Yapılacaklar:**
1. **İlk (en üstteki) hatayı oku**, sonrakiler genelde ona bağlı domino etkisidir.
2. ROS ortamının build öncesi source edildiğinden emin ol:
   ```bash
   source /opt/ros/jazzy/setup.bash
   ```
   (`env.sh` bunu otomatik yapıyor ama yeni açtığın bir terminalde unutma.)
3. Temiz build dene (bazen eski cache bozuk kalıyor):
   ```bash
   cd /home/asikarastallion/Documents/argaz/ardu_ws
   rm -rf build install log
   colcon build --packages-up-to ardupilot_gz_bringup
   ```
4. Detaylı log için:
   ```bash
   colcon build --packages-up-to ardupilot_gz_bringup --event-handlers console_direct+
   ```

---

## 5. `libgz-sim8-dev` bulunamıyor / `E: Unable to locate package`

**Sebep:** osrfoundation apt reposu eklenmemiş (Faz 2'yi atlamışsındır) ya da `apt update` yapılmamış.

**Çözüm:**
```bash
ls /etc/apt/sources.list.d/ | grep gazebo
```
Yoksa Faz 2'deki `wget`/`tee` komutlarını tekrar çalıştır, sonra:
```bash
sudo apt update
sudo apt install libgz-sim8-dev
```

---

## 6. ArduPilot derlemesi (`./waf`) hata veriyor

**Belirti:** `./waf configure` veya `./waf copter` sırasında Python modülü eksik, submodule eksik gibi hatalar.

**Çözüm:**
- Submodule'leri unuttuysan (repoyu `--recurse-submodules` olmadan klonladıysan):
  ```bash
  cd /home/asikarastallion/Documents/argaz/ardupilot
  git submodule update --init --recursive
  ```
- Prereqs scriptini tekrar çalıştır:
  ```bash
  Tools/environment_install/install-prereqs-ubuntu.sh -y
  . ~/.bashrc
  ```
- `waf` cache bozulduysa:
  ```bash
  ./waf distclean
  ./waf configure --board sitl
  ./waf copter
  ```

---

## 7. SITL çalışıyor ama Gazebo'ya bağlanmıyor (drone Gazebo'da düşmüyor / hareket etmiyor)

**Belirti:** `sim_vehicle.py` MAVProxy'de çalışıyor ama Gazebo'daki model hiç hareket etmiyor ya da `Failed to connect to Gazebo` hatası.

**Kontrol listesi:**
1. `GZ_VERSION` değişkeni set mi? (`echo $GZ_VERSION` → `harmonic` olmalı)
2. ArduPilot'ı **JSON backend** ile başlattın mı? Eğer manuel deniyorsan doğru komut:
   ```bash
   sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console
   ```
   Ama `argaz-sim` (yani `ros2 launch ardupilot_gz_bringup iris_runway.launch.py`) bunu zaten senin için otomatik yapıyor — elle SITL başlatıp ayrıca Gazebo açmaya çalışma, ikisi çakışır.
3. Port çakışması olabilir — aşağıdaki maddeye bak.

---

## 8. "Address already in use" / eski SITL süreçleri takılı kalmış

**Belirti:** Yeni bir simülasyon başlatınca port hatası, ya da Gazebo/SITL "zaten çalışıyor" gibi davranıyor.

**Çözüm:**
```bash
pkill -f sim_vehicle.py
pkill -f arducopter
pkill -f gz
```
Sonra tekrar dene.

---

## 9. `ros2 launch ardupilot_gz_bringup ...` paketi bulamıyor

**Belirti:** `Package 'ardupilot_gz_bringup' not found`

**Sebep:** Workspace source edilmemiş.

**Çözüm:**
```bash
source /home/asikarastallion/Documents/argaz/ardu_ws/install/setup.bash
```
Kalıcı çözüm için `env.sh` zaten bunu otomatik yapıyor — eğer hâlâ bulamıyorsa, build'in gerçekten başarıyla bittiğinden emin ol (Madde 4'e bak).

---

## 10. Disk alanı / derleme çok yavaş

ArduPilot + ROS2 + Gazebo kaynak derlemesi kolayca **15-20 GB** disk kullanır. Derleme başlamadan önce:
```bash
df -h /home
```
En az 25-30 GB boş alan öner. Derleme yavaşsa:
```bash
sudo apt install ccache
```
(`env.sh` ccache varsa otomatik PATH'e ekliyor.)

---

## 11. `.bashrc` değişiklikleri etkili olmuyor

Yeni terminal açmadan test ediyorsan:
```bash
source ~/.bashrc
```
Hâlâ olmuyorsa `.bashrc` içinde satırın gerçekten eklendiğini kontrol et:
```bash
tail -5 ~/.bashrc
```
`source /home/asikarastallion/Documents/argaz/env.sh` satırı orada olmalı.

---

## 12. Genel "sıfırdan başlamak istiyorum" komutu

Bir şeyler çok karıştıysa ve sadece proje klasörünü silip yeniden başlamak istersen (ROS2/Gazebo sistem paketlerine dokunmadan):
```bash
rm -rf /home/asikarastallion/Documents/argaz/ardu_ws/build
rm -rf /home/asikarastallion/Documents/argaz/ardu_ws/install
rm -rf /home/asikarastallion/Documents/argaz/ardu_ws/log
```
`src/` klasörünü ve `ardupilot/` klasörünü silmene gerek yok, sadece build çıktıları temizlenir.

---

## 13. Gazebo GUI / RViz açılmıyor ama headless simülasyon (SITL+DDS) sorunsuz çalışıyor

**Belirti:** `ros2 launch ardupilot_gz_bringup iris_runway.launch.py` çalıştırdığında `/ap/v1/*`
DDS topic'leri geliyor, sistem sağlıklı görünüyor, ama log'da şunlar var:
```
[ERROR] [rviz2-9]: process has died [pid ..., exit code 127, ...]
[ERROR] [gz sim-2]: process has died [pid ..., exit code 127, ...]
```
Yani sadece **görsel/GUI** süreçleri çöküyor, arka plan sunucusu (`gz sim -s`) etkilenmiyor.

**Sebep (VS Code'u snap üzerinden kurduysan):** VS Code'un snap paketi kendi terminaline
`GTK_PATH`, `GTK_EXE_PREFIX`, `GDK_PIXBUF_MODULE_FILE`, `GDK_PIXBUF_MODULEDIR`, `LOCPATH`,
`GIO_MODULE_DIR`, `GSETTINGS_SCHEMA_DIR` gibi ortam değişkenlerini enjekte ediyor. Bunlar,
`rviz2` ve `gz sim -g` gibi GTK/Qt tabanlı her alt sürece miras kalıyor ve snap'in kendi
paketlenmiş (sistemle uyumsuz) kütüphanelerini yüklemeye zorluyor. Sonuç, şuna benzer bir
sembol hatasıyla anlık çökme:
```
symbol lookup error: /snap/core20/current/lib/x86_64-linux-gnu/libpthread.so.0: undefined symbol: __libc_pthread_init, version GLIBC_PRIVATE
```

**Teşhis:** Başarısız komutu elle çalıştırıp gerçek hatayı gör (launch bazen stderr'i yutuyor):
```bash
source /home/asikarastallion/Documents/argaz/env.sh
timeout 5 /opt/ros/jazzy/lib/rviz2/rviz2 --help 2>&1 | head -20
```
`symbol lookup error` ve `/snap/...` yolu görüyorsan bu sorun kesinleşmiş demektir.

**Çözüm:** Bu değişkenleri `env.sh` içinde temizle (kalıcı hale getirmek için):
```bash
unset GTK_PATH GTK_EXE_PREFIX GTK_IM_MODULE_FILE GDK_PIXBUF_MODULE_FILE \
      GDK_PIXBUF_MODULEDIR LOCPATH GIO_MODULE_DIR GSETTINGS_SCHEMA_DIR
```
Bunu `env.sh`'ın en başına, ROS/Gazebo `source` satırlarından önce ekle. Tek seferlik test için:
```bash
env -u GTK_PATH -u GTK_EXE_PREFIX -u GTK_IM_MODULE_FILE -u GDK_PIXBUF_MODULE_FILE \
    -u GDK_PIXBUF_MODULEDIR -u LOCPATH -u GIO_MODULE_DIR -u GSETTINGS_SCHEMA_DIR \
    ros2 launch ardupilot_gz_bringup iris_runway.launch.py
```

**Not:** Bu sadece VS Code'u **snap** üzerinden kurduysan olur (`.deb` veya diğer paket
yöneticileriyle kurulmuşsa muhtemelen yaşanmaz). Sorunu ayırt etmek için:
```bash
env | grep -i "^SNAP" | head -3
```
Çıktı doluysa (örn. `SNAP=/snap/code/...`) bu senaryodasın demektir.

---

## Faydalı referans komutlar

```bash
# Gazebo sürümünü doğrula
gz sim --version

# ROS2 dağıtımını doğrula
echo $ROS_DISTRO

# Hangi ROS2 paketleri kurulu, ardupilot ile ilgili olanlar
ros2 pkg list | grep ardupilot

# Workspace içindeki tüm repoları güncelle
cd /home/asikarastallion/Documents/argaz/ardu_ws
vcs pull src
```
