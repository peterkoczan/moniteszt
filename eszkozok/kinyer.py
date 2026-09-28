#!/usr/bin/env python3
"""Megoldólapok letöltése és kinyerése strukturált JSON-ba.

Az OKFŐ oldalon (enk.okfo.gov.hu) közzétett megoldólap-PDF-ekben a megoldások
piros betűvel, az aláhúzandó válaszok és a definíciók kulcsszavai piros
aláhúzással szerepelnek. A szkript ezeket jelölve menti el:

    【szöveg】  piros (megoldás) szöveg
    ⟦szöveg⟧   pirossal aláhúzott szöveg

Használat:
    pip install pymupdf
    python3 eszkozok/kinyer.py [OLDAL_URL] [--modul "Egészségügyi alapmodul"]

Kimenet: forras/kerdesek.json (a PDF-ek a forras/pdf/ mappába kerülnek).
"""

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import pymupdf
except ImportError:  # régebbi PyMuPDF
    import fitz as pymupdf

ALAP_URL = (
    "https://enk.okfo.gov.hu/tevekenysegek/tgy-eu-alapmodul-es-szakmai-vizsga/"
    "vizsgaeredmenyek-2026/"
    "2026.-junius-8-11-termeszetgyogyaszati-es-egeszsegugyi-vizsgak-megoldolapjai"
)
GYOKER = Path(__file__).resolve().parent.parent
PIROS = 0xFF0000
FEJLEC = re.compile(r"^(\d+)\.\s*(\*)?\s*(\d+)\s*pont$")


