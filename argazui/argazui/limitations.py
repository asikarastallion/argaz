"""What a result does not establish — declared, in four named categories.

WHY A SEPARATE MODULE FOR THIS
------------------------------
v1.5 gave every flight report a "limitations and non-claims" section, and it
works: a reader who finishes a green report is told, in the report, where its
claims stop. But those limits are the ones that are true of *any* run this tool
produces. They are written by the tool, about the tool.

An experiment is where that stops being enough. An experiment states a
question, controls a comparison and produces a number — and the moment a
document says "GPS loss cost 3.4 s of climb time", it is being read as a fact
about an aircraft rather than about a simulation of one. The gap between those
two readings cannot be closed by better measurement. It is closed, if at all,
by somebody writing down what the simulation assumed, what its model does not
contain, which physical effects were never in it, and which conditions the test
deliberately did not cover.

So an experiment declares its own limits, in the file, beside the criteria, and
they are part of the document rather than a footnote to it.

THE FOUR CATEGORIES ARE NOT INTERCHANGEABLE
-------------------------------------------
    assumptions           what had to be true for the run to mean anything
    model_limitations     what the simulated aircraft is not
    unverified_effects    physics that was absent, or present but unvalidated
    out_of_scope          conditions the test deliberately did not enter

They are separate because a reader does different things with each. An
assumption can be checked. A model limitation bounds the claim. An unverified
effect is a reason to be careful about extrapolation. Something out of scope is
a reason to run something else. Collapsing them into one "notes" field — which
is what every project does eventually — turns four actionable statements into a
paragraph nobody reads.

VERIFICATION, NOT VALIDATION
----------------------------
This module is the mechanism behind the distinction `docs/verification-vs-
validation.md` describes. Verification is what the criteria do: the
implementation met limits somebody declared. Validation is the question of
whether those limits, that model and that scenario are representative of
anything — and nothing in this repository answers it. What this module does is
make the unanswered part *visible* and *specific*, instead of leaving it to a
reader's generosity.
"""
from __future__ import annotations

from typing import Any, Optional

SCHEMA = 1

ASSUMPTIONS = "assumptions"
MODEL_LIMITATIONS = "model_limitations"
UNVERIFIED_EFFECTS = "unverified_effects"
OUT_OF_SCOPE = "out_of_scope"

CATEGORIES = (ASSUMPTIONS, MODEL_LIMITATIONS, UNVERIFIED_EFFECTS, OUT_OF_SCOPE)

LABELS: dict[str, dict[str, str]] = {
    ASSUMPTIONS: {"en": "Simulation assumptions", "tr": "Simulasyon varsayimlari"},
    MODEL_LIMITATIONS: {"en": "Model limitations", "tr": "Model sinirlari"},
    UNVERIFIED_EFFECTS: {"en": "Unverified physical effects",
                         "tr": "Dogrulanmamis fiziksel etkiler"},
    OUT_OF_SCOPE: {"en": "Conditions outside the test scope",
                   "tr": "Test kapsami disindaki kosullar"},
}

WHAT: dict[str, dict[str, str]] = {
    ASSUMPTIONS: {
        "en": "What had to be true for these numbers to mean anything. An "
              "assumption is the one kind of limit a reader can go and check.",
        "tr": "Bu sayilarin bir anlam tasimasi icin dogru olmasi gereken "
              "seyler. Varsayim, okuyucunun gidip dogrulayabilecegi tek "
              "sinir turudur."},
    MODEL_LIMITATIONS: {
        "en": "What the simulated aircraft is not. This bounds the claim: a "
              "result can never be wider than the model that produced it.",
        "tr": "Simule edilen aracin ne OLMADIGI. Iddiayi sinirlar: bir sonuc, "
              "onu ureten modelden daha genis olamaz."},
    UNVERIFIED_EFFECTS: {
        "en": "Physics that was absent from the simulation, or present in it "
              "and never compared against anything real. These are the "
              "reasons not to extrapolate.",
        "tr": "Simulasyonda hic bulunmayan ya da bulunup gercek hicbir seyle "
              "karsilastirilmamis fizik. Sonucu genellememek icin "
              "gerekcelerdir."},
    OUT_OF_SCOPE: {
        "en": "Conditions this experiment deliberately did not enter. Stated "
              "so that 'it was not tested' cannot be read as 'it was fine'.",
        "tr": "Bu deneyin bilerek girmedigi kosullar. 'Test edilmedi' "
              "ifadesinin 'sorun yoktu' diye okunmamasi icin belirtilir."},
}

