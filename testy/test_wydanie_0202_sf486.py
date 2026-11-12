"""Kit 0.20.2: wydanie poprawkowe SF-486 (usterki 1–7, dokumentacja 15–17, pkt 18 przegląd z parsera, wersje floty).

v1.0.0 (12.11.2026) - APro Agents / arek · SF-486

CZEGO PILNUJĄ
· pkt 1: `-` przy otwartym, pustym stdin (nie terminal) = ZleWejscie po limicie, nie wiszenie; dane w potoku czytane.
· pkt 2: numer leada (domyślna lista go chowa) znajdowany drugim pytaniem w `widok=leady`.
· pkt 3: `Bug` → `bug`; nazwy i wartości z taksonomii `ticket_category`; nieznana = błąd z listą PRZED wysłaniem.
· pkt 4: własne konto pominięte z komunikatem, 409 „already exists” = już obserwuje (nie porażka).
· pkt 6: odmowa `--status resolved` wypisuje otwarte zadania i polecenia domknięcia.
· pkt 15: brak `sf.dpakula.pl` w AGENT.md i w adresie domyślnym.
· pkt 18 (BRAMKA): każde polecenie ma opis i rolę; przegląd ≤ 80 linii dla każdej roli; każde polecenie (poza
  wewnętrznymi) jest w przeglądzie; przykłady koordynatora przechodzą parser; `start` wkleja przegląd.
· pomiar wersji: `flota wersje` czyta pola `kit_*` z `GET /agents`.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import argparse
import io
import os
import shlex
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import asystent, cli, config, koordynacja, nawyki, przeglad, start  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

KOD = Path(__file__).resolve().parents[1]


def uruchom(funkcja, args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            kod = funkcja(args)
        except SystemExit as e:
            kod = e.code
    return kod, out.getvalue(), err.getvalue()


@unittest.skipIf(os.name == "nt", "select na potokach — tylko POSIX")
class TestStdinBezTerminala(unittest.TestCase):
    """pkt 1: „Kit wisi bez < /dev/null” — narzędzie agenta daje otwarty, pusty potok."""

    def _potok(self, dane: bytes | None):
        r, w = os.pipe()
        if dane is not None:
            os.write(w, dane)
            os.close(w)
        else:
            self.addCleanup(os.close, w)          # pisarz żyje: EOF nie przyjdzie nigdy
        strumien = os.fdopen(r, "r", encoding="utf-8")
        self.addCleanup(strumien.close)
        return strumien

    def test_otwarty_pusty_potok_konczy_sie_bledem_nie_wiszeniem(self):
        with mock.patch.dict(os.environ, {nawyki.ZMIENNA_CZEKAJ_STDIN: "0.2"}):
            with self.assertRaises(nawyki.ZleWejscie) as blad:
                nawyki.tresc(tresc_arg="-", stdin=self._potok(None))
        self.assertIn("nic na nie nie przyszło", str(blad.exception))

    def test_dane_w_potoku_sa_czytane(self):
        self.assertEqual(nawyki.tresc(opis="-", stdin=self._potok("raport\n".encode())), "raport\n")

    def test_pusty_zamkniety_potok_to_pusta_tresc_nie_wiszenie(self):
        with self.assertRaises(nawyki.ZleWejscie):
            nawyki.tresc(tresc_arg="-", stdin=self._potok(b""), wymagana=True)

    def test_atrapa_bez_deskryptora_jak_dotad(self):
        self.assertEqual(nawyki.tresc(tresc_arg="-", stdin=io.StringIO("x")), "x")


class TestLeadPoNumerze(unittest.TestCase):
    """pkt 2: „nie znalazłem sprawy FIX-40”, choć lead jest — domyślna lista SF chowa rodzaj Lead."""

    def test_drugie_pytanie_w_widoku_leady(self):
        klient = mock.Mock()
        klient.sprawy.side_effect = lambda **kw: (
            [{"id": "L1", "ticket_number": 40, "ticket_prefix": "FIX"}] if kw.get("widok") == "leady" else [])
        self.assertEqual(asystent.znajdz_sprawe(klient, "FIX-40")["id"], "L1")
        self.assertEqual(klient.sprawy.call_args.kwargs.get("widok"), "leady")

    def test_zwykla_sprawa_bez_drugiego_pytania(self):
        klient = mock.Mock()
        klient.sprawy.return_value = [{"id": "S1", "ticket_number": 7, "ticket_prefix": "SF"}]
        self.assertEqual(asystent.znajdz_sprawe(klient, "SF-7")["id"], "S1")
        self.assertEqual(klient.sprawy.call_count, 1)

    def test_parser_zna_leady(self):
        a = cli.zbuduj_parser().parse_args(["--org", "autera", "leady", "AUTERA-53", "--json"])
        self.assertEqual((a.lead, a.json, a.funkcja), ("AUTERA-53", True, cli.polecenie_leady))


class TestKategoria(unittest.TestCase):
    """pkt 3: `nowa-sprawa --tag Bug` → 422 (kategorie są małymi literami)."""

    TYPY = [{"slug": "ticket_category", "tags": [{"name": "Błąd", "value": "bug"}, {"name": "Pytanie", "value": "question"},
                                                 {"name": "Makieta", "value": "makieta"}]}]

    def test_wielkosc_liter_i_polskie_nazwy(self):
        self.assertEqual(nawyki.kategoria_sprawy("Bug"), "bug")
        self.assertEqual(nawyki.kategoria_sprawy("Pytanie"), "question")

    def test_kategorie_z_taksonomii_organizacji(self):
        mapa = nawyki.kategorie_z_taksonomii(self.TYPY)
        self.assertEqual(nawyki.kategoria_sprawy("Błąd", mapa), "bug")
        self.assertEqual(nawyki.kategoria_sprawy("MAKIETA", mapa), "makieta")

    def test_nieznana_odrzucona_z_lista_przed_wyslaniem(self):
        with self.assertRaises(nawyki.ZleWejscie) as blad:
            nawyki.kategoria_sprawy("Pilne")
        self.assertIn("bug, feature", str(blad.exception).replace("feedback, ", "").replace("feature, feedback", "feature"))

    def test_tag_kategorii_nie_jest_nadawany_jako_tag(self):
        klient = mock.Mock()
        with mock.patch.object(cli.konsola, "typy_wszystkie", return_value=self.TYPY):
            tagi, kategoria = cli._tagi_nowej_sprawy(klient, ["Błąd"])
        self.assertEqual((tagi, kategoria), ([], "bug"))


class TestObserwujacy(unittest.TestCase):
    """pkt 4: dwóch obserwujących → „dodał jednego, dołóż brakujących” (autor obserwuje od założenia, SF: 409)."""

    def test_wlasne_konto_pominiete_z_komunikatem_a_409_to_sukces(self):
        klient = mock.Mock()

        def dodaj(sprawa, adres):
            if adres == "juz@x.pl":
                raise BladAPI("Watcher juz@x.pl already exists", kod=409)
        klient.dodaj_obserwujacego.side_effect = dodaj
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            nieudane = cli._dodaj_obserwujacych(klient, "S", ["agata@x.pl", "juz@x.pl", "nowy@x.pl"],
                                                wlasny="Agata@x.pl")
        self.assertEqual(nieudane, [])
        self.assertIn("to Twoje konto", out.getvalue())
        self.assertIn("już obserwuje", out.getvalue())
        self.assertEqual([c.args[1] for c in klient.dodaj_obserwujacego.call_args_list], ["juz@x.pl", "nowy@x.pl"])


class TestOdmowaRozwiazania(unittest.TestCase):
    """pkt 6: odmowa ma pokazać, KTÓRE zadania są otwarte i jak je domknąć."""

    def test_lista_zadan_i_polecenia(self):
        klient = mock.Mock()
        klient.zadania_sprawy.return_value = [
            {"id": "z1", "external_id": "arek-1", "status": "in_progress", "assigned_agent_slug": "arek-localhost",
             "title": "Kit 0.20.2"},
            {"id": "z2", "status": "completed", "title": "stare"}]
        klient.tagi_sprawy.return_value = []
        with self.assertRaises(ValueError) as blad:
            koordynacja.zmien_status(klient, {"id": "S", "status": "in_progress"}, "resolved")
        tekst = str(blad.exception)
        self.assertIn("arek-1  [in_progress]  arek-localhost  Kit 0.20.2", tekst)
        self.assertIn("sf-kit zadanie arek-1 --status completed", tekst)
        self.assertIn("sf-kit odbierz arek-1", tekst)
        self.assertNotIn("stare", tekst)
        klient.zmien_sprawe.assert_not_called()


class TestAdresProd(unittest.TestCase):
    """pkt 15: od 09.10 PROD = https://sales-forge.pl."""

    def test_agent_md_i_adres_domyslny(self):
        self.assertNotIn("sf.dpakula.pl", (KOD / "AGENT.md").read_text(encoding="utf-8"))
        self.assertEqual(config.Konfiguracja().adres, "https://sales-forge.pl")


