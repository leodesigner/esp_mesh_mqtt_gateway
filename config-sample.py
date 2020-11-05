# MESH configuration file

# serial port that esp gateway connected to
serial_port = '/dev/ttyUSB0'
serial_speed = 230400

# master / main node name (keep it short to reduce mqtt message size)
node_name = 'm'

# mesh ttl, how many nodes can restransmit message 
mesh_send_ttl = 5

# publish timeout (milliseconds)
pub_timeout = 50

# publish restransmit try count 
pub_try_cnt = 10

# mqtt topic prefix for messages from MESH (sensors data)
mqtt_from_mesh_prefix = 'mesh/'

# mqtt topic prefix for message to MESH (commands)
mqtt_to_mesh_prefix = 'mesh-/'

# MQTT broker
mqtt_host = 'mqtt.local'
mqtt_port = 1883
