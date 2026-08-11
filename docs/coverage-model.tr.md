# Kapsam modeli

ArgazUI'nin neyi kapsam saydığı ve neyi saymayı reddettiği.

> Bu sayfa gerekçedir. **Rapor**, diskteki koşulardan üretilir ve her CI
> koşusunda üzerine yazılır — bkz. [coverage.md](coverage.md);
> [verification-model.tr.md](verification-model.tr.md) ile
> [status.md](status.md) arasındaki ilişkinin aynısı.

## Test sayısı değil

Bir test sayısı, biri test eklediğinde artar ve biri bir hava aracı, bir
prosedür ya da kimsenin koşmadığı bir kriter eklediğinde hiç azalmaz. Emeği
ölçer, erişimi değil; ve bu sayıyı izleyen bir proje er ya da geç geçen aydan
daha azını kapsayan bir test takımıyla gurur duyar hâle gelir.

Bu yüzden kapsam, **çalıştırılabilecek adlandırılmış şeyler** üzerinden, beş
boyutta ölçülür ve her boyut ulaşamadığı maddeleri listeler.

> Altında liste olmayan bir yüzde, okumayı bırakmaya davettir. Asıl teslim
> edilen şey listedir.

## Beş boyut

| boyut | ne zaman kapsanmış sayılır |
|---|---|
| **Modeller** | katman 2, kayıt defteri girdisini Gazebo'da uçurduysa |
| **Prosedürler** | kayıtlı bir koşu prosedür dosyasını çalıştırdıysa |
| **Kriterler** | bir koşu kabul kriterini gerçekten **değerlendirdiyse** |
| **Arızalar** | bir koşu ariza türünü ya da beyan edilmiş senaryo arızasını gerçekten **enjekte ettiyse** |
| **Deneyler** | kayıtlı bir koşu deneyin damgasını taşıdıysa — hem deney başına hem **kol başına** listelenir |

Bir [deneyin](experiments.tr.md) kolları, deneyin kendisinden ayrı listelenir;
beyan edilmiş bir senaryo arızasının, arkasındaki mekanizmadan ayrı
listelenmesiyle aynı gerekçeyle: kollarının yarısı uçurulmuş bir deney hiçbir
şeyi yanıtlamamıştır ve aksi hâlde kapsanmış görünürdü. Bir karşılaştırma iki
tarafı da ister.

Katman 1 model kapsamına sayılmaz. SITL'in kendi genel gövdelerini uçurur ve bir
hava aracı hakkında hiçbir şey söylemez — bir katman-1 koşusunu model kapsamı
saymak, tam olarak [status.md](status.md) dosyasının önlemek için var olduğu
karıştırmanın başka bir tabloya yöneltilmiş hâlidir.

**Atlanmış** bir katman-2 testi de kapsam değildir. Kapsamın yokluğudur.

## İki ret

### Kimsenin ulaşmadığı bir kriter kapsanmış değildir

Prosedürün hiç ulaşamadığı bir kriter — önceki bir adım düştüğü ya da dayandığı
telemetri hiç gelmediği için — araç hakkında hiçbir bilgi üretmemiştir. Sırf bir
`result.json` içinde göründüğü için saymak, ikinci adımda duran bir koşunun tam
kriter kapsamı raporlamasına izin verirdi.

Değerlendirilmiş ve **düşmüş** bir kriter kapsanmış *sayılır*. Kapsanmış, "bir
koşu bunu çalıştırdı ve bir sonuç üretti" demektir; düşen bir kriter de en
bilgilendirici türden sonucu üretmiştir. Yalnızca geçenleri saymak, kapsamı
ikinci ve daha kötü bir geçiş oranına dönüştürürdü.

### Tanımlayıcısı olmayan bir kriter tahmin edilmez, sayılır

ArgazUI v1.5'ten önce kaydedilmiş koşular
[kriter tanımlayıcısı](traceability.tr.md) taşımaz. Bugünün kriterleriyle
konuma göre eşleştirilmezler: prosedür o zamandan beri düzenlenmiş olabilir ve
tahminle şişirilmiş bir kapsam değeri, bu projenin ortadan kaldırmak için
yeniden kurulduğu hak edilmemiş iddianın ta kendisidir.

Onun yerine sayılır ve raporlanırlar; böylece yükseltmeden sonraki %0'lık ilk
okuma, hiçbir şeyi test etmeyen bir proje gibi görünmek yerine belirtilmiş bir
gerekçeye sahip olur. Prosedürleri bir kez daha uçurun, değer dolar.

## Nasıl çalıştırılır

```bash
python3 -m argazui coverage                        # docs/coverage.md yazar
python3 -m argazui coverage --runs runs --json
```

