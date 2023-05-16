from typing import Any

class BusMock():

    def __init__(self):
        self.fired_events = list()

    def fire(self, 
                event_type: str,
                event_data: dict[str, Any] | None = None,
                origin = None,
                context = None,
                ) -> None:
        
        self.fired_events.append({
            'event_type': event_type,
            'event_data': event_data,
            'origin': origin,
            'context': context
        })

class HassMock():
        
    def __init__(self) -> None:
        self.bus = BusMock()