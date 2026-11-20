import stat
from pathlib import Path

from acta.config import load_config, save_config


def test_save_config_is_owner_only_and_round_trips_capacity(
    tmp_path: Path,
):
    config_path = tmp_path / ".config"
    expected = {
        "MAX_SPINES": "4",
        "MAX_LEAVES": "8",
        "MAX_MLEAFS_PER_PAIR": "2",
    }

    save_config(config_path, expected)

    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    loaded = load_config(config_path)
    assert {key: loaded[key] for key in expected} == expected