class TestPrzegladZParsera(unittest.TestCase):
    """pkt 18 — BRAMKA WYDANIA: przegląd z parsera nie może się rozjechać z Kitem."""

    @classmethod
    def setUpClass(cls):
        cls.parser = cli.zbuduj_parser()

    def test_kazde_polecenie_ma_opis_i_role(self):
        self.assertEqual(przeglad.bez_roli(self.parser), [],
                         "polecenie bez opisu albo bez [rola] na początku pomocy — dopisz, zanim wydasz")

    def test_przeglad_miesci_sie_w_limicie_dla_kazdej_roli(self):
        for rola in (None, "asystent", "worker", "koordynator"):
            linie = przeglad.przeglad(self.parser, profil=rola, wersja="0.0.0").splitlines()
            self.assertLessEqual(len(linie), przeglad.MAKS_LINII, f"rola {rola}: {len(linie)} linii")

    def test_kazde_polecenie_jest_w_przegladzie(self):
        tekst = przeglad.przeglad(self.parser, profil="koordynator")
        for p in przeglad.polecenia(self.parser):
            if p["rola"] == przeglad.WEWNETRZNE:
                continue
            self.assertIn(f"`{p['nazwa']}", tekst.replace(" | ", "`| `"), p["nazwa"])

    def test_laczone_nazwy_istnieja(self):
        nazwy = {p["nazwa"] for p in przeglad.polecenia(self.parser)}
        for grupa, _ in przeglad.LACZONE:
            self.assertTrue(set(grupa) <= nazwy, grupa)

    def test_przyklady_koordynatora_przechodza_parser(self):
        for _, przyklad in przeglad.PRZYKLADY_KOORDYNATORA:
            for wariant in przyklad.split(" | "):
                argv = shlex.split(wariant.replace("<", "").replace(">", ""))
                with self.subTest(wariant), redirect_stderr(io.StringIO()):
                    self.parser.parse_args(argv)

    def test_asystent_nie_widzi_polecen_koordynatora(self):
        tekst = przeglad.przeglad(self.parser, profil="asystent")
        self.assertNotIn("- `zlec", tekst)
        self.assertIn("`sprawa <sprawa>`", tekst)

    def test_pomoc_polecenia_i_tematu(self):
        md = "## A\n### Aktualizacje Kita\nUżyj `sf-kit update`.\n### Inne\nnic\n"
        self.assertEqual([t for t, _ in przeglad.temat(md, "aktualizacje")], ["Aktualizacje Kita"])
        self.assertEqual(przeglad.sekcje_z_poleceniem(md, "update"), ["Aktualizacje Kita"])
        self.assertIn("--hurt", przeglad.pomoc_polecenia(self.parser, "odbierz"))

    def test_start_wkleja_przeglad_i_naglowek_profilu(self):
        p = przeglad.przeglad(self.parser, profil="worker", wersja="0.20.2")
        with tempfile.TemporaryDirectory() as k:
            start.przygotuj(Path(k), org_slug="sf", org_nazwa="SalesForge", readme=KOD / "AGENT.md", agent=None,
                            profil="worker", przeglad=p)
            tresc = (Path(k) / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("profil: worker", tresc)
        self.assertIn("SF Kit 0.20.2: przegląd", tresc)
        self.assertLess(tresc.index("SF Kit 0.20.2"), tresc.index(start.ZNACZNIK_KONIEC))


class TestCzystyAgent(unittest.TestCase):
    """pkt 19, próba generalna 12.11: czysty agent nie widział zadania w toku i dostawał obcięte wpisy."""

    def test_tasks_pokazuje_w_toku_i_wstrzymane(self):
        from sf_kit.api import WynikSzukania
        klient = mock.Mock()
        klient.moje_zadania.side_effect = lambda slug, status="queued": WynikSzukania(
            [{"external_id": f"z-{status}", "title": "t", "ticket_id": "S"}] if status != "queued" else [], 10, 10)
        a = argparse.Namespace(pelne=False, status=None, org=None)
        with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=mock.Mock(slug="arek")), \
                mock.patch.object(cli, "_klient", return_value=klient):
            kod, out, _ = uruchom(cli.polecenie_tasks, a)
        self.assertEqual(kod, 0)
        self.assertIn("z-in_progress  [in_progress]", out)
        self.assertIn("z-on_hold  [on_hold]", out)

    def test_sprawa_nie_obcina_wpisow(self):
        dlugi = "x" * 5000
        karta = {"id": "S", "ticket_prefix": "SF", "ticket_number": 1, "title": "t", "description": "d",
                 "entries": [{"entry_type": "note", "content": dlugi, "created_at": "2026-11-12T21:40:00Z"}]}
        klient = mock.Mock()
        klient.sprawa.return_value = karta
        a = argparse.Namespace(sprawa="SF-1", wszystkie=False, json=False, tylko_id=False, status=None, kind=None,
                               org="sf")
        with mock.patch.object(cli.konfiguracja, "wczytaj"), \
                mock.patch.object(cli, "_klient", return_value=klient), \
                mock.patch.object(cli, "_sprawa_dla_zapisu", return_value=({"id": "S"}, None)), \
                mock.patch.object(cli, "_pokaz_do_ciebie"):
            kod, out, _ = uruchom(cli.polecenie_sprawa, a)
        self.assertEqual(kod, 0)
        self.assertIn(dlugi, out)
        self.assertNotIn("obcięte", out)
        from sf_kit import kontekst
        self.assertEqual(kontekst.LIMIT_WPISU, 1500)          # limit kontekstu startowego przywrócony


