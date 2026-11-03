"""ADVERTPR-612: `sf-kit kontakt pokaz|ustaw|migruj` — profil komunikacji osoby (biblioteka i CLI, bez sieci).

v1.0.0 (04.11.2026) - APro Agents / borys-sf · kontrakt backend/docs/API-PROFIL-KOMUNIKACJI-KONTRAKT.md v0.2 (repo salesforge)

Co pilnujemy: brak profilu = kod 0 i zdanie „pisz neutralnie”; `ustaw` wysyła tylko zmienione pola, z wersją,
`--sucho` nic nie zapisuje; reguły dokładane bez dubli, `--usun-regule N` w numeracji agenta; parser LUDZIE.md
(blok osoby i tabela, tylko sekcja PROFILE); plan migracji nie nadpisuje SF bez `--nadpisz`; raport z danymi
osobowymi tylko w pliku 600, na ekranie adresy zamaskowane; `--zapisz` bez `--zgoda` = odmowa.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, kontakt  # noqa: E402
from sf_kit.api import BladAPI, Klient  # noqa: E402
from sf_kit.tozsamosc import Organizacja  # noqa: E402

MICHAL = "m.hanajczyk@advertpro.co"
ORG = Organizacja(uuid="289cef06-b8b9-4a0c-967f-2533b08e82c4", slug="advertpro-co", nazwa="AdvertPro")

LUDZIE = """# LUDZIE

## Kto jest kim
- Ktoś Spoza <spoza@example.com> — to nie jest sekcja profili

## PROFILE

### Michał Hanajczyk <m.hanajczyk@advertpro.co>
- Relacja: zespół — automaty i wdrożenia
- Forma: na ty („Michale”)
- Ton: L2
- Kanały: e-mail (preferowany), SF
- Reguły:
  - wiadomość o czymś do zrobienia → sprawa w SF + link w treści
- Lubi konkrety w punktach

### Tomasz Gawlik
- E-mail: t.gawlik@autera.pl
- Relacja: wspólnik Autery
- Zwrot: na ty („Tomku”)
- Ton: wprost
- Organizacja: autera

### Bez Adresu
- Ton: L1

