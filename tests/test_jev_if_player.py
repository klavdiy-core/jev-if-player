"""jev_if_player end to end on a planted two-passage Twine page in the real AI Chrome (9222), with a stand-in for Jev
(no network, no credits). Red before jev_if_player.py existed. Skips loudly if Chrome is not on 9222."""
import json
import os
import sys
import tempfile
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import jev_if_player as jp  # noqa: E402

PAGE = os.path.join(HERE, "two_passages.html")


def chrome_up():
    try:
        urllib.request.urlopen(jp.PORT + "/json/version", timeout=3).read()
        return True
    except OSError:
        return False


def first_choice(state, choices, may_stop=True):
    return 0, "interest", "noticeably", "text", 0.9


def ender(last, feeling):
    return {"liked": 70, "again": 60, "best": "the story", "best_conf": 80, "dislikes": [("it ended too soon", 66)]}


@unittest.skipUnless(chrome_up(), "AI Chrome is not listening on 127.0.0.1:9222")
class EndToEnd(unittest.TestCase):
    def test_a_two_passage_story_is_played_to_its_ending_and_reported(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(PAGE, "planted", turns=10, out=d, chooser=first_choice, ender=ender, log=lambda *_: None)
            self.assertEqual(len(r["rows"]), 1)
            self.assertEqual(r["rows"][0]["choices"], ["Climb the stairs", "Go back to sleep"])
            self.assertEqual(r["rows"][0]["picked"], "Climb the stairs")
            self.assertIn("ending", r["ending"])
            rep = open(r["report"], encoding="utf-8").read()
            self.assertIn("A ship turns toward shore", rep)          # the last page is the passage the click led to
            self.assertIn("Enjoyed it:** 70 %", rep)
            turns = [json.loads(x) for x in open(os.path.join(d, "planted", "turns.jsonl"), encoding="utf-8")]
            self.assertEqual(turns[0]["mood"], "interest")

    def test_a_choice_that_did_nothing_is_not_offered_again_and_the_right_element_is_clicked(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "dead_link.html"), "dead", turns=6, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            self.assertEqual(r["rows"][0]["choices"], ["[unlabeled link]", "Look around", "Open the door"])
            self.assertEqual([x["picked"] for x in r["rows"]], ["[unlabeled link]"])   # an icon link is a move too
            self.assertIn("trapdoor", open(r["report"], encoding="utf-8").read())

    def test_a_choice_that_did_nothing_is_not_offered_again(self):
        def skip_icon(state, choices, may_stop=True):              # never the icon: Look around, then what is left
            return next(i for i, c in enumerate(choices) if c != "[unlabeled link]"), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "dead_link.html"), "dead2", turns=6, out=d, chooser=skip_icon,
                        ender=ender, log=lambda *_: None)
            self.assertEqual([x["picked"] for x in r["rows"]], ["Look around", "Open the door", "[picture: act1.png]"])
            self.assertIn("onto the sea", open(r["report"], encoding="utf-8").read())

    def test_moves_come_from_the_story_or_an_open_dialog_never_the_sidebar(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "sidebar_dialog.html"), "side", turns=6, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            self.assertEqual([x["choices"] for x in r["rows"]], [["Codex"], ["Back"]])
            self.assertIn("You leave the inn", open(r["report"], encoding="utf-8").read())

    def test_a_continue_on_every_page_is_not_mistaken_for_a_menu(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "codex_loop.html"), "codex", turns=20, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            picks = [x["picked"] for x in r["rows"]]
            self.assertIn("the sea", open(r["report"], encoding="utf-8").read(), picks)
            self.assertLessEqual(picks.count("Codex"), 1, picks)

    def test_a_title_screen_with_only_new_game_is_clicked_not_taken_for_an_ending(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "title_new_game.html"), "title", turns=5, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            self.assertEqual([x["picked"] for x in r["rows"]], ["New Game"])
            self.assertIn("kennels", open(r["report"], encoding="utf-8").read())

    def test_a_hidden_main_behind_a_title_screen_is_not_the_story(self):
        # Diner Detective (31.10): <main id=game> hidden, the title screen beside it -> 0 choices, «ending» at turn 1
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "hidden_main_title.html"), "hmain", turns=5, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            self.assertEqual([x["picked"] for x in r["rows"]], ["Take the night shift"])
            self.assertIn("stranger waits", open(r["report"], encoding="utf-8").read())

    def test_a_native_modal_dialog_gives_the_moves_not_the_inert_page_behind_it(self):
        # Diner Detective (31.10): <dialog> opened by showModal(), no role -> the player offered the room behind it, every
        # click was swallowed by the modal, «stuck» at turn 5
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "native_dialog.html"), "ndlg", turns=5, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            self.assertEqual(r["rows"][0]["choices"], ["Help June with the checks"])
            self.assertIn("Pull up a chair", r["rows"][0]["passage"])
            self.assertIn("June smiles", open(r["report"], encoding="utf-8").read())

    def test_select_dropdowns_are_moves_and_their_values_are_shown(self):
        # Diner Detective (31.10): the puzzle is four <select>s; a clicks-only player saw only Hint/Submit and gave up
        plan = ["Choose «Pie» for Nora", "Choose «Stew» for Luis", "Submit answer"]

        def scripted(state, choices, may_stop=True):
            return choices.index(plan.pop(0)), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "select_puzzle.html"), "sel", turns=6, out=d, chooser=scripted,
                        ender=ender, log=lambda *_: None)
            first = r["rows"][0]["choices"]
            self.assertIn("Choose «Pie» for Nora", first)
            self.assertIn("Choose «Stew» for Luis", first)
            self.assertNotIn("Choose «Choose…» for Nora", first)              # the placeholder is no move
            self.assertIn("Nora: Pie", r["rows"][1]["passage"])                # the state he set is shown back
            # a select's own innerText is every option: four lists repeated drowned the clues (seen in a Diner Detective run)
            self.assertNotIn("Choose…", r["rows"][0]["passage"])
            self.assertIn("June pours coffee", open(r["report"], encoding="utf-8").read())

    def test_when_every_list_is_answered_the_submit_button_is_named_in_the_passage(self):
        # In a Diner Detective run all four answers right at turn 19, then hints, never Submit. A person SEES that every list is
        # filled and the Submit button; the passage says the same, and only when it is true
        plan = ["Choose «Pie» for Nora", "Choose «Stew» for Luis", "Submit answer"]

        def scripted(state, choices, may_stop=True):
            return choices.index(plan.pop(0)), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "select_puzzle.html"), "sub", turns=6, out=d, chooser=scripted,
                        ender=ender, log=lambda *_: None)
            p = [x["passage"] for x in r["rows"]]
            self.assertNotIn("All answers are chosen", p[0])                 # nothing chosen yet
            self.assertNotIn("All answers are chosen", p[1])                 # one of two
            self.assertIn("All answers are chosen; «Submit answer» checks them.", p[2])

    def test_when_every_list_is_answered_and_he_turns_away_the_tester_presses_submit_and_says_so(self):
        # The promise to the Diner Detective author: «Next time, our tester will press Submit».
        # The passage line (f6e54aa) did not move Jev (a later run). So the tester presses it once for that set of answers, and the
        # row says it was the tester, with what Jev picked instead: the report must not claim Jev pressed it.
        plan = ["Choose «Pie» for Nora", "Choose «Stew» for Luis"]

        def hints(state, choices, may_stop=True):
            # never Submit while anything else is offered; «Hint» leaves his offer by the menu rule after four pages
            away = [c for c in choices if c != "Submit answer" and not c.startswith("Choose")]
            want = plan.pop(0) if plan else ("Hint" if "Hint" in choices else (away or choices)[0])
            return choices.index(want), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "select_hint.html"), "hint", turns=8, out=d, chooser=hints,
                        ender=ender, log=lambda *_: None)
            rows = r["rows"]
            pressed = [x for x in rows if x.get("by") == "tester"]
            self.assertEqual(len(pressed), 1, [(x["picked"], x.get("by")) for x in rows])
            self.assertEqual(pressed[0]["picked"], "Submit answer")
            self.assertEqual(pressed[0]["jev_picked"], "Hint")
            self.assertTrue(all(x.get("by") != "tester" for x in rows[:2]), "the tester pressed before every list was answered")
            self.assertIn("ending", r["ending"])
            rep = open(r["report"], encoding="utf-8").read()
            self.assertIn("June pours coffee", rep)
            self.assertIn("Submit answer (pressed by the tester; Jev picked «Hint»)", rep)
            author = open(os.path.join(d, "hint", "author_report.md"), encoding="utf-8").read()
            self.assertIn("pressed «Submit answer» for him", author)

    def test_the_tester_presses_the_real_submit_not_a_story_move_that_starts_with_check(self):
        # Review finding: «Check the window», «Answer the phone», «Done reading» are moves in a story, not Submit
        plan = ["Choose «Pie» for Nora", "Choose «Stew» for Luis"]

        def hints(state, choices, may_stop=True):
            want = plan.pop(0) if plan else ("Hint" if "Hint" in choices else choices[0])
            return choices.index(want), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "check_first.html"), "c", turns=8, out=d, chooser=hints, ender=ender,
                        log=lambda *_: None)
            pressed = [x["picked"] for x in r["rows"] if x.get("by") == "tester"]
            self.assertEqual(pressed, ["Submit answer"], [(x["picked"], x.get("by")) for x in r["rows"]])

    def test_a_wrong_answer_set_is_pressed_once_and_not_again_while_he_keeps_it(self):
        plan = ["Choose «Stew» for Nora", "Choose «Pie» for Luis"]       # wrong: Submit says «Not quite.», the dialog stays

        def hints(state, choices, may_stop=True):
            away = [c for c in choices if c != "Submit answer" and not c.startswith("Choose")]
            want = plan.pop(0) if plan else ("Hint" if "Hint" in choices else (away or choices)[0])
            return choices.index(want), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "select_hint.html"), "w", turns=6, out=d, chooser=hints, ender=ender,
                        log=lambda *_: None)
            pressed = [x for x in r["rows"] if x.get("by") == "tester"]
            self.assertEqual(len(pressed), 1, [(x["picked"], x.get("by")) for x in r["rows"]])
            self.assertGreater(len(r["rows"]), pressed[0]["turn"], "the run ended at the press; the repeat was not tried")

    def test_two_buttons_that_could_be_submit_are_not_guessed_and_the_report_says_so(self):
        plan = ["Choose «Pie» for Nora", "Choose «Stew» for Luis"]

        def hints(state, choices, may_stop=True):
            want = plan.pop(0) if plan else ("Hint" if "Hint" in choices else choices[0])
            return choices.index(want), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "two_submits.html"), "two", turns=4, out=d, chooser=hints, ender=ender,
                        log=lambda *_: None)
            self.assertTrue(all(x.get("by") != "tester" for x in r["rows"]))
            rep = open(r["report"], encoding="utf-8").read()
            self.assertIn("more than one button could be Submit («Submit answer», «Check answers»): the tester pressed none", rep)

    def test_every_run_starts_without_the_games_saved_progress(self):
        page = os.path.join(HERE, "saved_progress.html")
        with tempfile.TemporaryDirectory() as d:
            for name in ("first", "second"):
                jp.play(page, name, turns=1, out=d, chooser=first_choice, ender=ender, log=lambda *_: None)
            first_page = [json.loads(x) for x in open(os.path.join(d, "second", "turns.jsonl"), encoding="utf-8")][0]
        self.assertIn("Visits before this one: 0.", first_page["passage"])   # the first run's save did not carry over

    def test_the_log_keeps_the_games_answer_to_a_click_that_changed_the_page_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "answer_in_place.html"), "place", turns=1, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            turns = [json.loads(x) for x in open(os.path.join(d, "place", "turns.jsonl"), encoding="utf-8")]
            self.assertEqual(turns[0]["picked"], "Ask June")
            self.assertIn("Nora always has the pie", turns[0]["after"])          # the game's answer to the click
            self.assertNotIn("A SMALL FAVOR", turns[0]["after"])                 # not the page's top
            self.assertIn("June waits for you to ask", turns[0]["after_gone"])   # and what the click replaced

    def test_with_a_list_still_open_the_tester_never_presses_for_him(self):
        def always_hint(state, choices, may_stop=True):
            return choices.index("Hint"), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "select_hint.html"), "open", turns=3, out=d, chooser=always_hint,
                        ender=ender, log=lambda *_: None)
            self.assertTrue(all(x.get("by") != "tester" for x in r["rows"]))
            self.assertTrue(all(x["picked"] == "Hint" for x in r["rows"]))

    def test_a_long_whole_sentence_choice_is_offered_shortened(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "late_link.html"), "long", turns=5, out=d, chooser=first_choice,
                        ender=ender, log=lambda *_: None)
            c = r["rows"][0]["choices"]
            self.assertEqual(len(c), 2, c)
            self.assertTrue(c[0].endswith("…") and len(c[0]) == 158, c[0])

    def test_a_link_that_appears_late_is_waited_for(self):
        def sit(state, choices, may_stop=True):
            return next(i for i, c in enumerate(choices) if not c.endswith("…")), "interest", "noticeably", "text", 0.9
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(os.path.join(HERE, "late_link.html"), "late", turns=5, out=d, chooser=sit,
                        ender=ender, log=lambda *_: None)
            self.assertEqual([x["picked"] for x in r["rows"]], ["Sit down", "Listen"])
            self.assertIn("tells you everything", open(r["report"], encoding="utf-8").read())

    def test_jev_choosing_stop_ends_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            r = jp.play(PAGE, "stop", turns=10, out=d, chooser=lambda s, c, m=True: (None, "boredom", "slightly", "pace", 0.5),
                        ender=ender, log=lambda *_: None)
            self.assertEqual(r["ending"], "Jev chose to stop")
            self.assertIn("lighthouse", open(r["report"], encoding="utf-8").read())


