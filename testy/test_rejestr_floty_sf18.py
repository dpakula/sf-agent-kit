"""`sf-kit flota rejestr` — migawka agents.json do SF (SF-18).

v0.1 (24.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJEMY
1. **Slug z `sf_agent_slug`, potem z `id` — nigdy z `sf.agent_slug`.** Na prawdziwym rejestrze
   (24.09) pięć wpisów ma w `sf.agent_slug` tę samą, skopiowaną wartość; wzięcie jej zlałoby
   pięć kont w jedno.
2. **Kształt ciała = model `WpisMigawki` w SF.** Pola przepisane z backendu 24.09 i sprawdzone
   jego prawdziwym modelem pydantic (round-trip identyczny). Pydantic po stronie SF po cichu
   GUBI nieznane pola, więc literówka w nazwie pola nie dałaby błędu — dałaby pustą kolumnę.
3. **Poza kontraktem nic nie wychodzi** — notatki i instrukcje z rejestru zostają na macu.
4. **`--pokaz` nie dotyka SF**, a 503 pokazuje treść serwera (brak tabel ≠ przeciążenie).

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, rejestr_floty  # noqa: E402
from sf_kit import config as konfiguracja  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402
from sf_kit.tozsamosc import Organizacja  # noqa: E402

#: Pola `WpisMigawki` w SF (backend/app/modules/agents/router.py @ aa153f28).
POLA_KONTRAKTU = {"slug", "nazwa", "rodzaj", "maszyna", "katalog", "aktywny"}

TERAZ = datetime(2026, 9, 24, 1, 30, tzinfo=timezone.utc)


def _wpis(ident, **pola):
    baza = {"id": ident, "name": ident.split("-")[0].title(), "model": "opus[1m]",
            "hostname": "localhost", "location": "localhost", "status": "active",
            "instructions": "TAJNE-INSTRUKCJE", "notes": "notatka wewnętrzna"}
    baza.update(pola)
    return baza


def _rejestr(*wpisy):
    return {"_version": "2.0.0", "agents": list(wpisy)}


KOPIA_SF = {"email": "codex_2@dpakula.pl", "agent_slug": "codex-2-dpakula",
            "tenant": "advertpro-co"}


class TestSlug(unittest.TestCase):

    def test_sf_agent_slug_wygrywa_z_id(self):
        m = rejestr_floty.zbuduj(_rejestr(_wpis("kimi-mac-dpakula", sf_agent_slug="kimi-mac")),
                                 teraz=TERAZ)
        self.assertEqual(m.cialo["agenci"][0]["slug"], "kimi-mac")
        self.assertEqual(m.pochodzenie, [("kimi-mac-dpakula", "kimi-mac", "sf_agent_slug")])

    def test_bez_sf_agent_slug_bierzemy_id(self):
        m = rejestr_floty.zbuduj(_rejestr(_wpis("borys-sf")), teraz=TERAZ)
        self.assertEqual(m.cialo["agenci"][0]["slug"], "borys-sf")

    def test_skopiowany_obiekt_sf_NIE_jest_zrodlem_sluga_tylko_ostrzezeniem(self):
        """Stan prawdziwego rejestru z 24.09: `sf` skopiowany z Kodeksa do wpisów Kimi."""
        m = rejestr_floty.zbuduj(_rejestr(
            _wpis("kodeks-dpakula", sf=KOPIA_SF, runtime="codex-cli", model="codex"),
            _wpis("kimi-mac-dpakula", sf=KOPIA_SF, sf_agent_slug="kimi-mac", model="kimi"),
            _wpis("kimi-autor", sf=KOPIA_SF, sf_agent_slug="kimi-autor-dpakula", model="kimi"),
        ), teraz=TERAZ)
        slugi = [a["slug"] for a in m.cialo["agenci"]]
        self.assertEqual(slugi, ["kodeks-dpakula", "kimi-mac", "kimi-autor-dpakula"])
        self.assertNotIn("codex-2-dpakula", slugi)
        self.assertEqual(len([o for o in m.ostrzezenia if "sf.agent_slug" in o]), 3)

    def test_zgodny_obiekt_sf_bez_ostrzezenia(self):
        m = rejestr_floty.zbuduj(_rejestr(
            _wpis("kimi-mac-dpakula", sf_agent_slug="kimi-mac",
                  sf={"agent_slug": "kimi-mac"}, model="kimi")), teraz=TERAZ)
        self.assertEqual(m.ostrzezenia, [])

    def test_drugi_wpis_z_tym_samym_slugiem_pominiety_i_nazwany(self):
        m = rejestr_floty.zbuduj(_rejestr(
            _wpis("kimi-mac-dpakula", sf_agent_slug="kimi-mac", model="kimi"),
            _wpis("kimi-mac-stary", sf_agent_slug="kimi-mac", model="kimi")), teraz=TERAZ)
        self.assertEqual(len(m.cialo["agenci"]), 1)
        self.assertTrue(any("kimi-mac-stary" in o and "pominięty" in o for o in m.ostrzezenia))


class TestPola(unittest.TestCase):

    def test_cialo_ma_DOKLADNIE_pola_kontraktu(self):
        m = rejestr_floty.zbuduj(_rejestr(_wpis("borys-sf"), _wpis("x", status="retired")),
                                 teraz=TERAZ)
        for a in m.cialo["agenci"]:
            self.assertEqual(set(a), POLA_KONTRAKTU)
        self.assertEqual(set(m.cialo), {"agenci", "zrodlo", "zebrano_o"})

    def test_notatki_i_instrukcje_zostaja_na_macu(self):
        m = rejestr_floty.zbuduj(_rejestr(_wpis("borys-sf")), teraz=TERAZ)
        tekst = json.dumps(m.cialo, ensure_ascii=False)
        self.assertNotIn("TAJNE-INSTRUKCJE", tekst)
        self.assertNotIn("notatka wewnętrzna", tekst)

    def test_wycofany_idzie_z_aktywny_false_a_nie_znika(self):
        """„Cała lista, nie różnica" — brak wpisu i wpis wycofany to dwie różne rzeczy."""
        m = rejestr_floty.zbuduj(_rejestr(_wpis("klaudiusz-ovh", status="retired")),
                                 teraz=TERAZ)
        self.assertEqual(m.cialo["agenci"][0]["aktywny"], False)

    def test_provisioning_jest_aktywny(self):
        m = rejestr_floty.zbuduj(_rejestr(_wpis("kimi-sf-dpakula", status="provisioning")),
                                 teraz=TERAZ)
        self.assertTrue(m.cialo["agenci"][0]["aktywny"])

    def test_maszyna_localhost_zastapiona_lokalizacja(self):
        m = rejestr_floty.zbuduj(_rejestr(
            _wpis("kimi-mac-dpakula", location="mac-damian"),
            _wpis("borys-sf", hostname="vps-b5c3dac1.vps.ovh.net", location="ssh")),
            teraz=TERAZ)
        self.assertEqual([a["maszyna"] for a in m.cialo["agenci"]],
                         ["mac-damian", "vps-b5c3dac1.vps.ovh.net"])

    def test_katalog_z_agent_home_potem_claude_home(self):
        m = rejestr_floty.zbuduj(_rejestr(
            _wpis("a", agent_home="~/homes/a", claude_home="/x/.claude"),
            _wpis("b", claude_home="/y/.claude")), teraz=TERAZ)
        self.assertEqual([a["katalog"] for a in m.cialo["agenci"]], ["~/homes/a", "/y/.claude"])

    def test_zrodlo_i_czas(self):
        m = rejestr_floty.zbuduj(_rejestr(_wpis("a")), teraz=TERAZ, nadawca="mac-damian")
        self.assertEqual(m.cialo["zrodlo"], "agents.json v2.0.0 z mac-damian")
        self.assertEqual(m.cialo["zebrano_o"], "2026-09-24T01:30:00+00:00")

    def test_zrodlo_miesci_sie_w_limicie_SF(self):
        m = rejestr_floty.zbuduj(_rejestr(_wpis("a")), teraz=TERAZ, nadawca="x" * 300)
        self.assertLessEqual(len(m.cialo["zrodlo"]), 120)