## Inne
- Inna Osoba <inna@example.com>
"""

KONTAKTY = """| Osoba | E-mail | Forma | Ton |
|---|---|---|---|
| Michał | m.hanajczyk@advertpro.co | per Pan | L1 |
| Anna Nowak | a.nowak@klient.pl | per Pani | L1 |
"""


def _profil(**pola) -> dict:
    baza = {"id": "11111111-1111-1111-1111-111111111111", "email": MICHAL, "wersja": 3, "nazwa": None,
            "relacja": None, "relacja_opis": None, "forma_zwrotu": None, "zwrot": None, "ton": None, "jezyk": "pl",
            "kanal_preferowany": None, "kanaly_dozwolone": [], "reguly": [], "notatki": None, "zrodlo": None,
            "ustalono_dnia": None, "party_id": None, "dla_agenta": "Profil komunikacji: <m.hanajczyk@advertpro.co>"}
    baza.update(pola)
    return baza


def _args(**pola) -> argparse.Namespace:
    domyslne = dict(nazwa=None, relacja_opis=None, zwrot=None, notatki=None, zrodlo=None, relacja=None, forma=None,
                    ton=None, kanal=None, kanaly=None, jezyk=None, ustalono=None, party=None, regula=None,
                    usun_regule=None, zastap_reguly=False)
    domyslne.update(pola)
    return argparse.Namespace(**domyslne)


class Atrapa:
    """Klient SF w pamięci: profile po adresie, zapisy do listy."""

    def __init__(self, profile: dict | None = None, klienci: dict | None = None, czlonkowie=()):
        self.profile = dict(profile or {})
        self.klienci_ = dict(klienci or {})
        self.czlonkowie = set(czlonkowie)
        self.zapisy: list = []

    def profil_po_adresie(self, email):
        return self.profile.get(email)

    def profil(self, profil_id):
        return next((p for p in self.profile.values() if p["id"] == profil_id), None)

    def profil_utworz(self, dane):
        self.zapisy.append(("POST", dane))
        return {"id": "nowy", "wersja": 1}

    def profil_zmien(self, profil_id, wersja, zmiany):
        self.zapisy.append(("PATCH", profil_id, wersja, zmiany))
        return {"id": profil_id, "wersja": wersja + 1}

    def klienci(self, q, limit=20):
        return self.klienci_.get(q, [])

    def czlonek(self, email):
        if email in self.czlonkowie:
            return {"email": email}
        raise BladAPI("nie członek", kod=404)


def _uruchom(argv, atrapa):
    with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=mock.Mock(adres="https://sf.test")), \
         mock.patch.object(cli, "_klient", return_value=atrapa), \
         mock.patch.object(cli, "_klient_dla_zapisu", return_value=(atrapa, ORG)), \
         redirect_stdout(io.StringIO()) as wyj, redirect_stderr(io.StringIO()) as err:
        kod = cli.main(argv)
    return kod, wyj.getvalue(), err.getvalue()


class TestZmianyZPolecenia(unittest.TestCase):

    def test_pola_slowniki_i_czyszczenie(self):
        z = kontakt.zmiany_z_polecenia(_args(forma="ty", ton="l3", zwrot="", kanaly="email, sf,email",
                                             kanal="sf", ustalono="2026-11-03"), None)
        self.assertEqual(z, {"forma_zwrotu": "ty", "ton": "L3", "zwrot": None, "kanaly_dozwolone": ["email", "sf"],
                             "kanal_preferowany": "sf", "ustalono_dnia": "2026-11-03"})

    def test_zla_wartosc_przed_siecia(self):
        for args in (_args(relacja="kolega"), _args(ton="L4"), _args(kanaly="email,fax"), _args(party="nie-uuid"),
                     _args(regula=["bez strzałki"])):
            with self.assertRaises(kontakt.BladProfilu):
                kontakt.zmiany_z_polecenia(args, None)

    def test_reguly_dokladane_bez_dubli_i_usuwane_w_numeracji_agenta(self):
        obecny = _profil(reguly=[
            {"id": "a", "warunek": "nieaktywna", "dzialanie": "x", "aktywna": False},
            {"id": "b", "warunek": "zadanie", "dzialanie": "sprawa + link", "aktywna": True},
            {"id": "c", "warunek": "pilne", "dzialanie": "telefon", "aktywna": True}])
        z = kontakt.zmiany_z_polecenia(_args(regula=["Zadanie => sprawa  + link", "faktura -> do Agaty"],
                                             usun_regule=[2]), obecny)
        self.assertEqual([r.get("id") for r in z["reguly"]], ["a", "b", None])   # 2. aktywna = „pilne”
        self.assertEqual(z["reguly"][2]["dzialanie"], "do Agaty")
        with self.assertRaises(kontakt.BladProfilu):
            kontakt.zmiany_z_polecenia(_args(usun_regule=[3]), obecny)
        z = kontakt.zmiany_z_polecenia(_args(zastap_reguly=True), obecny)
        self.assertEqual(z["reguly"], [])

    def test_tylko_zmienione_i_roznice(self):
        obecny = _profil(ton="L2", forma_zwrotu="ty")
        z = kontakt.tylko_zmienione(obecny, {"ton": "L2", "forma_zwrotu": "pan", "zwrot": ""})
        self.assertEqual(z, {"forma_zwrotu": "pan"})
        self.assertEqual(kontakt.roznice(obecny, z), ["forma_zwrotu: ty → pan"])

    def test_kanal_preferowany_poza_dozwolonymi(self):
        self.assertIsNotNone(kontakt.sprawdz_kanaly({"kanaly_dozwolone": ["email"], "kanal_preferowany": "sms"}))
        self.assertIsNone(kontakt.sprawdz_kanaly({"kanaly_dozwolone": [], "kanal_preferowany": "sms"}))


class TestParser(unittest.TestCase):

    def test_blok_osoby_tylko_sekcja_profile(self):
        osoby, uwagi = kontakt.parsuj_profile(LUDZIE, "LUDZIE.md", tylko_sekcja_profile=True)
        adresy = [o.email for o in osoby]
        self.assertEqual(adresy, [MICHAL, "t.gawlik@autera.pl"])          # spoza PROFILE i bez adresu — nie
        self.assertTrue(any("bez adresu" in u for u in uwagi))
        m = osoby[0]
        self.assertEqual(m.pola["nazwa"], "Michał Hanajczyk")
        self.assertEqual((m.pola["forma_zwrotu"], m.pola["zwrot"], m.pola["ton"]), ("ty", "Michale", "L2"))
        self.assertEqual((m.pola["relacja"], m.pola["relacja_opis"]), ("zespol", "zespół — automaty i wdrożenia"))
        self.assertEqual((m.pola["kanaly_dozwolone"], m.pola["kanal_preferowany"]), (["email", "sf"], "email"))
        self.assertEqual([(r["warunek"], r["dzialanie"]) for r in m.reguly],
                         [("wiadomość o czymś do zrobienia", "sprawa w SF + link w treści")])
        self.assertEqual(m.nierozpoznane, ["Lubi konkrety w punktach"])
        t = osoby[1]
        self.assertEqual((t.pola["forma_zwrotu"], t.pola["zwrot"], t.pola["ton"], t.pola["relacja"]),
                         ("ty", "Tomku", "L3", "wspolnik"))
        self.assertEqual(t.organizacja, "autera")

    def test_tabela_i_cały_plik(self):
        osoby, uwagi = kontakt.parsuj_profile(KONTAKTY, "contacts.md", tylko_sekcja_profile=False)
        self.assertEqual([(o.email, o.pola.get("forma_zwrotu"), o.pola.get("ton")) for o in osoby],
                         [(MICHAL, "pan", "L1"), ("a.nowak@klient.pl", "pani", "L1")])
        self.assertEqual(uwagi, [])

    def test_brak_sekcji_profile_czyta_calosc_z_uwaga(self):
        osoby, uwagi = kontakt.parsuj_profile("### X <x@y.pl>\n- Ton: L1\n", "L.md", tylko_sekcja_profile=True)
        self.assertEqual([o.email for o in osoby], ["x@y.pl"])
        self.assertTrue(any("PROFILE" in u for u in uwagi))

    def test_scalenie_ludzie_wygrywa_konflikt_w_raporcie(self):
        l, _ = kontakt.parsuj_profile(LUDZIE, "LUDZIE.md", tylko_sekcja_profile=True)
        c, _ = kontakt.parsuj_profile(KONTAKTY, "contacts.md", tylko_sekcja_profile=False)
        osoby, konflikty = kontakt.scal_zrodla(l, c)
        self.assertEqual(osoby[MICHAL].pola["forma_zwrotu"], "ty")
        self.assertEqual(osoby[MICHAL].pola["ton"], "L2")
        self.assertEqual(len([k for k in konflikty if k.startswith(MICHAL)]), 3)   # nazwa, forma, ton
        self.assertIn("a.nowak@klient.pl", osoby)


class TestPlan(unittest.TestCase):

    def _michal(self):
        osoby, _ = kontakt.parsuj_profile(LUDZIE, "LUDZIE.md", tylko_sekcja_profile=True)
        return osoby[0]

    def test_nowy_profil(self):
        poz = kontakt.zaplanuj(self._michal(), None)
        self.assertEqual(poz.akcja, "utworz")
        self.assertEqual(poz.zmiany["ton"], "L2")
        self.assertIn("nierozpoznane", poz.zmiany["notatki"])          # nic z pliku nie ginie po cichu
        self.assertIn("LUDZIE.md", poz.zmiany["zrodlo"])

    def test_sf_wygrywa_bez_nadpisz_puste_uzupelnia_reguly_dokladane(self):
        obecny = _profil(ton="L3", reguly=[{"id": "r1", "warunek": "Wiadomość o czymś do zrobienia",
                                           "dzialanie": "sprawa w SF + link w treści", "aktywna": True}])
        poz = kontakt.zaplanuj(self._michal(), obecny)
        self.assertEqual(poz.akcja, "uzupelnij")
        self.assertNotIn("ton", poz.zmiany)
        self.assertEqual(poz.konflikty_z_sf, ["ton: w SF L3 · w pliku L2"])
        self.assertNotIn("reguly", poz.zmiany)                            # ta sama reguła = bez dubla
        self.assertEqual(poz.zmiany["forma_zwrotu"], "ty")
        self.assertNotIn("zrodlo", poz.zmiany)
        self.assertEqual(kontakt.zaplanuj(self._michal(), obecny, nadpisz=True).zmiany["ton"], "L2")

    def test_maskowanie(self):
        self.assertEqual(kontakt.maskuj_email(MICHAL), "m***@a***.co")


class TestKlientApi(unittest.TestCase):

    def test_404_to_brak_profilu_a_nie_blad(self):
        k = Klient.__new__(Klient)
        with mock.patch.object(Klient, "_wywolaj", side_effect=BladAPI("x", kod=404)):
            self.assertIsNone(k.profil_po_adresie(MICHAL))
        with mock.patch.object(Klient, "_wywolaj", side_effect=BladAPI("x", kod=403)):
            with self.assertRaises(BladAPI):
                k.profil_po_adresie(MICHAL)

    def test_patch_niesie_wersje(self):
        k = Klient.__new__(Klient)
        with mock.patch.object(Klient, "_wywolaj", return_value={}) as w:
            k.profil_zmien("p-1", 4, {"ton": "L1"})
        w.assert_called_once_with("PATCH", "profile-komunikacji/p-1", cialo={"wersja": 4, "ton": "L1"})


class TestPolecenia(unittest.TestCase):

    def test_pokaz_profil_i_brak(self):
        a = Atrapa({MICHAL: _profil(dla_agenta="Profil komunikacji: Michał\n- Zwrot: na ty")})
        kod, out, _ = _uruchom(["kontakt", "pokaz", "M.Hanajczyk@AdvertPro.co"], a)
        self.assertEqual(kod, 0)
        self.assertTrue(out.startswith("Profil komunikacji: Michał\n- Zwrot: na ty"))
        kod, out, _ = _uruchom(["kontakt", "pokaz", "nikt@x.pl"], a)
        self.assertEqual(kod, 0)
        self.assertIn("pisz neutralnie", out)
        kod, out, _ = _uruchom(["kontakt", "pokaz", "nikt@x.pl", "--json"], a)
        self.assertEqual(out.strip(), "null")
        kod, out, _ = _uruchom(["kontakt", "pokaz", "11111111-1111-1111-1111-111111111111"], a)
        self.assertIn("Michał", out)

    def test_ustaw_sucho_nic_nie_zapisuje(self):
        a = Atrapa({MICHAL: _profil(ton="L2")})
        kod, out, _ = _uruchom(["kontakt", "ustaw", MICHAL, "--ton", "L3", "--sucho", "--org", "advertpro-co"], a)
        self.assertEqual((kod, a.zapisy), (0, []))
        self.assertIn("ton: L2 → L3", out)
        self.assertIn('"wersja": 3', out)

    def test_ustaw_patch_z_wersja_i_tylko_zmiana(self):
        a = Atrapa({MICHAL: _profil(ton="L2", forma_zwrotu="ty")})
        kod, _, _ = _uruchom(["kontakt", "ustaw", MICHAL, "--ton", "L3", "--forma", "ty",
                              "--regula", "zadanie => sprawa + link"], a)
        self.assertEqual(kod, 0)
        metoda, pid, wersja, zmiany = a.zapisy[0]
        self.assertEqual((metoda, wersja), ("PATCH", 3))
        self.assertEqual(set(zmiany), {"ton", "reguly"})

    def test_ustaw_nowy_adres_post(self):
        a = Atrapa()
        kod, _, _ = _uruchom(["kontakt", "ustaw", "Nowy@X.pl", "--forma", "pan", "--ton", "L1"], a)
        self.assertEqual(kod, 0)
        self.assertEqual(a.zapisy, [("POST", {"email": "nowy@x.pl", "forma_zwrotu": "pan", "ton": "L1"})])

    def test_ustaw_bez_zmian(self):
        a = Atrapa({MICHAL: _profil(ton="L2")})
        kod, out, _ = _uruchom(["kontakt", "ustaw", MICHAL, "--ton", "L2"], a)
        self.assertEqual((kod, a.zapisy), (0, []))
        self.assertIn("Bez zmian", out)


class TestMigracja(unittest.TestCase):

    def setUp(self):
        self.kat = tempfile.TemporaryDirectory()
        k = Path(self.kat.name)
        (k / "LUDZIE.md").write_text(LUDZIE, encoding="utf-8")
        (k / "contacts.md").write_text(KONTAKTY, encoding="utf-8")
        self.raport = k / "raport.md"
        self.argv = ["kontakt", "migruj", "--ludzie", str(k / "LUDZIE.md"), "--kontakty", str(k / "contacts.md"),
                     "--raport", str(self.raport), "--org", "advertpro-co"]

    def tearDown(self):
        self.kat.cleanup()

    def _atrapa(self):
        return Atrapa({MICHAL: _profil(ton="L3")},
                      klienci={"a.nowak@klient.pl": [{"id": "22222222-2222-2222-2222-222222222222",
                                                      "email": "a.nowak@klient.pl", "kind": "person"}]},
                      czlonkowie={MICHAL})

    def test_na_sucho_raport_w_pliku_ekran_bez_adresow(self):
        a = self._atrapa()
        kod, out, _ = _uruchom(self.argv, a)
        self.assertEqual((kod, a.zapisy), (0, []))
        self.assertNotIn("@advertpro.co", out)
        self.assertNotIn("a.nowak@", out)
        self.assertIn("nowe profile: 1 · uzupełnienia: 1", out)          # Anna nowa, Michał uzupełnienie
        self.assertIn("innej Organizacji: 1", out)                       # Tomasz → autera
        raport = self.raport.read_text(encoding="utf-8")
        self.assertIn(f"## {MICHAL} — UZUPEŁNIENIE", raport)
        self.assertIn("ton: w SF L3 · w pliku L2", raport)
        self.assertIn("party_id: — → 22222222", raport)
        self.assertIn("Kontakt w SF: członek", raport)
        self.assertEqual(os.stat(self.raport).st_mode & 0o777, 0o600)

    def test_zapis_tylko_ze_zgoda(self):
        a = self._atrapa()
        kod, _, err = _uruchom(self.argv + ["--zapisz"], a)
        self.assertEqual((kod, a.zapisy), (1, []))
        self.assertIn("--zgoda", err)
        kod, out, _ = _uruchom(self.argv + ["--zapisz", "--zgoda", "abcd1234"], a)
        self.assertEqual(kod, 0)
        self.assertEqual(sorted(z[0] for z in a.zapisy), ["PATCH", "POST"])
        patch = next(z for z in a.zapisy if z[0] == "PATCH")
        self.assertNotIn("ton", patch[3])                                # SF wygrywa bez --nadpisz
        self.assertIn("Zapisane: 2", out)


if __name__ == "__main__":
    unittest.main()
