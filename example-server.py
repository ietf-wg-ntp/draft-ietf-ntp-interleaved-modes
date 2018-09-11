#!/usr/bin/python3
# Minimal server implementation with support for the interleaved mode

import collections
import random
import socket
import struct
import time

class NtpServer:
    def __init__(self):
        # Map of server receive timestamps to transmit timestamps
        self.saved_timestamps = {}

        # Queue of timestamps removed from the map to limit its size
        self.timestamp_queue = collections.deque()
        self.max_timestamps = 1000

        self.precision = -20
        self.stratum = 5
        self.root_delay = 0
        self.root_dispersion = 0
        self.reference_id = 0x7f000001

    def read_clock(self):
        return int((time.time() + 0x83aa7e80) * 4294967296) ^ \
               int(random.getrandbits(32 + self.precision))

    def check_request(self, packet):
        if len(packet) < 48:
            return False;

        # Check mode and version
        if packet[0] & 7 != 3 or (packet[0] >> 3) & 7 not in (1, 2, 3, 4):
            return False;

        return True

    def make_response(self, request, address, server_receive, server_pre_transmit):
        (lvm, _, poll, _, _, _, _, _, origin_ts, receive_ts, transmit_ts) = \
                struct.unpack('!BBbbIIIQQQQ', request[:48])

        print("Request from {:22s}: org={:016x} rx={:016x} tx={:016x}".
                format("{}:{}".format(address[0], address[1]), origin_ts, receive_ts, transmit_ts))

        lvm = (lvm & 0x3f) + 1

        if receive_ts != transmit_ts and origin_ts in self.saved_timestamps:
            print("Response in interleaved mode       : ", end="")
            transmit_ts = self.saved_timestamps[origin_ts]
            origin_ts = receive_ts
            receive_ts = server_receive
        else:
            print("Response in basic mode             : ", end="")
            origin_ts = transmit_ts
            receive_ts = server_receive
            transmit_ts = server_pre_transmit

        print("org={:016x} rx={:016x} tx={:016x}".
                format(origin_ts, receive_ts, transmit_ts))

        return struct.pack('!BBbbIIIQQQQ', lvm, self.stratum, poll, self.precision,
                           self.root_delay, self.root_dispersion, self.reference_id,
                           receive_ts, origin_ts, receive_ts, transmit_ts)

    def save_timestamps(self, receive_ts, transmit_ts):
        assert(receive_ts not in self.saved_timestamps)
        assert(len(self.saved_timestamps) <= self.max_timestamps)
        assert(len(self.saved_timestamps) == len(self.timestamp_queue))

        self.saved_timestamps[receive_ts] = transmit_ts

        self.timestamp_queue.append(receive_ts)
        if len(self.timestamp_queue) > self.max_timestamps:
            self.saved_timestamps.pop(self.timestamp_queue[0])
            self.timestamp_queue.popleft()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 123))

        while True:
            request, address = sock.recvfrom(1024)

            receive_ts = self.read_clock()

            # Avoid conflict with a previous receive timestamp, e.g. after
            # a backward step of the clock
            while receive_ts in self.saved_timestamps:
                receive_ts += 1

            if not self.check_request(request):
                continue

            pre_transmit_ts = self.read_clock()

            # Make sure the transmit and receive timestamps are different
            while pre_transmit_ts == receive_ts:
                pre_transmit_ts = self.read_clock()

            response = self.make_response(request, address, receive_ts, pre_transmit_ts)
            try:
                sock.sendto(response, address)
            except Exception:
                continue

            # This should be the actual transmit timestamp of the response
            transmit_ts = self.read_clock()
            self.save_timestamps(receive_ts, transmit_ts)

        sock.close()


if __name__ == "__main__":
    server = NtpServer()
    server.run()
