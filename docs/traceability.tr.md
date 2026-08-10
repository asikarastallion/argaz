# İzlenebilirlik

Bir niyet ile onun kanıtı arasındaki her bağın bir adı var.

```
test amacı    test_id        pytest düğümü ya da `manual`
  -> prosedür     procedure_id   YAML dosyasının kendi kimliği
  -> adım         step_id        <prosedür>#s3 ya da beyan edilmiş bir ad
  -> kriter       criterion_id   <prosedür>#alt-reached — her zaman beyan edilir
  -> metrik       metric_id      anahtar@prosedür
  -> koşu         run_id         koşu dizini
  -> artefakt     kanıt listesindeki yollar
  -> hüküm        koşunun durumu ve arıza kategorisi
```

## Neden

v1.4'e kadarki her sürüm *olguları* iyileştirdi: ölçülen kriterler, zamansal
biçimler, metrikler, parmak izleri, kampanyalar, bir arıza kategorisi. Hiçbiri
tek bir iddiayı geriye doğru izlemeyi mümkün kılmadı. Elinde
[`status.md`](status.md) olan ve *"bu hangi kriter, hangi koşu gösterdi ve hangi
dosya kanıtlıyor"* diye sorulan bir inceleyicinin üç belgeyi okuyup gözle
birleştirmesi gerekiyordu.

## Veritabanı yok

Burada hiçbir şey saklanmaz. Zincir, her sorulduğunda koşunun `result.json`
dosyasından **hesaplanır** — tıpkı bir [kampanya](campaigns.tr.md) belgesinin
koşularından yeniden hesaplanması gibi.

Tarif ettiği koşudan sapabilecek bir izlenebilirlik kaydı, hiç olmamasından
kötü olurdu: bu projenin tek tuttuğu şey için ikinci bir kaynak olurdu.

```bash
python3 -m argazui trace runs/<koşu-id>          # zincir ve içindeki boşluklar
python3 -m argazui trace runs/<koşu-id> --json
```

| çıkış | anlamı |
|---|---|
| `0` | her bağ çözülüyor |
| `1` | zincirde bir sorun var — kopuk bir başvuru, yinelenen bir kimlik, zincirin adını verdiği ama listede bulunmayan bir artefakt |
| `2` | koşu okunamadı |

`0` değil `1`, çünkü bu komut CI için. Kimsenin denetlemediği bir izlenebilirlik
şeması sessizce çürür ve raporladığı sorunların her biri yine de kusursuz
görünen bir tablo üretir.

## Beyan edilen ve türetilen tanımlayıcılar

**Kriter kendi kimliğini beyan eder**:

```yaml
schema: 4

expect:
  - id: alt-reached
    condition: {alt_above: "{alt*0.9}"}
    within: 20s
```

**Adım ise kimliğini konumundan türetir** — `copter_takeoff#s3` — kendisi
beyan etmediği sürece.

Aradaki çizgi keyfi değil:

- Adım tanımlayıcısı yalnızca onu üreten koşunun *içinde* okunur. Rapor adımları
  listeler; arıza sınıflandırması düşen adımı adlandırır. Bunun için konum
  gayet iyi bir addır.
- Kriter tanımlayıcısı kendi koşusunun *dışında* alıntılanır:
  [kapsam raporunda](coverage-model.tr.md), [status.md](status.md) içindeki
  "neler test edilmedi" bölümünde, aylar arayla iki koşunun
  karşılaştırılmasında. Bunların, birisi üstlerine bir kriter eklediğinde sağ
  kalacak bir ada ihtiyacı var.

Gönderilen her prosedürdeki her kriter kendi kimliğini beyan eder ve bir test
bunu denetler. Beyan etmeyen bir prosedür yine çalışır — `<prosedür>#c2` alır —
ve zincir **o tanımlayıcıyı türetilmiş olarak işaretler**; çünkü okuyucunun
kararlılığını göremediği bir tanımlayıcı, görebildiğinden kötüdür.

### Bir kimliğin biçimi

Küçük harfler, rakamlar, `_` ve `-`; 1–48 karakter; asla `#`. Bir kimlik
tablolarda, URL'lerde ve kabuk komutlarında alıntılanır; bunlardan herhangi
birinde kaçış gerektiren bir kimlik, bir yerde mutlaka yanlış yazılacak bir
kimliktir — bu yüzden temizlenmez, yükleme anında reddedilir.

Bir dosyadaki iki kriter aynı kimliği paylaşamaz. Kapsam raporu ile "neler test
edilmedi" listesi iki farklı iddiayı sessizce tek satırda birleştirirdi.

## `test_id`: koşu *ne için*di

Bir test tarafından uçurulan koşu o testin pytest düğüm kimliğini taşır. Bir
insanın uçurduğu koşu ise `manual` taşır; bu gerçek bir cevaptır ve asıl önemli
olanıdır: **bu depodaki hiçbir test onun gösterdiğini iddia etmez.**

Uçuş raporunun [iddia-olmayanlar bölümü](runs-and-evidence.tr.md) böyle bir koşu
için bunu açıkça yazar; okuyucunun bir test adının yokluğundan çıkarmasına
bırakmaz.

## Bütünlük denetimi neyi yakalar

| sorun | anlamı |
|---|---|
| `missing-id` | kayıtlı bir prosedürün ya da kriterin tanımlayıcısı yok |
| `duplicate-id` | bir koşudaki iki adım ya da iki kriter aynı tanımlayıcıyı paylaşıyor |
| `dangling-link` | bir kriterin kimliği başka bir prosedürü adlandırıyor ya da bir metrik, koşunun hiç çalıştırmadığı bir prosedüre bağlı |
| `missing-evidence` | zincir, [listenin](evidence-manifest.tr.md) mevcut saymadığı bir artefakta başvuruyor |
| `missing-verdict` | koşu kaydında durum yok; içindeki hiçbir şey bir sonuca bağlanamaz |

## Nerede görünür

| | |
|---|---|
| `runs/<id>/result.json` | `test_id` ve her adım/kriterde `step_id` / `criterion_id` |
| `runs/<id>/report.md` | 1. bölüm amacı adlandırır; 3. bölüm her adımı kimliğiyle listeler; 5. bölüm düşen her kriteri kimliğiyle adlandırır |
| Uçuş Koşuları paneli | koşu sayfasında bir **İzlenebilirlik** bloğu ve çözülmeyen bağlar |
| `GET /api/runs/<id>/trace` | zincir, sorunları ve hangi kimliklerin türetildiği |
| [`coverage.md`](coverage.md) | kapsanmayan kriterler, kimlikleriyle |

## Ne değildir

Bu bir gereksinim yönetim sistemi değildir ve v1.5 bilerek öyle bir şey
kurmadı. Gereksinim belgesi, çift yönlü matris, onay akışı ya da bunları içe
aktaran bir araç yok. Olan şu: bu projenin yaptığı her iddia, tek bir komutla
onu destekleyen dosyaya kadar izlenebilir.

İzlenebilirlik tanımlayıcıları ArgazUI v1.5 ile eklendi.
