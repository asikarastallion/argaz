# Deneyler

**Deney**, bir dosyada beyan edilmiş kontrollü bir karşılaştırmadır: tek model,
bir ya da daha çok *kol* — belirtilen sayıda uçurulan bir prosedür —, bir ölçüm
kümesi, yalnızca bir koşu grubu hakkında söylenebilecek kabul kriterleri ve
yanıtın neyi kapsadığının sınırları.

## Alttaki katmanlar neden yetmedi

Bu projenin kurduğu her katman *tek bir şey* hakkındaki bir soruyu yanıtlar.

| katman | yanıtladığı soru |
|---|---|
| [prosedür](acceptance-criteria.tr.md) | ne uçurulacak ve neyin işe yaradığı sayılacak |
| [koşu](runs-and-evidence.tr.md) | bu sefer ne oldu |
| [kampanya](campaigns.tr.md) | aynı şey N kez aynı biçimde oluyor mu |
| [regresyon](regression.tr.md) | adı konmuş bir referanstan daha mı kötü |
| [arıza enjeksiyonu](fault-injection.tr.md) | bir şey bozulduğunda ne yapıyor |

Hiçbirinin söyleyemediği şey, bir mühendisin gerçekte elinde getirdiği sorudur:

> Tırmanış sırasında GPS'i kaybetmek, bu aracın irtifayı tutuşunu, hiçbir sorun
> yokken yapılan aynı tırmanışa kıyasla değiştiriyor mu?

Bunu yanıtlamak *kontrollü* bir koşu kümesi ister: aynı model, aynı
yapılandırma, bir nominal grup ve bir arızalı grup, belirtilmiş bir tekrar
sayısı, adı konmuş bir ölçüm kümesi ve önceden kararlaştırılmış bir kriter.
Bu parçaların hepsi zaten vardı. Olmayan şey, hangi bileşimin koşulduğunu yazan
bir yerdi — ki bileşimin kendisi de incelenebilir, sürümlenebilir ve
tekrarlanabilir olsun.

## Bileşim kurar; genişletmez

Deney; araca yeni bir yetenek, yeni bir adım tipi ya da bir uçuşu yargılamanın
yeni bir yolunu eklemez.

- bir kol **zaten var olan** bir prosedürü adlandırır; kendine ait bir uçuş
  tarif edemez ve deney dosyasında adım listesi yoktur;
- bir kol `campaign.CampaignRunner` tarafından, arayüzün sürdüğü aynı
  `ProcedureRunner` üzerinden koşulur — ikinci bir yürütme motoru yoktur;
- her yineleme, içinde her zamanki kanıt bulunan **sıradan bir koşu dizini**
  bırakır: `result.json`, dataflash logu, parmak izi, kanıt listesi, uçuş raporu;
- ifade dili, koşul ya da döngü yoktur.

## Neden "senaryo" değil de "deney"

v1.6 mimarisi bu nesneye *senaryo* diyor. Bu depo o kelimeyi v1.4'ten beri
başka bir şey için kullanıyor: `applies_to.role: scenario` nominal dışı bir
**prosedürdür**, her koşu dizininde çalıştırılan prosedürleri tutan bir
`scenario.yaml` vardır ve ortam parmak izinde bu prosedürlerin beyan ettiği
arızaları listeleyen bir `scenario` bloğu bulunur.

Kelimeyi yeniden kullanmak var olan üç artefaktı belirsizleştirirdi; üstelik en
çok önem taşıyan — bir incelemecinin gerçekte ne koştuğunu görmek için açtığı
dosya — bozulanların başında gelirdi. Bu yüzden buradaki kelime `experiment`.
Nominal dışı bir prosedür hâlâ bir senaryodur ve bir deney senaryo
*kullanabilir*; arızalı kol tam olarak budur.

## Bir deney dosyası neyi söyler