class TestFlotaWersje(unittest.TestCase):
    """Pomiar wersji: SF zapisuje wersję z User-Agent (ADVERTPR-960); Kit tylko ją pokazuje."""

    def test_wiersze_z_get_agents(self):
        klient = mock.Mock()
        klient.agenci.return_value = [
            {"agent_slug": "agata", "kit_version": "0.18.0", "kit_seen_at": "2026-11-12T21:40:00Z",
             "kit_outdated": True, "kit_below_min": False},
            {"agent_slug": "arek-localhost", "kit_version": "0.20.2", "kit_seen_at": "2026-11-13T10:00:00Z",
             "kit_outdated": False, "kit_below_min": False},
            {"agent_slug": "wojt", "kit_version": None}]
        org = mock.Mock(slug="advertpro-co")
        a = argparse.Namespace(ponizej=False, json=False, org="advertpro-co")
        with mock.patch.object(cli.konfiguracja, "wczytaj"), \
                mock.patch.object(cli, "_koordynator", return_value=(klient, org)):
            kod, out, _ = uruchom(cli.polecenie_flota_wersje, a)
        self.assertEqual(kod, 0)
        self.assertIn("agata", out)
        self.assertIn("nieaktualna", out)
        self.assertIn("nie widziany", out)
        self.assertIn("1 do aktualizacji", out)


if __name__ == "__main__":
    unittest.main()
