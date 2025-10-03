import tkinter as tk
from tkinter import ttk
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException
import time

# Config Modbus (thay COM_PORT nếu khác)
COM_PORT = 'COM3'  # Thay bằng COM của USB-RS485
BAUDRATE = 9600
PARITY = 'E'  # Even
BYTESIZE = 8
STOPBITS = 1
SLAVE_ID = 1
TIMEOUT = 1  # giây

# Mapping registers và scaling (dựa trên Danfoss FC302 manual)
REGISTERS = {
    'Output Frequency': {'addr': 3, 'scale': 0.01, 'unit': 'Hz'},  # raw /100 = Hz
    'Output Current': {'addr': 13, 'scale': 0.01, 'unit': 'A'},     # raw /100 = A
    'Output Voltage': {'addr': 19, 'scale': 0.1, 'unit': 'V'},      # raw /10 = V
    'DC Bus Voltage': {'addr': 20, 'scale': 0.1, 'unit': 'V'},      # raw /10 = V
    'Motor Speed': {'addr': 69, 'scale': 1.0, 'unit': 'RPM'}        # raw = RPM (signed 16-bit)
}

class FC302Monitor:
    def __init__(self, root):
        self.root = root
        self.root.title("FC302 Modbus Monitor - Danfoss VFD")
        self.root.geometry("500x400")
        
        # Modbus client
        self.client = ModbusSerialClient(
            method='rtu',
            port=COM_PORT,
            baudrate=BAUDRATE,
            parity=PARITY,
            bytesize=BYTESIZE,
            stopbits=STOPBITS,
            timeout=TIMEOUT
        )
        
        # Kết nối
        if not self.client.connect():
            self.show_error("Lỗi kết nối RS485! Check COM port và wiring.")
            return
        
        # GUI: Treeview để hiển thị table
        columns = ('Parameter', 'Raw Value (Dec)', 'Raw Value (Hex)', 'Scaled Value')
        self.tree = ttk.Treeview(root, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
        
        self.tree.pack(pady=10, fill=tk.BOTH, expand=True)
        
        # Status label
        self.status_label = tk.Label(root, text="Status: Connected - Polling every 1s", fg='green')
        self.status_label.pack(pady=5)
        
        # Insert rows
        for param in REGISTERS.keys():
            self.tree.insert('', 'end', values=(param, '---', '---', '---'))
        
        # Start polling
        self.update_data()
    
    def read_register(self, addr):
        try:
            result = self.client.read_holding_registers(addr, 1, slave=SLAVE_ID)
            if not result.isError():
                return result.registers[0]  # 16-bit unsigned, adjust signed nếu cần (e.g., for speed: if >32767: - (65536 - val))
            else:
                raise ModbusException(f"Error reading addr {addr}: {result}")
        except Exception as e:
            self.show_error(f"Lỗi đọc register {addr}: {e}")
            return None
    
    def update_data(self):
        for item in self.tree.get_children():
            param_name = self.tree.item(item)['values'][0]
            if param_name in REGISTERS:
                addr = REGISTERS[param_name]['addr']
                raw_dec = self.read_register(addr)
                if raw_dec is not None:
                    raw_hex = f"0x{raw_dec:04X}"
                    scaled = raw_dec * REGISTERS[param_name]['scale']
                    unit = REGISTERS[param_name]['unit']
                    self.tree.item(item, values=(param_name, raw_dec, raw_hex, f"{scaled:.2f} {unit}"))
                else:
                    self.tree.item(item, values=(param_name, 'Error', '---', '---'))
        
        # Schedule next poll
        self.root.after(1000, self.update_data)  # 1 giây
    
    def show_error(self, msg):
        self.status_label.config(text=f"Status: Error - {msg}", fg='red')
        print(f"Error: {msg}")  # Log console
    
    def __del__(self):
        if self.client:
            self.client.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = FC302Monitor(root)
    root.mainloop()