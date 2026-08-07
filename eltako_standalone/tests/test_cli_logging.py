"""The daemon writes its process log into the config folder, the quick commands do not.

The config folder mirrors the Home Assistant one, where `home-assistant.log` sits next to
`configuration.yaml` - so `serve` and `run` write `eltako-standalone.log` there. A `scan` is
over in a second and must not interleave its lines into the log of a running daemon.
"""

import logging
import os

from eltako_standalone import cli


def _args(command: str, config_dir: str, debug: bool = False):
    argv = ["--config", config_dir]
    if debug:
        argv.append("--debug")
    argv.append(command)
    return cli.build_parser().parse_args(argv)


def _teardown_logging():
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)


def test_serve_writes_the_log_file(tmp_path):
    try:
        cli._setup_logging(_args("serve", str(tmp_path)))
        logging.getLogger("eltako").info("a line the console hides but the file keeps")

        log_file = tmp_path / cli.LOG_FILENAME
        assert log_file.exists()
        content = log_file.read_text()
        assert "Process log:" in content                      # says where it logs to
        assert "a line the console hides but the file keeps" in content
    finally:
        _teardown_logging()


def test_the_config_folder_is_created_for_the_log(tmp_path):
    config_dir = tmp_path / "does" / "not" / "exist"
    try:
        cli._setup_logging(_args("run", str(config_dir)))
        assert (config_dir / cli.LOG_FILENAME).exists()
    finally:
        _teardown_logging()


def test_quick_commands_do_not_write_a_file(tmp_path):
    try:
        cli._setup_logging(_args("scan", str(tmp_path)))
        logging.getLogger("eltako").error("an error of a quick command")

        assert not (tmp_path / cli.LOG_FILENAME).exists()
        assert not os.listdir(tmp_path)
    finally:
        _teardown_logging()


def test_the_console_stays_quiet_without_debug(tmp_path):
    """The filter which protects the terminal: integration INFO is file-only."""
    try:
        cli._setup_logging(_args("serve", str(tmp_path)))
        console = next(handler for handler in logging.getLogger().handlers
                       if not hasattr(handler, 'baseFilename'))

        def visible(name, level):
            return console.filter(logging.LogRecord(name, level, __file__, 1, "x", (), None))

        assert not visible("eltako", logging.INFO)            # the integration talks a lot
        assert not visible("eltako", logging.WARNING)         # was ERROR-only before as well
        assert visible("eltako", logging.ERROR)
        assert not visible("eltako_standalone.server", logging.INFO)
        assert visible("eltako_standalone", logging.WARNING)
        assert not visible("aiohttp.access", logging.INFO)    # one line per http request
        assert visible("some.other.library", logging.WARNING)
    finally:
        _teardown_logging()


def test_debug_shows_everything_on_the_console(tmp_path):
    try:
        cli._setup_logging(_args("serve", str(tmp_path), debug=True))
        console = next(handler for handler in logging.getLogger().handlers
                       if not hasattr(handler, 'baseFilename'))

        record = logging.LogRecord("eltako", logging.DEBUG, __file__, 1, "x", (), None)
        assert console.filter(record)
        assert logging.getLogger().level == logging.DEBUG
    finally:
        _teardown_logging()
