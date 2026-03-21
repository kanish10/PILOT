"""
Dependency injection container.
main.py wires everything up; routes.py reads from here.
Avoids circular imports.
"""
class Container:
    def __init__(self) -> None:
        self._orchestrator = None

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            raise RuntimeError("Orchestrator has not been initialised yet")
        return self._orchestrator

    @orchestrator.setter
    def orchestrator(self, value) -> None:
        self._orchestrator = value


container = Container()
