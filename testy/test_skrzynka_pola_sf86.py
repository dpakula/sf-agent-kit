"""Kit używa pól kontraktu skrzynki SF-86 — pilne, ważność, wątek, dzierżawa, odmowa, eskalacja.

v0.1 (28.09.2026) - APro Agents / borys-sf

CZEGO TU PILNUJĘ
════════════════
1. **Pilne wyprzedza INNE wątki, nie własne zależności** — i dochodzi do agenta, nawet gdy
   w skrzynce stoi trzydziesta (Kit pobiera szerzej niż oddaje).
2. **Po terminie ważności — nie wykonujemy**, a lokalna kolejka nie trzyma trupów.
3. **Dwie sesje jednego agenta** — wiadomość z cudzą dzierżawą nie trafia do polecenia
   i nie jest potwierdzana przez tę sesję.
4. **Odmowa odbiornika** idzie do SF jako `failed` z powodem (licznik prób), nie w ciszę.
5. **Alarm Iris raz**: pilne — przy przyjęciu, eskalacja — raz na znacznik `eskalowano_at`;
   bez nowego pliku, nowego acka ani nowego prompta.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import skrzynka, wykonawcy  # noqa: E402
from sf_kit.api import Klient, Konflikt  # noqa: E402
from sf_kit.worker import obsluz_zadanie  # noqa: E402
from testy.test_skrzynka_812 import wiadomosc  # noqa: E402
from testy.test_worker import AtrapaKlienta, konfiguracja, zadanie  # noqa: E402

TERAZ = datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)


def w(mid, tresc="treść wiadomości", **pola):
    return {**wiadomosc(mid=mid, tresc=tresc), **pola}


class KlientPol:
    """Atrapa skrzynki z dzierżawą i potwierdzeniami zapisującymi WSZYSTKIE argumenty."""

    def __init__(self, wiadomosci, *, cudze_dzierzawy=(), dzierzawa_pada=None, konflikt_acka=()):
        self.wiadomosci = wiadomosci
        self.cudze = set(cudze_dzierzawy)
        self.dzierzawa_pada = dzierzawa_pada
        self.konflikt_acka = set(konflikt_acka)
        self.acki: list[dict] = []
        self.dzierzawy: list[tuple[str, str, int]] = []
        self.limity: list[int | None] = []

    def skrzynka(self, *, dni=None, limit=None, tylko_nieodebrane=False):
        self.limity.append(limit)
        return {"wiadomosci": self.wiadomosci[:limit] if limit else self.wiadomosci,
                "nieodebrane": len(self.wiadomosci), "zalegle": 0}

    def potwierdz_odbior(self, message_id, **kw):
        if str(message_id) in self.konflikt_acka:
            raise Konflikt("starsza generacja", kod=409)
        self.acki.append({"mid": str(message_id), **kw})
        return {}

    def dzierzawa(self, message_id, *, instancja, sekundy):
        if self.dzierzawa_pada:
            raise self.dzierzawa_pada
        self.dzierzawy.append((str(message_id), instancja, sekundy))
        if str(message_id) in self.cudze and sekundy:
            return {"przyznana": False, "instancja": "inna-sesja", "do": "2026-09-28T21:00:00Z"}
        return {"przyznana": True, "instancja": instancja, "do": "2026-09-28T21:00:00Z"}


# ── 1. kolejka odbiornika ─────────────────────────────────────────────────────────────

class TestUloz(unittest.TestCase):
    def test_bez_priorytetow_kolejnosc_z_SF_bez_zmian(self):
        wejscie = [w("a"), w("b"), w("c")]
        self.assertEqual([x["message_id"] for x in skrzynka.uloz(wejscie)], ["a", "b", "c"])

    def test_pilny_watek_idzie_pierwszy_razem_ze_swoimi_wczesniejszymi(self):
        """Pilna odpowiedź NIE przeskakuje wiadomości, na której stoi — ciągnie cały wątek."""
        wejscie = [w("inny", watek_id="W2"), w("pytanie", watek_id="W1"),
                   w("trzeci"), w("pilna-odp", watek_id="W1", priorytet="pilne")]
        self.assertEqual([x["message_id"] for x in skrzynka.uloz(wejscie)],
                         ["pytanie", "pilna-odp", "inny", "trzeci"])

    def test_niski_za_normalnym_a_nieznany_priorytet_jak_normal(self):
        wejscie = [w("n", priorytet="niski"), w("x", priorytet="kosmiczny"), w("z")]
        self.assertEqual([x["message_id"] for x in skrzynka.uloz(wejscie)], ["x", "z", "n"])


class TestPobierz(unittest.TestCase):
    def test_pilna_trzydziesta_w_kolejce_dochodzi_do_agenta(self):
        wejscie = [w(f"m{i}") for i in range(30)] + [w("pilna", priorytet="pilne")]
        k = KlientPol(wejscie)
        wynik = skrzynka.pobierz(k, limit=5, teraz=TERAZ)
        self.assertEqual(wynik.wiadomosci[0]["message_id"], "pilna")
        self.assertEqual(len(wynik.wiadomosci), 5)
        self.assertGreaterEqual(k.limity[0], skrzynka.LIMIT_PRZYJECIA)

    def test_po_terminie_nie_idzie_do_wykonania_i_jest_policzona(self):
        wejscie = [w("stara", wazne_do=(TERAZ - timedelta(minutes=1)).isoformat()),
                   w("zywa", wazne_do=(TERAZ + timedelta(minutes=5)).isoformat()), w("bez")]
        wynik = skrzynka.pobierz(KlientPol(wejscie), teraz=TERAZ)
        self.assertEqual([x["message_id"] for x in wynik.wiadomosci], ["zywa", "bez"])
        self.assertEqual(wynik.wygasle, 1)


# ── 2. przyjęcie w takcie: instancja, alarmy, eskalacja, sprzątanie ────────────────────

class TestPrzyjmij(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.katalog = Path(self._tmp.name) / "skrzynka"
        self.alarmy: list[tuple[str, str]] = []
        self._alarm = mock.patch.object(
            skrzynka, "alarm", side_effect=lambda t, tr: self.alarmy.append((t, tr)) or True)
        self._alarm.start()

    def tearDown(self):
        self._alarm.stop()
        self._tmp.cleanup()

    def test_ack_delivered_niesie_instancje_i_generacje(self):
        k = KlientPol([w("m1")])
        skrzynka.przyjmij(k, self.katalog, slug="kimi", teraz=TERAZ)
        [ack] = k.acki
        self.assertEqual(ack["status"], "delivered")
        self.assertIn(":kimi:", ack["instancja"])
        self.assertIsInstance(ack["generacja"], int)

    def test_pilna_alarmuje_raz_przy_przyjeciu_nie_w_kazdym_takcie(self):
        k = KlientPol([w("p1", priorytet="pilne")])
        skrzynka.przyjmij(k, self.katalog, slug="kimi", teraz=TERAZ)
        k.wiadomosci = [w("p1", priorytet="pilne", status="delivered")]
        skrzynka.przyjmij(k, self.katalog, slug="kimi", teraz=TERAZ)
        self.assertEqual(len(self.alarmy), 1)
        self.assertNotIn("treść wiadomości", self.alarmy[0][1], "treść nie wychodzi do alarmu")

    def test_zwykla_nie_alarmuje(self):
        skrzynka.przyjmij(KlientPol([w("m1")]), self.katalog, teraz=TERAZ)
        self.assertEqual(self.alarmy, [])

    def test_eskalacja_to_jeden_alarm_bez_nowego_pliku_i_acka(self):
        k = KlientPol([w("m1")])
        skrzynka.przyjmij(k, self.katalog, teraz=TERAZ)
        eskalowana = w("m1", status="delivered", eskalowano_at="2026-09-28T19:50:00Z")
        k.wiadomosci = [eskalowana]
        skrzynka.przyjmij(k, self.katalog, teraz=TERAZ)
        skrzynka.przyjmij(k, self.katalog, teraz=TERAZ)

        self.assertEqual(len(self.alarmy), 1, "ta sama eskalacja nie alarmuje drugi raz")
        self.assertEqual(len(k.acki), 1, "eskalacja to nie nowe doręczenie")
        self.assertEqual(sorted(p.name for p in self.katalog.iterdir()), ["m1.json"])
        zapisane = json.loads((self.katalog / "m1.json").read_text(encoding="utf-8"))
        self.assertEqual(zapisane["eskalowano_at"], "2026-09-28T19:50:00Z")

    def test_starsza_generacja_to_nie_porazka_tylko_inna_sesja(self):
        k = KlientPol([w("m1")], konflikt_acka={"m1"})
        wynik = skrzynka.przyjmij(k, self.katalog, teraz=TERAZ)
        self.assertEqual(wynik.u_innej_instancji, ["m1"])
        self.assertEqual(wynik.niepotwierdzone, [])

    def test_plik_po_terminie_znika_z_lokalnej_kolejki(self):
        self.katalog.mkdir(parents=True)
        (self.katalog / "stara.json").write_text(json.dumps(
            w("stara", wazne_do=(TERAZ - timedelta(seconds=1)).isoformat())), encoding="utf-8")
        (self.katalog / "zywa.json").write_text(json.dumps(w("zywa")), encoding="utf-8")
        skrzynka.przyjmij(KlientPol([]), self.katalog, teraz=TERAZ)
        self.assertEqual(sorted(p.name for p in self.katalog.iterdir()), ["zywa.json"])


# ── 3. dzierżawa i odmowa przy zadaniu ─────────────────────────────────────────────────

class KlientWorkeraPol(AtrapaKlienta, KlientPol):
    def __init__(self, wiadomosci, **kw):
        AtrapaKlienta.__init__(self)
        KlientPol.__init__(self, wiadomosci, **kw)


class Szpieg(wykonawcy.Wykonawca):
    nazwa = "szpieg-pola"
    chce_ramke = True

    def __init__(self):
        self.polecenia: list[str] = []

    def dostepny(self):
        return True, ""

    def wykonaj(self, polecenie, *, katalog, limit_s):
        self.polecenia.append(polecenie)
        return wykonawcy.Wynik(True, "**Sedno** — ok")


class TestZadanie(unittest.TestCase):
    def _obsluz(self, klient):
        szpieg = Szpieg()
        stare = dict(wykonawcy._WYKONAWCY)
        wykonawcy._WYKONAWCY["szpieg-pola"] = szpieg
        try:
            obsluz_zadanie(klient, konfiguracja(runtime="szpieg-pola"), zadanie(body_md="x"))
        finally:
            wykonawcy._WYKONAWCY.clear()
            wykonawcy._WYKONAWCY.update(stare)
        return szpieg.polecenia[0]

    def test_cudza_dzierzawa_nie_trafia_do_polecenia_ani_do_potwierdzen(self):
        k = KlientWorkeraPol([w("moja", tresc="MOJA TREŚĆ"), w("cudza", tresc="CUDZA TREŚĆ")],
                             cudze_dzierzawy={"cudza"})
        polecenie = self._obsluz(k)
        self.assertIn("MOJA TREŚĆ", polecenie)
        self.assertNotIn("CUDZA TREŚĆ", polecenie)
        self.assertEqual([a["mid"] for a in k.acki if a["status"] == "consumed"], ["moja"])

    def test_dzierzawa_na_czas_zadania_i_potwierdzenie_z_instancja(self):
        k = KlientWorkeraPol([w("m1")])
        self._obsluz(k)
        [(mid, instancja, sekundy)] = k.dzierzawy
        self.assertEqual(sekundy, 10 + 120)      # limit zadania z konfiguracji + zapas
        [ack] = [a for a in k.acki if a["status"] == "consumed"]
        self.assertEqual(ack["instancja"], instancja)

    def test_bez_trasy_dzierzawy_zachowanie_jak_przed_SF86(self):
        k = KlientWorkeraPol([w("m1", tresc="TREŚĆ")], dzierzawa_pada=RuntimeError("404"))
        self.assertIn("TREŚĆ", self._obsluz(k))

    def test_pilna_w_poleceniu_z_oznaczeniem(self):
        k = KlientWorkeraPol([w("m1", tresc="zwykła"), w("m2", tresc="PILNE!", priorytet="pilne")])
        polecenie = self._obsluz(k)
        self.assertLess(polecenie.index("PILNE!"), polecenie.index("zwykła"))
        self.assertIn("[PILNE]", polecenie)

    def test_odmowa_odbiornika_niesie_powod_i_instancje(self):
        k = KlientWorkeraPol([w("m1")])
        obsluz_zadanie(k, konfiguracja(), zadanie(body_md="echo ok"))      # powłoka: bez ramki
        [ack] = k.acki
        self.assertEqual(ack["status"], "failed")
        self.assertIn("nie przyjmuje ramki", ack["powod"])
        self.assertTrue(ack["instancja"])


# ── 4. tożsamość, alarm, klient API ────────────────────────────────────────────────────

class TestTozsamoscIAlarm(unittest.TestCase):
    def test_dwie_sesje_na_tej_samej_maszynie_maja_rozne_instancje(self):
        with mock.patch.object(os, "getpid", return_value=111):
            a, _ = skrzynka.ta_instancja("kimi")
        with mock.patch.object(os, "getpid", return_value=222):
            b, _ = skrzynka.ta_instancja("kimi")
        self.assertNotEqual(a, b)
        dluga, _ = skrzynka.ta_instancja("x" * 200 + " spacja")
        self.assertLessEqual(len(dluga), 64)
        self.assertNotIn(" ", dluga)

    def test_alarm_bez_iris_to_False_nie_wyjatek(self):
        with mock.patch.dict(os.environ, {"SF_KIT_IRIS": "/nie/ma/takiego"}):
            self.assertFalse(skrzynka.alarm("t", "x"))

    def test_alarm_idzie_z_flaga_u(self):
        with tempfile.TemporaryDirectory() as tmp:
            zapis = Path(tmp) / "argumenty"
            iris = Path(tmp) / "iris-notify"
            iris.write_text(f"#!/bin/sh\necho \"$@\" > {zapis}\n", encoding="utf-8")
            iris.chmod(iris.stat().st_mode | stat.S_IEXEC)
            with mock.patch.dict(os.environ, {"SF_KIT_IRIS": str(iris)}):
                self.assertTrue(skrzynka.alarm("Tytuł", "treść alarmu"))
            self.assertTrue(zapis.read_text(encoding="utf-8").startswith("-u "))

    def test_opis_oznacza_pilne_i_eskalowane(self):
        tekst = skrzynka.opis(skrzynka.Odebrane(wiadomosci=[
            w("a", priorytet="pilne"), w("b", eskalowano_at="2026-09-28T19:00:00Z")]))
        self.assertIn("[PILNE]", tekst)
        self.assertIn("[ESKALOWANA]", tekst)


class TestKlientAPI(unittest.TestCase):
    def setUp(self):
        self.k = Klient(baza="https://x", klucz="k", organizacja="o")

    def test_potwierdzenie_wysyla_instancje_i_generacje(self):
        with mock.patch.object(Klient, "_wywolaj", return_value={}) as wolanie:
            self.k.potwierdz_odbior("m1", status="delivered", instancja="h:kimi:1", generacja=7)
        cialo = wolanie.call_args.kwargs["cialo"]
        self.assertEqual((cialo["instancja"], cialo["generacja"]), ("h:kimi:1", 7))

    def test_cudza_dzierzawa_409_to_odpowiedz_a_nie_wyjatek(self):
        blad = Konflikt("zajęta", kod=409,
                        szczegoly=json.dumps({"przyznana": False, "instancja": "inna"}))
        with mock.patch.object(Klient, "_wywolaj", side_effect=blad):
            wynik = self.k.dzierzawa("m1", instancja="ja", sekundy=60)
        self.assertEqual(wynik, {"przyznana": False, "instancja": "inna", "do": None})


if __name__ == "__main__":
    unittest.main()
