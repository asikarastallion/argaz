# Geliştirme ve test

## Test kümesinin dayandığı kural

Testler, arayüz butonlarının çalıştırdığı **aynı** prosedür YAML'ını, **aynı**
`ProcedureRunner` üzerinden, **gerçek** bir SITL ikili dosyasına karşı koşturur
ve sonuçlarını arayüzün ürettiği **aynı** `runs/` dizinlerine yazar.

Test kümesinin hiçbir yerinde ikinci bir kalkış uygulaması ya da simüle edilmiş
bir otopilot yoktur. Bu denklik, kümenin bütün varlık sebebidir: yeşil bir test,
çalışan bir buton demektir.

## İşaretler (marker)

| işaret | gerektirir | neyi iddia edebilir |
|---|---|---|
| `tier1` | derlenmiş bir SITL ikili dosyası. Hiçbir şey gerektirmeyen saf birim testleri de bu işareti taşır. | prosedür mantığı, API, sayfa |
| `tier2` | SITL **ve** Gazebo **ve** model varlıkları | belirli bir modeli |
| `e2e` | süreç olarak sunucu ve başsız Chromium | kullanıcının tarayıcısının gördüğünü |
| `container_only` | katman imajı | başka yerde atlandığında *doğrulanmadı* diye raporlanır |

```bash
python3 -m pytest tests/ -m tier1 -q
python3 -m pytest tests/ -m tier2 -q -k skywalker
python3 -m pytest tests/ -m e2e -q
python3 -m pytest tests/test_temporal_criteria.py -q    # araç gerekmez, milisaniyeler
```

Test bağımlılıkları için `pip install -r argazui/requirements-test.txt`,
ardından e2e katmanı için `python3 -m playwright install chromium`.

## Atlamak geçmek değildir

Eksik ikili dosya, eksik Gazebo, eksik model: test gerekçesiyle **atlanır** ve
durum üreteci modeli `untested` olarak kaydeder. Bu kümede hiçbir şey,
uçurmadığı bir şey için başarı raporlamaz.

Her koşu `runs/tests/suite.json` yazar ve her aşamayı kaydeder — kurulum
sırasındaki bir atlama dahil; `report.passed` üzerine indirgemek bunu "hiçbir
şey" sayardı. "Hiçbir şey" ise tam olarak bir durum tablosunun tahminle
doldurduğu boşluktur.

Terminal özeti, kimse toplamı okumadan önce o ortamın **doğrulamadığı** şeyleri
adıyla yazar; çünkü yeşil bir özet satırı "her şey çalışıyor" diye okunur.

## Bir yeniden deneme, ve asla sessiz değil

Bir prosedürün bir yeniden deneme hakkı vardır: SITL yüklü bir makinede
gerçekten zamanlamaya duyarlıdır ve oturmamış bir EKF, on saniye sonra kabul
edeceği bir arm'ı reddedebilir. Bu denemenin bir bedeli vardır — `mark_flaky`,
koşunun [status.md](status.md) içinde `passed` değil `flaky` görünmesini sağlar
ve her deneme `result.json` içinde kalır. Yeşile ulaşana kadar sessizce yeniden
denemek, bu projenin engellemek için var olduğu davranışın ta kendisidir.

## Neden `pytest-timeout` yok

Her uçuş zaten iki yönden sınırlıdır: her prosedür kendi `timeout:` tavanını
taşır ve `tests/sitl.py`, SITL portunu hiç açmazsa vazgeçer. CI işleri bunun
üstüne `timeout-minutes` koyar. Aynı şeyi tekrarlamak için bir eklenti eklemek,
hiçbir şey için bir bağımlılık olurdu.

## e2e katmanı ve varlık sebebi

Her katman-1 testi `RunRecorder` ve `ProcedureRunner` nesnelerini doğrudan
sürer. Prosedür mantığını test etmenin doğru yolu budur ve uygulama tarayıcıda
kullanılamaz hâldeyken hepsinin yeşil olmasının sebebi de budur: FastAPI,
WebSocket ve sayfa hiç çalıştırılmıyordu. O regresyonu bir kullanıcı buldu.

Bu yüzden e2e testleri yalnızca bir kullanıcının yaptığını yapar — sunucuyu
süreç olarak başlatır, sayfayı başsız Chromium'da açar, tarayıcının gördüğü şeye
bakar. **Her şeyden önce konsolun temiz olduğuna.** Konsolu izlemeden sayfayı
süren bir "e2e testi", yakalamak için var olduğu regresyonun içinden geçip
giderdi: sayfa dolu görünüyordu ve tek kanıt yakalanmamış bir `TypeError`'dı.

Her e2e sunucusu `argazui/` dizininin atılabilir bir kopyasından koşar; böylece
gerçek kayma gerektiren testler — düzenlenmiş bir `.py`, dokunulmuş bir
prosedür — bunu checkout'a hiç yazmadan üretir.

## Bilerek kırmızı bırakılan bir test

`sitl_tailsitter` katman 1'de bilerek başarısızdır. Gövde arm olur, mod
değiştirir, gaz koluna uyar ve takla atarken 20 m'yi geçer; ArduPilot'un kendi
test kümesi onu *"unstable in hover; unflyable in cruise"* diye listeler ve
atlar. Kendi testimiz geçsin diye gövdeyi ayarlamak hiçbir şey kanıtlamaz;
`xfail` işaretlemek ise başarısızlığı görünmez kılardı. Bkz.
`tests/test_tier1_procedures.py` içindeki açıklama.

## Yeni bir test eklemek

Saf değerlendirici testlerini konusunun yanına koy
(`tests/test_temporal_criteria.py`, `tests/test_regression.py`) ve `tier1` ile
işaretle — işaret, hangi CI işinin koşturacağını söyler, araç gerektirdiğini
değil. Başlatılmış bir SITL gerektiren testler `support.boot()` kullanır; bu,
BAŞLAT'a basmanın test tarafındaki karşılığıdır: aynı `MavlinkLink`, aynı
`RunRecorder`, aynı yetenek sorgusu; yalnızca taşıma katmanı farklıdır.
