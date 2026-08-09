# Süreç ve oturum yaşam döngüsü

## BAŞLAT

1. Koşu kaydedicisi **önce** açılır, daha hiçbir komut yazılmadan; böylece
   açılış çıktısı — Gazebo ya da SITL hatası dahil — `console.log` içine
   düşer.
2. `session.build_launch_commands(model)`, modelin başlatma yöntemi için tam
   kabuk satırlarını üretir. Bu satırlar SİMÜLASYON terminaline birebir
   yazılır; böylece ne çalıştığı anlatılmaz, görünür.
3. MAVLink bağlantısı başlar ve 14550 portunda heartbeat bekler.
4. Yetenekler **araçtan** sorgulanır — `Q_ENABLE`, `Q_TAILSIT_ENABLE`,
   `Q_OPTIONS` — çünkü `models.json` bunları yanıtlayamaz. SkyCat TVBS orada
   düz bir QuadPlane olarak kayıtlıdır ve parametre dosyası onu tailsitter
   yapar.

## Neden iki terminal var

Simülasyon kabuğun ön planını işgal eder ve bu *zorunludur*: `sim_vehicle.py`
yolunda MAVProxy etkileşimlidir ve ön planda olmayan bir süreç stdin okuyamaz —
SIGTTIN ile durur. O kabuk ön planı tuttuğu sürece başka bir şey çalıştıramaz;
bu yüzden ArgazUI görev scriptleri ve elle komutlar için ikinci, boş bir kabuk
açar.

## Komutlar neden terminale değil MAVLink'e gider

`ros2_launch` yolunda MAVProxy'yi ROS 2 başlatır ve `--non-interactive`
bayrağını verir. O MAVProxy stdin'i hiç okumaz; dolayısıyla terminale `mode
guided` yazmak Iris'te hiçbir şey yapmaz. Her iki başlatma yolu da MAVLink
çıkışı üretir, bu yüzden butonlar o kanalı kullanır — her modelde aynı şekilde
ve raporlanacak bir ACK ile.

## DURDUR

1. Çalışan prosedür iptal edilir ve beyan ettiği parametre override'ları bir
   `finally` bloğundan geri alınır.
2. MAVLink bağlantısı durur.
3. Çocuk süreçler **süreç grubuyla** sonlandırılır, asla isimle değil.
4. Kapanışta iki tanıdık mesaj çıkar ve ikisi de zararsızdır: Gazebo'nun `gz`
   sarmalayıcısı `Errno::ESRCH` verir çünkü çocuklar zaten grup üzerinden
   kapatılmıştır; MAVProxy'nin `log_writer` thread'i ise kendi telemetri logunu
   kapatırken hata verir. İkisi de otopilotun dataflash logunu yazmaz — onu
   SITL yazar — ve her koşu o logun eksiksiz kapanıp kapanmadığını kaydeder.
5. Artefaktlar **ancak bundan sonra** toplanır. Dataflash logu süreç çıkınca
   kapanır; daha erken kopyalamak yarım bir dosya arşivlemek olurdu.

## Bir süreci asla ismiyle eşleştirme

`pkill -f arduplane` bu projenin hiçbir yerinde kullanılmaz ve kullanılmamalıdır.
Komut satırında o metni geçiren her şeyi eşleştirir — dosyayı açık tutan bir
editörü ve test koşucusunun kendisini dahil. ArgazUI'nin başlattığı her süreç
kendi oturumunda (`start_new_session=True`) çalışır ve süreç grubuyla
sonlandırılır.

## Sunucuyu kapatmak

Ctrl+C ile durdurulan bir sunucu önce koşusunu tamamlar. Aksi hâlde gerçek bir
uçuşun artefaktları yarım kalırdı — ki koşu dizini tam olarak bu durum için
vardır.

## Sıcak yeniden yükleme ve yüklenmeyenler

Diskten dört katman okunur ve sunucu çalışırken bunlardan yalnızca ikisi
bayatlayabilir:

| katman | yeniden yüklenir mi? |
|---|---|
| `argazui/**/*.py` | **hayır** — bir kez import edilir; yeniden başlatılana kadar bayattır |
| `static/**` | her istekte servis edilir, ama çalışan kodun sunduğu API'ye göre yazılmıştır |
| `procedures/*.yaml` | evet, mtime değişince |
| `config/*.json` | evet, her istekte |

Sayfa, kendisine servis edilen derleme kimliğini `/api/version` ile
karşılaştırır ve farklıysa bunu açıkça söyler: önceki bir checkout'tan kalma
bir sunucu tarayıcıya bugünün arayüzünü verirken dünün API'siyle yanıtlar ve bu
arıza, sayfadaki bir hata gibi görünür.
