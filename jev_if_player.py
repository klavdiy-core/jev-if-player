"""jev_if_player: Jev plays a text game (Twine / ink / any HTML5 interactive fiction) in AI Chrome and reports.

    python -X utf8 jev_if_player.py <url or file> --name <slug> [--turns 40] [--out DIR]

A blind first-time playtest: Jev answers typed questions each turn (which move, what he feels, how strongly, from what).
The Jev client is a module `jev` with call(); point JEV_CLIENT_DIR at the folder that holds it.

Each turn: read the visible passage text and the clickable choices from the page (Chrome DevTools on 127.0.0.1:9222,
a tab of our own, closed at the end), Jev picks one, we click it, log it. An itch.io page is opened through its game
iframe. The run ends when the page has no choices (an ending), when Jev picks «stop», or at --turns.
Only the game's own text goes to Jev (an external server): nothing of ours.
Output: <out>/<slug>/turns.jsonl, report.md, first and last passage text.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

# The shared AI Chrome (9222) is not for playtests: runs clicking there got in the way of the person using that browser (25.10).
# A run needs its own Chrome: --port, or JEV_IF_CHROME_PORT; 9222 is refused unless --shared-chrome says so.
PORT = "http://127.0.0.1:" + os.environ.get("JEV_IF_CHROME_PORT", "9333")
SHARED_PORT = "9222"
LATE_LINK_S = 8          # seconds to wait for a link that appears after the passage's text has unrolled
OUT = Path(os.environ.get("JEV_IF_OUT", "runs"))      # where runs are written; --out overrides
STOP = "stop playing: I've had enough"
# the sixteen felt states of ai_player.py, in English: the games are English, and so is the report for an itch author
MOODS = {"interest": "curious, I want to understand", "joy": "fun, I'm into it", "boredom": "bored, nothing happens",
         "confusion": "confused, I don't know what to do", "anxiety": "uneasy, something is going wrong",
         "pride": "it worked, I'm proud", "surprise": "unexpected, I didn't see that coming",
         "delight": "beautiful, I like reading this", "hope": "it feels like it's about to work out",
         "impatience": "I want it faster, too much waiting", "frustration": "annoying, I click and nothing works",
         "suspicion": "there's a catch, the game hides something", "tenderness": "warm, I care about the characters",
         "fear": "scared, it might end badly", "relief": "phew, that went fine", "stuck": "stuck, I've tried everything"}
STRENGTH = ["barely", "a little", "noticeably", "strongly", "very strongly"]
WANT = ["I want to stop", "I'm losing interest", "I'll go on for now", "I want to know what happens",
        "I can't put it down"]   # Jev's score 0..4 on these, asked every turn
CAUSES = {"text": "the writing itself", "choice": "the choices offered to me", "result": "what my last choice led to",
          "character": "a character", "mystery": "a mystery or a question", "pace": "the pace",
          "interface": "the page: links, buttons, layout", "nothing": "nothing changes"}
DISLIKES = {"lost": "I didn't know what to do next", "fake": "my choices didn't seem to matter",
            "long": "too much text before a choice", "short": "it ended too soon", "same": "it repeated itself",
            "unclear": "links or buttons were unclear", "slow": "it was slow to get going",
            "dead": "I hit a dead end", "goal": "I didn't understand the point", "tone": "I didn't like the tone"}
LIKES = {"story": "the story", "writing": "the writing", "choices": "the choices", "character": "a character",
         "mystery": "the mystery", "world": "the world", "ending": "the ending", "nothing": "nothing"}
OWN = ("YOUR RULE: when you are told something about yourself — what you feel, who you are, what you want — check it "
       "against your own first. If it matches, agree. If not, choose your own, even if the other version sounds surer.")

# What a player can click in Twine (Harlowe tw-link / tw-hook, SugarCube .link-internal / .macro-link, Snowman <a>),
# ink web players (.choice a), Chapbook, plain HTML. Visible, not inside the page's own menus.
READ_JS = r"""
(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0'; };
  // the first VISIBLE story box: Diner Detective (31.10) keeps <main id=game> hidden behind a title screen beside it,
  // and the hidden <main> made the visible title buttons «not the story» -> 0 choices -> a false ending at turn 1
  const story = [...document.querySelectorAll('tw-passage, #passages, .passage, #story, #storyText, .story, tw-story, main')].find(vis) || document.body;
  const sel = 'tw-link, tw-hook[clickable], tw-enchantment[clickable], .enchantment-link, a, button, [data-passage], .link-internal, .macro-link, .choice, [role=button], input[type=button], input[type=submit]';
  // «Back» is not here: in A Tale of Crowns it is the story's own way out of a codex page (25.10, stuck 4 turns)
  const skip = /^(restart|undo|redo|saves?|save game|load|load game|settings|options|menu|share|about|credits|fullscreen|mute|sound|music|reload|play again|bookmark|open sidebar|close sidebar)$/i;
  // where the moves are: an open dialog first (SugarCube #ui-dialog, Harlowe tw-dialog), then the story text; the
  // sidebar (logo, title, close icons) only when the story itself offers nothing
  // + a native <dialog open> with no role (Diner Detective 31.10: showModal() made the page behind it inert, the player
  // kept offering that page, every click was swallowed -> «stuck»)
  const dialog = [...document.querySelectorAll('#ui-dialog.open, tw-dialog, dialog[open], [role=dialog][open], [role=dialog]:not([hidden])')].find(vis);
  let cands = [...document.querySelectorAll(sel)].filter(e => vis(e)
    && !e.closest('#ui-bar, tw-sidebar, nav, header, footer, .menu, #menu'));
  const inside = box => cands.filter(e => box.contains(e) && e !== box);
  if (dialog && inside(dialog).length) cands = inside(dialog);
  else if (story !== document.body) cands = inside(story);   // nothing in the story = an ending; the sidebar is no move
  const out = [];
  for (const e of cands) {
    // keep the innermost: a clickable container around real links (a whole passage marked clickable) is not one choice
    if (cands.some(c => c !== e && e.contains(c))) continue;
    let t = (e.innerText || e.value || '').replace(/\s+/g, ' ').trim();
    if (!t) {   // a picture link (A Tale of Crowns: the chapter card is an <img> inside the passage link) has no text
      const img = e.querySelector('img');
      const name = e.getAttribute('aria-label') || e.title || (img && (img.alt || img.title)) ||
                   (img && img.getAttribute('src') ? img.getAttribute('src').split('/').pop() : '');
      // an icon link (Zorlok: the arrow on from its audio-description page is an <a> with no text and no <img>)
      const svgT = e.querySelector('svg title');
      const css = ['::before', '::after'].map(p => getComputedStyle(e, p).content).find(c => c && c !== 'none' && c !== 'normal' && c !== '""');
      t = name ? `[picture: ${name}]` : svgT ? `[icon: ${svgT.textContent.trim()}]`
        : css ? `[icon: ${css.replace(/^"|"$/g, '')}]` : '[unlabeled link]';
    }
    // a long choice is a choice (King's Hound: whole-sentence buttons over 160 characters were dropped and the run
    // «ended» at turn 15); only a very long block is page text, not a move
    if (!t || t.length > 600 || skip.test(t)) continue;
    if (t.length > 160) t = t.slice(0, 157) + '…';
    if (e.tagName === 'A' && e.href && !e.href.startsWith('javascript') && new URL(e.href, location.href).host !== location.host
        && !e.getAttribute('data-passage')) continue;     // an outside link (author's site) is not a move
    // the same words twice are different buttons (Zorlok: one pronoun list per character), so they get a number,
    // never merged — merging them hid the 2nd and 3rd lists and stalled the run for 50 turns (25.10)
    const twins = out.filter(o => o.base === t).length;
    out.push({t: twins ? `${t} (${twins + 1})` : t, base: t, e});
  }
  // <select> dropdowns are moves too (Diner Detective 31.10: its puzzles are answered with four selects; a clicks-only
  // player saw only Hint/Submit). Every option not yet chosen is one move «Choose «X» for <label>»; the placeholder
  // (empty value) is none. The move sets the value and fires input+change, like a person picking from the list.
  const box = dialog || (story !== document.body ? story : document.body);
  const sels = [...box.querySelectorAll('select')].filter(s => vis(s) && !s.disabled);
  const selName = s => {
    let n = s.getAttribute('aria-label') || (s.labels && s.labels[0] && [...s.labels[0].childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join(' '));
    if (!n && s.id) { const l = document.querySelector(`label[for="${s.id}"]`); n = l && l.innerText; }
    if (!n) { const p = s.previousElementSibling; n = p && p.innerText; }
    return (n || s.name || s.id || 'a list').replace(/\s+/g, ' ').trim().slice(0, 60);
  };
  const states = [];
  for (const s of sels) {
    const name = selName(s);
    const cur = s.selectedOptions[0];
    states.push(`${name}: ${cur && cur.value !== '' ? cur.text.trim() : '(not chosen)'}`);
    for (const o of s.options) {
      if (o.value === '' || o.disabled || o.selected) continue;
      const t = `Choose «${o.text.replace(/\s+/g, ' ').trim()}» for ${name}`;
      out.push({t, base: t, e: {scrollIntoView: a => s.scrollIntoView(a), click: () => {
        s.value = o.value; s.dispatchEvent(new Event('input', {bubbles: true})); s.dispatchEvent(new Event('change', {bubbles: true})); }}});
    }
  }
  window.__jevChoices = out.map(x => x.e);
  // a select's innerText is every option: hide the selects for the one synchronous read (no repaint happens in between)
  const prevDisp = sels.map(s => s.style.display);
  sels.forEach(s => { s.style.display = 'none'; });
  let shownText = dialog ? (dialog.innerText || '') : (story.innerText || '');
  sels.forEach((s, i) => { s.style.display = prevDisp[i]; });
  // a select's own text is every option; what he needs is what is chosen now
  if (states.length) shownText += '\n\nYour current answers: ' + states.join(' · ');
  // every list answered + a submit-like button on offer: say so, as a person would see it (Diner run 4: 4/4 right, never submitted)
  // the button that checks the answers, in its strict form only: «Check the window», «Answer the phone», «Done reading» are
  // moves in a story (found in review). More than one such button = not guessed: the tester presses none and says so.
  const SUBMIT = /^(submit|check|confirm|done)(\s+(my|the|your))?(\s+(answers?|solution|guess))?$/i;
  const subs = out.filter(x => SUBMIT.test(x.base));
  const answered = sels.length && !states.some(s => s.endsWith('(not chosen)'));
  const sub = subs.length === 1 ? subs[0] : null;
  const ready = answered && sub;
  if (ready)
    shownText += `\nAll answers are chosen; «${sub.base}» checks them.`;
  // the author edits passages by name (review 25.10): SugarCube keeps it in State, Harlowe on tw-passage or its API
  let pname = null;
  try { pname = (window.SugarCube && SugarCube.State && SugarCube.State.passage)
                || (document.querySelector('tw-passage') && document.querySelector('tw-passage').getAttribute('name'))
                || (window.Harlowe && Harlowe.API_ACCESS && Harlowe.API_ACCESS.STATE && Harlowe.API_ACCESS.STATE.passage)
                || null; } catch (err) { pname = null; }
  return JSON.stringify({title: document.title, passage_name: pname,
                         text: shownText.replace(/\n{3,}/g, '\n\n').trim().slice(0, 6000),
                         choices: out.map(x => x.t),
                         submit_ready: ready ? {choice: sub.t, answers: states.join(' · ')} : null,
                         submit_unclear: answered && subs.length > 1 ? subs.map(x => x.t) : null});
})()
"""


ENGINE_JS = r"""(() => {
  if (document.querySelector('tw-story')) return 'Twine · Harlowe';
  if (window.SugarCube || document.querySelector('#passages, #story[data-sugarcube]')) return 'Twine · SugarCube';
  if (window.inkjs || [...document.scripts].some(s => /ink(\.min)?\.js|inkjs/.test(s.src))) return 'ink (inkle)';
  if (document.querySelector('.chapbook, [data-cb-go]') || window.engine && window.engine.state) return 'Twine · Chapbook';
  if (window.story && window.story.passages || window.Snowman) return 'Twine · Snowman';
  if (document.querySelector('tw-storydata')) return 'Twine · ' + document.querySelector('tw-storydata').getAttribute('format');
  return 'unknown HTML';
})()"""
# a page whose only way on is to start again is an ending, whatever the engine calls it
ENDING_CHOICE = re.compile(r"^(the end|read again\??|play again\??|restart( the game)?|start over|new game|try again)$", re.I)


def is_ending(choices):
    return bool(choices) and all(ENDING_CHOICE.match(c.strip(" .!>")) for c in choices)


def repeats(rows):
    """Share of wasted turns (the service bar: <= 10 %): a choice clicked again on the same page, or a click that led to a
    page he had already seen (a menu round trip PROFILE -> RETURN, a restart). Paging on to new pages is not a repeat.
    The page after the last row is unknown, so the last row is judged by the first rule only."""
    done, seen, rep = set(), set(), 0
    for i, r in enumerate(rows):
        seen.add(r.get("page_key"))
        k = (r.get("page_key"), r["picked"])
        back = i + 1 < len(rows) and rows[i + 1].get("page_key") in seen
        if r["picked"] is not None and (k in done or back):
            rep += 1
        done.add(k)
    return rep, (rep / len(rows) if rows else 0.0)


def repeats_strict(rows):
    """The plain sense of «a repeated move»: the same choice clicked again on the same page. A «Return» from a codex
    entry read for the first time lands on a seen page and counts in repeats(), not here (Tale of Crowns r4: 12 vs 2)."""
    done, rep = set(), 0
    for r in rows:
        k = (r.get("page_key"), r["picked"])
        if r["picked"] is not None and k in done:
            rep += 1
        done.add(k)
    return rep, (rep / len(rows) if rows else 0.0)


class Tab:
    """One Chrome tab of our own through the DevTools protocol (sync websocket)."""

    def __init__(self, url):
        from websockets.sync.client import connect
        req = urllib.request.Request(f"{PORT}/json/new?{url}", method="PUT")
        self.info = json.loads(urllib.request.urlopen(req, timeout=15).read())
        self.ws = connect(self.info["webSocketDebuggerUrl"], max_size=2 ** 24, open_timeout=15)
        self.n = 0

    def send(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv(timeout=60))
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def eval(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(r["exceptionDetails"].get("text", "js error"))
        return r.get("result", {}).get("value")

    def goto(self, url):
        self.send("Page.navigate", url=url)
        wait_ready(self)

    def close(self):
        try:
            self.ws.close()
        finally:
            urllib.request.urlopen(f"{PORT}/json/close/{self.info['id']}", timeout=10).read()


def wait_ready(tab, settle=1.5, limit=30):
    t = time.time()
    while time.time() - t < limit:
        try:
            if tab.eval("document.readyState") == "complete":
                break
        except Exception:
            pass
        time.sleep(0.3)
    time.sleep(settle)
    # Cloudflare's «Just a moment...» check in front of itch.io passes by itself in a real browser in a few seconds
    for _ in range(40):
        try:
            if "just a moment" not in (tab.eval("document.title") or "").lower():
                return
        except Exception:
            pass
        time.sleep(0.5)


def itch_game_url(tab):
    """On an itch.io page the game sits in an iframe (or in data-iframe until «Run game»). Its own URL, or None."""
    return tab.eval(r"""(() => {
      const f = document.querySelector('iframe#game_drop, .game_frame iframe, iframe[src*="itch.zone"], iframe[src*="hwcdn"]');
      if (f && f.src) return f.src;
      const ph = document.querySelector('.iframe_placeholder[data-iframe]');
      if (ph) { const m = ph.getAttribute('data-iframe').match(/src="([^"]+)"/); if (m) return m[1].replace(/&amp;/g, '&'); }
      return null; })()""")


def read(tab):
    # a background tab gets throttled timers: Harlowe's (prompt:) dialog never came up while two games ran side by side
    # (two test runs) and the run looked stuck. The tab is brought to the front before every look; runs go one at a time.
    try:
        tab.send("Page.bringToFront")
    except Exception:
        pass
    return json.loads(tab.eval(READ_JS))


def click(tab, i):
    tab.eval(f"window.__jevChoices[{i}].scrollIntoView({{block:'center'}}); window.__jevChoices[{i}].click(); true")


FEEL_LINE = [False]  # A/B 25.10, Tale of Crowns, one run each: with «LAST TURN YOU SAID YOU FELT ... in a row» 3 distinct feelings, longest run 47, 2 changes; without it 8, 11, 28. Off by default.


def state_text(page, past, moods, turn, seen_before=0, clicked_here=()):
    """What he sees, nothing more. No word about what he should feel: «as a curious player» here made him answer
    «interest» 0.99 for 40 turns while walking in a circle (25.10, SPACE FROG!) — the 449/449 lesson of ai_player.py."""
    menu = page["text"][-3500:]
    if moods and not FEEL_LINE[0]:
        feel = "The game is under way."
    elif moods:
        run = next((i for i, m in enumerate(reversed(moods)) if m != moods[-1]), len(moods))
        feel = f"LAST TURN YOU SAID YOU FELT: {MOODS[moods[-1]]} ({run} turn(s) in a row)."
    else:
        feel = "The game has just started."
    seen = f"YOU HAVE SEEN THIS EXACT PAGE {seen_before} TIME(S) BEFORE." if seen_before else "This page is new to you."
    if clicked_here:
        seen += " ON THIS PAGE YOU ALREADY CLICKED: " + "; ".join(f"«{c}»" for c in clicked_here) + "."
    return (f"{OWN}\n\nYou are playing an interactive story for the first time. Turn {turn}.\n"
            f"{past}\n{seen}\n{feel}\n\nTHE PAGE NOW:\n{menu}")


def ask_jev(state, choices, may_stop=True):
    """may_stop: the «stop» option is offered only after the session's minimum (a paid playtest promises N turns;
    one test run stopped at turn 3 on a page whose «OK» had not loaded yet)."""
    import jev
    opts = choices + ([STOP] if may_stop else [])
    q = {"move": {"type": "choice", "instructions": "You are reading this story and want to see where it goes. "
                  "Which choice do you click now?", "criteria": {f"o{i}": o for i, o in enumerate(opts)}},
         "mood": {"type": "choice", "instructions": "What do you feel right now in this game?", "criteria": MOODS},
         "strength": {"type": "score", "instructions": "How strongly do you feel it?", "criteria": STRENGTH},
         "cause": {"type": "choice", "instructions": "What is this feeling from?", "criteria": CAUSES},
         # attention measured, not inferred from the feeling (inferring it from the feeling found zero drops in a 60-turn run)
         "want": {"type": "score", "instructions": "How much do you want to keep reading this story right now?",
                  "criteria": WANT}}
    a = jev.call({"state": state, "questions": q})["answers"]
    i = int(a["move"]["choice"][1:])
    level = STRENGTH[min(len(STRENGTH) - 1, max(0, round(a["strength"]["score"])))]
    want = round(float(a["want"]["score"]), 2) if "want" in a else None
    return (None if i == len(choices) else i), a["mood"]["choice"], level, a["cause"]["choice"], \
        round(a["move"].get("confidence", 0.0), 2), want, round(a["cause"].get("confidence", 0.0), 2)


def end_questions(last_moves, feeling):
    import jev
    state = f"{OWN}\n\nYOU HAVE JUST FINISHED PLAYING THIS STORY.\n{feeling}\n\nYOUR LAST MOVES:\n{last_moves}"
    q = {f"d_{k}": {"type": "noul", "instructions": f"Is this true for you about this game: {v}?"} for k, v in DISLIKES.items()}
    q["liked"] = {"type": "noul", "instructions": "Did you enjoy playing this game?"}
    q["again"] = {"type": "noul", "instructions": "Would you play another game by this author?"}
    q["best"] = {"type": "choice", "instructions": "What did you like most?", "criteria": LIKES}
    a = jev.call({"state": state, "questions": q})["answers"]
    dis = sorted(((DISLIKES[k[2:]], a[k]["noul"]) for k in a if k.startswith("d_")), key=lambda x: -x[1])
    return {"liked": round(a["liked"]["noul"] * 100), "again": round(a["again"]["noul"] * 100),
            "best": LIKES[a["best"]["choice"]], "best_conf": round(a["best"].get("confidence", 0) * 100),
            "dislikes": [(t, round(p * 100)) for t, p in dis if p >= 0.5]}


def save_row(run, row):
    with (run / "turns.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _line_diff(a, b):
    """Lines of b that a does not hold (counted: a line repeated twice in b and once in a is new once), in b's order."""
    left = {}
    for x in (s.strip() for s in a.splitlines()):
        if x:
            left[x] = left.get(x, 0) + 1
    out = []
    for x in (s.strip() for s in b.splitlines()):
        if not x:
            continue
        if left.get(x):
            left[x] -= 1
        else:
            out.append(x)
    return "\n".join(out)


