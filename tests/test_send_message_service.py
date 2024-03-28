import unittest
from mocks import *
from unittest import mock
from homeassistant.helpers import dispatcher
import inspect

dispatcher.dispatcher_send = mock.Mock(return_value=None)

class TestSendMessageService(unittest.IsolatedAsyncioTestCase):

    def create_gateway(self):
        gateway = GatewayMock(dev_id=123)

        return gateway
    
    def get_all_eep_names(self):
        subclasses = set()
        work = [EEP]
        while work:
            parent = work.pop()
            for child in parent.__subclasses__():
                if child not in subclasses:
                    subclasses.add(child)
                    work.append(child)
        return sorted(set([s.__name__.upper().replace('_','-') for s in subclasses if len(s.__name__) == 8 and s.__name__.count('_') == 2]))

    NOT_SUPPORTED_EEPS = ['A5-09-0C', 'A5-38-08']

    async def test_send_message(self):
        g = self.create_gateway()
        # Mock send_message
        g.send_message = lambda *args: None

        for eep_name in self.get_all_eep_names():

            if eep_name in self.NOT_SUPPORTED_EEPS:
                continue

            event = EventMock('service_name', {
                'id': 'FF-DD-CC-BB',
                'eep': eep_name,
                'command': 1,
                'identifier': 1
            })

            await g.async_service_send_message(event, True)


    async def test_write_eep_params_to_docs_file(self):
        text  = '# Paramters for EEPs in Send Message Events'
        text += '\n'

        text += "## Not Supported EEPs \n"
        for eep_name in self.NOT_SUPPORTED_EEPS:
            text += f"* {eep_name}\n"
        text += '\n'

        text += '## Parameters for events: \n'

        for eep_name in self.get_all_eep_names():

            if eep_name in self.NOT_SUPPORTED_EEPS:
                continue
    
            sig = inspect.signature(EEP.find(eep_name).__init__)
            eep_init_args = sorted([param.name for param in sig.parameters.values() if param.kind == param.POSITIONAL_OR_KEYWORD and param.name != 'self'])
            text += f"* {eep_name}: {', '.join(eep_init_args)}\n"

        text += '\n'
        text += '## References:\n'
        text += 'Implementation of EEPs can be found [eltako14bus library](https://github.com/grimmpp/eltako14bus/blob/master/eltakobus/eep.py).\n'

        file='./docs/service-send-message/eep-params.md' 
        with open(file, 'w') as filetowrite:
            filetowrite.write(text)


