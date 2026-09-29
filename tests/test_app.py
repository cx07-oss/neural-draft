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
from content import CASE, EFFECTS, FRONTS, make_card, resolve_play, winner


class RulesTest(unittest.TestCase):
    def test_all_effect_pairs_are_bounded_and_symmetric(self):
        for a, b, fa, fb, clue in itertools.product(EFFECTS, EFFECTS, FRONTS, FRONTS, [c['id'] for c in CASE['clues']]):
            pa = {'card': make_card('a', a, 'A'), 'front': fa, 'clue': clue}
            pb = {'card': make_card('b', b, 'B'), 'front': fb, 'clue': 'audit'}
            result = resolve_play(pa, pb)
            self.assertTrue(2 <= sum(result['delta'].values()) <= 4)
            self.assertTrue(all(v >= 0 for v in result['delta'].values()))
            evolved = {**pa, 'card': make_card('a', a, 'A', 'Luminous')}
            self.assertEqual(result, resolve_play(evolved, pb))

    def test_clue_relevance_and_counter(self):
        def play(kind, front='Evidence', clue='audit'):
            return {'card': make_card('x', kind, 'A'), 'front': front, 'clue': clue}
        self.assertEqual(resolve_play(play('Investigate'), play('Contain'))['delta']['Evidence'], 4)
        self.assertEqual(resolve_play(play('Investigate', clue='rumour'), play('Contain'))['delta']['Evidence'], 2)
        self.assertEqual(resolve_play(play('Contain'), play('Investigate'))['delta']['Evidence'], 4)
        self.assertEqual(resolve_play(play('Contain'), play('Investigate','People'))['delta']['Evidence'], 2)
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
        self.assertEqual(good['archetype'],'Coordinate')
        poor = offline('install',[])
        self.assertEqual(sum(poor['scores'].values()),0)
        self.assertEqual(poor['archetype'],'Challenge')
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
        self.assertEqual(asyncio.run(run({**valid,'cited_action':'install'}))['mode'],'offline')
        self.assertEqual(asyncio.run(run({**valid,'archetype':'Godmode'}))['mode'],'offline')


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_db=server.DB
        server.DB=str(Path(self.temp.name)/'test.sqlite3')
        server.rooms.clear()
        self.env=patch.dict(os.environ,{'NEURAL_OFFLINE':'1'})
        self.env.start()
        self.client=TestClient(server.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        server.DB=self.old_db
        self.env.stop()
        self.temp.cleanup()

    def post(self,path,token='',body=None):
        result=self.client.post('/api'+path,headers={'X-Player':token},json=body or {})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def test_full_forge_duel_reconnect_rematch_and_persistence(self):
        a=self.post('/profile',body={'nickname':'TestA'})['token']
        b=self.post('/profile',body={'nickname':'TestB','demo':True})
        attempt=self.post('/forge/start',a)
        for e in ('request','signature','scope'):self.post('/forge/inspect',a,{'attempt':attempt['id'],'evidence':e})
        self.assertIn('directory',self.post('/forge/ask',a,{'attempt':attempt['id'],'question':'How can I verify the vendor?'})['answer'])
        request={'attempt':attempt['id'],'action':'verify','reason':'Preserve the file and verify the signer through the trusted directory.'}
        card=self.post('/forge',a,request)
        self.assertEqual(card['archetype'],'Coordinate')
        self.assertEqual(self.post('/forge',a,request)['id'],card['id'])  # idempotent mint
        self.assertEqual(self.client.post('/api/forge/inspect',headers={'X-Player':b['token']},json={'attempt':attempt['id'],'evidence':'scope'}).status_code,404)
        code=self.post('/rooms',a,{'card_id':card['id']})['code']
        self.post(f'/rooms/{code}/join',b['token'],{'card_id':b['cards'][0]['id']})
        room=server.rooms[code]
        with self.client.websocket_connect('/ws/'+code) as wa:
            wa.send_json({'token':a});self.assertFalse(wa.receive_json()['opponent_online'])
            with self.client.websocket_connect('/ws/'+code) as wb:
                wb.send_json({'token':b['token']});sa=wa.receive_json();sb=wb.receive_json()
                self.assertTrue(sa['opponent_online'])
                for round_number in range(1,5):
                    ca=sa['deck'][round_number-1];cb=sb['deck'][round_number-1]
                    message={'type':'lock','round':round_number,'match':1,'card_id':ca['id'],'front':FRONTS[(round_number-1)%3],'clue':['audit','token','owner'][(round_number-1)%3]}
                    wa.send_json(message);sa=wa.receive_json();sb=wb.receive_json()
                    self.assertTrue(sb['opponent_locked']);self.assertIsNone(sb['own_play'])
                    self.assertNotIn('opponent_play',sb)
                    self.assertEqual(len(sb['history']),round_number-1)
                    # Rejected duplicates cannot resolve the round twice.
                    wa.send_json(message);self.assertEqual(wa.receive_json()['type'],'error');sa=wa.receive_json();sb=wb.receive_json()
                    wb.send_json({**message,'card_id':cb['id'],'front':'People','clue':'owner'})
                    sa=wa.receive_json();sb=wb.receive_json()
                    self.assertEqual(sa['scores'],sb['scores'])
                    self.assertEqual(len(sa['history']),round_number)
                    if round_number<4:
                        wa.send_json({'type':'ready','match':1,'round':round_number});sa=wa.receive_json();sb=wb.receive_json()
                        wb.send_json({'type':'ready','match':1,'round':round_number});sa=wa.receive_json();sb=wb.receive_json()
                self.assertEqual(sa['phase'],'result');self.assertEqual(sa['result'],sb['result'])
            sa=wa.receive_json();self.assertFalse(sa['opponent_online'])
            with self.client.websocket_connect('/ws/'+code) as wb:
                wb.send_json({'token':b['token']});sa=wa.receive_json();sb=wb.receive_json()
                self.assertEqual(sb['phase'],'result')
                wa.send_json({'type':'rematch','match':1,'round':4});sa=wa.receive_json();sb=wb.receive_json()
                wb.send_json({'type':'rematch','match':1,'round':4});sa=wa.receive_json();sb=wb.receive_json()
                self.assertEqual(sa['match'],2);self.assertEqual(sa['round'],1);self.assertEqual(sa['used'],[])
                wa.send_json({'type':'lock','match':1,'round':1,'card_id':card['id'],'front':'Evidence'})
                self.assertEqual(wa.receive_json()['type'],'error');wa.receive_json();wb.receive_json()
        server.rooms.clear()  # represents process restart; collection survives
        persisted=self.client.get('/api/me',headers={'X-Player':a}).json()
        self.assertEqual(len(persisted['cards']),1)
        self.assertEqual(persisted['cards'][0]['provenance']['reason'],request['reason'])

    def test_invalid_moves_and_missing_room(self):
        p=self.post('/profile',body={'nickname':'Bounds','demo':True})
        code=self.post('/rooms',p['token'],{'card_id':p['cards'][0]['id']})['code']
        with self.client.websocket_connect('/ws/'+code) as ws:
            ws.send_json({'token':'not-a-seat'})
            self.assertTrue(ws.receive_json()['fatal'])
        self.assertEqual(self.client.post('/api/rooms/WRONG/join',headers={'X-Player':p['token']},json={'card_id':p['cards'][0]['id']}).status_code,404)
        room=server.rooms[code]
        room['phase']='choose';room['sockets'][1]=object()
        base={'type':'lock','match':1,'round':1,'card_id':p['cards'][0]['id'],'front':'Evidence','clue':'audit'}
        for change in ({'card_id':'fabricated'},{'front':'Other'},{'clue':'fabricated'}):
            with self.assertRaises(ValueError):server.handle_move(room,0,{**base,**change})
        server.handle_move(room,0,base)
        self.assertEqual(room['used'][0],[p['cards'][0]['id']])


if __name__=='__main__':unittest.main()