class Offline(unittest.TestCase):
    def test_an_only_restart_page_is_an_ending(self):
        self.assertTrue(jp.is_ending(["THE END"]))
        self.assertTrue(jp.is_ending(["Play again?", "Restart"]))
        self.assertFalse(jp.is_ending(["THE END", "Go back"]))
        self.assertFalse(jp.is_ending([]))

    def test_repeats_count_the_same_choice_on_the_same_page(self):
        rows = [{"page_key": "a", "picked": ">>>"}, {"page_key": "b", "picked": "<<<"},
                {"page_key": "a", "picked": ">>>"}, {"page_key": "c", "picked": "x"}]
        self.assertEqual(jp.repeats(rows), (2, 0.5))                 # «<<<» led back to a; «>>>» on a again

    def test_the_arc_names_changes_not_a_tally(self):
        rows = [{"turn": i + 1, "mood": m} for i, m in enumerate(["interest"] * 3 + ["anxiety"] * 2 + ["relief"])]
        self.assertEqual(jp.arc(rows), "interest (1-3) → anxiety (4-5) → relief (6)")

    def test_attention_drops_rank_repeats_and_slipping_feelings_with_a_fix_and_what_he_got(self):
        def row(t, key, picked, mood="interest", strength="noticeably", choices=("a", "b"), passage=None, conf=0.9):
            return {"turn": t, "page_key": key, "picked": picked, "mood": mood, "strength": strength,
                    "choices": list(choices), "passage": passage or f"page {key}", "confidence": conf}
        rows = [row(1, "s", "Codex"), row(2, "c", "Return", passage="The codex."), row(3, "s", "Codex"),
                row(4, "f1", "On"), row(5, "f2", "On"), row(6, "z", "Left", choices="abcde", conf=0.2),
                row(7, "x", "Wait", mood="boredom", strength="strongly", passage="long " * 200),
                row(8, "y", "Go on", passage="The road.")]
        rows[6]["after"] = "Nothing happens for a while."
        d = jp.attention_drops(rows, "turn limit")
        self.assertEqual([x["turn"] for x in d][:2], [7, 3])         # strong boredom first, then the repeat
        self.assertIn("lost him", d[0]["fix"])
        self.assertEqual(d[0]["got"], "Nothing happens for a while.")
        self.assertEqual(d[0]["promised"], "Wait")
        self.assertIn("already seen", d[1]["fix"])                   # it led back to the codex: something changed
        self.assertFalse(any(x["turn"] == 6 for x in d))              # unsure on a calm page is no drop
        self.assertEqual(len({x["page"] for x in d}), len(d))          # one place per page

    def test_a_fall_in_his_wish_to_read_on_is_a_drop(self):
        rows = [{"turn": t, "page_key": str(t), "picked": "On", "mood": "interest", "strength": "noticeably",
                 "choices": ["On"], "passage": f"page {t}", "confidence": 0.9, "want": w}
                for t, w in [(1, 3.2), (2, 3.4), (3, 3.3), (4, 1.9), (5, 3.0), (6, 3.1), (7, 3.0), (8, 3.2)]]
        d = jp.attention_drops(rows, "turn limit")
        self.assertEqual([x["turn"] for x in d], [4])
        self.assertIn("want_fell", d[0]["signals"])
        self.assertIn("1.9/4", d[0]["want"])

    def test_a_menu_line_at_the_top_is_not_what_he_got(self):
        rows = [{"turn": t, "page_key": str(t), "picked": "On", "mood": "interest", "strength": "noticeably",
                 "choices": ["On"], "passage": f"page {t}", "confidence": 0.9, "want": w}
                for t, w in [(1, 3.2), (2, 3.4), (3, 3.3), (4, 1.9), (5, 3.0), (6, 3.1), (7, 3.0), (8, 3.2)]]
        rows[3]["after"] = "SAVE | LOAD | SCOUT PROFILE | RESTART “We got bad information?” you finish for her."
        self.assertEqual(jp.attention_drops(rows, "")[0]["got"], "“We got bad information?” you finish for her.")

    # --- review 25.10 ---
    @staticmethod
    def wrows(wants, **over):
        rows = [{"turn": t + 1, "page_key": str(t), "picked": "On", "mood": "interest", "strength": "noticeably",
                 "choices": ["On", "Wait"], "passage": f"Page {t + 1} text.", "confidence": 0.9, "want": w,
                 "cause": "result"}
                for t, w in enumerate(wants)]
        for t, kv in over.items():
            rows[int(t[1:]) - 1].update(kv)
        return rows

    def test_S1_a_dip_episode_is_measured_against_its_whole_range(self):
        w = [2.6] * 40 + [2.3, 1.7, 2.3, 1.8, 2.4, 2.0, 2.6] + [2.6] * 13       # a real run of Scout, turns 41-47
        d = jp.attention_drops(self.wrows(w), "turn limit")
        self.assertEqual(len(d), 1, [x["turns"] for x in d])
        self.assertEqual((d[0]["turns"][0], d[0]["turns"][-1]), (42, 46))
        self.assertIn("back to 2.6 at turn 47", d[0]["shape"])

    def test_S2_a_run_that_ends_by_his_stop_names_the_stop(self):
        w = [2.5] * 50 + [2.4, 2.3, 1.6, 1.8, 1.5]
        d = jp.attention_drops(self.wrows(w), "Jev chose to stop")
        # the stop names the place; the fix comes from the dip there, not from the stop itself (R1)
        self.assertIn("stop_end", d[0]["signals"])
        self.assertNotIn("stop", d[0]["fix"])
        self.assertEqual(d[0]["fix"], "the payoff of the last choice let him down: what did it promise, and what did "
                                      "he get?")                       # his named cause, «result»
        self.assertEqual(d[0]["turns"][-1], 55)

    def test_S2b_a_stop_after_the_same_click_again_is_navigation_trouble(self):
        rows = self.wrows([2.5] * 20, t19={"page_key": "x"}, t20={"page_key": "x"})   # «On» twice on one page, then stop
        d = jp.attention_drops(rows, "Jev chose to stop")
        self.assertIn("stop_end", d[0]["signals"])
        self.assertIn("repeat", d[0]["signals"])
        self.assertEqual(d[0]["kind"], "navigation")                    # the kind follows the signal the fix came from

    def test_S2c_at_a_stop_the_fix_comes_from_the_strongest_other_signal(self):
        # at the stop: feeling 9 (confusion), repeat 4, turn 3 -> the feeling's advice, a story place
        rows = self.wrows([2.5] * 20, t19={"page_key": "x"}, t20={"page_key": "x", "mood": "confusion"})
        d = jp.attention_drops(rows, "Jev chose to stop")
        self.assertEqual(d[0]["fix"], "unclear what the choices do: say what each one leads to")
        self.assertEqual(d[0]["kind"], "story")

    def test_S3_an_icon_link_with_no_label_gets_the_label_fix_and_is_navigation(self):
        rows = self.wrows([2.5] * 12, t5={"picked": "[unlabeled link]", "choices": ["[unlabeled link]", "x"]})
        d = jp.attention_drops(rows, "turn limit")
        self.assertIn("text label", d[0]["fix"])
        self.assertEqual(d[0]["kind"], "navigation")

    def test_S4_a_story_dip_fix_follows_his_named_cause_and_the_mood_is_shown_only_when_slipping(self):
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 5, t11={"cause": "nothing"})
        d = jp.attention_drops(rows, "turn limit")
        self.assertIn("nothing moved", d[0]["fix"])
        self.assertIsNone(d[0]["mood"])                                # «felt interest» under «attention dropped»: no

    def test_S5_a_one_word_link_comes_with_its_sentence(self):
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 5,
                          t11={"picked": "flat.", "passage": "You see nothing. It is just flat."})
        self.assertEqual(jp.attention_drops(rows, "")[0]["context"], "It is just flat.")
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 5, t11={"picked": "Return", "passage": "The codex.\nReturn"})
        self.assertIsNone(jp.attention_drops(rows, "")[0]["context"])   # a link on its own line

    def test_S6_a_shared_page_across_story_dips_is_named_as_a_pattern(self):
        rows = self.wrows([2.6] * 8 + [1.5] + [2.6] * 8 + [1.5] + [2.6] * 8 + [1.5] + [2.6] * 5,
                          t9={"passage": "ROYAL CODEX Geography"}, t18={"passage": "CHARACTER CODEX Rezan"},
                          t27={"passage": "CHARACTER CODEX Dara"})
        text = "\n".join(jp.attention_lines(rows, ""))
        self.assertIn("3 of 3 story dips are on pages with «CODEX»", text)
        self.assertIn("### Story dips", text)

    def test_S9_a_one_link_page_gets_no_choice_advice(self):
        # Second Sight turns 2/40/42: a splash picture or «Next» is not a choice
        pic = "[picture: b605bc_9f3e~mv2.jpg]"
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 9, t11={"choices": [pic], "picked": pic, "cause": "result"})
        d = jp.attention_drops(rows, "turn limit")
        self.assertEqual(d[0]["kind"], "navigation")
        self.assertIn("one way on («the chapter picture»)", d[0]["fix"])
        self.assertNotIn("payoff", d[0]["fix"])
        nxt = self.wrows([2.6] * 10 + [2.6] + [2.6] * 9,
                         t11={"choices": ["Next"], "picked": "Next", "want": 2.6, "mood": "confusion"})
        for x in jp.attention_drops(nxt, "turn limit"):
            self.assertNotIn("unclear what the choices do", x["fix"])

    def test_S10_a_text_dip_on_a_one_link_page_keeps_its_prose_advice(self):
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 9, t11={"choices": ["Next"], "cause": "text",
                                                               "passage": "x" * 254})
        d = jp.attention_drops(rows, "turn limit")
        self.assertIn("it is short: look at what this passage says", d[0]["fix"])
        self.assertNotIn("254", d[0]["fix"])

    def test_S12_a_one_link_place_where_his_wish_held_is_not_called_a_dip(self):
        # Second Sight 18 and 40 held (2.4, 2.7), only the feeling slipped
        from pathlib import Path
        rows = self.wrows([2.6] * 20, t11={"choices": ["Next"], "picked": "Next", "mood": "confusion",
                                           "strength": "strongly"})
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "turns.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            (run / "meta.json").write_text(json.dumps({"url": "https://x/held-test", "engine": "Twine"}),
                                           encoding="utf-8")
            jp.write_author_report(run)
            text = (run / "author_report.md").read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if "single link" in x)
        self.assertNotIn("attention dipped", line)
        self.assertIn("held but his feeling slipped (turn 11)", line)

    def test_S11_author_report_says_the_chapter_picture_and_ends_sentences(self):
        self.assertEqual(jp._plain("he clicked [picture: b605bc_x~mv2.jpg]"), "he clicked the chapter picture")
        self.assertEqual(jp._end("cut or break it"), "cut or break it.")
        self.assertEqual(jp._end("what did he get?"), "what did he get?")

    def test_S7_navigation_above_the_bar_says_held_and_a_long_loop_says_loop(self):
        rows = self.wrows([2.5] * 40, t5={"picked": "[unlabeled link]", "choices": ["[unlabeled link]", "x"]})
        d = jp.attention_drops(rows, "turn limit")
        self.assertIn("held (2.5/4)", d[0]["shape"])
        loop = self.wrows([2.5] * 40)
        for t in range(10, 25):
            loop[t].update({"page_key": "L", "picked": "[unlabeled link]", "choices": ["[unlabeled link]"]})
        d = jp.attention_drops(loop, "turn limit")
        self.assertIn("the same loop for", d[0]["shape"])

    def test_S8_a_sticky_feeling_label_is_flagged(self):
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 9)
        for r in rows:
            r["mood"] = "fear"
        self.assertIn("stayed «fear» for 20 of 20", "\n".join(jp.attention_lines(rows, "")))

    def test_a_feeling_fix_uses_the_slipping_feeling_of_its_episode_not_of_the_lowest_turn(self):
        rows = self.wrows([2.6] * 10 + [2.0, 1.2] + [2.6] * 8,
                          t11={"mood": "frustration", "strength": "very strongly"}, t12={"mood": "fear"})
        d = jp.attention_drops(rows, "turn limit")
        self.assertNotIn("look here", d[0]["fix"])

    # --- review of the author report 25.10 ---
    def test_A1_controls_is_said_only_for_navigation(self):
        rows = self.wrows([2.6] * 20, t8={"mood": "suspicion", "strength": "very strongly"})
        d = jp.attention_drops(rows, "turn limit")
        self.assertNotIn("controls", d[0]["shape"])
        self.assertIn("feeling slipped (suspicion, very strongly)", d[0]["shape"])

    def test_A2_a_dip_takes_its_fix_from_his_reason_and_an_unsure_reason_is_said(self):
        rows = self.wrows([2.6] * 10 + [1.6] + [2.6] * 9, t11={"cause": "text", "mood": "confusion",
                                                             "strength": "strongly"})
        self.assertIn("the prose here lost him", jp.attention_drops(rows, "")[0]["fix"])
        rows[10]["cause_conf"] = 0.2
        self.assertIn("not sure why", jp.attention_drops(rows, "")[0]["fix"])

    def test_A4_a_setup_page_or_a_hair_under_the_bar_is_no_dip(self):
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 9,
                          t11={"choices": ["She/her", "He/him", "They/them"], "picked": "She/her"})
        self.assertEqual(jp.attention_drops(rows, ""), [])
        stats = (2.6, 0.2, 2.3)                                       # mean, sd, bar
        hair = jp._signals(self.wrows([2.28]), "", stats)[0]          # 0.02 under the bar
        clear = jp._signals(self.wrows([2.15]), "", stats)[0]         # 0.15 under it
        self.assertNotIn("want_fell", hair)
        self.assertIn("want_fell", clear)

    def test_A4b_a_content_setting_page_is_setup_too(self):
        self.assertTrue(jp.is_setup({"choices": ["YES to mentions of physical sex", "NO to mentions of physical sex"]}))
        self.assertFalse(jp.is_setup({"choices": ["Help Oliver with the engine.", "Help Elle with the water."]}))

    def test_A5_quotes_are_cut_at_a_word(self):
        self.assertEqual(jp._cut("by the House of Saoirse", 10), "by the…")
        self.assertEqual(jp._phase_len("fear (8-54)"), 47)
        self.assertEqual(jp._phase_len("pride (52)"), 1)

    def test_the_author_report_is_plain_and_says_what_to_fix_first(self):
        rows = self.wrows([2.6] * 10 + [1.4] + [2.6] * 9,
                          t11={"picked": "flat.", "passage": "You search. It is just flat.", "after": "Bad intel."})
        with tempfile.TemporaryDirectory() as d:
            run = os.path.join(d, "g")
            os.makedirs(run)
            with open(os.path.join(run, "turns.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(r) for r in rows))
            with open(os.path.join(run, "meta.json"), "w", encoding="utf-8") as f:
                json.dump({"url": "https://x.itch.io/the-game", "engine": "Twine · Harlowe", "ending": "turn limit",
                           "end": {"liked": 61, "again": 58, "best": "the story", "best_conf": 70, "dislikes": []},
                           "title": ""}, f)
            text = open(jp.write_author_report(run), encoding="utf-8").read()
        self.assertIn("# Blind playtest: The Game", text)
        self.assertIn("61 % likely to say he enjoyed it", text)
        self.assertIn("Fix first:", text)
        self.assertIn("It is just flat.", text)
        self.assertIn("not a person", text)
        for inner in ("want_fell", "page_key", "signals", "stop_end"):   # none of the harness's own words
            self.assertNotIn(inner, text)

    def _author_text(self, rows, ending):
        with tempfile.TemporaryDirectory() as d:
            run = os.path.join(d, "g")
            os.makedirs(run)
            with open(os.path.join(run, "turns.jsonl"), "w", encoding="utf-8") as f:
                f.write("\n".join(json.dumps(r) for r in rows))
            with open(os.path.join(run, "meta.json"), "w", encoding="utf-8") as f:
                json.dump({"url": "https://x.itch.io/the-game", "engine": "unknown HTML", "ending": ending,
                           "end": {"liked": 40, "again": 48, "best": "nothing", "best_conf": 58, "dislikes": []},
                           "title": ""}, f)
            return open(jp.write_author_report(run), encoding="utf-8").read()

    # a puzzle run shaped like a real Diner Detective one: interest, the tester presses Submit, the game answers with
    # its rule, confusion follows, and the reader stops at the end (Diner Detective)
    PUZZLE = dict(t9={"by": "tester", "picked": "Submit answer", "mood": "confusion",
                      "after": "Each meal is used exactly once. Two customers cannot share the same check."},
                  t10={"mood": "confusion", "picked": "Reset pieces"},
                  t14={"mood": "confusion"}, t15={"mood": "confusion"}, t16={"mood": "confusion", "picked": None})

    def test_R1_the_readers_stop_is_never_the_fix_first(self):
        rows = self.wrows([2.3] * 8 + [2.2, 2.06] + [2.3] * 3 + [2.1, 2.1, 2.07], **self.PUZZLE)
        fix_first = [l for l in self._author_text(rows, "Jev chose to stop").splitlines() if "Fix first" in l]
        self.assertEqual(len(fix_first), 1, fix_first)
        self.assertNotIn("chose to stop", fix_first[0])                 # an empty piece of advice for an author

    def test_R1b_a_bare_stop_with_nothing_else_still_gives_advice(self):
        rows = self.wrows([2.5] * 20)                                   # flat wish, calm feeling: only the stop
        fix_first = [l for l in self._author_text(rows, "Jev chose to stop").splitlines() if "Fix first" in l]
        self.assertEqual(len(fix_first), 1, fix_first)
        self.assertNotIn("chose to stop", fix_first[0])
        self.assertIn("look at", fix_first[0])

    def test_R2_the_games_answer_to_the_testers_press_is_in_the_report(self):
        rows = self.wrows([2.3] * 8 + [2.2, 2.06] + [2.3] * 3 + [2.1, 2.1, 2.07], **self.PUZZLE)
        text = self._author_text(rows, "Jev chose to stop")
        where = text.split("## In three lines", 1)[1].split("## His wish to read on", 1)[0]   # the lines and the places
        self.assertIn("Each meal is used exactly once", where)

    def test_R2b_a_tester_press_with_no_label_is_not_an_empty_quote(self):
        puzzle = dict(self.PUZZLE, t9=dict(self.PUZZLE["t9"], picked=None))
        rows = self.wrows([2.3] * 8 + [2.2, 2.06] + [2.3] * 3 + [2.1, 2.1, 2.07], **puzzle)
        text = self._author_text(rows, "Jev chose to stop")
        self.assertIn("pressed «the game's button» for him", text)
        self.assertNotIn("pressed «»", text)
        self.assertIn("turned to «another link»", text)                # his own pick was not recorded either
        self.assertNotIn("turned to «»", text)

    def test_R3_a_stop_reads_as_a_stop_not_a_click_on_stop_and_never_an_empty_quote(self):
        rows = self.wrows([2.3] * 8 + [2.2, 2.06] + [2.3] * 3 + [2.1, 2.1, 2.07], **self.PUZZLE)
        text = self._author_text(rows, "Jev chose to stop")
        top = text.split("## Where his attention dropped")[0]
        self.assertNotIn("«(stop)»", text)                              # he pressed nothing at a stop
        self.assertNotIn("«»", text)                                    # the three lines had «got «»»
        self.assertIn("he stopped reading on this page", top)
        self.assertIn("- He stopped reading on this page.", text)

    def test_the_section_says_the_dips_are_relative_and_gives_the_average(self):
        rows = [{"turn": t, "page_key": str(t), "picked": "On", "mood": "interest", "strength": "noticeably",
                 "choices": ["On"], "passage": f"page {t}", "confidence": 0.9, "want": w}
                for t, w in [(1, 3.2), (2, 3.4), (3, 3.3), (4, 1.9), (5, 3.0), (6, 3.1), (7, 3.0), (8, 3.2)]]
        text = "\n".join(jp.attention_lines(rows, ""))
        self.assertIn("measured against this run", text)
        self.assertIn("3.0/4", text)                                  # the run's average (24.1 / 8)
        self.assertIn("1.9/4", text)                                  # the absolute level at the dip

    def test_neighbouring_drops_are_one_episode(self):
        rows = [{"turn": t, "page_key": k, "picked": p, "mood": "interest", "strength": "noticeably",
                 "choices": ["a"], "passage": f"page {k}", "confidence": 0.9}
                for t, k, p in [(1, "c", "R"), (2, "r", "Back"), (3, "c", "R"), (4, "r", "Back"), (5, "c", "D"),
                                (6, "d", "Back")]]
        d = jp.attention_drops(rows, "turn limit")
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["turns"], [3, 4])

    def test_new_part_is_what_the_click_added(self):
        self.assertEqual(jp.new_part("You wake.", "You wake. The lamp is lit."), "The lamp is lit.")
        self.assertEqual(jp.new_part("Old page.", "A new page."), "A new page.")

    def test_new_part_of_a_page_changed_in_place_is_the_changed_line_not_the_page_top(self):
        head = "01 · A SMALL FAVOR\n" + "The mixed-up checks, a long header line. " * 12
        before = head + "\nJune waits for you to ask.\nThe clock says ten past eleven."
        after = head + "\nJune: Nora always has the pie.\nThe clock says ten past eleven."
        self.assertEqual(jp.new_part(before, after), "June: Nora always has the pie.")
        # a text that only lost lines (a dialog closed) says what went, never the page top
        self.assertEqual(jp.new_part(before, head + "\nThe clock says ten past eleven."), "")
        self.assertEqual(jp.gone_part(before, head + "\nThe clock says ten past eleven."), "June waits for you to ask.")
        # a line said once more is new once (the same answer twice in a row)
        self.assertEqual(jp.new_part("Q\nNot quite.\nEnd", "Q\nNot quite.\nNot quite.\nEnd"), "Not quite.")

    def test_strict_repeats_count_only_the_same_choice_on_the_same_page(self):
        rows = [{"page_key": "s", "picked": "Codex"}, {"page_key": "c", "picked": "Return"},
                {"page_key": "s", "picked": "Continue"}, {"page_key": "t", "picked": "x"}]
        self.assertEqual(jp.repeats_strict(rows)[0], 0)              # Return from a first read is not a repeat
        self.assertEqual(jp.repeats(rows)[0], 1)                     # ...but it does land on a seen page

    def test_a_menu_round_trip_is_a_repeat_and_paging_is_not(self):
        keys = ["s1", "prof", "s1", "s2", "prof2", "s2", "s3"]
        picks = ["PROFILE", "RETURN", "Go", "PROFILE", "RETURN", "Go", "Run"]
        rows = [{"page_key": k, "picked": p} for k, p in zip(keys, picks)]
        self.assertEqual(jp.repeats(rows)[0], 2)                     # the two RETURNs land on seen pages
        pages = [{"page_key": str(i), "picked": ">>>"} for i in range(6)]
        self.assertEqual(jp.repeats(pages)[0], 0)

    def test_the_state_lists_what_he_already_clicked_here(self):
        s = jp.state_text({"text": "x"}, "", [], 4, seen_before=1, clicked_here=["<<<"])
        self.assertIn("ALREADY CLICKED: «<<<»", s)

    def test_by_default_the_state_does_not_repeat_his_last_feeling_to_him(self):
        self.assertNotIn("YOU FELT", jp.state_text({"text": "x"}, "", ["fear"] * 5, 6))

    def test_the_state_carries_the_page_and_the_last_move(self):
        jp.FEEL_LINE[0] = True                                       # off by default since the A/B; on here
        self.addCleanup(jp.FEEL_LINE.__setitem__, 0, False)
        s = jp.state_text({"text": "You wake in a lighthouse."}, "YOUR LAST MOVE: «x» -> the page changed.",
                          ["interest"], 3)
        self.assertIn("lighthouse", s)
        self.assertIn("Turn 3", s)
        self.assertIn("LAST TURN YOU SAID YOU FELT: curious", s)

    def test_the_state_never_tells_him_what_to_feel_and_counts_a_page_seen_again(self):
        s = jp.state_text({"text": "x"}, "", [], 1)
        self.assertNotIn("curious", s)                               # no planted feeling
        self.assertIn("SEEN THIS EXACT PAGE 2 TIME", jp.state_text({"text": "x"}, "", [], 5, seen_before=2))


if __name__ == "__main__":
    unittest.main()
