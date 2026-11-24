"""Kit 0.21.0: `sf-kit tura zamknij` — zamknięcie tury koordynatora jednym poleceniem (SF-574).

v1.0.0 (24.11.2026) - APro Agents / arek-sf · SF-574

CZEGO PILNUJĄ
· stan: „## Następny krok” / „Następny krok: …” / --nastepny; „## Decyzje” z punktami, „brak” = jawnie zero decyzji.
· ślady decyzji: #blok, SPRAWA-N, link sprawy, „wpis <id>”; sprawdzane w SF → ok / nie_znaleziono / niesprawdzony / brak.
· kickoffy: tylko zadania założone przez MOJE konto, ze wszystkich Organizacji; bez adresu konta = problem, nie „wszystko”.
· otwarty krok: wpis zamykający (stan, następny krok, kickoffy, decyzje, pomiar) + closed → kod 0, jedna linia wyniku.
· zamknięty krok + praca po nim → nowy krok (POST /kroki/dzis) i to on dostaje stan + closed; bez pracy → dopisek, bez zmiany statusu.
· brak następnego kroku / pusty stan / --bez-decyzji z decyzjami / profil bez kroków → kod 2, ZERO zapisów.
· decyzja bez śladu albo brak sekcji decyzji → wszystko zapisane, kod 3 i „braki: …” w linii.
· SF odmawia wpisu → kod 1, a plik stanu i tak powstaje (drugie okno nie traci punktu wznowienia).
· lokalnie z ustawień: plik stanu, dziennik z {data}, commit tylko zapisanych plików (tryb `pliki`) albo `-A`; --sucho nic nie pisze.
· pomiar: bez wskazniki.py presja Organizacji z SF (`GET /tasks/presja`), pomiar nigdy nie wywraca tury.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, tura, ustawienia  # noqa: E402
from sf_kit import config as konfiguracja  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

KROK = "11111111-1111-4111-8111-111111111111"
NOWY = "22222222-2222-4222-8222-222222222222"
SPRAWA = "33333333-3333-4333-8333-333333333333"
JA = "agata@dpakula.pl"
TERAZ = datetime.now(timezone.utc)

STAN = """Robiłam: przegląd floty i SF-574.
Status: w toku.

## Następny krok
Sprawdzić bramkę Kita 0.21.0 u seweryna.

