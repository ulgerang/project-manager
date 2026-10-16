import os
import json
from urllib.parse import urlsplit


def main():
    import webview
    from pmw.cli import load_config, config_dir

    config = load_config()
    base = config["url"].rstrip("/")
    url = os.getenv("PMW_WIDGET_URL", base + "/widget?compact=1")
    window = webview.create_window("Project Manager", url, width=460, height=640, on_top=True)

    def connected():
        # Never supply a saved token to a different origin after navigation.
        current = urlsplit(window.get_current_url() or "")
        trusted = urlsplit(base)
        if (current.scheme, current.netloc) != (trusted.scheme, trusted.netloc):
            return
        if config.get("token"):
            window.evaluate_js("window.pmwConnect(" + json.dumps(config["token"]) + ")")

    window.events.loaded += connected
    storage = config_dir() / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(gui="edgechromium", private_mode=False, storage_path=str(storage))
