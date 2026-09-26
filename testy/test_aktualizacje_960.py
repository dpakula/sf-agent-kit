"""Aktualizacje Kita: sprawdzanie raz na dobę, `sf-kit update`, auto_update (ADVERTPR-960).

v0.1 (25.09.2026) - APro Agents / kimi-autor

Serwer SF jest zamockowany ZGODNIE Z KONTRAKTEM z wpisu z 25.09 23:2x: `GET /kit/version`
oddaje `latest`, `min`, `tag`, `commit`, `breaking` itd. na każdym ważnym kluczu. Git
makieta nie wywołuje prawdziwego gita — `aktualizacje.aktualizuj` przyjmuje repo jako
parametr dokładnie po to, żeby tu wstrzyknąć atrapę.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import aktualizacje  # noqa: E402
from sf_kit.api import BladAPI  # noqa: E402

WERSJA = aktualizacje.WERSJA
CZESCI = [int(c) for c in WERSJA.split(".")]
# Kontraktowy przykład: na Kicie 0.13.2 najnowsza to 0.13.3 (poprawka), min 0.13.0.
PATCH_NOWSZY = f"{CZESCI[0]}.{CZESCI[1]}.{CZESCI[2] + 1}"
MINOR_NOWSZY = f"{CZESCI[0]}.{CZESCI[1] + 1}.0"
MINIMALNA = WERSJA  # „min” równe naszej wersji = nie jesteśmy poniżej minimum

TERAZ = 1_700_000_000.0
DZIEN = aktualizacje.SWIEZOSC_S


def info_sf(*, latest=PATCH_NOWSZY, min_=MINIMALNA, tag=None, commit=None, breaking=False):
    """Ciało odpowiedzi `GET /kit/version` z kontraktu."""
    return {
        "latest": latest,
        "min": min_,
        "tag": tag or f"v{latest}",
        "commit": commit or "a" * 40,
        "released_at": "2026-09-25T12:00:00Z",
        "notes_url": "https://github.com/dpakula/sf-agent-kit/releases/tag/"
                     + (tag or f"v{latest}"),
        "breaking": breaking,
    }


class AtrapaKlienta:
    """Klient, który zamiast pytać SF zwraca przygotowaną odpowiedź (albo rzuca BladAPI)."""

    def __init__(self, odpowiedz=None, blad=None):
        self.odpowiedz = odpowiedz
        self.blad = blad
        self.zapytan = 0

    def wersja_kita(self):
        self.zapytan += 1
        if self.blad:
            raise self.blad
        return self.odpowiedz


class AtrapaRepo:
    """Atrapa klonu gita: zapamiętuje wywołania, nie wywołuje prawdziwego `git`."""

    def __init__(self, *, brudne=None, head="stary-head", head_po_przejsciu=None,
                 dziennik="abc1234 jedna zmiana\nabc1235 druga zmiana",
                 tag_wskazuje=None, brak_tagu=False):
        self.brudne = brudne or []
        self._head = head
        self.head_po_przejsciu = head_po_przejsciu or head
        self._dziennik = dziennik
        self.tag_wskazuje = tag_wskazuje   # commit, na który wskazuje tag; None = zgadza się z SF
        self.brak_tagu = brak_tagu
        self.checkoutowano = []            # COMMITY (B1: checkout --detach <commit>), nie tagi
        self.weryfikowano = []             # (tag, commit) — potwierdz_zgodnosc
        self.tagi_pobrano = False
        self.dziennik_od = None

    def brudne_pliki(self):
        return list(self.brudne)

    def pobierz_tagi(self):
        self.tagi_pobrano = True

    def head(self):
        return self._head

    def potwierdz_zgodnosc(self, tag, commit):
        """Atrapa `git rev-parse --verify <tag>^{commit}` (B1: PRZED checkoutem)."""
        self.weryfikowano.append((tag, commit))
        if self.brak_tagu:
            raise aktualizacje.BladAktualizacji(
                f"WERYFIKACJA NIE PRZESZŁA: po pobraniu tagów w repo nie ma tagu {tag}")
        wskazuje = self.tag_wskazuje or commit
        if wskazuje != commit:
            raise aktualizacje.BladAktualizacji(
                f"WERYFIKACJA NIE PRZESZŁA: w repo tag {tag} wskazuje na {wskazuje[:12]}, "
                f"a SF wymaga {commit[:12]}.")

    def przejdz_na(self, commit):
        self.checkoutowano.append(commit)
        self._head = self.head_po_przejsciu

    def dziennik_zmian(self, od_sha, do_sha):
        self.dziennik_od = (od_sha, do_sha)
        return self._dziennik


class KonfiguracjaFake:
    def __init__(self, *, profil="worker", auto_update="patch"):
        self.profil = profil
        self.auto_update = auto_update


class TestPorownywaniaWersji(unittest.TestCase):

    def test_kolejnosc_semantyczna_nie_napisowa(self):
        self.assertEqual(aktualizacje.porownaj_wersje("0.13.2", "0.13.10"), -1)
        self.assertEqual(aktualizacje.porownaj_wersje("0.13.10", "0.13.9"), 1)
        self.assertEqual(aktualizacje.porownaj_wersje("0.13.2", "0.13.2"), 0)

    def test_v_prefiks_i_krotsze_zapisy(self):
        self.assertEqual(aktualizacje.porownaj_wersje("v0.13.2", "0.13.2"), 0)
        self.assertEqual(aktualizacje.porownaj_wersje("0.13", "0.13.0"), 0)
        self.assertEqual(aktualizacje.porownaj_wersje("0.13.0-rc1", "0.13.0"), 0)

    def test_ten_sam_minor(self):
        self.assertTrue(aktualizacje.ten_sam_minor("0.13.2", "0.13.9"))
        self.assertFalse(aktualizacje.ten_sam_minor("0.13.9", "0.14.0"))
        self.assertFalse(aktualizacje.ten_sam_minor("0.13.9", "1.0.0"))


class TestSprawdzanieWersjiCache(unittest.TestCase):

    def setUp(self):
        self.katalog = tempfile.TemporaryDirectory()
        self.plik = Path(self.katalog.name) / "aktualizacje.json"

    def tearDown(self):
        self.katalog.cleanup()

    def _pamiec(self, **pola):
        self.plik.write_text(json.dumps(pola), encoding="utf-8")

    def test_swieza_pamiec_nie_pyta_serwera(self):
        self._pamiec(sprawdzono_o=TERAZ, **info_sf())
        kl = AtrapaKlienta(blad=BladAPI("nie powinno pytać"))
        wynik = aktualizacje.sprawdz_wersje(kl, teraz=TERAZ, plik=self.plik)
        self.assertEqual(kl.zapytan, 0)
        self.assertEqual(wynik["latest"], PATCH_NOWSZY)

    def test_stara_pamiec_pyta_serwer_i_odswieza(self):
        self._pamiec(sprawdzono_o=TERAZ - DZIEN - 1, **info_sf(latest=WERSJA))
        kl = AtrapaKlienta(odpowiedz=info_sf())
        wynik = aktualizacje.sprawdz_wersje(kl, teraz=TERAZ, plik=self.plik)
        self.assertEqual(kl.zapytan, 1)
        self.assertEqual(wynik["latest"], PATCH_NOWSZY)
        zapisane = json.loads(self.plik.read_text(encoding="utf-8"))
        self.assertGreaterEqual(zapisane["sprawdzono_o"], TERAZ)

    def test_blad_sf_cichnie_i_ustawia_przerwe(self):
        kl = AtrapaKlienta(blad=BladAPI("padnięty SF"))
        self.assertIsNone(aktualizacje.sprawdz_wersje(kl, teraz=TERAZ, plik=self.plik))
        kl2 = AtrapaKlienta(odpowiedz=info_sf())
        wynik = aktualizacje.sprawdz_wersje(kl2, teraz=TERAZ + 60, plik=self.plik)
        self.assertEqual(kl2.zapytan, 0, "w przerwie po błędzie nie pytamy ponownie")
        self.assertIsNone(wynik)
        kl3 = AtrapaKlienta(odpowiedz=info_sf())
        aktualizacje.sprawdz_wersje(kl3, teraz=TERAZ + 3601, plik=self.plik)
        self.assertEqual(kl3.zapytan, 1, "po przerwie pytamy znowu")

    def test_brak_pamieci_zapisuje_odpowiedz(self):
        kl = AtrapaKlienta(odpowiedz=info_sf())
        aktualizacje.sprawdz_wersje(kl, teraz=TERAZ, plik=self.plik)
        zapisane = json.loads(self.plik.read_text(encoding="utf-8"))
        self.assertEqual(zapisane["tag"], f"v{PATCH_NOWSZY}")
        self.assertEqual(zapisane["commit"], "a" * 40)


class TestOstrzezeniaPrzedPoleceniem(unittest.TestCase):

    def setUp(self):
        self.katalog = tempfile.TemporaryDirectory()
        self.plik = Path(self.katalog.name) / "aktualizacje.json"

    def tearDown(self):
        self.katalog.cleanup()

    def _pamiec(self, **pola):
        self.plik.write_text(json.dumps(pola), encoding="utf-8")

    def test_nowy_kit_jedna_linia_raz_na_dobe(self):
        kl = AtrapaKlienta(odpowiedz=info_sf())
        linia = aktualizacje.ostrzezenie_przed_poleceniem(kl, teraz=TERAZ, plik=self.plik)
        self.assertEqual(linia, f"Dostępny Kit {PATCH_NOWSZY} — sf-kit update")
        self.assertIsNone(aktualizacje.ostrzezenie_przed_poleceniem(
            AtrapaKlienta(odpowiedz=info_sf()), teraz=TERAZ + 60, plik=self.plik),
            "tego samego dnia linia ma się NIE powtarzać")
        nastepna = aktualizacje.ostrzezenie_przed_poleceniem(
            AtrapaKlienta(odpowiedz=info_sf()), teraz=TERAZ + DZIEN, plik=self.plik)
        self.assertIsNotNone(nastepna, "następnego dnia linia wraca")

    def test_jestes_na_biezaco_cisza(self):
        kl = AtrapaKlienta(odpowiedz=info_sf(latest=WERSJA))
        self.assertIsNone(aktualizacje.ostrzezenie_przed_poleceniem(
            kl, teraz=TERAZ, plik=self.plik))

    def test_ponizej_minimalnej_ostrzezenie_przy_KAZDYM_poleceniu(self):
        kl = AtrapaKlienta(odpowiedz=info_sf(latest=PATCH_NOWSZY, min_=PATCH_NOWSZY))
        for i in range(3):
            linia = aktualizacje.ostrzezenie_przed_poleceniem(
                kl, teraz=TERAZ + i, plik=self.plik)
            self.assertIsNotNone(linia)
            self.assertIn("sf-kit update", linia)

    def test_breaking_ponizej_minimalnej_odmowa_z_instrukcja(self):
        kl = AtrapaKlienta(odpowiedz=info_sf(latest=MINOR_NOWSZY,
                                             min_=MINOR_NOWSZY, breaking=True))
        with self.assertRaises(aktualizacje.OdmowaPrzedPoleceniem) as ctx:
            aktualizacje.ostrzezenie_przed_poleceniem(kl, teraz=TERAZ, plik=self.plik)
        self.assertIn("sf-kit update", str(ctx.exception))

    def test_blad_sf_i_pusta_pamiec_cisza(self):
        kl = AtrapaKlienta(blad=BladAPI("brak sieci"))
        self.assertIsNone(aktualizacje.ostrzezenie_przed_poleceniem(
            kl, teraz=TERAZ, plik=self.plik))


def _starsza_od_zainstalowanej() -> str:
    """Wersja STARSZA od `WERSJA`, poprawna także dla `x.y.0`.

    Do 26.09 testy liczyły `patch - 1`, co przy wydaniu 0.14.0 dawało „0.14.-1" — napis
    spoza wzorca vX.Y.Z, więc Kit odmawiał jeszcze PRZED sprawdzaną ścieżką i trzy testy
    padały. Na gałęzi (0.13.4) błąd był niewidoczny; wyszedł dopiero przy podbiciu wersji.
    """
    major, minor, patch = (int(c) for c in WERSJA.split("."))
    if patch:
        return f"{major}.{minor}.{patch - 1}"
    if minor:
        return f"{major}.{minor - 1}.99"
    return f"{major - 1}.99.99"


class TestAktualizuj(unittest.TestCase):

    def test_juz_najnowsza_nie_rusza_gita(self):
        kl = AtrapaKlienta(odpowiedz=info_sf(latest=WERSJA))
        repo = AtrapaRepo()
        mowione = []
        self.assertFalse(aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append))
        self.assertFalse(repo.tagi_pobrano)
        self.assertEqual(repo.checkoutowano, [])

    def test_brudne_pliki_sledzone_odmowa_bez_checkoutu(self):
        kl = AtrapaKlienta(odpowiedz=info_sf())
        repo = AtrapaRepo(brudne=[" M sf_kit/wykonawcy.py"])
        mowione = []
        with self.assertRaises(aktualizacje.OdmowaAktualizacji) as ctx:
            aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append)
        self.assertIn("wykonawcy.py", str(ctx.exception))
        self.assertEqual(repo.checkoutowano, [], "brudne drzewo = żadnego checkoutu")

    def test_niesledzone_pliki_nie_blokuja(self):
        kl = AtrapaKlienta(odpowiedz=info_sf())
        # Brudne pliki: pusto — w realnym Repo nieśledzone (`??`) odpada w brudne_pliki()
        # (test wyżej, na prawdziwym klonie). Tu HEAD zgadza się z commit-em z SF.
        repo = AtrapaRepo(head="a" * 40, head_po_przejsciu="a" * 40)
        mowione = []
        self.assertTrue(aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append))
        self.assertEqual(repo.checkoutowano, ["a" * 40], "checkout --detach na COMMIT z SF")

    def test_szczesliwa_sciezka(self):
        info = info_sf(commit="b" * 40)
        kl = AtrapaKlienta(odpowiedz=info)
        repo = AtrapaRepo(head="a" * 40, head_po_przejsciu="b" * 40)
        mowione = []
        self.assertTrue(aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append))
        self.assertTrue(repo.tagi_pobrano)
        self.assertEqual(repo.weryfikowano, [(f"v{PATCH_NOWSZY}", "b" * 40)],
                         "zgodność tag↔commit sprawdzona PRZED checkoutem (B1)")
        self.assertEqual(repo.checkoutowano, ["b" * 40])
        self.assertEqual(repo.dziennik_od, ("a" * 40, "b" * 40))
        tekst = "\n".join(mowione)
        self.assertIn("jedna zmiana", tekst, "zmiany od obecnej wersji są pokazane")

    def test_tag_wskazuje_inny_commit_odmowa_PRZED_checkoutem(self):
        """B1/B2: rozjazd łapiemy PRZED zmianą — bez wycofywania, a komunikat pokazuje
        NIEZGODNY commit (to z repo), nie stary HEAD."""
        info = info_sf(commit="c" * 40)
        kl = AtrapaKlienta(odpowiedz=info)
        repo = AtrapaRepo(head="a" * 40, tag_wskazuje="b" * 40)  # tag ≠ commit z SF
        mowione = []
        with self.assertRaises(aktualizacje.BladAktualizacji) as ctx:
            aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append)
        self.assertEqual(repo.checkoutowano, [], "przy rozjazdzie NIE MA checkoutu (B1)")
        komunikat = str(ctx.exception)
        self.assertIn("WERYFIKACJA", komunikat)
        self.assertIn("b" * 12, komunikat, "komunikat pokazuje commit z repo (B2)")
        self.assertIn("c" * 12, komunikat, "komunikat pokazuje wymagany commit z SF")
        self.assertNotIn("a" * 12, komunikat, "stary HEAD nie ma się komunikatu pojawiać (B2)")

    def test_tagu_brak_w_repo_odmowa_przed_checkoutem(self):
        info = info_sf(commit="c" * 40)
        kl = AtrapaKlienta(odpowiedz=info)
        repo = AtrapaRepo(brak_tagu=True)
        with self.assertRaises(aktualizacje.BladAktualizacji) as ctx:
            aktualizacje.aktualizuj(kl, repo=repo, mow=lambda s: None)
        self.assertEqual(repo.checkoutowano, [])
        self.assertIn("WERYFIKACJA", str(ctx.exception))

    def test_sf_wskazuje_STARSZA_wersje_nie_cofa(self):
        """7a z przeglądu: starsza wersja w SF ≠ „masz najnowszą" — i git zostaje nietknięty."""
        starsza = _starsza_od_zainstalowanej()
        kl = AtrapaKlienta(odpowiedz=info_sf(latest=starsza))
        repo = AtrapaRepo()
        mowione = []
        self.assertFalse(aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append))
        tekst = "\n".join(mowione)
        self.assertIn("starszą wersję", tekst)
        self.assertIn("nie cofam bez --force", tekst)
        self.assertNotIn("Masz najnowszą", tekst)
        self.assertFalse(repo.tagi_pobrano)

    def test_wymuszenie_pozwala_przejsc_na_starsze_wydanie(self):
        """7a: `--force` (tylko człowiek, nigdy auto-patch) zgadza się na cofnięcie
        wersji — weryfikacja z SF i tak przechodzi PRZED checkoutem (B1)."""
        starsza = _starsza_od_zainstalowanej()
        info = info_sf(latest=starsza, commit="d" * 40)
        kl = AtrapaKlienta(odpowiedz=info)
        repo = AtrapaRepo(head="e" * 40, head_po_przejsciu="d" * 40)
        mowione = []
        self.assertTrue(aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append,
                                                wymusz=True))
        self.assertEqual(repo.weryfikowano, [(f"v{starsza}", "d" * 40)],
                         "zgodność tag↔commit sprawdzona tak samo jak przy zwykłym update")
        self.assertEqual(repo.checkoutowano, ["d" * 40])
        self.assertIn("Wymuszam", "\n".join(mowione))

    def test_auto_patch_nigdy_nie_wymusza(self):
        """Automatyczny patch workera nie przekazuje `wymusz` — starsze wydanie z SF
        zostawia maszynę nietkniętą (cofnięcie to decyzja człowieka)."""
        starsza = _starsza_od_zainstalowanej()
        kl = AtrapaKlienta(odpowiedz=info_sf(latest=starsza))
        repo = AtrapaRepo()
        mowione = []
        self.assertFalse(aktualizacje.aktualizuj(kl, repo=repo, mow=mowione.append))
        self.assertEqual(repo.checkoutowano, [])

    def test_tag_niezgodny_z_wzorcem_odmowa_przed_gitem(self):
        """B1: wartości z SF trafiają do gita — wzorce sprawdzamy lokalnie, bez cudzego
        polegania na walidacji serwera (napis od `-` byłby przez gita opcją)."""
        for zly_tag in ("--upload-pack=echo zle", "v0.13", "v0.13.3.1", "vX.Y.Z"):
            kl = AtrapaKlienta(odpowiedz=info_sf(tag=zly_tag))
            with self.assertRaises(aktualizacje.BladAktualizacji) as ctx:
                aktualizacje.aktualizuj(kl, repo=AtrapaRepo(), mow=lambda s: None)
            self.assertIn("tag", str(ctx.exception))

    def test_commit_niezgodny_z_wzorcem_odmowa_przed_gitem(self):
        for zly_commit in ("A" * 40, "g" * 40, "abc123", "a" * 39 + "-"):
            kl = AtrapaKlienta(odpowiedz=info_sf(commit=zly_commit))
            with self.assertRaises(aktualizacje.BladAktualizacji) as ctx:
                aktualizacje.aktualizuj(kl, repo=AtrapaRepo(), mow=lambda s: None)
            self.assertIn("commit", str(ctx.exception))

    def test_brak_wymaganego_pola_z_sf(self):
        zle = info_sf()
        del zle["commit"]
        kl = AtrapaKlienta(odpowiedz=zle)
        repo = AtrapaRepo()
        with self.assertRaises(aktualizacje.BladAktualizacji) as ctx:
            aktualizacje.aktualizuj(kl, repo=repo, mow=lambda s: None)
        self.assertIn("commit", str(ctx.exception))
        self.assertEqual(repo.checkoutowano, [])


