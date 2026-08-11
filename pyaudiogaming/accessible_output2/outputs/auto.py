from __future__ import absolute_import
import pyaudiogaming.accessible_output2
from .base import Output, OutputError


class Auto(Output):
    """An output which automatically selects the first available output on the system"""
    def __init__(self):
        output_classes = pyaudiogaming.accessible_output2.get_output_classes()
        self.outputs = []
        for output in output_classes:
            try:
                self.outputs.append(output())
            except OutputError:
                pass
        print(self.outputs)

    def get_first_available_output(self):
        """
        Finds the ffirst available output.
        This is automatically called in braille, output and speak.
        """
        for output in self.outputs:
            if output.is_active():
                return output
        return None

    def speak(self, *args, **kwargs):
        """
        Speaks the given text if the output supports speech

        Args:
          text (str): The text to speak.
          **options: Additional options.
        """
        output = self.get_first_available_output()
        if output:
            output.speak(*args, **kwargs)

    def silence(self):
        output = self.get_first_available_output()
        if output:
            if output.silence:
                output.silence()

    def get_volume(self):
        output = self.get_first_available_output()
        if output and hasattr(output, 'get_volume'):
            return output.get_volume()
    def set_volume(self, volume):
        output = self.get_first_available_output()
        if output and hasattr(output, 'set_volume'):
            output.set_volume(volume)

    def get_rate(self):
        output = self.get_first_available_output()
        if output and hasattr(output, 'get_rate'):
            return output.get_rate()
        return None

    def set_rate(self, rate):
        output = self.get_first_available_output()
        if output and hasattr(output, 'set_rate'):
            output.set_rate(rate)

    def get_pitch(self):
        output = self.get_first_available_output()
        if output and hasattr(output, 'get_pitch'):
            return output.get_pitch()
        return None

    def set_pitch(self, pitch):
        output = self.get_first_available_output()
        if output and hasattr(output, 'set_pitch'):
            output.set_pitch(pitch)

    def get_voice(self):
        output = self.get_first_available_output()
        if output and hasattr(output, 'get_voice'):
            return output.get_voice()
        return None

    def set_voice(self, voice):
        output = self.get_first_available_output()
        if output and hasattr(output, 'set_voice'):
            output.set_voice(voice)
    def braille(self, *args, **kwargs):
        """
        Brailles the given text if the output supports Braille

        Args:
          text (str): The text to braille.
          **options: Additional options.
        """
        output = self.get_first_available_output()
        if output:
            output.braille(*args, **kwargs)

    def output(self, *args, **kwargs):
        output = self.get_first_available_output()
        if output:
            output.speak(*args, **kwargs)

    def is_system_output(self):
        """Returns True if this output is a system output."""
        output = self.get_first_available_output()
        if output:
            return output.is_system_output()

    def call(self, name_functions, *args, **kwargs):
        output = self.get_first_available_output()

        if not output or not hasattr(output, name_functions): return None
        func = getattr(output, name_functions)
        if callable(func):
            return func(*args, **kwargs)
        return None