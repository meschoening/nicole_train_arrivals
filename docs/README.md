# nicole_train_arrivals
Python program to show train arrivals for any line, station, and direction combo for the WMATA metro system. Made with &lt;3 for Nicole.

# Program Outline & Fun Facts
- main_display.py - contains code for the interface.
- MetroAPI.py - interfaces with the official WMATA API to download data.
- data_handler.py - caches API data while the program is open. Helps reduce lag when switching windows and changing settings.
- services/config_store.py - saves selected settings in a file for retrieval every time the app opens.
- config.json - the file that stores your selected settings to be loaded when the app restarts.
- web_settings_server.py - routes the locally hosted web-based config pages to the right files.
- wifi_setup.py - enables connecting to a new WiFi network if connection fails on startup!
- templates/ - contains all the files for the web-based config interface! This allows easy remote configuration of the display by simply visiting "nicoletrains.local" on the same WiFi network as the display.
- assets/ - ideally contains all images and other files needed by the app, but for now only has the font I used. May or may not change in the future.
- and lots of other stuff! ;)