class TestPokazStatus(unittest.TestCase):

    def setUp(self):
        self.katalog = tempfile.TemporaryDirectory()
        self.plik = Path(self.katalog.name) / "aktualizacje.json"

    def tearDown(self):
        self.katalog.cleanup()

    def test_check_pokazuje_wersje_i_zwraca_zero(self):
        kl = AtrapaKlienta(odpowiedz=info_sf())
        mowione = []
        kod = aktualizacje.pokaz_status(kl, mow=mowione.append, plik=self.plik)
        self.assertEqual(kod, 0)
        tekst = "\n".join(mowione)
        self.assertIn(WERSJA, tekst)
        self.assertIn(PATCH_NOWSZY, tekst)
        self.assertIn("sf-kit update", tekst)
        self.assertNotIn("pamięci podręcznej", tekst,
                         "przy żywym SF nie ma adnotacji o pamięci")

    def test_check_bez_sieci_i_pusta_pamiec_zglasza_blad(self):
        kl = AtrapaKlienta(blad=BladAPI("brak sieci"))
        with self.assertRaises(aktualizacje.BladAktualizacji):
            aktualizacje.pokaz_status(kl, mow=lambda s: None, plik=self.plik)

    def test_check_bez_sieci_z_pamieci_pokazuje_z_data(self):
        self.plik.write_text(json.dumps({"sprawdzono_o": TERAZ, **info_sf()}),
                             encoding="utf-8")
        kl = AtrapaKlienta(blad=BladAPI("brak sieci"))
        mowione = []
        self.assertEqual(aktualizacje.pokaz_status(kl, mow=mowione.append,
                                                   plik=self.plik), 0)
        self.assertIn("pamięci podręcznej", "\n".join(mowione),
                      "przy padniętym SF pokazujemy to, co wiemy, z datą")