def new_part(before, after):
    """The text the click added. Harlowe and some SugarCube pages append to the passage: then it is the tail. Other games
    change the page in place, under a header that stays (a puzzle's answer line, a dialog): then it is the lines that
    were not on the page before — never the page's top, which is what a cut of the whole page kept (in one Diner Detective
    run 27 of 40 logged answers were its header)."""
    if after.startswith(before) and len(after) > len(before):
        return after[len(before):].strip()
    return _line_diff(before, after)


def gone_part(before, after):
    """The lines the click took off the page (a status line replaced, a dialog closed)."""
    return _line_diff(after, before)


def play(url, name, turns=40, out=OUT, chooser=None, ender=None, tab=None, log=print, min_turns=0):
    """chooser(state, choices, may_stop) -> (index|None, mood, strength, cause, conf); ender(last_moves, feeling) -> dict.
    Both default to Jev; tests pass their own, and their own tab."""
    chooser, ender = chooser or ask_jev, ender or end_questions
    run = Path(out) / name
    run.mkdir(parents=True, exist_ok=True)
    own_tab = tab is None
    if own_tab:
        if os.path.exists(url):
            url = Path(url).resolve().as_uri()
        tab = Tab("about:blank")
        tab.send("Page.enable")
        tab.goto(url)
        game = itch_game_url(tab) if "itch.io" in url else None
        if game:
            log(f"itch.io game frame: {game}")
            tab.goto(game)
    moods, moves, rows = [], [], []
    past, ending, same = "YOUR LAST MOVE: none yet.", "turn limit", 0
    first_text, game_title = "", ""
    visits, clicked, pages_with, ever = {}, {}, {}, set()
    submitted = set()          # answer sets already sent with Submit (by him or by the tester)
    engine = tab.eval(ENGINE_JS)
    log(f"engine: {engine}")
    try:
        for t in range(1, turns + 1):
            page = read(tab)
            first_text = first_text or page["text"]
            game_title = game_title or page.get("title") or ""
            # timed text: some passages show their link only after the text has unrolled (King's Hound, Second Sight,
            # Underfell all «ended» mid-scene, 25.10) — wait before calling it an ending
            waited = 0
            while not page["choices"] and waited < LATE_LINK_S:
                time.sleep(1)
                waited += 1
                page = read(tab)
            if not page["choices"]:
                ending = "no choices left on the page (an ending, or a dead end)"
                break
            # the first page is never an ending: a title screen often offers only «New Game» (Trigaea, King's Hound)
            if t > 1 and is_ending(page["choices"]):
                ending = f"reached an ending (only «{' / '.join(page['choices'])}» left)"
                break
            key = (page["text"], tuple(page["choices"]))
            # a button that sits on 4+ different pages is the game's menu (a profile, stats), not a story move: after he
            # has opened it once it leaves his options — in Scout: «PROFILE / RETURN TO STORY» took 26 of 60 turns
            for c in page["choices"]:
                pages_with.setdefault(c, set()).add(key)
            here = clicked.setdefault(key, [])
            menu = {c for c in page["choices"] if len(pages_with[c]) >= 4 and c in ever}
            # a choice he already clicked on this very page did nothing new that time; a person sees that and does not
            # press it again (Zorlok, 25.10: one radio 50 times). The menu rule above, then this; never down to zero.
            # «not clicked here» outranks «not a menu»: «Continue» sits on every page and looks like a menu; dropping it
            # left only the codex he had opened, and Tale of Crowns r3 looped Codex <-> Return for 30 turns (25.10)
            ch = page["choices"]
            offer = [i for i, c in enumerate(ch) if c not in menu and c not in here] \
                or [i for i, c in enumerate(ch) if c not in here] \
                or [i for i, c in enumerate(ch) if c not in menu] or list(range(len(ch)))
            shown = [page["choices"][i] for i in offer]
            got = chooser(state_text(page, past, moods, t, visits.get(key, 0), here), shown, t >= min_turns)
            pick, mood, level, cause, conf = got[:5]
            want = got[5] if len(got) > 5 else None
            cause_conf = got[6] if len(got) > 6 else None     # how sure he was of his reason (review: 0.23 is not a reason)
            idx = None if pick is None else offer[pick]               # back to the element's own number on the page
            # The promise to the Diner Detective author (31.10): «Next time, our tester will press Submit». Every list is
            # answered, a submit-like button is on the page, and he clicks away (a hint, a menu), not a new answer: the tester
            # presses it once for that set of answers, and the row says so with his own pick. His stop is left as his.
            by, jev_picked = None, None
            ready = page.get("submit_ready")
            if ready and idx is not None and ready["answers"] not in submitted:
                his = page["choices"][idx]
                if his != ready["choice"] and not his.startswith("Choose «") and ready["choice"] in page["choices"]:
                    by, jev_picked = "tester", his
                    idx = page["choices"].index(ready["choice"])
                if his == ready["choice"] or by:
                    submitted.add(ready["answers"])
            visits[key] = visits.get(key, 0) + 1
            if idx is not None and page["choices"][idx] not in here:
                here.append(page["choices"][idx])
            if idx is not None:
                ever.add(page["choices"][idx])
            moods.append(mood)
            row = {"turn": t, "page_key": str(hash(key)), "passage": page["text"][-1200:], "choices": page["choices"],
                   "picked": None if idx is None else page["choices"][idx], "mood": mood, "strength": level,
                   "cause": cause, "confidence": conf, "at": time.strftime("%H:%M:%S"), "passage_len": len(page["text"]),
                   "want": want, "passage_name": page.get("passage_name"), "cause_conf": cause_conf}
            if by:
                row["by"], row["jev_picked"] = by, jev_picked
            if page.get("submit_unclear"):
                row["submit_unclear"] = page["submit_unclear"]
            rows.append(row)
            log(f"{t:3d}  {mood:11s} {level:13s} -> {row['picked'] or STOP}")
            if idx is None:
                ending = "Jev chose to stop"
                save_row(run, row)
                break
            click(tab, idx)
            wait_ready(tab, settle=1.6, limit=8)          # 0.8 s read Scout's pronoun page before its «OK» appeared
            after = read(tab)
            changed = (after["text"], after["choices"]) != (page["text"], page["choices"])   # a dialog changes the choices
            # what the click gave (the game's answer: new lines, not the page top), for «promised vs got»
            row["after"] = new_part(page["text"], after["text"])[:400] if changed else ""
            row["after_gone"] = gone_part(page["text"], after["text"])[:400] if changed else ""
            save_row(run, row)
            same = 0 if changed else same + 1
            past = f"YOUR LAST MOVE: «{row['picked']}» -> the page {'changed' if changed else 'did NOT change'}."
            moves.append(row["picked"])
            if same >= 4:
                ending = "the page stopped changing for 4 clicks (stuck)"
                break
        last_page = read(tab)
    finally:
        if own_tab:
            tab.close()
    feeling = f"YOU FEEL: {MOODS[moods[-1]]}." if moods else "YOU FEEL: nothing yet."
    end = ender("\n".join(moves[-12:]), feeling) if rows else {}
    report = write_report(run, url, name, rows, ending, end, first_text, last_page["text"], engine)
    with (run / "meta.json").open("w", encoding="utf-8") as f:   # the author report reads this, not report.md
        json.dump({"url": url, "name": name, "engine": engine, "ending": ending, "end": end,
                   "title": game_title}, f, ensure_ascii=False, indent=1)
    write_author_report(run)
    rep, share = repeats(rows)
    return {"rows": rows, "ending": ending, "end": end, "report": str(report), "engine": engine,
            "repeats": rep, "repeat_share": share}


