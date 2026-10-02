"""SF-173: `sf-kit ustawienia` — lokalne i w SF, poziom powiadomień, źródło wartości, zgoda osoby.

v1.0.0 (02.10.2026) - APro Agents / borys-sf · projekt: wpis 7fde1fad na SF-173

CZEGO PILNUJĄ
· Odczyt pokazuje OBA miejsca (lokalne i w SF) i przy każdym zdarzeniu ŹRÓDŁO wartości.
· `powiadomienia.poziom` idzie do SF; definicji „ważnego" Kit nie ma (wysyła sam poziom).
· Cudze ustawienia: 403 tłumaczone na „jak włączyć zgodę", nie samo „403".
· Ustawienia lokalne zapisują plik i walidują `auto_update`.

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
from sf_kit.api import BrakUprawnienia  # noqa: E402
from sf_kit.config import Konfiguracja  # noqa: E402
from sf_kit.tozsamosc import z_odpowiedzi  # noqa: E402

JA = "11111111-1111-1111-1111-111111111111"
CZLOWIEK = "22222222-2222-2222-2222-222222222222"

STAN = {
    "poziom": "domyslny", "wyciszona": False, "nadpisania_regul": 0, "zgoda_na_automat": False,
    "podsumowanie": {"rytm": "daily_08"},
    "pozycje": [
        {"event_name": "ticket.comment_added", "etykieta": "Nowe wiadomości", "grupa": "sprawy",
         "wazne": False, "kanaly": ["email", "in_app"], "zrodlo": "domyslne_katalogu"},
        {"event_name": "ticket.assigned", "etykieta": "Przypisanie na mnie", "grupa": "sprawy",
         "wazne": True, "kanaly": ["email"], "zrodlo": "preferencja"},
        {"event_name": "lead.created", "etykieta": "Nowy lead", "grupa": "system",
         "wazne": False, "kanaly": ["email"], "zrodlo": "domyslne_poziomu"},
    ],
}


class Atrapa:
    def __init__(self, odmowa=False):
        self.odmowa = odmowa
        self.wolania = []

    def ustawienia_skuteczne(self, uid):
        self.wolania.append(("skuteczne", uid))
        if self.odmowa and uid != JA:
            raise BrakUprawnienia("Forbidden", kod=403)
        return STAN

    def ustaw_poziom_powiadomien(self, uid, poziom, kanaly=None):
        self.wolania.append(("poziom", uid, poziom, kanaly))
        if self.odmowa and uid != JA:
            raise BrakUprawnienia("Forbidden", kod=403)
        return {**STAN, "poziom": poziom}

    def czlonek(self, email):
        return {"user_id": CZLOWIEK, "email": email, "nazwa": "Damian"}

    def historia_ustawien(self, uid, limit=20):
        return [{"kiedy": "2026-10-02T10:00:00", "kto": "api:asystent", "przed": {"poziom": "domyslny"},
                 "po": {"poziom": "wazne"}, "opis": "poziom wazne"}]


def _uruchom(argv, atrapa, konf=None):
    konf = konf or Konfiguracja()
    toz = SimpleNamespace(konto_id=JA, konto_email="ja@sf.pl", konto_nazwa="Ja")
    org = SimpleNamespace(slug="sf", uuid="o")
    zapisane = []
    with mock.patch.object(cli.konfiguracja, "wczytaj", return_value=konf), \
            mock.patch.object(cli.konfiguracja, "zapisz", side_effect=zapisane.append), \
            mock.patch.object(cli.konfiguracja, "sciezka", return_value=Path("/tmp/sf-kit.json")), \
            mock.patch.object(cli, "_klient_organizacja_tozsamosc", return_value=(atrapa, org, toz)):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            kod = cli.main(argv)
    return kod, out.getvalue(), err.getvalue(), zapisane


class TestUstawienia(unittest.TestCase):
    def test_odczyt_pokazuje_lokalne_sf_i_zrodlo(self):
        kod, out, _, _ = _uruchom(["ustawienia"], Atrapa())
        self.assertEqual(kod, 0)
        self.assertIn("Ustawienia lokalne", out)
        self.assertIn("auto_update", out)
        self.assertIn("powiadomienia.poziom", out)
        self.assertIn("domyślny (nic nie ustawiono)", out)
        self.assertIn("Nowe wiadomości", out)
        self.assertIn("domyślne", out)
        self.assertIn("ustawione", out)                  # źródło `preferencja`
        self.assertNotIn("Nowy lead", out, "zdarzenia systemowe nieobowiązkowe nie zaśmiecają widoku")

    def test_poziom_idzie_do_sf_z_kanalami(self):
        a = Atrapa()
        kod, out, _, _ = _uruchom(["ustawienia", "powiadomienia.poziom", "wazne", "--kanaly", "email,push"], a)
        self.assertEqual(kod, 0)
        self.assertIn(("poziom", JA, "wazne", ["email", "push"]), a.wolania)
        self.assertIn("✓ w SF", out)

    def test_zly_poziom_i_zly_kanal_nie_wolaja_sf(self):
        a = Atrapa()
        self.assertEqual(_uruchom(["ustawienia", "powiadomienia.poziom", "glosno"], a)[0], 2)
        self.assertEqual(_uruchom(["ustawienia", "powiadomienia.poziom", "wazne", "--kanaly", "sms"], a)[0], 2)
        self.assertFalse([w for w in a.wolania if w[0] == "poziom"])

    def test_czlowiek_bez_zgody_dostaje_polskie_zdanie(self):
        konf = Konfiguracja()
        konf.pracuje_dla = "damian@sf.pl"
        kod, _, err, _ = _uruchom(["ustawienia", "--czlowiek", "powiadomienia.poziom", "cisza"],
                                  Atrapa(odmowa=True), konf)
        self.assertEqual(kod, 1)
        self.assertIn("zgody tej osoby", err)
        self.assertIn("notifications:manage:by-agent", err)

    def test_czlowiek_bez_pracuje_dla_mowi_co_zrobic(self):
        kod, _, err, _ = _uruchom(["ustawienia", "--czlowiek"], Atrapa())
        self.assertEqual(kod, 2)
        self.assertIn("pracuje_dla", err)

    def test_lokalne_zapisuje_i_waliduje(self):
        kod, out, _, zapisane = _uruchom(["ustawienia", "auto_update", "patch"], Atrapa())
        self.assertEqual(kod, 0)
        self.assertEqual(zapisane[0].auto_update, "patch")
        kod, _, err, zapisane = _uruchom(["ustawienia", "auto_update", "zawsze"], Atrapa())
        self.assertEqual(kod, 2)
        self.assertEqual(zapisane, [])

    def test_historia(self):
        kod, out, _, _ = _uruchom(["ustawienia", "--historia"], Atrapa())
        self.assertEqual(kod, 0)
        self.assertIn("poziom domyslny → wazne", out)

    def test_konto_id_z_me(self):
        toz = z_odpowiedzi({"konto": {"id": JA, "email": "ja@sf.pl"}, "organizacje": []})
        self.assertEqual(toz.konto_id, JA)
        self.assertIsNone(z_odpowiedzi({"konto": {}, "organizacje": []}).konto_id)


if __name__ == "__main__":
    unittest.main()