class TestAutoPatch(unittest.TestCase):

    def setUp(self):
        self.katalog = tempfile.TemporaryDirectory()
        self.plik = Path(self.katalog.name) / "aktualizacje.json"
        self.konf = KonfiguracjaFake(profil="worker", auto_update="patch")

    def tearDown(self):
        self.katalog.cleanup()

    def _pamiec(self, **pola):
        self.plik.write_text(json.dumps(pola), encoding="utf-8")

    def test_wylaczone_nawet_gdy_nowy_patch(self):
        konf = KonfiguracjaFake(auto_update="off")
        kl = AtrapaKlienta(odpowiedz=info_sf())
        self.assertIsNone(aktualizacje.auto_patch(kl, konf, teraz=TERAZ,
                                                  plik=self.plik, mow=lambda s: None))
        self.assertEqual(kl.zapytan, 0, "przy off nie pytamy w ogóle")

    def test_tylko_profil_worker(self):
        konf = KonfiguracjaFake(profil="asystent", auto_update="patch")
        kl = AtrapaKlienta(odpowiedz=info_sf())
        repo = AtrapaRepo()
        self.assertIsNone(aktualizacje.auto_patch(kl, konf, teraz=TERAZ, repo=repo,
                                                  plik=self.plik, mow=lambda s: None))
        self.assertEqual(repo.checkoutowano, [])

    def test_nowy_patch_ten_sam_minor_kod_restartu(self):
        info = info_sf(commit="b" * 40)
        kl = AtrapaKlienta(odpowiedz=info)
        repo = AtrapaRepo(head="a" * 40, head_po_przejsciu="b" * 40)
        mowione = []
        kod = aktualizacje.auto_patch(kl, self.konf, teraz=TERAZ, repo=repo,
                                      mow=mowione.append, plik=self.plik)
        self.assertEqual(kod, aktualizacje.KOD_RESTARTU_PO_AKTUALIZACJI)
        self.assertEqual(repo.checkoutowano, ["b" * 40])

    def test_nowy_minor_czlowiek_nie_worker(self):
        kl = AtrapaKlienta(odpowiedz=info_sf(latest=MINOR_NOWSZY))
        repo = AtrapaRepo()
        mowione = []
        kod = aktualizacje.auto_patch(kl, self.konf, teraz=TERAZ, repo=repo,
                                      mow=mowione.append, plik=self.plik)
        self.assertIsNone(kod)
        self.assertEqual(repo.checkoutowano, [], "minor NIE aktualizuje się sam")
        self.assertTrue(any("człowiek" in m for m in mowione),
                        "worker mówi, kto instaluje większe wydanie")

    def test_nieudana_proba_cofniecie_o_6h(self):
        kl = AtrapaKlienta(odpowiedz=info_sf())
        repo = AtrapaRepo(brudne=[" M sf_kit/cos.py"])
        mowione = []
        self.assertIsNone(aktualizacje.auto_patch(kl, self.konf, teraz=TERAZ, repo=repo,
                                                  mow=mowione.append, plik=self.plik))
        self.assertTrue(any("kolejna próba" in m for m in mowione))
        # Druga tura w ramach przerwy: repo nie jest już dotykane.
        repo2 = AtrapaRepo(brudne=[" M sf_kit/cos.py"])
        mowione2 = []
        self.assertIsNone(aktualizacje.auto_patch(kl, self.konf, teraz=TERAZ + 60,
                                                  repo=repo2, mow=mowione2.append,
                                                  plik=self.plik))
        self.assertEqual(repo2.tagi_pobrano, False)
        self.assertEqual(mowione2, [], "w przerwie po błędzie cisza, nie kolejny wpis")

    def test_brak_sieci_cisza(self):
        kl = AtrapaKlienta(blad=BladAPI("brak sieci"))
        self.assertIsNone(aktualizacje.auto_patch(kl, self.konf, teraz=TERAZ,
                                                  mow=lambda s: None, plik=self.plik))


