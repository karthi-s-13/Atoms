import serial.tools.list_ports

def list_com_ports():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No COM ports found. Is your Arduino plugged in?")
        return
    
    print("Available COM ports:")
    for port in ports:
        print(f"- {port.device}: {port.description}")

if __name__ == "__main__":
    list_com_ports()
