import asyncio # used for threading
from bleak import BleakClient # used to communicate with lights
import atexit # handle closing down cleanly
from colour import Color # used to help work with colours
from PIL import ImageGrab # used to get a picture of the monitor
import fast_colorthief # used to get the dominant colour of the screenshot
import io # used to work with fast_colorthief to allow in-memory byte buffer 
import time # used to control loop speed
import signal # used to handle CTRL+C or other SIGINT termination calls 
import sys # used to exit after a SIGINT call
from typing import Optional, Any # used to mark some parameters as optional (not needed but useful for linting tools/robustness)

# The address we obtained from the Wireshark logs
device_address = "be:89:10:00:f2:ca" 
# The characteristic UUID we got from the get_characteristics method (yours may change so run the method to find out)
characteristic_uuid = "0000fff3-0000-1000-8000-00805f9b34fb" 


# Two constant values for ON and OFF which we found from the Bluetooth logs
ON_HEX = "7e0404f00001ff00ef"
OFF_HEX = "7e0404000000ff00ef"

# Function to create a BleakClient and connect it to the address of the light's Bluetooth reciever
async def init_client(address: str) -> BleakClient:
    client =  BleakClient(address)  
    print("Connecting")
    await client.connect()
    print(f"Connected to {address}")
    return client

# Function we can call to make sure we disconnect properly otherwise there could be caching and other issues if you disconnect and reconnect quickly
async def disconnect_client(client: Optional[BleakClient] = None) -> None:
    if client is not None :
        print("Disconnecting")
        if characteristic_uuid is not None:
            print(f"charUUID: {characteristic_uuid}")
            await toggle_off(client, characteristic_uuid)
        await client.disconnect()
        print("Client Disconnected")
    print("Exited")

# Get the characteristic UUID of the lights. You don't need to run this every time
async def get_characteristics(client: BleakClient) -> None:
    # Get all the services the device (lights in this case) 
    services = await client.get_services() 
    # Iterate the services. Each service will have characteristics
    for service in services: 
        # Iterate and subsequently print the characteristic UUID
        for characteristic in service.characteristics: 
            print(f"Characteristic: {characteristic.uuid}") 
    print("Please test these characteristics to identify the correct one")
    await disconnect_client(client)



async def send_colour_to_device(client: BleakClient, uuid: str, value: str) -> None:
    #write to the characteristic we found, in the format that was obtained from the Bluetooth logs
    await client.write_gatt_char(uuid, bytes.fromhex(f"7e070503{value}10ef"))

async def toggle_on(client: BleakClient, uuid: str) -> None:
    await client.write_gatt_char(uuid, bytes.fromhex(ON_HEX))
    print("Turned on")

async def toggle_off(client: BleakClient, uuid: str) -> None:
    await client.write_gatt_char(uuid, bytes.fromhex(OFF_HEX))
    print("Turned off")


# Handle closing any connectioin on shutdown
async def on_exit(client: BleakClient) -> None:
    if client is not None:
        await disconnect_client(client)
    print("Exited")



'''
Instead of taking the whole screensize into account, I'm going to take a 640x480 resolution from the middle. 
This should make it faster but you can toy around depending on what works for you. You may, for example, want
to take the outer edge colours instead so it the ambience blends to the outer edges and not the main screen colour 
'''
screen_width, screen_height = ImageGrab.grab().size #get the overall resolution size 
region_width = 640
region_height = 480
region_left = (screen_width - region_width) // 2
region_top = (screen_height - region_height) // 2
screen_region = (region_left, region_top, region_left + region_width, region_top + region_height)

screenshot_memory = io.BytesIO(b"")

# Method to get the dominant colour on screen. You can change this method to return whatever colour you like
def get_dominant_colour() -> str:
    # Take a screenshot of the region specified earlier
    screenshot = ImageGrab.grab(screen_region)
    '''
    The fast_colorthief library doesn't work directly with PIL images but we can use an in memory buffer (BytesIO) to store the picture
    This saves us writing then reading from the disk which is costly
    '''
    
    # Save screenshot region to in-memory bytes buffer (instead of to disk)
    # Seeking and truncating fo performance rather than using "with" and creating/closing BytesIO object
    screenshot_memory.seek(0)
    screenshot_memory.truncate(0)
    screenshot.save(screenshot_memory, "PNG") 
    # Get the dominant colour
    dominant_color = fast_colorthief.get_dominant_color(screenshot_memory, quality=1) 
    # Return the colour in the form of hex (without the # prefix as our Bluetooth device doesn't use it)
    return '{:02x}{:02x}{:02x}'.format(*dominant_color)


async def main(address: str) -> None:

    # Handle any SIGINT interruptions and exit gracefully (e.g. CTRL + C in prompt)
    def sigterm_handler(signum: int, frame: Any) -> None:
        loop = asyncio.get_event_loop()
        loop.create_task(on_exit(client))
        sys.exit(1)
    
    # register the listening of SIGINT 
    signal.signal(signal.SIGINT, sigterm_handler)

    try:
        #initiate the connection to the device
        client = await init_client(address)
        if client is None:
             raise TypeError(f"Device {address} not found. Please try again if you recently disconnected from the device")
        
        #if the characteristic UUID hasn't been set, run this method to see which are available for the device
        if not characteristic_uuid:
            await get_characteristics(client)
        
        
        # Sometimes the Bluetooth device requires a moment before further commnmands can be sent (trial and error, 3 seconds worked)
        time.sleep(3) 
        # Turn the lights on (this has no effect if the lights are already on for my lights)
        await toggle_on(client, characteristic_uuid)

        print("Ambient Monitor Starting")

        while True: 
            # send the dominant colour to the device
            await send_colour_to_device(client, characteristic_uuid, get_dominant_colour())
            # allow a small amount of time before update
            time.sleep(0.1)
        
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if client is not None:
            await on_exit(client)




def run_main(address):
    # kick off the main functon in an asyncioi event loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(address))
    loop.close()


if __name__ == "__main__": 
    run_main(device_address)
    


