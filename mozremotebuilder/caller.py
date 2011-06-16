#!/usr/bin/python

# Caller class for mozremotebuilder's remote socket server

import socket
import sys
from utils import get_platform
from optparse import OptionParser

class BuildCaller():
    def __init__(self, host="localhost", port=9999, data="1"):
        self.host = host
        self.port = port

        # Create a socket (SOCK_STREAM means a TCP socket)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        system_platform = self.getPlatformString()

        self.data = str(data)+":macosx64" #default string

    def send(self):
        # Send data to server
        self.sock.connect((str(self.host), int(self.port)))
        self.sock.send(self.data + "\n")

    def getResponse(self):
        # Receive response data from the builder's socket server
        # Server sends (2) responses, first an ack after queue'ing
        # the changeset and the second is the built changeset
        confirm = self.sock.recv(1024)
        changeset = self.sock.recv(1024)

        self.sock.close()
        return changeset

    def getChangeset(self):
        # Returns response from server
        self.send()
        print "Sent request for changeset " + self.data
        print "Waiting for response from server..."
        return self.getResponse()

    def getPlatformString(self):
        platform = get_platform()
        if platform['name'] == "Windows":
            return "win32"
        elif platform['name'] == "Linux":
            if platform['bits'] == '64':
                return "linux64"
            return "linux"
        elif platform['name'] == "Mac":
            return "macosx64"

        print "ERROR, couldn't get platform."
        quit()



def cli():
    parser = OptionParser()
    parser.add_option("-c", "--changeset", dest="changeset",help="requested changeset",
                      metavar="", default=1)
    parser.add_option("-s", "--server", dest="hostname",help="build server to request from",
                      metavar="xxx.xxx.xxx.xxx", default="localhost")
    parser.add_option("-p", "--port", dest="port",help="server port",
                      metavar="9999", default=9999)
    (options, args) = parser.parse_args()

    caller = BuildCaller(host=options.hostname, port=options.port, data=options.changeset)

    response = caller.getChangeset()
    print response

if __name__ == "__main__":
    cli()