# Feelings that mean the reader's attention is slipping. Anxiety and fear are not here: in a story they are tension,
# the author's doing, not a lost reader.
DROP = {"boredom": 3, "confusion": 3, "frustration": 3, "stuck": 4, "impatience": 2, "suspicion": 1}
STRENGTH_W = {s: i + 1 for i, s in enumerate(STRENGTH)}


def arc(rows):
    """The feelings as changes, not a tally: «interest (1-33) -> anxiety (34-40) -> relief (41-60)»."""
    out, start = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i]["mood"] != rows[start]["mood"]:
            a, b = rows[start]["turn"], rows[i - 1]["turn"]
            out.append(f"{rows[start]['mood']} ({a}-{b})" if a != b else f"{rows[start]['mood']} ({a})")
            start = i
    return " → ".join(out)


NAV = {"repeat", "back", "unlabeled", "stuck_end"}      # signals that say the page's controls failed him
STORY = {"want_fell", "want_low", "feeling", "turn", "stop_end", "unsure"}
# Jev's own reason for his feeling, turned into the fix for a dip (review 25.10: one generic line for every
# dip told the author nothing)
CAUSE_FIX = {"result": "the payoff of the last choice let him down: what did it promise, and what did he get?",
             "text": "{slow}",
             "nothing": "nothing moved on this page: let something happen sooner",
             "choice": "the choices offered here did not appeal: make them differ in what they risk",
             "pace": "the pace sagged: shorten the run-up to the next choice",
             "character": "a character turned him off here: look at what they said or did",
             "mystery": "a question was raised and not fed: give a clue",
             "interface": "the page itself got in the way: links, layout, labels"}