def letolt(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def pdf_linkek(oldal_url: str, modul: str):
    """(link szövege, abszolút URL) párok a modul megoldólapjaihoz."""
    s = letolt(oldal_url).decode("utf-8", "replace")
    for href, belso in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', s, re.S):
        szoveg = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", belso))).strip()
        if szoveg.startswith(modul) and "pfile" in href:
            yield szoveg, urllib.parse.urljoin(oldal_url, html.unescape(href))


def alahuzasok(page):
    """A piros, vékony kitöltött téglalapok = aláhúzások."""
    return [
        d["rect"]
        for d in page.get_drawings()
        if d["type"] == "f" and d.get("fill") == (1.0, 0.0, 0.0)
        and d["rect"].height < 3 and d["rect"].width > 2
    ]


def alahuzott(bbox, rects):
    x0, y0, x1, y1 = bbox
    cx, h = (x0 + x1) / 2, y1 - y0
    return any(r.x0 - 0.5 <= cx <= r.x1 + 0.5 and y0 + 0.55 * h <= r.y0 <= y1 + 3 for r in rects)


def oldal_sorai(page):
    """Az oldal sorai [(szöveg jelölésekkel, félkövér-e)] alakban, fentről lefelé."""
    rects = alahuzasok(page)
    nyers = []
    for blokk in page.get_text("rawdict")["blocks"]:
        for sor in blokk.get("lines", []):
            jelek = []
            for span in sor["spans"]:
                piros = span["color"] == PIROS
                felkover = bool(span["flags"] & 16)
                for ch in span["chars"]:
                    jelek.append((ch["c"], piros, alahuzott(ch["bbox"], rects), felkover))
            if jelek:
                nyers.append((sor["bbox"][1], sor["bbox"][0], jelek))
    nyers.sort(key=lambda t: (t[0], t[1]))
    # az azonos magasságban lévő darabok (pl. táblázatcellák) egy sorba kerülnek, balról jobbra
    csoportok = []
    for y, x, jelek in nyers:
        if csoportok and abs(csoportok[-1][0] - y) < 2.5:
            csoportok[-1][1].append((x, jelek))
        else:
            csoportok.append([y, [(x, jelek)]])
    sorok = []
    for _, darabok in csoportok:
        darabok.sort(key=lambda t: t[0])
        jelek = []
        for i, (_, d) in enumerate(darabok):
            if i:
                jelek.append((" ", False, False, False))
            jelek.extend(d)
        szoveg, allapot = "", None
        for c, piros, ah, _ in jelek:
            uj = (piros, ah)
            if uj != allapot:
                if allapot is not None:
                    szoveg += ("⟧" if allapot[1] else "") + ("】" if allapot[0] else "")
                szoveg += ("【" if piros else "") + ("⟦" if ah else "")
                allapot = uj
            szoveg += c
        if allapot:
            szoveg += ("⟧" if allapot[1] else "") + ("】" if allapot[0] else "")
        szoveg = re.sub(r"【(\s*)】", r"\1", szoveg)
        szoveg = re.sub(r"⟦(\s*)⟧", r"\1", szoveg)
        szoveg = re.sub(r"\s+", " ", szoveg).strip()
        # félkövér a sor, ha a betűk (legalább 80%-a) félkövér; a kötőjel néha más betűtípusú
        betuk = [j for j in jelek if j[0].isalpha()]
        felkover = bool(betuk) and sum(j[3] for j in betuk) >= 0.8 * len(betuk)
        if szoveg:
            sorok.append((szoveg, felkover))
    return sorok


def kerdesek(pdf_path: Path):
    doc = pymupdf.open(pdf_path)
    sorok = []
    for i, page in enumerate(doc):
        if i < 2:  # borító + tájékoztató
            continue
        ls = oldal_sorai(page)
        if ls and re.fullmatch(r"\d+", ls[0][0]):  # oldalszám
            ls = ls[1:]
        sorok.extend(ls)
    eredmeny, akt = [], None
    for szoveg, felkover in sorok:
        m = FEJLEC.match(szoveg)
        if m:
            akt = {"szam": int(m.group(1)), "pont": int(m.group(3)),
                   "csillag": bool(m.group(2)), "kerdes": "", "sorok": [], "pontozas": ""}
            eredmeny.append(akt)
            continue
        if akt is None:
            continue
        # a kérdés a fejléc utáni félkövér sorokból áll; ha már felkiáltó- vagy kérdőjelre
        # végződik, a további félkövér sorok (pl. táblázatfejléc) már a feladathoz tartoznak
        kesz = akt["kerdes"].endswith(("!", "?")) and not szoveg.startswith(("Írj", "Írja"))
        if felkover and not akt["sorok"] and not kesz:
            akt["kerdes"] = (akt["kerdes"] + " " + szoveg).strip()
        elif szoveg.startswith("(") and ("pont" in szoveg or "adható" in szoveg):
            akt["pontozas"] = szoveg.strip("() ")
        else:
            akt["sorok"].append(szoveg)
    return eredmeny


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", default=ALAP_URL)
    ap.add_argument("--modul", default="Egészségügyi alapmodul")
    ap.add_argument("--ki", default=str(GYOKER / "forras" / "kerdesek.json"))
    args = ap.parse_args()

    pdf_mappa = GYOKER / "forras" / "pdf"
    pdf_mappa.mkdir(parents=True, exist_ok=True)
    dolgozatok = []
    for szoveg, url in pdf_linkek(args.url, args.modul):
        m = re.search(r"(\d{4})(\d{2})(\d{2})\s+([IVXL]+)\.?$", szoveg)
        if not m:
            print("kihagyva (ismeretlen cím):", szoveg, file=sys.stderr)
            continue
        jel = m.group(4)
        cel = pdf_mappa / f"{m.group(1)}{m.group(2)}{m.group(3)}_{jel}.pdf"
        if not cel.exists():
            cel.write_bytes(letolt(url))
        k = kerdesek(cel)
        dolgozatok.append({
            "jel": jel,
            "datum": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
            "cim": szoveg,
            "pdf": url,
            "osszpont": sum(q["pont"] for q in k),
            "kerdesek": k,
        })
        print(f"{jel:>5}  {len(k):2d} kérdés  {sum(q['pont'] for q in k):3d} pont  {szoveg}")
    if not dolgozatok:
        sys.exit("Nem találtam megoldólapot ezen az oldalon: " + args.url)
    ki = {"forras_oldal": args.url, "modul": args.modul, "dolgozatok": dolgozatok}
    Path(args.ki).write_text(json.dumps(ki, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("mentve:", args.ki)


if __name__ == "__main__":
    main()
