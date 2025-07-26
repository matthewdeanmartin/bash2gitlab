# --- pytest ---
from bash2gitlab.__main__ import to_job


def test_to_job(tmp_path):
    test_script = tmp_path / "deploy.sh"
    test_script.write_text("""#!/bin/bash
# CI_STAGE=deploy
# CI_IMAGE=alpine:latest
# CI_TAGS=fast,secure
# CI_ARTIFACTS=out.log,build/
echo 'Hello world'
""")
    expected = {
        "deploy": {
            "stage": "deploy",
            "image": "alpine:latest",
            "tags": ["fast", "secure"],
            "artifacts": {"paths": ["out.log", "build/"]},
            "script": ["bash deploy.sh"]
        }
    }
    result = to_job(test_script)
    assert result == expected
