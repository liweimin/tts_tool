import unittest
from pathlib import Path

from tts_reader.config import (
    AppConfig,
    get_app_dir,
    get_default_config_path,
    parse_hotkey,
    read_config,
    write_config,
    write_default_config_if_missing,
)
from tts_reader.autostart import (
    _normalize_cmd,
    get_target_command,
    get_startup_shortcut_path,
)


class TestConfigAndAutostart(unittest.TestCase):
    def test_hotkey_parsing(self):
        mods, vk = parse_hotkey("alt+q")
        self.assertGreater(mods, 0)
        self.assertEqual(vk, ord("Q"))

    def test_config_path_is_absolute_and_valid(self):
        config_path = get_default_config_path()
        self.assertTrue(config_path.is_absolute())
        self.assertNotIn("System32", str(config_path))

    def test_app_dir_exists(self):
        app_dir = get_app_dir()
        self.assertTrue(app_dir.exists())

    def test_cmd_normalization(self):
        cmd1 = '"C:\\Program Files\\app.exe"'
        cmd2 = "c:/program files/app.exe"
        self.assertEqual(_normalize_cmd(cmd1), _normalize_cmd(cmd2))

    def test_startup_shortcut_path(self):
        p = get_startup_shortcut_path()
        self.assertTrue(p.name.endswith(".lnk"))
        self.assertIn("Startup", str(p))


if __name__ == "__main__":
    unittest.main()
