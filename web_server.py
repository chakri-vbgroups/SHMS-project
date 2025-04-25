import asyncio
import websockets
import base64
from PIL import Image
from io import BytesIO

async def websocket_handler(websocket):
    print(f"New connection from {8765}")
    try:
        async for message in websocket:
            # print("Image sending to dash...")
            if message.startswith("image:"):  # Check for image data
                image_data = message[6:]  # Assuming base64-encoded image data
                # print(f"Image data received: {image_data[:20]}...")  # Only show a snippet for clarity
                print("Image sent \n")
                # Decode the image data
                # image_bytes = base64.b64decode(image_data)
                # image = Image.open(BytesIO(image_bytes))

                # Save or process the image (you can save it or send it to Dash here)
                # image.save("received_image.jpg")
                # print("Image saved.")
                # You can send the image to Dash here (or any other part of your app)
                # await websocket.send("Image received and saved.")
            else:
                # Handle non-image messages
                print("image Sent to dash\n")
                await websocket.send(f"Echo: {message}")
    except Exception as e:
        print(f"Connection error: {e}")
        await websocket.send("Error: Something went wrong!")

# WebSocket server setup
async def start_server():
    server = await websockets.serve(websocket_handler, "localhost", 8765)
    print("WebSocket server running on ws://localhost:8765")
    await server.wait_closed()

# Start the WebSocket server
asyncio.run(start_server())
