# Arıza sınıflandırması

ArgazUI'nin kaydettiği her arıza **makine tarafından okunabilen tek bir
kategori** taşır ve bu kategori, okuyanın çıkarmasına bırakılmaz; koşunun içine
yazılır.

## Neden

v1.4'e kadar başarısız bir koşunun bir hükmü ve bir cümlesi vardı. `failed` ile
birlikte *"beklenen duruma 60 sn içinde ulaşılmadı"* doğrudur ve neredeyse
işe yaramaz: aracın mı yanlış davrandığını, SITL'in mi hiç başlamadığını,
dataflash logunun mu kaybolduğunu, yoksa ArgazUI'nin mi bozulduğunu söylemez.
Bunlar dört ayrı incelemedir ve hangisinin geçerli olduğunu bir cümleyi okuyarak
çıkarmak, tam olarak bir makinenin acele eden bir insana bırakmaması gereken
karardır.

## Yedi kategori

Küme **kapalıdır**. Yeni bir şey ters gittiğinde yeni bir kategori üreten bir
sınıflandırma, tanı olmaktan çıkıp hata mesajının ikinci bir kopyası olur.
Aşağıdaki her ad *farklı bir incelemeyi* adlandırır.

| kategori | ne demek | önce nereye bakılır |
|---|---|---|
| `environment` | Simülasyon, koşunun ihtiyaç duyduğu duruma getirilemedi: SITL ya da Gazebo başlamadı, bir varlık eksikti, beyan edilen bir override ya da arıza uygulanamadı. | `console.log`, dosyanın başındaki başlatma komutları, `argazui doctor` |
| `vehicle_readiness` | Araç hazır hale getirilemedi: arm öncesi kontroller hiç geçmedi ya da bir arm reddedildi. | `console.log` ve `mavlink_events.jsonl` içindeki otopilot mesajları |
| `procedure` | Akışın bir adımı istediğini yapamadı — bir mod reddedildi, bir komut geri çevrildi, bir bekleme zaman aşımına uğradı. Kabul kriterlerine hiç gelinmedi. | `result.json` içindeki başarısız adım ve `scenario.yaml` |
| `acceptance` | Akış sonuna kadar koştu ve beyan edilen bir kriter sağlanmadı. | `result.json` içindeki `expect` bloğu ve `report.md` içindeki grafikler |
| `evidence` | Uçtu ve kanıtı eksik: dataflash logu yok, yarım kalmış ya da iki koşu karşılaştırılamıyor. | `result.json` içindeki `artefacts.dataflash_check` |
| `regression` | Hiçbir şey düşmedi. Ölçülen bir büyüklük, adı verilmiş bir referansa göre eşiğini aştı. | `regression.md` ve adını verdiği referans |
| `infrastructure` | ArgazUI, bağlantı ya da CI işi bozuldu. | koşunun `text` alanındaki hata izi ve iş akışı kaydı |

> **Yalnızca `acceptance` bir araç hakkında hükümdür.**
>
> Diğer altısı simülasyonun, araçların ya da kanıtın bozulduğunu söyler. Bunları
> birbirine karıştırmak, bozuk bir test düzeneğinin bozuk bir araç diye
> raporlanmasına yol açar — ki bu, hak edilmemiş bir onay işaretiyle aynı
> doğruluk kaybının ters yönüdür.

## Kodlar

Kod, kategoriden ince, mesajdan kabadır: *aynı biçimde* düşen iki koşunun ortak
noktasıdır. Kategori "kim inceleyecek" sorusunu, kod "bu geçen seferkiyle aynı
şey mi" sorusunu yanıtlar.

| kod | kategori |
|---|---|
| `prearm-never-passed` | `vehicle_readiness` |
| `arm-refused` | `vehicle_readiness` |
| `step-failed`, `step-timeout` | `procedure` |
| `criterion-failed` | `acceptance` |
| `criterion-not-judged` | `acceptance` |
| `override-not-applied` | `environment` |
| `fault-not-applied`, `fault-not-cleared` | `environment` |
| `dataflash-missing`, `dataflash-truncated` | `evidence` |
| `runs-not-comparable` | `evidence` |
| `metric-degraded` | `regression` |
| `runner-error` | `infrastructure` |
| `iteration-launch-failed` | `environment` |