# The limits that are true of every experiment this tool can run, whatever the
# file says. They are printed alongside the declared ones and marked as
# standing, so a definition that declares nothing still produces an honest
# document — and so that a definition cannot quietly drop one of them.
STANDING: dict[str, list[dict[str, str]]] = {
    ASSUMPTIONS: [
        {"en": "The aircraft, its sensors and its environment are ArduPilot's "
               "SITL simulation. Nothing here was measured on hardware.",
         "tr": "Arac, sensorleri ve ortami ArduPilot SITL simulasyonudur. "
               "Burada hicbir sey donanim uzerinde olculmedi."},
        {"en": "Every arm is assumed to have flown the same configuration; the "
               "environment fingerprint of each run is what makes that "
               "checkable rather than assumed, and the document reports it "
               "when the runs disagree.",
         "tr": "Her kolun ayni yapilandirmayla ucurulmus oldugu varsayilir; "
               "bunu varsayim olmaktan cikaran sey her kosunun ortam parmak "
               "izidir ve kosular anlasmazsa belge bunu bildirir."},
        {"en": "Simulated time is the vehicle's clock. Where it stopped "
               "advancing, durations were measured on the wall clock and "
               "converted, and the run record says so.",
         "tr": "Simule zaman aracin saatidir. Bu saatin ilerlemedigi yerlerde "
               "sureler duvar saatiyle olculup cevrildi ve kosu kaydi bunu "
               "belirtir."},
    ],
    MODEL_LIMITATIONS: [
        {"en": "A SITL frame is a generic airframe of its class. It is not a "
               "model of any particular aircraft, and a result obtained on one "
               "says nothing about a specific airframe.",
         "tr": "Bir SITL govdesi, sinifinin genel bir hava aracidir. Belirli "
               "bir hava aracinin modeli degildir ve uzerinde alinan bir sonuc "
               "belirli bir govde hakkinda hicbir sey soylemez."},
        {"en": "A Gazebo model reproduces the geometry, mass properties and "
               "aerodynamic coefficients its author declared. No part of it "
               "has been compared against a measurement of a real aircraft by "
               "anything in this repository.",
         "tr": "Bir Gazebo modeli, yazarinin beyan ettigi geometriyi, kutle "
               "ozelliklerini ve aerodinamik katsayilari yeniden uretir. Bu "
               "depodaki hicbir sey, modelin herhangi bir parcasini gercek bir "
               "hava aracinin olcumuyle karsilastirmamistir."},
    ],
    UNVERIFIED_EFFECTS: [
        {"en": "Battery sag, ESC and motor dynamics, propeller efficiency, "
               "structural flexibility and airframe wear are either absent "
               "from the simulation or present in an idealised form that has "
               "not been validated here.",
         "tr": "Batarya gerilim dususu, ESC ve motor dinamikleri, pervane "
               "verimi, yapisal esneklik ve govde yipranmasi ya simulasyonda "
               "hic yoktur ya da burada gecerlenmemis idealize bir bicimde "
               "vardir."},
        {"en": "Sensor failure modes are simulated by changing a parameter. "
               "Real receivers, IMUs and radio links fail in ways no parameter "
               "reproduces.",
         "tr": "Sensor ariza bicimleri bir parametre degistirilerek simule "
               "edilir. Gercek alicilar, IMU'lar ve telsiz baglantilari hicbir "
               "parametrenin yeniden uretmedigi bicimlerde bozulur."},
    ],
    OUT_OF_SCOPE: [
        {"en": "Hardware in the loop, real flight controllers and real "
               "airframes. ArgazUI has no hardware path and does not claim "
               "one.",
         "tr": "Donanim dongude (HITL), gercek ucus kontrolculeri ve gercek "
               "govdeler. ArgazUI'nin donanim yolu yoktur ve boyle bir iddiasi "
               "da yoktur."},
        {"en": "More than one vehicle, and any interaction between vehicles.",
         "tr": "Birden fazla arac ve araclar arasindaki herhangi bir "
               "etkilesim."},
        {"en": "Anything a person did outside the recorded procedures. Only "
               "what is in the run directories was judged.",
         "tr": "Bir kisinin kaydedilen prosedurlerin disinda yaptigi hicbir "
               "sey. Yalnizca kosu dizinlerindeki seyler degerlendirildi."},
    ],
}

DECLARED, STANDING_SOURCE = "declared", "standing"


class LimitationError(ValueError):
    """A limitations block is malformed. Carries the file for the message."""


def label_for(category: str, lang: str = "en") -> str:
    entry = LABELS.get(category, {})
    return entry.get(lang) or entry.get("en") or category


def what_for(category: str, lang: str = "en") -> str:
    entry = WHAT.get(category, {})
    return entry.get(lang) or entry.get("en") or ""