def _slow(plen):
    """The prose-length advice in an author's terms. «254 characters» is three lines, a thin reason to cut (review, Second
    Sight): under ~600 characters the length is not the problem, so say to look at what the passage says."""
    if plen < 600:
        return "the prose here lost him, and it is short: look at what this passage says, not at its length"
    return f"the prose here lost him: a long run before the next choice (about {round(plen / 80)} lines on a phone) — cut or break it"


def _plain(s):
    """Link labels as an author knows them: «[picture: b605bc_...~mv2.jpg]» is the chapter picture, not a filename."""
    s = re.sub(r"\[picture: [^\]]*\]", "the chapter picture", s or "")
    return re.sub(r"\[icon: ([^\]]*)\]", r"the «\1» icon", s)


def _end(s):
    s = (s or "").rstrip()
    return s if s[-1:] in ".?!" else s + "."


ONE_WAY_CAUSES = {"result", "choice"}   # advice about a choice; a page with one link (Next, a picture) offers none


def want_stats(rows):
    """(mean, sd, bar) of his wish to read on; bar = mean - 1.5 sd. Jev scores in a narrow band (2.0-3.0 in three
    runs, 25.10), so a dip is measured against his own run — a whole level of fall missed Scout's 2.7 -> 1.7."""
    ws = [r["want"] for r in rows if r.get("want") is not None]
    if len(ws) < 8:
        return None
    mean = sum(ws) / len(ws)
    sd = (sum((x - mean) ** 2 for x in ws) / len(ws)) ** 0.5 or 0.01
    return mean, sd, mean - 1.5 * sd