class TestRepoZGitem(unittest.TestCase):
    """Rozróżnienie śledzone/nieśledzone w prawdziwym klonie — punkt kontraktu:
    lokalne łatki (nieśledzone) mają przeżyć aktualizację, śledzone zmiany ją blokują."""

    def setUp(self):
        self.katalog = tempfile.TemporaryDirectory()
        self.klon = Path(self.katalog.name)
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        (self.klon / "plik.txt").write_text("v1\n", encoding="utf-8")
        self._git("add", "plik.txt")
        self._git("commit", "-q", "-m", "start")

    def tearDown(self):
        self.katalog.cleanup()

    def _git(self, *argumenty):
        return subprocess.run(["git", "-C", str(self.klon), *argumenty],
                              capture_output=True, text=True)

    def test_nieśledzone_pliki_nie_blokuja(self):
        (self.klon / "wykonawcy.py.lokalna-latka").write_text("# łatka\n", encoding="utf-8")
        repo = aktualizacje.Repo(self.klon)
        self.assertEqual(repo.brudne_pliki(), [])

    def test_zmiana_sledzonego_blokuje(self):
        (self.klon / "plik.txt").write_text("zmienione\n", encoding="utf-8")
        repo = aktualizacje.Repo(self.klon)
        brudne = repo.brudne_pliki()
        self.assertEqual(len(brudne), 1)
        self.assertIn("plik.txt", brudne[0])


