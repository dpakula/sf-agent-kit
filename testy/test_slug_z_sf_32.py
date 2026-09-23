"""Slug z SF, a nie z nazwy katalogu (SF-32, ADVERTPR-918).

v0.1 (24.09.2026) - APro Agents / borys-sf

CO SIĘ STAŁO
Konto Kimi-mac ma w SF slug `kimi-mac`, a `sf-kit init` na macu zapisał `kimi-mac-dpakula`
(konwencja z VPS). Worker odsiewa zadania po slugu z ustawień, więc widział „0 zadań",
a `whoami` obok pokazywał działające konto. Do 0.8.0 jedno pole `slug` znaczyło dwie rzeczy:
nazwę na tej maszynie (katalog, usługa, tętno) i slug w SF (filtr zadań).

CZEGO TU PILNUJEMY
1. `init` zapisuje slug z `GET /me`, a katalog i usługa zostają pod nazwą lokalną.
2. Ponowny `init` z Enterem nie przenosi ustawień do katalogu nazwanego slugiem z SF.
3. Worker z rozjechanym slugiem ODMAWIA startu — i nie woła pętli.
4. `usluga` generuje `--agent <nazwa lokalna>`, bo tylko ona trafia w katalog ustawień.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import builtins
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, klucz, tozsamosc  # noqa: E402
from sf_kit import config as konfiguracja  # noqa: E402
from sf_kit.tozsamosc import Organizacja, Tozsamosc  # noqa: E402
import sf_kit.worker as worker  # noqa: E402


def _org(slug_org="sf", agent_slug="kimi-mac", prawa=("tickets:read",)):
    return Organizacja(uuid=f"uuid-{slug_org}", slug=slug_org, nazwa=slug_org.upper(),
                       agent_slug=agent_slug, uprawnienia=list(prawa))


def _toz(*organizacje):
    return Tozsamosc(konto_nazwa="Kimi", konto_kind="agent", klucz_prefiks="sk_live_x",
                     klucz_scope="member", klucz_zawezony=True, organizacje=list(organizacje))


def _me(*organizacje):
    """Odpowiedź `GET /me` w kształcie z SF (klucze jak w `tozsamosc.z_odpowiedzi`)."""
    return {"konto": {"nazwa": "Kimi", "kind": "agent"},
            "klucz": {"prefiks": "sk_live_x", "scope": "member", "zawezony": True},
            "organizacje": [{"tenant_uuid": o.uuid, "slug": o.slug, "nazwa": o.nazwa,
                             "agent_slug": o.agent_slug,
                             "uprawnienia_efektywne": o.uprawnienia} for o in organizacje]}


class MaszynaTestowa:
    """`~/.config/sf-kit` w katalogu tymczasowym. Opcjonalnie z gotowym agentem."""

    def __init__(self, agent: str | None = None, slug: str | None = None):
        self.katalog = tempfile.TemporaryDirectory()
        self.korzen = Path(self.katalog.name) / "sf-kit"
        if agent:
            (self.korzen / agent).mkdir(parents=True)
            (self.korzen / agent / "config.json").write_text(
                json.dumps({"slug": slug or agent, "runtime": "kimi"}), encoding="utf-8")

    def __enter__(self):
        self._xdg = os.environ.get("XDG_CONFIG_HOME")
        self._dom = os.environ.pop(klucz.ZMIENNA_DOMU, None)
        os.environ["XDG_CONFIG_HOME"] = self.katalog.name
        klucz.ustaw_agenta(None)
        return self

    def __exit__(self, *_):
        klucz.ustaw_agenta(None)
        if self._xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._xdg
        if self._dom is not None:
            os.environ[klucz.ZMIENNA_DOMU] = self._dom
        self.katalog.cleanup()

    def ustawienia(self, agent: str) -> dict:
        return json.loads((self.korzen / agent / "config.json").read_text(encoding="utf-8"))


class TestSlugWSf(unittest.TestCase):

    def test_wskazana_organizacja_daje_jej_slug(self):
        toz = _toz(_org("sf", "kimi-mac"), _org("autera", "kimi-inny"))
        self.assertEqual(tozsamosc.slug_w_sf(toz, "autera"), "kimi-inny")

    def test_bez_wskazania_wspolny_slug(self):
        toz = _toz(_org("sf", "kimi-mac"), _org("autera", "kimi-mac"))
        self.assertEqual(tozsamosc.slug_w_sf(toz), "kimi-mac")

    def test_bez_wskazania_rozne_slugi_to_brak_odpowiedzi(self):
        """Slug siedzi na członkostwie — przy dwóch różnych nie wybieramy za człowieka."""
        toz = _toz(_org("sf", "kimi-mac"), _org("autera", "kimi-inny"))
        self.assertIsNone(tozsamosc.slug_w_sf(toz))

    def test_organizacja_bez_nadan_nie_glosuje(self):
        toz = _toz(_org("sf", "kimi-mac"), _org("autera", "kimi-inny", prawa=()))
        self.assertEqual(tozsamosc.slug_w_sf(toz), "kimi-mac")


class TestRozjazd(unittest.TestCase):

    def test_zgodny_slug_to_brak_rozjazdu(self):
        self.assertIsNone(tozsamosc.rozjazd_sluga("kimi-mac", _org(agent_slug="kimi-mac")))

    def test_rozny_slug_nazywa_oba(self):
        zdanie = tozsamosc.rozjazd_sluga("kimi-mac-dpakula", _org(agent_slug="kimi-mac"))
        self.assertIn("kimi-mac-dpakula", zdanie)
        self.assertIn("„kimi-mac”", zdanie)

    def test_czlonkostwo_bez_sluga_to_nie_rozjazd(self):
        """Nie ma z czym porównać — odmowa zatrzymałaby workera bez powodu."""
        self.assertIsNone(tozsamosc.rozjazd_sluga("cokolwiek", _org(agent_slug=None)))


class TestNazwaLokalna(unittest.TestCase):

    def test_nazwa_lokalna_to_katalog_nie_slug(self):
        """Stan maca po ręcznej poprawce: katalog `kimi-mac-dpakula`, slug `kimi-mac`."""
        with MaszynaTestowa(agent="kimi-mac-dpakula", slug="kimi-mac"):
            self.assertEqual(klucz.nazwa_lokalna("kimi-mac"), "kimi-mac-dpakula")

    def test_SF_KIT_HOME_oddaje_zapasowa(self):
        with MaszynaTestowa(), tempfile.TemporaryDirectory() as dom:
            os.environ[klucz.ZMIENNA_DOMU] = dom
            try:
                self.assertEqual(klucz.nazwa_lokalna("kimi-mac"), "kimi-mac")
            finally:
                os.environ.pop(klucz.ZMIENNA_DOMU, None)


class TestInit(unittest.TestCase):
    """Cały `init` z podmienionym wejściem, magazynem klucza i SF."""

    def _init(self, odpowiedzi: list[str], me: dict, agent_z_flagi=None) -> tuple[int, str]:
        wejscia = iter(odpowiedzi)

        class KlientAtrapa:
            def __init__(self, **_k):
                pass

            def kim_jestem(self):
                return me

        stare = (builtins.input, cli.Klient, klucz.zapytaj_i_zapisz, klucz.wczytaj,
                 cli._wlacz_ochrone_repozytorium)
        builtins.input = lambda _p="": next(wejscia)
        cli.Klient = KlientAtrapa
        klucz.zapytaj_i_zapisz = lambda: ("sk_live_…abcd", "atrapa")
        klucz.wczytaj = lambda: "sk_live_atrapa"
        cli._wlacz_ochrone_repozytorium = lambda: None

        class Argumenty:
            agent = agent_z_flagi

        bledy = io.StringIO()
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(bledy):
                kod = cli.polecenie_init(Argumenty())
        finally:
            (builtins.input, cli.Klient, klucz.zapytaj_i_zapisz, klucz.wczytaj,
             cli._wlacz_ochrone_repozytorium) = stare
        return kod, bledy.getvalue()

    def test_init_zapisuje_slug_z_SF_a_katalog_zostaje_pod_nazwa_lokalna(self):
        """Dokładnie przypadek z ADVERTPR-918."""
        with MaszynaTestowa() as m:
            # nazwa, profil, adres, katalog roboczy, wykonawca
            kod, bledy = self._init(["kimi-mac-dpakula", "", "", "", "kimi"],
                                    _me(_org("sf", "kimi-mac")))
            self.assertEqual(kod, 0)
            ustawienia = m.ustawienia("kimi-mac-dpakula")
        self.assertEqual(ustawienia["slug"], "kimi-mac")
        self.assertEqual(ustawienia["organizacja"], "uuid-sf")
        self.assertIn("UWAGA", bledy)
        self.assertIn("kimi-mac-dpakula", bledy)

    def test_ponowny_init_z_Enterem_nie_przenosi_ustawien(self):
        """Podpowiedź nazwy = katalog. Gdyby była polem `slug`, Enter przeniósłby ustawienia
        do `kimi-mac/`, a usługa launchd dalej wołałaby `--agent kimi-mac-dpakula`."""
        with MaszynaTestowa(agent="kimi-mac-dpakula", slug="kimi-mac") as m:
            kod, _ = self._init(["", "", "", "", ""], _me(_org("sf", "kimi-mac")))
            self.assertEqual(kod, 0)
            self.assertEqual(klucz.agenci(), ["kimi-mac-dpakula"])
            self.assertEqual(m.ustawienia("kimi-mac-dpakula")["slug"], "kimi-mac")

    def test_zgodna_nazwa_bez_ostrzezenia(self):
        with MaszynaTestowa() as m:
            kod, bledy = self._init(["kimi-mac", "", "", "", "kimi"],
                                    _me(_org("sf", "kimi-mac")))
            self.assertEqual(kod, 0)
            self.assertEqual(m.ustawienia("kimi-mac")["slug"], "kimi-mac")
        self.assertNotIn("UWAGA", bledy)


class _Doszlo(Exception):
    pass


class TestWorkerOdmawia(unittest.TestCase):

    def setUp(self):
        self._stare = (konfiguracja.wczytaj, cli._klient_i_organizacja, worker.uruchom)

    def tearDown(self):
        konfiguracja.wczytaj, cli._klient_i_organizacja, worker.uruchom = self._stare

    def _worker(self, slug_w_ustawieniach: str, org: Organizacja):
        konf = konfiguracja.Konfiguracja(adres="https://x", organizacja=org.uuid,
                                         slug=slug_w_ustawieniach, runtime="codex")
        konfiguracja.wczytaj = lambda: konf
        cli._klient_i_organizacja = lambda *_a, **_k: (object(), org)

        def _podniesc(*_a, **_k):
            raise _Doszlo()
        worker.uruchom = _podniesc

        class Argumenty:
            runtime = None
            interval = None
            once = True
        return cli.polecenie_worker(Argumenty())

    def test_rozjechany_slug_to_odmowa_PRZED_petla(self):
        with self.assertRaises(SystemExit) as odmowa:
            self._worker("kimi-mac-dpakula", _org(agent_slug="kimi-mac"))
        tresc = str(odmowa.exception)
        self.assertIn("nie startuje", tresc)
        self.assertIn('"slug": "kimi-mac"', tresc, "odmowa ma mówić, co wpisać")

    def test_zgodny_slug_dochodzi_do_petli(self):
        with self.assertRaises(_Doszlo):
            self._worker("kimi-mac", _org(agent_slug="kimi-mac"))

    def test_czlonkostwo_bez_sluga_dochodzi_do_petli(self):
        with self.assertRaises(_Doszlo):
            self._worker("kimi-mac", _org(agent_slug=None))


class TestUsluga(unittest.TestCase):

    def _usluga(self, system: str) -> str:
        class Argumenty:
            pokaz = True
        Argumenty.system = system
        wyjscie = io.StringIO()
        with contextlib.redirect_stdout(wyjscie):
            self.assertEqual(cli.polecenie_usluga(Argumenty()), 0)
        return wyjscie.getvalue()

    def test_usluga_wola_agenta_po_NAZWIE_LOKALNEJ(self):
        """Po ręcznej poprawce na macu (`slug: kimi-mac`) `--agent kimi-mac` nie trafiłby
        w żaden katalog ustawień."""
        with MaszynaTestowa(agent="kimi-mac-dpakula", slug="kimi-mac"):
            plist = self._usluga("macos")
            unit = self._usluga("linux")
        self.assertIn("<string>kimi-mac-dpakula</string>", plist)
        self.assertIn("pl.dpakula.sf-kit.worker.kimi-mac-dpakula", plist)
        self.assertNotIn("<string>kimi-mac</string>", plist)
        self.assertIn("--agent kimi-mac-dpakula worker", unit)


if __name__ == "__main__":
    unittest.main()