class TestRodzajSilnika(unittest.TestCase):

    def test_rodziny(self):
        przypadki = {
            ("opus[1m]", None): "claude",
            ("claude-fable-5-1[1m]", None): "claude",
            ("sonnet-4-5", None): "claude",
            ("haiku", None): "claude",
            ("codex", "codex-cli"): "codex",
            ("kimi", "kimi-cli"): "kimi",
        }
        for (model, runtime), oczekiwany in przypadki.items():
            with self.subTest(model=model):
                self.assertEqual(rejestr_floty.rodzaj_silnika(
                    {"model": model, "runtime": runtime}), oczekiwany)

    def test_niejednoznaczny_to_None_z_ostrzezeniem_nie_zgadywanie(self):
        self.assertIsNone(rejestr_floty.rodzaj_silnika({"model": "codex", "runtime": "kimi"}))
        m = rejestr_floty.zbuduj(_rejestr(_wpis("x", model="gpt-9")), teraz=TERAZ)
        self.assertIsNone(m.cialo["agenci"][0]["rodzaj"])
        self.assertTrue(any("silnika" in o for o in m.ostrzezenia))

    def test_prefiks_sluga_nie_decyduje(self):
        """`kimi-*` to konwencja nazw, nie silnik."""
        m = rejestr_floty.zbuduj(_rejestr(_wpis("kimi-cos", model="opus[1m]")), teraz=TERAZ)
        self.assertEqual(m.cialo["agenci"][0]["rodzaj"], "claude")


class TestWczytaj(unittest.TestCase):

    def _plik(self, tresc: str) -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        f.write(tresc)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_brak_pliku_mowi_gdzie_lezy_rejestr(self):
        with self.assertRaises(rejestr_floty.ZlyRejestr) as blad:
            rejestr_floty.wczytaj("/nie/ma/agents.json")
        self.assertIn("macu", str(blad.exception))

    def test_zly_json(self):
        with self.assertRaises(rejestr_floty.ZlyRejestr):
            rejestr_floty.wczytaj(self._plik("{nie json"))

    def test_json_bez_listy_agents(self):
        with self.assertRaises(rejestr_floty.ZlyRejestr):
            rejestr_floty.wczytaj(self._plik('{"agenci": []}'))


