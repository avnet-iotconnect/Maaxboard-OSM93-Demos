import threading
import time
import datetime

class CarAttributesHandler:
    """
    Multithreaded handler to manager speed, and rpm parameters for the car.
    Class is a Singleton to aid in being used in localWindow.

    Two states are monitored:
    - acceleratiing
    - braking

    During car idle, values are kept static.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CarAttributesHandler, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.speed = 0
        self.rpm = 1400
        self.throttle = 0
        self.accelerating = False
        self.braking = False
        self.callbacks = []

    def add_speed_callback(self, callback):
        self.callbacks.append(callback)

    def notify_speed_change(self):
        for callback in self.callbacks:
            callback(self.speed, self.rpm, self.throttle)

    def calculate_rpm(self):
        '''
        Simulates an RPM value based on speed with
        added "shifting" effect when speed passes certain thresholds.

        '''
        if self.accelerating:
            if 0 <= self.speed <= 20:
                self.rpm = 1400 + (self.speed / 20) * (3500 - 1400)
            elif 20 < self.speed <= 40:
                self.rpm = 2000 + ((self.speed - 20) / 20) * (4000 - 2000)
            elif 40 < self.speed <= 60:
                self.rpm = 2400 + ((self.speed - 40) / 20) * (4500 - 2400)
            elif self.speed > 60:
                self.rpm = 2800 + ((self.speed - 60) / 40) * (5400 - 2800)
        elif self.braking:
            if 0 < self.speed <= 20:
                self.rpm = 3500 - ((20 - self.speed) / 20) * (3500 - 1400)
            elif 20 < self.speed <= 40:
                self.rpm = 4000 - ((40 - self.speed) / 20) * (4000 - 2000)
            elif 40 < self.speed <= 60:
                self.rpm = 4500 - ((60 - self.speed) / 20) * (4500 - 2400)
            elif self.speed > 60:
                self.rpm = 5400 - ((100 - self.speed) / 40) * (5400 - 2800)

    def accelerate(self):
        '''
        Continually increase speed and throttle position during acceleration.
        '''
        self.accelerating = True
        while self.accelerating and self.speed < 100:
            self.speed += 1
            self.throttle += 1
            self.calculate_rpm()
            self.notify_speed_change()
            time.sleep(0.05)

    def brake(self):
        '''
        Continually decrease speed and throttle position during acceleration.
        '''
        self.braking = True
        while self.braking and self.speed > 0:
            self.speed -= 1
            self.throttle -= 1
            self.calculate_rpm()
            self.notify_speed_change()
            time.sleep(0.05)

    def start_acceleration(self):
        threading.Thread(target=self.accelerate).start()

    def start_braking(self):
        threading.Thread(target=self.brake).start()

    def stop_acceleration(self):
        self.accelerating = False

    def stop_braking(self):
        self.braking = False

