# jev-if-player

**A blind first-time playtest for browser text games (Twine, ink, any HTML5 interactive fiction).**
An AI reader plays your game from the start, clicking only what a player sees, and says every turn how much it wants to
keep reading, what it feels and why. You get a one-page report: where attention dropped and what to fix first.

Русским: слепой плейтест текстовой браузерной игры — ИИ-читатель проходит её с нуля и пишет автору одну страницу о том, где терял интерес.

## Run

```
# 1. a Chrome only for playtests (own profile, DevTools on 9333; never your everyday browser)
powershell -NoProfile -File playtest_chrome.ps1            # or: chrome --remote-debugging-port=9333 --user-data-dir=<new dir>

# 2. the reader's client: a module `jev` with call(); tell the player where it is
set JEV_CLIENT_DIR=<folder with jev.py>

# 3. play
python -X utf8 jev_if_player.py https://someone.itch.io/some-game --name some-game --turns 40 --out runs
```

Output in `runs/some-game/`: `author_report.md` (the page for the author), `report.md` (turn by turn), `turns.jsonl`.

Options: `--port N` (or `JEV_IF_CHROME_PORT`) for another Chrome port; `--min-turns N` offers «stop» only from turn N;
`JEV_IF_OUT` sets the default output folder. Port 9222 is refused unless you pass `--shared-chrome`.

## Example

A two-list logic puzzle where the reader picks the right answers and then turns to «Hint»: the tester presses
«Submit answer» for it once, and both reports say the tester pressed it, not the reader (`tests/select_hint.html`).

## What it does not do

- It is not a person. Its feelings are a model's answers to the same questions each turn: a careful first reader's
  signal, not a verdict. A human playtest still sees things this cannot.
- It plays one run, from the start. No saves, no second route.
- It reads only what is visible as text and clickable; canvas games, parser games and printable games are out of reach.
- Only the game's own text is sent to the reader's server.

## Tests

```
set JEV_IF_CHROME_PORT=9333
python -X utf8 -m unittest tests.test_jev_if_player
```

The end-to-end tests skip loudly when no Chrome listens on that port; a headless Chrome works
(`chrome --headless=new --remote-debugging-port=9334 --user-data-dir=<new dir>`). They use a stand-in for the reader:
no network, no credits.

MIT.