class TestWeryfikacjaSF(unittest.TestCase):
    """`GET /kit/version` — trasa dodana do Klienta zgodnie z kontraktem."""

    def test_trasa_i_sciezka(self):
        from sf_kit.api import Klient
        kl = Klient(baza="https://sf.dpakula.pl", klucz="sk_live_testowy")
        self.assertTrue(hasattr(kl, "wersja_kita"))


class TestCLIUpdate(unittest.TestCase):

    def test_update_w_pomocy(self):
        skrypt = Path(__file__).resolve().parents[1] / "sf-kit"
        wynik = subprocess.run([sys.executable, str(skrypt), "--help"],
                               capture_output=True, text=True)
        self.assertEqual(wynik.returncode, 0)
        self.assertIn("update", wynik.stdout)

    def test_update_check_bez_klucza_daje_zrozumiala_odmowe(self):
        """Bez klucza `--check` nie może zadziałać — ma powiedzieć człowiekowi, co zrobić."""
        skrypt = Path(__file__).resolve().parents[1] / "sf-kit"
        wynik = subprocess.run([sys.executable, str(skrypt), "update", "--check"],
                               capture_output=True, text=True,
                               env={"PATH": "/usr/bin:/bin", "HOME": "/tmp/nie-ma-takiego"})
        self.assertNotEqual(wynik.returncode, 0)
        self.assertIn("init", wynik.stderr + wynik.stdout,
                      "odmowa bez klucza prowadzi do init, nie do tracebacka")


