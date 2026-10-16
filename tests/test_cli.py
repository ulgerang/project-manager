import json
import os
from unittest.mock import patch

from pmw import cli


def test_offline_queue_is_explicit(tmp_path,capsys):
    os.environ["PMW_CONFIG_DIR"]=str(tmp_path)
    os.environ["PMW_URL"]="http://127.0.0.1:1"
    os.environ["PMW_TOKEN"]="nope"
    assert cli.main(["--json","init","--name","Queued","--queue"]) == 0
    result=json.loads(capsys.readouterr().out)
    assert result["pending"] is True
    assert len((tmp_path/"queue.jsonl").read_text().splitlines()) == 1

def test_offline_without_queue_fails(tmp_path,capsys):
    os.environ["PMW_CONFIG_DIR"]=str(tmp_path); os.environ["PMW_URL"]="http://127.0.0.1:1"; os.environ["PMW_TOKEN"]="nope"
    assert cli.main(["init","--name","Not queued"]) == 1
    assert "NOT committed" in capsys.readouterr().err