Çıkış kodu her zaman `0`. **Kapsam bir ölçümdür, bir kapı değil.** Kapsanmayan
bir prosedürü olan projenin bir boşluğu vardır; bunu kırmızı bir derlemeye
çevirmek, doğru olan şeyi — bir prosedürü uçurulabilmeden önce beyan etmeyi —
CI'ı bozan şey hâline getirirdi.

`python3 -m argazui status`, `coverage.md` dosyasını `status.md` ile aynı
derlemeden yazar; böylece birindeki "neler test edilmedi" özeti ile diğerindeki
tam listeler hangi koşuları okuduğu konusunda asla çelişemez.

## "Kapsanmış" ne demek değildir

- Sonucun geçtiği anlamına gelmez — bkz. [status.md](status.md).
- Yakın zamanda çalıştırıldığı anlamına gelmez.
- Birden fazla kez çalıştırıldığı anlamına gelmez — bkz.
  [campaigns.tr.md](campaigns.tr.md).

**Kapsanmayan** madde daha faydalı olanıdır: bu projenin beyan ettiği ve hiç
koşmadığı bir şeydir — bir doğrulama iddiasının üzerinden atlanarak
okunmaması gereken boşluğun ta kendisi.

## Mekanizma matrisi: tek bit yerine beş cevap

Boyut başına bir oran doğru bir özettir ve v1.7'nin sorduğu soruyu yanıtlayamaz:
*bu projenin sahip olduğunu SÖYLEDİĞİ mekanizma gerçekten çalıştırılabilir mi ve
onu hiç çalıştıran oldu mu?*

"Kapsanmış" tek bir bittir ve ayırt edilebilir beş cevap vardır. `faults.KINDS`
içinde birim testleriyle var olan ve hiçbir senaryosu olmayan bir arıza türü,
senaryosu olan ama hiçbir koşunun uçurmadığı bir türle aynı değildir; ikisi de
uçurulmuş ve kriterlerle hüküm verilmiş bir türle aynı değildir. Üçünü birden
"kapsanmamış" diye raporlamak, bundan sonra ne yapılacağını söyleyen ayrımı
kaybeder.

| durum | anlamı |
|---|---|
| `DEFINED` | kod ya da bir belge onu beyan eder |
| `EXECUTABLE` | onu gerçekten çağırabilecek bir şey var — bir senaryo onu gösterir |
| `EXERCISED` | kayıtlı bir koşu onu bir araca uyguladı |
| `VERIFIED` | kayıtlı bir koşu onu uyguladı **ve** bir kriter sonucu değerlendirdi |
| `NOT_EXERCISED` | tanımlanabilir ve çalıştırılabilir, ve hiçbir şey onu koşturmadı |
| `UNSUPPORTED` | beyan edilmiş ve burada çalıştırılamayacağı bilinen, gerekçesiyle |

### Bir hava aracı hakkında bir şey söyleyen tek durum `VERIFIED`'dır

Ve ona ulaşmak bilerek zordur. Enjekte edilip hükümsüz bırakılan bir arıza
`VERIFIED` değil `EXERCISED`'dır; çünkü *mekanizma işledi* ile *araç bununla
başa çıktı* iki ayrı iddiadır — `FaultResult`'ın dört ayrı alanla dayattığı
ayrımın aynısı. Her kriteri eksik kanıt yüzünden reddedilmiş bir prosedür
uygulanmıştır ve hiçbir şeyi doğrulamamıştır.

`VERIFIED`, **geçti** değil **hüküm verildi** demektir. Ölçülmüş ve
sağlanmamış bir kriter, geçen bir kriter kadar doğrulamıştır: mekanizma koştu ve
araç hakkında bir hüküm üretti. Geçmiş olmayı şart koşmak, matrisi kanıtı değil
yeşili ödüllendirir hâle getirirdi.

### Hiçbir şey bir koşu dizini olmadan yükseltilemez

`EXECUTABLE` üzerindeki her hücre, arkasındaki koşu kimliklerini adlandırır;
böylece matristeki bir iddia açılıp denetlenebilir. Burada çalıştırılamayan bir
mekanizma, gerekçesiyle `UNSUPPORTED` işaretlenir ve **uydurulmaz** — eksik bir
bağımlılık yüzünden projeyi cezalandıran bir rapor, birini kanıt uydurmaya
iterdi; bu matris tam da bunu görünür kılmak için vardır.

Matris, aynı koşu dizinlerinden, her çağrıda yeniden hesaplanarak boyutların
yanında `docs/coverage.md` içine yazılır. Altıncı bir boyut değildir: bir oran
değildir ve onu bir orana zorlamak durumları kaybettirirdi.