Tam başvuru [`argazui/experiments/SCHEMA.md`](#docs=experiment-schema)
dosyasındadır. Ana hatlarıyla:

```yaml
schema: 1
id: copter_gps_loss_vs_nominal
question:                         # zorunlu — aşağıya bak
  en: Does losing the position source change how well this aircraft tracks...
model: iris                       # tek bir kayıt defteri girdisi
values: {alt: 25}                 # her kola uygulanan prosedür girdileri
arms:
  - {id: nominal,  procedure: copter_takeoff,  runs: 3, role: reference}
  - {id: gps_loss, procedure: copter_gps_loss, runs: 3, role: treatment}
metrics: [tracking_error_roll_rms, peak_angular_rate]
compare: {policy: arms, reference_arm: nominal}
accept:
  - {id: nominal-reliable, arm: nominal, min_pass_rate: 1.0}
  - {id: roll-tracking, arm: gps_loss, metric: tracking_error_roll_rms,
     max_delta: 3.0, delta_vs: nominal}
limitations:
  assumptions: [...]
  model_limitations: [...]
  unverified_effects: [...]
  out_of_scope: [...]
```

**`question` zorunludur.** Sorusu yazılmamış bir deney, bir koşu yığınıdır ve
ürettiği belge, karşısında okunacak hiçbir şey olmayan bir sayı tablosudur.
Hiçbir aracın türetemeyeceği, doğrulayamayacağı ya da varsayılana
bağlayamayacağı tek alan budur; zorunlu olmasının nedeni tam olarak budur.

## Yapısal olarak: bir kol, bir kampanyadır

N sıradan koşu dizinine basılmış bir deney koşu kimliği ve yanına basılmış
kolun kendi kampanya kimliği.

```
runs/
├── 20260810T124500Z_iris/   result.json → "campaign":   {"id": …-copter_takeoff-nominal, "index": 1}
│                                        → "experiment": {"run": …, "arm": "nominal", "index": 1}
├── …
├── campaigns/
│   ├── 20260810T124500Z_iris.copter_takeoff-nominal/    campaign.json / .md
│   └── 20260810T124500Z_iris.copter_gps_loss-gps_loss/  campaign.json / .md
└── experiments/
    └── 20260810T124500Z_copter_gps_loss_vs_nominal/
        ├── experiment.json
        └── experiment.md
```

Bir değil, iki damga. Bir kol gerçekten *bir* tekrarlanabilirlik kampanyasıdır;
böylece kampanyaları okuyan her araç onu bulmaya devam eder ve her kolun
kampanya belgesi, o belgeleri zaten üreten kod tarafından üretilir.

Bir dizinde tutulmak yerine koşulara basılır — kampanyada olduğu gibi: bir deney
**koşuları okunarak** bulunur, böylece ağaçtan dışarı kopyalanmış bir koşu bile
neye ait olduğunu söyler ve bir belge asla var olmayan bir koşuyu adlandıramaz.

## Bir deney çalıştırmak

Arayüzden — **Deneyler** paneli: beyan edilmiş bir deney seç, DENEYİ ÇALIŞTIR'a
bas. Her kolu sırayla, her birini bir kampanya olarak, her yinelemeyi gerçek bir
başlatma ve gerçek bir kapatma ile uçurur.

Kabuktan, neyin beyan edildiğini ve neyin gerçekten uçurulduğunu görmek için:

```bash
python3 -m argazui experiment                              # iki liste birlikte
python3 -m argazui experiment copter_gps_loss_vs_nominal   # en yeni koşusu
python3 -m argazui experiment 20260810T124500Z_copter_gps_loss_vs_nominal
```

Çıkış kodları, çünkü bu CI içindir:

| kod | anlamı |
|---|---|
| `0` | deney toplandı ve beyan edilen hiçbir şey başarısız olmadı |
| `1` | beyan edilen bir kriter sağlanmadı |
| `2` | böyle bir deney yok ya da o adla hiçbir şey uçurulmamış |

**Eksik** bir deney `0` verir. Koşu sayısı eksik kalan kollar, daha çok uçurmak
için bir nedendir; bir yapıyı kırmak için değil — ve bir deneyi uçurulabilir
olmadan önce beyan ettiği için CI'ı kızaran bir proje, deney beyan etmemeyi
öğrenir. [Kapsam](coverage-model.tr.md) da aynı gerekçe üzerine kuruludur.

## Belge

On sabit, numaralı bölüm; [uçuş raporunun](runs-and-evidence.tr.md) v1.5'ten beri
taşıdığı sırayla ve aynı gerekçeyle — iki deneyi okuyan bir incelemeci aynı
bilgiyi iki farklı yerde aramak zorunda kalmamalıdır.

1. Soru ve kapsam
2. Yapılandırma
3. Yürütme — her kol, kampanyası, sayıları
4. Hüküm
5. Sağlanmayan kriterler ve **değerlendirilemeyenler**
6. Ölçülen büyüklükler, kol kol
7. Karşılaştırma — politikanın istediği farklar
8. Kanıt — her koşu ve her şeyi geride bırakıp bırakmadığı
9. Bu belge nasıl yeniden üretilir
10. Sınırlar ve yapılmayan iddialar

### Kimliğe göre değil, metrik anahtarına göre karşılaştırma

Bu projede başka her yerde bir metrik `key@procedure` ile tanımlanır ve bu
doğrudur: "hedef irtifaya ulaşma süresi" kimin hedefi olduğu söylenmeden hiçbir
şey ifade etmez ve iki farklı prosedür arasındaki bir regresyon karşılaştırması,
birbiriyle ilgisiz iki sayının çıkarılmasıdır.

Deney, bunu tersine çeviren durumdur. Kolları bilerek *farklı* prosedürler uçurur
— nominal bir tırmanış ve GPS'i alınmış aynı tırmanış — ve bütün soru, aynı
ölçülen büyüklüğün iki koşul altında ne yaptığıdır. Kimliğe göre eşleştirmek
hiçbir şeyi hizalamazdı. Bu yüzden bir deneyin içinde kimlik **anahtardır** ve
her sayının hangi prosedürlerden geldiği yanında listelenir.

### Analizin hesaplamayı reddettiği şeyler

**p değeri yok, güven aralığı yok, etki büyüklüğü yok, "anlamlı" yok.** Bir SITL
kampanyasının ürettiği örneklem büyüklüklerinde bunların her biri sorunsuz
çalışan ama hiçbir anlam taşımayan aritmetik olurdu ve her biri incelemeciye
farkın kanıtlanmış olduğu izlenimini verirdi.

Bunun yerine raporlanan şey bilinçli olarak sıradan:

| | |
|---|---|
| `n` | her iki tarafta, her sayının yanında |
| iki ortalama | ve farkları |
| Δ% | referans kolun ortalamasına göre |
| aralıklar örtüşüyor mu | iki kolun gözlenen aralıkları hiç değiyor mu |
| dayanak | `measured`, `indicative` ya da `none` |

Örtüşme **bir anlamlılık testi değildir.** Gerçekten görülmüş sayılar hakkında
bir ifadedir; bu örneklemin destekleyebileceği tek ifade türü de budur.

Bir fark yalnızca her iki kolun da en az üç ölçülmüş değeri olduğunda
`measured` olur — kampanyaların standart sapma yazdırmadan önce kullandığı eşiğin
aynısı. Altında `indicative`tir ve belge bunu satırda söyler.

### Hükümler

| hüküm | anlamı |
|---|---|
| `passed` | beyan edilen her kriter, beyan edilen koşular üzerinde sağlandı |
| `failed` | bir kriter değerlendirildi ve sağlanmadı |
| `incomplete` | bir kolun koşuları eksik ya da bir kriter hiç değerlendirilemedi |
| `not-judged` | deney kabul kriteri beyan etmiyor — hiçbir iddiada bulunulmadı |
| `not-run` | bu deney kimliğini taşıyan hiçbir şey yok |

`failed`, `incomplete`ten önce kararlaştırılır; çünkü değerlendirilmiş ve
sağlanmamış bir kriter bir sonuçtur ve beşi yerine üç koşudan gelmiş olması onu
hâlâ o sonuç yapar — belge yanına `n` yazar.

Değerlendirilemeyen bir kriter **asla geçmiş sayılmaz.** "Hiçbir koşu bunu
ölçmedi" ile "bu sağlandı" farklı olgulardır ve yalnızca biri bir yanıttır.

## Grup hakkındaki kabul kriterleri

Tek bir uçuş hakkındaki kriterler zaten prosedürde durur ve burada
tekrarlanmaz. Yalnızca üç biçim vardır, fazlası yoktur:

| biçim | anahtarlar | neyi yargılar |
|---|---|---|
| geçiş oranı | `min_pass_rate` | kolun **temiz** geçiş oranı — yeniden deneme `flaky`dir, asla geçiş değil |
| aralık | `min` / `max` + `metric` | kolun o metrikteki ortalaması |
| fark | `max_delta` + `delta_vs` + `metric` | iki kolun ortalamaları arasındaki mutlak uzaklık |

Bir kriter yalnızca deneyin `metrics:` listesindeki bir metriği yargılayabilir;
aksi hâlde hükmü, raporun göstermediği bir sayıya dayanırdı.

## Sınırlar sonucun bir parçasıdır

Dört adlandırılmış kategori — simülasyon varsayımları, model sınırları,
doğrulanmamış fiziksel etkiler, test kapsamı dışındaki koşullar — dosyada beyan
edilir ve bu aracın koşabildiği her deney için geçerli olan "her zaman geçerli"
ifadelerle birlikte 10. bölüm olarak yazılır.

Hangisinin neye ait olduğu için [Geçerleme sınırları](validation-limits.tr.md)
sayfasına, bu ayrımın bir deneyde neden akademik olmaktan çıktığı için
[Doğrulama ve geçerleme](verification-vs-validation.tr.md) sayfasına bak.

## Kapsam

Deneyler beşinci [kapsam](coverage-model.tr.md) boyutudur ve her kol ayrı
listelenir — çünkü kollarının yarısı uçurulmuş bir deney hiçbir şeyi
yanıtlamamıştır. Bir karşılaştırma iki tarafı da ister.

## Kod nerede

| | |
|---|---|
| `argazui/experiments.py` | tanım, doğrulaması ve her kolu bir kampanyaya devreden koşturucu |
| `argazui/analysis.py` | kol başına dağılımlar, aralarındaki farklar, hüküm, belge |
| `argazui/limitations.py` | dört kategori ve her zaman geçerli ifadeler |
| `argazui/campaign.py` | her kolu koşar — bu sürümde değişmedi |
| `argazui/runs.py` | `result.json` içindeki `experiment` damgası (şema 6) |

Deneyler ArgazUI v1.6'da eklendi.
