import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from multiformat import save_file


class SaveDialogTests(unittest.TestCase):
    def test_save_and_cancel_destroy_dialog_and_restore_window_list(self):
        for result, expected in ((1, 'D:/Music/song.inv'), (0, None)):
            dialog = Mock()
            dialog.ShowModal.return_value = result
            dialog.GetPath.return_value = 'D:/Music/song.inv'
            wx = SimpleNamespace(FileDialog=Mock(return_value=dialog), FD_SAVE=2,
                                 FD_OVERWRITE_PROMPT=4, ID_OK=1)
            buffer = SimpleNamespace(names_window=[])
            package = SimpleNamespace(buffer=buffer)
            with patch.dict(sys.modules, {'wx': wx, 'pyaudiogaming': package}):
                self.assertEqual(save_file('Save Project', 'project.inv', '*.inv'), expected)
            self.assertEqual(wx.FileDialog.call_args.kwargs['style'], 6)
            self.assertEqual(wx.FileDialog.call_args.kwargs['defaultFile'], 'project.inv')
            dialog.Destroy.assert_called_once()
            self.assertEqual(buffer.names_window, [])
