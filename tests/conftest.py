from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("LOG_FILE", "")


# дублирует pytest.ini, чтобы тесты шли и без него
def pytest_configure(config):
    config.option.asyncio_mode = "auto"
    config.inicfg.setdefault("asyncio_default_fixture_loop_scope", "function")

