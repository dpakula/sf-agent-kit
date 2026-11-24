"""Kit 0.21.1: `--tresc` z tekstem dłuższym niż limit nazwy pliku (SF-576).

v1.0.0 (24.11.2026) - APro Agents / borys-sf · SF-576 (zgłosił klaudiusz-seco)

CO SIĘ DZIAŁO
· `sf-kit wpis --do agata --tresc "<~400 znaków>"` kończył się tracebackiem `OSError: [Errno 36] File name too long`.
  `--tresc` przyjmuje TEKST albo PLIK, więc Kit najpierw pytał system „czy to plik?” (`Path.is_file()`), a dla napisu
  dłuższego niż 255 bajtów system odpowiada wyjątkiem ENAMETOOLONG, nie fałszem. To nie było ucinanie treści — zapis
  w ogóle nie dochodził do SF.

CZEGO PILNUJĄ
· Tekst ze zgłoszenia (ze spacjami, ~420 znaków, z polskimi literami) idzie jako treść, bez wyjątku, bajt w bajt.
· Jedno „słowo” > 255 B bez `/` i rozszerzenia = treść; z `/` (wygląda na ścieżkę) = czytelny błąd kodu 2, bez wyjątku.
· `--opis <za długa nazwa>` = czytelny błąd kodu 2 (`ZleWejscie`), nie traceback.
· Krótki plik i `-` działają jak dotąd. Ścieżka CLI (`wpis … --tresc`) przez `_opis_z_wejscia` daje pełny tekst.

Uruchomienie: `python3 -m unittest discover -s testy`
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sf_kit import cli, nawyki  # noqa: E402

ZGLOSZENIE = ("SECO-334: flota NIE ma dostępu do strefy secocosmetics.com w dhosting (brak w AProCredentials, Pęku, "
              "pamięci floty i sprawach). Konto ma Damian albo Emil, rozstrzygnie Damian. Gotowa linia strefy, szkic dla "
              "Emila i ważna uwaga (SOA zmienione dziś, serial 2026112401) są w wpisie na ADVERTPR-1362. Po dopisaniu "
              "sprawdzam dig i podaję godzinę. — klaudiusz-seco")


class TrescDlugaSF576(unittest.TestCase):

    def test_tekst_ze_zgloszenia_przechodzi_bajt_w_bajt(self):
        self.assertGreater(len(ZGLOSZENIE.encode()), 255)
        self.assertEqual(nawyki.tresc(tresc_arg=ZGLOSZENIE), ZGLOSZENIE)

    def test_jedno_dlugie_slowo_bez_ukosnika_to_tresc(self):
        slowo = "ą" * 200                                    # 400 B, bez spacji, bez „/” i rozszerzenia
        self.assertEqual(nawyki.tresc(tresc_arg=slowo), slowo)

    def test_dluga_sciezka_ktorej_nie_ma_to_czytelny_blad(self):
        sciezka = "/tmp/" + "x" * 300 + ".md"
        with self.assertRaises(nawyki.ZleWejscie) as b:
            nawyki.tresc(tresc_arg=sciezka)
        self.assertIn("wygląda na plik", str(b.exception))

    def test_opis_z_za_dluga_nazwa_to_czytelny_blad(self):
        with self.assertRaises(nawyki.ZleWejscie) as b:
            nawyki.tresc(opis="r" * 400 + ".md")
        self.assertIn("nie ma pliku", str(b.exception))

    def test_krotki_plik_dalej_czytany(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("treść z pliku")
        self.assertEqual(nawyki.tresc(tresc_arg=f.name), "treść z pliku")
        Path(f.name).unlink()

    def test_cli_wpis_tresc_dluga_daje_pelny_tekst(self):
        args = cli.zbuduj_parser().parse_args(["wpis", "SF-1", "--do", "agata", "--tresc", ZGLOSZENIE])
        self.assertEqual(cli._opis_z_wejscia(args), ZGLOSZENIE)


if __name__ == "__main__":
    unittest.main()
