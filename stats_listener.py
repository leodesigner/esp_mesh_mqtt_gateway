# mesh stats listener
# receives stats messages and maps mac addresses for new nodes

import paho.mqtt.client as mqtt
import logging
import time
import csv
import base64
import sys
import select
from datetime import datetime
import networkx as nx

import config

# name -> mac mapping
name_mac = {}
mac_name = {}
mac_req_list = []
stats_req_list = []

DG = nx.DiGraph()

logging.basicConfig(format='%(message)s', level=logging.INFO)

# keyboard listener
def heardEnter():
    i,o,e = select.select([sys.stdin],[],[],0.0001)
    for s in i:
        if s == sys.stdin:
            input = sys.stdin.readline()
            return input
    return False


def g_add_node(src_node, dest_node, weight):
    # logging.info(f'+ Adding node: {src_node} -> {dest_node} w: {weight}')
    DG.add_edge(src_node, dest_node, weight=weight)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    logging.info('MQTT Connected with result code ' + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe(config.mqtt_from_mesh_prefix + '#')


def convert2hex(message):
    return ','.join(hex(ord(x))[2:] for x in message)


def remove_prefix(text, prefix):
    return text[text.startswith(prefix) and len(prefix):]


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    topic = remove_prefix(msg.topic, config.mqtt_from_mesh_prefix)
    value = msg.payload.decode('ascii', 'replace')
    logging.info('> ' + msg.topic + ' ' + value)
    node_name, topic2 = topic.split("/", 1)
    #logging.info('node name: ' + node_name)

    if name_mac.get(node_name, False) == False:
        if node_name not in mac_req_list and node_name not in config.nodes_exclude:
            mac_req_list.append(node_name)

    if topic.endswith('/string/mac_addr/value'):
        if name_mac.get(node_name, False) == False:
            # store mac addr for node
            name_mac[node_name] = value
            mac_name[value] = node_name
            logging.info('Storing mac addr for node name: ' +
                         node_name + ' mac: ' + value)
            save_mac_names_db()

    if topic.endswith('/bin/stats/value'):
        # Parse stats bas64 encoded objects:  mac_addr[6] last_seen[4] received_pkts[2] duplicate_pkts[2]
        logging.info('Processing stats from node: ' + node_name)
        b = base64.b64decode(value)
        for idx in range(0, len(b)//14):
            o = idx * 14
            mac_addr = ':'.join('%02x' % c for c in b[o:o+6])
            last_seen_ts = (b[o+6]) + (b[o+7] << 8) + (b[o+8] << 16) + (b[o+9] << 24)
            last_seen_d = datetime.utcfromtimestamp(last_seen_ts).strftime('%Y-%m-%d %H:%M:%S')
            received_pkts = (b[o+10]) + (b[o+11] << 8)
            duplicate_pkts = (b[o+12]) + (b[o+13] << 8)
            seen_node_name = mac_name.get(mac_addr,'---')
            logging.info(f'Mac: {idx} {mac_addr} name: ' + '%15s' % seen_node_name + f' seen: {last_seen_d} rcv: {received_pkts} dup:{duplicate_pkts}')
            if time.time() - 10 * 60 < last_seen_ts:
                g_add_node(seen_node_name, node_name, 1)


# m/dimmer/led1/value -> nodename/dimmer/led1/value
def translate_topic(src_node, from_mesh_topic):
    _, raw_topic = from_mesh_topic.split("/", 1)
    mqtt_topic = src_node + '/' + raw_topic
    return mqtt_topic


def save_mac_names_db():
    with open('stats/mac_names.csv', 'w', newline='') as csvfile:
        fieldnames = ['name', 'mac_addr']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for name, mac in name_mac.items():
            writer.writerow({'name': name, 'mac_addr': mac})

    csvfile.close()


logging.info('Stats listener starting...')
logging.info('Press "g Enter" to build NetworkX graph and export to Gexf format\n')

try:
    with open('stats/mac_names.csv', 'r', newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            print(row['name'], row['mac_addr'])
            name_mac[row['name']] = str(row['mac_addr'])
            mac_name[str(row['mac_addr'])] = row['name']
except:
    logging.info(
        'mac names database file not found (mac_names.csv) , starting with empty db.')

logging.info('---------')

# connect to mqtt broker
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(config.mqtt_host, config.mqtt_port, 60)
# start mqtt async loop
client.loop_start()  # async loop


ts_ms = int(time.time() * 1000)
ts_ms_sr = int(time.time() * 1000)

stats_mode = 0

while True:
    time.sleep(0.1)

    if int(time.time() * 1000) > ts_ms + 15000:
        ts_ms = int(time.time() * 1000)
        logging.info(".")
        if len(mac_req_list) > 0:
            logging.info('Request list size: %u', len(mac_req_list))
            node_name = mac_req_list.pop()
            logging.info('Requesting mac_addr from: ' + node_name)
            client.publish(config.mqtt_to_mesh_prefix +
                           node_name + '/ota/set', 'mac_addr')

    kinput = heardEnter()
    if kinput != False:
        kinput = kinput.rstrip()
        if str(kinput) == 'g' and stats_mode == 0:
            logging.info('... Building graph from existing data ...')
            for name, mac in name_mac.items():
                logging.info('> ' + name)
                if name not in config.nodes_exclude:
                    stats_req_list.append(name)
                    stats_mode = 1

    if int(time.time() * 1000) > ts_ms_sr + 3000:
        ts_ms_sr = int(time.time() * 1000)
        if stats_mode > 0:
            if len(stats_req_list) > 0:
                node_name = stats_req_list.pop()
                logging.info('Requesting stats from: %s', node_name)
                client.publish(config.mqtt_to_mesh_prefix +
                            node_name + '/ota/set', 'stats')
                continue
            if len(stats_req_list) == 0:
                logging.info('*** Graph processing ***')
                stats_mode = 0
                nx.write_gexf(DG, "stats/graph.gexf")

