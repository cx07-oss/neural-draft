import asyncio
import itertools
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

import app as server
from assessment import AIReview, assess, offline
from content import CASE, CHOICES, EFFECTS, FRONTS, forged_record, make_card, resolve_play, strategy_observations, winner

def decision(kind, front):
    return {"Investigate": {"Evidence":"audit","Response":"token","People":"owner"}[front], "Contain":"session", "Challenge":"breach", "Coordinate":{"Evidence":"analyst","Response":"operator","People":"liaison"}[front]}[kind]


class RulesTest(unittest.TestCase):
    def test_all_forge_paths_and_grounded_discovery(self):
        for action, focus, kind, pattern in [('verify','source','Investigate','source'), ('verify','claim','Challenge','claim'), ('isolate','source','Contain','exposure'), ('coordinate','source','Coordinate','escalate')]:
            record = forged_record(action, ['request','signature','scope'], focus)
            self.assertEqual(record['pattern'],pattern)
            self.assertEqual(offline(action,['request','signature','scope'],focus)['archetype'],kind)
            self.assertTrue(record['forged_because'].startswith('Forged because you '))
            empty = forged_record(action, [], focus)
            self.assertIsNone(empty['pattern'])
            self.assertIn('No evidence items were opened',empty['forged_because'])

    def test_strategy_observations_cite_real_rounds(self):
        def h(n, front, other, kind='Investigate', good=True):
            a={'card':make_card('a',kind,'A'),'front':front,'choice':decision(kind,front) if good else 'rumour'}
            b={'card':make_card('b','Investigate','B'),'front':other,'choice':decision('Investigate',other)}
            return {'round':n,'plays':[a,b],'effects':[resolve_play(a,b),resolve_play(b,a)]}
        history=[h(1,'Evidence','Evidence',good=False),h(2,'People','Response'),h(3,'Response','People'),h(4,'Evidence','Evidence','Contain')]
        insight=strategy_observations(history,0)
        self.assertIn('3 of 3 fronts',insight[0]['text'])
        self.assertIn('3 of 4 written decisions',insight[1]['text'])
        self.assertEqual(insight[2]['rounds'],[1,2])
        self.assertEqual(insight[2]['skills'],['Adaptation'])
        unchanged=[h(n,'Evidence','People') for n in range(1,5)]
        self.assertEqual(len(strategy_observations(unchanged,0)),2)
        self.assertNotIn('Prediction',str(strategy_observations(unchanged,0)))
        contest=[h(n,'Evidence','Evidence','Contain') for n in range(1,5)]
        self.assertEqual(strategy_observations(contest,0)[2]['rounds'],[1])

    def test_all_effect_pairs_are_bounded_and_symmetric(self):
        for a, b, fa, fb, clue in itertools.product(EFFECTS, EFFECTS, FRONTS, FRONTS, [c['id'] for c in CASE['clues']]):
            pa = {'card': make_card('a', a, 'A'), 'front': fa, 'choice': clue if a=='Investigate' else decision(a,fa)}
            pb = {'card': make_card('b', b, 'B'), 'front': fb, 'choice': decision(b,fb)}
            result = resolve_play(pa, pb)
            self.assertTrue(2 <= sum(result['delta'].values()) <= 4)
            self.assertTrue(all(v >= 0 for v in result['delta'].values()))
            evolved = {**pa, 'card': make_card('a', a, 'A', 'Luminous')}
            self.assertEqual(result, resolve_play(evolved, pb))

    def test_clue_relevance_and_counter(self):
        def play(kind, front='Evidence', clue='audit'):
            return {'card': make_card('x', kind, 'A'), 'front': front, 'choice': clue if kind=='Investigate' else decision(kind,front)}
        self.assertEqual(resolve_play(play('Investigate'), play('Contain'))['delta']['Evidence'], 4)
        self.assertEqual(resolve_play(play('Investigate', clue='rumour'), play('Contain'))['delta']['Evidence'], 2)
        self.assertEqual(resolve_play(play('Contain'), play('Investigate'))['delta']['Evidence'], 4)
        self.assertEqual(resolve_play(play('Contain'), play('Investigate','People'))['delta']['Evidence'], 3)
        self.assertEqual(resolve_play(play('Challenge'), play('Coordinate','People'))['delta']['Evidence'], 4)
        self.assertEqual(resolve_play(play('Coordinate','People'), play('Contain'))['delta'], {'Evidence':1,'Response':0,'People':2})

    def test_winner_all_tie_paths(self):
        def scores(a,b): return [dict(zip(FRONTS,a)),dict(zip(FRONTS,b))]
        self.assertEqual(winner(scores([3,3,0],[2,2,12]))[0],0)  # majority beats total
        self.assertEqual(winner(scores([5,0,2],[0,4,2]))[0],0)  # 1/1/1 total
        self.assertIsNone(winner(scores([4,0,2],[0,4,2]))[0])
        self.assertIsNone(winner(scores([1,0,0],[0,0,0]))[0])  # one lead, two ties
        self.assertIsNone(winner(scores([2,2,2],[2,2,2]))[0])

    def test_assessment_is_honest_and_power_fixed(self):
        good = offline('verify',['request','signature','scope'])
        self.assertEqual(good['scores'],dict(verification=2,risk=2,response=2))
        self.assertEqual(good['archetype'],'Investigate')
        poor = offline('isolate',[])
        self.assertEqual(sum(poor['scores'].values()),2)
        self.assertEqual(poor['archetype'],'Contain')
        self.assertIn('not interpreted',poor['notice'])

    def test_ai_validation_and_fallback(self):
        valid = dict(verification=2,risk=2,response=2,cited_action='verify',feedback='Independent verification and a limited pause are well supported.',confidence=0.8,archetype='Investigate')
        AIReview.model_validate(valid)
        for change in ({'archetype':'Godmode'},{'response':99},{'confidence':2},{'invented_power':20}):
            with self.assertRaises(ValueError): AIReview.model_validate({**valid,**change})
        async def run(payload):
            transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(payload)}]}]}))
            client=httpx.AsyncClient(transport=transport)
            with patch('assessment.httpx.AsyncClient',return_value=client), patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','NEURAL_OFFLINE':'0'}):
                return await assess('verify',['request','signature','scope'],'Verify through the directory before any install.')
        self.assertEqual(asyncio.run(run(valid))['mode'],'ai')
        self.assertEqual(asyncio.run(run({**valid,'cited_action':'isolate'}))['mode'],'offline')
        self.assertEqual(asyncio.run(run({**valid,'archetype':'Godmode'}))['mode'],'offline')
        self.assertEqual(asyncio.run(run({**valid,'archetype':'Coordinate'}))['mode'],'offline')

    def test_ai_malformed_envelope_and_evidence_ceiling(self):
        async def run(envelope, seen):
            transport=httpx.MockTransport(lambda req:httpx.Response(200,json=envelope))
            client=httpx.AsyncClient(transport=transport)
            with patch('assessment.httpx.AsyncClient',return_value=client), patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','NEURAL_OFFLINE':'0'}):
                return await assess('verify',seen,'Persuasive text cannot stand in for inspecting evidence.')
        self.assertEqual(asyncio.run(run({'output':[None]},[]))['mode'],'offline')
        payload=dict(verification=2,risk=2,response=2,cited_action='verify',feedback='A bounded pause supports an independent check.',confidence=0.7,archetype='Investigate')
        result=asyncio.run(run({'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(payload)}]}]},[]))
        self.assertEqual(result['mode'],'ai')
        self.assertEqual(result['scores'],offline('verify',[])['scores'])


if __name__=='__main__':unittest.main()
