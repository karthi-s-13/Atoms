import serial
import time

class SignalController:
    def __init__(self, port=None, baudrate=9600, mock=False):
        if port is None:
            port = os.getenv("SERIAL_PORT", "COM5")
        self.mock = mock
        self.last_command = "NONE"
        self._connected = False
        
        if self.mock:
            self._connected = True
            print(f"[HW] Running in MOCK mode (no Serial initialization)")
            return

        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
            time.sleep(2) # Wait for Arduino reset
            self._connected = True
            print(f"[HW] Connected to Arduino on {port}")
        except Exception as e:
            self._connected = False
            print(f"[HW] Failed to connect on {port}: {e}")

    def update(self, active_direction, phase_state, pedestrian_active=False):
        if not self._connected:
            return
        
        # Determine the command
        if pedestrian_active or active_direction is None:
            command = "ALL_RED"
        elif phase_state == "GREEN":
            command = f"{active_direction}_GREEN"
        elif phase_state == "YELLOW":
            command = f"{active_direction}_YELLOW"
        else:
            command = "ALL_RED"
            
        if command == self.last_command:
            return

        self.last_command = command
        print(f"[HW] Sending command: {command}")
        
        if not self.mock:
            try:
                self.ser.write(f"{command}\n".encode('utf-8'))
            except Exception as e:
                print(f"[HW] Write failed: {e}")
                self._connected = False # Mark as disconnected to avoid repeated errors

    def close(self):
        if not self.mock and hasattr(self, 'ser'):
            self.ser.close()