from tkinter import *
import tkinter.messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket
import threading
import time
import io
import sys

from RtpPacket import RtpPacket

TIME_PER_FRAME = 0.04
TIME_STEP = 5


class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    DESCRIBE = 4
    FORWARD = 5
    BACKWARD = 6
    SWITCH = 7

    # Initiation..

    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.lock = threading.Lock()
        self.count = 0
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Extend 1
        self.totalBytes = 0
        self.lostNum = 0
        self.statLost = 0
        self.startTime = 0
        self.totalPlayTime = 0
        self.dataRate = 0
        # Extend 3
        self.describable = False
        # Extend 4
        self.duration = 0
        self.predict = 1
        self.isBackward = 0

    def createWidgets(self):
        """Build GUI."""
        # Create Play/Pause button
        self.start = Button(self.master, width=16,
                            padx=3, pady=3, bg="#61baff")
        self.start["text"] = "Play ▶"
        self.start["command"] = self.playOrPause
        self.start.grid(row=2, column=2, padx=2, pady=2)

        # Create Teardown button
        self.teardown = Button(self.master, width=16,
                               padx=3, pady=3, bg="#ff614f")
        self.teardown["text"] = "Stop ■"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=2, column=3, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=5,
                        sticky=W+E+N+S, padx=5, pady=5)

        # Create a label to display the stats
        self.label2 = Label(self.master)
        self.label2["text"] = "Total Bytes Received: 0"
        self.label2.grid(row=3, column=1, columnspan=4, padx=5, pady=5)
        self.label3 = Label(self.master)
        self.label3["text"] = "Packets Lost Rate: 0"
        self.label3.grid(row=4, column=1, columnspan=4, padx=5, pady=5)
        self.label4 = Label(self.master)
        self.label4["text"] = "Data Rate (bytes/sec): 0"
        self.label4.grid(row=5, column=1, columnspan=4, padx=5, pady=5)

        # Create Describe button
        self.setup = Button(self.master, width=16, padx=3, pady=3, bg="yellow")
        self.setup["text"] = "Describe ⓘ"
        self.setup["command"] = self.describe
        self.setup.grid(row=1, column=1, padx=2, pady=2)

        # Create a label to display total time of the movie
        self.durationBox = Label(
            self.master, width=16, text="Total time: 00:00")
        self.durationBox.grid(row=1, column=3, columnspan=1, padx=5, pady=5)

        # Create a label to display remaining time of the movie
        self.remainTimeBox = Label(
            self.master, width=16, text="Remaining time: 00:00")
        self.remainTimeBox.grid(row=1, column=2, columnspan=1, padx=5, pady=5)

        # Create forward button
        self.forward = Button(self.master, width=15, padx=3,
                              pady=3, bg="#ffd4fb")
        self.forward["text"] = "⏩️"
        self.forward["command"] = self.forwardMovie
        self.forward.grid(row=2, column=4, columnspan=2,
                          padx=2, sticky=E + W, pady=2)

        # Create backward button
        self.backward = Button(self.master, width=15, padx=3,
                               pady=3, bg="#ffd4fb")
        self.backward["text"] = "⏪"
        self.backward["command"] = self.backwardMovie
        self.backward.grid(row=2, column=1, padx=2, sticky=E + W, pady=2)

        self.fileSwitch = Text(self.master, height=1, width=13)
        self.fileSwitch.grid(row=1, column=4, padx=2, sticky=E + W, pady=2)

        self.switch = Button(self.master, width=2, bg="#57ff84")
        self.switch["text"] = "SW"
        self.switch["command"] = self.switchMovie
        self.switch.grid(row=1, column=5, padx=2, pady=2, sticky=E + W)

    def updateStat(self):
        self.label2["text"] = "Total Bytes Received: " + str(self.totalBytes)
        self.label3["text"] = "Packets Lost Rate: " + str(self.statLost)
        self.label4["text"] = "Data Rate (bytes/sec): " + str(self.dataRate)

    def exitClient(self):
        """Teardown button handler."""
        try:
            self.sendRtspRequest(self.TEARDOWN)
        except:
            print("Lost connection to server")

        self.master.destroy()
        if self.lock.locked():
            self.lock.release()
        sys.exit()

    def describe(self):
        """Describe button handler."""
        if self.describable:
            self.sendRtspRequest(self.DESCRIBE)

    def playOrPause(self):
        if self.state == self.INIT or self.state == self.READY:
            self.playMovie()
            self.start["text"] = "Pause ⏸"
        else:
            self.pauseMovie()
            self.start["text"] = "Play ▶"

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)
            return

        if self.state == self.READY:
            self.describable = True
            # Create a new thread to listen for RTP packets
            self.playEvent = threading.Event()
            self.playEvent.clear()
            threading.Thread(target=self.listenRtp).start()
            self.sendRtspRequest(self.PLAY)

    def forwardMovie(self):
        self.sendRtspRequest(self.FORWARD)

    def backwardMovie(self):
        self.sendRtspRequest(self.BACKWARD)

    def switchMovie(self):
        fileName = self.fileSwitch.get("1.0", "end-1c").strip()
        if fileName and fileName != self.fileName:
            self.oldFile = self.fileName
            self.fileName = fileName
            self.sendRtspRequest(self.SWITCH)

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)

                curTime = time.time()
                self.totalPlayTime += curTime - self.startTime
                self.startTime = curTime

                if data:
                    with self.lock:
                        pre = self.predict
                        rtpPacket = RtpPacket()
                        rtpPacket.decode(data)

                        curFrameNbr = rtpPacket.seqNum()
                        print(
                            f"current Seq Num: {curFrameNbr}")

                        # Total bytes received
                        self.totalBytes += len(rtpPacket.getPayload())

                        # Lost packets
                        if self.frameNbr + self.predict != curFrameNbr:
                            self.lostNum += curFrameNbr - self.frameNbr - self.predict
                            print(f"[*] Lost {self.lostNum} packets")

                        # Loss rate
                        self.statLost = 0 if self.lostNum == 0 else self.lostNum / curFrameNbr

                        # Data rate
                        self.dataRate = round(
                            self.totalBytes / self.totalPlayTime, 2)

                        # Update
                        self.updateStat()

                        # Update time label
                        currentTime = curFrameNbr * TIME_PER_FRAME
                        self.remainTimeBox.configure(
                            text="Remaining time: %02d:%02d" % ((self.duration - currentTime) // 60,
                                                                int((self.duration - currentTime) % 60 + 0.9)))

                        if curFrameNbr > self.frameNbr or self.isBackward > 0:  # Discard the late packet
                            self.frameNbr = curFrameNbr
                            if self.count == 0:
                                self.count += 1
                            self.updateMovie(rtpPacket.getPayload())
                            self.isBackward -= 1

                        if pre == self.predict:
                            self.predict = 1

            except:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.playEvent.isSet():
                    break

                # Upon receiving ACK for TEARDOWN request,
                # close the RTP socket
                if self.teardownAcked == 1:
                    self.rtpSocket.shutdown(socket.SHUT_RDWR)
                    self.rtpSocket.close()
                    break

    def updateMovie(self, image_data):
        """Update the image file as video frame in the GUI."""
        image = Image.open(io.BytesIO(image_data))
        photo = ImageTk.PhotoImage(image)
        self.label.configure(image=photo, height=288)
        self.label.image = photo

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            tkMessageBox.showwarning(
                'Connection Failed', 'Connection to \'%s\' failed.' % self.serverAddr)

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # -------------
        # TO COMPLETE
        # -------------

        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = 1

            # Write the RTSP request to be sent.
            # request = ...
            request = "SETUP " + str(self.fileName) + " RTSP/1.0\nCSeq: " + str(
                self.rtspSeq) + "\nTransport: RTP/UDP; client_port= " + str(self.rtpPort)
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.SETUP
            threading.Thread(target=self.recvRtspReply).start()

        # Play request
        elif requestCode == self.PLAY and self.state == self.READY:
            # save the time start
            self.startTime = time.time()

            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1

            # Write the RTSP request to be sent.
            # request = ...
            request = "PLAY " + str(self.fileName) + " RTSP/1.0\nCSeq: " + \
                str(self.rtspSeq) + "\nSession: " + str(self.sessionId)
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.PLAY

        # Pause request
        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1

            # Write the RTSP request to be sent.
            # request = ...
            request = "PAUSE " + str(self.fileName) + " RTSP/1.0\nCSeq: " + \
                str(self.rtspSeq) + "\nSession: " + str(self.sessionId)
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.PAUSE

        # Teardown request
        elif requestCode == self.TEARDOWN and not self.state == self.INIT:
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
            # Write the RTSP request to be sent.
            # request = ...
            request = "TEARDOWN " + str(self.fileName) + " RTSP/1.0\nCSeq: " + str(
                self.rtspSeq) + "\nSession: " + str(self.sessionId)
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.TEARDOWN

        # Describe request
        elif requestCode == self.DESCRIBE:
            self.rtspSeq = self.rtspSeq + 1
            request = "DESCRIBE " + str(self.fileName) + " RTSP/1.0\nCSeq: " + str(
                self.rtspSeq) + "\nSession: " + str(self.sessionId)
            self.requestSent = self.DESCRIBE

        # Forward request
        elif requestCode == self.FORWARD:
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
            # Write the RTSP request to be sent.
            # request = ...
            request = "FORWARD %s RTSP/1.0\nCSeq: %d\nSESSION: %d" % (
                self.fileName, self.rtspSeq, self.sessionId)
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.FORWARD

        # Backward request
        elif requestCode == self.BACKWARD:
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
            # Write the RTSP request to be sent.
            # request = ...
            request = "BACKWARD %s RTSP/1.0\nCSeq: %d\nSESSION: %d" % (
                self.fileName, self.rtspSeq, self.sessionId)
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.BACKWARD

        # SWITCH request
        elif requestCode == self.SWITCH:
            # Update RTSP sequence number.
            # ...
            self.rtspSeq = self.rtspSeq + 1
            # Write the RTSP request to be sent.
            # request = ...
            request = "SWITCH %s RTSP/1.0\nCSeq: %d\nSESSION: %d" % (
                self.fileName, self.rtspSeq, self.sessionId)
            # Keep track of the sent request.
            # self.requestSent = ...
            self.requestSent = self.SWITCH
        else:
            return

        # Send the RTSP request using rtspSocket.
        # ...
        self.rtspSocket.send(request.encode("utf-8"))
        print('\nData sent:\n' + request)

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            reply = self.rtspSocket.recv(1024)

            if reply:
                with self.lock:
                    self.parseRtspReply(reply.decode("utf-8"))

            # Close the RTSP socket upon requesting Teardown
            if self.requestSent == self.TEARDOWN:
                self.rtspSocket.shutdown(socket.SHUT_RDWR)
                self.rtspSocket.close()
                break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        print("-" * 40 + "\nData received:\n" + data)
        lines = data.split('\n')
        seqNum = int(lines[1].split(' ')[1])

        # Process only if the server reply's sequence number is the same as the request's
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(' ')[1])
            # New RTSP session ID
            if self.sessionId == 0:
                self.sessionId = session

            # Process only if the session ID is the same
            if self.sessionId == session:
                if int(lines[0].split(' ')[1]) == 200:
                    if self.requestSent == self.SETUP:
                        # -------------
                        # TO COMPLETE
                        # -------------
                        # Update RTSP state.
                        # self.state = ...
                        self.duration = int(lines[3].split(
                            ' ')[1]) * TIME_PER_FRAME
                        self.durationBox.configure(
                            text="Total time: %02d:%02d" % (self.duration // 60, self.duration % 60))
                        self.state = self.READY

                        # Open RTP port.
                        self.playMovie()
                        self.openRtpPort()
                    elif self.requestSent == self.PLAY:
                        # self.state = ...
                        self.state = self.PLAYING
                    elif self.requestSent == self.PAUSE:
                        # self.state = ...
                        self.state = self.READY
                        # The play thread exits. A new thread is created on resume.
                        self.playEvent.set()
                    elif self.requestSent == self.TEARDOWN:
                        # self.state = ...
                        self.state = self.INIT
                        # Flag the teardownAcked to close the socket.
                        self.teardownAcked = 1
                    elif self.requestSent == self.FORWARD:
                        if self.frameNbr + TIME_STEP / TIME_PER_FRAME < self.duration / TIME_PER_FRAME:
                            self.predict = int(TIME_STEP / TIME_PER_FRAME)
                        else:
                            self.predict = int(
                                self.duration / TIME_PER_FRAME) - self.frameNbr
                    elif self.requestSent == self.BACKWARD:
                        if self.frameNbr - TIME_STEP / TIME_PER_FRAME > 0:
                            self.predict = - \
                                int(TIME_STEP / TIME_PER_FRAME)
                        else:
                            self.predict = - (self.frameNbr - 1)
                        self.isBackward = int(TIME_STEP / TIME_PER_FRAME)
                    elif self.requestSent == self.SWITCH:
                        self.predict = 1
                        self.frameNbr = 0
                        self.duration = int(lines[3].split(
                            ' ')[1]) * TIME_PER_FRAME
                        self.durationBox.configure(
                            text="Total time: %02d:%02d" % (self.duration // 60, self.duration % 60))

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        # -------------
        # TO COMPLETE
        # -------------
        # Create a new datagram socket to receive RTP packets from the server
        # self.rtpSocket = ...
        self.rtpSocket.settimeout(0.5)
        # Set the timeout value of the socket to 0.5sec
        # ...

        try:
            # Bind the socket to the address using the RTP port given by the client user
            # ...
            self.rtpSocket.bind((self.serverAddr, self.rtpPort))
        except:
            tkMessageBox.showwarning(
                'Unable to Bind', 'Unable to bind PORT=%d' % self.rtpPort)

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:  # When the user presses cancel, resume playing.
            self.playMovie()
