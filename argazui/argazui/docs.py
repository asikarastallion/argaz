"""The engineering documentation portal: an index over the repository's own docs.

WHY THIS IS AN INDEX AND NOT A DOCUMENTATION SYSTEM
---------------------------------------------------
The obvious way to add a Docs section to the interface is to write the
documentation into the interface. That produces a second source of truth within
a week: the page says one thing, `README.md` says another, and the one a
developer edits is whichever they happen to open.

So nothing here holds prose. Every page is either a file in this repository or
a named section extracted from one, and the portal reports which file each page
came from. Editing the documentation means editing the repository, exactly as
before; the portal only makes it navigable — a tree, a search over headings and
a deep link, instead of twenty browser tabs.

The one exception is the landing page, which is generated from this registry
and states no technical fact of its own.

LANGUAGES
---------
A page may name a different source per language. Where a Turkish source exists
— the documents v1.3 added, and `TROUBLESHOOTING.md`, which was written in
Turkish — the Turkish reader gets Turkish. Where it does not, the reader gets
the canonical English file and a notice, in Turkish, saying so. Forking every
repository document into a second language would recreate precisely the
duplicate-source problem this module is built to avoid, and a stale translation
of a technical page is worse than an honest English one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import paths

SCHEMA = 1

# Where a page's `source` may live. Two roots, named rather than guessed: the
# repository the documentation belongs to, and the application tree, which is
# a copy of itself in the e2e sandbox.
ROOT_REPO, ROOT_APP = "repo", "app"

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass
class Group:
    id: str
    title: dict


@dataclass
class Page:
    id: str
    group: str
    title: dict
    summary: dict
    # {"en": "README.md", "tr": "docs/metrics.tr.md"} — a language with no
    # entry falls back to English, and the page says that it did.
    source: dict = field(default_factory=dict)
    # A heading to extract, per language. Omitted means the whole file.
    section: dict = field(default_factory=dict)
    root: str = ROOT_REPO
    # Per-language exception to `root`. Needed exactly once, and honestly:
    # Troubleshooting's English text is a section of the application's
    # USAGE.md while its Turkish text is the repository's TROUBLESHOOTING.md,
    # which was written in Turkish in the first place.
    source_root: dict = field(default_factory=dict)
    generated: str = ""          # name of the generator, for the landing page


GROUPS = [
    Group("overview", {"en": "Overview", "tr": "Genel bakış"}),
    Group("configuration", {"en": "Configuration", "tr": "Yapılandırma"}),
    Group("procedures", {"en": "Procedures", "tr": "Prosedürler"}),
    Group("verification", {"en": "Verification", "tr": "Doğrulama"}),
    Group("operations", {"en": "Operations", "tr": "İşletim"}),
    Group("reference", {"en": "Reference", "tr": "Başvuru"}),
]

PAGES = [
    Page("index", "overview",
         {"en": "Documentation", "tr": "Dokümantasyon"},
         {"en": "What is in this portal and where each page comes from.",
          "tr": "Bu portalda ne var ve her sayfa nereden geliyor."},
         generated="landing"),
    Page("architecture", "overview",
         {"en": "Architecture", "tr": "Mimari"},
         {"en": "The pipeline from models.json to a verified run.",
          "tr": "models.json'dan doğrulanmış bir koşuya uzanan hat."},
         source={"en": "README.md"}, section={"en": "Architecture"}),
    Page("quick-start", "overview",
         {"en": "Quick Start", "tr": "Hızlı başlangıç"},
         {"en": "Install, check the prerequisites, fly something.",
          "tr": "Kur, ön koşulları doğrula, bir şey uçur."},
         source={"en": "README.md"}, section={"en": "Quick start"}),

    Page("configuration", "configuration",
         {"en": "Configuration", "tr": "Yapılandırma"},
         {"en": "argaz.toml, environment variables and the precedence between them.",
          "tr": "argaz.toml, ortam değişkenleri ve aralarındaki öncelik."},
         source={"en": "README.md"}, section={"en": "Configuration files"}),
    Page("reproducibility", "configuration",
         {"en": "Configuration & Reproducibility", "tr": "Yapılandırma ve tekrarlanabilirlik"},
         {"en": "The environment fingerprint every run captures, field by field.",
          "tr": "Her koşunun kaydettiği ortam parmak izi, alan alan."},
         source={"en": "docs/reproducibility.md", "tr": "docs/reproducibility.tr.md"}),
    Page("model-registry", "configuration",
         {"en": "Model Registry", "tr": "Model kayıt defteri"},
         {"en": "How models.json is built and how to add an aircraft.",
          "tr": "models.json nasıl üretilir, bir hava aracı nasıl eklenir."},
         source={"en": "USAGE.md"}, section={"en": "7. Adding a model / the registry"},
         root=ROOT_APP),

    Page("procedures", "procedures",
         {"en": "Procedures", "tr": "Prosedürler"},
         {"en": "What a procedure is and why takeoff is not one command.",
          "tr": "Prosedür nedir ve kalkış neden tek bir komut değildir."},
         source={"en": "USAGE.md"},
         section={"en": "5b. Takeoff and landing procedures"}, root=ROOT_APP),
    Page("procedure-schema", "procedures",
         {"en": "Procedure Schema", "tr": "Prosedür şeması"},
         {"en": "The complete YAML reference, schema 1 to 4.",
          "tr": "Tam YAML başvurusu, şema 1'den 4'e."},
         source={"en": "procedures/SCHEMA.md"}, root=ROOT_APP),
    Page("scenario-schema", "procedures",
         {"en": "Scenario Schema", "tr": "Senaryo şeması"},
         {"en": "The failures: block — declaring a fault, its window and its "
                "criteria.",
          "tr": "failures: bloğu — bir arızanın, penceresinin ve "
                "kriterlerinin beyanı."},
         source={"en": "procedures/SCHEMA.md"},
         section={"en": "Scenarios and fault injection (schema 3)"},
         root=ROOT_APP),
    Page("experiment-schema", "procedures",
         {"en": "Experiment Schema", "tr": "Deney şeması"},
         {"en": "The complete YAML reference for a controlled comparison.",
          "tr": "Kontrollü bir karşılaştırma için tam YAML başvurusu."},
         source={"en": "experiments/SCHEMA.md"}, root=ROOT_APP),

    Page("verification-model", "verification",
         {"en": "Verification Model", "tr": "Doğrulama modeli"},
         {"en": "What a green result claims, and everything it does not.",
          "tr": "Yeşil bir sonuç neyi iddia eder, neyi asla etmez."},
         source={"en": "docs/verification-model.md",
                 "tr": "docs/verification-model.tr.md"}),
    Page("acceptance-criteria", "verification",
         {"en": "Acceptance Criteria", "tr": "Kabul kriterleri"},
         {"en": "Conditions, and the temporal shapes within / for / never.",
          "tr": "Koşullar ve zamansal biçimler: within / for / never."},
         source={"en": "docs/acceptance-criteria.md",
                 "tr": "docs/acceptance-criteria.tr.md"}),
    Page("metrics", "verification",
         {"en": "Metrics", "tr": "Metrikler"},
         {"en": "The measured quantities, their units and their source signals.",
          "tr": "Ölçülen büyüklükler, birimleri ve kaynak sinyalleri."},
         source={"en": "docs/metrics.md", "tr": "docs/metrics.tr.md"}),
    Page("runs-and-evidence", "verification",
         {"en": "Runs & Evidence", "tr": "Koşular ve kanıt"},
         {"en": "What a run directory contains and why each file is in it.",
          "tr": "Bir koşu dizininde ne var ve her dosya neden orada."},
         source={"en": "docs/runs-and-evidence.md",
                 "tr": "docs/runs-and-evidence.tr.md"}),
    Page("regression", "verification",
         {"en": "Regression", "tr": "Regresyon"},
         {"en": "Baseline versus current, thresholds and the CI contract.",
          "tr": "Referans ve güncel karşılaştırması, eşikler ve CI sözleşmesi."},
         source={"en": "docs/regression.md", "tr": "docs/regression.tr.md"}),
    Page("campaigns", "verification",
         {"en": "Repeatability Campaigns", "tr": "Tekrarlanabilirlik kampanyaları"},
         {"en": "The same flight N times, and what a spread is worth.",
          "tr": "Aynı uçuş N kez ve bir dağılımın ne değeri var."},
         source={"en": "docs/campaigns.md", "tr": "docs/campaigns.tr.md"}),
    Page("fault-injection", "verification",
         {"en": "Fault Injection", "tr": "Arıza enjeksiyonu"},
         {"en": "The two faults, their mechanisms and the five rules they obey.",
          "tr": "İki arıza, mekanizmaları ve uydukları beş kural."},
         source={"en": "docs/fault-injection.md",
                 "tr": "docs/fault-injection.tr.md"}),
    Page("traceability", "verification",
         {"en": "Traceability", "tr": "İzlenebilirlik"},
         {"en": "From a test's intent to the file that proves its verdict.",
          "tr": "Bir testin amacından hükmünü kanıtlayan dosyaya."},
         source={"en": "docs/traceability.md", "tr": "docs/traceability.tr.md"}),
    Page("evidence-manifest", "verification",
         {"en": "Evidence Manifest", "tr": "Kanıt listesi"},
         {"en": "What a run was expected to leave behind, and what it did.",
          "tr": "Bir koşunun neyi bırakması bekleniyordu ve ne bıraktı."},
         source={"en": "docs/evidence-manifest.md",
                 "tr": "docs/evidence-manifest.tr.md"}),
    Page("experiments", "verification",
         {"en": "Experiments", "tr": "Deneyler"},
         {"en": "A controlled comparison: arms, deltas, and what a delta is "
                "worth.",
          "tr": "Kontrollü karşılaştırma: kollar, farklar ve bir farkın "
                "değeri."},
         source={"en": "docs/experiments.md", "tr": "docs/experiments.tr.md"}),
    Page("validation-limits", "verification",
         {"en": "Validation Limits", "tr": "Geçerleme sınırları"},
         {"en": "Four categories in which a result states what it does not "
                "establish.",
          "tr": "Bir sonucun neyi kanıtlamadığını belirttiği dört kategori."},
         source={"en": "docs/validation-limits.md",
                 "tr": "docs/validation-limits.tr.md"}),
    Page("coverage-model", "verification",
         {"en": "Coverage Model", "tr": "Kapsam modeli"},
         {"en": "What counts as coverage, and what is refused as coverage.",
          "tr": "Neyin kapsam sayıldığı ve neyin sayılmadığı."},
         source={"en": "docs/coverage-model.md",
                 "tr": "docs/coverage-model.tr.md"}),
    Page("verification-vs-validation", "verification",
         {"en": "Verification vs Validation", "tr": "Doğrulama ve geçerleme"},
         {"en": "Two words that get confused, and only one of which this does.",
          "tr": "Karıştırılan iki kavram ve bu araç yalnızca birini yapar."},
         source={"en": "docs/verification-vs-validation.md",
                 "tr": "docs/verification-vs-validation.tr.md"}),
    Page("failure-classification", "verification",
         {"en": "Failure Classification", "tr": "Arıza sınıflandırması"},
         {"en": "Seven categories, and why only one is about the aircraft.",
          "tr": "Yedi kategori ve neden yalnızca biri araçla ilgili."},
         source={"en": "docs/failure-classification.md",
                 "tr": "docs/failure-classification.tr.md"}),
    Page("dataflash", "verification",
         {"en": "DataFlash Analysis", "tr": "DataFlash analizi"},
         {"en": "The post-flight report built from the autopilot's own log.",
          "tr": "Otopilotun kendi logundan üretilen uçuş sonrası rapor."},
         source={"en": "USAGE.md"},
         section={"en": "5c. Flight runs and the post-flight report"}, root=ROOT_APP),

    Page("ci", "operations",
         {"en": "CI/CD", "tr": "CI/CD"},
         {"en": "Which workflow runs which tier, and what each may claim.",
          "tr": "Hangi iş akışı hangi katmanı koşar ve neyi iddia edebilir."},
         source={"en": "docs/ci.md", "tr": "docs/ci.tr.md"}),
    Page("failure-investigation", "operations",
         {"en": "Failure Investigation", "tr": "Arıza inceleme"},
         {"en": "A failed run, from its category to the file that explains it.",
          "tr": "Başarısız bir koşu: kategorisinden onu açıklayan dosyaya."},
         source={"en": "docs/failure-investigation.md",
                 "tr": "docs/failure-investigation.tr.md"}),
    Page("diagnostics", "operations",
         {"en": "Diagnostics (doctor)", "tr": "Tanılama (doctor)"},
         {"en": "What argazui doctor checks and what a failure means.",
          "tr": "argazui doctor neyi kontrol eder, hata ne demektir."},
         source={"en": "docs/diagnostics.md", "tr": "docs/diagnostics.tr.md"}),
    Page("lifecycle", "operations",
         {"en": "Process/Session Lifecycle", "tr": "Süreç/oturum yaşam döngüsü"},
         {"en": "START to STOP: what is launched, and how it is shut down.",
          "tr": "BAŞLAT'tan DURDUR'a: ne başlatılır, nasıl kapatılır."},
         source={"en": "docs/lifecycle.md", "tr": "docs/lifecycle.tr.md"}),
    Page("mavlink-ports", "operations",
         {"en": "MAVLink & Ports", "tr": "MAVLink ve portlar"},
         {"en": "14550, 14551, 14552 — who listens on what, and why.",
          "tr": "14550, 14551, 14552 — kim neyi dinler ve neden."},
         source={"en": "USAGE.md"}, section={"en": "4. MAVLink ports"},
         root=ROOT_APP),
    Page("gazebo-sitl", "operations",
         {"en": "Gazebo/SITL Integration", "tr": "Gazebo/SITL entegrasyonu"},
         {"en": "The launch methods, including the one that needs no Gazebo.",
          "tr": "Başlatma yöntemleri, Gazebo gerektirmeyen yöntem dahil."},
         source={"en": "USAGE.md"}, section={"en": "3. Launch methods"},
         root=ROOT_APP),

    Page("troubleshooting", "reference",
         {"en": "Troubleshooting", "tr": "Sorun giderme"},
         {"en": "Known failures and what actually fixes them.",
          "tr": "Bilinen arızalar ve onları gerçekten çözen adımlar."},
         source={"en": "USAGE.md", "tr": "TROUBLESHOOTING.md"},
         section={"en": "10. Troubleshooting"}, root=ROOT_APP,
         source_root={"tr": ROOT_REPO}),
    Page("testing", "reference",
         {"en": "Development/Testing", "tr": "Geliştirme/test"},
         {"en": "How to run each tier, and what a skip is worth.",
          "tr": "Her katman nasıl koşulur ve bir atlama ne ifade eder."},
         source={"en": "docs/testing.md", "tr": "docs/testing.tr.md"}),
    Page("changelog", "reference",
         {"en": "Changelog", "tr": "Değişiklik günlüğü"},
         {"en": "Every release, what it changed and what it verified.",
          "tr": "Her sürüm, neyi değiştirdi ve neyi doğruladı."},
         source={"en": "CHANGELOG.md"}),
]

BY_ID = {page.id: page for page in PAGES}


# ------------------------------------------------------------------ resolving
def _root_for(page: Page, lang: str) -> Path:
    # ROOT_APP follows the running installation, so the e2e sandbox reads its
    # own copy; ROOT_REPO is the configured project root, which is where
    # README.md, docs/ and CHANGELOG.md live.
    root = page.source_root.get(lang, page.root)
    return paths.ARGAZUI_DIR if root == ROOT_APP else paths.ARGAZ


def source_path(page: Page, lang: str) -> tuple[Optional[Path], str]:
    """The file backing a page in this language, and the language it is in."""
    name = page.source.get(lang)
    used = lang
    if not name:
        name, used = page.source.get("en", ""), "en"
    if not name:
        return None, used
    return _root_for(page, used) / name, used


# ------------------------------------------------------------------ extraction
def headings(text: str) -> list[dict]:
    """Every ATX heading, ignoring anything inside a fenced code block.

    The fence check is not fussiness: `SCHEMA.md` and `README.md` both contain
    shell blocks whose comment lines start with `#`, and without it the
    navigation tree would fill up with fragments of commands.
    """
    out: list[dict] = []
    fence = ""
    for line in text.splitlines():
        opening = _FENCE.match(line)
        if opening:
            marker = opening.group(1)
            fence = "" if fence == marker else (fence or marker)
            continue
        if fence:
            continue
        found = _HEADING.match(line)
        if found:
            out.append({"level": len(found.group(1)), "text": found.group(2).strip()})
    return out


def extract_section(text: str, heading: str) -> str:
    """One heading and everything under it, up to the next heading as high.

    Returns an empty string when the heading is not there, so a renamed
    section shows up as a missing page rather than as a silently empty one.
    """
    lines = text.splitlines()
    wanted = heading.strip().lower()
    start = level = None
    fence = ""
    for index, line in enumerate(lines):
        opening = _FENCE.match(line)
        if opening:
            marker = opening.group(1)
            fence = "" if fence == marker else (fence or marker)
            continue
        if fence:
            continue
        found = _HEADING.match(line)
        if not found:
            continue
        depth, title = len(found.group(1)), found.group(2).strip().lower()
        if start is None:
            if title == wanted:
                start, level = index, depth
            continue
        if depth <= level:
            return "\n".join(lines[start:index]).strip() + "\n"
    if start is None:
        return ""
    return "\n".join(lines[start:]).strip() + "\n"


def _landing(lang: str) -> str:
    """The one page this module writes, and it states no technical fact.

    It is a table of contents with the source of every page named, so that a
    reader who wants to change something knows which file to open.
    """
    header = {
        "en": ["# Documentation", "",
               "Every page in this portal is a file in the ArgazUI repository, "
               "or one named section of one. Nothing here is written by the "
               "interface: to change a page, change the file it names.", "",
               "| Page | What it covers | Source |", "|---|---|---|"],
        "tr": ["# Dokumantasyon", "",
               "Bu portaldaki her sayfa, ArgazUI deposundaki bir dosyadir ya da "
               "boyle bir dosyanin adi verilmis bir bolumudur. Hicbiri arayuz "
               "tarafindan yazilmaz: bir sayfayi degistirmek icin adi gecen "
               "dosyayi degistir.", "",
               "| Sayfa | Neyi kapsar | Kaynak |", "|---|---|---|"],
    }[lang if lang in ("en", "tr") else "en"]

    lines = list(header)
    for page in PAGES:
        if page.generated:
            continue
        name = page.source.get(lang) or page.source.get("en", "")
        used = lang if page.source.get(lang) else "en"
        in_app = page.source_root.get(used, page.root) == ROOT_APP
        where = "argazui/" + name if in_app else name
        section = page.section.get(lang) or page.section.get("en")
        if section:
            where += f" § {section}"
        # `#docs=<id>` rather than `#<id>`: the interface routes on that form,
        # so a link here opens the page in the portal instead of scrolling to
        # an anchor that does not exist.
        lines.append(f"| [{page.title.get(lang, page.title['en'])}](#docs={page.id}) "
                     f"| {page.summary.get(lang, page.summary['en'])} "
                     f"| `{where}` |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- public
def read(page_id: str, lang: str = "en") -> dict:
    """One page: its markdown, where it came from, and in which language."""
    page = BY_ID.get(page_id)
    if page is None:
        return {"ok": False, "id": page_id, "error": "unknown page"}

    if page.generated == "landing":
        text = _landing(lang)
        return {"ok": True, "id": page.id, "group": page.group,
                "title": page.title.get(lang, page.title["en"]),
                "markdown": text, "headings": headings(text),
                "source": "", "source_language": lang, "translated": True,
                "generated": True}

    path, used = source_path(page, lang)
    if path is None or not path.is_file():
        return {"ok": False, "id": page.id, "source": page.source.get(used, ""),
                "title": page.title.get(lang, page.title["en"]),
                "error": f"the source file for this page is missing: "
                         f"{page.source.get(used, '(none declared)')}"}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "id": page.id, "source": page.source.get(used, ""),
                "title": page.title.get(lang, page.title["en"]),
                "error": f"{path} could not be read: {exc}"}

    # Looked up by the language actually used, with no fallback: a page whose
    # Turkish source is a different document (Troubleshooting) must not be
    # asked for the English document's heading.
    section = page.section.get(used, "")
    if section:
        text = extract_section(text, section)
        if not text:
            return {"ok": False, "id": page.id, "source": page.source.get(used, ""),
                    "title": page.title.get(lang, page.title["en"]),
                    "error": f"the section '{section}' is no longer in "
                             f"{page.source.get(used)}"}
    # HTML comments carry generator instructions and editing notes; they are
    # not content, and the renderer escapes rather than executes markup.
    text = _HTML_COMMENT.sub("", text)

    relative = page.source.get(used, "")
    # The prefix follows the root that was ACTUALLY used, not the page's
    # default one: Troubleshooting reads its English text from the application
    # tree and its Turkish text from the repository, and a source line naming
    # the wrong directory sends a reader to a file that is not there.
    in_app = page.source_root.get(used, page.root) == ROOT_APP
    return {
        "ok": True, "id": page.id, "group": page.group,
        "title": page.title.get(lang, page.title["en"]),
        "markdown": text,
        "headings": headings(text),
        "source": ("argazui/" + relative if in_app else relative),
        "section": section or "",
        "source_language": used,
        # False means the reader asked for a language this page has no source
        # in, and is looking at the canonical English file. The interface says
        # so above the text rather than letting it pass unremarked.
        "translated": used == lang,
        "generated": False,
    }


def index(lang: str = "en") -> dict:
    """The navigation tree, with each page's headings for the search box."""
    groups = []
    for group in GROUPS:
        entries = []
        for page in PAGES:
            if page.group != group.id:
                continue
            document = read(page.id, lang)
            entries.append({
                "id": page.id,
                "title": page.title.get(lang, page.title["en"]),
                "summary": page.summary.get(lang, page.summary["en"]),
                "source": document.get("source", ""),
                "available": bool(document.get("ok")),
                "translated": bool(document.get("translated")),
                "error": document.get("error", ""),
                "headings": [h for h in document.get("headings", [])
                             if 1 < h["level"] <= 3],
            })
        if entries:
            groups.append({"id": group.id,
                           "title": group.title.get(lang, group.title["en"]),
                           "pages": entries})
    return {"schema": SCHEMA, "lang": lang, "groups": groups}
