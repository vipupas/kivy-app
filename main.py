from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock

from jnius import autoclass, PythonJavaClass, java_method, cast
from android.permissions import request_permissions, Permission

import threading

# Android BLE Java classes
BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
BluetoothLeScanner = autoclass('android.bluetooth.le.BluetoothLeScanner')
ScanCallback = autoclass('android.bluetooth.le.ScanCallback')
ScanResult = autoclass('android.bluetooth.le.ScanResult')
BluetoothGatt = autoclass('android.bluetooth.BluetoothGatt')
BluetoothGattCallback = autoclass('android.bluetooth.BluetoothGattCallback')
BluetoothGattCharacteristic = autoclass('android.bluetooth.BluetoothGattCharacteristic')
UUID = autoclass('java.util.UUID')
PythonActivity = autoclass('org.kivy.android.PythonActivity')

SERVICE_UUID = UUID.fromString("0000FFE0-0000-1000-8000-00805F9B34FB")
CHAR_UUID = UUID.fromString("0000FFE1-0000-1000-8000-00805F9B34FB")

class GattCallback(PythonJavaClass):
    __javainterfaces__ = ['android.bluetooth.BluetoothGattCallback']
    __javacontext__ = 'app'

    def __init__(self, app):
        super().__init__()
        self.app = app

    @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
    def onConnectionStateChange(self, gatt, status, new_state):
        if new_state == BluetoothGatt.STATE_CONNECTED:
            self.app.gatt = gatt
            gatt.discoverServices()
            Clock.schedule_once(lambda dt: self.app.on_connected(), 0)
        else:
            Clock.schedule_once(lambda dt: self.app.on_disconnected(), 0)

    @java_method('(Landroid/bluetooth/BluetoothGatt;I)Landroid/bluetooth/BluetoothGattCharacteristic;')
    def onServicesDiscovered(self, gatt, status):
        Clock.schedule_once(lambda dt: self.app.on_services_discovered(), 0)

class RelayControlApp(App):
    def build(self):
        # ask permissions
        request_permissions([
            Permission.BLUETOOTH,
            Permission.BLUETOOTH_CONNECT,
            Permission.BLUETOOTH_SCAN,
            Permission.ACCESS_FINE_LOCATION
        ], lambda perms, results: None)

        self.adapter = BluetoothAdapter.getDefaultAdapter()
        self.scanner = self.adapter.getBluetoothLeScanner()
        self.gatt = None
        self.device_address = None

        # (UI building code same as before)...
        # use self.scan_btn, self.address_input, self.status_label, self.connect_btn etc.

        # simplified for brevity — replicate your original UI structure
        layout = BoxLayout(orientation='vertical')
        self.status_label = Label(text="Not connected")
        layout.add_widget(self.status_label)
        self.address_input = TextInput(hint_text="Device MAC", multiline=False)
        layout.add_widget(self.address_input)
        self.scan_btn = Button(text="Scan devices")
        self.scan_btn.bind(on_press=self.scan_devices)
        layout.add_widget(self.scan_btn)
        self.connect_btn = Button(text="Connect")
        self.connect_btn.bind(on_press=self.connect_device)
        layout.add_widget(self.connect_btn)
        # plus relay controls...
        self.set_controls_enabled(False)
        return layout

    def scan_devices(self, instance):
        self.scan_btn.disabled = True
        self.status_label.text = "Scanning..."
        # setup callback
        class MyScanCallback(ScanCallback):
            def __init__(self, app):
                super().__init__()
                self.app = app
            @java_method('(Landroid/bluetooth/le/ScanResult;)V')
            def onScanResult(self, callbackType, result):
                dev = result.getDevice()
                name = dev.getName() or ""
                addr = dev.getAddress()
                if "ESP32" in name.upper():
                    Clock.schedule_once(lambda dt: self.app._on_device_found(f"{name} - {addr}"), 0)

        self.scan_cb = MyScanCallback(self)
        self.scanner.startScan(self.scan_cb)
        Clock.schedule_once(lambda dt: self.stop_scan(), 10)  # stop after 10 sec

    def stop_scan(self):
        self.scanner.stopScan(self.scan_cb)
        self.scan_btn.disabled = False
        self.status_label.text = "Scan complete"

    def _on_device_found(self, device_info):
        # show popup list — similar to before
        self.address_input.text = device_info.split(" - ")[-1]

    def connect_device(self, instance):
        if self.gatt:
            self.gatt.disconnect()
            self.status_label.text = "Disconnecting..."
            return
        addr = self.address_input.text.strip()
        if not addr:
            self.show_error("Enter MAC address or scan")
            return
        dev = self.adapter.getRemoteDevice(addr)
        self.status_label.text = "Connecting..."
        cb = GattCallback(self)
        dev.connectGatt(PythonActivity.mActivity, False, cb)

    def on_connected(self):
        self.status_label.text = "Connected"
        self.connect_btn.text = "Disconnect"
        self.set_controls_enabled(True)

    def on_disconnected(self):
        self.status_label.text = "Disconnected"
        self.connect_btn.text = "Connect"
        self.set_controls_enabled(False)
        self.gatt = None

    def on_services_discovered(self):
        # optional validation of service/characteristic
        pass

    def send_command(self, cmd):
        if not self.gatt:
            self.show_error("Not connected")
            return
        svc = self.gatt.getService(SERVICE_UUID)
        char = svc.getCharacteristic(CHAR_UUID)
        b = cmd.encode('utf-8')
        char.setValue(b)
        self.gatt.writeCharacteristic(char)
        self.show_message(f"Sent: {cmd}")

    # your methods set_controls_enabled, show_error, show_message unchanged

if __name__ == '__main__':
    RelayControlApp().run()
