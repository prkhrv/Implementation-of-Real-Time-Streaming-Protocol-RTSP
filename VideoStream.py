class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except:
            raise IOError
        self.frameNum = 0

    def nextFrame(self):
        """Get next frame."""
        data = self.file.read(5)  # Get the framelength from the first 5 bits
        if data:
            framelength = int(data)

            # Read the current frame
            data = self.file.read(framelength)
            self.frameNum += 1
        return data

    def frameNbr(self):
        """Get frame number."""
        return self.frameNum

    def get_total_frame(self):
        if (hasattr(self, 'totalFrame')):
            return self.totalFrame
        totalFrame = 0
        while True:
            data = self.file.read(5)
            if data:
                framelength = int(data)
                self.file.read(framelength)
                totalFrame += 1
            else:
                self.file.seek(0)
                break
        self.totalFrame = totalFrame
        return totalFrame

    def forward(self, frames):
        totalFrame = self.get_total_frame()
        if (frames + self.frameNum >= totalFrame):
            frames = totalFrame - self.frameNum

        for _ in range(frames - 1):
            self.nextFrame()

    def backward(self, frames):
        """Re-traverse to go backwards."""
        destination = self.frameNum - frames - 1
        self.frameNum = 0
        self.file.seek(0)
        if destination <= 0:
            return

        while self.frameNum < destination:
            data = self.file.read(5)
            if data:
                framelength = int(data)

                self.file.read(framelength)
                self.frameNum += 1
