import win32serviceutil
import win32service
import win32event
import servicemanager
import threading
import time
import traceback
from pc_super_core import process_loop, log, log_error

class PCSuperService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PC_super"
    _svc_display_name_ = "PC_super Mail AI Service"
    _svc_description_ = "Sprawdza maile, generuje odpowiedzi AI i obrazy."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.worker_thread = None
        self.watchdog_thread = None
        self._stop_requested = False

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self._stop_requested = True
        try:
            win32event.SetEvent(self.stop_event)
        except Exception:
            pass
        log("SvcStop called, oczekiwanie na zakończenie wątków...")

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("PC_super service started")
        log("Usługa PC_super uruchomiona")
        # Start worker thread
        self._start_worker_and_watchdog()
        # Czekaj na sygnał stop
        win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
        # Po otrzymaniu stop, ustaw flagę i poczekaj na zakończenie
        self._stop_requested = True
        log("Otrzymano sygnał stop, kończenie wątków...")
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=10)
        if self.watchdog_thread and self.watchdog_thread.is_alive():
            self.watchdog_thread.join(timeout=5)
        servicemanager.LogInfoMsg("PC_super service stopped")
        log("Usługa PC_super zatrzymana")

    def _start_worker_and_watchdog(self):
        # Worker thread runs process_loop
        def worker():
            try:
                log("Worker thread start")
                process_loop()
            except Exception as e:
                log_error(f"Worker thread exception: {e}\n{traceback.format_exc()}")
            finally:
                log("Worker thread zakończony")

        # Watchdog restarts worker if it dies unexpectedly
        def watchdog():
            while not self._stop_requested:
                if not self.worker_thread or not self.worker_thread.is_alive():
                    log("Watchdog: worker nieaktywny, uruchamiam nowy wątek worker")
                    self.worker_thread = threading.Thread(target=worker, daemon=True)
                    self.worker_thread.start()
                time.sleep(5)
            log("Watchdog kończy działanie")

        # Start initial worker and watchdog
        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()
        self.watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        self.watchdog_thread.start()

if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(PCSuperService)
