"""Application bootstrap layer."""

import os
from .config import kmodel_path


def start():
    try:
        os.stat(kmodel_path)
    except Exception:
        raise RuntimeError("Model file not found: {}".format(kmodel_path))

    from .steel_ball_app import run
    run()
