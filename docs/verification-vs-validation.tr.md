# Doğrulama (verification) ve geçerleme (validation)

Birbirinin yerine kullanılan ama farklı şeyler anlatan iki kavram. ArgazUI
bunlardan birini yapar.

| | yanıtladığı soru | ArgazUI |
|---|---|---|
| **Doğrulama** | Uygulama, birilerinin beyan ettiği kriterleri karşıladı mı? | **evet, yaptığı şey budur** |
| **Geçerleme** | Model, kriterler ve senaryo, gerçekten önemsenen davranışı temsil ediyor mu? | **hayır** |

Bu depodaki her yeşil sonuç bir doğrulama sonucudur. Bir prosedürün koştuğunu ve
içindeki kriterlerin sağlandığını söyler. Bunların doğru kriterler olup
olmadığı, simüle aracın gerçeğine benzeyip benzemediği ya da senaryonun hiç
yaşanan bir şey olup olmadığı hakkında hiçbir şey söylemez.

## Bu sayfa neden var

Çünkü aradaki boşluk okuyucunun zihninde kendiliğinden kapanır.

Geçen kontrollerle dolu bir sayfa, bir kapsam değeri, özetlenmiş artefaktlarla
dolu bir koşu dizini ve çözülen bir izlenebilirlik zinciri — hepsi *bu araç
çalışıyor* diye okunur. Hiçbiri bunu söylemez. Bu projenin bütün düzeneği
doğrulama iddialarını kesinleştirmek için kurulmuştur ve onları fazla
okunabilir kılan tam da bu kesinliktir.

Bu yüzden uçuş raporunun son bölümü
[**Sınırlar ve iddia olmayanlar**](runs-and-evidence.tr.md) başlığını taşır ve
bu sayfa, o bölümün işaret ettiği yerdir.

## SITL neyin kanıtıdır

SITL, **simüle bir fizik modeli altındaki yazılım davranışının** kanıtıdır. Bu
hem gerçekten faydalı hem de gerçekten sınırlıdır.

Gösterebildikleri:

- otopilot mantığının prosedürün istediğini yaptığı — bir moda girildiği, bir
  komutun kabul edildiği, bir irtifaya ulaşılıp korunduğu;
- ArgazUI'nin kendi katmanlarının çalıştığı — prosedür koşturucusu, kriterler,
  kanıt zinciri;
- bir değişikliğin, adı verilmiş bir referansa göre bir şeyi ölçülebilir
  biçimde kötüleştirdiği;
- davranışın N koşu boyunca tekrarlandığı ya da tekrarlanmadığı.

Gösteremedikleri:

- hava aracının uçtuğu. Dinamik model bir modeldir. SITL'de kusursuz asılı duran
  bir tailsitter havada trimlenemez olabilir; SITL'de takla atan biri gayet iyi
  olabilir.
- sensörlerin davrandığı. Simüle GPS, IMU ve barometre gürültüsü, bir cihazdan
  ölçülmüş değil makul görünsün diye seçilmiş gürültü modelleridir.
- zamanlamanın tuttuğu. SITL genel amaçlı bir işletim sisteminde bir hız
  çarpanıyla koşar; gerçek bir uçuş kontrolcüsü gerçek donanımda gerçek bir
  zamanlayıcı çalıştırır.
- güç, sıcaklık, titreşim, EMI, gövde esnemesi ya da hava araçlarını gerçekten
  bozan şeylerin herhangi biri hakkında hiçbir şey.

> **Hiçbir dinamik model, ne kadar iyi olursa olsun, donanım hakkında kanıt
> değildir.**

## Geçerleme ne olurdu

Bu araç değil. Bir uçuş kontrol iddiasının geçerlenmesi en azından şunları
ister:

- gerçek gövdede, ölçüm donanımıyla yapılmış uçuş testi;
- simülasyonun öngördüğü ile aracın yaptığı arasında bir karşılaştırma;
- simülatörün ölçebildiğinden değil, aracın *ne için* olduğundan türetilmiş ve
  görevi bilen biri tarafından gözden geçirilmiş kriterler.

ArgazUI bunlardan ikincisine katkı verebilir: bir koşu dizini, simülasyonun ne
öngördüğüne dair eksiksiz, özetlenmiş ve tekrarlanabilir bir kayıttır ve bunu
gerçek bir uçuşla karşılaştırmak istemek makul bir arzudur. Bu karşılaştırmayı
kendisi yapmaz ve yaptığı iddiasında da değildir.

## Kriterler nereden geliyor ve bu ne anlama geliyor

Bu projedeki bir kriteri, prosedürü yazan kişi yazar. Eşiği bir yorumda
savunulur ve ArduPilot'un kendi dokümantasyonundan geliyorsa kaynak verilir —
bkz. [acceptance-criteria.tr.md](acceptance-criteria.tr.md).

Bu dürüst bir mühendislik pratiğidir ve bir gereksinimle **aynı şey değildir**.
Buradaki hiçbir şey belirtilmiş bir operasyonel ihtiyaca izlenmez, çünkü
izlenecek bir gereksinim belgesi yoktur ve v1.5 bilerek öyle bir belge icat
etmedi. [İzlenebilirlik](traceability.tr.md) bir iddiayı kanıtına bağlar;
amacına bağlamaz.

Sonucu açıkça söylemeye değer: **bu projenin sağladığı bir kriteri, yine bu
proje seçmiştir.** Yeşil bir koşu, aracın buradaki birinin ondan istemeye karar
verdiği şeyi yaptığı anlamına gelir.

## Dürüst özet

ArgazUI şunu yanıtlar: *ne çalıştırıldı, tam olarak hangi yapılandırma altında,
araç ne yaptı, hangi kriterler değerlendirildi, sonucu hangi kanıt kanıtlıyor ve
bu, bilinen bir referansla nasıl karşılaştırılıyor?*

Şunu yanıtlamaz: *sorulması gereken doğru şey bu muydu ve gerçek araç aynı
fikirde olur muydu?*

Bu ikisini ayrı tutmak, bütün aracın varlık sebebidir. İkinci sorunun
birincisiyle yanıtlanmasına izin veren bir doğrulama platformu, v1.0'ın birlikte
geldiği elle yazılmış destek tablosunun daha inandırıcı bir sürümü olurdu — ki
bu proje tam olarak onu ortadan kaldırmak için var.