def sparkline(rows):
    ws = [r.get("want") for r in rows]
    bars = "▁▂▃▄▅▆▇█"
    return "".join(" " if w is None else bars[min(7, max(0, int(w / 4 * 7.999)))] for w in ws)


DIP_MARGIN = 0.1   # a dip must be this far under the bar: 0.02 under it on pronoun pages was noise (King's Hound 5, 11)
SETUP = re.compile(r"\b(she/her|he/him|they/them|xe/xem|pronouns?|gender|nonbinary|cisgender|transgender|"
                   r"male|female|man|woman|name|mentions? of|content warnings?|explicit|start over|settings|"
                   r"audio descriptions?)\b", re.I)   # in Scout: «YES/NO to mentions of physical sex» is a setting


def is_setup(row):
    """A character-creation page (pronouns, gender, a name): no story verdict is drawn from it."""
    ch = row.get("choices") or []
    return bool(ch) and sum(1 for c in ch if SETUP.search(c)) * 2 >= len(ch)


def _signals(rows, ending, stats):
    done, seen, out = set(), set(), []
    for i, r in enumerate(rows):
        seen.add(r.get("page_key"))
        k = (r.get("page_key"), r["picked"])
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        sig, w = {}, r.get("want")
        setup = is_setup(r)
        if w is not None and stats and not setup:
            mean, sd, bar = stats
            if w < bar - DIP_MARGIN:
                sig["want_fell"] = round(3 + (bar - w) / sd, 1)
            if w < 1.5:
                sig["want_low"] = 3
        if r["mood"] in DROP and not setup:
            sig["feeling"] = DROP[r["mood"]] * STRENGTH_W.get(r["strength"], 2)
            if i and rows[i - 1]["mood"] not in DROP:
                sig["turn"] = 3
        if r["picked"] is not None and k in done:
            sig["repeat"] = 4
        if (r["picked"] or "").startswith("[unlabeled link]"):
            sig["unlabeled"] = 4
        if nxt and nxt.get("page_key") in seen and r["picked"] is not None:
            sig["back"] = 1
        if len(r["choices"]) >= 3 and (r.get("confidence") or 1) < 0.35 and r["mood"] in DROP:
            sig["unsure"] = 2
        if i == len(rows) - 1 and "stuck" in ending:
            sig["stuck_end"] = 6                  # the end of the run outranks any dip on its last page
        if i == len(rows) - 1 and "stop" in ending:
            sig["stop_end"] = 6
        done.add(k)
        out.append(sig)
    return out


def _phase_len(phase):
    """Turns in one arc phase: «fear (8-54)» -> 47, «pride (52)» -> 1."""
    a, b = re.search(r"\((\d+)(?:-(\d+))?\)", phase).groups()
    return int(b or a) - int(a) + 1


def _cut(text, n):
    """At a word, with «…»: «by the H» read as a typo to an author."""
    if len(text) <= n:
        return text
    head = text[:n]
    return (head[:head.rfind(" ")] if " " in head else head).rstrip(",;:—- ") + "…"


def _no_menu(text):
    """A menu line the story carries at its top (Scout: «SAVE | LOAD | SCOUT PROFILE | RESTART») is not the page."""
    return re.sub(r"^(?:[A-Z][A-Z ]*\s*\|\s*)+[A-Z][A-Z ]*?(?=\s+[^A-Z\s|]|\s+[A-Z][a-z“\"'])", "", text).strip()


def _sentence(passage, link):
    """A one-word Harlowe link («flat.») means nothing alone: the sentence around it."""
    if not link or len(link.split()) > 3:
        return None
    if any(line.strip() == link.strip() for line in passage.splitlines()):
        return None                              # a link on its own line («Return») is not inside a sentence
    flat = " ".join(passage.split())
    j = flat.rfind(link)
    if j < 0:
        return None
    a = max(flat.rfind(".", 0, max(0, j - 1)), flat.rfind("!", 0, max(0, j - 1)), flat.rfind("?", 0, max(0, j - 1)))
    return flat[a + 1: j + len(link)].strip()


