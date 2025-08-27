from CanTools.can_bus_manager import CanBusManager
from CanTools.car_status import CarStatus
from CanTools.setup_can import setup_can0
from CanTools.car_attributes_handler import CarAttributesHandler
import can
import time

CAN_CHANNEL='can0'
CAN_INTERFACE='socketcan'
CAN_BAUD=500000


class CanDemoManager():

    # setup the can0 on board
    setup_can0()

    def __init__(self, selectedDemo):
        self.selectedDemo = selectedDemo # Does nothing, to be used in the future to isolate CAN demo operations while other demos running
        self.can_bus_manager = CanBusManager(can_channel=CAN_CHANNEL, can_interface=CAN_INTERFACE, can_baud=CAN_BAUD)
        self.car_state = CarStatus.IDLE
        self.car_speed_handler = CarAttributesHandler()

    def update_car_speed_rpm(self, speed, rpm, throttle):
        self.can_bus_manager.update_car_speed_rpm(speed, rpm, throttle)

    def update_car_state(self, carState):
        self.car_state = carState

        if (carState == CarStatus.ACCELERATE):
            self.car_speed_handler.add_speed_callback(self.update_car_speed_rpm)
            self.car_speed_handler.start_acceleration()

        elif (carState == CarStatus.BRAKE):
            self.car_speed_handler.add_speed_callback(self.update_car_speed_rpm)
            self.car_speed_handler.start_braking()

        elif (carState == CarStatus.IDLE):
            self.car_speed_handler.stop_acceleration()
            self.car_speed_handler.stop_braking()

