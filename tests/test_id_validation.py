import unittest
from custom_components.eltako.config_helpers import compare_enocean_ids
from eltakobus import AddressExpression

class TestIdComparison(unittest.TestCase):

    def mock_send_message(self, msg):
        self.last_sent_command = msg

    def test_id_validation(self):
        id1 = AddressExpression.parse('00-12-FA-50')
        id2 = AddressExpression.parse('00-12-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=4)

        self.assertTrue(result)

    def test_neg_id_validation(self):
        id1 = AddressExpression.parse('00-12-FA-FF')
        id2 = AddressExpression.parse('00-12-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=4)

        self.assertTrue(not result)

        id1 = AddressExpression.parse('11-12-FA-FF')
        id2 = AddressExpression.parse('00-12-FA-FF')
        result = compare_enocean_ids(id1[0], id2[0], len=4)

        self.assertTrue(not result)

    def test_base_id_comparison(self):
        id1 = AddressExpression.parse('FF-BB-FA-00')
        id2 = AddressExpression.parse('FF-BB-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(result)

        id1 = AddressExpression.parse('00-00-00-00')
        id2 = AddressExpression.parse('00-00-00-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(result)

    def test_neg_base_id_comparison(self):
        id1 = AddressExpression.parse('00-BB-FA-00')
        id2 = AddressExpression.parse('FF-BB-FA-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(not result)

        id1 = AddressExpression.parse('FF-BB-00-00')
        id2 = AddressExpression.parse('00-00-00-50')
        result = compare_enocean_ids(id1[0], id2[0], len=3)

        self.assertTrue(not result)