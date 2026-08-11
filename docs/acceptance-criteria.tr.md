# Kabul kriterleri

Kabul kriteri, prosedürün uçuşun işe yarayıp yaramadığına karar veren
parçasıdır. Prosedürün `expect:` bloğunda beyan edilir, `ProcedureRunner`
tarafından ölçülmüş araç durumuna karşı değerlendirilir ve bir koşuyu kırmızıya
döndürebilecek tek şeydir.

Sözdiziminin tamamı
[`argazui/procedures/SCHEMA.md`](../argazui/procedures/SCHEMA.md) içindedir. Bu
sayfa, kriterlerin *ne anlama geldiğiyle* ilgilidir.

## ACK başarı değildir

`MAV_RESULT_ACCEPTED`, otopilotun bir komutu değerlendirmeye almaya razı
olduğunu söyler. Hava aracı hakkında hiçbir şey söylemez. Bu yüzden buradaki
her kriter ölçülmüş duruma karşı değerlendirilir — ulaşılmış bir irtifa,
heartbeat'te geri dönen bir mod numarası, gerçekten olmuş bir disarm.

## Koşullar

| koşul | ne zaman doğrudur |
|---|---|
| `armed: true` / `false` | arm bayrağı eşleşiyor |
| `mode: QLOITER` | mevcut mod eşleşiyor — numara üzerinden |
| `mode_in: [QLOITER, QHOVER]` | mevcut mod bunlardan biri |
| `alt_above: 15` / `alt_below: 1.5` | göreli irtifa, metre |
| `climb_rate_above` / `climb_rate_below` | `VFR_HUD.climb`, m/sn |
| `groundspeed_above: 5` | `VFR_HUD.groundspeed`, m/sn |
| `prearm_ok: true` | `SYS_STATUS` ARM öncesi sağlık biti set |
| `param: {name: Q_ENABLE, min: 1}` | parametre sınırlar içinde |
| `attitude_stable: {...}` | biriktirilmiş tutum zarfı korundu |
| `roll_within: [-20, 20]` | şema 2 — anlık yatış, derece |
| `pitch_within: [-20, 20]` | şema 2 — anlık yunuslama, derece |
| `angular_rate_above: 90` | şema 2 — \|p\|, \|q\|, \|r\| içindeki en büyüğü, °/sn |
| `angular_rate_below: 90` | şema 2 — aynı büyüklük, ters yönde |

Euler açısının değişim hızı yerine gövde eksen hızları kullanılır: Euler
açıları dik tutumda tekildir — burun +90° yunuslamaya yakınken yatış ve sapma
aynı dönüşü tarif eder — ve bir tailsitter kalkışının tamamını orada geçirir.

## Zamansal biçimler

Şema 1'de tek bir biçim vardı: *bu şu anda doğru mu, ya da bir zaman aşımından
önce doğru oluyor mu?* Bu, aracın nerede sonlandığını söyler, başka bir şey
söylemez. Şema 2, **ne zaman** ve **ne kadar süreyle** sorularını yanıtlayan üç
biçim ekler.

```yaml
schema: 2

expect:
  # bir süre sınırı içinde DOĞRU HÂLE GELMELİ
  - condition: {alt_above: "{alt*0.9}"}
    within: 20s

  # doğru hâle gelmeli, sonra kesintisiz DOĞRU KALMALI
  - condition: {alt_above: "{alt*0.9}", armed: true, mode: GUIDED}
    for: 5s

  # bir pencere boyunca gözlenen hiçbir anda DOĞRU OLMAMALI
  - condition: {angular_rate_above: 180}
    never: 5s
```

Kriter başına en fazla bir zamansal anahtar. İkisi bir arada tek bir
değerlendirme sırası vermez ve anlamı okuyana göre değişen bir kriter, hiç
olmayan bir kriterden kötüdür.

### Süreler birimini yazmak zorundadır

`10s`, `500ms`, `2min`. Çıplak bir `for: 5` yükleme anında reddedilir.

Bir prosedürdeki diğer her sayı bir metre, bir derece, bir PWM değeri ya da bir
parametre değeridir. Bunlardan birine benzeyen bir süre tam olarak bir kez
yanlış okunurdu — sessizce, uçuş sırasında, dosyayı devralan kişi tarafından.
`m` burada bilerek bir birim değildir: bir uçuş prosedüründe metre diye okunur.

### Aracın saatiyle ölçülürler

Süreler `time.time()` ile değil, `ATTITUDE.time_boot_ms` ile sayılır. SITL
hızlandırması altında bir duvar saati saniyesi bir uçuş saniyesi değildir;
dolayısıyla varış zamanına göre değerlendirilen bir `for: 5s`, yazdığının beş
katı kadar uçuş isterdi — ya da beşte biri kadar, hızlandırmanın yönüne göre.

Aracın saati yalnızca telemetri geldiği sürece ilerler; bu yüzden her pencere
ayrıca, ölçülen hızlandırmadan türetilmiş bir duvar saati emniyeti taşır.
Pencereyi kapatan şey o emniyetse, kriter bunu sonucunda belirtir: duvar
saatiyle yapılmış bir ölçümü araç zamanıymış gibi raporlamak, koşunun
kanıtındaki her süreyi hızlandırma katsayısı kadar yanlış yapardı.

### `for:` baştan başlamaz

