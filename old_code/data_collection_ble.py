import asyncio
import sys
import csv
from datetime import datetime
from bleak import BleakScanner, BleakClient
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox, QInputDialog, QComboBox, QDateEdit
from PyQt5.QtCore import QDate, QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QIcon



# UUIDs and other data
UART_SERVICE_UUID_2 = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID_2 = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UART_SERVICE_UUID_3 = "7E400001-A5B3-C393-D0E9-F50E24DCCA9E"
UART_RX_CHAR_UUID_3 = "7E400003-A5B3-C393-D0E9-F50E24DCCA9E"
UART_SERVICE_UUID_1 = "8E400004-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID_1 = "8E400006-B5A3-F393-E0A9-E50E24DCCA9E"

buffers = {1: "", 2: "", 3: ""}
start_times = {1: None, 2: None, 3: None}
sensor_data = {1: {"timestamp": None, "values": [None] * 6}, 2: {"timestamp": None, "values": [None] * 6}, 3: {"timestamp": None, "values": [None] * 6}}
csv_filename = "./data/sensor_data.csv"
STOP_FLAG = False

async def notification_handler(sender, data, sensor_id):
    global buffers, start_times, STOP_FLAG
    if STOP_FLAG:
        return
    
    if start_times[sensor_id] is None:
        start_times[sensor_id] = datetime.now()

    buffers[sensor_id] += data.decode('utf-8')
    buffer = buffers[sensor_id]

    while '\n' in buffer:
        line, buffer = buffer.split('\n', 1)
        buffers[sensor_id] = buffer
        if line.strip() == "":
            continue

        elapsed_time = (datetime.now() - start_times[sensor_id]).total_seconds() * 1000
        imu_values = list(map(float, line.split(',')))

        sensor_data[sensor_id]["timestamp"] = elapsed_time
        sensor_data[sensor_id]["values"] = imu_values

        if all(sensor_data[i]["values"][0] is not None for i in range(1, 4)):
            timestamp = round(sensor_data[1]["timestamp"], 3)
            with open(csv_filename, 'a', newline='') as file:
                writer = csv.writer(file)
                row = [timestamp] + sensor_data[1]["values"] + sensor_data[2]["values"] + sensor_data[3]["values"]
                writer.writerow(row)
            for i in range(1, 4):
                sensor_data[i]["timestamp"] = None
                sensor_data[i]["values"] = [None] * 6

async def connect_to_sensor(device, sensor_id, char_uuid):
    async with BleakClient(device) as client:
        if client.is_connected:
            await client.start_notify(char_uuid, lambda sender, data: asyncio.create_task(notification_handler(sender, data, sensor_id)))
            while not STOP_FLAG:
                await asyncio.sleep(0.1)
        else:
            print(f"Failed to connect to {device.name}")

async def scan_and_connect():
    devices = await BleakScanner.discover()
    target_names = ["Sense Right", "Sense Left", "Sense MPU"]
    devices = [d for d in devices if d.name in target_names]
    tasks = []
    for device in devices:
        if device.name == "Sense Right":
            tasks.append(connect_to_sensor(device, 1, UART_RX_CHAR_UUID_1))
        elif device.name == "Sense Left":
            tasks.append(connect_to_sensor(device, 2, UART_RX_CHAR_UUID_2))
        elif device.name == "Sense MPU":
            tasks.append(connect_to_sensor(device, 3, UART_RX_CHAR_UUID_3))
    await asyncio.gather(*tasks)

class AsyncRunner(QThread):
    updateStatus = pyqtSignal(str)

    def run(self):
        global STOP_FLAG
        STOP_FLAG = False
        self.updateStatus.emit("Connecting to sensors...")
        asyncio.run(scan_and_connect())

    def stop(self):
        global STOP_FLAG
        STOP_FLAG = True