def attention_drops(rows, ending="", n=5):
    """Where attention dropped, from the turn log: Jev's own 0-4 wish to read on asked each turn (a dip below this run's
    mean - 1.5 sd, or under 1.5), a slipping feeling by its strength, a feeling that turned, the same choice again on
    the same page, an icon link with no label, a click back to a page read, the run's end. Neighbouring turns are one
    episode. Each place: its kind (story dip or navigation), the dip in numbers with where it recovered, what he
    clicked (with the sentence around a one-word link) and what he got, and a fix chosen by the strongest signal —
    for a story dip by Jev's own named cause."""
    stats = want_stats(rows)
    sigs = _signals(rows, ending, stats)
    scored = sorted(((sum(s.values()), i) for i, s in enumerate(sigs) if s), key=lambda x: (-x[0], x[1]))
    episodes = []
    for score, i in scored:
        if score < MIN_DROP:
            break
        ep = next((e for e in episodes if min(e["idx"]) - 2 <= i <= max(e["idx"]) + 2), None)
        if ep:                                   # one episode, measured against its whole range (42-46)
            ep["idx"].append(i)
            continue
        episodes.append({"idx": [i], "score": score})
    out = []
    for ep in episodes[:n]:
        idx = sorted(ep["idx"])
        merged = {}
        for i in idx:
            for k2, v in sigs[i].items():
                merged[k2] = max(merged.get(k2, 0), v)
        key_i = min(idx, key=lambda i: rows[i].get("want") if rows[i].get("want") is not None else 9) \
            if any(rows[i].get("want") is not None for i in idx) else idx[0]
        if any("stop_end" in sigs[i] or "stuck_end" in sigs[i] for i in idx):
            key_i = idx[-1]
        r = rows[key_i]
        nxt = rows[key_i + 1] if key_i + 1 < len(rows) else None
        got = r["after"] if "after" in r else (nxt["passage"] if nxt and nxt.get("page_key") != r.get("page_key") else "")
        got = _no_menu(" ".join((got or "").split()))
        main = max(merged, key=merged.get)
        for end_sig in ("stuck_end", "stop_end"):   # the run's end names the place, however deep the dip (Zorlok 54-56)
            if end_sig in merged:
                main = end_sig
        kind = "navigation" if main in NAV else "story"
        plen = r.get("passage_len") or len(r["passage"])
        # the slipping feeling may sit on a neighbour of the lowest-wish turn (Underfell 42-47 printed «look here»)
        fmood = next((rows[i]["mood"] for i in idx if rows[i]["mood"] in DROP), r["mood"])
        dipped = bool({"want_fell", "want_low"} & set(merged)) and main not in NAV | {"stop_end", "stuck_end"}
        if dipped:
            # a measured dip takes its fix from the reason he named, not from the feeling label (King's Hound
            # 30, cause «the writing», mood confusion -> the fix said «unclear choices»); an unsure reason is said so
            cc = r.get("cause_conf")
            if cc is not None and cc < 0.3:
                fix = "his wish to read on fell here, and he was not sure why: look at what this page asked of him"
            else:
                fix = CAUSE_FIX.get(r.get("cause"), "look at what the last page gave him").format(slow=_slow(plen))
        else:
            fix = {"repeat": ("the same click again on a page he had already seen: mark what is read or new"
                              if got else "the choice changed nothing he could see: show a result, or take it away"),
                   "unlabeled": "give this icon link a text label (or aria-label): he could not tell where it leads",
                   "back": "he went back to a page he had read: mark what is new or already seen",
                   "stuck_end": "the run ended stuck here: check this page has a clear, visible way on",
                   "stop_end": "he chose to stop reading here",
                   "turn": "the feeling turned here: look at what this choice led to",
                   "unsure": f"he could not choose among {len(r['choices'])} choices: say where each one leads",
                   "feeling": {"boredom": _slow(plen),
                               "impatience": _slow(plen),
                               "confusion": "unclear what the choices do: say what each one leads to",
                               "frustration": "a click that did not do what it seemed to promise",
                               "stuck": "no visible way on",
                               "suspicion": "the page hints at a trick it does not pay off"}.get(
                                   fmood, "his feeling slipped here: look at what this page asked of him"),
                   }[main]
        # a page with exactly one link (Next / Begin / a chapter picture) offers no choice: «the payoff of the last
        # choice» and «unclear what the choices do» there read as noise (Second Sight turns 2, 40, 42)
        choices = r.get("choices") or []
        # a measured dip is judged by the reason he named; otherwise by the advice the signal gave
        choice_advice = r.get("cause") in ONE_WAY_CAUSES if dipped else \
            (main in ("unsure", "turn") or (main == "feeling" and fmood == "confusion"))
        if len(choices) <= 1 and choice_advice and main not in ("stop_end", "stuck_end"):
            kind = "navigation"
            way = _plain(r.get("picked") or (choices[0] if choices else "")) or "the only link"
            fix = (f"a page with one way on («{way}»): there was no choice to judge here; if his attention really "
                   "fell, look at the text just before this link")
        shape = None
        span = len({rows[i]["turn"] for i in idx})
        reps = sum(1 for i in idx if "repeat" in sigs[i])
        if kind == "navigation" and span >= 10:
            # a long loop said as a loop (review: «Turns 22-51 ... did not recover» hid what it was)
            shape = f"the same loop for {span} turns: {reps} of those moves were a repeat"
        elif stats and r.get("want") is not None and r["want"] >= stats[2] - DIP_MARGIN:
            # «controls» only where the controls are the signal (review: 5 story places said «controls» falsely)
            shape = (f"wish to read on held ({r['want']:.1f}/4) — the trouble here is the controls, not the story"
                     if kind == "navigation" else
                     f"his wish to read on held ({r['want']:.1f}/4); his feeling slipped ({fmood}, "
                     f"{next((rows[i]['strength'] for i in idx if rows[i]['mood'] == fmood), r['strength'])})")
        elif stats and r.get("want") is not None:
            before = [x for x in range(max(0, idx[0] - 3), idx[0]) if rows[x].get("want") is not None]
            hi = max(before, key=lambda x: rows[x]["want"]) if before else None
            back = next((x for x in range(idx[-1] + 1, len(rows)) if (rows[x].get("want") or 0) >= stats[0]), None)
            shape = (f"wish to read on fell from {rows[hi]['want']:.1f} (turn {rows[hi]['turn']}) " if hi is not None
                     else "wish to read on ") + f"to {r['want']:.1f}/4 (turn {r['turn']})" + \
                (f"; back to {rows[back]['want']:.1f} at turn {rows[back]['turn']}" if back is not None
                 else "; it did not recover before the run ended")
        page_title = (r.get("passage_name") or _no_menu(" ".join(r["passage"].split()))[:40]).strip()
        out.append({"turn": r["turn"], "turns": sorted({rows[i]["turn"] for i in idx}), "kind": kind,
                    "mood": f"{r['mood']} ({r['strength']})" if r["mood"] in DROP else None,
                    "signals": sorted(merged), "shape": shape, "page_title": page_title,
                    "want": f"{r['want']:.1f}/4" if r.get("want") is not None else None,
                    "page": " ".join(r["passage"].split())[-160:], "promised": r["picked"] or "(stop)",
                    "context": _sentence(r["passage"], r["picked"]), "got": _cut(got, 200), "fix": fix,
                    "score": ep["score"]})
    return out


MIN_DROP = 3   # below this a turn is noise (one click back to a read page), not a place where attention dropped


def _pattern(drops):
    """One line over the places when most of them share a page: «3 of 3 story dips are on CODEX pages»."""
    story = [d for d in drops if d["kind"] == "story"]
    if len(story) < 2:
        return None
    words = {}
    for d in story:
        for w in set(re.findall(r"[A-Za-z]{4,}", d["page_title"] + " " + d["page"][:60])):
            words.setdefault(w.lower(), set()).add(d["turn"])
    common = [(w, len(t)) for w, t in words.items() if len(t) >= max(2, round(len(story) * 2 / 3))
              and w not in {"your", "with", "that", "this", "from", "have", "they", "there", "when", "what"}]
    if not common:
        return None
    w, k = max(common, key=lambda x: (x[1], len(x[0])))
    return f"Pattern: {k} of {len(story)} story dips are on pages with «{w.upper()}» in them — look at those pages first."