def empty() -> dict[str, list]:
    return {category: [] for category in CATEGORIES}


def parse(raw: Any, where: str) -> dict[str, list[dict[str, str]]]:
    """Validates a declared `limitations:` block into {category: [{en, tr}]}.

    An unknown category is refused rather than kept. A statement filed under a
    name this module does not print would be a limit somebody wrote down and
    nobody ever read, which is worse than not writing it: the author believes
    it was stated.
    """
    out = empty()
    if raw is None:
        return out
    if not isinstance(raw, dict):
        raise LimitationError(
            f"{where}: expected a map of "
            f"{{{', '.join(CATEGORIES)}}} to lists of statements")
    for category, items in raw.items():
        if category not in CATEGORIES:
            raise LimitationError(
                f"{where}: unknown category '{category}'. Known: "
                f"{', '.join(CATEGORIES)}.")
        if isinstance(items, (str, dict)):
            items = [items]
        if not isinstance(items, list) or not items:
            raise LimitationError(
                f"{where}.{category}: expected a non-empty list of statements. "
                f"A category present and empty says nothing; leave it out.")
        for index, item in enumerate(items):
            spot = f"{where}.{category}[{index}]"
            if isinstance(item, str):
                text = {"en": item, "tr": item}
            elif isinstance(item, dict):
                text = {k: str(v) for k, v in item.items() if k in ("en", "tr")}
                if not text:
                    raise LimitationError(f"{spot}: needs an 'en' and/or 'tr' key")
                text.setdefault("tr", text.get("en", ""))
                text.setdefault("en", text.get("tr", ""))
            else:
                raise LimitationError(
                    f"{spot}: expected a string or an {{en, tr}} map")
            if not text["en"].strip():
                raise LimitationError(f"{spot}: an empty statement is not one")
            out[category].append(text)
    return out


def declared_count(declared: Optional[dict]) -> int:
    return sum(len(items) for items in (declared or {}).values())


def statements(declared: Optional[dict] = None,
               lang: str = "en") -> list[dict]:
    """Every limitation that applies, declared and standing, in category order.

    The standing ones come last within each category. A reader should meet the
    experiment's own statements first — those are the ones somebody thought
    about for this question — and then the ones that are always true.
    """
    declared = declared or {}
    out: list[dict] = []
    for category in CATEGORIES:
        rows = [(DECLARED, text) for text in (declared.get(category) or [])]
        rows += [(STANDING_SOURCE, text) for text in STANDING.get(category, [])]
        for source, text in rows:
            out.append({
                "category": category,
                "label": label_for(category, lang),
                "source": source,
                "text": text.get(lang) or text.get("en") or "",
            })
    return out


def as_list(declared: Optional[dict] = None, lang: str = "en") -> list[dict]:
    """Only what the experiment itself declared — for the definition listing."""
    declared = declared or {}
    return [{"category": category, "label": label_for(category, lang),
             "text": text.get(lang) or text.get("en") or ""}
            for category in CATEGORIES
            for text in (declared.get(category) or [])]


def catalogue(lang: str = "en") -> list[dict]:
    """The four categories, what belongs in each, and the standing statements."""
    return [{"category": category,
             "label": label_for(category, lang),
             "what": what_for(category, lang),
             "standing": [text.get(lang) or text.get("en", "")
                          for text in STANDING.get(category, [])]}
            for category in CATEGORIES]


def render(declared: Optional[dict] = None, lang: str = "en") -> list[str]:
    """The limitations as a document section. Returns markdown lines."""
    lines: list[str] = []
    rows = statements(declared, lang)
    count = declared_count(declared)

    lines.append(
        "This section is the one a verification document is least likely to "
        "contain. Everything above is **verification** — an implementation met "
        "criteria somebody declared. None of it is **validation**: nothing "
        "here shows the criteria, the model or the question are "
        "representative of anything that happens outside a simulator. See "
        "[verification-vs-validation.md](../../docs/verification-vs-validation.md).")
    lines.append("")
    if not count:
        lines.append(
            "**This experiment declared no limitations of its own**, so only "
            "the standing ones below apply. That is allowed and it is worth "
            "noticing: the limits that matter most to a particular question "
            "are usually the ones only its author knows.")
        lines.append("")

    for category in CATEGORIES:
        entries = [row for row in rows if row["category"] == category]
        if not entries:
            continue
        lines.append(f"### {label_for(category, lang)}")
        lines.append("")
        lines.append(what_for(category, lang))
        lines.append("")
        for row in entries:
            mark = "" if row["source"] == DECLARED else " *(standing)*"
            lines.append(f"- {row['text']}{mark}")
        lines.append("")
    return lines
