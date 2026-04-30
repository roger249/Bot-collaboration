import pytest

from src import main


def test_run_client_investment_proposal_monkeypatched(monkeypatch):
    called = {}

    def fake_run(app_config, cfg_path, proposal):
        called['args'] = (app_config, cfg_path, proposal)
        class Dummy:
            pass

        return Dummy()

    monkeypatch.setattr(main, 'run_crew_planbot', fake_run)

    result = main.run_planbot_programmatically(
        config_path='config/config.yaml',
        planbot_config='config/config_planbot.yaml',
        proposal='client_investment_proposal',
    )

    assert 'args' in called
    assert called['args'][1] == 'config/config_planbot.yaml'
    assert called['args'][2] == 'client_investment_proposal'
    assert result is not None
