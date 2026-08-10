# Kanıt listesi

Her koşu `evidence.json` yazar: geriye **bırakması beklenen** şeyler ve her
artefakta gerçekte ne olduğu.

## Neden

Bir koşu dizini bir dosya yığınıdır. O yığının *eksiksiz* olup olmadığı, eskiden
okuyucunun içinde ne bulunması gerektiğini hatırlayarak çıkardığı bir şeydi — ve
arıza biçimi sessizdir. Hiç üretilmemiş bir rapor, boş bir grafik dizini,
analizin atladığı bir parametre dökümü: bunların her biri gayet düzgün görünen
bir dizin bırakır ve her biri, bir yerdeki bir iddianın kimsenin açamayacağı bir
kanıta dayandığı anlamına gelir.

## Üç beklenti düzeyi

| düzey | anlamı |
|---|---|
| `required` | koşu, o olmadan kanıt değildir. Yoksa → bir [`evidence` arızası](failure-classification.tr.md). |
| `conditional` | yalnızca belirtilen koşul geçerliyse gereklidir |
| `optional` | yokluğu sorun değildir — **ama yalnızca gerekçesi belirtilmişse** |

### Koşullu olan

Dataflash logu, *araç arm ettiyse* gereklidir; etmediyse değil. ArduPilot
`LOG_DISARMED=0` ile gelir, yani hiç arm etmemiş bir oturum log yazmaz ve
kaybolan bir şey yoktur. Yine de log istemek, sağlıklı bir koşuyu kanıtı eksik
diye raporlamak olurdu.

Liste iki düzeyi de kaydeder: `level_declared` (`conditional`) ve bu koşuya
uygulanmış hâliyle `level` (`required`, çünkü araç arm etti). İnceleyicinin
ikisine de ihtiyacı vardır — "araç arm ettiği için gerekli" ile "her zaman
gerekli" aynı satır hakkında farklı ifadelerdir.

### İsteğe bağlı olan — asıl mesele

Gerekçesi kaydedilmeden yok olan isteğe bağlı bir artefakt
`absent_unexplained` olarak listelenir.

> "matplotlib kurulu olmadığı için grafik yok" ile "grafik yok" farklı
> olgulardır ve yalnızca birincisi bir cevaptır.

Bu, projenin ölçülemeyen bir metriğe ve okunamayan bir
[parmak izi](reproducibility.tr.md) alanına uyguladığı kuralın aynısıdır.
Gerekçeli yokluk kanıttır; gerekçesiz yokluk boşluktur.

## Artefakt başına neler kaydedilir

| alan | |
|---|---|
| `path` | koşu dizinine göre |
| `type` | MIME tipi ya da `directory` |
| `level` / `level_declared` | bu koşuya uygulanmış hâli ve beyan edilmiş hâli |
| `exists` | gerçekten orada mı |
| `size_bytes` | |
| `hash` | `sha256:…` ya da `hash_absent_reason` ile birlikte `null` |
| `producer` | onu hangi modül yazdı |
| `producer_schema` | o modülün şema sürümü |
| `absent_reason` | yoksa, neden yok |
| `purpose` | ne işe yaradığı, tek cümlede |

**Üreten**, özet kadar önemlidir. Şema 3 ile yazılmış bir `result.json` ile şema
5 ile yazılmış biri de geçerlidir ve farklı alanlar taşırlar; iki koşuyu
karşılaştıran bir inceleyici hangisine baktığını dosyayı açmadan görebilmelidir.

## İki şey bilerek özetlenmez

**`result.json`**, uçuş raporu tamamlandığında yeniden yazılır — danışma sayısı,
metrikler ve derleme kaydı ancak dataflash logu okununca var olur. Bu anlardan
herhangi birinde alınan bir özet diğerlerinde yanlıştır ve *bazen* yanlış olan
bir özet, dürüst bir yokluktan kötüdür: kusursuz bir koşuyu bütünlük
denetiminden düşürürdü. Onun yerine varlığı, boyutu ve şeması kaydedilir.

**Uçuş raporuna gömülen kopya** hiç özet taşımaz. Rapor, listenin tarif ettiği
artefaktlardan biridir; dolayısıyla içine gömülen liste, raporun kendi son
yazımından önce alınmıştır. Özetleri orada tutmak, iki belgenin üçüncü bir
belgenin özeti konusunda — yalnızca yazılma sıraları yüzünden — anlaşmazlığa
düşmesi demek olurdu. Özetler tek bir yerdedir: `evidence.json`.

Liste bu yüzden **iki kez** alınır — bir kez rapor yazıldıktan sonra, bir kez de
7. bölüm doldurulduktan sonra. Rapora gömülen hiçbir şey özet taşımadığı için
her iki alım da aynı içeriği gömer ve ikinci geçiş yalnızca özetleri değiştirir;
onların yeri de zaten orasıdır.

256 MB üstündeki dosyalar mevcut ve özetsiz olarak, boyutu belirtilerek
kaydedilir. Kimsenin beklemediği bir özet, özet değildir.

## Nasıl okunur

```bash
python3 -c "import json;print(json.load(open('runs/<id>/evidence.json'))['complete'])"
python3 -m argazui trace runs/<id>      # listenin sorunlarını da içerir
```

Tarayıcıda koşu sayfası, raporun üstünde bir **Kanıt listesi** bloğu gösterir:
eksiksiz ya da neyin eksik olduğu.

`report.md` 7. bölüm aynı tabloyu üretir.

## Eksiksiz bir liste ne demektir, ne demek değildir

Eksiksiz, **gereken** her artefaktın dizinde olduğu anlamına gelir. Koşunun
geçtiği anlamına gelmez, artefaktların doğru olduğu anlamına gelmez ve araç
hakkında hiçbir şey söylemez. Koşunun ileri sürdüğü iddianın kanıtının okunmak
üzere gerçekten orada olduğu anlamına gelir.

Kanıt listesi ArgazUI v1.5 ile eklendi.
