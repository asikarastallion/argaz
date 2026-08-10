# Geçerleme sınırları

Bir deneyin, sonucunun neyi kanıtlamadığını açıkça belirttiği dört
adlandırılmış kategori.

[Doğrulama ve geçerleme](verification-vs-validation.tr.md) bu ayrımın neden
önemli olduğunu anlatır. Bu sayfa mekanizmadır: ifadeler nereye yazılır, hangi
kategoriye ne girer ve yazar yazmasa bile hangileri eklenir.

## Bu neden koşuda değil de deneyde gerekti

Her uçuş raporu v1.5'ten beri bir **Sınırlar ve yapılmayan iddialar** bölümü
taşıyor ve işe yarıyor. Ama oradaki sınırlar, bu aracın ürettiği *herhangi* bir
koşu için doğru olanlardır. Aracın kendisi tarafından, kendisi hakkında
yazılmışlardır.

Deney, bunun yetmez hâle geldiği yerdir. Bir soru koyar, bir karşılaştırmayı
denetler ve bir sayı üretir — ve bir belge

> GPS kaybı 4,7° RMS yatış takip hatasına mal oldu

dediği anda, bir simülasyon hakkında değil, bir hava aracı hakkında bir olgu
gibi okunur. Bu boşluk daha iyi ölçümle kapanmaz. Kapanacaksa, birinin
simülasyonun neyi varsaydığını, modelinin neyi içermediğini, hangi fiziksel
etkilerin hiç orada olmadığını ve testin bilerek hangi koşullara girmediğini
yazmasıyla kapanır.

Bu yüzden bir deney kendi sınırlarını dosyada, kriterlerin yanında beyan eder —
ve bunlar belgeye eklenen bir dipnot değil, belgenin bir parçasıdır.

## Dört kategori

| kategori | neye ait | okuyucu ne yapar |
|---|---|---|
| `assumptions` | sayıların bir anlam taşıması için doğru olması gerekenler | **gider doğrular** |
| `model_limitations` | simüle edilen aracın ne *olmadığı* | **iddiayı sınırlar** |
| `unverified_effects` | hiç bulunmayan ya da bulunup gerçek hiçbir şeyle karşılaştırılmamış fizik | **genelleme yapmaz** |
| `out_of_scope` | deneyin bilerek girmediği koşullar | **başka bir şey koşar** |

Ayrı olmalarının nedeni, okuyucunun her biriyle farklı bir şey yapmasıdır.
Hepsini tek bir `notes:` alanında toplamak — ki her proje eninde sonunda bunu
yapar — dört eyleme dönüşebilir ifadeyi, kimsenin okumadığı bir paragrafa
çevirir.

Bilinmeyen bir kategori saklanmaz, **yükleme anında reddedilir.** Raporun
yazdırmadığı bir ad altında dosyalanmış bir ifade, birinin yazdığı ve kimsenin
hiç okumadığı bir sınırdır; bu, hiç yazmamaktan da kötüdür: yazar onu belirtmiş
olduğuna inanır.

## Nasıl beyan edilir

```yaml
limitations:
  assumptions:
    - en: >-
        GPS loss is simulated by switching the SITL receiver off with SIM_GPS
        parameters...
      tr: >-
        GPS kaybı, SIM_GPS parametreleriyle SITL alıcısı kapatılarak simüle
        edilir. Otopilot, alıcının raporlamayı kesmesini görür; karıştırılan,
        aldatılan ya da makul ama yanlış konum bildiren bir alıcıyı görmez.
  model_limitations:
    - tr: EKF'nin GPS'siz davranışı, modelin sağladığı diğer sensörlere ve
          EK3_SRC1_POSXY gibi parametrelere bağlıdır...
  unverified_effects: [...]
  out_of_scope: [...]
```

Dördü de isteğe bağlıdır. Bir ifade ya bir metindir ya da bir `{en, tr}`
eşlemesidir; iki dil de sürüm artefaktı olduğundan yeni dosyalar ikisini de
vermelidir.

