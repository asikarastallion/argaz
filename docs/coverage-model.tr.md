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

Bu yüzden kapsam, **çalıştırılabilecek adlandırılmış şeyler** üzerinden, dört
boyutta ölçülür ve her boyut ulaşamadığı maddeleri listeler.

> Altında liste olmayan bir yüzde, okumayı bırakmaya davettir. Asıl teslim
> edilen şey listedir.

## Dört boyut

| boyut | ne zaman kapsanmış sayılır |
|---|---|
| **Modeller** | katman 2, kayıt defteri girdisini Gazebo'da uçurduysa |
| **Prosedürler** | kayıtlı bir koşu prosedür dosyasını çalıştırdıysa |
| **Kriterler** | bir koşu kabul kriterini gerçekten **değerlendirdiyse** |
| **Arızalar** | bir koşu ariza türünü ya da beyan edilmiş senaryo arızasını gerçekten **enjekte ettiyse** |

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
