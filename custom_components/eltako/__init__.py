import os
# optionally do not load integration init
# when using e.g. const as lib in a different project whole home assistant is loaded because it expects the setup functions in the __init__.py file. 
# To avoid loading home assistant which also crashes the event loop this opt out is placed.
if not os.environ.get('SKIPP_IMPORT_HOME_ASSISTANT'):
    from .eltako_integration_init import *