## Her zaman geçerli sınırlar

Bazı sınırlar, dosyada ne yazarsa yazsın, bu aracın koşabildiği her deney için
doğrudur. Bunlar kendiliğinden eklenir, beyan edilenlerin yanında yazılır ve
*(standing)* diye işaretlenir; böylece okuyucu, bu soru için birinin yazdığı
sınırlarla her zaman geçerli olanları birbirinden ayırabilir.

Bir tanım **bunlardan birini düşüremez.** Asıl mesele budur: bir anahtarı
yazmayarak "burada hiçbir şey donanım üzerinde ölçülmedi" ifadesini atlayabilen
bir belge onu atlardı ve o belgeyi okuyan kişi eksik olduğunu bilemezdi.

Şu anki küme — metnin kendisi için `argazui/argazui/limitations.py` dosyasına
bak, yetkili kaynak odur:

| kategori | her zaman söylenen |
|---|---|
| `assumptions` | her şey SITL'dir, hiçbir şey donanımda ölçülmemiştir; kolların aynı yapılandırmayla uçtuğu varsayılır ve bunu denetlenebilir kılan şey parmak izidir; simüle zaman aracın saatidir |
| `model_limitations` | bir SITL gövdesi sınıfının genel bir gövdesidir; bir Gazebo modeli yazarının beyan ettiğini yeniden üretir ve gerçek bir hava aracının ölçümüyle hiç karşılaştırılmamıştır |
| `unverified_effects` | batarya gerilim düşüşü, ESC ve motor dinamikleri, pervane verimi, yapısal esneklik ve yıpranma ya yoktur ya idealizedir; gerçek sensörler hiçbir parametrenin yeniden üretmediği biçimlerde bozulur |
| `out_of_scope` | HITL, gerçek uçuş kontrolcüleri ve gerçek gövdeler; birden fazla araç; kaydedilen prosedürlerin dışında yapılan her şey |

## Hiç beyan etmeyen bir deney

Buna izin verilir ve belge bunu açıkça söyler:

> **Bu deney kendine ait bir sınır beyan etmedi**, bu yüzden yalnızca aşağıdaki
> her zaman geçerli olanlar uygulanır. Buna izin vardır ve fark edilmeye
> değerdir: belirli bir soru için en çok önem taşıyan sınırlar, genellikle
> yalnızca o sorunun yazarının bildiği sınırlardır.

Bu bir dürtmedir, bir kapı değil. Her deneyi bir sınır beyan etmeye zorlayan bir
kural, kuralı sağlamak için yazılmış sınırlarla dolu bir depo üretirdi; bu da
dürüst bir boşluktan kötüdür.

## Nerede görünürler

| | |
|---|---|
| `experiment.md` §10 | önce beyan edilenler, sonra her zaman geçerli olanlar, kategorilere ayrılmış |
| `experiment.json` | `limitations` — her ifade bir satır, `source` alanıyla |
| Deneyler paneli | aynı liste, karşılaştırmanın altında |
| `GET /api/limitations` | dört kategori, her birine ne girdiği ve her zaman geçerli ifadeler |

Arayüzde kopyalanmak yerine modülden servis edilir; arıza ve metrik
kataloglarıyla aynı gerekçe: koda eklenen her zaman geçerli bir sınır, onu
gösteren sayfadan eksik kalabilecek durumda olmamalıdır.

## Bu ne değildir

Bir risk kaydı, bir tehlike analizi ya da bir emniyet dosyası değildir. Bir
simülasyon sonucunun neyi kanıtlamadığını kaydeder. Bu konuda ne *yapılacağına*
— boşluğun önemli olup olmadığına, onu neyin kapatacağına, aracın uçup
uçamayacağına — karar vermek bir insana ait mühendislik yargısıdır ve bu depodaki
hiçbir şey buna kalkışmaz.

Geçerleme sınırları ArgazUI v1.6'da eklendi.
