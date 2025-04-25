import paho.mqtt.client as mqtt
import json
import mysql.connector
from datetime import datetime
import time
broker = "broker.emqx.io"
data_topic = "trail_me"

# MySQL connection
mysql_conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",
    database="practice"
)
mysql_cursor = mysql_conn.cursor()

# Insert data into MySQL
def insert_to_mysql(data):
    query = """
        INSERT INTO machine_alerts (machine_id, timestamp, temperature, vibration, rpm)
        VALUES (%s, %s, %s, %s, %s)
    """
    values = (
        data["machine_id"],
        datetime.fromisoformat(data["timestamp"]),
        data["temperature"],
        data["vibration"],
        data["rpm"]
    )
    mysql_cursor.execute(query, values)
    mysql_conn.commit()
    print("Data inserted into MySQL.")

# MQTT connection callback
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(data_topic)
    print("Subscriber connected and subscribed to data topic.")

# MQTT message callback
def on_message(client, userdata, msg):
    print(f"\n[Subscriber] Received message: {msg.payload.decode()}")
    json_str = msg.payload.decode()
    data = json.loads(json_str)      
    print("Received JSON data:", data)

    if data["temperature"] > 80 or data["vibration"] > 3.0:
        insert_to_mysql(data)

# Create MQTT client
client = mqtt.Client(clean_session=True)  # clean_session ensures no retained session data
client.on_connect = on_connect
client.on_message = on_message

# Connect to the MQTT broker
client.connect(broker, 1883, 60)

# Start MQTT loop in the background
client.loop_start()

# Keep the script running
try:
    print("Press Ctrl+C to exit")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nExiting gracefully...")
    client.disconnect()
