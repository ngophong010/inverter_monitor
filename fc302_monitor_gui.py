import tkinter as tk
from tkinter import ttk
import threading
import time
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ConnectionException

# --- Cấu hình Modbus ---
COM_PORT = 'COM3'  # <-- NHỚ THAY ĐỔI CỔNG COM CỦA BẠN Ở ĐÂY
BAUD_RATE = 9600
SLAVE_ID = 1

# --- Mapping registers và scaling (Cải tiến từ code của Grok) ---
REGISTERS = {
    'Output Frequency': {'addr': 3, 'scale': 0.01, 'unit': 'Hz', 'signed': False},
    'Output Current':   {'addr': 13, 'scale': 0.01, 'unit': 'A', 'signed': False},
    'Output Voltage':   {'addr': 19, 'scale': 0.1, 'unit': 'V', 'signed': False},
    'DC Bus Voltage':   {'addr': 20, 'scale': 0.1, 'unit': 'V', 'signed': False},
    'Motor Speed':      {'addr': 69, 'scale': 1.0, 'unit': 'RPM', 'signed': True} # Tốc độ có thể âm
}

class ModbusMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Danfoss FC302 Monitor (Improved Version)")
        self.root.geometry("600x250")
        
        # Dùng để lưu trữ dữ liệu mới nhất, thread-safe
        self.data_values = {} 

        self._setup_ui()

        # Bắt đầu luồng đọc Modbus
        self.is_running = True
        self.modbus_thread = threading.Thread(target=self.poll_modbus_data, daemon=True)
        self.modbus_thread.start()

        # Bắt đầu vòng lặp cập nhật GUI
        self.update_gui()
        
        # Xử lý khi đóng cửa sổ một cách an toàn
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _setup_ui(self):
        # Tạo Treeview với các cột mới
        columns = ('raw_dec', 'raw_hex', 'scaled')
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings")
        
        self.tree.heading("#0", text="Thông số")
        self.tree.heading("raw_dec", text="Giá trị Raw (Dec)")
        self.tree.heading("raw_hex", text="Giá trị Raw (Hex)")
        self.tree.heading("scaled", text="Giá trị Quy đổi")
        
        # Chỉnh độ rộng cột
        self.tree.column("#0", width=150, anchor="w")
        self.tree.column("raw_dec", width=120, anchor="center")
        self.tree.column("raw_hex", width=120, anchor="center")
        self.tree.column("scaled", width=150, anchor="center")

        # Thêm các dòng cho từng thông số
        for param_name in REGISTERS.keys():
            self.tree.insert("", "end", iid=param_name, text=param_name, values=("N/A", "N/A", "N/A"))

        self.tree.pack(expand=True, fill="both", padx=10, pady=10)

        # Thanh trạng thái
        self.status_var = tk.StringVar(value="Đang khởi tạo...")
        self.status_label = tk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w")
        self.status_label.pack(side="bottom", fill="x")

    def poll_modbus_data(self):
        # Sửa lỗi: Đã xóa 'method'
        client = ModbusSerialClient(port=COM_PORT, baudrate=BAUD_RATE, parity='E', stopbits=1, timeout=1)
        
        while self.is_running:
            try:
                if not client.is_socket_open():
                    client.connect()

                if client.is_socket_open():
                    self.status_var.set(f"Đã kết nối tới {COM_PORT} - Đang đọc dữ liệu...")
                    
                    for param_name, details in REGISTERS.items():
                        addr = details['addr']
                        result = client.read_holding_registers(address=addr - 1, count=1, slave=SLAVE_ID)
                        
                        if not result.isError():
                            raw_value = result.registers[0]
                            
                            # Xử lý giá trị signed 16-bit nếu cần
                            if details['signed'] and raw_value > 32767:
                                signed_value = raw_value - 65536
                            else:
                                signed_value = raw_value
                                
                            scaled_value = f"{signed_value * details['scale']:.2f} {details['unit']}"
                            hex_value = f"0x{raw_value:04X}"
                            
                            self.data_values[param_name] = (signed_value, hex_value, scaled_value)
                        else:
                            self.data_values[param_name] = ("Error", "Error", "Error")
                else:
                    self.status_var.set(f"Lỗi: Không thể kết nối tới {COM_PORT}")

            except ConnectionException:
                 self.status_var.set(f"Lỗi kết nối. Kiểm tra cổng {COM_PORT} và thiết bị.")
            except Exception as e:
                self.status_var.set(f"Lỗi không xác định: {e}")
            
            time.sleep(1) # Chờ 1 giây
        
        client.close()
        print("Modbus client closed.")

    def update_gui(self):
        # Cập nhật giá trị trong Treeview
        for param_name, values in self.data_values.items():
            self.tree.item(param_name, values=values)
        
        # Lên lịch chạy lại hàm này sau 200ms
        if self.is_running:
            self.root.after(200, self.update_gui)

    def on_closing(self):
        print("Closing application...")
        self.is_running = False # Dừng luồng đọc dữ liệu
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ModbusMonitorApp(root)
    root.mainloop()
    