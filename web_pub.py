import paho.mqtt.client as mqtt
import random
import time
from datetime import datetime
import json
from pymongo import MongoClient
from PIL import Image, ImageDraw, ImageFont
import os
import websockets
import asyncio
import base64

# MQTT & MongoDB setup
broker = "broker.emqx.io"  # Make sure this is the correct broker address
data_topic = "trail_me"

# Image output folder
image_folder = os.path.join(os.getcwd(), 'static', 'images')
os.makedirs(image_folder, exist_ok=True)

# MongoDB connection
mongo_client = MongoClient("mongodb://localhost:27017/")
mongo_db = mongo_client["demo"]
mongo_collection = mongo_db["machine_metrics"]

# WebSocket setup
WS_SERVER = "ws://localhost:8765"

# MQTT connection callback
def on_connect(client, userdata, flags, rc):
    print("Publisher connected and started.")

# Generate sample machine data
def generate_single_machine_data():
    machine_ids = [f"M{100 + i}" for i in range(11)]
    data = {
        "machine_id": random.choice(machine_ids),
        "timestamp": datetime.now().isoformat(),
        "temperature": round(random.uniform(60.0, 100.0), 1),
        "vibration": round(random.uniform(0.5, 5.0), 2),
        "rpm": random.randint(1000, 2000)
    }
    return data

# Create snapshot image with raw text data
def create_image(data):
    img = Image.new('RGB', (300, 200), color='white')
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except IOError:
        font = ImageFont.load_default()

    lines = [
        f"Machine: {data['machine_id']}",
        f"Temp: {data['temperature']}°C",
        f"RPM: {data['rpm']}",
        f"Vibration: {data['vibration']}",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ]

    y = 20
    for line in lines:
        draw.text((10, y), line, fill="black", font=font)
        y += 30

    img_path = os.path.join(image_folder, f"{data['machine_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
    img.save(img_path)
    return img_path

# Convert image to base64 string for WebSocket transmission
def convert_image_to_base64(img_path):
    with open(img_path, "rb") as img_file:
        img_base64 = base64.b64encode(img_file.read()).decode("utf-8")
    return img_base64

# Function to send the image to WebSocket server
async def send_image_to_ws(image_base64):
    async with websockets.connect(WS_SERVER) as websocket:
        # Adding 'image:' prefix to the base64 data
        await websocket.send("image:" + image_base64)

# Set up and start MQTT client
client = mqtt.Client()
client.on_connect = on_connect
client.connect(broker, 1883)
client.loop_start()

# Asynchronous function to send images continuously
async def send_images_continuously():
    while True:
        data = generate_single_machine_data()

        # Publish data to MQTT
        try:
            client.publish(data_topic, json.dumps(data))
            print()
        except Exception as e:
            print(f"Error publishing data: {e}")

        # Insert data into MongoDB
        try:
            mongo_collection.insert_one(data)
        except Exception as e:
            print(f"Error inserting data into MongoDB: {e}")

        # Create image and send it to WebSocket server
        try:
            img_path = create_image(data)
            img_base64 = convert_image_to_base64(img_path)
            await send_image_to_ws(img_base64)  # Send the image via WebSocket

            if os.path.exists(img_path):
                os.remove(img_path)
                # print(f"Deleted temporary image: {img_path}")
        except Exception as e:
            print(f"Error creating or sending image: {e}")

        print(f"Published: {data}")
        await asyncio.sleep(10)

# Main function
def main():
    asyncio.run(send_images_continuously())

if __name__ == "__main__":
    main()