class _KlientAtrapa:
    def __init__(self, odpowiedz=None, blad=None):
        self.odpowiedz, self.blad, self.wyslane = odpowiedz, blad, None

    def zapisz_migawke_rejestru(self, cialo):
        self.wyslane = cialo
        if self.blad:
            raise self.blad
        return self.odpowiedz


class TestPolecenie(unittest.TestCase):

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._koordynator)
        katalog = tempfile.TemporaryDirectory()
        self.addCleanup(katalog.cleanup)
        self.plik = os.path.join(katalog.name, "agents.json")
        Path(self.plik).write_text(json.dumps(_rejestr(
            _wpis("borys-sf"), _wpis("kimi-mac-dpakula", sf_agent_slug="kimi-mac",
                                     model="kimi"))), encoding="utf-8")
        konfiguracja.wczytaj = lambda: konfiguracja.Konfiguracja(adres="https://x",
                                                                 organizacja="uuid-sf")

    def tearDown(self):
        konfiguracja.wczytaj, cli._koordynator = self._stare

    def _uruchom(self, *argv, klient=None):
        org = Organizacja(uuid="uuid-sf", slug="sf", nazwa="SF", uprawnienia=["x"])

        def _bez_sieci(*_a, **_k):
            if klient is None:
                raise AssertionError("polecenie sięgnęło do SF, choć nie powinno")
            return klient, org
        cli._koordynator = _bez_sieci
        wyjscie, bledy = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(wyjscie), contextlib.redirect_stderr(bledy):
            kod = cli.main(["flota", "rejestr", self.plik, *argv])
        return kod, wyjscie.getvalue(), bledy.getvalue()

    def test_pokaz_niczego_nie_wysyla(self):
        kod, wyjscie, _ = self._uruchom("--pokaz")
        self.assertEqual(kod, 0)
        self.assertIn('"slug": "kimi-mac"', wyjscie)
        self.assertIn("nic nie wysłałem", wyjscie)

    def test_wysylka_i_rozjazdy_pogrupowane(self):
        klient = _KlientAtrapa({"przyjeto": 2, "rozjazdy": [
            {"rodzaj": "rozjazd_nazwy", "slug": "borys-sf", "w_sf": "Borys", "lokalnie": "Arek",
             "szczegol": "ten sam slug, inna nazwa"},
            {"rodzaj": "tylko_sf", "slug": "wojt", "w_sf": "Wójt", "szczegol": "brak wpisu"}]})
        kod, wyjscie, _ = self._uruchom(klient=klient)
        self.assertEqual(kod, 0, "rozjazd to wiadomość, nie awaria wysyłki")
        self.assertEqual([a["slug"] for a in klient.wyslane["agenci"]], ["borys-sf", "kimi-mac"])
        self.assertIn("przyjął 2", wyjscie)
        self.assertIn("rozjazd_nazwy: 1, tylko_sf: 1", wyjscie)
        self.assertIn("lokalnie: Arek", wyjscie)

    def test_503_pokazuje_tresc_serwera(self):
        """Ogólne „odczekaj" przy braku tabel wysłałoby człowieka na fałszywy trop."""
        blad = BladAPI("serwer nie dał rady (PUT /flota/rejestr, 503)", kod=503,
                       szczegoly='{"detail":"brakuje tabel rewizji flota_koszty_rejestr_sf18"}')
        kod, _, bledy = self._uruchom(klient=_KlientAtrapa(blad=blad))
        self.assertEqual(kod, 1)
        self.assertIn("flota_koszty_rejestr_sf18", bledy)

    def test_404_bez_tresci_serwera_ale_z_kodem_1(self):
        """Stan produkcji 24.09: trasa niewdrożona → 404. Wysyłka ma się przyznać, że nie poszła."""
        blad = BladAPI("nie ma takiego obiektu (PUT /flota/rejestr, 404)", kod=404)
        kod, _, bledy = self._uruchom(klient=_KlientAtrapa(blad=blad))
        self.assertEqual(kod, 1)
        self.assertIn("NIE poszła", bledy)

    def test_zly_plik_kod_2_bez_siegania_do_SF(self):
        Path(self.plik).write_text("{}", encoding="utf-8")
        kod, _, bledy = self._uruchom()
        self.assertEqual(kod, 2)
        self.assertIn("agents", bledy)

    def test_gole_flota_dalej_woła_liste_agentow(self):
        """Podpolecenie jest opcjonalne — `sf-kit flota` bez niczego ma działać jak dotąd."""
        wywolane = []
        stare = cli.polecenie_flota
        cli.polecenie_flota = lambda args: wywolane.append(args) or 0
        try:
            # Parser wiąże funkcję przy budowie, więc sprawdzamy przez `main` po podmianie.
            self.assertEqual(cli.main(["flota"]), 0)
        finally:
            cli.polecenie_flota = stare
        self.assertEqual(len(wywolane), 1)


if __name__ == "__main__":
    unittest.main()
