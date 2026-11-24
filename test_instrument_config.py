import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import core as instruments
import setting
from audio_instruments import vst3


class InstrumentConfigTests(unittest.TestCase):
    def test_all_instruments_include_vst3_fields(self):
        cfg = instruments.default_config()
        for inst_name in ('piano', 'guitar', 'drum', 'bass', 'electronic drum', 'strings', 'synth', 'flute'):
            entry = cfg['instruments'][inst_name]
            self.assertIn('vst3_path', entry)
            self.assertIn('vst3_state', entry)
            self.assertIn('vst3_use_native_gui', entry)

    def test_missing_optional_fonts_use_general_font_and_preserve_program(self):
        for name, program in [('strings', 48), ('synth', 81), ('flute', 73)]:
            original = dict(active_engine='sf2', sf2_path=f'sf2toolkit/{name.title()}.sf2', sf2_id=program)
            config = {'instruments': {name: original}}
            resolved = instruments.resolve_config(config, name)
            self.assertEqual(Path(resolved['sf2_path']), instruments.GENERAL_FONT)
            self.assertEqual(resolved['sf2_id'], program)
            self.assertEqual(original['sf2_path'], f'sf2toolkit/{name.title()}.sf2')

    def test_custom_missing_font_reports_error(self):
        with self.assertRaises(FileNotFoundError):
            instruments.resolve_config({'instruments': {'guitar': dict(sf2_path='missing-custom.sf2')}}, 'guitar')

    def test_existing_custom_font_is_preserved(self):
        with tempfile.TemporaryDirectory(dir='.') as folder:
            path = Path(folder).resolve() / 'Strings.sf2'
            path.touch()
            resolved = instruments.resolve_config({'instruments': {'strings': dict(sf2_path=str(path))}}, 'strings')
            self.assertEqual(resolved['sf2_path'], str(path))

    def test_android_automatically_avoids_vst_and_vst3(self):
        for eng in ('vst', 'vst3'):
            cfg = {'instruments': {'bass': dict(
                active_engine=eng, vst_path='fake.dll', vst3_path='fake.vst3',
                sf2_path='sf2toolkit/GeneralUserGS-v1471.sf2', sf2_id=32)}}
            with patch('core.system.get_platform', return_value={'os': 'android'}):
                self.assertTrue(instruments.is_android())
                self.assertFalse(instruments.vst_supported())
                resolved = instruments.resolve_config(cfg, 'bass')
                self.assertEqual(resolved['active_engine'], 'sf2')
                self.assertTrue(Path(resolved['sf2_path']).is_file())

    def test_vst3_checkbox_switches_between_native_gui_and_vb_form(self):
        with tempfile.TemporaryDirectory(dir='.') as folder:
            fake_vst3 = Path(folder) / 'Vital.vst3'
            fake_vst3.touch()
            fake_w = Mock()
            fake_plugin = Mock()
            fake_plugin.create_instrument.return_value = True
            fake_plugin.get_parameter_index.return_value = []
            fake_plugin.show_native_gui.return_value = 'U1RBVEVfR1VJ'
            fake_plugin.get_state.return_value = 'U1RBVEVfRk9STQ=='

            with patch('audio_instruments.vst3', return_value=fake_plugin), \
                 patch('setting._probe_vst3_safe', return_value=(True, '')), \
                 patch('setting.save'), \
                 patch('core.vst_supported', return_value=True), \
                 patch('setting.open_vst3_parameter_form', return_value=True) as form_mock:
                setting._VST3_CACHE.clear()
                # Checkbox True -> Native GUI
                ok_gui = setting.open_vst3_controls(fake_w, 'bass', str(fake_vst3), use_native_gui=True)
                self.assertTrue(ok_gui)
                fake_plugin.show_native_gui.assert_called_once()
                form_mock.assert_not_called()
                self.assertEqual(instruments.config['instruments']['bass']['vst3_state'], 'U1RBVEVfR1VJ')

                # Checkbox False -> Accessible vb.form
                ok_form = setting.open_vst3_controls(fake_w, 'bass', str(fake_vst3), use_native_gui=False)
                self.assertTrue(ok_form)
                form_mock.assert_called_once()
                self.assertEqual(instruments.config['instruments']['bass']['vst3_state'], 'U1RBVEVfRk9STQ==')
                setting._VST3_CACHE.clear()

    def test_vst3_render_events_outputs_stereo_pcm16(self):
        import numpy as np
        host = vst3()
        host.plugin = Mock()
        host.engine = Mock()
        host.engine.get_audio.return_value = np.zeros((2, 4410), dtype=np.float32)
        pcm = host.render_events([(0, 'on', 60, 100), (100, 'off', 60, 0)], total_time_ms=100, chan=0)
        self.assertEqual(len(pcm), 4410 * 4)
