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
        self.assertIn('3 of 4 case choices',insight[1]['text'])
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

    def test_forged_record_persists_across_app_restart(self):
        token=self.post('/profile',body={'nickname':'Record'})['token']
        attempt=self.post('/forge/start',token)['id']
        for e in ('request','signature'):
            self.post('/forge/inspect',token,{'attempt':attempt,'evidence':e})
        card=self.post('/forge',token,{'attempt':attempt,'action':'verify','focus':'claim','reason':'This reason is stored but not semantically interpreted.'})
        self.assertEqual(card['archetype'],'Challenge')
        self.assertEqual(card['pattern'],'claim')
        self.assertEqual(len(card['provenance']['evidence_snapshot']),2)
        self.assertIn('not interpreted',card['assessment']['notice'])
        self.assertNotIn('This reason',card['forged_because'])
        self.client.__exit__(None,None,None)
        server.rooms.clear()
        self.client=TestClient(server.app)
        self.client.__enter__()
        saved=self.client.get('/api/me',headers={'X-Player':token}).json()['cards'][0]
        self.assertEqual(saved,card)

    def test_context_spoofing_rejected_or_ignored_on_server(self):
        a=self.post('/profile',body={'nickname':'Spoof','demo':True})
        code=self.post('/rooms',a['token'],{'card_id':a['cards'][0]['id']})['code']
        room=server.rooms[code]
        room['phase']='choose';room['sockets'][1]=object()
        room['decks'].append(room['decks'][0])
        room['sockets'][0]=object()
        for card in room['decks'][0][:5]:
            msg={'type':'lock','match':1,'round':1,'card_id':card['id'],'front':'Evidence','choice':'invented','correct':True,'bonus':100}
            with self.assertRaises(ValueError):server.handle_move(room,0,msg)
        bad={'type':'lock','match':1,'round':1,'card_id':a['cards'][0]['id'],'front':'Evidence','choice':'rumour','context_match':True,'delta':{'Evidence':100}}
        server.handle_move(room,0,bad)
        server.handle_move(room,1,{**bad,'choice':'audit'})
        self.assertEqual(room['scores'][0]['Evidence'],2)
        self.assertFalse(room['history'][0]['effects'][0]['context_match'])
        server.handle_move(room,0,{'type':'ready','match':1,'round':1})
        server.handle_move(room,1,{'type':'ready','match':1,'round':1})
        with self.assertRaises(ValueError):server.handle_move(room,0,{**bad,'round':2})
        public=self.client.get('/api/config').json()
        self.assertTrue(all('front' not in c for c in public['case']['clues']))

    def test_queued_simultaneous_locks_and_locked_reconnect(self):
        a=self.post('/profile',body={'nickname':'SimA','demo':True})
        b=self.post('/profile',body={'nickname':'SimB','demo':True})
        code=self.post('/rooms',a['token'],{'card_id':a['cards'][0]['id']})['code']
        self.post(f'/rooms/{code}/join',b['token'],{'card_id':b['cards'][0]['id']})
        def until(ws, predicate):
            for _ in range(12):
                state=ws.receive_json()
                if predicate(state):return state
            self.fail('Expected WebSocket state not delivered')
        move={'type':'lock','match':1,'round':1,'front':'Evidence','choice':'audit'}
        with self.client.websocket_connect('/ws/'+code) as wa:
            wa.send_json({'token':a['token']});wa.receive_json()
            with self.client.websocket_connect('/ws/'+code) as wb:
                wb.send_json({'token':b['token']});wa.receive_json();wb.receive_json()
                # Queue both without waiting for a state between commitments.
                wa.send_json({**move,'card_id':a['cards'][0]['id']})
                wb.send_json({**move,'card_id':b['cards'][0]['id']})
                sa=until(wa,lambda s:s.get('phase')=='reveal')
                sb=until(wb,lambda s:s.get('phase')=='reveal')
                self.assertEqual(sa['scores'],sb['scores'])
                self.assertEqual(len(sa['history']),1)
                wa.send_json({'type':'ready','match':1,'round':1})
                wb.send_json({'type':'ready','match':1,'round':1})
                until(wa,lambda s:s.get('round')==2);until(wb,lambda s:s.get('round')==2)
                wb.send_json({**move,'round':2,'card_id':'s1'})
                before=until(wb,lambda s:s.get('locked'))
                until(wa,lambda s:s.get('opponent_locked'))
            until(wa,lambda s:not s.get('opponent_online'))
            with self.client.websocket_connect('/ws/'+code) as restored:
                restored.send_json({'token':b['token']})
                after=restored.receive_json()
                self.assertEqual(after['own_play'],before['own_play'])
                self.assertEqual(after['used'],before['used'])
                self.assertEqual(after['scores'],before['scores'])

    def test_full_forge_duel_reconnect_rematch_and_persistence(self):
        a=self.post('/profile',body={'nickname':'TestA'})['token']
        b=self.post('/profile',body={'nickname':'TestB','demo':True})
        attempt=self.post('/forge/start',a)
        for e in ('request','signature','scope'):self.post('/forge/inspect',a,{'attempt':attempt['id'],'evidence':e})
        self.assertIn('directory',self.post('/forge/ask',a,{'attempt':attempt['id'],'question':'How can I verify the vendor?'})['answer'])
        request={'attempt':attempt['id'],'action':'verify','reason':'Preserve the file and verify the signer through the trusted directory.'}
        card=self.post('/forge',a,request)
        self.assertEqual(card['archetype'],'Investigate')
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
                    message={'type':'lock','round':round_number,'match':1,'card_id':ca['id'],'front':FRONTS[(round_number-1)%3],'choice':decision(ca['archetype'],FRONTS[(round_number-1)%3])}
                    wa.send_json(message);sa=wa.receive_json();sb=wb.receive_json()
                    self.assertTrue(sb['opponent_locked']);self.assertIsNone(sb['own_play'])
                    self.assertNotIn('opponent_play',sb)
                    self.assertEqual(len(sb['history']),round_number-1)
                    # Rejected duplicates cannot resolve the round twice.
                    wa.send_json(message);self.assertEqual(wa.receive_json()['type'],'error');sa=wa.receive_json();sb=wb.receive_json()
                    wb.send_json({**message,'card_id':cb['id'],'front':'People','choice':decision(cb['archetype'],'People')})
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
