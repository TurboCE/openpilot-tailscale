import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from installer import add_block, remove_block, BEGIN, END


class StartupHookTests(unittest.TestCase):
    def test_carrot_boot_is_preserved_and_nonblocking(self):
        old = '#!/usr/bin/env bash\n\ncd /data/openpilot\nexec ./launch_openpilot.sh\n'
        new = add_block(old)
        self.assertIn('start.sh >> /data/tailscale-start.log 2>&1 &\n', new)
        self.assertTrue(new.endswith('\ncd /data/openpilot\nexec ./launch_openpilot.sh\n'))
        self.assertEqual(remove_block(new), old)

    def test_frog_custom_commands_are_preserved(self):
        old = '#!/usr/bin/bash\nset -e\n/custom/hook --flag\nexec /data/openpilot/launch_openpilot.sh\n'
        self.assertEqual(remove_block(add_block(old)), old)

    def test_rerun_does_not_duplicate_hook(self):
        old = '#!/bin/bash\nexec ./launch.sh\n'
        once = add_block(old)
        self.assertEqual(add_block(once), once)
        self.assertEqual(once.count(BEGIN), 1)

    def test_refuse_old_unmanaged_tailscale_hook(self):
        with self.assertRaises(ValueError):
            add_block('#!/bin/bash\n/data/tailscale/start.sh\nexec ./launch.sh\n')

    def test_refuse_unbalanced_markers(self):
        for text in (BEGIN + '\n', END + '\n', BEGIN + '\n' + BEGIN + '\n' + END + '\n' + END):
            with self.assertRaises(ValueError):
                remove_block(text)


if __name__ == '__main__':
    unittest.main()
