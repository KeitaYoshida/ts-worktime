#!/bin/bash

# 接続情報
REMOTE_USER="tse"
REMOTE_HOST="192.168.11.103"
REMOTE_PATH="/home/tse/dev/tse-server/db_worktime/attendance.db"
LOCAL_PATH="/home/pi/dev/worktime/attendance.db"

# 転送実行
scp "$LOCAL_PATH" "${REMOTE_USER}@${REMOTE_HOST}:$REMOTE_PATH"
