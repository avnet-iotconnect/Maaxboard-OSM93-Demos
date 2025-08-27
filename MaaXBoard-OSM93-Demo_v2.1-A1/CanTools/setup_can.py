"""
A module for configuring the CAN0 network interface on MaaXBoard systems.


Functions:
    setup_can0(): Configures and activates the CAN0 interface.
    shutdown_can0(): Deactivates the CAN0 interface and cleans up resources.

Attributes:
    DEFAULT_BITRATE (int): The default bitrate for the CAN0 interface.

"""
import os
DEFAULT_BITRATE = 500000  # in bits per second

def setup_can0():
    """
    Sets up the CAN0 interface with the default bitrate.
    """

    os.system('sudo ip link set can0 down')
    os.system(f'sudo ip link set can0 type can bitrate {DEFAULT_BITRATE}')
    os.system('sudo ip link set can0 up')
    print("CAN0 interface has been configured and activated.")

def shutdown_can0():
    """
    Shuts down the CAN0 interface.
    """

    os.system('sudo ip link set can0 down')
    print("CAN0 interface has been deactivated.")
