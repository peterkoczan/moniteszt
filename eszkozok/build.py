#!/usr/bin/env python3
"""Tananyag generálása a kártyákból.

Bemenet:  forras/kartyak.txt  (kézzel gondozott kártyák)
          forras/kerdesek.json (a megoldólapokból kinyert kérdések, lásd kinyer.py)
Kimenet:  TANANYAG.md – olvasható jegyzet (GitHubon is)
          index.html  – önálló, interaktív oldal (önellenőrzés, kikérdezés, keresés)

Ellenőrzi, hogy minden vizsgakérdés pontosan egyszer szerepel-e, és a pontszámok
meg a csillagok egyeznek-e a megoldólappal. Hiba esetén nem ír ki semmit.

Használat: python3 eszkozok/build.py [--artifact CÉL.html]
"""

import argparse
import datetime
import difflib
import html
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

GYOKER = Path(__file__).resolve().parent.parent
ROMAI = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
HONAP = ["január", "február", "március", "április", "május", "június", "július",
         "augusztus", "szeptember", "október", "november", "december"]
CIM = "Egészségügyi alapmodul tananyag"
LEIRAS = ("A 2026. júniusi egészségügyi alapmodul vizsgák 8 megoldólapjának mind a 190 kérdése "
          "témák szerint, a hivatalos megoldásokkal, önellenőrzéssel és kikérdezéssel.")
OLDAL = "https://peterkoczan.github.io/moniteszt/"
ALSO = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


# ---------------------------------------------------------------- beolvasás

class Kerdes:
    def __init__(self, src, pont, csillag, szoveg, sor):
        m = re.fullmatch(r"([IVX]+)/(\d+)([a-z]?)", src)
        if not m:
            raise ValueError(f"{sor}. sor: hibás forrás: {src}")
        self.src, self.dolgozat, self.szam, self.resz = src, m.group(1), int(m.group(2)), m.group(3)
        self.pont, self.csillag, self.szoveg = int(pont), csillag == "*", szoveg
        self.opciok = []

    @property
    def jel(self):
        return f"{self.dolgozat}/{self.szam}"


class Kartya:
    def __init__(self, cim):
        self.cim, self.kerdesek, self.sorok, self.id = cim, [], [], ""

    @property
    def dolgozatok(self):
        return sorted({q.dolgozat for q in self.kerdesek}, key=ROMAI.index)

    @property
    def kerdes_jelek(self):
        return sorted({(q.dolgozat, q.szam) for q in self.kerdesek}, key=lambda t: (ROMAI.index(t[0]), t[1]))


def beolvas(path):
    temak, tema, fejezet, kartya = [], None, None, None
    for n, nyers in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        sor = nyers.rstrip()
        if sor.startswith("//"):
            continue
        if sor.startswith("@topic "):
            tema = {"cim": sor[7:].strip(), "fejezetek": []}
            temak.append(tema)
            fejezet = kartya = None
        elif sor.startswith("@section "):
            fejezet = {"cim": sor[9:].strip(), "kartyak": []}
            tema["fejezetek"].append(fejezet)
            kartya = None
        elif sor.startswith("@card "):
            kartya = Kartya(sor[6:].strip())
            fejezet["kartyak"].append(kartya)
        elif sor.startswith("?> "):
            kartya.kerdesek[-1].opciok.append(sor[3:].strip())
        elif sor.startswith("? "):
            reszek = [r.strip() for r in sor[2:].split("|", 3)]
            if len(reszek) != 4:
                raise ValueError(f"{n}. sor: a kérdéssor formája: ? forrás | pont | * | kérdés")
            kartya.kerdesek.append(Kerdes(*reszek, sor=n))
        elif kartya is not None:
            kartya.sorok.append(sor)
        elif sor.strip():
            raise ValueError(f"{n}. sor: kártyán kívüli szöveg: {sor}")
    # azonosítók
    hasznalt = set()
    for t in temak:
        for f in t["fejezetek"]:
            for k in f["kartyak"]:
                alap = ascii_slug(k.cim)
                azon, i = alap, 2
                while azon in hasznalt:
                    azon, i = f"{alap}-{i}", i + 1
                hasznalt.add(azon)
                k.id = azon
    return temak


