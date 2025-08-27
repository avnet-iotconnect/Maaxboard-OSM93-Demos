import serial
import os
import threading
from elm import Elm
import can
from can import Message
from can import BusState
import time
import subprocess
import re
import queue


class CarSimulator():

    def __init__(self):
        self.process = None
        self.elm_port = None
        self._start()

    def _start(self):
        # Start the ELM simulator
        self.process = subprocess.Popen(['python3', '-m', 'elm', '-s', 'car', '-e', '-a', '230400'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True)
        # self.process = subprocess.Popen(['python3', '-m', 'elm', '-a', '230400'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, text=True)

        pattern = re.compile(r'pseudo-tty port "(/dev/pts/\d+)"')

        # Wait for simulator to start
        time.sleep(2)
        # Scan output text and search for pattern
        while True:
            line = self.process.stdout.readline()
            if not line:
                break
            # Pattern found, set port as found port (i.e /dev/pts/*)
            match = pattern.search(line)
            if match:
                self.elm_port = match.group(1)
                break

    def get_elm_port(self):
        try:
            if self.elm_port:
                print("Port is: ", self.elm_port)
                return self.elm_port

        except:
            print("Error! No port assigned from simulator. Restart Application.")
            self._stop()

    def _stop(self):
        # Stop the emulator
        if self.process:
            self.process.terminate()

class CanBusManager():
    """
    Class to manage CAN bus communication. Create a bus, send, and receive messages.
    """
    def __init__(self, can_channel='can0', can_interface='socketcan', can_baud=500000):
        self.serial_manager = None
        self.can_channel = can_channel
        self.can_interface = can_interface
        self.can_baud = can_baud
        self.message_queue = queue.Queue()
        self.tx_arb_id = 0x7E8 # ECU arbitration ID
        self.rx_arb_id = 0x7DF # OBDII scanner arbitration ID
        self.bus = can.interface.Bus(channel=self.can_channel, bustype=self.can_interface, bitrate=self.can_baud) # create can bus
        self.notifier = can.Notifier(self.bus, [self.enqueue_message]) # setup a notifier object to handle incoming messages
        self.worker_thread = threading.Thread(target=self.process_can_message)
        self.worker_thread.start()


    def set_serial_manager(self, serial_manager):
        self.serial_manager = serial_manager

    def enqueue_message(self, msg):
        if msg.arbitration_id == self.rx_arb_id:
            if msg.data == bytearray(b'\x02\x01\x00\x00\x00\x00\x00\x00'):
                # initial pairing message
                # print("Received 0100 PID support request.")
                PID_0100_response_1 = bytearray(b'\x06\x41\x00\x98\x3A\x80\x13')
                PID_0100_response_2 = bytearray(b'\x06\x41\x00\xBE\x3F\xA8\x13')
                message1 = can.Message(arbitration_id=self.tx_arb_id, data=PID_0100_response_1, is_extended_id=False)
                message2 = can.Message(arbitration_id=self.tx_arb_id, data=PID_0100_response_2, is_extended_id=False)
                self.bus.send(message1, 1)
                self.bus.send(message2, 1)
            else:
                self.message_queue.put(msg)

    def process_can_message(self):
        while True:
            msg = self.message_queue.get()
            if msg:
                # start = time.time()
                data = self.convert_can_to_bytes(msg)
                # print("Can message processed: ", data)
                self.serial_manager.send_data(data)
                # end = time.time()
                # print("Time: ", end-start)

    def convert_can_to_bytes(self, can_msg):
        """Convert CAN data to Bytes data"""
        can_data = ""
        for data in can_msg.data[1:can_msg.data[0]+1]:
            can_data += '%02X' % data

        # can_data += '\r'
        byte_data = can_data.encode()
        # print("Write Serial: ", byte_data)
        return byte_data

    def format_ecu_response_to_can(self, data_list):

        for data in data_list:
            # separate individual hex values in response
            hex_values = data.split()
            # count number of bytes for CAN message formatting
            msg_length = len(hex_values)

            # create CAN data frame, initial byte as length
            byte_array = bytearray([msg_length])

            # add data values into byte array after msg length
            byte_array.extend(int(value, 16) for value in hex_values)

            try:
                # print("Sending message: ", can.Message(arbitration_id=self.tx_arb_id, data=byte_array, is_extended_id=False))
                self.bus.send(can.Message(arbitration_id=self.tx_arb_id, data=byte_array, is_extended_id=False), 1)

            except:
                print("Error sending")


class SerialManager():
    """Serial port handler to interface between CAN and ELM327 ECU emulator."""

    def __init__(self, elm_port, baud):
        self.elm_port = elm_port
        self.ser = serial.Serial(port=elm_port, baudrate=baud)
        self.can_manager = None
        self.data_queue = queue.Queue()
        self.receiving_thread = threading.Thread(target=self.receive_data)
        self.processing_thread = threading.Thread(target=self.process_serial_data)
        self.receiving_thread.start()
        self.processing_thread.start()

    def set_can_manager(self, can_manager):
        self.can_manager = can_manager

    def send_data(self, data):
        self.ser.write(data + b'\r')
        self.ser.flush()
        # print("Sent Serial Data: ", data)

    def receive_data(self):
        while True:
            if self.ser.in_waiting > 5:
                # print("Serial data waiting: ", self.ser.in_waiting)
                data = self.ser.read_all()
                # print("Received serial data: ", data)
                self.data_queue.put(data)

    def process_serial_data(self):
        while True:
            data = self.data_queue.get()
            if data:
                response = self.parse_ecu_byte_response(data)
                self.can_manager.format_ecu_response_to_can(response)

    def parse_ecu_byte_response(self, data_bytes):
        match_data = list()

        # Convert bytes to a normal string
        data = data_bytes.decode()
        # print("Decoded Data: ", data)

        # Regex pattern to match ECU byte responses only
        pattern = re.compile(r'(?:\d+:)?\s*([0-9A-F]{2}(?:\s+[0-9A-F]{2})+)', re.IGNORECASE)

        # split messages by '\r', appending matched data groups to match_data
        messages = data.split('\r')
        for msg in messages:
            if msg.strip():
                match = pattern.search(msg)
                if match:
                    # print("Regex found: ", match.group(1))
                    match_data.append(match.group(1))

        # print("Matched data: ", match_data)
        return match_data

    def close(self):
        self.ser.close()
        self.receiving_thread.join()
        self.processing_thread.join()
        print("Serial port closed and threads terminated.")


def start_can_applicaiton():

    print("Setting up CAN bus")
    os.system("ifconfig can0 down")
    time.sleep(1)
    os.system("ip link set can0 type can bitrate 500000")
    time.sleep(1)
    os.system("ifconfig can0 up")
    time.sleep(1)
    print("CAN interface setup. Starting application...")
    # car_simulator = Elm(batch_mode=True)
    car_simulator = CarSimulator()
    serial_manager = SerialManager(elm_port=car_simulator.get_elm_port(), baud=230400)
    # serial_manager = SerialManager(elm_port=car_simulator.get_pty(), baud=230400)
    can_application = CanBusManager()
    serial_manager.set_can_manager(can_application)
    can_application.set_serial_manager(serial_manager)
    # car_simulator.run()


if __name__ == "__main__":

    # Setup Can0 with 250k baud
    print("Setting up CAN bus")
    os.system("ifconfig can0 down")
    time.sleep(1)
    os.system("ip link set can0 type can bitrate 500000")
    time.sleep(1)
    os.system("ifconfig can0 up")
    time.sleep(1)
    print("CAN interface setup. Starting application...")

    try:
        print("Running...")
        while True:
            pass


    except Exception as e:
        print("Error: ", e)


