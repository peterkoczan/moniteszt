# Egészségügyi alapmodul – tananyag

**Megnyitás böngészőben, telefonon is: https://peterkoczan.github.io/moniteszt/**

Olvasható változat itt, GitHubon: **[TANANYAG.md](TANANYAG.md)**

Tananyag a természetgyógyászati képzés egészségügyi alapmoduljának 2026. június 8–11-i
írásbeli vizsgáiból, az [OKFŐ megoldólapjai](https://enk.okfo.gov.hu/tevekenysegek/tgy-eu-alapmodul-es-szakmai-vizsga/vizsgaeredmenyek-2026/2026.-junius-8-11-termeszetgyogyaszati-es-egeszsegugyi-vizsgak-megoldolapjai)
alapján (I–VIII. feladatsor).

- **190 vizsgakérdés 171 kártyán, 12 témában**, a feladatsorok sorrendjében, a hivatalos megoldásokkal.
- Az azonos vagy átfedő kérdések (pl. a lép, a vitaminok, a légzőrendszer igaz/hamis állításai)
  egy kártyára kerültek, a forrásuk megjelölésével.
- Az interaktív oldalon: **Tanulás** mód (minden megoldás látszik), **Önellenőrzés** (a megoldás
  rejtve, koppintásra jelenik meg), **Kikérdezés** (véletlen sorrendben a még nem tudott kártyák),
  keresés, „tudom” jelölés (a böngésző megjegyzi).

## Hogyan készült

| fájl | szerep |
|---|---|
| `eszkozok/kinyer.py` | letölti a megoldólap-PDF-eket, és kinyeri a kérdéseket, pontszámokat, csillagokat, a piros megoldásokat és a piros aláhúzásokat → `forras/kerdesek.json` |
| `forras/kartyak.txt` | a kézzel gondozott kártyák: témák, összevonások, rendezett megoldások (a formátum a fájl elején) |
| `eszkozok/build.py` | ellenőrzi, hogy minden kérdés pontosan egyszer szerepel-e, és a pontszámok meg a csillagok egyeznek-e, majd legenerálja a `TANANYAG.md`-t és az `index.html`-t |
| `eszkozok/sablon.html` | a HTML-oldal sablonja (stílus és működés) |

Újragenerálás:

```sh
pip install pymupdf            # csak a kinyeréshez kell
python3 eszkozok/kinyer.py     # PDF → forras/kerdesek.json
python3 eszkozok/build.py      # kartyak.txt + kerdesek.json → TANANYAG.md, index.html
```

A `kinyer.py` egy megoldólap-oldalt dolgoz fel (alapból a 2026. júniusit); másik vizsgaidőszak
hozzáadásához a kártyafájl forrásjelöléseit (pl. `II/5`) is bővíteni kell.

Nem hivatalos összeállítás. A megoldások a megoldólapokról származnak; a zárójeles magyar nevek,
a „→” javítások és a tippek kiegészítések.