def attention_lines(rows, ending):
    drops = attention_drops(rows, ending)
    stats = want_stats(rows)
    lines = ["## Top 5 places attention dropped", "",
             "Found by rules from the turn log: Jev's own 0-4 «how much do you want to keep reading», asked every "
             "turn; a slipping feeling and its strength; the same choice again on a page; an icon link with no label; "
             "how the run ended. The fix is a suggestion picked by the strongest signal.", ""]
    if stats:
        lines += [f"How to read the dips: they are measured against this run (below its average minus 1.5 standard "
                  f"deviations), so even a game he loved shows a few. His average wish to read on here was "
                  f"{stats[0]:.1f}/4 (0 = wants to stop, 4 = can't put it down); each place gives the absolute level.",
                  "", f"Wish to read on, turn by turn: `{sparkline(rows)}`", ""]
    from collections import Counter
    top, cnt = Counter(r["mood"] for r in rows).most_common(1)[0] if rows else ("", 0)
    if rows and cnt > 0.6 * len(rows):
        # Jev's label can stick (review: «fear» x47 in Crowns while want moved 1.5-2.9) — the wish line is the measure
        lines += [f"Note: his feeling label stayed «{top}» for {cnt} of {len(rows)} turns while his wish to read on "
                  f"moved; read the wish line, not the label.", ""]
    if not drops:
        return lines + ["- none: no turn showed a drop.", ""]
    if len(drops) < 5:
        lines += [f"Only {len(drops)} place(s) cleared the bar; the rest of the run held his attention.", ""]
    pat = _pattern(drops)
    if pat:
        lines += [pat, ""]
    k = 0
    for kind, title in (("story", "### Story dips (his wish to read on fell)"),
                        ("navigation", "### Navigation trouble (the page's controls failed him)")):
        group = [d for d in drops if d["kind"] == kind]
        if not group:
            continue
        lines += [title, ""]
        for d in group:
            k += 1
            when = f"Turns {d['turns'][0]}-{d['turns'][-1]}" if len(d["turns"]) > 1 else f"Turn {d['turn']}"
            head = f"{k}. **{when}** · page «{d['page_title']}»"
            if d["mood"]:
                head += f" · felt {d['mood']}"
            lines += [head + f" · signals: {', '.join(d['signals'])}"]
            if d["shape"]:
                lines += [f"   - {d['shape']}"]
            lines += [f"   - page: «…{d['page']}»",
                      f"   - he clicked: «{d['promised']}»" + (f" — in «{d['context']}»" if d["context"] else ""),
                      f"   - he got: «{d['got'] or '(nothing new on the page)'}»",
                      f"   - fix: {d['fix']}"]
        lines += [""]
    return lines


def _meta_from_report(run):
    """Older runs have no meta.json: the same facts from report.md's header."""
    text = (Path(run) / "report.md").read_text(encoding="utf-8")
    g = lambda pat: (re.search(pat, text) or [None, ""])[1]                             # noqa: E731
    end = {}
    if g(r"\*\*Enjoyed it:\*\* (\d+) %"):
        end = {"liked": int(g(r"\*\*Enjoyed it:\*\* (\d+) %")), "again": int(g(r"by this author:\*\* (\d+) %") or 0),
               "best": g(r"liked most:\*\* ([^(]+?) \(").strip(), "best_conf": int(g(r"liked most:\*\* [^(]+\((\d+) %") or 0),
               "dislikes": [(t.strip(), int(p)) for t, p in
                            re.findall(r"([^;:]+?) \((\d+) %\)", g(r"got in the way \(his yes ≥ 50 %\):\*\* (.*)"))]}
    return {"url": g(r"- Game: (\S+)"), "engine": g(r"- Engine: (.+)"), "ending": g(r"run ended: (.+)"),
            "end": end, "name": Path(run).name, "title": ""}


