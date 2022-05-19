from random import randint
import threading
import socket
from Client import TIME_PER_FRAME

from VideoStream import VideoStream
from RtpPacket import RtpPacket

TIME_PER_FRAME = 0.04
TIME_STEP = 5


class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    DESCRIBE = 'DESCRIBE'
    FORWARD = 'FORWARD'
    BACKWARD = 'BACKWARD'
    SWITCH = 'SWITCH'

    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2

    clientInfo = {}

    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        self.lock = threading.Lock()

    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()

    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:
            data = connSocket.recv(256)
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))

    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        # Get the request type
        request = data.split('\n')
        line1 = request[0].split(' ')
        requestType = line1[0]

        # Get the media file name
        filename = line1[1]

        # Get the RTSP sequence number
        seq = request[1].split(' ')

        # Process SETUP request
        if requestType == self.SETUP:
            if self.state == self.INIT:
                # Update state
                print("processing SETUP\n")

                try:
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])

                # Generate a randomized RTSP session ID
                self.clientInfo['session'] = randint(100000, 999999)

                # Send RTSP reply
                self.replySetup(self.OK_200, seq[1])

                # Get the RTP/UDP port from the last line
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]

        # Process PLAY request
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING

                # Create a new socket for RTP/UDP
                self.clientInfo["rtpSocket"] = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM)

                self.replyRtsp(self.OK_200, seq[1])

                # Create a new thread and start sending RTP packets
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker'] = threading.Thread(
                    target=self.sendRtp)
                self.clientInfo['worker'].start()

        # Process PAUSE request
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY

                self.clientInfo['event'].set()

                self.replyRtsp(self.OK_200, seq[1])

        # Process TEARDOWN request
        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")

            self.clientInfo['event'].set()

            self.replyRtsp(self.OK_200, seq[1])

            # Close the RTP socket
            self.clientInfo['rtpSocket'].close()

        elif requestType == self.DESCRIBE:
            print("processing DESCRIBE\n")
            self.replyDescribe(self.OK_200, seq[1])

        # Process FORWARD request
        elif requestType == self.FORWARD and self.state != self.INIT:
            print("processing FORWARD\n")
            with self.lock:
                self.clientInfo['videoStream'].forward(
                    int(TIME_STEP / TIME_PER_FRAME))
                self.replyRtsp(self.OK_200, seq[1])

        # Process BACKWARD request
        elif requestType == self.BACKWARD and self.state != self.INIT:
            print("processing BACKWARD\n")
            with self.lock:
                self.clientInfo['videoStream'].backward(
                    int(TIME_STEP / TIME_PER_FRAME))
                self.replyRtsp(self.OK_200, seq[1])

        # Process SWITCH request
        elif requestType == self.SWITCH and self.state != self.INIT:
            print("processing SWITCH\n")
            try:
                with self.lock:
                    self.clientInfo['videoStream'] = VideoStream(filename)
            except IOError:
                self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                return
            self.replySetup(self.OK_200, seq[1])

    def sendRtp(self):
        """Send RTP packets over UDP."""
        while True:
            self.clientInfo['event'].wait(TIME_PER_FRAME)

            # Stop sending if request is PAUSE or TEARDOWN
            if self.clientInfo['event'].isSet():
                break

            with self.lock:
                data = self.clientInfo['videoStream'].nextFrame()
                if data:
                    frameNumber = self.clientInfo['videoStream'].frameNbr()
                    try:
                        address = self.clientInfo['rtspSocket'][1][0]
                        port = int(self.clientInfo['rtpPort'])
                        self.clientInfo['rtpSocket'].sendto(
                            self.makeRtp(data, frameNumber), (address, port))
                    except:
                        print("Connection Error")

    def makeRtp(self, payload, frameNbr):
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = 26  # MJPEG type #PayloadType
        seqnum = frameNbr
        ssrc = 0

        rtpPacket = RtpPacket()

        rtpPacket.encode(version, padding, extension, cc,
                         seqnum, marker, pt, ssrc, payload)

        return rtpPacket.getPacket()

    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            #print("200 OK")
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + \
                '\nSession: ' + str(self.clientInfo['session'])
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode())

        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")

    def describe(self):
        seq1 = "v=0\nm=video " + str(self.clientInfo['rtpPort']) + " RTP/AVP 26\na=control:streamid=" \
            + str(self.clientInfo['session']) + \
            "\na=mimetype:string;\"video/Mjpeg\"\n"
        seq2 = "Content-Base: " + str(self.clientInfo['videoStream'].filename) + "\nContent-Length: " \
            + str(len(seq1)) + "\n"
        return seq2 + seq1

    def replyDescribe(self, code, seq):
        des = self.describe()
        if code == self.OK_200:
            reply = "RTSP/1.0 200 OK\nCSeq: " + seq + "\nSession: " + \
                str(self.clientInfo['session']) + "\n" + des
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode())
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")

    def replySetup(self, code, seq):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            with self.lock:
                totalTime = self.clientInfo['videoStream'].get_total_frame()
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + \
                str(self.clientInfo['session']) + \
                '\nTotalTime: ' + str(totalTime)
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode())
        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")