class TestSerwerHTTPMockKontraktu(unittest.TestCase):
    """Serwer SF zamockowany ZGODNIE Z KONTRAKTEM: prawdziwy HTTP, jedyna trasa to
    `GET /api/v1/kit/version`; zapytanie musi nosić `User-Agent: sf-agent-kit/<wersja>`."""

    def setUp(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from sf_kit.api import Klient

        naglowki = {}

        class Obsluga(BaseHTTPRequestHandler):
            def do_GET(self):
                naglowki["user_agent"] = self.headers.get("User-Agent", "")
                naglowki["sciezka"] = self.path
                if self.path.startswith("/api/v1/kit/version"):
                    cialo = json.dumps(info_sf(commit=self.server.commit)).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(cialo)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *argumenty):
                pass

        self.Klient = Klient
        self.naglowki = naglowki
        self.serwer = ThreadingHTTPServer(("127.0.0.1", 0), Obsluga)
        self.serwer.commit = "a" * 40
        import threading
        self.watek = threading.Thread(target=self.serwer.serve_forever, daemon=True)
        self.watek.start()
        self.adres = f"http://127.0.0.1:{self.serwer.server_address[1]}"

    def tearDown(self):
        self.serwer.shutdown()
        self.serwer.server_close()

    def test_wersja_kita_naglowek_i_cialo(self):
        kl = self.Klient(baza=self.adres, klucz="sk_live_testowy")
        info = kl.wersja_kita()
        self.assertEqual(info["latest"], PATCH_NOWSZY)
        self.assertEqual(self.naglowki["user_agent"], f"sf-agent-kit/{WERSJA}",
                         "kontrakt: zapytanie z Kita niesie User-Agent z wersją")
        self.assertEqual(self.naglowki["sciezka"], "/api/v1/kit/version")


