import itertools
import unittest
from content import CHOICES, EFFECTS, FRONTS, make_card, resolve_play


def play(kind, choice, front="Evidence", evolution="Initiate"):
    return {"card": make_card("x", kind, "Test", evolution), "front": front, "choice": choice}


class ContextEffectsTest(unittest.TestCase):
    def test_all_four_relevant_and_irrelevant_choices(self):
        rival = play("Investigate", "audit")
        for kind, good, bad, maximum in [
            ("Investigate", "audit", "rumour", 4),
            ("Contain", "session", "archive", 4),
            ("Challenge", "breach", "record", 4),
            ("Coordinate", "analyst", "liaison", 3),
        ]:
            with self.subTest(kind=kind):
                self.assertEqual(sum(resolve_play(play(kind, good), rival)["delta"].values()), maximum)
                result = resolve_play(play(kind, bad), rival)
                self.assertEqual(sum(result["delta"].values()), 2)
                self.assertFalse(result["context_match"])

    def test_exhaustive_choices_fronts_opponents_and_evolution(self):
        for kind, other, front, rival_front in itertools.product(EFFECTS, EFFECTS, FRONTS, FRONTS):
            for option in CHOICES[kind]["options"]:
                p = play(kind, option["id"], front)
                rival = play(other, CHOICES[other]["options"][0]["id"], rival_front)
                result = resolve_play(p, rival)
                self.assertTrue(2 <= sum(result["delta"].values()) <= 4)
                self.assertEqual(result, resolve_play(play(kind, option["id"], front, "Luminous"), rival))

    def test_tactics_only_reward_a_relevant_decision(self):
        self.assertEqual(sum(resolve_play(play("Contain", "session"), play("Contain", "session", "People"))["delta"].values()), 3)
        self.assertEqual(sum(resolve_play(play("Challenge", "breach"), play("Contain", "session"))["delta"].values()), 3)
        self.assertEqual(resolve_play(play("Coordinate", "liaison", "People"), play("Contain", "session"))["delta"], {"Evidence": 1, "Response": 0, "People": 2})