## İnceleme sırası

Arm edemeyen bir koşu kabul kriterlerine hiç ulaşmadı; dolayısıyla
değerlendirilmemiş kriterleri raporlamak bir belirtiyi adlandırıp nedeni
gizlemek olurdu. Bu yüzden sınıflandırıcı **ilk ters giden şeyi** raporlar, şu
sırayla:

1. bir yürütücü hatası — sonrasındaki her şey zaten bozulmuş bir koşu tarafından
   kaydedildi;
2. uygulanamayan, beyan edilmiş bir override — araç, prosedürün gerektirdiği
   yapılandırmada değil;
3. enjekte edilemeyen ya da geri alınamayan, beyan edilmiş bir arıza;
4. başarısız olan ilk adım;
5. sağlanmayan ilk kriter;
6. koşunun kanıtı.

6. adım, prosedürlerinin tamamı geçmiş bir koşunun neden yine de düşebileceğini
açıklar: kimsenin gerçekleştiğini kanıtlayamadığı bir uçuş, hiç olmamış bir uçuş
kadar değerlidir.

## `criterion-not-judged`, `criterion-failed` değildir

Telemetrisi hiç gelmemiş bir kriter *değerlendirilmedi* olarak raporlanır. Bu
hâlâ bir `acceptance` arızasıdır — prosedür iddia ettiği şeyi ortaya koyamadı —
ama kod, kriterin aslında hiç değerlendirilmediğini söyler. "Hiçbir şey
ölçülmedi" ile "bir şey yanlıştı", bu projenin ayrı tutmak için var olduğu iki
cevaptır ve ikisini herhangi bir yönde birleştirmek, olmayan bir sonuç uydurmak
olur.

## Nerede görünür

| | |
|---|---|
| `runs/<id>/result.json` | `failure` — geçen bir koşuda `null`, asla `"none"` |
| içindeki her prosedür | kendi `failure` alanı; böylece iki prosedürlü bir koşu hangisi olduğunu söyler |
| `runs/<id>/report.md` | **Bu koşu neden geçmedi** bölümü |
| `runs/<id>/regression.json` | karşılaştırmanın kendi sınıflandırması |
| `docs/status.md` | bir **Why** sütunu ve kategori başına toplam |
| Uçuş Koşuları paneli | hükmün yanında bir rozet; kod ve ayrıntı üzerine gelince görünür |
| `campaign.json` | kampanya boyunca sayılmış `failure_categories` |

Geçen bir koşuda `"failure": null` yazar. Bilerek `"category": "none"` diye bir
şey yok: aksi hâlde *failure* kelimesini arayan biri dizindeki her koşuda bir
tane bulurdu.

## Dil

**Kategori etiketi** kullanıcıya görünen bir metindir; arayüzde de API'de de
(`GET /api/failure-categories`) İngilizce ve Türkçe olarak bulunur.

**`detail` alanı ise bilerek İngilizcedir.** O alan, CI'ın okuduğu ve iki koşu
arasındaki bir karşılaştırmanın eşleştirebilmesi gereken makine tarafından
okunabilir kaydın parçasıdır; dolayısıyla uçuşun yapıldığı sırada arayüzün
hangi dilde olduğuna göre değişmemelidir. Zaten büyük bölümü otopilotun kendi
ifadesidir ve o her hâlükârda İngilizcedir.

## Kod nerede

`argazui/failures.py` tek uygulamadır. Kod tabanında başka hiçbir yer kategori
kararı vermez — `procrunner.py`, `runs.py`, `regression.py`, `status.py` ve
`campaign.py` hepsi buraya çağrı yapar — çünkü ikinci bir uygulama, bir adım
tipi eklenir eklenmez birinciyle çelişirdi.

Arıza sınıflandırması ArgazUI v1.4 ile eklendi.
