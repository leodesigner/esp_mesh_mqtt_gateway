# Esp32/ESP8266 espnow mesh mqtt gateway

It can be run on the RaspberryPI, OrangePI or any capable machine.

gateway.py - gateway that connects to mqtt broker and relay messages between mesh and mqtt  
stats_listener.py - collects and displays node stats, listen to mesh mqtt messages, stores nodes names / mac_addr  
config-sample.py should be renamed to config.py, don't forget to specify your mqtt broker hostname  


The gateway node (esp32/esp8266) 

https://github.com/leodesigner/esp_mesh_gw_node

should be connected via usb to the host running these scripts.


Mesh node example: https://github.com/leodesigner/esp_mesh_pir_sensor
