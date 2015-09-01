#! /usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import chatwork

def usage():
    sys.stderr.write("Usage: {0} api-token room-id message\n".format(sys.argv[0]))

def main():
    if 4 != len(sys.argv):
        sys.stderr.write('3 arguments are needed\n')
        usage()
        exit(1)
    token = chatwork.ChatworkApiToken(sys.argv[1])
    room = chatwork.ChatworkRoom(sys.argv[2])
    message = sys.argv[3]
    client = chatwork.ChatworkClient(token)
    client.send_message(room, message)

if __name__ == '__main__':
    main()