Bekleme penceresi içindeki bir kopma kriteri düşürür ve ne kadar süre
korunduğunu raporlar. Yeniden başlayan bir pencere, açılıp kapanan bir koşulun
eninde sonunda geçmesine izin verirdi — ki bu, *kesintisiz* kelimesinin tam
tersidir.

### `never:`, gözlenen şey hakkında bir iddiadır

Değerlendirici araç durumunu her 0,2 duvar saati saniyesinde bir okur. Araç
zamanı cinsinden bir örnekleme aralığından kısa bir sapma, iki örnek arasında
görülmeden geçebilir; bu saklanmaz, yazılır: `never`, o hızda gözlenen şey
hakkında bir iddiadır.

Aracın gönderdiği **her** tutum örneğini tartan kriter `attitude_stable` olmaya
devam eder; soru "araç bir bandın dışında ne kadar zaman geçirdi" ise doğru
araç odur.

### Sessizlik asla başarı değildir

**Her** koşul, dayandığı telemetriyi adıyla bildirir; sinyali hiç gelmemiş bir
koşul, dört biçimin hiçbirinde sağlanmış sayılamaz.

| koşul | gerektirdiği |
|---|---|
| `armed`, `mode`, `mode_in` | araçtan bir `HEARTBEAT` |
| `alt_above`, `alt_below` | `GLOBAL_POSITION_INT` |
| `climb_rate_above`, `climb_rate_below`, `groundspeed_above` | `VFR_HUD` |
| `roll_within`, `pitch_within`, `angular_rate_*`, `attitude_stable` | `ATTITUDE` |
| `prearm_ok` | `SYS_STATUS` |
| `param` | aracın okumayı yanıtlaması — bu zaten kapalı tarafa düşer |

Gerekçe şu: araç durumundaki her alanın bir başlangıç değeri vardır ve
başlangıç değeri bir ölçüm değildir. `alt`, bir kayan sayı bir yerden başlamak
zorunda olduğu için 0,0'dan başlar; bu, aracın **yerde olduğu anlamına gelmez**
ve yalnızca değere bakıldığında ikisi birbirinin aynısıdır. v1.6 düzeltme
sürümüne kadar değerlendirici için de aynıydılar: `alt_below: 3` ve
`armed: false` — ki ikisi birlikte her iniş prosedürünün kabul bloğunun
tamamıdır — hiçbir şeyin yazmadığı bir duruma karşı doğru çıkıyordu ve konum
akışı hiç gelmemiş bir uçuş için koşu kaydı `yerde — alt=0.0m` diyordu.

Bu şekilde reddedilen bir kriter **değerlendirilmedi** durumundadır; bu üçüncü
bir sonuçtur ve bir başarısızlık değildir:

| `passed` | `evaluated` | anlamı |
|---|---|---|
| `true` | `true` | araç kriteri sağladı |
| `false` | `true` | araç sağlamadı — araç hakkında bir hüküm |
| `false` | `false` | hiçbir şey ölçülmedi — hiçbir şey hakkında hüküm **değil** |

Koşu yine de geçmez. Değişen şey, nasıl raporlandığıdır: değerlendirilmemiş bir
kriter `acceptance` değil `evidence` olarak sınıflandırılır, çünkü aracın yanlış
bir şey yaptığı anlamına gelen tek kategori `acceptance`'tır. Bkz.
[failure-classification.tr.md](failure-classification.tr.md).

Bir `for:` ya da `never:`, penceresi **açılmadan önce** reddedilir; çünkü bir
zaman aralığı hakkında olumlu bir iddiada bulunur. `within:` ve şema 1 biçimi
ise birer bekleyiştir, dolayısıyla beklemeyi sürdürürler — bir bekleyişin
ortasında gelmeye başlayan telemetri gayet geçerli bir uçuştur — ve yalnızca
süre dolduğunda sinyal hâlâ eksikse reddedilirler.

## `attitude_stable` ve varlık sebebi

`tailsitter_takeoff`, 1300 °/sn'ye varan hızlarla takla atan bir araçta üç kez
geçti. İrtifaya ulaştı, armlı kaldı ve QHOVER bildirdi — kriterlerin sorduğu
tek üç şey. İrtifa, bir süre boyunca kabaca yukarıyı gösteren bir itki
vektörünün yan etkisidir.

`attitude_stable` prosedürün tamamındaki tutumu biriktirir ve tepe değerlerle
değil, **bandın dışında geçen saniyelerle** değerlendirilir: bir tepe tek bir
örnektir ve tek bir örnek bir rüzgâr, bir mod değişimi ya da kötü bir okumadır.
Her prosedür bu saniyelerden kaçını affettiğini kendisi beyan eder.

Zaten prosedürün tamamı hakkında bir cevap olduğu için, ayrıca bir zamansal
anahtar taşıyamaz. Onun için anlık koşulları kullan.

## Geriye dönük uyumluluk

Şema 1 dosyaları eskisi gibi yüklenir ve eskisi gibi davranır. Zamansal
kriterler ve anlık tutum koşulları `schema: 2` ister; bunları kullanan bir
şema-1 dosyası yükleme anında, sebebini söyleyen bir mesajla reddedilir. Şema
1'i yerinde genişletmek daha sessiz ve daha kötü olurdu: eski bir ArgazUI,
karşıladığını iddia ettiği bir sürüm numarası taşıyan bir belgeden,
uygulamadığı bir `within:` okurdu.