class ExerciseTracker(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.timer = QTimer(self)
        self.elapsed_time = 0
        self.timer.timeout.connect(self.update_timer)
        self.async_runner = AsyncRunner()
        self.async_runner.updateStatus.connect(self.setStatus)

    def initUI(self):
        self.layout = QVBoxLayout()

        # School Name
        self.school_name_label = QLabel("School Name:")
        self.school_name_input = QLineEdit()
        self.layout.addWidget(self.school_name_label)
        self.layout.addWidget(self.school_name_input)

        # Date Selector
        self.date_label = QLabel('Date:')
        self.date_input = QDateEdit(self)
        self.date_input.setCalendarPopup(True)
        self.date_input.setDisplayFormat('dd/MM/yyyy')
        self.date_input.setDate(QDate.currentDate())
        self.layout.addWidget(self.date_label)
        self.layout.addWidget(self.date_input)

        # Grade
        self.grade_label = QLabel("Grade:")
        self.grade_input = QLineEdit()
        self.layout.addWidget(self.grade_label)
        self.layout.addWidget(self.grade_input)

        # Exercise Name
        self.exercise_name_label = QLabel("Exercise Name:")
        self.exercise_name_dropdown = QComboBox()
        self.exercise_name_dropdown.addItems(["Push-up", "Squat", "Jumping Jack", "Burpee"])
        self.layout.addWidget(self.exercise_name_label)
        self.layout.addWidget(self.exercise_name_dropdown)

        # Connect / Track Status
        self.status_label = QLabel("")
        self.layout.addWidget(self.status_label)

        # Timer
        self.timer_label = QLabel("Elapsed Time: 0s")
        self.layout.addWidget(self.timer_label)

        # Buttons
        self.start_button = QPushButton('Start Exercise', self)
        self.start_button.clicked.connect(self.startExercise)
        self.layout.addWidget(self.start_button)

        self.stop_button = QPushButton('Stop Exercise', self)
        self.stop_button.clicked.connect(self.stopExercise)
        self.stop_button.setEnabled(False)
        self.layout.addWidget(self.stop_button)

        self.setLayout(self.layout)

    def setStatus(self, status):
        self.status_label.setText(status)

    def startExercise(self):
        global csv_filename
        school_name = self.school_name_input.text()
        date_selected = self.date_input.date().toString("yyyyMMdd")
        grade = self.grade_input.text()
        exercise_name = self.exercise_name_dropdown.currentText()
        csv_filename = f"./{school_name}_{date_selected}_{grade}_{exercise_name}.csv"
        
        with open(csv_filename, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['timestamp', 'right_hand_Accel_X', 'right_hand_Accel_Y', 'right_hand_Accel_Z', 'right_hand_Gyro_X', 'right_hand_Gyro_Y', 'right_hand_Gyro_Z', 'left_hand_Accel_X', 'left_hand_Accel_Y', 'left_hand_Accel_Z', 'left_hand_Gyro_X', 'left_hand_Gyro_Y', 'left_hand_Gyro_Z', 'right_leg_Accel_X', 'right_leg_Accel_Y', 'right_leg_Accel_Z', 'right_leg_Gyro_X', 'right_leg_Gyro_Y', 'right_leg_Gyro_Z'])
        
        self.timer.start(1000)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.async_runner.start()

    def update_timer(self):
        self.elapsed_time += 1
        self.timer_label.setText(f"Elapsed Time: {self.elapsed_time}s")

    def stopExercise(self):
        self.async_runner.stop()
        self.async_runner.wait()
        
        reply = QMessageBox.question(self, 'Message', "Do you want to keep the data?", QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            label, ok = QInputDialog.getItem(self, 'Input Dialog', 'Enter a label for the data:', ["Label1", "Label2", "Label3"], 0, False)
            if ok:
                self.status_label.setText(f"Data labeled as {label} and saved to {csv_filename}")
            else:
                self.status_label.setText("Label input canceled")
        else:
            self.status_label.setText("Data discarded")

        self.elapsed_time = 0
        self.timer.stop()
        self.timer_label.setText("Elapsed Time: 0s")
        self.school_name_input.clear()
        self.grade_input.clear()
        self.exercise_name_dropdown.setCurrentIndex(0)
        self.date_input.setDate(QDate.currentDate())
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

app = QApplication(sys.argv)
ex = ExerciseTracker()
ex.show()
sys.exit(app.exec_())