## Decyzje
- Damian: Kit 0.21.0 przez bramkę → #2458
- Damian: kolejność paczek → SF-574
- Damian: ustnie, bez śladu
"""


def iso(dt):
    return dt.isoformat()


class TestStan(unittest.TestCase):
    def test_sekcje(self):
        nastepny, decyzje = tura.rozbierz_stan(STAN)
        self.assertEqual(nastepny, "Sprawdzić bramkę Kita 0.21.0 u seweryna.")
        self.assertEqual(len(decyzje), 3)
        self.assertTrue(decyzje[0].startswith("Damian: Kit 0.21.0"))

    def test_linia_nastepny_i_brak_sekcji_decyzji(self):
        nastepny, decyzje = tura.rozbierz_stan("Zrobione X.\n**Następny krok:** wdrożyć Y\n")
        self.assertEqual(nastepny, "wdrożyć Y")
        self.assertIsNone(decyzje)

    def test_jawny_brak_decyzji(self):
        for tekst in ("## Decyzje\nbrak\n", "## Decyzje\n- brak\n", "## Decyzje\n(brak)\n"):
            with self.subTest(tekst):
                self.assertEqual(tura.rozbierz_stan(tekst)[1], [])

    def test_slady(self):
        self.assertEqual(tura.slady("A → #2458, SF-574, wpis 7FD59229"), ["#2458", "SF-574", "wpis 7fd59229"])
        self.assertEqual(tura.slady("link https://sales-forge.pl/tickets/numer/SF-574?org=sf."),
                         ["https://sales-forge.pl/tickets/numer/SF-574?org=sf"])
        self.assertEqual(tura.slady("KROK V, bez śladu"), [])

    def test_sprawdz_decyzje(self):
        d = tura.sprawdz_decyzje(
            ["A → #2458", "B → SF-1", "C → wpis 7fd59229", "D → #9999", "E bez"],
            jest_blok=lambda s: s == "#2458", jest_sprawa=lambda s: None)
        self.assertEqual([x.stan for x in d], ["ok", "niesprawdzony", "niesprawdzony", "nie_znaleziono", "brak"])
        self.assertEqual([x.ma_slad for x in d], [True, True, True, False, False])
        self.assertIn("#9999", d[3].uwaga)


class TestCzas(unittest.TestCase):
    def test_czas_bez_strefy_to_utc_i_porownywalny(self):
        self.assertEqual(tura.czas("2026-11-24T01:00:00").tzinfo, timezone.utc)
        k = mock.MagicMock()
        k.kroki_konsoli.return_value = [{"krok": {"id": KROK}, "bloki": [
            {"rodzaj": "action", "kiedy": "2026-11-24T02:00:00"},
            {"rodzaj": "rozstrzygniecie", "kiedy": "2026-11-24T02:00:00Z"},
            {"rodzaj": "info", "kiedy": "2026-11-24T00:30:00Z"}]}]
        po = tura.bloki_kroku_po(k, KROK, datetime(2026, 11, 24, 1, 0, tzinfo=timezone.utc))
        self.assertEqual([b["rodzaj"] for b in po], ["action"])

    def test_zamkniety_o_resolved_przed_updated(self):
        s = {"resolved_at": "2026-11-24T01:00:00Z", "updated_at": "2026-11-24T03:00:00Z"}
        self.assertEqual(tura.zamkniety_o(s).hour, 1)
        self.assertEqual(tura.zamkniety_o({"updated_at": "2026-11-24T03:00:00Z"}).hour, 3)


class TestKickoffy(unittest.TestCase):
    def test_tylko_moje_ze_wszystkich_org(self):
        a, b = mock.MagicMock(), mock.MagicMock()
        a.zadania_od.return_value = [{"external_id": "Z-1", "created_by": JA, "created_at": "2026-11-24T01:00:00Z"},
                                     {"external_id": "Z-2", "created_by": "inny@x.pl"}]
        b.zadania_od.side_effect = BladAPI("403")
        lista, problemy = tura.kickoffy([("sf", a), ("fm", b)], TERAZ, "AGATA@dpakula.pl")
        self.assertEqual([z["external_id"] for z in lista], ["Z-1"])
        self.assertEqual(lista[0]["_org"], "sf")
        self.assertEqual(len(problemy), 1)
        self.assertIn("fm", problemy[0])

    def test_bez_adresu_nie_ma_kickoffow(self):
        a = mock.MagicMock()
        lista, problemy = tura.kickoffy([("sf", a)], TERAZ, None)
        self.assertEqual(lista, [])
        a.zadania_od.assert_not_called()
        self.assertTrue(problemy)


class TestPomiar(unittest.TestCase):
    def test_bez_wskaznikow_presja_z_sf(self):
        k = mock.MagicMock()
        k.presja_zadan.return_value = {"razem": 12, "decide": {"wazona": 5}, "do": {"otwarte": 7}}
        with mock.patch.dict(os.environ, {"SF_KIT_WSKAZNIKI": "/nie/ma/wskazniki.py"}):
            linia, zrodlo = tura.pomiar(kto=None, wskazniki=None, klient=k)
        self.assertEqual(zrodlo, "sf")
        self.assertIn("presja Org 12", linia)

    def test_nic_nie_dziala_to_nd(self):
        k = mock.MagicMock()
        k.presja_zadan.side_effect = BladAPI("503")
        with mock.patch.dict(os.environ, {"SF_KIT_WSKAZNIKI": "/nie/ma/wskazniki.py"}):
            linia, zrodlo = tura.pomiar(kto=None, wskazniki=None, klient=k)
        self.assertEqual(zrodlo, "brak")
        self.assertTrue(linia.startswith("pomiar n/d"))


class TestUstawienia(unittest.TestCase):
    def test_tura_commit_tylko_dwie_wartosci(self):
        konf = konfiguracja.Konfiguracja()
        with self.assertRaises(ValueError):
            ustawienia.zmien_lokalne(konf, "tura_commit", "push")
        ustawienia.zmien_lokalne(konf, "tura_commit", "wszystko")
        self.assertEqual(konf.tura_commit, "wszystko")
        for klucz in ("rozgrywka", "tura_plik_stanu", "tura_dziennik", "tura_repo"):
            self.assertIn(klucz, ustawienia.LOKALNE)


class Atrapa:
    """Klient SF w zakresie, którego dotyka `tura zamknij`. Wszystkie Organizacje = ta sama atrapa."""

    def __init__(self, *, status="in_progress", zamkniety_o=None, zadania=(), bloki=(), blad_wpisu=False):
        self.organizacja = "org-sf"
        self.karty = {
            KROK: {"id": KROK, "ticket_prefix": "SF", "ticket_number": 600, "status": status,
                   "created_at": iso(TERAZ - timedelta(hours=3)),
                   "updated_at": iso(zamkniety_o or TERAZ - timedelta(hours=1)), "resolved_at": None},
            SPRAWA: {"id": SPRAWA, "ticket_prefix": "SF", "ticket_number": 574, "status": "in_progress",
                     "created_at": iso(TERAZ - timedelta(days=1))},
        }
        self._zadania, self._bloki, self.blad_wpisu = list(zadania), list(bloki), blad_wpisu
        self.wpisy, self.patche, self.nowe_kroki = [], [], []

    def w_organizacji(self, org):
        return self

    def sprawa(self, sid):
        return dict(self.karty[sid])

    def kroki_konsoli(self, *, dni=2):
        return [{"data": "2026-11-24", "krok": {"id": KROK, "numer": "SF-600"}, "bloki": self._bloki}]

    def zadania_od(self, od, *, limit=200):
        return [z for z in self._zadania if z["created_at"] >= od[:19]]

    def presja_zadan(self):
        return {"razem": 3, "decide": {"wazona": 1}, "do": {"otwarte": 2}}

    def wpis(self, sid, tresc, *, widocznosc="internal", w_odpowiedzi_do=None):
        if self.blad_wpisu:
            raise BladAPI("SF odmówił (500)")
        self.wpisy.append((sid, tresc, widocznosc))
        return {"id": "w1"}

    def zmien_sprawe(self, sid, cialo):
        self.patche.append((sid, cialo))
        self.karty[sid]["status"] = cialo.get("status", self.karty[sid]["status"])

    def krok_dzis(self, sedno):
        self.nowe_kroki.append(sedno)
        self.karty[NOWY] = {"id": NOWY, "ticket_prefix": "SF", "ticket_number": 601, "status": "open"}
        return {"id": NOWY, "numer": "SF-601", "utworzony": True}

    def bloki(self, **filtry):
        return [{"id": "b1", "numer": "#2458"}] if filtry.get("numer") == 2458 else []

    def sprawy(self, **kw):
        return [self.karty[SPRAWA]]


class TestPolecenie(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.rozgrywka = self.dir / "rozgrywka.json"
        self.rozgrywka.write_text(json.dumps({"ostatni_ticket_id": KROK}), encoding="utf-8")
        self.konf = konfiguracja.Konfiguracja(profil="koordynator", slug="agata", rozgrywka=str(self.rozgrywka))
        self.env = mock.patch.dict(os.environ, {"SF_KIT_WSKAZNIKI": str(self.dir / "brak.py")})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def uruchom(self, k, *argv, konf=None):
        org = SimpleNamespace(uuid="org-sf", slug="sf")
        toz = SimpleNamespace(konto_email=JA, z_nadaniami=[org], organizacje=[org])
        args = cli.zbuduj_parser().parse_args(["--org", "sf", "tura", "zamknij", *argv])
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(konfiguracja, "wczytaj", return_value=konf or self.konf), \
                mock.patch.object(cli, "_klient_dla_zapisu", return_value=(k, org)), \
                mock.patch.object(cli, "_tozsamosc", return_value=toz), \
                mock.patch.object(cli.asystent, "znajdz_sprawe",
                                  side_effect=lambda kl, s: kl.karty[SPRAWA] if s in ("SF-574", SPRAWA) else
                                  (_ for _ in ()).throw(ValueError("nie ma"))), \
                redirect_stdout(out), redirect_stderr(err):
            kod = args.funkcja(args)
        return kod, out.getvalue(), err.getvalue()

    def stan(self, tekst=STAN):
        p = self.dir / "stan.md"
        p.write_text(tekst, encoding="utf-8")
        return str(p)

    def test_otwarty_krok_wpis_i_closed(self):
        zadania = [{"external_id": "SF-574-T1", "assigned_agent_slug": "arek-sf", "title": "Kit tura",
                    "created_by": JA, "created_at": iso(TERAZ - timedelta(hours=2))}]
        k = Atrapa(zadania=zadania)
        kod, out, _ = self.uruchom(k, "--opis", self.stan(STAN.replace("- Damian: ustnie, bez śladu\n", "")))
        self.assertEqual(kod, 0, out)
        (sid, tresc, widocznosc), = k.wpisy
        self.assertEqual((sid, widocznosc), (KROK, "internal"))
        for fragment in ("**Następny krok:** Sprawdzić bramkę", "SF-574-T1 → arek-sf", "(2/2 ze śladem)",
                         "presja Org 3", "Robiłam: przegląd floty"):
            self.assertIn(fragment, tresc)
        self.assertEqual(k.patche, [(KROK, {"status": "closed"})])
        self.assertEqual(out.count("\n"), 1)
        self.assertTrue(out.startswith("zapisane: wpis SF-600, closed | następny krok: Sprawdzić bramkę"), out)

    def test_decyzja_bez_sladu_to_kod_3_ale_zapisane(self):
        k = Atrapa()
        kod, out, _ = self.uruchom(k, "--opis", self.stan())
        self.assertEqual(kod, 3)
        self.assertEqual(len(k.wpisy), 1)
        self.assertIn("✗ Damian: ustnie, bez śladu", k.wpisy[0][1])
        self.assertIn("braki: 1 decyzji bez śladu", out)

    def test_brak_sekcji_decyzji_to_brak(self):
        k = Atrapa()
        kod, out, _ = self.uruchom(k, "--tresc", "Zrobione X.", "--nastepny", "Y")
        self.assertEqual(kod, 3)
        self.assertIn("decyzje człowieka nie podane", out)
        kod, out, _ = self.uruchom(Atrapa(), "--tresc", "Zrobione X.", "--nastepny", "Y", "--bez-decyzji")
        self.assertEqual(kod, 0, out)

    def test_zle_wejscie_nic_nie_wysyla(self):
        for argv in (["--tresc", "Zrobione X, bez następnego kroku"],
                     ["--opis", str(self.dir / "nie-ma.md"), "--nastepny", "Y"],
                     ["--opis", self.stan(), "--bez-decyzji"]):
            with self.subTest(argv):
                k = Atrapa()
                kod, _, _ = self.uruchom(k, *argv)
                self.assertEqual(kod, 2)
                self.assertEqual((k.wpisy, k.patche, k.nowe_kroki), ([], [], []))

    def test_profil_bez_krokow_bez_sprawy_to_2(self):
        k = Atrapa()
        konf = konfiguracja.Konfiguracja(profil="asystent", slug="x")
        kod, _, err = self.uruchom(k, "--tresc", "X", "--nastepny", "Y", "--bez-decyzji", konf=konf)
        self.assertEqual(kod, 2)
        self.assertIn("--sprawa", err)
        self.assertEqual(k.wpisy, [])

    def test_sesja_asystenta_na_sprawie_bez_statusu(self):
        k = Atrapa()
        konf = konfiguracja.Konfiguracja(profil="asystent", slug="x")
        kod, out, _ = self.uruchom(k, "--sprawa", "SF-574", "--tresc", "X", "--nastepny", "Y", "--bez-decyzji",
                                   konf=konf)
        self.assertEqual(kod, 0, out)
        self.assertEqual(k.wpisy[0][0], SPRAWA)
        self.assertEqual(k.patche, [])

    def test_zamkniety_krok_z_praca_po_nim_dostaje_nowy_krok(self):
        zamk = TERAZ - timedelta(hours=1)
        zadania = [{"external_id": "Z-PO", "created_by": JA, "created_at": iso(TERAZ - timedelta(minutes=10)),
                    "title": "po zamknięciu"}]
        k = Atrapa(status="closed", zamkniety_o=zamk, zadania=zadania)
        kod, out, _ = self.uruchom(k, "--tresc", "Praca dalej.", "--nastepny", "Y", "--bez-decyzji")
        self.assertEqual(kod, 0, out)
        self.assertEqual(len(k.nowe_kroki), 1)
        self.assertIn("SF-600", k.nowe_kroki[0])
        self.assertEqual(k.wpisy[0][0], NOWY)
        self.assertIn("był już zamknięty", k.wpisy[0][1])
        self.assertEqual(k.patche, [(NOWY, {"status": "closed"})])
        self.assertIn("nowy krok SF-601", out)

    def test_zamkniety_krok_z_blokiem_po_nim_to_tez_praca(self):
        zamk = TERAZ - timedelta(hours=1)
        k = Atrapa(status="closed", zamkniety_o=zamk,
                   bloki=[{"rodzaj": "action", "kiedy": iso(TERAZ - timedelta(minutes=5))}])
        kod, _, _ = self.uruchom(k, "--tresc", "X", "--nastepny", "Y", "--bez-decyzji")
        self.assertEqual(kod, 0)
        self.assertEqual(len(k.nowe_kroki), 1)

    def test_zamkniety_krok_bez_pracy_dopisek(self):
        k = Atrapa(status="closed", zamkniety_o=TERAZ - timedelta(minutes=30),
                   bloki=[{"rodzaj": "action", "kiedy": iso(TERAZ - timedelta(hours=2))}])
        kod, _, _ = self.uruchom(k, "--tresc", "X", "--nastepny", "Y", "--bez-decyzji")
        self.assertEqual(kod, 0)
        self.assertEqual(k.nowe_kroki, [])
        self.assertEqual(k.wpisy[0][0], KROK)
        self.assertIn("nie wykryłem", k.wpisy[0][1])
        self.assertEqual(k.patche, [])

    def test_sf_odmawia_kod_1_a_plik_stanu_jest(self):
        k = Atrapa(blad_wpisu=True)
        stan_plik = self.dir / "drugie-okno" / "resume.md"
        kod, out, _ = self.uruchom(k, "--tresc", "X", "--nastepny", "Y", "--bez-decyzji",
                                   "--plik-stanu", str(stan_plik))
        self.assertEqual(kod, 1)
        self.assertTrue(stan_plik.is_file())
        self.assertIn("NASTĘPNY KROK: Y", stan_plik.read_text(encoding="utf-8"))
        self.assertIn("braki: SF:", out)
        self.assertEqual(k.patche, [])

    def test_sucho_nic_nie_zapisuje(self):
        k = Atrapa()
        stan_plik = self.dir / "resume.md"
        kod, out, _ = self.uruchom(k, "--tresc", "X", "--nastepny", "Y", "--bez-decyzji", "--sucho",
                                   "--plik-stanu", str(stan_plik))
        self.assertEqual(kod, 0)
        self.assertEqual((k.wpisy, k.patche, k.nowe_kroki), ([], [], []))
        self.assertFalse(stan_plik.exists())
        self.assertIn("--- plan ---", out)

    def test_lokalnie_stan_dziennik_commit(self):
        repo = self.dir / "dom"
        repo.mkdir()
        git = ["git", "-C", str(repo)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["config", "user.email", "t@t"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        (repo / "obcy.txt").write_text("nie moje", encoding="utf-8")
        konf = konfiguracja.Konfiguracja(
            profil="koordynator", slug="agata", rozgrywka=str(self.rozgrywka),
            tura_plik_stanu=str(repo / "stan" / "resume.md"), tura_dziennik=str(repo / "diary" / "{data}.md"),
            tura_repo=str(repo), tura_commit="pliki")
        kod, out, _ = self.uruchom(Atrapa(), "--tresc", "X", "--nastepny", "Y", "--bez-decyzji", konf=konf)
        self.assertEqual(kod, 0, out)
        dziennik = repo / "diary" / f"{datetime.now().astimezone():%Y-%m-%d}.md"
        self.assertIn("tura zamknięta (SF-600", dziennik.read_text(encoding="utf-8"))
        pliki = subprocess.run(git + ["show", "--name-only", "--format=%s", "HEAD"], capture_output=True,
                               text=True, check=True).stdout
        self.assertIn("tura: SF-600 zamknięta — następny krok: Y", pliki)
        self.assertIn("stan/resume.md", pliki)
        self.assertNotIn("obcy.txt", pliki)
        self.assertIn("commit ", out)
        # druga tura bez zmian w plikach stanu = nadal commit (dziennik rośnie), a „wszystko” bierze obcy plik
        konf.tura_commit = "wszystko"
        kod, out, _ = self.uruchom(Atrapa(), "--tresc", "X", "--nastepny", "Y", "--bez-decyzji", konf=konf)
        self.assertEqual(kod, 0, out)
        pliki = subprocess.run(git + ["show", "--name-only", "--format=%s", "HEAD"], capture_output=True,
                               text=True, check=True).stdout
        self.assertIn("obcy.txt", pliki)

    def test_plik_spoza_repo_pomijany_przy_commicie(self):
        repo = self.dir / "dom"
        repo.mkdir()
        git = ["git", "-C", str(repo)]
        subprocess.run(git + ["init", "-q"], check=True)
        subprocess.run(git + ["config", "user.email", "t@t"], check=True)
        subprocess.run(git + ["config", "user.name", "t"], check=True)
        konf = konfiguracja.Konfiguracja(
            profil="koordynator", slug="agata", rozgrywka=str(self.rozgrywka),
            tura_plik_stanu=str(self.dir / "poza" / "resume.md"), tura_dziennik=str(repo / "{data}.md"),
            tura_repo=str(repo))
        kod, out, _ = self.uruchom(Atrapa(), "--tresc", "X", "--nastepny", "Y", "--bez-decyzji", konf=konf)
        self.assertEqual(kod, 0, out)
        pliki = subprocess.run(git + ["show", "--name-only", "--format=", "HEAD"], capture_output=True,
                               text=True, check=True).stdout.split()
        self.assertEqual(pliki, [f"{datetime.now().astimezone():%Y-%m-%d}.md"])

    def test_zly_repo_to_brak_kod_3(self):
        konf = konfiguracja.Konfiguracja(profil="koordynator", slug="agata", rozgrywka=str(self.rozgrywka),
                                         tura_repo=str(self.dir / "nie-repo"))
        (self.dir / "nie-repo").mkdir()
        kod, out, _ = self.uruchom(Atrapa(), "--tresc", "X", "--nastepny", "Y", "--bez-decyzji", konf=konf)
        self.assertEqual(kod, 3)
        self.assertIn("braki: commit:", out)

    def test_json(self):
        kod, out, _ = self.uruchom(Atrapa(), "--tresc", "X", "--nastepny", "Y", "--bez-decyzji", "--json")
        dane = json.loads(out)
        self.assertEqual((kod, dane["ok"], dane["krok"]["numer"]), (0, True, "SF-600"))
        self.assertIn("następny krok: Y", dane["linia"])

    def test_bez_rozgrywki_najnowszy_krok_z_sf(self):
        self.rozgrywka.write_text(json.dumps({"ostatni_ticket_id": None}), encoding="utf-8")
        k = Atrapa()
        kod, _, err = self.uruchom(k, "--tresc", "X", "--nastepny", "Y", "--bez-decyzji")
        self.assertEqual(kod, 0)
        self.assertIn("najnowszy krok w sf", err)
        self.assertEqual(k.wpisy[0][0], KROK)


if __name__ == "__main__":
    unittest.main()
