import sys
import time
import serial.tools.list_ports
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QComboBox, QPushButton, QTableWidget, QTableWidgetItem, 
                             QLabel, QHeaderView, QAbstractItemView)
from PySide6.QtCore import QThread, QObject, Signal, Slot
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ConnectionException

# --- Cấu hình Registers (Giữ nguyên cấu trúc tốt) ---
REGISTERS = {
    'Output Frequency': {'addr': 3, 'scale': 0.01, 'unit': 'Hz', 'signed': False},
    'Output Current':   {'addr': 13, 'scale': 0.01, 'unit': 'A', 'signed': False},
    'Output Voltage':   {'addr': 19, 'scale': 0.1, 'unit': 'V', 'signed': False},
    'DC Bus Voltage':   {'addr': 20, 'scale': 0.1, 'unit': 'V', 'signed': False},
    'Motor Speed':      {'addr': 69, 'scale': 1.0, 'unit': 'RPM', 'signed': True}
}

# --- Lớp Worker: Chạy trong một luồng riêng để đọc Modbus ---
class ModbusWorker(QObject):
    data_ready = Signal(dict) 
    status_updated = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, port, slave_id, baudrate=9600):
        super().__init__()
        self.port = port
        self.slave_id = slave_id
        self.baudrate = baudrate
        self.is_running = True
        self.client = None

    @Slot()
    def run(self):
        self.status_updated.emit(f"Connecting to {self.port}...")
        try:
            self.client = ModbusSerialClient(
                port=self.port, baudrate=self.baudrate, 
                parity='E', stopbits=1, timeout=1
            )
            self.client.connect()
        except Exception as e:
            self.error_occurred.emit(f"Failed to connect: {e}")
            return

        if not self.client.is_socket_open():
            self.error_occurred.emit("Connection failed. Check port and wiring.")
            return

        self.status_updated.emit("Connected. Polling data...")

        while self.is_running:
            all_data = {}
            try:
                for param_name, details in REGISTERS.items():
                    addr = details['addr']
                    result = self.client.read_holding_registers(address=addr - 1, count=1, slave=self.slave_id)
                    
                    if not result.isError():
                        raw_value = result.registers[0]
                        all_data[param_name] = raw_value
                    else:
                        all_data[param_name] = "Error"
                        self.status_updated.emit(f"Error reading {param_name}")

                self.data_ready.emit(all_data)
                time.sleep(1)

            except Exception as e:
                self.error_occurred.emit(f"Modbus error: {e}")
                self.is_running = False
        
        if self.client:
            self.client.close()
        self.status_updated.emit("Disconnected.")
    
    def stop(self):
        self.is_running = False

# --- Lớp Giao diện chính ---
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro FC302 Monitor")
        self.setGeometry(100, 100, 700, 400)
        
        self.thread = None
        self.worker = None

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(self._create_connection_panel())
        main_layout.addWidget(self._create_data_table())
        self.status_label = QLabel("Status: Ready. Please connect to a device.")
        main_layout.addWidget(self.status_label)

    def _create_connection_panel(self):
        panel_layout = QHBoxLayout()
        panel_layout.addWidget(QLabel("COM Port:"))
        self.com_port_combo = QComboBox()
        self._populate_com_ports()
        panel_layout.addWidget(self.com_port_combo)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        panel_layout.addWidget(self.connect_button)
        panel_layout.addStretch()
        return panel_layout
    
    def _create_data_table(self):
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Parameter", "Raw (Dec)", "Raw (Hex)", "Scaled Value"])
        self.table.setRowCount(len(REGISTERS))
        for row, param_name in enumerate(REGISTERS.keys()):
            self.table.setItem(row, 0, QTableWidgetItem(param_name))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        return self.table

    def _populate_com_ports(self):
        self.com_port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.com_port_combo.addItem(port.device)

    def toggle_connection(self):
        if self.thread is None or not self.thread.isRunning():
            self.start_modbus_worker()
        else:
            self.stop_modbus_worker()

    def start_modbus_worker(self):
        port = self.com_port_combo.currentText()
        if not port:
            self.update_status("Error: No COM port selected.", is_error=True)
            return

        self.thread = QThread()
        self.worker = ModbusWorker(port=port, slave_id=1)
        self.worker.moveToThread(self.thread)

        self.worker.data_ready.connect(self.update_table)
        self.worker.status_updated.connect(self.update_status)
        self.worker.error_occurred.connect(lambda msg: self.update_status(msg, is_error=True))
        
        self.thread.started.connect(self.worker.run)
        
        # *** DÒNG ĐÃ SỬA ***
        # Dọn dẹp khi luồng kết thúc
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker.deleteLater) # Sửa ở đây

        self.thread.start()
        
        self.connect_button.setText("Disconnect")
        self.com_port_combo.setEnabled(False)

    def stop_modbus_worker(self):
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
        
        self.thread = None
        self.worker = None
        
        self.connect_button.setText("Connect")
        self.com_port_combo.setEnabled(True)
        self.update_status("Disconnected by user.")

    @Slot(dict)
    def update_table(self, data):
        for row, (param_name, details) in enumerate(REGISTERS.items()):
            raw_value = data.get(param_name)
            if raw_value == "Error" or raw_value is None:
                self.table.setItem(row, 1, QTableWidgetItem("Error"))
                self.table.setItem(row, 2, QTableWidgetItem("Error"))
                self.table.setItem(row, 3, QTableWidgetItem("Error"))
                continue

            if details['signed'] and raw_value > 32767:
                signed_value = raw_value - 65536
            else:
                signed_value = raw_value
            
            scaled_value = f"{signed_value * details['scale']:.2f} {details['unit']}"
            hex_value = f"0x{raw_value:04X}"
            self.table.setItem(row, 1, QTableWidgetItem(str(signed_value)))
            self.table.setItem(row, 2, QTableWidgetItem(hex_value))
            self.table.setItem(row, 3, QTableWidgetItem(scaled_value))

    @Slot(str)
    def update_status(self, message, is_error=False):
        self.status_label.setText(f"Status: {message}")
        if is_error:
            self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setStyleSheet("color: green;")

    def closeEvent(self, event):
        self.stop_modbus_worker()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    