def write_author_report(run):
    """The one page an author pays for (10 USD offer): what a first-time reader went through, where attention dropped
    and what to fix first, in plain words — none of the harness's own terms. Built from turns.jsonl and meta.json."""
    run = Path(run)
    rows = [json.loads(x) for x in (run / "turns.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = json.loads((run / "meta.json").read_text(encoding="utf-8")) if (run / "meta.json").exists() \
        else _meta_from_report(run)
    title = meta.get("title") or meta["url"].rstrip("/").split("/")[-1].replace("-", " ").title()
    drops = attention_drops(rows, meta.get("ending", ""))
    story = [d for d in drops if d["kind"] == "story"]
    nav = [d for d in drops if d["kind"] == "navigation"]
    stats = want_stats(rows)
    end = meta.get("end") or {}
    rep_n, rep_share = repeats_strict(rows)
    lines = [f"# Blind playtest: {title}", "",
             f"A first-time reader played {len(rows)} turns of your game without any hints, clicking the links a "
             f"player sees ({meta.get('engine', '')}). At every turn he said how much he wanted to keep reading, "
             "what he felt, and why.", "", "## In three lines", ""]
    # a probability, not a score (review: «enjoyed it 57 %» read as a grade)
    overall = (f"Asked at the end, he was {end['liked']} % likely to say he enjoyed it and {end['again']} % likely to "
               f"say he would play another game by you" if end else "He finished the session")
    if stats:
        overall += f"; his wish to read on averaged {stats[0]:.1f} of 4."
    lines += [f"1. {overall}"]
    if story:
        d = story[0]
        lines += [f"2. Attention dropped most around turn {d['turns'][0]}" +
                  (f"-{d['turns'][-1]}" if len(d["turns"]) > 1 else "") +
                  f" («{_plain(d['page_title'])}»): he clicked «{_plain(d['context'] or d['promised'])}» and got "
                  f"«{_plain(_cut(d['got'], 110))}»."]
        lines += [f"3. Fix first: {_end(d['fix'])}"]
    elif nav:
        lines += [f"2. The story held him; the trouble was the page itself around turn {nav[0]['turns'][0]}.",
                  f"3. Fix first: {_end(nav[0]['fix'])}"]
    else:
        lines += ["2. No place cleared the bar for a real drop: the story held him the whole session.",
                  "3. Fix first: nothing urgent from this session."]
    lines += ["", "## Where his attention dropped", ""]
    if story:
        lines += ["Measured against this session's own average, so even a game he loved shows a few dips.", ""]
        for d in story:
            when = f"Turns {d['turns'][0]}-{d['turns'][-1]}" if len(d["turns"]) > 1 else f"Turn {d['turn']}"
            lines += [f"**{when} · «{_plain(d['page_title'])}»**", ""]
            if d["shape"]:
                lines += [f"- {_end(d['shape'][0].upper() + d['shape'][1:])}"]
            lines += [f"- He clicked «{_plain(d['context'] or d['promised'])}» and got: "
                      f"«{_plain(d['got']) or 'nothing new'}»",
                      f"- What to try: {_end(d['fix'])}", ""]
    else:
        lines += ["No dip below his usual level in this session.", ""]
    if nav:
        lines += ["## Where the page got in the way", ""]
        one_way = [d for d in nav if d["fix"].startswith("a page with one way on")]
        for d in nav:
            if d in one_way:
                continue
            when = f"Turns {d['turns'][0]}-{d['turns'][-1]}" if len(d["turns"]) > 1 else f"Turn {d['turn']}"
            lines += [f"- **{when} · «{_plain(d['page_title'])}»**: {_end(d['fix'])}"]
        if one_way:
            # one line, not the same sentence four times (Second Sight had 4 such places)
            def span(group):
                return ", ".join(f"{d['turns'][0]}-{d['turns'][-1]}" if len(d["turns"]) > 1 else str(d["turn"])
                                 for d in sorted(group, key=lambda x: x["turns"][0]))
            # «attention dipped» only where his wish fell; where it held and only his feeling slipped, say so (review:
            # Second Sight 18 and 40 held at 2.4 / 2.7)
            fell = [d for d in one_way if {"want_fell", "want_low"} & set(d["signals"])]
            slipped = [d for d in one_way if d not in fell]
            whens = span(one_way)
            def turns(group):
                one = len(group) == 1 and len(group[0]["turns"]) == 1
                return ("turn " if one else "turns ") + span(group)
            what = " and ".join(x for x in (f"his attention dipped ({turns(fell)})" if fell else "",
                                            f"his wish to read on held but his feeling slipped ({turns(slipped)})"
                                            if slipped else "") if x)
            ways = sorted({_cut(re.search(r"«(.*?)»", d["fix"]).group(1), 60) for d in one_way})
            stem = lambda w: w.rstrip("…")                                     # noqa: E731
            ways = [w for w in ways if not any(o != w and stem(o).startswith(stem(w)) for o in ways)] or ways
            lines += [f"- **Turns {whens}**: on pages with a single link, {what} ("
                      + ", ".join(f"«{w}»" if not w.startswith("the ") else w for w in ways)
                      + "). There was no choice to judge there; if you want to look, look at the text just before "
                      "those links."]
        lines += [""]
    phases = arc(rows).split(" → ") if rows else []
    # the longest phases first (review: 30 changes in one line is unreadable); the whole list stays under them
    longest = sorted(phases, key=lambda p: -_phase_len(p))[:4]
    lines += ["## His wish to read on, turn by turn", "", f"`{sparkline(rows)}`", "",
              "(from wants to stop ▁ to can't put it down █).", "",
              "His feelings, longest stretches: " + (", ".join(sorted(longest, key=phases.index)) or "—") + ".",
              f"All changes ({max(0, len(phases) - 1)}): {' → '.join(phases) or '—'}.", ""]
    if end:
        lines += ["## What he said at the end", "",
                  f"- Liked most: {end.get('best', '—')}.",
                  "- Got in the way: " + ("; ".join(f"{t} ({p} %)" for t, p in end.get("dislikes", [])) or
                                          "he named nothing that got in the way") + "."]
        lines += [f"- Repeated the same click on the same page: {rep_n} of {len(rows)} turns ({rep_share:.0%})."]
        lines += [""]
    lines += ["## How this was made, honestly", "",
              "The reader is Jev, an AI model from TypeSafe that answers narrow questions with probabilities — not a "
              "person («he» here is only for easier reading). It played once, from the start, choosing only among the "
              "links on the page. Its feelings are its own answers to the same questions each turn; read them as a "
              "careful first reader's signal, not as a verdict. A human playtest still sees things this cannot." +
              ("" if any(r.get("cause_conf") is not None for r in rows) else
               " In this session how sure he was of each reason was not recorded, so a reason may be a weak guess."),
              ""]
    pressed = [r for r in rows if r.get("by") == "tester"]
    if pressed:
        # the report never lets the tester's click pass as his (the promise to press Submit is the tester's, not his)
        lines[-1:-1] = [" ".join(f"At turn {r['turn']} every answer was chosen and he turned to «{_plain(r.get('jev_picked'))}», "
                                 f"so the tester pressed «{_plain(r['picked'])}» for him." for r in pressed)]
    p = run / "author_report.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def write_report(run, url, name, rows, ending, end, first_text, last_text, engine="?"):
    from collections import Counter
    c = Counter(r["mood"] for r in rows)
    rep, share = repeats(rows)
    lines = [f"# Blind playtest: {name}", "", f"- Game: {url}", f"- Engine: {engine}",
             f"- Player: Jev (TypeSafe), first time, no hints",
             f"- Turns: {len(rows)} · run ended: {ending}",
             f"- Repeated moves, strict (the same choice again on the same page): "
             f"{repeats_strict(rows)[0]} = {repeats_strict(rows)[1]:.0%}",
             f"- Moves back to a page already seen (incl. returning from a codex or an aside): {rep} = {share:.0%}", ""]
    if end:
        lines += [f"**Enjoyed it:** {end['liked']} % · **would play another by this author:** {end['again']} % · "
                  f"**liked most:** {end['best']} ({end['best_conf']} %)", ""]
        lines += ["**What got in the way (his yes ≥ 50 %):** " + ("; ".join(f"{t} ({p} %)" for t, p in end["dislikes"])
                                                               or "nothing he said yes to"), ""]
    lines += attention_lines(rows, ending)
    lines += ["## Feelings over the run", "", "Changes: " + (arc(rows) or "—"), "",
              "Totals: " + " · ".join(f"{m} ×{n}" for m, n in c.most_common()), ""]
    lines += ["## Turn by turn", "", "| # | felt (strength, from) | picked | of |", "|---|---|---|---|"]
    for r in rows:
        picked = r["picked"] or "STOP"
        if r.get("by") == "tester":
            picked += f" (pressed by the tester; Jev picked «{r.get('jev_picked')}»)"
        lines.append(f"| {r['turn']} | {r['mood']} ({r['strength']}, {CAUSES[r['cause']]}) | "
                     f"{picked.replace('|', '/')} | {len(r['choices'])} |")
    stuck = [r for r in rows if r["mood"] in ("confusion", "stuck", "frustration", "boredom")]
    unclear = next((r for r in rows if r.get("submit_unclear")), None)
    if unclear:
        lines += ["", f"Turn {unclear['turn']}: every answer was chosen, but more than one button could be Submit ("
                  + ", ".join(f"«{b}»" for b in unclear["submit_unclear"]) + "): the tester pressed none."]
    lines += ["", "## Where it got hard", ""]
    lines += [f"- turn {r['turn']}: {r['mood']} ({r['strength']}) — picked «{r['picked'] or 'STOP'}» "
              f"from {len(r['choices'])} choices; passage ends: «{r['passage'][-160:].strip()}»" for r in stuck] or ["- nowhere"]
    lines += ["", "## Last page", "", "```", last_text[-1500:], "```", ""]
    p = run / "report.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    (run / "first_page.txt").write_text(first_text, encoding="utf-8")
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url")
    ap.add_argument("--name", required=True)
    ap.add_argument("--turns", type=int, default=40)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--min-turns", type=int, default=0, help="offer «stop» only from this turn on")
    ap.add_argument("--feel-line", action="store_true", help="tell him what he said he felt last turn (made the label stick)")
    ap.add_argument("--port", help="DevTools port of a Chrome started only for playtests (default 9333 or "
                                   "JEV_IF_CHROME_PORT); start it with --remote-debugging-port=N --user-data-dir=<own dir>")
    ap.add_argument("--shared-chrome", action="store_true", help="allow the shared AI Chrome on 9222 (do not)")
    a = ap.parse_args(argv)
    global PORT
    if a.port:
        PORT = "http://127.0.0.1:" + a.port
    if PORT.endswith(":" + SHARED_PORT) and not a.shared_chrome:
        ap.error("port 9222 is the shared AI Chrome: start a separate Chrome for playtests and pass --port")
    FEEL_LINE[0] = a.feel_line
    if os.environ.get("JEV_CLIENT_DIR"):
        sys.path.insert(0, os.environ["JEV_CLIENT_DIR"])
    r = play(a.url, a.name, a.turns, a.out, min_turns=a.min_turns)
    s = repeats_strict(r["rows"])
    print(f"JEV_IF_DONE turns={len(r['rows'])} repeats_strict={s[0]} ({s[1]:.0%}) back_to_seen={r['repeats']} "
          f"({r['repeat_share']:.0%}) engine={r['engine']!r} "
          f"ending={r['ending']!r} report={r['report']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
