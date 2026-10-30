import unittest
from pathlib import Path

from src.confirmation_flow import FlowStore
from src.reply_details import parse_detail_reply
from test_confirmation_flow import recommendation
from test_data_pipeline import order,temporary_directory


class DetailParserTests(unittest.TestCase):
    def test_user_hinglish_example_extracts_only_quoted_values(self):
        self.assertEqual(parse_detail_reply('mera address ye hai "Satpur Nashik" aur Name "Kunal"'),
                         {'address':'Satpur Nashik','name':'Kunal'})

    def test_hindi_labels_smart_quotes_and_reversed_order(self):
        self.assertEqual(parse_detail_reply('मेरा नाम “कुणाल” और पता “मकान 12, मेन रोड, नाशिक”'),
                         {'name':'कुणाल','address':'मकान 12, मेन रोड, नाशिक'})
        self.assertEqual(parse_detail_reply('naam "Kunal" aur pata "House 12, Satpur, Nashik"'),
                         {'name':'Kunal','address':'House 12, Satpur, Nashik'})

    def test_existing_commands_and_quoted_commands(self):
        self.assertEqual(parse_detail_reply('ADDRESS: House 12, Name Apartments'),{'address':'House 12, Name Apartments'})
        self.assertEqual(parse_detail_reply('NAME: Kunal'),{'name':'Kunal'})
        self.assertEqual(parse_detail_reply('ADDRESS: "House 12, Main Road"'),{'address':'House 12, Main Road'})

    def test_unquoted_prose_and_ambiguous_values_are_not_guessed(self):
        for text in ('Mera address ye hai Satpur Nashik aur Name Kunal',
                     'address "A" name Kunal','name "Kunal','name ""',
                     'name "Kunal" name "Other"','address "A" aur "B"',
                     'ADDRESS: House 12 NAME: Kunal','name address "Kunal"'):
            with self.subTest(text=text),self.assertRaises(ValueError):
                parse_detail_reply(text)

    def test_commands_inside_values_stay_literal(self):
        self.assertEqual(parse_detail_reply('address "House 12, Name Road, cancel" name "Yes"'),
                         {'address':'House 12, Name Road, cancel','name':'Yes'})
        self.assertIsNone(parse_detail_reply('YES'))
        self.assertIsNone(parse_detail_reply('"NO"'))


class DetailReplyFlowTests(unittest.TestCase):
    def setUp(self):
        self.context=temporary_directory()
        self.directory=Path(self.context.__enter__())
        self.store=FlowStore(self.directory/'flow.sqlite',start='2026-10-30T09:00:00+05:30')
        self.order=order()
        self.initial=self.store.start(self.order,recommendation(self.order,address='unknown',name='unknown'),'Hinglish')

    def tearDown(self):
        self.context.__exit__(None,None,None)

    def test_short_address_is_saved_but_not_treated_as_deliverable(self):
        result=self.store.reply('A1','mera address ye hai "Satpur Nashik" aur Name "Kunal"','details')
        self.assertEqual(result['order']['address'],'Satpur Nashik')
        self.assertEqual(result['order']['customer_name'],'Kunal')
        self.assertFalse(result['needs_name'])
        self.assertTrue(result['needs_address'])
        self.assertFalse(result['can_ship'])
        self.assertIn('Satpur Nashik',result['messages'][-1]['text'])
        self.assertIn('house/building',result['messages'][-1]['text'])
        self.assertFalse(self.store.reply('A1','YES','yes')['can_ship'])

    def test_full_quoted_details_require_separate_confirmation(self):
        text='mera address "House 21, Gali 4, Satpur, Nashik" aur name "Kunal"'
        result=self.store.reply('A1',text,'details')
        self.assertEqual(result['state'],'awaiting_confirmation')
        self.assertFalse(result['can_ship'])
        self.assertEqual(result['deadline'],self.initial['deadline'])
        self.assertTrue(self.store.reply('A1','YES','yes')['can_ship'])

    def test_format_help_does_not_count_as_unclear_or_change_fields(self):
        text='Mera address ye hai Satpur Nashik aur Name Kunal'
        for event in ('first','second'):
            result=self.store.reply('A1',text,event)
        self.assertEqual(result['unclear_replies'],0)
        self.assertEqual(result['order'],self.initial['order'])
        self.assertEqual(result['messages'][-1]['template'],'detail_format')
        self.assertIn('double quotes',result['messages'][-1]['text'])

    def test_duplicate_field_or_invalid_name_is_atomic(self):
        for text in ('address "House 12, Main Road" name "test"',
                     'address "House 12, Main Road" name "Kunal" name "Other"'):
            result=self.store.reply('A1',text,text)
            self.assertEqual(result['order'],self.initial['order'])

    def test_replayed_combined_reply_is_idempotent(self):
        text='address "House 12, Main Road" name "Kunal"'
        first=self.store.reply('A1',text,'same')
        self.assertEqual(first,self.store.reply('A1',text,'same'))
        self.assertEqual(sum(r['kind']=='customer_corrected_details' for r in first['audit']),2)

    def test_closed_conversation_does_not_reopen_for_quoted_corrections(self):
        self.store.reply('A1','NO','cancel')
        result=self.store.reply('A1','address "House 12, Main Road" name "Kunal"','late')
        self.assertEqual(result['state'],'cancelled')
        self.assertEqual(result['order'],self.initial['order'])
