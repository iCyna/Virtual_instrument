from .base import Output
from pyaudiogaming import system
from plyer import tts # Thư viện gọi TTS của Android/iOS

class Android_TTS(Output):
    """Trình đọc màn hình dành riêng cho Mobile (Android/iOS)"""
    name = "Android_TTS"
    priority = 100 # Đặt priority cao để nó ghi đè Auto() trên mobile

    def is_active(self):
        # Tự động kích hoạt nếu platform là android hoặc ios
        os_info = system.get_platform()["os"]
        return os_info in ("android", "ios")

    def speak(self, text, interrupt=False):
        if interrupt:
            self.silence()
        tts.speak(str(text))

    def silence(self):
        # Plyer TTS hiện tại không hỗ trợ ngắt giữa chừng, 
        # nhưng nếu dùng Pyjnius để gọi thẳng Android API thì có thể ngắt được.
        pass