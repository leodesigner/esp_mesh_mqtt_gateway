#!/bin/bash

source venv/bin/activate

while true
do
  python gateway.py > /dev/null 2>&1
  date >> stats/gw_exit.log
  sleep 10
done

