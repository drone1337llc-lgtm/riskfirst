#!/usr/bin/env bash
echo -n "localhost: "; curl -s --max-time 4 http://localhost:11434/api/version || echo FAIL
HOSTIP=$(ip route show default | awk '{print $3}')
echo; echo -n "hostip ($HOSTIP): "; curl -s --max-time 4 "http://$HOSTIP:11434/api/version" || echo FAIL
echo
