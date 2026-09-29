"""Kit 0.14.1 (ADVERTPR-976, przed szkoleniem FM 30.09): zapis do pęku kluczy bez terminala
sterującego i komunikat 403, który mówi, czego brakuje i kogo prosić.

v0.1 (29.09.2026) - APro Agents / borys-sf

1. `security add-generic-password -w` z terminalem sterującym czyta monity z `/dev/tty`, nie ze
   stdin — `init` wisiał na Macu (sprawdził seweryn w pseudoterminalu). Nowa sesja
   (`start_new_session=True`) = brak terminala sterującego, wartość idzie ze stdin.
   Tu (Linux, bez `security`) pilnujemy kontraktu wywołania; zachowanie na macOS potwierdził
   seweryn w pty (zapis 0,2 s, bez monitów).
2. 403 z nazwą brakującego uprawnienia (trzy kształty odmowy w SF), Organizacją i wskazaniem
   administratora. Bez rozpoznanej nazwy — dotychczasowy komunikat.
"""
import unittest
from unittest import mock

from sf_kit import api, klucz


class ZapisDoPekuBezTerminala(unittest.TestCase):
    def test_security_w_nowej_sesji_i_klucz_tylko_na_stdin(self):
        with mock.patch.object(klucz.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stderr="")
            klucz._zapisz_keychain("sk_live_SEKRET")
        args, kwargs = run.call_args
        self.assertTrue(kwargs.get("start_new_session"), "bez nowej sesji `security` czyta /dev/tty")
        self.assertNotIn("sk_live_SEKRET", " ".join(args[0]), "klucz nie może trafić do argv (ps)")
        self.assertIn("sk_live_SEKRET", kwargs["input"])


class Komunikat403(unittest.TestCase):
    def _blad(self, tresc, org="formarketing"):
        return api.Klient._na_wyjatek(403, "POST", "tickets", tresc, org)

    def test_klucz_bez_uprawnienia_mowi_co_i_kogo_prosic(self):
        b = self._blad('{"detail":"API key lacks permission: tickets:write"}')
        self.assertIsInstance(b, api.BrakUprawnienia)
        tekst = str(b)
        self.assertIn("`tickets:write`", tekst)
        self.assertIn("formarketing", tekst)
        self.assertIn("administratora Organizacji", tekst)

    def test_dwa_uprawnienia_do_wyboru_i_polski_ksztalt(self):
        self.assertIn("`tickets:read lub tickets:write`",
                      str(self._blad('{"detail":"Missing permission: tickets:read or tickets:write"}')))
        self.assertIn("`console:write`", str(self._blad('{"detail":"Brak uprawnienia: console:write"}')))

    def test_bez_nazwy_uprawnienia_dotychczasowy_komunikat(self):
        tekst = str(self._blad('{"detail":"Insufficient role"}'))
        self.assertIn("nie wolno ci tej operacji", tekst)


if __name__ == "__main__":
    unittest.main()
