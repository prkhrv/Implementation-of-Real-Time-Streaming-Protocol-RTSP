# Implementation-of-Real-Time-Streaming-Protocol-RTSP

The goal is to implement a streaming video server and client that communicate
using the Real-Time Streaming Protocol (RTSP) and send data using the Realtime
Transfer Protocol (RTP); and in order to achieve this, we will have to fullfill
these requirements.

## User manual
### Run the program

At the folder containing the source code, open two terminals.
In the first terminal, run the command:

```
python Server.py <server-port>
```
server-port is the port that you want to listen all the RTSP requests at.
Standard RTSP port is 554, but we have to choose > 1024. For example:
py Server.py 2000
  
At the second terminal, run the command:
  
```
python ClientLauncher.py <server-host> <server-port> <RTP-port> <video-file>
```

In this command:

* server-host is the IP address of the server, in my case it is 192.168.0.102,
it will be different in your case.
* server-post is the same at the port you created in the first terminal (2000).
* RTP-port is the port that you want to receive the RTP packets at, you can
choose a random positive integer.
* video-file the video name you want to be played, in this case it is
movie.Mjpeg

For example:

```
python ClientLauncher.py 192.168.0.102 2000 100 movie.Mjpeg
```