def ascii_slug(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def kartyak(temak):
    for ti, t in enumerate(temak, 1):
        for f in t["fejezetek"]:
            for k in f["kartyak"]:
                yield ti, t, f, k


# ---------------------------------------------------------------- ellenőrzés

def normal(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return re.sub(r"[^a-z0-9 ]+", "", "".join(c for c in s if not unicodedata.combining(c)))


def ellenoriz(temak, adat):
    hibak, figyelm = [], []
    jq = {(d["jel"], q["szam"]): q for d in adat["dolgozatok"] for q in d["kerdesek"]}
    elofordul = defaultdict(list)
    cimek = set()
    for _, _, _, k in kartyak(temak):
        if k.cim in cimek:
            hibak.append(f"ismétlődő kártyacím: {k.cim}")
        cimek.add(k.cim)
        if not k.kerdesek:
            hibak.append(f"kérdés nélküli kártya: {k.cim}")
        if not any(s.strip() for s in k.sorok):
            hibak.append(f"megoldás nélküli kártya: {k.cim}")
        for q in k.kerdesek:
            kulcs = (q.dolgozat, q.szam)
            if kulcs not in jq:
                hibak.append(f"ismeretlen kérdés: {q.src} ({k.cim})")
                continue
            elofordul[kulcs].append((q, k))
            if not q.resz:
                arany = difflib.SequenceMatcher(None, normal(q.szoveg), normal(jq[kulcs]["kerdes"])).ratio()
                if arany < 0.75:
                    figyelm.append(f"{q.src}: a kérdés szövege eltér a megoldólaptól ({arany:.2f}): {q.szoveg[:50]}…")
    for kulcs, j in jq.items():
        jel = f"{kulcs[0]}/{kulcs[1]}"
        elof = elofordul.get(kulcs)
        if not elof:
            hibak.append(f"hiányzó kérdés: {jel} – {j['kerdes'][:60]}")
            continue
        reszek = [q.resz for q, _ in elof]
        if len(elof) > 1 and ("" in reszek or len(set(reszek)) != len(reszek)):
            hibak.append(f"többször szereplő kérdés: {jel}")
        osszeg = sum(q.pont for q, _ in elof)
        if osszeg != j["pont"]:
            hibak.append(f"pontszám eltér: {jel} (kártyán {osszeg}, megoldólapon {j['pont']})")
        for q, _ in elof:
            if q.csillag != j["csillag"]:
                hibak.append(f"csillag eltér: {q.src}")
    return hibak, figyelm


# ---------------------------------------------------------------- megoldás-szöveg

def blokkok(sorok):
    sorok = [s.rstrip() for s in sorok]
    while sorok and not sorok[0].strip():
        sorok.pop(0)
    while sorok and not sorok[-1].strip():
        sorok.pop()
    ki, i = [], 0
    while i < len(sorok):
        s = sorok[i]
        if not s.strip():
            i += 1
        elif s.startswith("|"):
            sorai = []
            while i < len(sorok) and sorok[i].startswith("|"):
                sorai.append(sorok[i])
                i += 1
            ki.append(("tabla", sorai))
        elif s.startswith("- "):
            elemek = []
            while i < len(sorok) and sorok[i].startswith("- "):
                elemek.append(sorok[i][2:].strip())
                i += 1
            ki.append(("ul", elemek))
        elif re.match(r"\d+\.\s", s):
            elemek = []
            while i < len(sorok) and re.match(r"\d+\.\s", sorok[i]):
                elemek.append(re.sub(r"^\d+\.\s+", "", sorok[i]).strip())
                i += 1
            ki.append(("ol", elemek))
        elif s.startswith("💡"):
            ki.append(("tipp", s[1:].strip()))
            i += 1
        elif re.fullmatch(r"\*\*[^*]+\*\*(\s+\*\([^*]+\)\*)?", s.strip()):
            ki.append(("alcim", s.strip()))
            i += 1
        elif re.fullmatch(r"\*[^*].*[^*]\*", s.strip()):
            ki.append(("kulcs", s.strip()[1:-1]))
            i += 1
        else:
            ki.append(("p", s.strip()))
            i += 1
    return ki


def allitas(x):
    return x.startswith(("✅", "❌"))


def valasztos(x):
    return not allitas(x) and "✅" in x


def jel_nelkul(x):
    return re.sub(r"^[✅❌]️?\s*", "", x)


def fajta(bl):
    """'mark': csupa helyes/hibás állítás vagy választós sor – önellenőrzéskor jelölés nélkül látszik."""
    van = False
    for t, p in bl:
        if t in ("alcim", "tipp"):
            continue
        if t == "ul" and all(allitas(x) or valasztos(x) for x in p):
            van = True
            continue
        return "std"
    return "mark" if van else "std"


def levag_cimke(x):
    m = re.search(r"\s*(\*\([^*]+\)\*)$", x)
    return (x[:m.start()], m.group(1)) if m else (x, "")


def inl(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"[₀-₉]+", lambda m: "<sub>" + m.group(0).translate(ALSO) + "</sub>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"__(.+?)__", r'<u class="kw">\1</u>', s)
    s = re.sub(r"\*\(([^*]+?)\)\*", r'<span class="tag">(\1)</span>', s)
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return s


def allitas_html(x):
    jo = x.startswith("✅")
    torzs, cimke = levag_cimke(jel_nelkul(x))
    javitas = ""
    if " → " in torzs:
        torzs, javitas = torzs.split(" → ", 1)
    h = f'<li class="st {"ok" if jo else "no"}"><span class="t">{inl(torzs)}</span>'
    if javitas:
        h += f' <span class="fix">→ {inl(javitas)}</span>'
    if cimke:
        h += " " + inl(cimke)
    return h + "</li>"


def valasztos_bont(x):
    torzs, cimke = levag_cimke(x)
    m = re.match(r"^(.*?[:?])\s+(.*)$", torzs)
    if not m:
        raise ValueError(f"választós sor kérdés nélkül: {x}")
    return m.group(1), [o.strip() for o in m.group(2).split(" / ")], cimke


def valasztos_html(x):
    tors, opciok, cimke = valasztos_bont(x)
    reszek = []
    for o in opciok:
        if o.startswith("✅"):
            reszek.append(f'<span class="o ok">{inl(jel_nelkul(o))}</span>')
        else:
            reszek.append(f'<span class="o no">{inl(o)}</span>')
    h = f'<li class="ch"><span class="stem">{inl(tors)}</span> ' + '<span class="sep">/</span>'.join(reszek)
    if cimke:
        h += " " + inl(cimke)
    return h + "</li>"


def tabla_cellak(sorai):
    cellak = [[c.strip() for c in s.strip().strip("|").split("|")] for s in sorai]
    fej = cellak[0]
    torzs = [r for r in cellak[1:] if not all(re.fullmatch(r":?-{3,}:?", c) for c in r)]
    return fej, torzs


def tabla_html(sorai):
    fej, torzs = tabla_cellak(sorai)
    h = ['<div class="tbl"><table><thead><tr>']
    h += [f'<th scope="col">{inl(c)}</th>' for c in fej]
    h.append("</tr></thead><tbody>")
    for r in torzs:
        h.append("<tr>" + "".join(f"<td>{inl(c)}</td>" for c in r) + "</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def megoldas_html(bl):
    ki = []
    for t, p in bl:
        if t == "ul":
            li = [allitas_html(x) if allitas(x) else valasztos_html(x) if valasztos(x) else f"<li>{inl(x)}</li>" for x in p]
            ki.append("<ul>" + "".join(li) + "</ul>")
        elif t == "ol":
            ki.append("<ol>" + "".join(f"<li>{inl(x)}</li>" for x in p) + "</ol>")
        elif t == "tabla":
            ki.append(tabla_html(p))
        elif t == "tipp":
            ki.append(f'<p class="tip">{inl(p)}</p>')
        elif t == "alcim":
            ki.append(f'<p class="sub">{inl(p)}</p>')
        elif t == "kulcs":
            ki.append(f'<p class="key">{inl(p)}</p>')
        else:
            ki.append(f"<p>{inl(p)}</p>")
    return "\n".join(ki)


def md_inl(s):
    return re.sub(r"__(.+?)__", r"**<ins>\1</ins>**", s)


def megoldas_md(bl):
    ki = []
    for t, p in bl:
        if t == "ul":
            sorok = []
            for x in p:
                if valasztos(x):
                    tors, opciok, cimke = valasztos_bont(x)
                    x = tors + " " + " / ".join(
                        f"✅ **{jel_nelkul(o)}**" if o.startswith("✅") else f"~~{o}~~" for o in opciok
                    ) + (" " + cimke if cimke else "")
                sorok.append("- " + md_inl(x))
            ki.append("\n".join(sorok))
        elif t == "ol":
            ki.append("\n".join(f"{i}. {md_inl(x)}" for i, x in enumerate(p, 1)))
        elif t == "tabla":
            fej, torzs = tabla_cellak(p)
            sorok = ["| " + " | ".join(fej) + " |", "|" + "---|" * len(fej)]
            sorok += ["| " + " | ".join(md_inl(c) for c in r) + " |" for r in torzs]
            ki.append("\n".join(sorok))
        elif t == "tipp":
            ki.append("💡 " + md_inl(p))
        elif t == "kulcs":
            ki.append("*" + md_inl(p) + "*")
        else:
            ki.append(md_inl(p))
    return "\n\n".join(ki)


# ---------------------------------------------------------------- statisztika

def datum_hu(iso):
    ev, ho, nap = (int(x) for x in iso.split("-"))
    return f"{ev}. {HONAP[ho - 1]} {nap}."


def statisztika(temak, adat):
    osszes = sum(len(d["kerdesek"]) for d in adat["dolgozatok"])
    lista = list(kartyak(temak))
    osszevont = [k for _, _, _, k in lista if len(k.kerdes_jelek) > 1]
    temastat = []
    for ti, t in enumerate(temak, 1):
        ks = [k for _, _, _, k in kartyak([t])]
        pont = sum(q.pont for k in ks for q in k.kerdesek)
        temastat.append({"n": ti, "cim": t["cim"], "kartya": len(ks), "pont": pont})
    ossz_pont = sum(d["osszpont"] for d in adat["dolgozatok"])
    return {
        "kerdes": osszes, "kartya": len(lista), "tema": len(temak),
        "osszevont": len(osszevont), "osszevont_kerdes": sum(len(k.kerdes_jelek) for k in osszevont),
        "temak": temastat, "ossz_pont": ossz_pont, "dolgozat": len(adat["dolgozatok"]),
    }


def szazalek(resz, egesz):
    return f"{round(100 * resz / egesz)}%"


# ---------------------------------------------------------------- Markdown

class Slugger:
    """A GitHub-féle fejléchorgonyok (github-slugger) utánzása."""

    def __init__(self):
        self.lat = {}

    def __call__(self, szoveg):
        s = re.sub(r"[^\w\- ]", "", szoveg.strip().lower()).replace(" ", "-")
        n = self.lat.get(s, 0)
        self.lat[s] = n + 1
        return f"{s}-{n}" if n else s


def build_md(temak, adat, st, oldal):
    slug = Slugger()
    datumok = {d["jel"]: d["datum"] for d in adat["dolgozatok"]}
    ki = []

    def fejlec(szint, szoveg):
        s = slug(szoveg)
        ki.append(f"{'#' * szint} {szoveg}")
        ki.append("")
        return s

    fejlec(1, "Egészségügyi alapmodul – tananyag")
    ki += [
        "Tananyag a természetgyógyászati képzés **egészségügyi alapmoduljának** 2026. június 8–11-i "
        "szakmai írásbeli vizsgáiból: mind a nyolc feladatsor (I–VIII.) minden kérdése a hivatalos "
        "megoldásokkal, témák szerint rendezve. Az azonos vagy átfedő kérdések egy kártyára kerültek.",
        "",
        f"**{st['kerdes']}** vizsgakérdés → **{st['kartya']}** kártya · ebből **{st['osszevont']}** összevont "
        f"kártya ({st['osszevont_kerdes']} kérdésből) · **{st['tema']}** téma",
        "",
        f"**Interaktív változat** (telefonon is; önellenőrzés, kikérdezés, keresés, „tudom” jelölés): {oldal}",
        "",
    ]
    fejlec(3, "Jelek")
    ki += [
        "- **II/5** – II. feladatsor, 5. kérdés (I–II: jún. 8., III–IV: jún. 9., V–VI: jún. 10., VII–VIII: jún. 11.)",
        "- **✱** – tartalmilag azonos, más megfogalmazású válasz is elfogadható",
        "- **<ins>kulcsszó</ins>** – fogalommeghatározásnál csak akkor jár teljes pont, ha minden aláhúzott kulcsszó szerepel",
        "- ✅ / ❌ – aláhúzandó / nem aláhúzandó állítás; a „→” utáni javítás kiegészítés, nem a megoldólapról való",
        "- *(1–B)* – megoldókulcs a párosító és csoportosító feladatokhoz",
        "- 🔁 – több dolgozatban is szereplő, összevont kérdés",
        "",
    ]
    fejlec(3, "Így pontoznak")
    ki += [
        "- 100 pont a maximum, **71 ponttól** megfelelt.",
        "- A „/” jellel elválasztott válaszok egyenértékűek.",
        "- A felsoroltatós kérdéseknél a megoldólap több helyes választ ad, mint amennyi kell: elég a kért darabszám.",
        "- Ha választós feladatban minden lehetőséget megjelölsz, 0 pont jár; a fölösleges jelölések levonnak.",
        "- A tartalmat értékelik, a helyesírást nem.",
        "",
    ]
    fejlec(3, "Tartalom")
    # a témák horgonyait előre kiszámoljuk ugyanazzal a sorrenddel
    ki.append("| # | Téma | Kártya | Pont (800-ból) |")
    ki.append("|---|---|---:|---:|")
    tabla_helye = len(ki)
    ki.append("")

    horgony = {}
    tema_horgony = []
    for ti, t in enumerate(temak, 1):
        ts = st["temak"][ti - 1]
        tema_horgony.append(fejlec(2, f"{ti}. {t['cim']}"))
        ki += [f"*{ts['kartya']} kártya · {ts['pont']} pont a {st['dolgozat']} dolgozatban "
               f"({szazalek(ts['pont'], st['ossz_pont'])})*", ""]
        for f in t["fejezetek"]:
            fejlec(3, f["cim"])
            for k in f["kartyak"]:
                horgony[k.id] = fejlec(4, k.cim)
                dg = k.dolgozatok
                if len(dg) > 1:
                    ki += [f"*🔁 {len(dg)} dolgozatban: {', '.join(d + '.' for d in dg)}*", ""]
                qs = []
                for q in k.kerdesek:
                    if qs:
                        qs.append(">")
                    csillag = " ✱" if q.csillag else ""
                    qs.append(f"> **{q.jel}** · {q.pont} pont{csillag} · {q.szoveg}")
                    for o in q.opciok:
                        qs += [">", f"> *{o}*"]
                ki += qs + [""]
                ki += [megoldas_md(blokkok(k.sorok)), ""]
    sorok = [f"| {ts['n']} | [{ts['cim']}](#{tema_horgony[ts['n'] - 1]}) | {ts['kartya']} | "
             f"{ts['pont']} ({szazalek(ts['pont'], st['ossz_pont'])}) |" for ts in st["temak"]]
    ki[tabla_helye:tabla_helye] = sorok

    fejlec(2, "Melyik kérdés hol van?")
    ki += ["A feladatsorok kérdései sorszám szerint; a szám a megfelelő kártyára visz.", ""]
    hol = forras_index(temak)
    for d in adat["dolgozatok"]:
        linkek = [f"[{q['szam']}](#{horgony[hol[(d['jel'], q['szam'])]]})" for q in d["kerdesek"]]
        ki += [f"**{d['jel']}. feladatsor** ({datum_hu(datumok[d['jel']])}): " + " · ".join(linkek), ""]
    ki += [
        "---",
        "",
        "Nem hivatalos összeállítás. A megoldások az Országos Kórházi Főigazgatóság (OKFŐ) "
        f"[megoldólapjairól]({adat['forras_oldal']}) származnak; a zárójeles magyar nevek, a „→” "
        "javítások és a 💡 tippek kiegészítések. Újragenerálás: `python3 eszkozok/build.py`.",
        "",
    ]
    return "\n".join(ki)


def forras_index(temak):
    hol = {}
    for _, _, _, k in kartyak(temak):
        for q in k.kerdesek:
            hol.setdefault((q.dolgozat, q.szam), k.id)
    return hol


# ---------------------------------------------------------------- HTML

def esc(s):
    return html.escape(s, quote=True)


def kartya_html(k, datumok):
    bl = blokkok(k.sorok)
    dg = k.dolgozatok
    h = [f'<article class="card" id="k-{k.id}" data-id="{k.id}" data-rep="{len(dg)}" data-kind="{fajta(bl)}">',
         '<div class="card-h">', f"<h4>{inl(k.cim)}</h4>"]
    if len(dg) > 1:
        h.append(f'<span class="rep" title="{esc(", ".join(d + ". feladatsor" for d in dg))}">{len(dg)} dolgozatban</span>')
    h += ['<button class="known" type="button" aria-pressed="false">Tudom</button>', "</div>"]
    for q in k.kerdesek:
        cim = f"{q.dolgozat}. feladatsor, {q.szam}. kérdés – {datum_hu(datumok[q.dolgozat])}"
        oldal = f'<span class="src" title="{esc(cim)}">{q.jel}</span><span class="pts">{q.pont} pont</span>'
        if q.csillag:
            oldal += '<span class="star" title="Tartalmilag azonos más válasz is elfogadható">✱</span>'
        opciok = "".join(f'<p class="opt">{inl(o)}</p>' for o in q.opciok)
        h.append(f'<div class="q"><div class="q-main"><p class="q-text">{inl(q.szoveg)}</p>{opciok}</div>'
                 f'<div class="q-side">{oldal}</div></div>')
    h += [f'<div class="ans">{megoldas_html(bl)}</div>',
          '<button class="reveal" type="button">Megoldás</button>', "</article>"]
    return "\n".join(h)


def build_html(temak, adat, st, sablon, oldal):
    datumok = {d["jel"]: d["datum"] for d in adat["dolgozatok"]}
    toc, tabla, torzs = [], [], []
    for ti, t in enumerate(temak, 1):
        ts = st["temak"][ti - 1]
        toc.append(f'      <li><a href="#t{ti}" data-topic="t{ti}"><span class="n">{ti}</span>'
                   f'<span>{esc(t["cim"])}</span><span class="c">0/{ts["kartya"]}</span></a></li>')
        tabla.append(f'              <tr><td class="n">{ti}</td><td><a href="#t{ti}">{esc(t["cim"])}</a></td>'
                     f'<td class="r">{ts["kartya"]}</td><td class="r">{ts["pont"]} · '
                     f'{szazalek(ts["pont"], st["ossz_pont"])}</td></tr>')
        torzs.append(f'<section class="topic" id="t{ti}" aria-labelledby="t{ti}-h">')
        torzs.append(f'<div class="topic-h"><span class="n">{ti}</span><h2 id="t{ti}-h">{esc(t["cim"])}</h2></div>')
        torzs.append(f'<p class="topic-meta"><span>{ts["kartya"]} kártya · {ts["pont"]} pont a '
                     f'{st["dolgozat"]} dolgozatban</span><a class="no-print" href="#temak">↑ Témák</a></p>')
        for f in t["fejezetek"]:
            torzs.append(f'<div class="sect-wrap"><h3 class="sect">{esc(f["cim"])}</h3>')
            torzs += [kartya_html(k, datumok) for k in f["kartyak"]]
            torzs.append("</div>")
        torzs.append("</section>")

    hol = forras_index(temak)
    cimek = {k.id: k.cim for _, _, _, k in kartyak(temak)}
    idx = ['<section class="idx" id="forrasindex" aria-labelledby="idx-h">',
           '<h2 id="idx-h">Melyik kérdés hol van?</h2>',
           "<p>A feladatsorok kérdései sorszám szerint; a szám a megfelelő kártyára visz.</p>"]
    for d in adat["dolgozatok"]:
        chips = "".join(
            f'<a href="#k-{hol[(d["jel"], q["szam"])]}" data-card="{hol[(d["jel"], q["szam"])]}" '
            f'title="{esc(cimek[hol[(d["jel"], q["szam"])]])}">{q["szam"]}</a>' for q in d["kerdesek"])
        idx.append(f'<div class="idx-row"><h3>{d["jel"]}. feladatsor<small>{datum_hu(d["datum"])}</small></h3>'
                   f'<div class="chips">{chips}</div></div>')
    idx.append("</section>")

    pdf = " · ".join(f'<a href="{esc(d["pdf"])}" target="_blank" rel="noopener" '
                     f'title="{esc(datum_hu(d["datum"]))}">{d["jel"]}.</a>' for d in adat["dolgozatok"])
    ma = datetime.date.today()
    csere = {
        "{{TITLE}}": CIM,
        "{{DESC}}": LEIRAS,
        "{{SITE}}": oldal,
        "{{EYEBROW}}": "OKFŐ megoldólapok · 2026. június 8–11. · I–VIII. feladatsor",
        "{{STAT_KERDES}}": str(st["kerdes"]),
        "{{STAT_KARTYA}}": str(st["kartya"]),
        "{{STAT_OSSZEVONT}}": str(st["osszevont"]),
        "{{STAT_TEMA}}": str(st["tema"]),
        "{{TOC}}": "\n".join(toc),
        "{{TOPICTABLE}}": "\n".join(tabla),
        "{{TOPICS}}": "\n".join(torzs),
        "{{INDEX}}": "\n".join(idx),
        "{{PDFLINKS}}": pdf,
        "{{GENERATED}}": f"Összeállítva: {ma.year}. {HONAP[ma.month - 1]} {ma.day}.",
    }
    for mit, mire in csere.items():
        sablon = sablon.replace(mit, mire)
    if "{{" in sablon:
        raise ValueError("kitöltetlen helyőrző a sablonban: " + re.search(r"\{\{\w+\}\}", sablon).group(0))
    fej, test = sablon.split("<!--TORZS-->", 1)
    return fej.strip(), test.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", help="a claude.ai Artifacthoz szánt változat (fej és törzs, dokumentumváz nélkül)")
    ap.add_argument("--oldal", default=OLDAL, help="a közzétett oldal címe (linkekhez és előnézethez)")
    args = ap.parse_args()

    temak = beolvas(GYOKER / "forras" / "kartyak.txt")
    adat = json.loads((GYOKER / "forras" / "kerdesek.json").read_text(encoding="utf-8"))
    hibak, figyelm = ellenoriz(temak, adat)
    for f in figyelm:
        print("figyelem:", f, file=sys.stderr)
    if hibak:
        for h in hibak:
            print("HIBA:", h, file=sys.stderr)
        sys.exit(f"{len(hibak)} hiba, nem generáltam semmit.")

    st = statisztika(temak, adat)
    (GYOKER / "TANANYAG.md").write_text(build_md(temak, adat, st, args.oldal), encoding="utf-8")
    fej, test = build_html(temak, adat, st, (GYOKER / "eszkozok" / "sablon.html").read_text(encoding="utf-8"), args.oldal)
    teljes = ('<!doctype html>\n<html lang="hu">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
              f"{fej}\n</head>\n<body>\n{test}\n</body>\n</html>\n")
    (GYOKER / "index.html").write_text(teljes, encoding="utf-8")
    if args.artifact:
        Path(args.artifact).write_text(f"{fej}\n{test}\n", encoding="utf-8")
    print(f"{st['kerdes']} kérdés → {st['kartya']} kártya ({st['osszevont']} összevont, "
          f"{st['osszevont_kerdes']} kérdésből), {st['tema']} téma")
    for ts in st["temak"]:
        print(f"  {ts['n']:2d}. {ts['cim']:<45} {ts['kartya']:3d} kártya {ts['pont']:4d} pont")


if __name__ == "__main__":
    main()
