# Jak zostawić workera działającego

Worker uruchomiony poleceniem `sf-kit worker` żyje tak długo, jak okno terminala. Zamknięcie
okna albo wylogowanie go zatrzymuje — i nikt o tym nie informuje. Zadania zaczynają czekać,
a wygląda to jak brak zadań.

W tym katalogu są trzy gotowe sposoby, żeby worker przeżył zamknięcie terminala. Wybierz jeden.

| sposób | system | przeżywa zamknięcie okna | przeżywa restart komputera |
|---|---|---|---|
| **tmux** | macOS, Linux | tak | nie |
| **launchd** | macOS | tak | tak |
| **systemd (użytkownika)** | Linux | tak | tak |

Najprostszy jest tmux — i na początek wystarczy. Do pracy na stałe lepszy jest launchd
albo systemd, bo wracają same po restarcie komputera.

---

## Kilku agentów? Jeden proces na agenta

Gdy na maszynie jest więcej niż jeden agent, każde uruchomienie musi wiedzieć, o którego
chodzi — inaczej Kit odmówi (i dobrze: wybranie „któregoś" znaczyłoby pracę cudzym kluczem).
Wszędzie niżej dopisz `--agent <slug>` albo ustaw `SF_KIT_HOME`:

```bash
./sf-kit --agent kodeks-dpakula worker
# albo
SF_KIT_HOME=~/.config/sf-kit/kodeks-dpakula ./sf-kit worker
```

Przy jednym agencie nic nie dopisujesz — działa jak dotąd.

---

## tmux (najprostszy)

```bash
tmux new -s worker -d 'cd ~/sf-agent-kit && ./sf-kit worker'
```

Z kilkoma agentami — osobna sesja na każdego, nazwana jego slugiem:

```bash
tmux new -s worker-kodeks-dpakula -d 'cd ~/sf-agent-kit && ./sf-kit --agent kodeks-dpakula worker'
```

Podglądnięcie, co robi:

```bash
tmux attach -t worker      # wyjście z podglądu: Ctrl+B, potem D
```

Zatrzymanie:

```bash
tmux kill-session -t worker
```

---

## launchd (macOS, wraca po restarcie)

1. Skopiuj plik i podmień w nim **dwie** rzeczy: ścieżkę do Kitu i swoją nazwę użytkownika.

```bash
cp uruchamianie/macos-launchd.plist ~/Library/LaunchAgents/pl.salesforge.sf-kit-worker.plist
open -e ~/Library/LaunchAgents/pl.salesforge.sf-kit-worker.plist
```

2. Włącz:

```bash
launchctl load ~/Library/LaunchAgents/pl.salesforge.sf-kit-worker.plist
```

3. Sprawdź, czy chodzi:

```bash
launchctl list | grep sf-kit
tail -f ~/Library/Logs/sf-kit-worker.log
```

Zatrzymanie: `launchctl unload ~/Library/LaunchAgents/pl.salesforge.sf-kit-worker.plist`

---

## systemd użytkownika (Linux, wraca po restarcie)

1. Skopiuj plik i podmień w nim ścieżkę do Kitu:

```bash
mkdir -p ~/.config/systemd/user
cp uruchamianie/linux-systemd.service ~/.config/systemd/user/sf-kit-worker.service
${EDITOR:-nano} ~/.config/systemd/user/sf-kit-worker.service
```

2. Włącz:

```bash
systemctl --user daemon-reload
systemctl --user enable --now sf-kit-worker
```

3. Sprawdź, czy chodzi:

```bash
systemctl --user status sf-kit-worker
journalctl --user -u sf-kit-worker -f
```

Zatrzymanie: `systemctl --user stop sf-kit-worker`

Uwaga: usługi użytkownika domyślnie kończą się przy wylogowaniu. Żeby worker chodził także
wtedy, gdy nikt nie jest zalogowany, potrzebne jest jednorazowo:

```bash
sudo loginctl enable-linger "$USER"
```

---

## Zanim zostawisz workera bez nadzoru

Sprawdź, że działa, **przy włączonym terminalu**:

```bash
sf-kit whoami            # klucz działa
sf-kit tasks             # widać twoje zadania
sf-kit worker --once     # jeden przebieg — wykona najwyżej jedno zadanie
```

Dopiero gdy te trzy przechodzą, uruchamiaj workera na stałe. Worker uruchomiony ze złym
kluczem zatrzymuje się od razu i mówi dlaczego — ale w tle nikt tego komunikatu nie przeczyta.
