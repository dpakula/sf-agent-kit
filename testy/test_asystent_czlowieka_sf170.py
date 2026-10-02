"""SF-170: asystent związany ze swoim człowiekiem — `pracuje_dla`, „co czeka”, podpis wpisów.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · projekt: wpis a3c7608d; korekta Damiana 02.10 (SF-200):
powiązanie to tożsamość i kolejka, NIE uprawnienia.

CZEGO PILNUJĄ
· `pracuje_dla` zapisuje się tylko dla członka Organizacji (sprawdzenie w SF, 404 = nie zapisuję).
· `sprawy` w profilu asystenta = sprawy człowieka + moje, ze źródłem; „poza zasięgiem” liczbą.
· SF sprzed SF-170 (bez `poza_zasiegiem`) → komunikat, NIE cała Organizacja udająca sprawy człowieka.
· Podpis `na_rzecz` idzie we wpisie; SF sprzed SF-170 (422) → wpis i tak powstaje, bez podpisu.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli  # noqa: E402
from sf_kit.api import BladAPI, Klient  # noqa: E402
from sf_kit.config import Konfiguracja  # noqa: E402

JA = "11111111-1111-1111-1111-111111111111"


def _sprawa(sid, numer, tytul):
    return {"id": sid, "ticket_prefix": "GRA01", "ticket_number": numer, "title": tytul, "status": "new"}


class Atrapa:
    def __init__(self, *, zna=True, poza=0):
        self.zna, self.poza = zna, poza
        self.pytania = []

    def czlonek(self, email):
        if email != "damian@sf.pl":
            raise BladAPI("Nie ma takiej osoby w tej Organizacji", kod=404)
        return {"user_id": "22222222-2222-2222-2222-222222222222", "email": email, "nazwa": "Damian"}

    def sprawy_osoby(self, kto, limit=100):
        self.pytania.append(kto)
        if not self.zna:
            return [], None, False
        if kto == "damian@sf.pl":
            return [_sprawa("a", 1, "Zadanie 1"), _sprawa("b", 2, "Wspólne")], self.poza, True
        return [_sprawa("b", 2, "Wspólne"), _sprawa("c", 3, "Moje")], 0, True


def _uruchom(argv, atrapa, konf):
    toz = SimpleNamespace(konto_id=JA, konto_email="ala@sf.pl", konto_nazwa="Ala")
    org = SimpleNamespace(slug="gra01", uuid="o")
    zapisane = []
    with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=konf), \
            mock.patch.object(cli.konfiguracja, "zapisz", side_effect=zapisane.append), \
            mock.patch.object(cli, "_klient_organizacja_tozsamosc", return_value=(atrapa, org, toz)):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            kod = cli.main(argv)
    return kod, out.getvalue(), err.getvalue(), zapisane


def _asystent(pracuje_dla="damian@sf.pl"):
    k = Konfiguracja()
    k.profil = "asystent"
    k.pracuje_dla = pracuje_dla
    return k


class TestAsystentCzlowieka(unittest.TestCase):
    def test_pracuje_dla_tylko_dla_czlonka(self):
        kod, out, _, zapisane = _uruchom(["ustawienia", "pracuje_dla", "damian@sf.pl"], Atrapa(), _asystent(None))
        self.assertEqual(kod, 0)
        self.assertEqual(zapisane[0].pracuje_dla, "damian@sf.pl")
        kod, _, err, zapisane = _uruchom(["ustawienia", "pracuje_dla", "obcy@x.pl"], Atrapa(), _asystent(None))
        self.assertEqual(kod, 1)
        self.assertEqual(zapisane, [])
        self.assertIn("nie jest członkiem", err)

    def test_co_czeka_czlowiek_plus_ja_ze_zrodlem(self):
        """GRA01-1: Zadanie 1 przypisane do Damiana znajduje się przez powiązanie."""
        a = Atrapa(poza=2)
        kod, out, _, _ = _uruchom(["sprawy"], a, _asystent())
        self.assertEqual(kod, 0)
        self.assertIn("Zadanie 1", out)
        self.assertIn("[człowiek]", out)
        self.assertIn("[człowiek + ja]", out)                   # wspólna sprawa raz, z oboma źródłami
        self.assertIn("[ja]", out)
        self.assertEqual(out.count("Wspólne"), 1)
        self.assertIn("2 spraw Twojego człowieka jest poza moimi uprawnieniami", out)

    def test_flagi_zawezaja_zrodla(self):
        a = Atrapa()
        _uruchom(["sprawy", "--tylko-czlowieka"], a, _asystent())
        self.assertEqual(a.pytania, ["damian@sf.pl"])
        a = Atrapa()
        _uruchom(["sprawy", "--tylko-moje"], a, _asystent())
        self.assertEqual(a.pytania, [JA])

    def test_stary_sf_nie_udaje_spraw_czlowieka(self):
        kod, out, err, _ = _uruchom(["sprawy"], Atrapa(zna=False), _asystent())
        self.assertEqual(kod, 1)
        self.assertIn("nie zna jeszcze filtra", err)
        self.assertNotIn("Zadanie", out)


class TestPodpisWpisu(unittest.TestCase):
    def test_na_rzecz_idzie_w_ciele(self):
        k = Klient(baza="https://sf", klucz="k")
        k.na_rzecz = "damian@sf.pl"
        with mock.patch.object(k, "_wywolaj", return_value={"id": "w"}) as w:
            k.wpis("s", "treść")
        self.assertEqual(w.call_args.kwargs["cialo"]["na_rzecz"], "damian@sf.pl")

    def test_stary_sf_odrzuca_pole_wpis_i_tak_powstaje(self):
        k = Klient(baza="https://sf", klucz="k")
        k.na_rzecz = "damian@sf.pl"
        odmowa = BladAPI("422", kod=422, szczegoly='{"detail":[{"loc":["body","na_rzecz"],"msg":"Extra inputs"}]}')
        with mock.patch.object(k, "_wywolaj", side_effect=[odmowa, {"id": "w"}]) as w:
            self.assertEqual(k.wpis("s", "treść"), {"id": "w"})
        self.assertNotIn("na_rzecz", w.call_args.kwargs["cialo"])
        self.assertIsNone(k.na_rzecz, "po pierwszej odmowie nie wysyłamy pola dalej")

    def test_inny_422_nie_jest_polykany(self):
        k = Klient(baza="https://sf", klucz="k")
        k.na_rzecz = "damian@sf.pl"
        with mock.patch.object(k, "_wywolaj", side_effect=BladAPI("422", kod=422, szczegoly="content too long")):
            with self.assertRaises(BladAPI):
                k.wpis("s", "treść")

    def test_podpis_tylko_w_profilu_asystenta(self):
        with mock.patch.object(cli.magazyn_klucza, "wczytaj", return_value="k"):
            k = _asystent()
            k.adres, k.slug = "https://sf", "ala"
            self.assertEqual(cli._klient_bez_organizacji(k).na_rzecz, "damian@sf.pl")
            k.profil = "worker"
            self.assertIsNone(cli._klient_bez_organizacji(k).na_rzecz)


if __name__ == "__main__":
    unittest.main()
