# mesh mqtt gateway (main node)

#import serial
from periphery import Serial
import io
import time
import random, string
from datetime import datetime
import paho.mqtt.client as mqtt
import logging

import config

# to allow send stored messages after node subscribes
message_cache = {}

#logging.getLogger().setLevel('INFO')
logging.basicConfig(format='%(message)s', level=logging.INFO)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    logging.info('MQTT Connected with result code ' + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(config.mqtt_to_mesh_prefix + '#')


def convert2hex(message):
    return ','.join(hex(ord(x))[2:] for x in message)


def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]


def mesh_publish_topic(topic, value):
    # cleanup and prepare value
    value = str(value).rstrip(" \r\n")
    # send message to the mesh #  REQC ttl timeout try_cnt [message]
    msgid = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
    message1 = f'MQTT {config.node_name}/{msgid}\nP:{topic} {value}\n\0'
    message = 'REQC ' + str(config.mesh_send_ttl) + ' ' + str(config.pub_timeout) + ' ' + str(config.pub_try_cnt) 
    message += ' [' + convert2hex(message1) + '];\n'
    logging.info('>>> MESH Publishing: ' + message)
    sio.write(message.encode())
    sio.flush()


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    logging.info('From MQTT broker: ' + msg.topic + ' ' + str(msg.payload))
    topic = remove_prefix(msg.topic, config.mqtt_to_mesh_prefix)
    value = msg.payload.decode('ascii', 'replace')

    if topic.startswith(config.node_name + '/'):
        # process internal commands
        topic_parts = topic.split('/')
        if topic_parts[1] == 'ota' and topic_parts[2] == 'set':
            command = value.upper() + ';'
            sio.write(command.encode())
            sio.flush()
        return

    # store message in the internal cache
    message_cache[topic] = msg
    # publush to mesh
    mesh_publish_topic(topic, value)


def readline(sio, timeout = 3000):
    start_ms = int(time.time() * 1000)
    res = ''
    while int(time.time() * 1000) - start_ms < timeout: 
        c = sio.read(1, 0.1).decode('ascii','replace')
        if c != '':
            res = res + c
            start_ms = int(time.time() * 1000)
            if c == '\n' or c == '\r':
                return res
    return res


def send_expect(sio, send, expect, timeout_ms = 3000):
    sio.write(send.encode())
    sio.flush()
    ts_ms = int(time.time() * 1000)
    elapsed = 0
    while timeout_ms - elapsed > 0:
        s = readline(sio).rstrip()
        if s != '':
            logging.info("rec: %s",s)
        if s.startswith(expect):
            return s
        elapsed = int(time.time() * 1000) - ts_ms
    return False


def send_rtc():
    sio.write("RTC SET ".encode())
    sio.write( str(int(time.time())).encode() )
    sio.write(';'.encode())
    sio.flush()


def init_mesh():
    send_expect(sio, f'ROLE MASTER {config.mesh_send_ttl};', f'ACK {config.mesh_send_ttl};')
    send_rtc()
    send_expect(sio, 'INIT;', 'ACKINIT;')


# m/dimmer/led1/value -> nodename/dimmer/led1/value
def translate_topic(src_node, from_mesh_topic):
    _, raw_topic = from_mesh_topic.split("/", 1)
    mqtt_topic = src_node + '/' + raw_topic
    return mqtt_topic


mesh_initialized = False

with Serial(config.serial_port, config.serial_speed) as sio:
    #sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser), errors='replace', encoding='ascii')
    rebooted = False
    while rebooted == False:
        rebooted = send_expect(sio, "REBOOT;", "READY;")
    init_mesh()
    mesh_initialized = True
    ts_ms = int(time.time() * 1000)

    # connect to mqtt broker
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.mqtt_host, config.mqtt_port, 60)
    # start mqtt async loop
    client.loop_start() # async loop

    while True:
        s = readline(sio).rstrip(' \r\n')

        if s != "":
            logging.info("-<< %s", s)

            if s.startswith('MQTT '):
                try:
                    prefix, src_node, msgid, cmd, topic, value = s.split(' ', 5)
                except:
                    value = ''
                    prefix, src_node, msgid, cmd, topic = s.split(' ', 4)
                mqtt_topic = translate_topic(src_node, topic)
                if cmd == 'P':
                    logging.info('Publishing to broker: %s %s', config.mqtt_from_mesh_prefix + mqtt_topic, value)
                    client.publish(config.mqtt_from_mesh_prefix + mqtt_topic, value)
                if cmd == 'S':
                    logging.info('Subscribe, send last message to mesh: ' + value)
                    if mqtt_topic in message_cache:
                        value = message_cache[mqtt_topic].payload.decode('ascii')
                        if value != '':
                            mesh_publish_topic(mqtt_topic, value)
                    # TODO: add broadcast subscribe .../#
                if cmd == 'G':
                    logging.info('Get, send last message to mesh')
                    if mqtt_topic in message_cache:
                        value = message_cache[mqtt_topic].payload.decode('ascii')
                        if value != '':
                            mesh_publish_topic(mqtt_topic, value)

            if s.startswith('REC '):
                prefix, p1, p2 = s.split(' ', 3)
                p2 = p2.translate(dict.fromkeys(map(ord, '[];')))
                arr = p2.split(',')
                if (len(arr) == 4 and arr[3] == '0'):
                    arr = arr[:-1]
                    p2 = ''.join([ bytes.fromhex(c).decode('ascii', 'replace') for c in arr ])
                    if p2 == 'ACK':
                        logging.info('ACK Received: %s', p1)

            if s.startswith('READY;'):
                mesh_initialized = False
                init_mesh()
                mesh_initialized = True

            if s.startswith('STATS') or s.startswith('MAC_ADDR'):
                prefix, p1 = s.split(' ')
                topic = config.node_name + '/bin/' + prefix.lower() + '/value'
                client.publish(config.mqtt_from_mesh_prefix + topic, p1.rstrip(';'))

            if s.startswith('STATS_OLD'):
                prefix, p1, p2 = s.split(' ', 3)
                p2 = p2.translate(dict.fromkeys(map(ord, '[];')))
                arr = p2.split(',')
                bin_len = len(arr)
                # post it as a blob under nodename/stats
                bin_blob = bytes([int(x,base=16) for x in arr])
                topic = config.node_name + '/stats'
                client.publish(config.mqtt_from_mesh_prefix + topic, bin_blob)

        # time sync
        if int(time.time() * 1000) > ts_ms + 300000:
            ts_ms = int(time.time() * 1000)
            # Time sync
            logging.info("Sending timesync: %d", int(time.time()))
            send_rtc()

