import time
import psutil

class TelemetryRadar:
    def __init__(self):
        print("📡 Booting Hardware Telemetry...")
        self.start_time = time.time()
        self.net_start = psutil.net_io_counters()

    def shutdown_and_report(self):
        end_time = time.time()
        net_end = psutil.net_io_counters()

        elapsed_sec = end_time - self.start_time
        mb_downloaded = (net_end.bytes_recv - self.net_start.bytes_recv) / (1024 * 1024)
        mb_uploaded = (net_end.bytes_sent - self.net_start.bytes_sent) / (1024 * 1024)

        ram_info = psutil.virtual_memory()
        ram_used_gb = ram_info.used / (1024**3)
        ram_total_gb = ram_info.total / (1024**3)
        
        print("\n" + "="*50)
        print(" 📉 HARDWARE & NETWORK DIAGNOSTICS")
        print("="*50)
        print(f"⏱️ Execution Time : {elapsed_sec:.2f} Seconds")
        print(f"📥 Total Downloaded : {mb_downloaded:.2f} MB")
        print(f"📤 Total Uploaded   : {mb_uploaded:.2f} MB")
        print(f"🧠 RAM Usage (End)  : {ram_used_gb:.2f} GB / {ram_total_gb:.2f} GB ({ram_info.percent}%)")
        print("="*50 + "\n")
