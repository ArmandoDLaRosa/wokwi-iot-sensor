import network
import urequests
import machine
import utime
import ujson
from machine import I2C, Pin
import dht
from i2c_lcd import I2cLcd

CONFIG = {
    "WIFI_SSID": "Wokwi-GUEST",
    "WIFI_PASSWORD": "",
    "SENSOR_STATUS_ENDPOINT": "https://apex.oracle.com/pls/apex/leds/sensor_status/status?id=1",
    "DATA_INSERT_ENDPOINT": "https://apex.oracle.com/pls/apex/leds/sensor_status/data",
    "GEMINI_API_KEY": "", 
    "GEMINI_ENDPOINT": "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
    "I2C_ADDR": 0x27,
    "ROWS": 2,
    "COLS": 16,
    "IDEAL_HUMIDITY_LOW": 60.0,
    "IDEAL_HUMIDITY_HIGH": 75.0,
    "SENSOR_PIN": 4,
    "I2C_SCL": 22,
    "I2C_SDA": 21
}

i2c = I2C(scl=Pin(CONFIG["I2C_SCL"]), sda=Pin(CONFIG["I2C_SDA"]), freq=100000)
lcd = I2cLcd(i2c, CONFIG["I2C_ADDR"], CONFIG["ROWS"], CONFIG["COLS"])
dht_sensor = dht.DHT22(Pin(CONFIG["SENSOR_PIN"]))
humidity_readings = []

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(ssid, password)
        for _ in range(10):
            if wlan.isconnected():
                print("WiFi Connected!")
                print("IP Address:", wlan.ifconfig()[0])
                return True
            utime.sleep(1)
        print("WiFi Connect Failed")
        return False
    else:
        print("Already connected.")
        return True

def request_endpoint(url, params=None, method='get'):
    try:
        if method == 'get':
            response = urequests.get(url)
        elif method == 'post':
            headers = {'Content-Type': 'application/json'}
            response = urequests.post(url, data=ujson.dumps(params), headers=headers)
            return None
            
        data = response.json()
        response.close()
        return data
    except Exception as e:
        log(f"Failed to reach endpoint {url}: {e}", level='error')
        return None

def check_sensor_status():
    data = request_endpoint(CONFIG["SENSOR_STATUS_ENDPOINT"]) or {}
    return data.get("items", {})[0].get("status", 'OFF') == 'ON'

def calculate_humidity_status(humidity):
    if humidity < CONFIG["IDEAL_HUMIDITY_LOW"]:
        return "Too Dry!"
    elif humidity > CONFIG["IDEAL_HUMIDITY_HIGH"]:
        return "Too Humid!"
    return "Optimal"

def store_humidity_data(humidity, avg_humidity):
    year, month, mday, hour, minute, second, weekday, yearday = utime.localtime()
    current_time = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(year, month, mday, hour, minute, second)
    
    params = {
        "humidity": humidity,
        "datetime": current_time,
        "avg_humidity": avg_humidity
    }
    request_endpoint(CONFIG["DATA_INSERT_ENDPOINT"], params=params, method='post')

def calculate_average_humidity():
    return sum(humidity_readings) / len(humidity_readings) if humidity_readings else 0

def update_lcd(message, delay=2):
    lcd.clear()
    lcd.putstr(message)
    utime.sleep(delay)

def log(message, level='info'):
    print(f"[{level.upper()}] {message}")

def request_gemini_response(prompt):
    url = f"{CONFIG['GEMINI_ENDPOINT']}?key={CONFIG['GEMINI_API_KEY']}"
    headers = {
        'Content-Type': 'application/json'
    }
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        response = urequests.post(url, headers=headers, data=ujson.dumps(payload))
        result = response.json()
        response.close()
        return result
    except Exception as e:
        log(f"Failed to reach Gemini endpoint: {e}", level='error')
        return None

def generate_vegetable_suggestions(humidity, humidity_status):
    prompt = f"The current humidity level is {humidity}%, status: {humidity_status}. What brief advice would you provide for vegetable processing under these conditions?"
    response = request_gemini_response(prompt)
    if response:
        generated_text = response.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        advice_text = generated_text[0].get("text", "No advice available.")
        advice_text = ' '.join(advice_text.split()[:20]) + '...'
        update_lcd(f"{humidity_status}\n{advice_text}", delay=3)
    else:
        update_lcd("Failed to get advice")

def process_humidity():
    try:
        dht_sensor.measure()
        humidity = dht_sensor.humidity()
        if humidity is not None:
            humidity_readings.append(humidity)
            avg_humidity = calculate_average_humidity()
            humidity_status = calculate_humidity_status(humidity)
            update_lcd(f"Humidity: {humidity:.2f}%\n{humidity_status}", delay=3)
            generate_vegetable_suggestions(humidity, humidity_status)
            store_humidity_data(humidity, avg_humidity)
    except Exception as e:
        log(f"Sensor error: {e}", level='error')
        update_lcd("Sensor error")

def main():
    update_lcd("Veg Sanitization\nInitializing...")
    if not connect_wifi(CONFIG["WIFI_SSID"], CONFIG["WIFI_PASSWORD"]):
        update_lcd("WiFi Fail!\nCheck config")
        return

    while True:
        if check_sensor_status():
            process_humidity()
        else:
            update_lcd("Sensor is OFF")
        update_lcd("Sensor working...")
        utime.sleep(2)

if __name__ == "__main__":
    main()