class TestEndToEndGitIHttp(unittest.TestCase):
    """Cała droga: mock SF (HTTP) → `aktualizuj` → prawdziwy klon gita. Klon stoi na
    starszym commicie A, „nowe wydanie" (tag wskazany przez SF) to commit B w origin —
    po aktualizacji HEAD klonu musi być B, a dziennik zmian A..B pokazany."""

    def setUp(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from sf_kit.api import Klient
        import threading

        self.katalog = tempfile.TemporaryDirectory()
        self.baza = Path(self.katalog.name)

        origin = self.baza / "origin.git"
        subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
        self.klon = self.baza / "klon"
        subprocess.run(["git", "clone", "-q", str(origin), str(self.klon)], check=True)
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "Test")
        (self.klon / "sf_kit").mkdir()
        (self.klon / "sf_kit" / "__init__.py").write_text("WERSJA = '0.0.0'\n",
                                                          encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "-q", "-m", "pierwszy")
        self._git("push", "-q", "origin", "HEAD")
        self.stary = self._git("rev-parse", "HEAD").stdout.strip()

        # „Wydanie" robi drugi klon — tak jak na prawdziwym GitHubie: tag powstaje PO
        # tym, jak stare maszyny pobrały A.
        klon2 = self.baza / "klon2"
        subprocess.run(["git", "clone", "-q", str(origin), str(klon2)], check=True)
        (klon2 / "sf_kit" / "__init__.py").write_text("WERSJA = '0.13.3'\n",
                                                      encoding="utf-8")
        subprocess.run(["git", "-C", str(klon2), "config", "user.email", "t@e.com"],
                       check=True)
        subprocess.run(["git", "-C", str(klon2), "config", "user.name", "T"], check=True)
        subprocess.run(["git", "-C", str(klon2), "add", "."], check=True)
        subprocess.run(["git", "-C", str(klon2), "commit", "-q", "-m", "druga zmiana"],
                       check=True)
        subprocess.run(["git", "-C", str(klon2), "tag", f"v{PATCH_NOWSZY}"], check=True)
        subprocess.run(["git", "-C", str(klon2), "push", "-q", "origin", "HEAD", "--tags"],
                       check=True)
        self.commit = subprocess.run(
            ["git", "-C", str(klon2), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()

        class Obsluga(BaseHTTPRequestHandler):
            def do_GET(self):
                cialo = json.dumps(info_sf(commit=self.server.commit)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(cialo)

            def log_message(self, *argumenty):
                pass

        self.serwer = ThreadingHTTPServer(("127.0.0.1", 0), Obsluga)
        self.serwer.commit = self.commit
        self.watek = threading.Thread(target=self.serwer.serve_forever, daemon=True)
        self.watek.start()
        self.klient = Klient(baza=f"http://127.0.0.1:{self.serwer.server_address[1]}",
                             klucz="sk_live_testowy")

    def tearDown(self):
        self.serwer.shutdown()
        self.serwer.server_close()
        self.katalog.cleanup()

    def _git(self, *argumenty):
        return subprocess.run(["git", "-C", str(self.klon), *argumenty],
                              capture_output=True, text=True, check=True)

    def test_aktualizacja_przez_http_i_git(self):
        repo = aktualizacje.Repo(self.klon)
        mowione = []
        self.assertTrue(aktualizacje.aktualizuj(self.klient, repo=repo,
                                                mow=mowione.append))
        self.assertEqual(self._git("rev-parse", "HEAD").stdout.strip(), self.commit)
        self.assertEqual(self._git("describe", "--tags").stdout.strip(),
                         f"v{PATCH_NOWSZY}")
        tekst = "\n".join(mowione)
        self.assertIn("sprawdzone zgodnie z SF", tekst)
        self.assertIn("druga zmiana", tekst, "zmiany od poprzedniej wersji są pokazane")
        self.assertNotEqual(self.stary, self.commit)


class TestNaglowkiWersji(unittest.TestCase):
    """`X-Kit-Latest`/`X-Kit-Min` z KAŻDEJ odpowiedzi (także 401/403) odświeżają pamięć
    podręczną — dobowe `GET /kit/version` zostaje zapasem (poprawka z przeglądu 94268501)."""

    def setUp(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from sf_kit.api import Klient
        import threading

        self.katalog = tempfile.TemporaryDirectory()
        korzen = Path(self.katalog.name) / "sf-kit"
        (korzen / "agent-testowy").mkdir(parents=True)
        (korzen / "agent-testowy" / "config.json").write_text("{}", encoding="utf-8")
        self._stare_xdg = os.environ.get("XDG_CONFIG_HOME")
        self._stary_dom = os.environ.pop("SF_KIT_HOME", None)
        os.environ["XDG_CONFIG_HOME"] = self.katalog.name
        self.plik_pamieci = korzen / "agent-testowy" / aktualizacje.PLIK_PAMIECI

        stan = {"kod": 200, "latest": None, "min": None}

        class Obsluga(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(stan["kod"])
                self.send_header("Content-Type", "application/json")
                if stan["latest"]:
                    self.send_header("X-Kit-Latest", stan["latest"])
                if stan["min"]:
                    self.send_header("X-Kit-Min", stan["min"])
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *argumenty):
                pass

        self.stan = stan
        self.Klient = Klient
        self.serwer = ThreadingHTTPServer(("127.0.0.1", 0), Obsluga)
        self.watek = threading.Thread(target=self.serwer.serve_forever, daemon=True)
        self.watek.start()
        self.adres = f"http://127.0.0.1:{self.serwer.server_address[1]}"

    def tearDown(self):
        self.serwer.shutdown()
        self.serwer.server_close()
        if self._stare_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._stare_xdg
        if self._stary_dom is not None:
            os.environ["SF_KIT_HOME"] = self._stary_dom
        self.katalog.cleanup()

    def _pamiec(self) -> dict:
        return aktualizacje.wczytaj_pamiec(self.plik_pamieci)

    def test_naglowki_z_odpowiedzi_200_odswiezaja_pamiec(self):
        self.stan.update(latest=PATCH_NOWSZY, min=MINIMALNA)
        kl = self.Klient(baza=self.adres, klucz="sk_live_testowy")
        kl.kim_jestem()
        pamiec = self._pamiec()
        self.assertEqual(pamiec["latest"], PATCH_NOWSZY)
        self.assertEqual(pamiec["min"], MINIMALNA)

    def test_naglowki_z_bledu_401_też_odswiezaja_pamiec(self):
        """Serwer niesie wersje TAKŻE przy 401/403 — Kit ma je zapisać, zanim poleci wyjątek."""
        self.stan.update(kod=401, latest=PATCH_NOWSZY, min=MINIMALNA)
        kl = self.Klient(baza=self.adres, klucz="sk_live_testowy")
        with self.assertRaises(BladAPI):
            kl.kim_jestem()
        self.assertEqual(self._pamiec()["latest"], PATCH_NOWSZY)

    def test_odpowiedz_bez_naglowkow_nic_nie_zapisuje(self):
        kl = self.Klient(baza=self.adres, klucz="sk_live_testowy")
        kl.kim_jestem()
        self.assertFalse(self.plik_pamieci.exists(),
                         "bez nagłówków wersji nie powstaje żaden plik pamięci")

    def test_naglowki_nie_zacieraja_znacznika_dobowego(self):
        """Zapas zostaje zapasem: świeże `latest` z nagłówków NIE zastępuje pełnego
        sprawdzenia (dobowe `GET /kit/version` dalej dostarcza tag/commit/breaking)."""
        self.stan.update(latest=PATCH_NOWSZY, min=MINIMALNA)
        kl = self.Klient(baza=self.adres, klucz="sk_live_testowy")
        kl.kim_jestem()
        self.assertNotIn("sprawdzono_o", self._pamiec(),
                         "nagłówki mówią TYLKO o wersjach — pełny zapis oznacza pełną odpowiedź")

    def test_bez_istniejacego_agenta_nic_sie_nie_zapisuje(self):
        """`init` pyta `GET /me`, zanim powstanie podkatalog — taka odpowiedź nie może
        podpisać cudzej (albo jeszcze żadnej) pamięci podręcznej."""
        (Path(self.katalog.name) / "sf-kit" / "agent-testowy" / "config.json").unlink()
        self.stan.update(latest=PATCH_NOWSZY, min=MINIMALNA)
        kl = self.Klient(baza=self.adres, klucz="sk_live_testowy")
        kl.kim_jestem()
        self.assertFalse(self.plik_pamieci.exists())


if __name__ == "__main__":
    unittest.main()
